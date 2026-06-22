#!/usr/bin/env python3
"""Electrical control forensics for the 4->8->12 bridge.

This track asks whether the 150 MHz purity seen in tuned hybrid/varactor
electrical rows is produced inside the line before extraction, or whether the
passive readout/filter network is manufacturing apparent purity from a weak
broadband response.  It reuses the existing hybrid purity-lock-in netlists but
forces wider ngspice probes at multiple internal nodes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import spice_412_electrical_candidate_race as race
import spice_412_hybrid_purity_lockin as lockin
import spice_412_varactor_nltl_design as design


OUT_DIR = Path("runs") / "spice_412_electrical_control_forensics"
SOURCE_HZ = design.SOURCE_HZ
GENERATED_HZ = design.GENERATED_HZ
TARGET_HZ = design.TARGET_HZ
EPS = 1.0e-30


@dataclass(frozen=True)
class ForensicsCase(lockin.LockinCase):
    probe_kind: str = "hybrid"
    prior_case_id: str = ""
    generated_path_suppressed: bool = False
    target_velocity_detuned_probe: bool = False
    phase_mismatched_probe: bool = False
    extraction_removed_probe: bool = False
    forensics_role: str = "line_probe"


@dataclass(frozen=True)
class ForensicsExport:
    case: ForensicsCase
    netlist_path: Path
    csv_path: Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
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
    return race.safe_float(value, default)


def spice_num(value: float) -> str:
    return design.spice_num(value)


def clean_name(value: str) -> str:
    return race.clean_name(value)


def to_forensics_case(base: lockin.LockinCase, **updates: object) -> ForensicsCase:
    data = asdict(base)
    data.update(updates)
    return ForensicsCase(**data)


def make_probe(
    case_id: str,
    prior: str,
    seed: str,
    probe_kind: str,
    role: str,
    notes: str,
    case_updates: Dict[str, object] | None = None,
    **kwargs: object,
) -> ForensicsCase:
    base = lockin.make_case(case_id, seed=seed, role=role, notes=notes, **kwargs)
    name = clean_name(f"{case_id}_{probe_kind}_{prior}")
    updates: Dict[str, object] = {
        "name": name,
        "filename": f"{name}.cir",
        "probe_kind": probe_kind,
        "prior_case_id": prior,
        "forensics_role": "ceiling_reference" if role == "ceiling_reference" else "line_probe",
    }
    if case_updates:
        updates.update(case_updates)
    return to_forensics_case(
        base,
        **updates,
    )


def build_cases() -> List[ForensicsCase]:
    """Return the fixed 12-row forensic study requested by the task."""

    p033 = dict(
        extraction_topology="single_high_q",
        extraction_q=24.0,
        q_label="high",
        output_load=100.0,
        post_filter=1.5,
        target_scale=0.993,
        generated_scale=1.004,
        phase_velocity_m_s=5.10e6,
    )
    h024 = dict(extraction_topology="single_high_q", extraction_q=18.0, q_label="medium")
    h025 = dict(extraction_topology="single_high_q", extraction_q=18.0, q_label="medium")

    cases: List[ForensicsCase] = [
        make_probe(
            "f001",
            "p033",
            "h025",
            "best_lockin_hybrid",
            "discovery",
            "Best prior p033 hybrid purity-lock-in row, re-instrumented before and after extraction.",
            **p033,
        ),
        make_probe(
            "f002",
            "h024",
            "h024",
            "previous_hybrid_near_miss",
            "discovery",
            "Best previous h024 hybrid near-miss baseline.",
            **h024,
        ),
        make_probe(
            "f003",
            "h025",
            "h025",
            "growth_preserving_hybrid_near_miss",
            "discovery",
            "Best previous h025 growth-preserving hybrid near-miss baseline.",
            **h025,
        ),
        make_probe(
            "f004",
            "pure_varactor_tuned",
            "h025",
            "tuned_pure_varactor_extraction",
            "control",
            "Pure-varactor line using the same tuned 150 MHz extraction as p033.",
            family="pure_varactor_tuned_extraction_forensics",
            varactor_fraction=1.0,
            magnetic_strength=0.0,
            magnetic_count=0,
            magnetic_loss=0.0,
            **p033,
        ),
        make_probe(
            "f005",
            "pure_varactor_no_extraction",
            "h025",
            "pure_varactor_no_extraction",
            "control",
            "Pure-varactor line with target extraction removed.",
            family="pure_varactor_no_extraction_forensics",
            varactor_fraction=1.0,
            magnetic_strength=0.0,
            magnetic_count=0,
            magnetic_loss=0.0,
            cleanup="none",
            extraction_topology="none",
            notch50=False,
            notch100=False,
        ),
        make_probe(
            "f006",
            "pure_magnetic_same_extraction",
            "h024",
            "pure_magnetic_same_extraction",
            "control",
            "Pure magnetic-core nonlinearity proxy with fixed capacitors and the same extraction network.",
            family="pure_magnetic_same_extraction_forensics",
            fixed_cap_only=True,
            cjo_scale=0.0,
            magnetic_strength=0.85,
            magnetic_count=22,
            magnetic_loss=0.25,
            **p033,
        ),
        make_probe(
            "f007",
            "hybrid_no_extraction",
            "h025",
            "hybrid_no_extraction",
            "discovery",
            "Hybrid row with all target extraction and rejection filtering removed.",
            family="hybrid_no_extraction_forensics",
            cleanup="none",
            extraction_topology="none",
            notch50=False,
            notch100=False,
            drive_v=1.8,
            cjo_scale=0.90,
            magnetic_strength=0.30,
            case_updates={"nonlinear_fraction": 0.55},
        ),
        make_probe(
            "f008",
            "generated_path_suppressed",
            "h025",
            "generated_path_suppressed",
            "control",
            "Hybrid line with the 50+50 to 100 MHz pathway intentionally weakened before target extraction.",
            family="hybrid_generated_path_suppressed_forensics",
            varactor_fraction=0.16,
            magnetic_start=0.62,
            magnetic_end=1.00,
            overlap=0.00,
            cjo_scale=0.28,
            bias_v=12.0,
            magnetic_strength=0.22,
            magnetic_count=10,
            magnetic_loss=0.10,
            case_updates={"generated_path_suppressed": True, "nonlinear_fraction": 0.12},
            **{**p033, "generated_scale": 0.76},
        ),
        make_probe(
            "f009",
            "target_velocity_detuned",
            "h025",
            "target_velocity_detuned",
            "control",
            "Hybrid line with target phase velocity detuned while retaining extraction.",
            family="detuned_150mhz_phase_velocity_line",
            case_updates={"target_velocity_detuned_probe": True},
            **{**h024, "target_scale": 0.82, "generated_scale": 0.94, "phase_velocity_m_s": 3.9e6},
        ),
        make_probe(
            "f010",
            "phase_mismatched_line",
            "h024",
            "phase_mismatched_line",
            "control",
            "Hybrid line with deliberate generated and target phase mismatch.",
            family="hybrid_phase_mismatched_forensics",
            target_scale=1.22,
            generated_scale=0.91,
            phase_velocity_m_s=4.1e6,
            case_updates={"phase_mismatched_probe": True},
            **h024,
        ),
        make_probe(
            "f011",
            "linear_fixed_component_extraction",
            "h024",
            "linear_fixed_component_extraction",
            "control",
            "Linear fixed-component line with the target extraction network still present.",
            family="linear_fixed_component_extraction_forensics",
            fixed_cap_only=True,
            cjo_scale=0.0,
            magnetic_strength=0.0,
            magnetic_count=0,
            magnetic_loss=0.0,
            case_updates={"nonlinear_fraction": 0.0},
            **p033,
        ),
        make_probe(
            "direct_50plus100_reference",
            "direct_reference",
            "h024",
            "direct_50plus100_ceiling_reference",
            "ceiling_reference",
            "Separated direct 50+100 MHz ceiling denominator only; not a discovery row.",
            family="direct_50plus100_reference",
            source_only=False,
            direct_100_v=1.0,
            magnetic_strength=0.0,
            magnetic_count=0,
            magnetic_loss=0.0,
        ),
    ]

    # The line-only probe intentionally has no extraction network.
    cases[6] = to_forensics_case(cases[6], extraction_removed_probe=True)
    return cases


def original_measure_node(netlist: str, fallback: str) -> str:
    for line in netlist.splitlines():
        stripped = line.strip()
        if not stripped.startswith("wrdata "):
            continue
        voltage_tokens: List[str] = []
        parts = stripped.replace(",", " ").split()
        for token in parts:
            token_lower = token.lower()
            if token_lower.startswith("v(") and token.endswith(")"):
                voltage_tokens.append(token[2:-1])
        if voltage_tokens:
            return voltage_tokens[-1]
    return fallback


def instrument_netlist(case: ForensicsCase, csv_path: Path) -> str:
    text = lockin.netlist_for_case(case, csv_path)
    raw_node = design.n(case.cell_count)
    measure = original_measure_node(text, raw_node)
    q1 = max(1, case.cell_count // 4)
    mid = max(1, case.cell_count // 2)
    q3 = max(1, (3 * case.cell_count) // 4)
    replacement = (
        f"wrdata {csv_path.name} time "
        f"v({design.n(0)}) v({design.n(q1)}) v({design.n(mid)}) v({design.n(q3)}) "
        f"v({raw_node}) v({measure}) i(Vsrc) i(Vbias)"
    )
    lines: List[str] = []
    replaced = False
    for line in text.splitlines():
        if line.strip().startswith("wrdata "):
            lines.append(replacement)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise ValueError(f"could not find wrdata line for {case.case_id}")
    lines.insert(
        1,
        (
            f"* Forensics probes: pre-extraction raw={raw_node}; post-extraction={measure}; "
            f"source-only={case.source_only_drive}; no direct 150 MHz source."
        ),
    )
    return "\n".join(lines) + "\n"


def export_netlists(out_dir: Path) -> List[ForensicsExport]:
    ensure_dir(out_dir)
    exports: List[ForensicsExport] = []
    for case in build_cases():
        netlist_path = out_dir / case.filename
        csv_path = out_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist_path.write_text(instrument_netlist(case, csv_path), encoding="utf-8")
        exports.append(ForensicsExport(case=case, netlist_path=netlist_path, csv_path=csv_path))
    return exports


def run_ngspice(export: ForensicsExport, ngspice_path: str, timeout_s: int) -> design.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = design.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return design.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def read_forensics_transient(path: Path) -> Dict[str, np.ndarray]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"empty transient CSV {path}")
    first = lines[0].replace(",", " ").split()
    has_header = any(try_float(tok) is None for tok in first)
    data_lines = lines[1:] if has_header else lines
    rows: List[List[float]] = []
    for line in data_lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(v) for v in values if v is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"no numeric rows in {path}")
    width = min(len(row) for row in rows)
    arr = np.asarray([row[:width] for row in rows], dtype=float)
    if has_header:
        offset = 2 if len(first) > 1 and first[1].lower() == "time" else 1
    else:
        offset = 2 if width >= 10 and np.allclose(arr[:, 0], arr[:, 1]) else 1
    if width < offset + 8:
        raise ValueError(f"expected time plus 8 vectors in {path}, got {width} columns")
    return {
        "time": arr[:, 0],
        "v_in": arr[:, offset + 0],
        "v_q1": arr[:, offset + 1],
        "v_mid": arr[:, offset + 2],
        "v_q3": arr[:, offset + 3],
        "v_raw": arr[:, offset + 4],
        "v_post": arr[:, offset + 5],
        "i_src": arr[:, offset + 6],
        "i_bias": arr[:, offset + 7],
    }


def uniform_resample(data: Dict[str, np.ndarray], max_points: int = 12000) -> Dict[str, np.ndarray]:
    keys = ("v_in", "v_q1", "v_mid", "v_q3", "v_raw", "v_post", "i_src", "i_bias")
    t = np.asarray(data["time"], dtype=float)
    finite = np.isfinite(t)
    for key in keys:
        finite &= np.isfinite(np.asarray(data[key], dtype=float))
    order = np.argsort(t[finite])
    t_sorted = t[finite][order]
    keep = np.concatenate(([True], np.diff(t_sorted) > 0.0))
    t_sorted = t_sorted[keep]
    if len(t_sorted) < 16:
        raise ValueError("not enough unique transient samples")
    n_points = min(max_points, len(t_sorted))
    target_t = np.linspace(float(t_sorted[0]), float(t_sorted[-1]), n_points)
    result: Dict[str, np.ndarray] = {"time": target_t}
    for key in keys:
        values = np.asarray(data[key], dtype=float)[finite][order][keep]
        result[key] = np.interp(target_t, t_sorted, values)
    return result


def complex_projection(signal: np.ndarray, t: np.ndarray, freq_hz: float) -> complex:
    return 2.0 * np.mean(signal * np.exp(-1j * 2.0 * math.pi * freq_hz * t))


def sliding_projection(signal: np.ndarray, t: np.ndarray, freq_hz: float, cycles: int = 8) -> Tuple[np.ndarray, np.ndarray]:
    dt = float(np.median(np.diff(t)))
    window = max(16, int(round(cycles / (freq_hz * max(dt, EPS)))))
    step = max(4, window // 4)
    amps: List[float] = []
    phases: List[float] = []
    for start in range(0, max(0, len(signal) - window), step):
        stop = start + window
        z = complex_projection(signal[start:stop], t[start:stop], freq_hz)
        amps.append(abs(z))
        phases.append(float(np.angle(z)))
    return np.asarray(amps), np.asarray(phases)


def fft_peak(signal: np.ndarray, t: np.ndarray, lo_hz: float, hi_hz: float) -> Tuple[float, float]:
    dt = float(np.median(np.diff(t)))
    centered = signal - np.mean(signal)
    window = np.hanning(len(centered))
    spec = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), dt)
    power = np.abs(spec) ** 2
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    if not np.any(mask):
        return 0.0, 0.0
    idxs = np.nonzero(mask)[0]
    peak_idx = idxs[int(np.argmax(power[mask]))]
    return float(freqs[peak_idx]), float(power[peak_idx])


def band_power(signal: np.ndarray, t: np.ndarray, center_hz: float, half_width_hz: float) -> float:
    dt = float(np.median(np.diff(t)))
    centered = signal - np.mean(signal)
    spec = np.fft.rfft(centered * np.hanning(len(centered)))
    freqs = np.fft.rfftfreq(len(centered), dt)
    power = np.abs(spec) ** 2
    mask = (freqs >= center_hz - half_width_hz) & (freqs <= center_hz + half_width_hz)
    return float(np.sum(power[mask]))


def band_metrics(signal: np.ndarray, t: np.ndarray, source_phase_signal: np.ndarray | None = None) -> Dict[str, object]:
    source_peak, source_power = fft_peak(signal, t, SOURCE_HZ * 0.85, SOURCE_HZ * 1.15)
    gen_peak, gen_power = fft_peak(signal, t, GENERATED_HZ * 0.85, GENERATED_HZ * 1.15)
    target_peak, target_power = fft_peak(signal, t, TARGET_HZ * 0.85, TARGET_HZ * 1.15)
    target_band = band_power(signal, t, TARGET_HZ, 8.0e6)
    broad_power = band_power(signal, t, 100.0e6, 90.0e6)
    source_amp, source_phase = sliding_projection(source_phase_signal if source_phase_signal is not None else signal, t, SOURCE_HZ)
    gen_amp, gen_phase = sliding_projection(signal, t, GENERATED_HZ)
    target_amp, target_phase = sliding_projection(signal, t, TARGET_HZ)
    n_gen = min(len(gen_phase), len(source_phase))
    n_target = min(len(target_phase), len(source_phase))
    phase_lock_generated = (
        float(abs(np.mean(np.exp(1j * (gen_phase[:n_gen] - 2.0 * source_phase[:n_gen])))))
        if n_gen
        else 0.0
    )
    phase_lock_target = (
        float(abs(np.mean(np.exp(1j * (target_phase[:n_target] - 3.0 * source_phase[:n_target])))))
        if n_target
        else 0.0
    )
    generated_cv = float(np.std(gen_amp) / max(np.mean(gen_amp), EPS)) if len(gen_amp) else 0.0
    target_cv = float(np.std(target_amp) / max(np.mean(target_amp), EPS)) if len(target_amp) else 0.0
    if len(target_phase) > 2:
        jumps = np.abs(np.diff(np.unwrap(target_phase)))
        max_jump = float(np.max(jumps))
        near_slips = int(np.sum(jumps > 1.0))
    else:
        max_jump = 0.0
        near_slips = 0
    first = max(1, len(target_amp) // 5)
    last = max(1, len(target_amp) // 5)
    target_growth = float(np.mean(target_amp[-last:]) / max(np.mean(target_amp[:first]), EPS)) if len(target_amp) else 0.0
    coherent_power = float(abs(complex_projection(signal, t, TARGET_HZ)) ** 2)
    return {
        "source_fft_peak_hz": source_peak,
        "source_fft_power": source_power,
        "generated_fft_peak_hz": gen_peak,
        "generated_fft_power": gen_power,
        "target_fft_peak_hz": target_peak,
        "target_fft_power": target_power,
        "spectral_purity_150mhz": target_band / max(broad_power, EPS),
        "target_band_coherent_growth": target_growth,
        "target_coherent_power": coherent_power,
        "phase_lock_generated": phase_lock_generated,
        "phase_lock_target": phase_lock_target,
        "generated_envelope_cv": generated_cv,
        "target_envelope_cv": target_cv,
        "max_phase_jump": max_jump,
        "near_slip_count": near_slips,
    }


def amplitude_at(signal: np.ndarray, t: np.ndarray, freq_hz: float) -> float:
    return float(abs(complex_projection(signal, t, freq_hz)))


def db_rejection(pre_power: float, post_power: float) -> float:
    return 10.0 * math.log10(max(pre_power, EPS) / max(post_power, EPS))


def control_leakage(purity: float, growth: float, bridge_ratio: float, lock: float) -> float:
    return float(
        min(
            1.0,
            max(purity - 0.20, 0.0)
            + max(growth - 1.0, 0.0) / 2.0
            + (max(bridge_ratio - 1.0, 0.0) / 3.0 if lock > 0.50 else 0.0),
        )
    )


def measure_case(export: ForensicsExport, data: Dict[str, np.ndarray], reference_power: float | None) -> Dict[str, object]:
    case = export.case
    vals = lockin.lockin_cell_values(case)
    d = uniform_resample(data)
    t = d["time"]
    start = int(0.25 * len(t))
    t2 = t[start:]
    raw = d["v_raw"][start:]
    post = d["v_post"][start:]
    source_probe = d["v_in"][start:]

    pre = band_metrics(raw, t2, source_probe)
    post_metrics = band_metrics(post, t2, source_probe)
    q1 = d["v_q1"][start:]
    mid = d["v_mid"][start:]
    q3 = d["v_q3"][start:]
    node_signals = {"q1": q1, "mid": mid, "q3": q3, "raw": raw}
    source_amps = {name: amplitude_at(sig, t2, SOURCE_HZ) for name, sig in node_signals.items()}
    generated_amps = {name: amplitude_at(sig, t2, GENERATED_HZ) for name, sig in node_signals.items()}
    target_amps = {name: amplitude_at(sig, t2, TARGET_HZ) for name, sig in node_signals.items()}

    pre_target_power = safe_float(pre.get("target_fft_power"))
    post_target_power = safe_float(post_metrics.get("target_fft_power"))
    pre_source_power = safe_float(pre.get("source_fft_power"))
    post_source_power = safe_float(post_metrics.get("source_fft_power"))
    pre_generated_power = safe_float(pre.get("generated_fft_power"))
    post_generated_power = safe_float(post_metrics.get("generated_fft_power"))
    gain_150 = post_target_power / max(pre_target_power, EPS)
    gain_50 = post_source_power / max(pre_source_power, EPS)
    gain_100 = post_generated_power / max(pre_generated_power, EPS)
    filter_selectivity = gain_150 / max(0.5 * (gain_50 + gain_100), EPS)
    bridge_ratio = safe_float(post_metrics.get("target_coherent_power")) / max(reference_power or post_metrics.get("target_coherent_power") or EPS, EPS)
    pre_bridge_proxy = (
        safe_float(pre.get("spectral_purity_150mhz"))
        * safe_float(pre.get("target_band_coherent_growth"))
        * safe_float(pre.get("phase_lock_target"))
    )
    post_bridge_proxy = (
        safe_float(post_metrics.get("spectral_purity_150mhz"))
        * safe_float(post_metrics.get("target_band_coherent_growth"))
        * safe_float(post_metrics.get("phase_lock_target"))
    )
    peak_voltage = float(
        max(
            np.max(np.abs(d["v_in"])),
            np.max(np.abs(d["v_q1"])),
            np.max(np.abs(d["v_mid"])),
            np.max(np.abs(d["v_q3"])),
            np.max(np.abs(d["v_raw"])),
            np.max(np.abs(d["v_post"])),
        )
    )
    peak_bias_current = float(np.max(np.abs(d["i_bias"])))
    peak_varactor_current = peak_bias_current / max(case.cell_count + 1, 1)
    reverse_bias_margin = case.bias_v - peak_voltage
    stress_score = float(
        max(
            peak_voltage / max(case.bias_v * 0.85, EPS),
            peak_varactor_current / 0.020,
            (case.bias_v + peak_voltage) / max(case.varactor_bv_v, EPS),
        )
    )
    if stress_score < 0.75 and reverse_bias_margin > 0.25:
        stress_class = "plausible"
    elif stress_score < 1.35 and reverse_bias_margin > -0.5:
        stress_class = "aggressive-but-testable"
    else:
        stress_class = "unrealistic"

    leakage = 0.0
    if case.role == "control":
        leakage = max(
            control_leakage(
                safe_float(pre.get("spectral_purity_150mhz")),
                safe_float(pre.get("target_band_coherent_growth")),
                bridge_ratio,
                safe_float(pre.get("phase_lock_target")),
            ),
            control_leakage(
                safe_float(post_metrics.get("spectral_purity_150mhz")),
                safe_float(post_metrics.get("target_band_coherent_growth")),
                bridge_ratio,
                safe_float(post_metrics.get("phase_lock_target")),
            ),
        )

    metrics = {
        "pre_extraction_150mhz_purity": pre.get("spectral_purity_150mhz", 0.0),
        "post_extraction_150mhz_purity": post_metrics.get("spectral_purity_150mhz", 0.0),
        "pre_extraction_target_growth": pre.get("target_band_coherent_growth", 0.0),
        "post_extraction_target_growth": post_metrics.get("target_band_coherent_growth", 0.0),
        "extraction_gain_at_150mhz": gain_150,
        "source_rejection_at_50mhz": db_rejection(pre_source_power, post_source_power),
        "generated_rejection_at_100mhz": db_rejection(pre_generated_power, post_generated_power),
        "filter_selectivity_score": filter_selectivity,
        "bridge_before_filter_score": pre_bridge_proxy,
        "bridge_after_filter_score": post_bridge_proxy,
        "internal_100mhz_growth": math.sqrt(max(pre_generated_power, EPS)) / max(math.sqrt(max(band_power(q1, t2, GENERATED_HZ, 8.0e6), EPS)), EPS),
        "internal_150mhz_growth": math.sqrt(max(pre_target_power, EPS)) / max(math.sqrt(max(band_power(q1, t2, TARGET_HZ, 8.0e6), EPS)), EPS),
        "phase_lock_target_pre_filter": pre.get("phase_lock_target", 0.0),
        "phase_lock_target_post_filter": post_metrics.get("phase_lock_target", 0.0),
        "phase_lock_generated": pre.get("phase_lock_generated", 0.0),
        "control_leakage_score": leakage,
        "varactor_only_leakage_score": leakage if "varactor" in case.probe_kind else 0.0,
        "magnetic_only_leakage_score": leakage if "magnetic" in case.probe_kind else 0.0,
        "generated_path_dependency_score": 0.0,
        "phase_mismatch_kill_score": 0.0,
        "target_velocity_dependency_score": 0.0,
        "component_stress_score": stress_score,
        "component_stress_class": stress_class,
        "behavioral_dependency_score": lockin.behavioral_dependency(case),
        "bridge_ratio_vs_direct_reference": bridge_ratio,
        "source_fft_peak_pre_hz": pre.get("source_fft_peak_hz", 0.0),
        "generated_fft_peak_pre_hz": pre.get("generated_fft_peak_hz", 0.0),
        "target_fft_peak_pre_hz": pre.get("target_fft_peak_hz", 0.0),
        "source_fft_power_pre": pre_source_power,
        "generated_fft_power_pre": pre_generated_power,
        "target_fft_power_pre": pre_target_power,
        "source_fft_peak_post_hz": post_metrics.get("source_fft_peak_hz", 0.0),
        "generated_fft_peak_post_hz": post_metrics.get("generated_fft_peak_hz", 0.0),
        "target_fft_peak_post_hz": post_metrics.get("target_fft_peak_hz", 0.0),
        "source_fft_power_post": post_source_power,
        "generated_fft_power_post": post_generated_power,
        "target_fft_power_post": post_target_power,
        "generated_envelope_cv_pre": pre.get("generated_envelope_cv", 0.0),
        "target_envelope_cv_pre": pre.get("target_envelope_cv", 0.0),
        "generated_envelope_cv_post": post_metrics.get("generated_envelope_cv", 0.0),
        "target_envelope_cv_post": post_metrics.get("target_envelope_cv", 0.0),
        "max_phase_jump_pre": pre.get("max_phase_jump", 0.0),
        "max_phase_jump_post": post_metrics.get("max_phase_jump", 0.0),
        "near_slip_count_pre": pre.get("near_slip_count", 0),
        "near_slip_count_post": post_metrics.get("near_slip_count", 0),
        "source_band_envelope_along_line_json": json.dumps(source_amps, sort_keys=True),
        "generated_band_envelope_along_line_json": json.dumps(generated_amps, sort_keys=True),
        "target_band_envelope_along_line_json": json.dumps(target_amps, sort_keys=True),
        "local_50plus50_to_100_growth_estimate": generated_amps["raw"] / max(source_amps["raw"] ** 2, EPS),
        "local_50plus100_to_150_growth_estimate": target_amps["raw"] / max(source_amps["raw"] * generated_amps["raw"], EPS),
        "peak_voltage_v": peak_voltage,
        "varactor_peak_current_a": peak_varactor_current,
        "reverse_bias_margin_v": reverse_bias_margin,
        "per_cell_inductance_h": vals["l_cell_h"],
        "per_cell_total_capacitance_f": vals["c_cell_f"],
        "varactor_cjo_f": vals["cjo_f"],
    }
    if case.role == "ceiling_reference":
        metrics["promotion_category"] = "ceiling_reference_not_discovery"
    elif case.role == "control":
        metrics["promotion_category"] = "control_dead" if leakage < 0.15 else "reject_due_to_control_leakage"
    else:
        metrics["promotion_category"] = "forensics_probe_pending_aggregate"
    return metrics


def summarize_export(
    export: ForensicsExport,
    run_requested: bool,
    ngspice_available: bool,
    ngspice_path: str | None,
    result: design.RunResult,
    metrics: Dict[str, object] | None,
) -> Dict[str, object]:
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_412_electrical_control_forensics",
        "case_id": case.case_id,
        "name": case.name,
        "prior_case_id": case.prior_case_id,
        "probe_kind": case.probe_kind,
        "family": case.family,
        "role": case.role,
        "forensics_role": case.forensics_role,
        "netlist_file": export.netlist_path.name,
        "csv_file": export.csv_path.name if result.success else "",
        "execution_status": result.execution_status,
        "convergence_failure_reason": "" if result.success else result.reason,
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "ngspice_path": ngspice_path or "",
        "source_only_drive": str(case.source_only_drive),
        "direct_100mhz_drive_present": str(case.direct_100_drive_present),
        "direct_150mhz_drive_present": str(case.direct_150_drive_present),
        "target_frequency_injection_present": str(case.target_frequency_injection_present),
        "hidden_behavioral_target_source_present": "False",
        "generated_path_suppressed": str(case.generated_path_suppressed),
        "target_velocity_detuned_probe": str(case.target_velocity_detuned_probe),
        "phase_mismatched_probe": str(case.phase_mismatched_probe),
        "extraction_removed_probe": str(case.extraction_removed_probe),
        "cell_count": case.cell_count,
        "z0_target_ohm": case.z0_ohm,
        "total_length_m": case.total_length_m,
        "source_frequency_hz": SOURCE_HZ,
        "generated_frequency_hz": GENERATED_HZ,
        "target_frequency_hz": TARGET_HZ,
        "source_amplitude_v": case.source_amplitude_v,
        "bias_v": case.bias_v,
        "nonlinear_fraction": case.nonlinear_fraction,
        "magnetic_strength": case.magnetic_strength,
        "extraction_topology": case.extraction_topology,
        "extraction_q": case.extraction_q,
        "post_filter_strength": case.post_filter_strength,
        "output_load_ohm": case.output_load_ohm,
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
    elif result.execution_status in {"failed_to_converge", "parser_failed"}:
        row["promotion_category"] = "reject_due_to_convergence_or_parser_failure"
    return row


def get_row(rows: List[Dict[str, object]], case_id: str) -> Dict[str, object]:
    return next((row for row in rows if row.get("case_id") == case_id), {})


def successful(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    return [row for row in rows if row.get("execution_status") == "ran_successfully"]


def apply_dependency_scores(rows: List[Dict[str, object]]) -> Dict[str, float]:
    hybrid_rows = successful([get_row(rows, cid) for cid in ("f001", "f002", "f003", "f007")])
    best_hybrid = max(hybrid_rows, key=lambda row: safe_float(row.get("target_fft_power_pre")), default={})
    best_power = safe_float(best_hybrid.get("target_fft_power_pre"))

    suppressed = get_row(rows, "f008")
    detuned = get_row(rows, "f009")
    mismatched = get_row(rows, "f010")
    scores = {
        "generated_path_dependency_score": max(0.0, 1.0 - safe_float(suppressed.get("target_fft_power_pre")) / max(best_power, EPS)),
        "target_velocity_dependency_score": max(0.0, 1.0 - safe_float(detuned.get("target_fft_power_pre")) / max(best_power, EPS)),
        "phase_mismatch_kill_score": max(0.0, 1.0 - safe_float(mismatched.get("target_fft_power_pre")) / max(best_power, EPS)),
    }
    for row in rows:
        if row.get("case_id") == "f008":
            row["generated_path_dependency_score"] = scores["generated_path_dependency_score"]
        if row.get("case_id") == "f009":
            row["target_velocity_dependency_score"] = scores["target_velocity_dependency_score"]
        if row.get("case_id") == "f010":
            row["phase_mismatch_kill_score"] = scores["phase_mismatch_kill_score"]
    return scores


def aggregate_summary(rows: List[Dict[str, object]], run_requested: bool, ngspice_available: bool) -> Dict[str, object]:
    data = [row for row in rows if row.get("row_type") == "spice_412_electrical_control_forensics"]
    dependencies = apply_dependency_scores(data)
    ran = successful(data)
    discovery = [row for row in data if row.get("role") == "discovery"]
    controls = [row for row in data if row.get("role") == "control"]
    hybrid_rows = successful([get_row(data, cid) for cid in ("f001", "f002", "f003")])
    best_hybrid_pre = max(hybrid_rows, key=lambda row: safe_float(row.get("target_fft_power_pre")), default={})
    best_hybrid_post = max(hybrid_rows, key=lambda row: safe_float(row.get("post_extraction_150mhz_purity")), default={})
    pure_varactor = get_row(data, "f004")
    pure_varactor_no_ext = get_row(data, "f005")
    pure_magnetic = get_row(data, "f006")
    hybrid_no_ext = get_row(data, "f007")
    linear = get_row(data, "f011")
    max_control_leak = max((safe_float(row.get("control_leakage_score")) for row in controls), default=0.0)
    controls_dead_pre = all(
        safe_float(row.get("pre_extraction_150mhz_purity")) < 0.20
        or safe_float(row.get("pre_extraction_target_growth")) <= 1.05
        for row in controls
        if row.get("execution_status") == "ran_successfully"
    )
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls if row.get("execution_status") == "ran_successfully")
    hybrid_pre_materially_above_pure = (
        safe_float(best_hybrid_pre.get("target_fft_power_pre")) > 1.5 * safe_float(pure_varactor.get("target_fft_power_pre"))
        and safe_float(best_hybrid_pre.get("pre_extraction_150mhz_purity")) > 1.2 * safe_float(pure_varactor.get("pre_extraction_150mhz_purity"))
    )
    pure_varactor_post_beats_hybrid = safe_float(pure_varactor.get("post_extraction_150mhz_purity")) >= safe_float(best_hybrid_post.get("post_extraction_150mhz_purity"))
    extraction_dominates = (
        safe_float(best_hybrid_post.get("post_extraction_150mhz_purity")) > 3.0 * max(safe_float(best_hybrid_post.get("pre_extraction_150mhz_purity")), EPS)
        or safe_float(best_hybrid_post.get("filter_selectivity_score")) > 10.0
    )
    generated_suppression_kills = dependencies["generated_path_dependency_score"] > 0.60
    phase_mismatch_kills = dependencies["phase_mismatch_kill_score"] > 0.60
    target_velocity_kills = dependencies["target_velocity_dependency_score"] > 0.60
    stress_ok = str(best_hybrid_pre.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}
    real_signal = bool(
        hybrid_pre_materially_above_pure
        and generated_suppression_kills
        and phase_mismatch_kills
        and not extraction_dominates
        and controls_dead_pre
        and stress_ok
    )
    artifact_likely = bool(
        pure_varactor_post_beats_hybrid
        or extraction_dominates
        or not hybrid_pre_materially_above_pure
        or not generated_suppression_kills
        or not phase_mismatch_kills
        or not controls_dead
    )
    for row in discovery:
        if row.get("execution_status") == "ran_successfully":
            row["promotion_category"] = "electrical_bridge_real_signal" if real_signal else "electrical_filter_artifact_likely"

    if real_signal:
        recommendation = "continue electrical work with component refinement and PCB/transmission-line modeling"
    elif artifact_likely:
        recommendation = "pause this electrical topology behind the acoustic branch while testing a different electrical topology"
    else:
        recommendation = "run a narrower repeat with independent extraction readout"

    statuses = ";".join(sorted(set(str(row.get("execution_status")) for row in data)))
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "aggregate",
        "valid_spice_netlists_generated": str(all((OUT_DIR / str(row.get("netlist_file"))).exists() for row in data)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": statuses,
        "rows_total": len(data),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "ran_successfully_count": len(ran),
        "best_hybrid_pre_case": best_hybrid_pre.get("case_id", ""),
        "best_hybrid_pre_purity": best_hybrid_pre.get("pre_extraction_150mhz_purity", ""),
        "best_hybrid_pre_target_power": best_hybrid_pre.get("target_fft_power_pre", ""),
        "best_hybrid_post_case": best_hybrid_post.get("case_id", ""),
        "best_hybrid_post_purity": best_hybrid_post.get("post_extraction_150mhz_purity", ""),
        "pure_varactor_pre_purity": pure_varactor.get("pre_extraction_150mhz_purity", ""),
        "pure_varactor_post_purity": pure_varactor.get("post_extraction_150mhz_purity", ""),
        "pure_varactor_no_extraction_pre_purity": pure_varactor_no_ext.get("pre_extraction_150mhz_purity", ""),
        "pure_magnetic_pre_purity": pure_magnetic.get("pre_extraction_150mhz_purity", ""),
        "pure_magnetic_post_purity": pure_magnetic.get("post_extraction_150mhz_purity", ""),
        "hybrid_no_extraction_pre_purity": hybrid_no_ext.get("pre_extraction_150mhz_purity", ""),
        "linear_pre_purity": linear.get("pre_extraction_150mhz_purity", ""),
        "linear_post_purity": linear.get("post_extraction_150mhz_purity", ""),
        "hybrid_pre_materially_above_pure_varactor": str(hybrid_pre_materially_above_pure),
        "pure_varactor_post_beats_hybrid": str(pure_varactor_post_beats_hybrid),
        "generated_path_dependency_score": dependencies["generated_path_dependency_score"],
        "phase_mismatch_kill_score": dependencies["phase_mismatch_kill_score"],
        "target_velocity_dependency_score": dependencies["target_velocity_dependency_score"],
        "generated_suppression_kills_150mhz": str(generated_suppression_kills),
        "phase_mismatch_kills_150mhz": str(phase_mismatch_kills),
        "target_velocity_detuning_kills_150mhz": str(target_velocity_kills),
        "extraction_dominates_apparent_purity": str(extraction_dominates),
        "controls_dead_pre_extraction": str(controls_dead_pre),
        "controls_dead_overall": str(controls_dead),
        "max_control_leakage_score": max_control_leak,
        "electrical_bridge_real_signal": str(real_signal),
        "electrical_filter_artifact_likely": str(artifact_likely),
        "acoustic_branch_only_clean_physical_proof_route": str(not real_signal),
        "recommended_next_step": recommendation,
    }


def timeseries_rows(export: ForensicsExport, data: Dict[str, np.ndarray], stride: int = 24) -> List[Dict[str, object]]:
    d = uniform_resample(data, max_points=6000)
    rows: List[Dict[str, object]] = []
    for idx in range(0, len(d["time"]), stride):
        rows.append(
            {
                "row_type": "spice_412_electrical_control_forensics_timeseries",
                "case_id": export.case.case_id,
                "name": export.case.name,
                "probe_kind": export.case.probe_kind,
                "role": export.case.role,
                "time_s": float(d["time"][idx]),
                "v_in": float(d["v_in"][idx]),
                "v_q1": float(d["v_q1"][idx]),
                "v_mid": float(d["v_mid"][idx]),
                "v_q3": float(d["v_q3"][idx]),
                "v_raw_pre_extraction": float(d["v_raw"][idx]),
                "v_post_extraction": float(d["v_post"][idx]),
                "i_src": float(d["i_src"][idx]),
                "i_bias": float(d["i_bias"][idx]),
            }
        )
    return rows


def write_report(out_dir: Path, rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    data = [row for row in rows if row.get("row_type") == "spice_412_electrical_control_forensics"]
    lines = [
        "# SPICE 4->8->12 Electrical Control Forensics",
        "",
        "Strict probe pass to separate true pre-extraction 150 MHz bridge generation from tuned extraction/filter artifacts.",
        "",
        "## Direct Answers",
        "",
        (
            "1. Is the electrical 150 MHz signal real bridge generation or mostly extraction/filter artifact? "
            f"real_signal={aggregate.get('electrical_bridge_real_signal')}; "
            f"filter_artifact_likely={aggregate.get('electrical_filter_artifact_likely')}."
        ),
        (
            "2. Does hybrid produce more pre-extraction 150 MHz than pure varactor? "
            f"{aggregate.get('hybrid_pre_materially_above_pure_varactor')}; "
            f"best_hybrid_pre_purity={aggregate.get('best_hybrid_pre_purity')}; "
            f"pure_varactor_pre_purity={aggregate.get('pure_varactor_pre_purity')}."
        ),
        (
            "3. Does generated-path suppression kill 150 MHz? "
            f"{aggregate.get('generated_suppression_kills_150mhz')}; "
            f"dependency_score={aggregate.get('generated_path_dependency_score')}."
        ),
        (
            "4. Does phase mismatch kill 150 MHz? "
            f"{aggregate.get('phase_mismatch_kills_150mhz')}; "
            f"kill_score={aggregate.get('phase_mismatch_kill_score')}."
        ),
        (
            "5. Does extraction create apparent purity from weak broadband response? "
            f"{aggregate.get('extraction_dominates_apparent_purity')}; "
            f"pure_varactor_post_beats_hybrid={aggregate.get('pure_varactor_post_beats_hybrid')}."
        ),
        f"6. Should electrical work continue, pivot, or pause? {aggregate.get('recommended_next_step')}.",
        (
            "7. Is acoustic now the only clean physical proof route? "
            f"{aggregate.get('acoustic_branch_only_clean_physical_proof_route')} under this electrical topology."
        ),
        "",
        "## Aggregate",
        "",
        f"- Rows: total={aggregate.get('rows_total')}, successful={aggregate.get('ran_successfully_count')}, statuses={aggregate.get('execution_statuses')}.",
        f"- Controls: pre_extraction_dead={aggregate.get('controls_dead_pre_extraction')}, overall_dead={aggregate.get('controls_dead_overall')}, max_leakage={aggregate.get('max_control_leakage_score')}.",
        f"- Best hybrid pre case: {aggregate.get('best_hybrid_pre_case')} purity={aggregate.get('best_hybrid_pre_purity')} target_power={aggregate.get('best_hybrid_pre_target_power')}.",
        f"- Best hybrid post case: {aggregate.get('best_hybrid_post_case')} purity={aggregate.get('best_hybrid_post_purity')}.",
        "",
        "## Rows",
        "",
    ]
    for row in data:
        lines.append(
            "- {case_id} {probe}: role={role}, status={status}, category={cat}, "
            "pre_purity={pre_purity}, post_purity={post_purity}, pre_growth={pre_growth}, "
            "post_growth={post_growth}, filter_selectivity={selectivity}, bridge={bridge}, "
            "control_leak={leak}, stress={stress}.".format(
                case_id=row.get("case_id"),
                probe=row.get("probe_kind"),
                role=row.get("role"),
                status=row.get("execution_status"),
                cat=row.get("promotion_category", ""),
                pre_purity=row.get("pre_extraction_150mhz_purity", ""),
                post_purity=row.get("post_extraction_150mhz_purity", ""),
                pre_growth=row.get("pre_extraction_target_growth", ""),
                post_growth=row.get("post_extraction_target_growth", ""),
                selectivity=row.get("filter_selectivity_score", ""),
                bridge=row.get("bridge_ratio_vs_direct_reference", ""),
                leak=row.get("control_leakage_score", ""),
                stress=row.get("component_stress_class", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Probe Notes",
            "",
            "- Every discovery/control row except the separated direct reference drives only the 50 MHz source.",
            "- No discovery/control row uses direct 100 MHz drive, direct 150 MHz drive, target-frequency injection, or hidden target-band behavioral source.",
            "- Each netlist writes v(n0), quarter-line, mid-line, three-quarter-line, raw line output, post-extraction output, source current, and bias current.",
            "- The direct 50+100 MHz row is a ceiling denominator only and is excluded from discovery conclusions.",
        ]
    )
    (out_dir / "README_SPICE_412_ELECTRICAL_CONTROL_FORENSICS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def sanitize(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Run electrical 4->8->12 control-forensics SPICE probes.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per netlist in seconds.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    exports = export_netlists(out_dir)
    ngspice_path = design.resolve_ngspice_path(args.ngspice_path or None)
    ngspice_available = ngspice_path is not None

    run_results: Dict[str, design.RunResult] = {}
    parsed: Dict[str, Dict[str, np.ndarray]] = {}
    if args.run and not ngspice_available:
        for export in exports:
            run_results[export.case.case_id] = design.RunResult("skipped_no_ngspice", False, "ngspice not found")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed[export.case.case_id] = read_forensics_transient(export.csv_path)
                except Exception as exc:
                    result = design.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            run_results[export.case.case_id] = result
    else:
        for export in exports:
            run_results[export.case.case_id] = design.RunResult("exported", False, "export only; use --run")

    reference_power: float | None = None
    reference = next((export for export in exports if export.case.role == "ceiling_reference"), None)
    if reference and reference.case.case_id in parsed:
        ref_metrics = measure_case(reference, parsed[reference.case.case_id], None)
        reference_power = safe_float(ref_metrics.get("target_coherent_power"), safe_float(ref_metrics.get("target_fft_power_post")))

    summary_rows: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for export in exports:
        result = run_results[export.case.case_id]
        metrics: Dict[str, object] | None = None
        if result.success and export.case.case_id in parsed:
            metrics = measure_case(export, parsed[export.case.case_id], reference_power)
            if export.case.role in {"discovery", "control", "ceiling_reference"}:
                timeseries.extend(timeseries_rows(export, parsed[export.case.case_id]))
        summary_rows.append(summarize_export(export, args.run, ngspice_available, ngspice_path, result, metrics))

    aggregate = aggregate_summary(summary_rows, args.run, ngspice_available)
    all_rows = [aggregate] + summary_rows
    write_csv(out_dir / "spice_412_electrical_control_forensics_summary.csv", all_rows)
    if timeseries:
        write_csv(out_dir / "spice_412_electrical_control_forensics_timeseries.csv", timeseries)
    elif (out_dir / "spice_412_electrical_control_forensics_timeseries.csv").exists():
        (out_dir / "spice_412_electrical_control_forensics_timeseries.csv").unlink()
    (out_dir / "spice_412_electrical_control_forensics_summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": aggregate,
                    "rows": all_rows,
                    "netlists": [
                        {
                            **asdict(export.case),
                            "netlist_path": str(export.netlist_path),
                            "csv_path": str(export.csv_path),
                        }
                        for export in exports
                    ],
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(out_dir, all_rows, aggregate)
    print(
        json.dumps(
            sanitize(
                {
                    "rows_total": aggregate.get("rows_total"),
                    "ran_successfully_count": aggregate.get("ran_successfully_count"),
                    "electrical_bridge_real_signal": aggregate.get("electrical_bridge_real_signal"),
                    "electrical_filter_artifact_likely": aggregate.get("electrical_filter_artifact_likely"),
                    "recommended_next_step": aggregate.get("recommended_next_step"),
                    "summary": str(out_dir / "spice_412_electrical_control_forensics_summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
