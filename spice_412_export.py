#!/usr/bin/env python3
"""Export the physical 4->8->12 LC bridge to ngspice netlists.

The generated circuits are intended as a first circuit-level validation track,
not as final hardware designs.  They preserve the discovery rule that only the
source resonator is externally driven.  The direct 4+8 circuit is emitted only
as a separated ceiling/reference denominator.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

import physical_412_lc_bridge as phys


OUT_DIR = Path("runs") / "spice_412_bridge"
REFERENCE_SCALE = "low-RF-scale"
NETLIST_SPECS = (
    ("audio_412_bridge", "audio-scale", phys.CANDIDATE, "discovery"),
    ("low_rf_412_bridge", "low-RF-scale", phys.CANDIDATE, "discovery"),
    ("normalized_412_bridge", "arbitrary-normalized-scale", phys.CANDIDATE, "discovery"),
    ("reference_direct_4plus8", REFERENCE_SCALE, phys.DIRECT_REFERENCE, "ceiling_reference"),
)
PYTHON_BASELINE = {
    "phase_lock_target": 0.992108,
    "bridge_ratio": 1.606971,
    "spectral_purity_target": 0.922789,
    "generated_envelope_cv": 0.134693,
    "max_phase_jump": 0.971944,
    "near_slip_count": 0.0,
    "energy_budget_error": 0.0000510,
}


@dataclass(frozen=True)
class SpiceExport:
    circuit_name: str
    scale_name: str
    role: str
    netlist_path: Path
    csv_path: Path
    raw_path: Path
    source_frequency_hz: float
    generated_frequency_hz: float
    target_frequency_hz: float
    nominal_generated_frequency_hz: float
    nominal_target_frequency_hz: float
    tstop_s: float
    tstep_s: float
    direct_8_drive: bool
    direct_12_drive: bool
    target_frequency_injection: bool


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


def spice_num(value: float) -> str:
    if value == 0:
        return "0"
    return f"{value:.12g}"


def direct_drive_flags(config: phys.BridgeConfig) -> Dict[str, bool]:
    direct_8 = any(abs(freq - config.target_6) < 1e-9 and mode == 1 for freq, mode in zip(config.drive_freqs, config.drive_modes))
    direct_12 = any(abs(freq - config.target_9) < 1e-9 and mode == 2 for freq, mode in zip(config.drive_freqs, config.drive_modes))
    target_injection = any(abs(freq - config.target_9) < 1e-9 for freq in config.drive_freqs)
    return {
        "direct_8_drive": direct_8,
        "direct_12_drive": direct_12,
        "target_frequency_injection": target_injection,
    }


def physical_timing(scale_name: str) -> Tuple[float, float, float, float]:
    preset = phys.SCALE_PRESETS[scale_name]
    scale = phys.scale_factor(preset)
    tstop = phys.BASE_TMAX / scale
    source_hz = preset.source_frequency_hz
    tstep = 1.0 / (source_hz * 64.0)
    drive_until = 0.74 * tstop
    ramp = min(10.0 / scale, 0.20 * drive_until)
    return tstop, tstep, drive_until, max(ramp, tstep)


def nonlinear_mix_coefficients(scale_name: str, config: phys.BridgeConfig) -> Dict[str, float]:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    scale = phys.scale_factor(preset)
    gamma_a, gamma_b = phys.bridge_route_strengths(config)
    c = [p.capacitance_f for p in params]
    s_v = [p.voltage_scale_v for p in params]

    def coeff(out_idx: int, in_a: int, in_b: int, gamma: float) -> float:
        return c[out_idx] * s_v[out_idx] * (scale ** 2) * gamma / max(s_v[in_a] * s_v[in_b], 1e-30)

    return {
        "mixa_01_to_1": coeff(0, 0, 1, gamma_a),
        "mixa_00_to_2": coeff(1, 0, 0, 0.5 * gamma_a),
        "mixb_12_to_1": coeff(0, 1, 2, gamma_b),
        "mixb_02_to_2": coeff(1, 0, 2, gamma_b),
        "mixb_01_to_3": coeff(2, 0, 1, gamma_b),
    }


def soft_limiter_params(scale_name: str, config: phys.BridgeConfig) -> Dict[str, float]:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    vscale = [p.voltage_scale_v for p in params]
    r = [p.resistance_ohm for p in params]
    gbase = 0.030 * config.spark_strength
    return {
        "gsoft12": gbase / max(math.sqrt(r[0] * r[1]), 1e-18),
        "gsoft23": gbase / max(math.sqrt(r[1] * r[2]), 1e-18),
        "vlim12": config.spark_threshold * math.sqrt(vscale[0] * vscale[1]),
        "vlim23": config.spark_threshold * math.sqrt(vscale[1] * vscale[2]),
    }


def drive_current_for_mode(scale_name: str, config: phys.BridgeConfig, mode_idx: int, drive_count: int) -> float:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    norm = math.sqrt(max(1, drive_count))
    return params[mode_idx].current_scale_a_per_model_velocity * config.drive_amp / norm


def netlist_text(circuit_name: str, scale_name: str, config: phys.BridgeConfig, role: str,
                 out_dir: Path) -> Tuple[str, SpiceExport]:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    coupling = phys.coupling_summary(config)
    mix = nonlinear_mix_coefficients(scale_name, config)
    limiter = soft_limiter_params(scale_name, config)
    flags = direct_drive_flags(config)
    tstop, tstep, drive_until, ramp = physical_timing(scale_name)
    hold_time = max(ramp, drive_until - ramp)
    netlist_path = out_dir / f"{circuit_name}.cir"
    csv_path = out_dir / f"{circuit_name}_tran.csv"
    raw_path = out_dir / f"{circuit_name}.raw"

    drive_count = max(1, len(config.drive_freqs))
    drive_lines: List[str] = []
    for drive_idx, (freq_ratio, mode_idx) in enumerate(zip(config.drive_freqs, config.drive_modes), start=1):
        node = f"n{mode_idx + 1}"
        drive_frequency = phys.BASE_HZ * freq_ratio * phys.scale_factor(preset)
        amp = drive_current_for_mode(scale_name, config, mode_idx, drive_count)
        role_note = "source-only discovery drive" if role == "discovery" else "direct reference drive"
        drive_lines.append(f"* {role_note}: mode {mode_idx + 1}, f={spice_num(drive_frequency)} Hz")
        drive_lines.append(f".param idrive{drive_idx}={spice_num(amp)}")
        drive_lines.append(f".param fdrive{drive_idx}={spice_num(drive_frequency)}")
        drive_lines.append(f"Bdrive{drive_idx} {node} 0 I={{-idrive{drive_idx}*V(env)*sin(2*pi*fdrive{drive_idx}*time)}}")

    lines = [
        f"* {circuit_name}: physical 4->8->12 nonlinear LC bridge",
        f"* scale={scale_name}; role={role}",
        "* Generated by spice_412_export.py.",
        "* Discovery rule: no direct generated/target drive and no target-frequency injection.",
        "* The direct 4+8 file is a separated ceiling/reference denominator only.",
        ".option method=gear reltol=1e-5 abstol=1e-12 vntol=1e-8 maxord=2",
        ".param pi=3.141592653589793",
        f".param tstop={spice_num(tstop)}",
        f".param tstep={spice_num(tstep)}",
        f".param drive_until={spice_num(drive_until)}",
        f".param drive_ramp={spice_num(ramp)}",
        "",
        "* Drive envelope: source ramps in, holds, then ramps out before the transient ends.",
        f"Venv env 0 PWL(0 0 {spice_num(ramp)} 1 {spice_num(hold_time)} 1 {spice_num(drive_until)} 0 {spice_num(tstop)} 0)",
        "",
        "* Three lossy LC resonators. R is the inductor-branch loss selected from Q=omega*L/R.",
    ]
    for idx, p_lc in enumerate(params, start=1):
        lines.extend([
            f".param c{idx}={spice_num(p_lc.capacitance_f)}",
            f".param l{idx}={spice_num(p_lc.inductance_h)}",
            f".param r{idx}={spice_num(p_lc.resistance_ohm)}",
            f"C{idx} n{idx} 0 {{c{idx}}}",
            f"R{idx} n{idx} n{idx}l {{r{idx}}}",
            f"L{idx} n{idx}l 0 {{l{idx}}} IC=0",
        ])
    lines.extend([
        "",
        "* Weak linear coupling, exported as mutual inductive coupling between the LC tanks.",
        f"K12 L1 L2 {spice_num(float(coupling['linear_k01_fraction_of_omega_product']))}",
        f"K23 L2 L3 {spice_num(float(coupling['linear_k12_fraction_of_omega_product']))}",
        "",
        "* Varactor-like nonlinear capacitance: Ceff ~= C0*(1 + beta*V^2).",
    ])
    for idx, p_lc in enumerate(params, start=1):
        lines.append(f".param beta{idx}={spice_num(p_lc.varactor_beta_per_v2)}")
        lines.append(f"Bvar{idx} n{idx} 0 I={{c{idx}*beta{idx}*V(n{idx})*V(n{idx})*ddt(V(n{idx}))}}")
    lines.extend([
        "",
        "* Behavioral nonlinear mixing terms, scaled from the validated normalized LC model.",
        f".param mixa_01_to_1={spice_num(mix['mixa_01_to_1'])}",
        f".param mixa_00_to_2={spice_num(mix['mixa_00_to_2'])}",
        f".param mixb_12_to_1={spice_num(mix['mixb_12_to_1'])}",
        f".param mixb_02_to_2={spice_num(mix['mixb_02_to_2'])}",
        f".param mixb_01_to_3={spice_num(mix['mixb_01_to_3'])}",
        "Bmix1 n1 0 I={-(mixa_01_to_1*V(n1)*V(n2) + mixb_12_to_1*V(n2)*V(n3))}",
        "Bmix2 n2 0 I={-(mixa_00_to_2*V(n1)*V(n1) + mixb_02_to_2*V(n1)*V(n3))}",
        "Bmix3 n3 0 I={-(mixb_01_to_3*V(n1)*V(n2))}",
        "",
        "* Passive soft limiter / loss proxy. Current follows voltage drop, so it dissipates.",
        f".param gsoft12={spice_num(limiter['gsoft12'])}",
        f".param gsoft23={spice_num(limiter['gsoft23'])}",
        f".param vlim12={spice_num(limiter['vlim12'])}",
        f".param vlim23={spice_num(limiter['vlim23'])}",
        "Bsoft12 n1 n2 I={gsoft12*V(n1,n2)*0.5*(1+tanh((abs(V(n1,n2))-vlim12)/(0.3*vlim12+1e-30)))}",
        "Bsoft23 n2 n3 I={gsoft23*V(n2,n3)*0.5*(1+tanh((abs(V(n2,n3))-vlim23)/(0.3*vlim23+1e-30)))}",
        "",
        "* External drives.",
        *drive_lines,
        "",
        ".ic V(n1)=0 V(n2)=0 V(n3)=0",
        f".tran {{tstep}} {{tstop}} 0 {{tstep}} uic",
        ".control",
        "set noaskquit",
        "set wr_singlescale",
        "set wr_vecnames",
        "run",
        f"wrdata {csv_path.name} time v(n1) v(n2) v(n3) i(L1) i(L2) i(L3)",
        f"write {raw_path.name} v(n1) v(n2) v(n3) i(L1) i(L2) i(L3)",
        "quit",
        ".endc",
        ".end",
        "",
    ])
    export = SpiceExport(
        circuit_name=circuit_name,
        scale_name=scale_name,
        role=role,
        netlist_path=netlist_path,
        csv_path=csv_path,
        raw_path=raw_path,
        source_frequency_hz=params[0].frequency_hz,
        generated_frequency_hz=params[1].frequency_hz,
        target_frequency_hz=params[2].frequency_hz,
        nominal_generated_frequency_hz=2.0 * params[0].frequency_hz,
        nominal_target_frequency_hz=3.0 * params[0].frequency_hz,
        tstop_s=tstop,
        tstep_s=tstep,
        direct_8_drive=flags["direct_8_drive"],
        direct_12_drive=flags["direct_12_drive"],
        target_frequency_injection=flags["target_frequency_injection"],
    )
    return "\n".join(lines), export


def export_netlists(out_dir: Path) -> List[SpiceExport]:
    exports: List[SpiceExport] = []
    for circuit_name, scale_name, config, role in NETLIST_SPECS:
        text, export = netlist_text(circuit_name, scale_name, config, role, out_dir)
        export.netlist_path.write_text(text, encoding="utf-8")
        exports.append(export)
    return exports


def run_ngspice(export: SpiceExport, ngspice_path: str, timeout_s: int) -> Tuple[bool, str]:
    cmd = [ngspice_path, "-b", export.netlist_path.name]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(export.netlist_path.parent),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - depends on local ngspice install.
        return False, f"{type(exc).__name__}: {exc}"
    log_path = export.netlist_path.with_suffix(".log")
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
    return proc.returncode == 0 and export.csv_path.exists(), f"returncode={proc.returncode}; log={log_path.name}"


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def read_ngspice_csv(path: Path) -> Dict[str, np.ndarray]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No data in {path}")
    first_tokens = lines[0].replace(",", " ").split()
    first_numeric = [try_float(tok) for tok in first_tokens]
    has_header = any(value is None for value in first_numeric)
    if has_header:
        names = [name.strip().lower() for name in first_tokens]
        data_lines = lines[1:]
    else:
        names = ["time", "v_n1", "v_n2", "v_n3", "i_l1", "i_l2", "i_l3"]
        data_lines = lines
    rows: List[List[float]] = []
    for line in data_lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(v) for v in values if v is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"No numeric rows in {path}")
    arr = np.asarray(rows, dtype=float)
    if arr.shape[1] > len(names):
        arr = arr[:, :len(names)]
    if arr.shape[1] < 4:
        raise ValueError(f"Expected at least time and three voltages in {path}, got {arr.shape[1]} columns")
    normalized = {
        "time": arr[:, 0],
        "v1": arr[:, 1],
        "v2": arr[:, 2],
        "v3": arr[:, 3],
    }
    if arr.shape[1] >= 7:
        normalized["i1"] = arr[:, 4]
        normalized["i2"] = arr[:, 5]
        normalized["i3"] = arr[:, 6]
    return normalized


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


def coalesced_indices(indices: np.ndarray, min_separation: int = 2) -> List[int]:
    events: List[int] = []
    last = -1000000
    for raw_idx in indices:
        idx = int(raw_idx)
        if idx - last >= min_separation:
            events.append(idx)
            last = idx
        elif events and idx > events[-1]:
            events[-1] = idx
            last = idx
    return events


def envelope_cv(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    mean_abs = float(np.mean(np.abs(values)))
    if mean_abs <= 1e-18:
        return 0.0
    return float(np.std(np.abs(values)) / mean_abs)


def spice_metrics(export: SpiceExport, data: Dict[str, np.ndarray],
                  reference_data: Dict[str, np.ndarray] | None = None) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    t = data["time"]
    v1 = data["v1"]
    v2 = data["v2"]
    v3 = data["v3"]
    if len(t) < 32:
        return {"spice_metric_error": "not_enough_samples"}, []
    drive_until = 0.74 * export.tstop_s
    mask = (t >= 0.35 * drive_until) & (t < drive_until)
    if int(np.sum(mask)) < 32:
        mask = t >= 0.45 * float(t[-1])
    tm = t[mask]
    if len(tm) < 32:
        return {"spice_metric_error": "not_enough_window_samples"}, []
    sample_dt = float(np.median(np.diff(t))) if len(t) > 1 else export.tstep_s
    window = max(24, int((6.0 / phys.scale_factor(phys.SCALE_PRESETS[export.scale_name])) / max(sample_dt, 1e-18)))
    window = min(window, max(24, len(tm) // 2))
    step = max(4, window // 5)

    mids, z1 = sliding_complex(v1[mask], tm, export.source_frequency_hz, window, step)
    _, z2 = sliding_complex(v2[mask], tm, export.nominal_generated_frequency_hz, window, step)
    _, z3 = sliding_complex(v3[mask], tm, export.nominal_target_frequency_hz, window, step)
    min_len = min(len(z1), len(z2), len(z3))
    if min_len == 0:
        return {"spice_metric_error": "no_sliding_windows"}, []
    phase_error = np.unwrap(np.angle(z1[:min_len]) + np.angle(z2[:min_len]) - np.angle(z3[:min_len]))
    wrapped = (phase_error + np.pi) % (2.0 * np.pi) - np.pi
    lock = float(abs(np.mean(np.exp(1j * wrapped))))
    phase_step = np.abs(np.diff(phase_error)) if len(phase_error) >= 2 else np.asarray([])
    near_slips = coalesced_indices(np.where(phase_step > 1.0)[0] + 1)
    target_amp = complex_projection(v3[mask], tm, export.nominal_target_frequency_hz)
    generated_amp = complex_projection(v2[mask], tm, export.nominal_generated_frequency_hz)
    target_power = 0.5 * abs(target_amp) ** 2
    purity = float(min(1.0, target_power / (float(np.mean(v3[mask] ** 2)) + 1e-18)))
    bridge_ratio = float("nan")
    if reference_data is not None:
        rt = reference_data["time"]
        rv3 = reference_data["v3"]
        rmask = (rt >= 0.35 * drive_until) & (rt < drive_until)
        if int(np.sum(rmask)) >= 32:
            ref_amp = complex_projection(rv3[rmask], rt[rmask], export.nominal_target_frequency_hz)
            ref_power = 0.5 * abs(ref_amp) ** 2
            bridge_ratio = float(target_power / max(ref_power, 1e-30))
    rows: List[Dict[str, float | str]] = []
    for idx in range(min_len):
        rows.append({
            "row_type": "spice_phase_window",
            "circuit": export.circuit_name,
            "scale_preset": export.scale_name,
            "time_s": float(mids[idx]),
            "phase_error_target": float(wrapped[idx]),
            "unwrapped_phase_error_target": float(phase_error[idx]),
            "generated_envelope": float(abs(z2[idx])),
            "target_envelope": float(abs(z3[idx])),
        })
    return {
        "spice_phase_lock_target": lock,
        "spice_bridge_ratio": bridge_ratio,
        "spice_spectral_purity_target": purity,
        "spice_generated_envelope_cv": envelope_cv(z2[:min_len]),
        "spice_target_envelope_cv": envelope_cv(z3[:min_len]),
        "spice_max_phase_jump": float(np.max(phase_step)) if len(phase_step) else 0.0,
        "spice_near_slip_count": float(len(near_slips)),
        "spice_target_rms_v": float(np.sqrt(np.mean(v3[mask] ** 2))),
        "spice_generated_rms_v": float(np.sqrt(np.mean(v2[mask] ** 2))),
        "spice_target_projection_power": float(target_power),
    }, rows


def summarize_export(export: SpiceExport, ngspice_available: bool, ngspice_path: str | None,
                     run_ok: bool, run_message: str, metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    preset = phys.SCALE_PRESETS[export.scale_name]
    params = phys.build_lc_params(phys.DIRECT_REFERENCE if export.role == "ceiling_reference" else phys.CANDIDATE, preset)
    coupling = phys.coupling_summary(phys.CANDIDATE)
    row: Dict[str, float | str] = {
        "row_type": "spice_export",
        "circuit": export.circuit_name,
        "scale_preset": export.scale_name,
        "role": export.role,
        "netlist_path": str(export.netlist_path),
        "csv_path": str(export.csv_path) if run_ok else "",
        "raw_path": str(export.raw_path) if run_ok else "",
        "valid_spice_netlist_generated": str(export.netlist_path.exists()),
        "ngspice_available": str(ngspice_available),
        "ngspice_path": ngspice_path or "",
        "ngspice_run_succeeded": str(run_ok),
        "ngspice_run_message": run_message,
        "source_frequency_hz": export.source_frequency_hz,
        "generated_frequency_hz": export.generated_frequency_hz,
        "target_frequency_hz": export.target_frequency_hz,
        "nominal_generated_frequency_hz": export.nominal_generated_frequency_hz,
        "nominal_target_frequency_hz": export.nominal_target_frequency_hz,
        "tstop_s": export.tstop_s,
        "tstep_s": export.tstep_s,
        "direct_8_drive_present": str(export.direct_8_drive),
        "direct_12_drive_present": str(export.direct_12_drive),
        "target_frequency_injection_present": str(export.target_frequency_injection),
        "L1_h": params[0].inductance_h,
        "C1_f": params[0].capacitance_f,
        "R1_ohm": params[0].resistance_ohm,
        "Q1": params[0].q_factor,
        "L2_h": params[1].inductance_h,
        "C2_f": params[1].capacitance_f,
        "R2_ohm": params[1].resistance_ohm,
        "Q2": params[1].q_factor,
        "L3_h": params[2].inductance_h,
        "C3_f": params[2].capacitance_f,
        "R3_ohm": params[2].resistance_ohm,
        "Q3": params[2].q_factor,
        "linear_coupling_k12": coupling["linear_k01_fraction_of_omega_product"],
        "linear_coupling_k23": coupling["linear_k12_fraction_of_omega_product"],
        "nonlinear_element_assessment": "aggressive behavioral varactor/mixing proxy; plausible as a validation model, not yet a component-level implementation",
        "recommended_next_step": "nonlinear component refinement, parameter sweep, then spatial phase-matching model",
    }
    if metrics:
        row.update(metrics)
        if all(key in metrics for key in ("spice_phase_lock_target", "spice_spectral_purity_target")):
            row["rough_python_match_lock"] = str(abs(float(metrics["spice_phase_lock_target"]) - PYTHON_BASELINE["phase_lock_target"]) < 0.15)
            row["rough_python_match_purity"] = str(abs(float(metrics["spice_spectral_purity_target"]) - PYTHON_BASELINE["spectral_purity_target"]) < 0.20)
            if not math.isnan(float(metrics.get("spice_bridge_ratio", float("nan")))):
                row["rough_python_match_bridge_ratio"] = str(abs(float(metrics["spice_bridge_ratio"]) - PYTHON_BASELINE["bridge_ratio"]) < 0.50)
    return row


def aggregate_summary(rows: List[Dict[str, float | str]], ngspice_available: bool) -> Dict[str, float | str]:
    exports = [r for r in rows if str(r.get("row_type")) == "spice_export"]
    discovery = [r for r in exports if str(r.get("role")) == "discovery"]
    ran = [r for r in discovery if str(r.get("ngspice_run_succeeded")) == "True"]
    return {
        "row_type": "aggregate",
        "valid_spice_netlists_generated": str(all(str(r["valid_spice_netlist_generated"]) == "True" for r in exports)),
        "ngspice_available": str(ngspice_available),
        "ngspice_runs_completed": str(bool(ran) and all(str(r["ngspice_run_succeeded"]) == "True" for r in ran)),
        "discovery_rows_source_only": str(all(str(r["direct_8_drive_present"]) == "False" and str(r["direct_12_drive_present"]) == "False" and str(r["target_frequency_injection_present"]) == "False" for r in discovery)),
        "reference_direct_4plus8_separated": str(any(str(r.get("role")) == "ceiling_reference" for r in exports)),
        "spice_target_build_up_observed": str(any(float(r.get("spice_target_rms_v", 0.0) or 0.0) > 0.0 for r in ran)) if ran else "not_run",
        "rough_python_match_available": str(bool(ran)) if ran else "not_run",
        "nonlinear_element_assessment": "aggressive behavioral varactor/mixing proxy; needs component-level refinement",
        "recommended_next_step": "Install/run ngspice if missing; then refine nonlinear components, sweep parameters, and add spatial phase-matching modeling",
    }


def write_report(out_dir: Path, summary_rows: List[Dict[str, float | str]], aggregate: Dict[str, float | str]) -> None:
    rows = [r for r in summary_rows if str(r.get("row_type")) == "spice_export"]
    lines = [
        "# SPICE 4->8->12 Bridge Export",
        "",
        "This track exports the physical 4->8->12 LC bridge into ngspice-compatible netlists. The discovery netlists drive only resonator 1. The direct 4+8 netlist is separated as a ceiling/reference denominator and is not a discovery row.",
        "",
        "## Direct Answers",
        f"1. Were valid SPICE netlists generated? {aggregate.get('valid_spice_netlists_generated')}.",
        f"2. Does ngspice run locally? {aggregate.get('ngspice_available')}; completed={aggregate.get('ngspice_runs_completed')}.",
        f"3. Does the SPICE transient preserve target build-up without direct 8/12 drive? {aggregate.get('spice_target_build_up_observed')}.",
        f"4. Does SPICE roughly match Python lock, purity, and bridge-ratio behavior? {aggregate.get('rough_python_match_available')} for local execution; see summary metrics when ngspice runs.",
        f"5. Is the nonlinear element physically plausible, aggressive, or unrealistic? {aggregate.get('nonlinear_element_assessment')}.",
        f"6. Next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Exported Netlists",
    ]
    for row in rows:
        lines.append(
            f"- {row['circuit']}: role={row['role']}, scale={row['scale_preset']}, "
            f"f=({float(row['source_frequency_hz']):.6g}, {float(row['generated_frequency_hz']):.6g}, {float(row['target_frequency_hz']):.6g}) Hz, "
            f"ngspice_run={row['ngspice_run_succeeded']}, netlist={Path(str(row['netlist_path'])).name}."
        )
        lines.append(
            f"  Drive flags: direct_8={row['direct_8_drive_present']}, direct_12={row['direct_12_drive_present']}, target_injection={row['target_frequency_injection_present']}."
        )
        if str(row.get("ngspice_run_succeeded")) == "True":
            lines.append(
                f"  SPICE metrics: lock={float(row.get('spice_phase_lock_target', 0.0)):.6g}, "
                f"bridge={float(row.get('spice_bridge_ratio', 0.0)):.6g}, purity={float(row.get('spice_spectral_purity_target', 0.0)):.6g}, "
                f"gen_cv={float(row.get('spice_generated_envelope_cv', 0.0)):.6g}, max_jump={float(row.get('spice_max_phase_jump', 0.0)):.6g}."
            )
        else:
            lines.append(f"  Execution note: {row['ngspice_run_message']}.")
    lines.extend([
        "",
        "## Circuit Notes",
        "",
        "- Each resonator is a capacitor in parallel with an inductor branch whose series resistance matches the physical Q.",
        "- Weak linear coupling is exported as mutual inductive coupling between adjacent resonators.",
        "- Varactor-like behavior is exported with behavioral current sources using `ddt(V(node))`.",
        "- Nonlinear mixing is exported as behavioral current injection scaled from the normalized Python LC model.",
        "- The soft limiter is a passive voltage-drop-dependent conductance between resonators.",
        "- These behavioral nonlinear elements are deliberately marked aggressive: they preserve the bridge mechanism for SPICE testing but are not yet a bill of materials.",
    ])
    (out_dir / "README_SPICE_412_EXPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and optionally run ngspice validation for the physical 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice if installed. By default the script also runs if ngspice is present unless --no-run is used.")
    parser.add_argument("--no-run", action="store_true", help="Only export netlists, even if ngspice is installed.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per ngspice netlist in seconds.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    exports = export_netlists(out_dir)
    ngspice_path = shutil.which("ngspice")
    ngspice_available = ngspice_path is not None
    should_run = ngspice_available and not args.no_run

    parsed_data: Dict[str, Dict[str, np.ndarray]] = {}
    run_results: Dict[str, Tuple[bool, str]] = {}
    if should_run:
        for export in exports:
            run_results[export.circuit_name] = run_ngspice(export, ngspice_path or "ngspice", args.timeout)
            if run_results[export.circuit_name][0]:
                try:
                    parsed_data[export.circuit_name] = read_ngspice_csv(export.csv_path)
                except Exception as exc:
                    run_results[export.circuit_name] = (False, f"parse_failed: {type(exc).__name__}: {exc}")
    else:
        reason = "ngspice not installed on PATH" if not ngspice_available else "run disabled by --no-run"
        for export in exports:
            run_results[export.circuit_name] = (False, reason)

    reference_data = parsed_data.get("reference_direct_4plus8")
    summary_rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    for export in exports:
        run_ok, run_message = run_results[export.circuit_name]
        metrics: Dict[str, float | str] | None = None
        phase_rows: List[Dict[str, float | str]] = []
        if run_ok and export.circuit_name in parsed_data:
            metrics, phase_rows = spice_metrics(export, parsed_data[export.circuit_name], reference_data)
            data = parsed_data[export.circuit_name]
            for idx in range(len(data["time"])):
                item: Dict[str, float | str] = {
                    "row_type": "spice_timeseries",
                    "circuit": export.circuit_name,
                    "scale_preset": export.scale_name,
                    "time_s": float(data["time"][idx]),
                    "v_source": float(data["v1"][idx]),
                    "v_generated": float(data["v2"][idx]),
                    "v_target": float(data["v3"][idx]),
                }
                if "i1" in data:
                    item.update({
                        "i_source": float(data["i1"][idx]),
                        "i_generated": float(data["i2"][idx]),
                        "i_target": float(data["i3"][idx]),
                    })
                timeseries_rows.append(item)
            timeseries_rows.extend(phase_rows)
        summary_rows.append(summarize_export(export, ngspice_available, ngspice_path, run_ok, run_message, metrics))

    aggregate = aggregate_summary(summary_rows, ngspice_available)
    all_summary_rows = [aggregate] + summary_rows
    write_csv(out_dir / "spice_412_summary.csv", all_summary_rows)
    if timeseries_rows:
        write_csv(out_dir / "spice_412_timeseries.csv", timeseries_rows)
    (out_dir / "spice_412_summary.json").write_text(json.dumps({
        "aggregate": aggregate,
        "rows": all_summary_rows,
        "python_lc_baseline": PYTHON_BASELINE,
        "netlists": [asdict(export) | {
            "netlist_path": str(export.netlist_path),
            "csv_path": str(export.csv_path),
            "raw_path": str(export.raw_path),
        } for export in exports],
    }, indent=2), encoding="utf-8")
    write_report(out_dir, all_summary_rows, aggregate)

    print(f"SPICE 4->8->12 export written to: {out_dir.resolve()}")
    print(f"valid_spice_netlists_generated={aggregate['valid_spice_netlists_generated']}")
    print(f"ngspice_available={aggregate['ngspice_available']}")
    print(f"ngspice_runs_completed={aggregate['ngspice_runs_completed']}")
    print(f"discovery_rows_source_only={aggregate['discovery_rows_source_only']}")


if __name__ == "__main__":
    main()
