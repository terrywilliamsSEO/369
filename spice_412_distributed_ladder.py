#!/usr/bin/env python3
"""Export and optionally run a distributed-ladder SPICE model for 4->8->12.

This track translates the successful normalized spatial phase-matching model
into an ngspice-compatible envelope ladder.  Each ladder cell stores real and
quadrature envelopes for the source, generated, and target bands on unit
capacitors; behavioral current sources implement propagation, distributed
nonlinear mixing, phase mismatch, passive loss, and saturation loss.

The netlists are normalized topology-screening artifacts, not hardware-realistic
component values.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import spice_412_export as spice_base


OUT_DIR = Path("runs") / "spice_412_distributed_ladder"
TSTOP = 96.0
TSTEP = 0.04
EPS = 1e-18
EXECUTION_STATUSES = (
    "exported",
    "skipped_no_ngspice",
    "ran_successfully",
    "failed_to_converge",
    "parser_failed",
)
REQUIRED_NETLISTS = (
    "phase_matched_codirectional_ladder.cir",
    "qpm_ladder.cir",
    "mismatched_ladder_control.cir",
    "lumped_equivalent_control.cir",
    "linear_no_nonlinearity_control.cir",
    "detuned_target_control.cir",
    "shuffled_frequency_control.cir",
    "direct_4plus8_ceiling_reference.cir",
)


@dataclass(frozen=True)
class LadderCase:
    name: str
    filename: str
    topology: str
    role: str = "discovery"
    source_mode: float = 4.0
    generated_mode: float = 8.0
    target_mode: float = 12.0
    k4: float = 1.0
    k8: float = 2.0
    k12: float = 3.0
    delta_k_448: float = 0.0
    delta_k_4812: float = 0.0
    qpm_period_448: float = 0.0
    qpm_period_4812: float = 0.0
    qpm_duty_cycle: float = 0.5
    grating_kind: str = "none"
    coupling_sign_pattern: str = "uniform"
    chain_length: float = 24.0
    cell_count: int = 32
    group_velocity_mismatch_8: float = 0.0
    group_velocity_mismatch_12: float = 0.0
    nonlinear_strength_448: float = 0.085
    nonlinear_strength_4812: float = 0.115
    coupling_strength: float = 0.16
    damping_loss: float = 0.045
    saturation_loss: float = 0.010
    drive_amplitude: float = 0.20
    direct_8_drive_scale: float = 0.50
    direct_8_reference_drive: bool = False
    no_nonlinearity: bool = False
    target_detuning: float = 0.0
    generated_detuning: float = 0.0
    random_seed: int = 0


@dataclass(frozen=True)
class LadderExport:
    case: LadderCase
    netlist_path: Path
    csv_path: Path
    vector_names: Tuple[str, ...]


@dataclass(frozen=True)
class RunResult:
    execution_status: str
    success: bool
    reason: str
    log_path: Path | None = None


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, rows: List[Dict[str, float | str]]) -> None:
    if not rows:
        return
    keys: List[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def spice_num(value: float) -> str:
    if value == 0:
        return "0"
    return f"{value:.12g}"


def qpm_pattern(z: np.ndarray, period: float, duty_cycle: float, kind: str, seed: int) -> np.ndarray:
    if kind == "none" or period <= 0.0:
        return np.ones_like(z)
    if kind == "randomized":
        rng = np.random.default_rng(seed)
        cells = np.floor(z / max(period, EPS)).astype(int)
        unique = int(np.max(cells)) + 1
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=max(1, unique))
        return signs[np.clip(cells, 0, unique - 1)]
    cells = np.floor(z / max(period, EPS)).astype(int)
    if kind == "alternating":
        return np.where(cells % 2 == 0, 1.0, -1.0)
    phase = (z % period) / max(period, EPS)
    return np.where(phase < duty_cycle, 1.0, -1.0)


def sign_pattern(z: np.ndarray, kind: str, length: float) -> np.ndarray:
    if kind == "alternating_cell":
        return np.where(np.arange(len(z)) % 2 == 0, 1.0, -1.0)
    if kind == "alternating_section":
        return np.where(np.floor(6.0 * z / max(length, EPS)).astype(int) % 2 == 0, 1.0, -1.0)
    return np.ones_like(z)


def qpm_gain_factor(case: LadderCase) -> float:
    z = np.linspace(0.0, case.chain_length, max(8, case.cell_count))
    p448 = qpm_pattern(z, case.qpm_period_448, case.qpm_duty_cycle, case.grating_kind, case.random_seed)
    p4812 = qpm_pattern(z, case.qpm_period_4812, case.qpm_duty_cycle, case.grating_kind, case.random_seed + 17)
    g448 = abs(np.mean(p448 * np.exp(-1j * case.delta_k_448 * z)))
    g4812 = abs(np.mean(p4812 * np.exp(-1j * case.delta_k_4812 * z)))
    return float(math.sqrt(g448 * g4812))


def build_cases() -> List[LadderCase]:
    phase = LadderCase(
        name="phase_matched_codirectional_ladder",
        filename="phase_matched_codirectional_ladder.cir",
        topology="co_directional_phase_matched",
        nonlinear_strength_448=0.085 * 1.55,
        nonlinear_strength_4812=0.115 * 1.55,
    )
    qpm = LadderCase(
        name="qpm_ladder",
        filename="qpm_ladder.cir",
        topology="quasi_phase_matched_grating",
        delta_k_448=1.20,
        delta_k_4812=1.20,
        qpm_period_448=2.0 * math.pi / 1.20,
        qpm_period_4812=2.0 * math.pi / 1.20,
        grating_kind="square",
        nonlinear_strength_448=0.22,
        nonlinear_strength_4812=0.30,
        coupling_strength=0.20,
        damping_loss=0.038,
    )
    mismatched = LadderCase(
        name="mismatched_ladder_control",
        filename="mismatched_ladder_control.cir",
        topology="phase_mismatched_control",
        role="control",
        delta_k_448=1.80,
        delta_k_4812=2.20,
        group_velocity_mismatch_8=0.18,
        group_velocity_mismatch_12=-0.22,
    )
    lumped = LadderCase(
        name="lumped_equivalent_control",
        filename="lumped_equivalent_control.cir",
        topology="compact_lumped_equivalent_control",
        role="control",
        cell_count=8,
        chain_length=2.0,
        delta_k_448=0.55,
        delta_k_4812=0.70,
        group_velocity_mismatch_8=0.04,
        group_velocity_mismatch_12=-0.06,
        nonlinear_strength_448=0.060,
        nonlinear_strength_4812=0.075,
    )
    linear = replace(
        phase,
        name="linear_no_nonlinearity_control",
        filename="linear_no_nonlinearity_control.cir",
        topology="linear_no_nonlinearity_control",
        role="control",
        no_nonlinearity=True,
    )
    detuned = replace(
        phase,
        name="detuned_target_control",
        filename="detuned_target_control.cir",
        topology="detuned_target_control",
        role="control",
        target_mode=12.65,
        target_detuning=1.45,
        delta_k_4812=1.15,
        group_velocity_mismatch_12=0.40,
    )
    shuffled = replace(
        phase,
        name="shuffled_frequency_control",
        filename="shuffled_frequency_control.cir",
        topology="shuffled_frequency_control",
        role="control",
        generated_mode=12.0,
        target_mode=8.0,
        k8=3.0,
        k12=2.0,
        delta_k_448=1.0,
        delta_k_4812=-1.0,
        group_velocity_mismatch_8=0.25,
        group_velocity_mismatch_12=-0.35,
    )
    reference = replace(
        phase,
        name="direct_4plus8_ceiling_reference",
        filename="direct_4plus8_ceiling_reference.cir",
        topology="direct_4plus8_ceiling_reference",
        role="ceiling_reference",
        direct_8_reference_drive=True,
        nonlinear_strength_448=0.055,
        nonlinear_strength_4812=0.075,
        damping_loss=0.055,
        cell_count=24,
        chain_length=10.0,
    )
    return [phase, qpm, mismatched, lumped, linear, detuned, shuffled, reference]


def node(band: int, part: str, idx: int) -> str:
    return f"a{band}{part}{idx}"


def vexpr(name: str) -> str:
    return f"V({name})"


def lap_expr(band: int, part: str, idx: int, count: int) -> str:
    current = vexpr(node(band, part, idx))
    if count < 2:
        return "0"
    if idx == 0:
        return f"({vexpr(node(band, part, 1))}-{current})"
    if idx == count - 1:
        return f"({vexpr(node(band, part, idx - 1))}-{current})"
    return f"({vexpr(node(band, part, idx - 1))}-2*{current}+{vexpr(node(band, part, idx + 1))})"


def add_expr(*parts: str) -> str:
    clean = [part for part in parts if part and part != "0"]
    if not clean:
        return "0"
    return "(" + "+".join(clean) + ")"


def source_profile(z: np.ndarray, length: float) -> np.ndarray:
    profile = np.exp(-0.5 * (z / max(0.08 * length, EPS)) ** 2)
    return profile / max(float(np.max(profile)), EPS)


def output_weights(z: np.ndarray, length: float) -> np.ndarray:
    weights = np.exp(-0.5 * ((z - length) / max(0.22 * length, EPS)) ** 2)
    return weights / max(float(np.sum(weights)), EPS)


def weighted_sum(nodes: Iterable[str], weights: np.ndarray) -> str:
    terms = []
    for name, weight in zip(nodes, weights):
        if abs(float(weight)) > 1e-14:
            terms.append(f"{spice_num(float(weight))}*V({name})")
    return add_expr(*terms)


def nonlinear_terms(case: LadderCase, idx: int, z_value: float, pattern448: float, pattern4812: float,
                    sign: float) -> Tuple[str, str, str, str]:
    if case.no_nonlinearity:
        return "0", "0", "0", "0"
    x4 = vexpr(node(4, "r", idx))
    y4 = vexpr(node(4, "i", idx))
    x8 = vexpr(node(8, "r", idx))
    y8 = vexpr(node(8, "i", idx))
    mismatch448 = case.generated_mode - 2.0 * case.source_mode
    mismatch4812 = case.target_mode - case.generated_mode - case.source_mode
    omega448 = case.group_velocity_mismatch_8 + 0.42 * mismatch448
    omega4812 = case.group_velocity_mismatch_12 + 0.42 * mismatch4812
    theta448 = f"({spice_num(case.delta_k_448 * z_value)}+{spice_num(omega448)}*time)"
    theta4812 = f"({spice_num(case.delta_k_4812 * z_value)}+{spice_num(omega4812)}*time)"
    nr448 = f"(({x4})*({x4})-({y4})*({y4}))"
    ni448 = f"(2*({x4})*({y4}))"
    pr4812 = f"(({x4})*({x8})-({y4})*({y8}))"
    pi4812 = f"(({x4})*({y8})+({y4})*({x8}))"
    c448 = spice_num(case.nonlinear_strength_448 * pattern448 * sign)
    c4812 = spice_num(case.nonlinear_strength_4812 * pattern4812 * sign)
    n448r = f"({c448}*(({nr448})*cos({theta448})+({ni448})*sin({theta448})))"
    n448i = f"({c448}*(({ni448})*cos({theta448})-({nr448})*sin({theta448})))"
    n4812r = f"({c4812}*(({pr4812})*cos({theta4812})+({pi4812})*sin({theta4812})))"
    n4812i = f"({c4812}*(({pi4812})*cos({theta4812})-({pr4812})*sin({theta4812})))"
    return n448r, n448i, n4812r, n4812i


def rhs_exprs(case: LadderCase, idx: int, z_value: float, pattern448: float, pattern4812: float,
              sign: float) -> Tuple[str, str, str, str, str, str]:
    loss = spice_num(case.damping_loss)
    loss8 = spice_num(1.08 * case.damping_loss)
    loss12 = spice_num(1.16 * case.damping_loss)
    coupling = spice_num(case.coupling_strength)
    coupling8 = spice_num(0.92 * case.coupling_strength)
    coupling12 = spice_num(0.84 * case.coupling_strength)
    sat = spice_num(case.saturation_loss)
    x4 = vexpr(node(4, "r", idx))
    y4 = vexpr(node(4, "i", idx))
    x8 = vexpr(node(8, "r", idx))
    y8 = vexpr(node(8, "i", idx))
    x12 = vexpr(node(12, "r", idx))
    y12 = vexpr(node(12, "i", idx))
    density = f"(({x4})*({x4})+({y4})*({y4})+({x8})*({x8})+({y8})*({y8})+({x12})*({x12})+({y12})*({y12}))"
    sat4r = f"(-{sat}*{density}*({x4}))"
    sat4i = f"(-{sat}*{density}*({y4}))"
    sat8r = f"(-{sat}*{density}*({x8}))"
    sat8i = f"(-{sat}*{density}*({y8}))"
    sat12r = f"(-{sat}*{density}*({x12}))"
    sat12i = f"(-{sat}*{density}*({y12}))"
    n448r, n448i, n4812r, n4812i = nonlinear_terms(case, idx, z_value, pattern448, pattern4812, sign)
    d4r = add_expr(f"(-{loss}*({x4}))", f"(-{coupling}*{lap_expr(4, 'i', idx, case.cell_count)})", sat4r)
    d4i = add_expr(f"(-{loss}*({y4}))", f"({coupling}*{lap_expr(4, 'r', idx, case.cell_count)})", sat4i)
    d8r = add_expr(
        f"(-{loss8}*({x8}))",
        f"({spice_num(case.generated_detuning)}*({y8}))",
        f"(-{coupling8}*{lap_expr(8, 'i', idx, case.cell_count)})",
        sat8r,
        n448r,
    )
    d8i = add_expr(
        f"(-{loss8}*({y8}))",
        f"(-{spice_num(case.generated_detuning)}*({x8}))",
        f"({coupling8}*{lap_expr(8, 'r', idx, case.cell_count)})",
        sat8i,
        n448i,
    )
    d12r = add_expr(
        f"(-{loss12}*({x12}))",
        f"({spice_num(case.target_detuning)}*({y12}))",
        f"(-{coupling12}*{lap_expr(12, 'i', idx, case.cell_count)})",
        sat12r,
        n4812r,
    )
    d12i = add_expr(
        f"(-{loss12}*({y12}))",
        f"(-{spice_num(case.target_detuning)}*({x12}))",
        f"({coupling12}*{lap_expr(12, 'r', idx, case.cell_count)})",
        sat12i,
        n4812i,
    )
    return d4r, d4i, d8r, d8i, d12r, d12i


def netlist_text(case: LadderCase, out_dir: Path) -> LadderExport:
    n = case.cell_count
    z = np.linspace(0.0, case.chain_length, n)
    p448 = qpm_pattern(z, case.qpm_period_448, case.qpm_duty_cycle, case.grating_kind, case.random_seed)
    p4812 = qpm_pattern(z, case.qpm_period_4812, case.qpm_duty_cycle, case.grating_kind, case.random_seed + 17)
    signs = sign_pattern(z, case.coupling_sign_pattern, case.chain_length)
    drive = source_profile(z, case.chain_length)
    weights = output_weights(z, case.chain_length)
    netlist_path = out_dir / case.filename
    csv_path = out_dir / f"{netlist_path.stem}_tran.csv"
    lines = [
        f"* {case.name}",
        "* Normalized distributed envelope ladder for 4->8->12 phase matching.",
        f"* topology={case.topology} role={case.role}",
        "* Source-only discovery rule: direct 8 and direct 12 drives are absent unless role=ceiling_reference.",
        ".options reltol=1e-4 abstol=1e-8 chgtol=1e-12 method=gear maxord=2",
        f".param tstep={spice_num(TSTEP)}",
        f".param tstop={spice_num(TSTOP)}",
        "",
    ]
    for idx in range(n):
        for band in (4, 8, 12):
            for part in ("r", "i"):
                name = node(band, part, idx)
                lines.append(f"C{name} {name} 0 1 ic=0")
                lines.append(f"R{name} {name} 0 1e12")
        d4r, d4i, d8r, d8i, d12r, d12i = rhs_exprs(case, idx, float(z[idx]), float(p448[idx]), float(p4812[idx]), float(signs[idx]))
        lines.append(f"B4r{idx} {node(4, 'r', idx)} 0 I={{-({d4r})}}")
        lines.append(f"B4i{idx} {node(4, 'i', idx)} 0 I={{-({d4i})}}")
        lines.append(f"B8r{idx} {node(8, 'r', idx)} 0 I={{-({d8r})}}")
        lines.append(f"B8i{idx} {node(8, 'i', idx)} 0 I={{-({d8i})}}")
        lines.append(f"B12r{idx} {node(12, 'r', idx)} 0 I={{-({d12r})}}")
        lines.append(f"B12i{idx} {node(12, 'i', idx)} 0 I={{-({d12i})}}")
        amp4 = case.drive_amplitude * float(drive[idx])
        if abs(amp4) > 1e-14:
            lines.append(f"Idrive4_{idx} {node(4, 'r', idx)} 0 PWL(0 0 11.52 -{spice_num(amp4)} 78.72 -{spice_num(amp4)} 96 0)")
        if case.direct_8_reference_drive:
            amp8 = case.direct_8_drive_scale * case.drive_amplitude * float(drive[idx])
            if abs(amp8) > 1e-14:
                lines.append(f"Idrive8_{idx} {node(8, 'r', idx)} 0 PWL(0 0 11.52 -{spice_num(amp8)} 78.72 -{spice_num(amp8)} 96 0)")
        lines.append("")
    lines.extend([
        f"Bobs4r obs4r 0 V={{{weighted_sum((node(4, 'r', i) for i in range(n)), weights)}}}",
        f"Bobs4i obs4i 0 V={{{weighted_sum((node(4, 'i', i) for i in range(n)), weights)}}}",
        f"Bobs8r obs8r 0 V={{{weighted_sum((node(8, 'r', i) for i in range(n)), weights)}}}",
        f"Bobs8i obs8i 0 V={{{weighted_sum((node(8, 'i', i) for i in range(n)), weights)}}}",
        f"Bobs12r obs12r 0 V={{{weighted_sum((node(12, 'r', i) for i in range(n)), weights)}}}",
        f"Bobs12i obs12i 0 V={{{weighted_sum((node(12, 'i', i) for i in range(n)), weights)}}}",
        "",
        ".control",
        "set noaskquit",
        "set filetype=ascii",
        f"tran {spice_num(TSTEP)} {spice_num(TSTOP)} 0 {spice_num(TSTEP)} uic",
    ])
    vector_names: List[str] = ["obs4r", "obs4i", "obs8r", "obs8i", "obs12r", "obs12i"]
    state_vectors: List[str] = []
    for idx in range(n):
        for band in (4, 8, 12):
            for part in ("r", "i"):
                state_vectors.append(node(band, part, idx))
    vector_names.extend(state_vectors)
    wr_vectors = " ".join([f"v({name})" for name in vector_names])
    lines.extend([
        f"wrdata {csv_path.name} {wr_vectors}",
        "quit",
        ".endc",
        ".end",
        "",
    ])
    export = LadderExport(case=case, netlist_path=netlist_path, csv_path=csv_path, vector_names=tuple(vector_names))
    netlist_path.write_text("\n".join(lines), encoding="utf-8")
    return export


def export_netlists(out_dir: Path) -> List[LadderExport]:
    ensure_dir(out_dir)
    return [netlist_text(case, out_dir) for case in build_cases()]


def run_ngspice(export: LadderExport, ngspice_path: str, timeout_s: int) -> RunResult:
    proxy = type("ExportProxy", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = spice_base.run_ngspice(proxy, ngspice_path, timeout_s)
    return RunResult(result.execution_status, result.success, result.reason, result.log_path)


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def read_wrdata(path: Path, vector_names: Tuple[str, ...]) -> Dict[str, np.ndarray]:
    if not path.exists():
        raise ValueError(f"CSV does not exist: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No data in {path}")
    first_tokens = lines[0].replace(",", " ").split()
    has_header = any(try_float(tok) is None for tok in first_tokens)
    data_lines = lines[1:] if has_header else lines
    rows: List[List[float]] = []
    for line in data_lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(value) for value in values if value is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"No numeric rows in {path}")
    min_cols = min(len(row) for row in rows)
    arr = np.asarray([row[:min_cols] for row in rows], dtype=float)
    if min_cols < len(vector_names) + 1:
        raise ValueError(f"Expected at least {len(vector_names) + 1} columns, got {min_cols}")
    result: Dict[str, np.ndarray] = {"time": arr[:, 0]}
    if has_header and min_cols >= len(vector_names) + 1:
        clean_header = [token.lower().replace('"', "").replace("'", "") for token in first_tokens[:min_cols]]
        for name in vector_names:
            wanted = f"v({name.lower()})"
            if wanted in clean_header:
                result[name] = arr[:, clean_header.index(wanted)]
    if all(name in result for name in vector_names):
        return result
    if min_cols >= 2 * len(vector_names):
        for idx, name in enumerate(vector_names):
            result[name] = arr[:, 2 * idx + 1]
    else:
        for idx, name in enumerate(vector_names):
            result[name] = arr[:, idx + 1]
    return result


def envelope_cv(values: np.ndarray) -> float:
    amp = np.abs(values)
    mean = float(np.mean(amp))
    if mean <= EPS:
        return float("inf")
    return float(np.std(amp) / mean)


def coalesced_count(indices: np.ndarray) -> int:
    if len(indices) == 0:
        return 0
    count = 1
    last = int(indices[0])
    for idx in indices[1:]:
        if int(idx) > last + 1:
            count += 1
        last = int(idx)
    return count


def parse_complex_cells(data: Dict[str, np.ndarray], band: int, count: int) -> np.ndarray:
    real = np.vstack([data[node(band, "r", idx)] for idx in range(count)]).T
    imag = np.vstack([data[node(band, "i", idx)] for idx in range(count)]).T
    return real + 1j * imag


def row_power(data: Dict[str, np.ndarray], case: LadderCase) -> np.ndarray:
    power = np.zeros_like(data["time"], dtype=float)
    for idx in range(case.cell_count):
        for band in (4, 8, 12):
            power += data[node(band, "r", idx)] ** 2 + data[node(band, "i", idx)] ** 2
    return power


def metrics_from_data(export: LadderExport, data: Dict[str, np.ndarray],
                      reference_data: Dict[str, np.ndarray] | None = None) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    case = export.case
    t = np.asarray(data["time"], dtype=float)
    finite = np.isfinite(t)
    for name in export.vector_names:
        finite &= np.isfinite(data[name])
    if int(np.sum(finite)) < 32:
        return {"metric_error": "not_enough_finite_samples"}, []
    for key in list(data):
        data[key] = np.asarray(data[key], dtype=float)[finite]
    t = data["time"]
    obs4 = data["obs4r"] + 1j * data["obs4i"]
    obs8 = data["obs8r"] + 1j * data["obs8i"]
    obs12 = data["obs12r"] + 1j * data["obs12i"]
    late = t >= 0.55 * float(t[-1])
    early = (t >= 0.12 * float(t[-1])) & (t < 0.30 * float(t[-1]))
    if int(np.sum(early)) < 3:
        early = t < 0.30 * float(t[-1])
    rel_target = obs4 * obs8 * np.conj(obs12)
    rel_generated = obs4 * obs4 * np.conj(obs8)
    rel_t = rel_target[late]
    rel_g = rel_generated[late]
    temporal_target = abs(np.mean(rel_t / np.maximum(np.abs(rel_t), EPS))) if len(rel_t) else 0.0
    temporal_generated = abs(np.mean(rel_g / np.maximum(np.abs(rel_g), EPS))) if len(rel_g) else 0.0
    a4 = parse_complex_cells(data, 4, case.cell_count)
    a8 = parse_complex_cells(data, 8, case.cell_count)
    a12 = parse_complex_cells(data, 12, case.cell_count)
    z = np.linspace(0.0, case.chain_length, case.cell_count)
    weights = output_weights(z, case.chain_length)
    local_target = weights[None, :] * a4 * a8 * np.conj(a12)
    local_generated = weights[None, :] * a4 * a4 * np.conj(a8)
    spatial_target_series = np.abs(np.sum(local_target, axis=1)) / np.maximum(np.sum(np.abs(local_target), axis=1), EPS)
    spatial_generated_series = np.abs(np.sum(local_generated, axis=1)) / np.maximum(np.sum(np.abs(local_generated), axis=1), EPS)
    spatial_target = float(np.median(spatial_target_series[late])) if int(np.sum(late)) else 0.0
    spatial_generated = float(np.median(spatial_generated_series[late])) if int(np.sum(late)) else 0.0
    phase_lock_target = float(temporal_target * spatial_target)
    phase_lock_generated = float(temporal_generated * spatial_generated)
    target_total_power = float(np.mean(np.abs(obs12[late]) ** 2)) if int(np.sum(late)) else 0.0
    target_coherent_power = float(abs(np.mean(obs12[late])) ** 2) if int(np.sum(late)) else 0.0
    purity = float(min(1.0, target_coherent_power / max(target_total_power, EPS)))
    early_target = float(abs(np.mean(obs12[early])) ** 2) if int(np.sum(early)) else 0.0
    target_coherent_growth = float(target_coherent_power / max(early_target, 1e-15))
    bridge_ratio: float | str = ""
    if reference_data is not None:
        rt = np.asarray(reference_data["time"], dtype=float)
        rlate = rt >= 0.55 * float(rt[-1])
        ref_obs12 = reference_data["obs12r"] + 1j * reference_data["obs12i"]
        ref_power = float(abs(np.mean(ref_obs12[rlate])) ** 2) if int(np.sum(rlate)) else 0.0
        bridge_ratio = float(target_coherent_power / max(ref_power, 1e-15))
    target_phase = np.unwrap(np.angle(rel_t)) if int(np.sum(late)) else np.asarray([])
    phase_step = np.abs(np.diff(target_phase)) if len(target_phase) >= 2 else np.asarray([])
    max_jump = float(np.max(phase_step)) if len(phase_step) else 0.0
    near_slips = float(coalesced_count(np.where(phase_step > 1.0)[0]))
    energy = row_power(data, case)
    energy_proxy = float(abs(energy[-1] - energy[0]) / max(float(np.max(np.abs(energy))), 1.0))
    accumulated = float(math.sqrt(case.delta_k_448 ** 2 + case.delta_k_4812 ** 2) * case.chain_length)
    generated_cv = envelope_cv(obs8[late])
    target_cv = envelope_cv(obs12[late])
    metrics: Dict[str, float | str] = {
        "phase_lock_target": phase_lock_target,
        "phase_lock_generated": phase_lock_generated,
        "bridge_ratio": bridge_ratio,
        "target_spectral_purity": purity,
        "target_coherent_growth": target_coherent_growth,
        "target_coherent_power": target_coherent_power,
        "target_total_power": target_total_power,
        "generated_envelope_cv": generated_cv if math.isfinite(generated_cv) else "",
        "target_envelope_cv": target_cv if math.isfinite(target_cv) else "",
        "max_phase_jump": max_jump,
        "near_slip_count": near_slips,
        "spatial_coherence_length": float(case.chain_length * spatial_target),
        "spatial_target_coherence": spatial_target,
        "spatial_generated_coherence": spatial_generated,
        "accumulated_phase_mismatch": accumulated,
        "qpm_gain_factor": qpm_gain_factor(case),
        "energy_budget_proxy": energy_proxy,
        "stored_energy_proxy_final": float(energy[-1]),
        "stored_energy_proxy_peak": float(np.max(energy)),
    }
    ts_rows: List[Dict[str, float | str]] = []
    stride = max(1, len(t) // 320)
    for idx in range(0, len(t), stride):
        phase_error: float | str = ""
        if abs(rel_target[idx]) > EPS:
            phase_error = float((np.angle(rel_target[idx]) + math.pi) % (2.0 * math.pi) - math.pi)
        ts_rows.append({
            "row_type": "spice_distributed_ladder_timeseries",
            "case_id": "",
            "name": case.name,
            "topology": case.topology,
            "role": case.role,
            "time": float(t[idx]),
            "source_envelope": float(abs(obs4[idx])),
            "generated_envelope": float(abs(obs8[idx])),
            "target_envelope": float(abs(obs12[idx])),
            "target_phase_error": phase_error,
            "spatial_target_coherence": float(spatial_target_series[idx]),
            "energy_proxy": float(energy[idx]),
        })
    return metrics, ts_rows


def control_leakage(row: Dict[str, float | str]) -> float:
    if str(row.get("role")) != "control":
        return 0.0
    if str(row.get("execution_status")) != "ran_successfully":
        return 0.0
    lock = safe_float(row.get("phase_lock_target"))
    if lock < 0.50:
        return 0.0
    growth = safe_float(row.get("target_coherent_growth"))
    bridge = safe_float(row.get("bridge_ratio"))
    purity = safe_float(row.get("target_spectral_purity"))
    target_power = safe_float(row.get("target_coherent_power"))
    power_gate = min(target_power / 1e-8, 1.0)
    return float(
        power_gate
        * (
            0.45 * min(lock / 0.50, 1.0)
            + 0.20 * min(growth / 1.0, 1.0)
            + 0.25 * min(max(bridge, 0.0) / 0.50, 1.0)
            + 0.10 * min(purity / 0.80, 1.0)
        )
    )


def promotion_category(row: Dict[str, float | str], controls_dead: bool, controls_mostly_clean: bool) -> str:
    if str(row.get("role")) == "ceiling_reference":
        return "ceiling_reference_not_discovery"
    if str(row.get("role")) == "control":
        if row.get("topology") in ("phase_mismatched_control", "compact_lumped_equivalent_control"):
            if safe_float(row.get("target_coherent_growth")) > 1.0 and safe_float(row.get("phase_lock_target")) < 0.50:
                return "reject_due_to_phase_mismatch"
        return "control_dead" if control_leakage(row) < 0.10 else "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "ran_successfully":
        return "not_promoted"
    if not controls_dead and safe_float(row.get("phase_lock_target")) > 0.50:
        return "reject_due_to_control_leakage"
    lock = safe_float(row.get("phase_lock_target"))
    bridge = safe_float(row.get("bridge_ratio"))
    purity = safe_float(row.get("target_spectral_purity"))
    growth = safe_float(row.get("target_coherent_growth"))
    gen_cv = safe_float(row.get("generated_envelope_cv"), float("inf"))
    jump = safe_float(row.get("max_phase_jump"), float("inf"))
    if growth > 1.0 and lock < 0.50:
        return "reject_due_to_phase_mismatch"
    if (
        lock > 0.90
        and bridge > 1.5
        and purity > 0.80
        and growth > 1.0
        and gen_cv < 0.25
        and jump < 1.0
        and controls_dead
        and str(row.get("direct_8_drive_present")) == "False"
        and str(row.get("direct_12_drive_present")) == "False"
        and str(row.get("target_frequency_injection_present")) == "False"
    ):
        return "spice_distributed_phase_candidate"
    if lock > 0.50 and bridge > 1.0 and purity > 0.80 and controls_mostly_clean:
        return "spice_distributed_phase_near_miss"
    return "not_promoted"


def summarize_export(case_id: str, export: LadderExport, run_result: RunResult,
                     metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    case = export.case
    direct_8 = case.direct_8_reference_drive
    row: Dict[str, float | str] = {
        "row_type": "spice_distributed_ladder",
        "case_id": case_id,
        "name": case.name,
        "topology": case.topology,
        "role": case.role,
        "netlist_file": export.netlist_path.name,
        "csv_file": export.csv_path.name if export.csv_path.exists() else "",
        "execution_status": run_result.execution_status,
        "execution_status_allowed": str(run_result.execution_status in EXECUTION_STATUSES),
        "convergence_failure_reason": "" if run_result.success else run_result.reason,
        "source_mode": case.source_mode,
        "generated_mode": case.generated_mode,
        "target_mode": case.target_mode,
        "k4": case.k4,
        "k8": case.k8,
        "k12": case.k12,
        "delta_k_448": case.delta_k_448,
        "delta_k_4812": case.delta_k_4812,
        "qpm_period_448": case.qpm_period_448,
        "qpm_period_4812": case.qpm_period_4812,
        "qpm_duty_cycle": case.qpm_duty_cycle,
        "grating_kind": case.grating_kind,
        "coupling_sign_pattern": case.coupling_sign_pattern,
        "chain_length": case.chain_length,
        "cell_count": case.cell_count,
        "group_velocity_mismatch_8": case.group_velocity_mismatch_8,
        "group_velocity_mismatch_12": case.group_velocity_mismatch_12,
        "nonlinear_strength_448": case.nonlinear_strength_448,
        "nonlinear_strength_4812": case.nonlinear_strength_4812,
        "coupling_strength": case.coupling_strength,
        "damping_loss": case.damping_loss,
        "saturation_loss": case.saturation_loss,
        "direct_8_drive_present": str(direct_8),
        "direct_12_drive_present": str(False),
        "target_frequency_injection_present": str(False),
    }
    if metrics:
        row.update(metrics)
    return row


def aggregate(rows: List[Dict[str, float | str]], run_requested: bool, ngspice_available: bool,
              out_dir: Path) -> Dict[str, float | str]:
    controls = [r for r in rows if str(r.get("role")) == "control"]
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    leakage = max((control_leakage(r) for r in controls), default=0.0)
    controls_dead = leakage < 0.10
    controls_mostly_clean = leakage < 0.25
    for row in rows:
        row["control_leakage_score"] = leakage
        row["promotion_category"] = promotion_category(row, controls_dead, controls_mostly_clean)
    candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_distributed_phase_candidate"]
    near = [r for r in discovery if str(r.get("promotion_category")) == "spice_distributed_phase_near_miss"]
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    best = max(successful, key=lambda r: safe_float(r.get("phase_lock_target")), default={})
    phase = next((r for r in rows if str(r.get("name")) == "phase_matched_codirectional_ladder"), {})
    qpm = next((r for r in rows if str(r.get("name")) == "qpm_ladder"), {})
    lumped = next((r for r in rows if str(r.get("name")) == "lumped_equivalent_control"), {})
    mismatch = next((r for r in rows if str(r.get("name")) == "mismatched_ladder_control"), {})
    statuses = sorted(set(str(r.get("execution_status")) for r in rows))
    if candidates:
        next_step = "physical waveguide modeling and transmission-line ladder refinement"
    elif near:
        next_step = "transmission-line ladder refinement before physical waveguide modeling"
    else:
        next_step = "reject the present SPICE ladder realization or revisit the envelope-to-circuit mapping"
    return {
        "row_type": "aggregate",
        "valid_spice_netlists_generated": str(all((out_dir / name).exists() for name in REQUIRED_NETLISTS)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": ";".join(statuses),
        "rows_total": len(rows),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "successful_discovery_rows": len(successful),
        "spice_distributed_phase_candidate_count": len(candidates),
        "spice_distributed_phase_near_miss_count": len(near),
        "best_phase_lock_case": str(best.get("case_id", "")),
        "best_phase_lock_topology": str(best.get("topology", "")),
        "best_phase_lock": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio", ""),
        "phase_matched_ladder_lock": phase.get("phase_lock_target", ""),
        "phase_matched_ladder_bridge_ratio": phase.get("bridge_ratio", ""),
        "lumped_control_lock": lumped.get("phase_lock_target", ""),
        "lumped_control_bridge_ratio": lumped.get("bridge_ratio", ""),
        "phase_matched_beats_lumped": str(
            str(phase.get("promotion_category")) == "spice_distributed_phase_candidate"
            and str(lumped.get("promotion_category")) != "spice_distributed_phase_candidate"
            and safe_float(phase.get("phase_lock_target")) > safe_float(lumped.get("phase_lock_target"))
        ),
        "mismatched_ladder_lock": mismatch.get("phase_lock_target", ""),
        "phase_mismatch_kills_lock": str(safe_float(mismatch.get("phase_lock_target")) < 0.50),
        "qpm_ladder_lock": qpm.get("phase_lock_target", ""),
        "qpm_ladder_bridge_ratio": qpm.get("bridge_ratio", ""),
        "qpm_helps": str(
            safe_float(qpm.get("phase_lock_target")) > safe_float(mismatch.get("phase_lock_target"))
            and safe_float(qpm.get("bridge_ratio")) > safe_float(mismatch.get("bridge_ratio"))
        ),
        "controls_dead": str(controls_dead),
        "controls_mostly_clean": str(controls_mostly_clean),
        "max_control_leakage_score": leakage,
        "recommended_next_step": next_step,
    }


def write_report(out_dir: Path, summary: Dict[str, float | str], rows: List[Dict[str, float | str]]) -> None:
    ranked = sorted(
        [r for r in rows if str(r.get("role")) != "ceiling_reference"],
        key=lambda r: (
            1 if str(r.get("promotion_category")) == "spice_distributed_phase_candidate" else 0,
            safe_float(r.get("phase_lock_target")),
            safe_float(r.get("bridge_ratio")),
        ),
        reverse=True,
    )
    lines = [
        "# SPICE 4->8->12 Distributed Ladder",
        "",
        "Normalized ngspice envelope-ladder export for the distributed phase-matched 4->8->12 topology.",
        "",
        "## Direct Answers",
        "",
        f"1. Can SPICE reproduce the distributed phase-matched 4->8->12 lock? candidates={summary['spice_distributed_phase_candidate_count']}; best={summary['best_phase_lock_case']} lock={summary['best_phase_lock']} bridge={summary['best_bridge_ratio']}.",
        f"2. Does the phase-matched ladder beat the lumped-equivalent control? {summary['phase_matched_beats_lumped']}; phase_lock={summary['phase_matched_ladder_lock']} vs lumped={summary['lumped_control_lock']}.",
        f"3. Does deliberate phase mismatch kill lock? {summary['phase_mismatch_kills_lock']}; mismatched_lock={summary['mismatched_ladder_lock']}.",
        f"4. Does QPM help? {summary['qpm_helps']}; qpm_lock={summary['qpm_ladder_lock']}, qpm_bridge={summary['qpm_ladder_bridge_ratio']}.",
        f"5. Do linear, detuned, and shuffled controls stay dead? {summary['controls_dead']}; max_control_leakage={summary['max_control_leakage_score']}.",
        f"6. Next step: {summary['recommended_next_step']}.",
        "",
        "## Rows",
        "",
    ]
    for row in ranked:
        lines.append(
            f"- {row.get('case_id')} {row.get('name')}: status={row.get('execution_status')}, "
            f"category={row.get('promotion_category')}, lock={row.get('phase_lock_target', '')}, "
            f"bridge={row.get('bridge_ratio', '')}, purity={row.get('target_spectral_purity', '')}, "
            f"growth={row.get('target_coherent_growth', '')}."
        )
    lines.extend([
        "",
        "## Notes",
        "",
        "- Discovery rows drive only the source band at the first/source section.",
        "- Direct 4+8 is exported only as a separated ceiling denominator.",
        "- The ladder uses normalized envelope state variables, not hardware-realistic LC component values.",
    ])
    (out_dir / "README_SPICE_412_DISTRIBUTED_LADDER.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and optionally run distributed-ladder SPICE for 4->8->12.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting.")
    parser.add_argument("--ngspice-path", default="", help="Explicit ngspice path; use wsl:ngspice for WSL.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per netlist in seconds.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    exports = export_netlists(out_dir)
    ngspice_path = None
    if args.run:
        try:
            ngspice_path = spice_base.resolve_ngspice_path(args.ngspice_path or None)
        except subprocess.TimeoutExpired:
            ngspice_path = None
    ngspice_available = ngspice_path is not None
    run_results: Dict[str, RunResult] = {}
    parsed: Dict[str, Dict[str, np.ndarray]] = {}
    if args.run and not ngspice_available:
        for export in exports:
            run_results[export.case.name] = RunResult("skipped_no_ngspice", False, "ngspice not found; pass --ngspice-path or add ngspice to PATH")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed[export.case.name] = read_wrdata(export.csv_path, export.vector_names)
                except Exception as exc:
                    result = RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            run_results[export.case.name] = result
    else:
        for export in exports:
            run_results[export.case.name] = RunResult("exported", False, "export only; use --run to execute ngspice")

    reference_data = parsed.get("direct_4plus8_ceiling_reference")
    rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    case_ids: Dict[str, str] = {
        "phase_matched_codirectional_ladder": "d001",
        "qpm_ladder": "d002",
        "mismatched_ladder_control": "c001",
        "lumped_equivalent_control": "c002",
        "linear_no_nonlinearity_control": "c003",
        "detuned_target_control": "c004",
        "shuffled_frequency_control": "c005",
        "direct_4plus8_ceiling_reference": "direct_4plus8_ceiling_reference",
    }
    for export in exports:
        metrics: Dict[str, float | str] | None = None
        ts: List[Dict[str, float | str]] = []
        if export.case.name in parsed:
            ref = None if export.case.role == "ceiling_reference" else reference_data
            try:
                metrics, ts = metrics_from_data(export, parsed[export.case.name], ref)
            except Exception as exc:
                run_results[export.case.name] = RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", run_results[export.case.name].log_path)
                metrics = {"metric_error": f"{type(exc).__name__}: {exc}"}
        case_id = case_ids[export.case.name]
        for item in ts:
            item["case_id"] = case_id
            timeseries_rows.append(item)
        rows.append(summarize_export(case_id, export, run_results[export.case.name], metrics))

    summary = aggregate(rows, args.run, ngspice_available, out_dir)
    all_rows = [summary] + rows
    write_csv(out_dir / "spice_412_distributed_ladder_summary.csv", all_rows)
    if timeseries_rows:
        write_csv(out_dir / "spice_412_distributed_ladder_timeseries.csv", timeseries_rows)
    write_report(out_dir, summary, rows)
    (out_dir / "spice_412_distributed_ladder_summary.json").write_text(json.dumps({
        "aggregate": summary,
        "rows": all_rows,
        "model": {
            "description": "Normalized ngspice envelope ladder with distributed phase matching and controls.",
            "tstop": TSTOP,
            "tstep": TSTEP,
            "execution_statuses": EXECUTION_STATUSES,
        },
        "cases": [asdict(export.case) for export in exports],
    }, indent=2), encoding="utf-8")
    print(f"SPICE 4->8->12 distributed ladder written to: {out_dir.resolve()}")
    print(f"valid_spice_netlists_generated={summary['valid_spice_netlists_generated']}")
    print(f"run_requested={summary['run_requested']}")
    print(f"ngspice_available={summary['ngspice_available']}")
    print(f"execution_statuses={summary['execution_statuses']}")
    print(f"candidate_count={summary['spice_distributed_phase_candidate_count']}")
    print(f"controls_dead={summary['controls_dead']}")


if __name__ == "__main__":
    main()
