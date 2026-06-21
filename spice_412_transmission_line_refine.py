#!/usr/bin/env python3
"""Transmission-line refinement for the SPICE 4->8->12 bridge.

This track moves one step away from the behavioral envelope ladder.  The source,
generated, and target bands propagate on explicit normalized LC ladder sections.
Distributed nonlinear inter-band mixing is still represented by behavioral
current sources, so every row reports a behavioral dependency score.
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


OUT_DIR = Path("runs") / "spice_412_transmission_line_refine"
TSTOP = 32.0
TSTEP = 0.002
SOURCE_HZ = 4.0
GENERATED_HZ = 8.0
TARGET_HZ = 12.0
EPS = 1e-18
ENVELOPE_LADDER_BEHAVIORAL_BASELINE = 0.65

REQUIRED_NETLISTS = (
    "tl_phase_matched_ladder.cir",
    "tl_qpm_ladder.cir",
    "tl_mismatched_ladder_control.cir",
    "tl_lumped_equivalent_control.cir",
    "tl_linear_no_nonlinearity_control.cir",
    "tl_detuned_target_control.cir",
    "tl_shuffled_frequency_control.cir",
    "tl_direct_4plus8_reference.cir",
)


@dataclass(frozen=True)
class TLCase:
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
    qpm_period: float = 0.0
    qpm_duty_cycle: float = 0.5
    grating_kind: str = "none"
    chain_length: float = 24.0
    cell_count: int = 32
    drive_amplitude: float = 0.70
    direct_8_reference_drive: bool = False
    direct_8_drive_scale: float = 0.18
    mix448: float = 2.4
    mix4812: float = 16.0
    saturation_conductance: float = 0.010
    shunt_loss_scale: float = 1.0
    coupling_cap_scale: float = 0.012
    no_nonlinearity: bool = False
    detune_target: float = 0.0
    shuffled: bool = False
    random_seed: int = 0


@dataclass(frozen=True)
class TLExport:
    case: TLCase
    netlist_path: Path
    csv_path: Path


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


def node(prefix: str, idx: int) -> str:
    return f"{prefix}{idx}"


def qpm_pattern(z: np.ndarray, case: TLCase) -> np.ndarray:
    if case.grating_kind == "none" or case.qpm_period <= 0.0:
        return np.ones_like(z)
    if case.grating_kind == "randomized":
        rng = np.random.default_rng(case.random_seed)
        bins = np.floor(z / max(case.qpm_period, EPS)).astype(int)
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=max(1, int(np.max(bins)) + 1))
        return signs[np.clip(bins, 0, len(signs) - 1)]
    phase = (z % case.qpm_period) / max(case.qpm_period, EPS)
    return np.where(phase < case.qpm_duty_cycle, 1.0, -1.0)


def qpm_gain_factor(case: TLCase) -> float:
    z = np.linspace(0.0, case.chain_length, max(8, case.cell_count))
    pattern = qpm_pattern(z, case)
    g448 = abs(np.mean(pattern * np.exp(-1j * case.delta_k_448 * z)))
    g4812 = abs(np.mean(pattern * np.exp(-1j * case.delta_k_4812 * z)))
    return float(math.sqrt(g448 * g4812))


def line_inductance(freq_hz: float, wave_number: float, dx: float, capacitance: float = 1.0) -> float:
    omega = 2.0 * math.pi * freq_hz
    kd = min(abs(wave_number * dx), math.pi * 0.92)
    numerator = 2.0 * math.sin(0.5 * kd)
    return max((numerator / max(omega, EPS)) ** 2 / capacitance, 1e-9)


def build_cases() -> List[TLCase]:
    phase = TLCase(
        name="tl_phase_matched_ladder",
        filename="tl_phase_matched_ladder.cir",
        topology="tl_phase_matched",
    )
    qpm = replace(
        phase,
        name="tl_qpm_ladder",
        filename="tl_qpm_ladder.cir",
        topology="tl_qpm",
        delta_k_448=1.20,
        delta_k_4812=1.20,
        qpm_period=2.0 * math.pi / 1.20,
        grating_kind="square",
        mix448=3.2,
        mix4812=20.0,
    )
    mismatched = replace(
        phase,
        name="tl_mismatched_ladder_control",
        filename="tl_mismatched_ladder_control.cir",
        topology="tl_phase_mismatched_control",
        role="control",
        k8=3.35,
        k12=1.45,
        delta_k_448=1.35,
        delta_k_4812=-1.90,
    )
    lumped = replace(
        phase,
        name="tl_lumped_equivalent_control",
        filename="tl_lumped_equivalent_control.cir",
        topology="tl_lumped_equivalent_control",
        role="control",
        cell_count=4,
        chain_length=2.0,
        k8=3.10,
        k12=1.85,
        delta_k_448=0.55,
        delta_k_4812=0.70,
        mix448=1.0,
        mix4812=6.0,
    )
    linear = replace(
        phase,
        name="tl_linear_no_nonlinearity_control",
        filename="tl_linear_no_nonlinearity_control.cir",
        topology="tl_linear_no_nonlinearity_control",
        role="control",
        no_nonlinearity=True,
    )
    detuned = replace(
        phase,
        name="tl_detuned_target_control",
        filename="tl_detuned_target_control.cir",
        topology="tl_detuned_target_control",
        role="control",
        target_mode=12.65,
        k12=1.70,
        detune_target=0.65,
        delta_k_4812=1.15,
    )
    shuffled = replace(
        phase,
        name="tl_shuffled_frequency_control",
        filename="tl_shuffled_frequency_control.cir",
        topology="tl_shuffled_frequency_control",
        role="control",
        generated_mode=12.0,
        target_mode=8.0,
        k8=3.0,
        k12=2.0,
        delta_k_448=1.0,
        delta_k_4812=-1.0,
        shuffled=True,
    )
    reference = replace(
        phase,
        name="tl_direct_4plus8_reference",
        filename="tl_direct_4plus8_reference.cir",
        topology="tl_direct_4plus8_reference",
        role="ceiling_reference",
        direct_8_reference_drive=True,
        direct_8_drive_scale=0.22,
        mix448=1.0,
        mix4812=8.0,
    )
    return [phase, qpm, mismatched, lumped, linear, detuned, shuffled, reference]


def output_weights(case: TLCase) -> np.ndarray:
    z = np.linspace(0.0, case.chain_length, case.cell_count)
    weights = np.exp(-0.5 * ((z - case.chain_length) / max(0.22 * case.chain_length, EPS)) ** 2)
    return weights / max(float(np.sum(weights)), EPS)


def weighted_sum(prefix: str, weights: np.ndarray) -> str:
    terms = [f"{spice_num(float(weight))}*V({node(prefix, idx)})" for idx, weight in enumerate(weights) if abs(float(weight)) > 1e-14]
    return "(" + "+".join(terms) + ")" if terms else "0"


def add_ladder(lines: List[str], prefix: str, case: TLCase, freq_hz: float, wave_number: float,
               detune: float = 0.0) -> Tuple[float, float, float]:
    n = case.cell_count
    dx = case.chain_length / max(n - 1, 1)
    cap = 1.0
    effective_freq = max(freq_hz + detune, 0.25)
    series_l = line_inductance(effective_freq, wave_number, dx, cap)
    shunt_l = 1.0 / max((2.0 * math.pi * effective_freq) ** 2 * cap, 1e-12)
    shunt_r = 1.0 / max(2.0 * 0.035 * case.shunt_loss_scale * cap, 1e-9)
    z0 = math.sqrt(series_l / cap)
    for idx in range(n):
        lines.append(f"C{prefix}{idx} {node(prefix, idx)} 0 {spice_num(cap)}")
        lines.append(f"Lres{prefix}{idx} {node(prefix, idx)} 0 {spice_num(shunt_l)}")
        lines.append(f"Rloss{prefix}{idx} {node(prefix, idx)} 0 {spice_num(shunt_r)}")
        if idx < n - 1:
            lines.append(f"L{prefix}{idx}_{idx+1} {node(prefix, idx)} {node(prefix, idx + 1)} {spice_num(series_l)}")
    lines.append(f"Rterm{prefix} {node(prefix, n - 1)} 0 {spice_num(max(6.0 * z0, 0.02))}")
    return series_l, cap, z0


def netlist_text(case: TLCase, out_dir: Path) -> TLExport:
    netlist_path = out_dir / case.filename
    csv_path = out_dir / f"{netlist_path.stem}_tran.csv"
    n = case.cell_count
    z = np.linspace(0.0, case.chain_length, n)
    pattern = qpm_pattern(z, case)
    weights = output_weights(case)
    freq8 = case.generated_mode
    freq12 = case.target_mode
    if case.shuffled:
        freq8 = 12.0
        freq12 = 8.0
    lines: List[str] = [
        f"* {case.name}",
        "* Normalized LC transmission-line / waveguide-like 4->8->12 ladder.",
        f"* topology={case.topology} role={case.role}",
        ".options reltol=3e-4 abstol=1e-8 chgtol=1e-12 method=gear maxord=2",
        "",
    ]
    l4, c4, z04 = add_ladder(lines, "s", case, SOURCE_HZ, case.k4)
    l8, c8, z08 = add_ladder(lines, "g", case, freq8, case.k8)
    l12, c12, z012 = add_ladder(lines, "t", case, freq12, case.k12, case.detune_target)
    cc = max(case.coupling_cap_scale, 0.0)
    if cc > 0:
        for idx in range(n):
            lines.append(f"Ccsg{idx} {node('s', idx)} {node('g', idx)} {spice_num(cc)}")
            lines.append(f"Ccgt{idx} {node('g', idx)} {node('t', idx)} {spice_num(0.75 * cc)}")
    if not case.no_nonlinearity:
        for idx, sign in enumerate(pattern):
            theta448 = case.delta_k_448 * float(z[idx])
            theta4812 = case.delta_k_4812 * float(z[idx])
            mix448 = case.mix448 * float(sign)
            mix4812 = case.mix4812 * float(sign)
            src = node("s", idx)
            gen = node("g", idx)
            tgt = node("t", idx)
            # V(source)^2 contains an 8-band component; V(source)*V(generated) contains a 12-band component.
            lines.append(f"Bmix8_{idx} {gen} 0 I={{-({spice_num(mix448)}*V({src})*V({src})*cos({spice_num(theta448)}))}}")
            lines.append(f"Bmix12_{idx} {tgt} 0 I={{-({spice_num(mix4812)}*V({src})*V({gen})*cos({spice_num(theta4812)}))}}")
            lines.append(f"Bsat{idx} {tgt} 0 I={{ {spice_num(case.saturation_conductance)}*V({tgt})*(V({src})*V({src})+V({gen})*V({gen})+V({tgt})*V({tgt})) }}")
    lines.extend([
        "",
        f"Vdrive4 vin4 0 SIN(0 {spice_num(case.drive_amplitude)} {spice_num(SOURCE_HZ)})",
        f"Rdrive4 vin4 {node('s', 0)} {spice_num(max(z04, 0.02))}",
    ])
    if case.direct_8_reference_drive:
        lines.extend([
            f"Vdrive8 vin8 0 SIN(0 {spice_num(case.drive_amplitude * case.direct_8_drive_scale)} {spice_num(GENERATED_HZ)})",
            f"Rdrive8 vin8 {node('g', 0)} {spice_num(max(z08, 0.02))}",
        ])
    lines.extend([
        f"Bobs4 obs4 0 V={{{weighted_sum('s', weights)}}}",
        f"Bobs8 obs8 0 V={{{weighted_sum('g', weights)}}}",
        f"Bobs12 obs12 0 V={{{weighted_sum('t', weights)}}}",
        "",
        ".control",
        "set noaskquit",
        "set filetype=ascii",
        f"tran {spice_num(TSTEP)} {spice_num(TSTOP)} 0 {spice_num(TSTEP)} uic",
        f"wrdata {csv_path.name} time v(obs4) v(obs8) v(obs12)",
        "quit",
        ".endc",
        ".end",
        "",
    ])
    netlist_path.write_text("\n".join(lines), encoding="utf-8")
    return TLExport(case=case, netlist_path=netlist_path, csv_path=csv_path)


def export_netlists(out_dir: Path) -> List[TLExport]:
    ensure_dir(out_dir)
    return [netlist_text(case, out_dir) for case in build_cases()]


def run_ngspice(export: TLExport, ngspice_path: str, timeout_s: int) -> RunResult:
    proxy = type("ExportProxy", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = spice_base.run_ngspice(proxy, ngspice_path, timeout_s)
    return RunResult(result.execution_status, result.success, result.reason, result.log_path)


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def read_wrdata(path: Path) -> Dict[str, np.ndarray]:
    if not path.exists():
        raise ValueError(f"CSV does not exist: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No data in {path}")
    first_tokens = lines[0].replace(",", " ").split()
    has_header = any(try_float(tok) is None for tok in first_tokens)
    rows: List[List[float]] = []
    for line in lines[1:] if has_header else lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(value) for value in values if value is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"No numeric data in {path}")
    min_cols = min(len(row) for row in rows)
    arr = np.asarray([row[:min_cols] for row in rows], dtype=float)
    if min_cols >= 8:
        return {"time": arr[:, 0], "v4": arr[:, 3], "v8": arr[:, 5], "v12": arr[:, 7]}
    if min_cols >= 4:
        return {"time": arr[:, 0], "v4": arr[:, 1], "v8": arr[:, 2], "v12": arr[:, 3]}
    raise ValueError(f"Expected at least four columns, got {min_cols}")


def complex_projection(signal: np.ndarray, time_s: np.ndarray, freq_hz: float) -> complex:
    phase = np.exp(-1j * 2.0 * np.pi * freq_hz * time_s)
    return 2.0 * np.mean(signal * phase)


def sliding_complex(signal: np.ndarray, time_s: np.ndarray, freq_hz: float,
                    window: int, step: int) -> Tuple[np.ndarray, np.ndarray]:
    mids: List[float] = []
    values: List[complex] = []
    for start in range(0, max(0, len(signal) - window), step):
        stop = start + window
        mids.append(float(np.mean(time_s[start:stop])))
        values.append(complex_projection(signal[start:stop], time_s[start:stop], freq_hz))
    return np.asarray(mids), np.asarray(values)


def envelope_cv(values: np.ndarray) -> float:
    if len(values) == 0:
        return float("inf")
    mean = float(np.mean(np.abs(values)))
    if mean <= EPS:
        return float("inf")
    return float(np.std(np.abs(values)) / mean)


def rms(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.sqrt(np.mean(values ** 2)))


def fft_peak(signal: np.ndarray, time_s: np.ndarray) -> Tuple[float, float]:
    if len(signal) < 8:
        return 0.0, 0.0
    dt = float(np.median(np.diff(time_s)))
    centered = signal - float(np.mean(signal))
    spec = np.fft.rfft(centered * np.hanning(len(centered)))
    freqs = np.fft.rfftfreq(len(centered), dt)
    idx = int(np.argmax(np.abs(spec[1:]))) + 1
    return float(freqs[idx]), float(np.abs(spec[idx]))


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


def behavioral_dependency_score(case: TLCase) -> float:
    if case.no_nonlinearity:
        return 0.08
    behavioral_mix = 0.28
    behavioral_saturation = 0.05 if case.saturation_conductance > 0 else 0.0
    behavioral_phase_signs = 0.05 if case.grating_kind != "none" or abs(case.delta_k_448) > 0 or abs(case.delta_k_4812) > 0 else 0.03
    return float(behavioral_mix + behavioral_saturation + behavioral_phase_signs)


def realism_score(case: TLCase) -> float:
    lc_fraction = 0.72
    if case.cell_count < 8:
        lc_fraction -= 0.15
    return max(0.0, min(1.0, lc_fraction + 0.25 * (1.0 - behavioral_dependency_score(case))))


def stress_proxy(values: Iterable[np.ndarray]) -> float:
    peak = max((float(np.max(np.abs(v))) for v in values if len(v)), default=0.0)
    return peak


def metrics(export: TLExport, data: Dict[str, np.ndarray],
            reference: Dict[str, np.ndarray] | None = None) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    case = export.case
    t = np.asarray(data["time"], dtype=float)
    v4 = np.asarray(data["v4"], dtype=float)
    v8 = np.asarray(data["v8"], dtype=float)
    v12 = np.asarray(data["v12"], dtype=float)
    finite = np.isfinite(t) & np.isfinite(v4) & np.isfinite(v8) & np.isfinite(v12)
    if int(np.sum(finite)) < 100:
        return {"metric_error": "not_enough_finite_samples"}, []
    t, v4, v8, v12 = t[finite], v4[finite], v8[finite], v12[finite]
    order = np.argsort(t)
    t, v4, v8, v12 = t[order], v4[order], v8[order], v12[order]
    keep = np.concatenate(([True], np.diff(t) > 0.0))
    t, v4, v8, v12 = t[keep], v4[keep], v8[keep], v12[keep]
    late = (t >= 0.45 * TSTOP) & (t < 0.92 * TSTOP)
    early = (t >= 0.08 * TSTOP) & (t < 0.25 * TSTOP)
    if int(np.sum(late)) < 100:
        late = t >= 0.50 * float(t[-1])
    tm = t[late]
    sample_dt = float(np.median(np.diff(t)))
    window = max(64, int(2.0 / max(sample_dt, EPS)))
    window = min(window, max(64, len(tm) // 2))
    step = max(8, window // 6)
    mids, z4 = sliding_complex(v4[late], tm, SOURCE_HZ, window, step)
    _, z8 = sliding_complex(v8[late], tm, GENERATED_HZ, window, step)
    _, z12 = sliding_complex(v12[late], tm, TARGET_HZ, window, step)
    min_len = min(len(z4), len(z8), len(z12))
    if min_len == 0:
        return {"metric_error": "no_phase_windows"}, []
    z4, z8, z12, mids = z4[:min_len], z8[:min_len], z12[:min_len], mids[:min_len]
    stable = np.median(np.abs(z8)) > 1e-9 and np.median(np.abs(z12)) > 1e-9
    if stable:
        phase_target = np.unwrap(np.angle(z4) + np.angle(z8) - np.angle(z12))
        phase_generated = np.unwrap(2.0 * np.angle(z4) - np.angle(z8))
        lock_target = float(abs(np.mean(np.exp(1j * ((phase_target + np.pi) % (2.0 * np.pi) - np.pi)))))
        lock_generated = float(abs(np.mean(np.exp(1j * ((phase_generated + np.pi) % (2.0 * np.pi) - np.pi)))))
        phase_step = np.abs(np.diff(phase_target))
    else:
        phase_target = np.asarray([])
        lock_target = 0.0
        lock_generated = 0.0
        phase_step = np.asarray([])
    target_amp = complex_projection(v12[late], tm, TARGET_HZ)
    target_power = 0.5 * abs(target_amp) ** 2
    purity = float(min(1.0, target_power / max(float(np.mean(v12[late] ** 2)), EPS)))
    ref_power = 0.0
    if reference is not None:
        rt = np.asarray(reference["time"], dtype=float)
        rv12 = np.asarray(reference["v12"], dtype=float)
        rlate = (rt >= 0.45 * TSTOP) & (rt < 0.92 * TSTOP)
        if int(np.sum(rlate)) > 100:
            ref_amp = complex_projection(rv12[rlate], rt[rlate], TARGET_HZ)
            ref_power = 0.5 * abs(ref_amp) ** 2
    bridge_ratio = float(target_power / max(ref_power, 1e-15)) if reference is not None else ""
    src_peak, _ = fft_peak(v4[late], tm)
    gen_peak, _ = fft_peak(v8[late], tm)
    tgt_peak, _ = fft_peak(v12[late], tm)
    mismatch = math.sqrt(case.delta_k_448 ** 2 + case.delta_k_4812 ** 2) * case.chain_length
    velocity = float(2.0 * math.pi * SOURCE_HZ / max(abs(case.k4), EPS))
    gen_cv = envelope_cv(z8)
    tgt_cv = envelope_cv(z12)
    energy_proxy = float(abs(rms(v4[late]) + rms(v8[late]) + rms(v12[late]) - rms(v4[early])) / max(rms(v4[late]) + rms(v8[late]) + rms(v12[late]), 1.0))
    result: Dict[str, float | str] = {
        "phase_lock_target": lock_target,
        "phase_lock_generated": lock_generated,
        "bridge_ratio": bridge_ratio,
        "target_spectral_purity": purity,
        "target_coherent_growth": float(rms(v12[late]) / max(rms(v12[early]), 1e-15)),
        "target_coherent_power": float(target_power),
        "generated_envelope_cv": gen_cv if math.isfinite(gen_cv) else "",
        "target_envelope_cv": tgt_cv if math.isfinite(tgt_cv) else "",
        "max_phase_jump": float(np.max(phase_step)) if len(phase_step) else 0.0,
        "near_slip_count": float(coalesced_count(np.where(phase_step > 1.0)[0])),
        "accumulated_phase_mismatch": mismatch,
        "effective_phase_velocity_estimate": velocity,
        "source_fft_peak": src_peak,
        "generated_fft_peak": gen_peak,
        "target_fft_peak": tgt_peak,
        "transmission_line_realism_score": realism_score(case),
        "behavioral_dependency_score": behavioral_dependency_score(case),
        "energy_budget_proxy": energy_proxy,
        "component_stress_proxy": stress_proxy((v4, v8, v12)),
    }
    rows: List[Dict[str, float | str]] = []
    for idx in range(0, min_len, max(1, min_len // 180)):
        rows.append({
            "row_type": "spice_tl_timeseries",
            "case_id": "",
            "name": case.name,
            "topology": case.topology,
            "role": case.role,
            "time": float(mids[idx]),
            "source_envelope": float(abs(z4[idx])),
            "generated_envelope": float(abs(z8[idx])),
            "target_envelope": float(abs(z12[idx])),
            "target_phase_error": float(((phase_target[idx] + np.pi) % (2.0 * np.pi) - np.pi)) if len(phase_target) else "",
        })
    return result, rows


def control_leakage(row: Dict[str, float | str]) -> float:
    if str(row.get("role")) != "control" or str(row.get("execution_status")) != "ran_successfully":
        return 0.0
    lock = safe_float(row.get("phase_lock_target"))
    bridge = max(0.0, safe_float(row.get("bridge_ratio")))
    if bridge < 0.50:
        return 0.0
    if lock < 0.50:
        return 0.0
    growth = safe_float(row.get("target_coherent_growth"))
    purity = safe_float(row.get("target_spectral_purity"))
    power = safe_float(row.get("target_coherent_power"))
    gate = min(power / 1e-8, 1.0)
    return float(gate * (0.45 * min(lock / 0.50, 1.0) + 0.25 * min(bridge / 0.50, 1.0) + 0.20 * min(growth / 1.0, 1.0) + 0.10 * min(purity / 0.80, 1.0)))


def promotion(row: Dict[str, float | str], controls_dead: bool, controls_mostly_clean: bool) -> str:
    if str(row.get("role")) == "ceiling_reference":
        return "ceiling_reference_not_discovery"
    if str(row.get("role")) == "control":
        if safe_float(row.get("target_coherent_growth")) > 1.0 and safe_float(row.get("phase_lock_target")) < 0.50:
            return "reject_due_to_phase_mismatch"
        return "control_dead" if control_leakage(row) < 0.10 else "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "ran_successfully":
        return "not_promoted"
    lock = safe_float(row.get("phase_lock_target"))
    bridge = safe_float(row.get("bridge_ratio"))
    purity = safe_float(row.get("target_spectral_purity"))
    growth = safe_float(row.get("target_coherent_growth"))
    gen_cv = safe_float(row.get("generated_envelope_cv"), float("inf"))
    jump = safe_float(row.get("max_phase_jump"), float("inf"))
    dep = safe_float(row.get("behavioral_dependency_score"), 1.0)
    if growth > 1.0 and lock < 0.50:
        return "reject_due_to_phase_mismatch"
    if lock > 0.90 and bridge > 1.5 and purity > 0.80 and growth > 1.0 and gen_cv < 0.25 and jump < 1.0 and controls_dead and dep < ENVELOPE_LADDER_BEHAVIORAL_BASELINE:
        return "spice_tl_phase_candidate"
    if lock > 0.50 and bridge > 1.0 and controls_mostly_clean:
        return "spice_tl_phase_near_miss"
    return "not_promoted"


def summarize_row(case_id: str, export: TLExport, result: RunResult, row_metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    case = export.case
    row: Dict[str, float | str] = {
        "row_type": "spice_tl_refine",
        "case_id": case_id,
        "name": case.name,
        "topology": case.topology,
        "role": case.role,
        "netlist_file": export.netlist_path.name,
        "csv_file": export.csv_path.name if export.csv_path.exists() else "",
        "execution_status": result.execution_status,
        "convergence_failure_reason": "" if result.success else result.reason,
        "source_only_drive": str(not case.direct_8_reference_drive and case.role != "ceiling_reference"),
        "direct_8_drive_present": str(case.direct_8_reference_drive),
        "direct_12_drive_present": str(False),
        "target_frequency_injection_present": str(False),
        "cell_count": case.cell_count,
        "chain_length": case.chain_length,
        "k4": case.k4,
        "k8": case.k8,
        "k12": case.k12,
        "delta_k_448": case.delta_k_448,
        "delta_k_4812": case.delta_k_4812,
        "qpm_period": case.qpm_period,
        "grating_kind": case.grating_kind,
        "mix448": case.mix448,
        "mix4812": case.mix4812,
        "behavioral_dependency_score": behavioral_dependency_score(case),
        "transmission_line_realism_score": realism_score(case),
    }
    if row_metrics:
        row.update(row_metrics)
    return row


def aggregate(rows: List[Dict[str, float | str]], out_dir: Path, run_requested: bool, ngspice_available: bool) -> Dict[str, float | str]:
    controls = [r for r in rows if str(r.get("role")) == "control"]
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    leakage = max((control_leakage(r) for r in controls), default=0.0)
    controls_dead = leakage < 0.10
    controls_mostly_clean = leakage < 0.25
    for row in rows:
        row["control_leakage_score"] = leakage
        row["promotion_category"] = promotion(row, controls_dead, controls_mostly_clean)
    candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_tl_phase_candidate"]
    near = [r for r in discovery if str(r.get("promotion_category")) == "spice_tl_phase_near_miss"]
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    best = max(successful, key=lambda r: safe_float(r.get("phase_lock_target")), default={})
    phase = next((r for r in rows if str(r.get("name")) == "tl_phase_matched_ladder"), {})
    qpm = next((r for r in rows if str(r.get("name")) == "tl_qpm_ladder"), {})
    mismatch = next((r for r in rows if str(r.get("name")) == "tl_mismatched_ladder_control"), {})
    lumped = next((r for r in rows if str(r.get("name")) == "tl_lumped_equivalent_control"), {})
    statuses = sorted(set(str(r.get("execution_status")) for r in rows))
    if candidates:
        next_step = "physical waveguide modeling, then PCB/transmission-line approximation"
    elif near:
        next_step = "transmission-line ladder refinement before physical waveguide modeling"
    else:
        next_step = "acoustic waveguide model or rejection of this physical route under current assumptions"
    return {
        "row_type": "aggregate",
        "valid_spice_netlists_generated": str(all((out_dir / name).exists() for name in REQUIRED_NETLISTS)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": ";".join(statuses),
        "rows_total": len(rows),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "spice_tl_phase_candidate_count": len(candidates),
        "spice_tl_phase_near_miss_count": len(near),
        "best_case": str(best.get("case_id", "")),
        "best_topology": str(best.get("topology", "")),
        "best_phase_lock": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio", ""),
        "phase_matched_lock": phase.get("phase_lock_target", ""),
        "phase_matched_bridge_ratio": phase.get("bridge_ratio", ""),
        "phase_matched_behavioral_dependency": phase.get("behavioral_dependency_score", ""),
        "behavioral_dependency_lower_than_envelope": str(safe_float(phase.get("behavioral_dependency_score"), 1.0) < ENVELOPE_LADDER_BEHAVIORAL_BASELINE),
        "phase_mismatch_kills_lock": str(safe_float(mismatch.get("phase_lock_target")) < 0.50),
        "phase_mismatch_suppresses_material_bridge": str(safe_float(mismatch.get("bridge_ratio")) < 0.50),
        "mismatched_lock": mismatch.get("phase_lock_target", ""),
        "mismatched_bridge_ratio": mismatch.get("bridge_ratio", ""),
        "qpm_helps": str(
            safe_float(qpm.get("phase_lock_target")) * max(safe_float(qpm.get("bridge_ratio")), 0.0)
            > safe_float(mismatch.get("phase_lock_target")) * max(safe_float(mismatch.get("bridge_ratio")), 0.0)
        ),
        "qpm_lock": qpm.get("phase_lock_target", ""),
        "qpm_bridge_ratio": qpm.get("bridge_ratio", ""),
        "lumped_lock": lumped.get("phase_lock_target", ""),
        "controls_dead": str(controls_dead),
        "controls_mostly_clean": str(controls_mostly_clean),
        "max_control_leakage_score": leakage,
        "recommended_next_step": next_step,
    }


def write_report(out_dir: Path, summary: Dict[str, float | str], rows: List[Dict[str, float | str]]) -> None:
    lines = [
        "# SPICE 4->8->12 Transmission-Line Refinement",
        "",
        "Normalized LC transmission-line refinement of the distributed phase-matched bridge.",
        "",
        "## Direct Answers",
        "",
        f"1. Can a less-behavioral transmission-line ladder preserve the lock? candidates={summary['spice_tl_phase_candidate_count']}; best={summary['best_case']} lock={summary['best_phase_lock']} bridge={summary['best_bridge_ratio']}.",
        f"2. Does lowering behavioral dependency weaken or preserve the bridge? behavioral_dependency_lower_than_envelope={summary['behavioral_dependency_lower_than_envelope']}; phase_matched_dependency={summary['phase_matched_behavioral_dependency']}.",
        f"3. Does phase mismatch still kill lock? raw_lock={summary['phase_mismatch_kills_lock']}; material_bridge_suppressed={summary['phase_mismatch_suppresses_material_bridge']}; mismatched_lock={summary['mismatched_lock']}, mismatched_bridge={summary['mismatched_bridge_ratio']}.",
        f"4. Does QPM help? {summary['qpm_helps']}; qpm_lock={summary['qpm_lock']}, qpm_bridge={summary['qpm_bridge_ratio']}.",
        f"5. Do controls remain dead? {summary['controls_dead']}; max_control_leakage={summary['max_control_leakage_score']}.",
        f"6. Next step: {summary['recommended_next_step']}.",
        "",
        "## Rows",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row.get('case_id')} {row.get('name')}: status={row.get('execution_status')}, "
            f"category={row.get('promotion_category')}, lock={row.get('phase_lock_target', '')}, "
            f"bridge={row.get('bridge_ratio', '')}, purity={row.get('target_spectral_purity', '')}, "
            f"behavioral_dependency={row.get('behavioral_dependency_score', '')}."
        )
    lines.extend([
        "",
        "## Notes",
        "",
        "- LC ladder propagation and loading are explicit SPICE components.",
        "- Behavioral sources remain for distributed nonlinear mixing and saturation proxies.",
        "- Direct 4+8 is a separated ceiling reference only.",
    ])
    (out_dir / "README_SPICE_412_TRANSMISSION_LINE_REFINE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 4->8->12 transmission-line SPICE refinement.")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--ngspice-path", default="")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    exports = export_netlists(out_dir)
    ngspice_path = None
    if args.run:
        if args.ngspice_path:
            ngspice_path = args.ngspice_path
        else:
            try:
                ngspice_path = spice_base.resolve_ngspice_path(None)
            except subprocess.TimeoutExpired:
                ngspice_path = None
    ngspice_available = ngspice_path is not None
    results: Dict[str, RunResult] = {}
    parsed: Dict[str, Dict[str, np.ndarray]] = {}
    if args.run and not ngspice_available:
        for export in exports:
            results[export.case.name] = RunResult("skipped_no_ngspice", False, "ngspice not found")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed[export.case.name] = read_wrdata(export.csv_path)
                except Exception as exc:
                    result = RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            results[export.case.name] = result
    else:
        for export in exports:
            results[export.case.name] = RunResult("exported", False, "export only; use --run")

    ids = {
        "tl_phase_matched_ladder": "t001",
        "tl_qpm_ladder": "t002",
        "tl_mismatched_ladder_control": "c001",
        "tl_lumped_equivalent_control": "c002",
        "tl_linear_no_nonlinearity_control": "c003",
        "tl_detuned_target_control": "c004",
        "tl_shuffled_frequency_control": "c005",
        "tl_direct_4plus8_reference": "direct_4plus8_reference",
    }
    reference = parsed.get("tl_direct_4plus8_reference")
    rows: List[Dict[str, float | str]] = []
    ts_rows: List[Dict[str, float | str]] = []
    for export in exports:
        metric_row: Dict[str, float | str] | None = None
        ts: List[Dict[str, float | str]] = []
        if export.case.name in parsed:
            try:
                metric_row, ts = metrics(export, parsed[export.case.name], None if export.case.role == "ceiling_reference" else reference)
            except Exception as exc:
                results[export.case.name] = RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", results[export.case.name].log_path)
                metric_row = {"metric_error": f"{type(exc).__name__}: {exc}"}
        case_id = ids[export.case.name]
        for item in ts:
            item["case_id"] = case_id
            ts_rows.append(item)
        rows.append(summarize_row(case_id, export, results[export.case.name], metric_row))
    summary = aggregate(rows, out_dir, args.run, ngspice_available)
    all_rows = [summary] + rows
    write_csv(out_dir / "spice_412_tl_summary.csv", all_rows)
    if ts_rows:
        write_csv(out_dir / "spice_412_tl_timeseries.csv", ts_rows)
    write_report(out_dir, summary, rows)
    (out_dir / "spice_412_tl_summary.json").write_text(json.dumps({
        "aggregate": summary,
        "rows": all_rows,
        "cases": [asdict(export.case) for export in exports],
        "model": {
            "description": "Normalized LC transmission-line ladder with distributed nonlinear mixing.",
            "tstop": TSTOP,
            "tstep": TSTEP,
            "envelope_ladder_behavioral_baseline": ENVELOPE_LADDER_BEHAVIORAL_BASELINE,
        },
    }, indent=2), encoding="utf-8")
    print(f"SPICE 4->8->12 transmission-line refinement written to: {out_dir.resolve()}")
    print(f"valid_spice_netlists_generated={summary['valid_spice_netlists_generated']}")
    print(f"run_requested={summary['run_requested']}")
    print(f"ngspice_available={summary['ngspice_available']}")
    print(f"execution_statuses={summary['execution_statuses']}")
    print(f"candidate_count={summary['spice_tl_phase_candidate_count']}")
    print(f"controls_dead={summary['controls_dead']}")


if __name__ == "__main__":
    main()
