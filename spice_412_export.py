#!/usr/bin/env python3
"""Export and optionally run ngspice validation for the 4->8->12 LC bridge.

The generated circuits are first-pass validation artifacts, not final hardware
designs.  Discovery netlists drive only the source resonator.  The direct 4+8
netlist is emitted only as a separated ceiling/reference denominator.
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
from typing import Dict, Iterable, List, Tuple

import numpy as np

import physical_412_lc_bridge as phys


OUT_DIR = Path("runs") / "spice_412_bridge"
REFERENCE_SCALE = "low-RF-scale"
DISCOVERY_SCALES = (
    ("audio_412_bridge", "audio-scale"),
    ("low_rf_412_bridge", "low-RF-scale"),
    ("normalized_412_bridge", "arbitrary-normalized-scale"),
)
REQUIRED_CANONICAL_FILES = (
    "audio_412_bridge.cir",
    "low_rf_412_bridge.cir",
    "normalized_412_bridge.cir",
    "reference_direct_4plus8.cir",
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
EXECUTION_STATUSES = (
    "exported",
    "skipped_no_ngspice",
    "ran_successfully",
    "failed_to_converge",
    "parser_failed",
)


@dataclass(frozen=True)
class NonlinearVariant:
    name: str
    description: str
    realism_label: str
    realism_score: float
    include_behavioral_mix: bool = False
    include_vdep_cap: bool = False
    include_diode_pair: bool = False
    include_varactor_diode: bool = False
    include_saturable_inductor: bool = False
    include_soft_limiter: bool = False


@dataclass(frozen=True)
class SpiceExport:
    circuit_name: str
    scale_name: str
    role: str
    nonlinear_variant: str
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


@dataclass(frozen=True)
class RunResult:
    execution_status: str
    success: bool
    reason: str
    log_path: Path | None = None


NONLINEAR_VARIANTS: Dict[str, NonlinearVariant] = {
    "behavioral_proxy_current": NonlinearVariant(
        name="behavioral_proxy_current",
        description="Original behavioral current export: varactor-like ddt(C(V)) plus explicit nonlinear mixing currents.",
        realism_label="aggressive behavioral proxy",
        realism_score=0.52,
        include_behavioral_mix=True,
        include_vdep_cap=True,
        include_soft_limiter=True,
    ),
    "voltage_dependent_capacitance_proxy": NonlinearVariant(
        name="voltage_dependent_capacitance_proxy",
        description="Voltage-controlled capacitance terms without explicit sum-frequency current injection.",
        realism_label="aggressive but component-adjacent",
        realism_score=0.62,
        include_vdep_cap=True,
        include_soft_limiter=True,
    ),
    "diode_pair_proxy": NonlinearVariant(
        name="diode_pair_proxy",
        description="Anti-parallel diode pairs between adjacent resonators as a passive nonlinear coupling proxy.",
        realism_label="physically plausible component proxy, likely weak",
        realism_score=0.74,
        include_diode_pair=True,
        include_soft_limiter=True,
    ),
    "varactor_diode_model_proxy": NonlinearVariant(
        name="varactor_diode_model_proxy",
        description="Diode junction-capacitance varactor proxy between adjacent resonators.",
        realism_label="plausible but parameter-sensitive",
        realism_score=0.70,
        include_varactor_diode=True,
        include_soft_limiter=True,
    ),
    "saturable_inductor_proxy": NonlinearVariant(
        name="saturable_inductor_proxy",
        description="Cubic restoring-current proxy for a saturable magnetic branch.",
        realism_label="aggressive magnetic saturation proxy",
        realism_score=0.58,
        include_saturable_inductor=True,
        include_soft_limiter=True,
    ),
    "linear_no_nonlinearity_control": NonlinearVariant(
        name="linear_no_nonlinearity_control",
        description="Linear LC and weak coupling only; should not reproduce the nonlinear bridge.",
        realism_label="linear control",
        realism_score=1.0,
    ),
}


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


def clean_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


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


def variant_suffix(variant_name: str) -> str:
    return "" if variant_name == "behavioral_proxy_current" else f"_{variant_name}"


def discovery_specs(variant_names: Iterable[str]) -> List[Tuple[str, str, phys.BridgeConfig, str, NonlinearVariant]]:
    specs: List[Tuple[str, str, phys.BridgeConfig, str, NonlinearVariant]] = []
    for variant_name in variant_names:
        variant = NONLINEAR_VARIANTS[variant_name]
        suffix = variant_suffix(variant_name)
        for prefix, scale_name in DISCOVERY_SCALES:
            specs.append((f"{prefix}{suffix}", scale_name, phys.CANDIDATE, "discovery", variant))
    reference_variant = NONLINEAR_VARIANTS["behavioral_proxy_current"]
    specs.append(("reference_direct_4plus8", REFERENCE_SCALE, phys.DIRECT_REFERENCE, "ceiling_reference", reference_variant))
    return specs


def variant_lines(scale_name: str, config: phys.BridgeConfig, variant: NonlinearVariant) -> List[str]:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    mix = nonlinear_mix_coefficients(scale_name, config)
    limiter = soft_limiter_params(scale_name, config)
    c = [p.capacitance_f for p in params]
    vscale = [p.voltage_scale_v for p in params]
    lines: List[str] = [
        "",
        f"* Nonlinear variant: {variant.name}",
        f"* {variant.description}",
    ]
    if variant.include_vdep_cap:
        lines.append("* Voltage-dependent capacitance terms.")
        for idx, p_lc in enumerate(params, start=1):
            lines.append(f".param beta{idx}={spice_num(p_lc.varactor_beta_per_v2)}")
            lines.append(f"Bvar{idx} n{idx} 0 I={{c{idx}*beta{idx}*V(n{idx})*V(n{idx})*ddt(V(n{idx}))}}")
        if variant.name == "voltage_dependent_capacitance_proxy":
            bx12 = 0.15 * abs(mix["mixa_00_to_2"]) / max(c[1], 1e-30)
            bx23 = 0.08 * abs(mix["mixb_01_to_3"]) / max(c[2], 1e-30)
            lines.extend([
                f".param betax12={spice_num(bx12)}",
                f".param betax23={spice_num(bx23)}",
                "Bxcap12 n2 0 I={c2*betax12*V(n1)*V(n1)*ddt(V(n2))}",
                "Bxcap23 n3 0 I={c3*betax23*V(n2)*V(n2)*ddt(V(n3))}",
            ])
    if variant.include_behavioral_mix:
        lines.extend([
            "* Explicit behavioral nonlinear mixing currents, scaled from the validated normalized LC model.",
            f".param mixa_01_to_1={spice_num(mix['mixa_01_to_1'])}",
            f".param mixa_00_to_2={spice_num(mix['mixa_00_to_2'])}",
            f".param mixb_12_to_1={spice_num(mix['mixb_12_to_1'])}",
            f".param mixb_02_to_2={spice_num(mix['mixb_02_to_2'])}",
            f".param mixb_01_to_3={spice_num(mix['mixb_01_to_3'])}",
            "Bmix1 n1 0 I={-(mixa_01_to_1*V(n1)*V(n2) + mixb_12_to_1*V(n2)*V(n3))}",
            "Bmix2 n2 0 I={-(mixa_00_to_2*V(n1)*V(n1) + mixb_02_to_2*V(n1)*V(n3))}",
            "Bmix3 n3 0 I={-(mixb_01_to_3*V(n1)*V(n2))}",
        ])
    if variant.include_diode_pair:
        vt = 0.035 * math.sqrt(vscale[0] * vscale[1])
        rs = max(0.1, 0.05 * math.sqrt(params[0].resistance_ohm * params[1].resistance_ohm))
        lines.extend([
            "* Anti-parallel diode-pair nonlinear coupling proxy.",
            f".model DPAIR D(Is={spice_num(1e-12)} N=1.7 Rs={spice_num(rs)} Cjo={spice_num(0.002 * min(c))} Vj={spice_num(max(vt, 0.1))} M=0.45)",
            "Dpair12a n1 n2 DPAIR",
            "Dpair12b n2 n1 DPAIR",
            "Dpair23a n2 n3 DPAIR",
            "Dpair23b n3 n2 DPAIR",
        ])
    if variant.include_varactor_diode:
        lines.extend([
            "* Junction-capacitance varactor-diode proxy between adjacent resonators.",
            f".model DVAR D(Is={spice_num(1e-14)} N=1.2 Rs={spice_num(0.5)} Cjo={spice_num(0.015 * min(c))} Vj=1.0 M=0.5 Fc=0.5)",
            "Dvar12a n1 n2 DVAR",
            "Dvar12b n2 n1 DVAR",
            "Dvar23a n2 n3 DVAR",
            "Dvar23b n3 n2 DVAR",
        ])
    if variant.include_saturable_inductor:
        scale = phys.scale_factor(preset)
        ksat1 = 0.012 * c[0] * (2.0 * math.pi * params[0].frequency_hz) ** 2 / max(vscale[0] ** 2, 1e-30)
        ksat2 = 0.012 * c[1] * (2.0 * math.pi * params[1].frequency_hz) ** 2 / max(vscale[1] ** 2, 1e-30)
        ksat3 = 0.012 * c[2] * (2.0 * math.pi * params[2].frequency_hz) ** 2 / max(vscale[2] ** 2, 1e-30)
        _ = scale
        lines.extend([
            "* Cubic restoring-current proxy for saturable magnetic branches.",
            f".param ksat1={spice_num(ksat1)}",
            f".param ksat2={spice_num(ksat2)}",
            f".param ksat3={spice_num(ksat3)}",
            "Bsat1 n1 0 I={ksat1*V(n1)*V(n1)*V(n1)}",
            "Bsat2 n2 0 I={ksat2*V(n2)*V(n2)*V(n2)}",
            "Bsat3 n3 0 I={ksat3*V(n3)*V(n3)*V(n3)}",
        ])
    if variant.include_soft_limiter:
        lines.extend([
            "* Passive soft limiter / loss proxy. Current follows voltage drop, so it dissipates.",
            f".param gsoft12={spice_num(limiter['gsoft12'])}",
            f".param gsoft23={spice_num(limiter['gsoft23'])}",
            f".param vlim12={spice_num(limiter['vlim12'])}",
            f".param vlim23={spice_num(limiter['vlim23'])}",
            "Bsoft12 n1 n2 I={gsoft12*V(n1,n2)*0.5*(1+tanh((abs(V(n1,n2))-vlim12)/(0.3*vlim12+1e-30)))}",
            "Bsoft23 n2 n3 I={gsoft23*V(n2,n3)*0.5*(1+tanh((abs(V(n2,n3))-vlim23)/(0.3*vlim23+1e-30)))}",
        ])
    if variant.name == "linear_no_nonlinearity_control":
        lines.append("* Linear control: no nonlinear capacitance, diode, saturable, limiter, or behavioral mixing elements.")
    return lines


def netlist_text(circuit_name: str, scale_name: str, config: phys.BridgeConfig, role: str,
                 variant: NonlinearVariant, out_dir: Path) -> Tuple[str, SpiceExport]:
    preset = phys.SCALE_PRESETS[scale_name]
    params = phys.build_lc_params(config, preset)
    coupling = phys.coupling_summary(config)
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
        f"* scale={scale_name}; role={role}; nonlinear_variant={variant.name}",
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
    ])
    lines.extend(variant_lines(scale_name, config, variant))
    lines.extend([
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
        nonlinear_variant=variant.name,
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


def export_netlists(out_dir: Path, variant_names: Iterable[str]) -> List[SpiceExport]:
    exports: List[SpiceExport] = []
    for circuit_name, scale_name, config, role, variant in discovery_specs(variant_names):
        text, export = netlist_text(circuit_name, scale_name, config, role, variant, out_dir)
        export.netlist_path.write_text(text, encoding="utf-8")
        exports.append(export)
    return exports


def classify_run_failure(message: str) -> str:
    lower = message.lower()
    if any(token in lower for token in ("convergence", "timestep too small", "singular", "failed", "error")):
        return "failed_to_converge"
    return "failed_to_converge"


def run_ngspice(export: SpiceExport, ngspice_path: str, timeout_s: int) -> RunResult:
    if ngspice_path.startswith("wsl:"):
        tool = ngspice_path.split(":", 1)[1] or "ngspice"
        cwd_proc = subprocess.run(
            ["wsl", "-e", "wslpath", "-a", str(export.netlist_path.parent)],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if cwd_proc.returncode != 0:
            return RunResult("failed_to_converge", False, f"wslpath failed: {cwd_proc.stderr.strip()}")
        wsl_cwd = cwd_proc.stdout.strip()
        cmd = ["wsl", "-e", "sh", "-lc", f"cd {sh_quote(wsl_cwd)} && {tool} -b {sh_quote(export.netlist_path.name)}"]
        run_cwd = None
    else:
        cmd = [ngspice_path, "-b", export.netlist_path.name]
        run_cwd = str(export.netlist_path.parent)
    try:
        proc = subprocess.run(
            cmd,
            cwd=run_cwd,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - depends on local ngspice install.
        return RunResult("failed_to_converge", False, f"{type(exc).__name__}: {exc}")
    log_path = export.netlist_path.with_suffix(".log")
    log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    log_path.write_text(log_text, encoding="utf-8")
    if proc.returncode != 0:
        return RunResult(classify_run_failure(log_text), False, f"returncode={proc.returncode}; log={log_path.name}", log_path)
    if not export.csv_path.exists():
        return RunResult("failed_to_converge", False, f"returncode=0 but CSV missing; log={log_path.name}", log_path)
    return RunResult("ran_successfully", True, f"returncode=0; log={log_path.name}", log_path)


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def normalize_header_name(name: str) -> str:
    lowered = name.strip().lower()
    lowered = lowered.replace('"', "").replace("'", "")
    return lowered


def column_by_alias(names: List[str], aliases: Iterable[str]) -> int | None:
    alias_set = set(aliases)
    for idx, name in enumerate(names):
        clean = normalize_header_name(name)
        if clean in alias_set:
            return idx
        for alias in alias_set:
            if alias and alias in clean:
                return idx
    return None


def read_ngspice_csv(path: Path) -> Dict[str, np.ndarray]:
    if not path.exists():
        raise ValueError(f"CSV does not exist: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No data in {path}")
    first_tokens = lines[0].replace(",", " ").split()
    first_numeric = [try_float(tok) for tok in first_tokens]
    has_header = any(value is None for value in first_numeric)
    data_lines = lines[1:] if has_header else lines
    rows: List[List[float]] = []
    for line in data_lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(v) for v in values if v is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"No numeric rows in {path}")
    min_cols = min(len(row) for row in rows)
    arr = np.asarray([row[:min_cols] for row in rows], dtype=float)
    if has_header:
        names = first_tokens[: arr.shape[1]]
        idx_time = column_by_alias(names, ("time", "time-s"))
        idx_v1 = column_by_alias(names, ("v(n1)", "n1", "v_n1"))
        idx_v2 = column_by_alias(names, ("v(n2)", "n2", "v_n2"))
        idx_v3 = column_by_alias(names, ("v(n3)", "n3", "v_n3"))
        idx_i1 = column_by_alias(names, ("i(l1)", "l1#branch", "i_l1"))
        idx_i2 = column_by_alias(names, ("i(l2)", "l2#branch", "i_l2"))
        idx_i3 = column_by_alias(names, ("i(l3)", "l3#branch", "i_l3"))
        required = (idx_time, idx_v1, idx_v2, idx_v3)
        if any(idx is None for idx in required):
            raise ValueError(f"Missing required time/v(n1)/v(n2)/v(n3) columns in {path}; header={first_tokens}")
        result = {
            "time": arr[:, int(idx_time)],
            "v1": arr[:, int(idx_v1)],
            "v2": arr[:, int(idx_v2)],
            "v3": arr[:, int(idx_v3)],
        }
        if idx_i1 is not None and idx_i2 is not None and idx_i3 is not None:
            result.update({"i1": arr[:, int(idx_i1)], "i2": arr[:, int(idx_i2)], "i3": arr[:, int(idx_i3)]})
        return result
    if arr.shape[1] >= 12 and np.allclose(arr[:, 0], arr[:, 2]) and np.allclose(arr[:, 0], arr[:, 4]):
        return {
            "time": arr[:, 0],
            "v1": arr[:, 3],
            "v2": arr[:, 5],
            "v3": arr[:, 7],
            "i1": arr[:, 9],
            "i2": arr[:, 11],
            "i3": arr[:, 13] if arr.shape[1] > 13 else arr[:, 11],
        }
    if arr.shape[1] >= 7:
        return {
            "time": arr[:, 0],
            "v1": arr[:, 1],
            "v2": arr[:, 2],
            "v3": arr[:, 3],
            "i1": arr[:, 4],
            "i2": arr[:, 5],
            "i3": arr[:, 6],
        }
    raise ValueError(f"Expected at least time and three voltage columns in {path}, got {arr.shape[1]}")


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


def fft_peak(signal: np.ndarray, time_s: np.ndarray, min_hz: float = 0.0) -> Tuple[float, float]:
    if len(signal) < 8:
        return float("nan"), 0.0
    dt = float(np.median(np.diff(time_s)))
    if dt <= 0:
        return float("nan"), 0.0
    centered = signal - float(np.mean(signal))
    window = np.hanning(len(centered))
    spec = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), dt)
    amps = np.abs(spec)
    mask = freqs >= min_hz
    if not np.any(mask):
        return float("nan"), 0.0
    sub_idx = int(np.argmax(amps[mask]))
    full_idx = np.flatnonzero(mask)[sub_idx]
    return float(freqs[full_idx]), float(amps[full_idx])


def rms(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.sqrt(np.mean(values ** 2)))


def spice_metrics(export: SpiceExport, data: Dict[str, np.ndarray],
                  reference_data: Dict[str, np.ndarray] | None = None) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    t = data["time"]
    v1 = data["v1"]
    v2 = data["v2"]
    v3 = data["v3"]
    if len(t) < 32:
        return {"spice_metric_error": "not_enough_samples"}, []
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(v1)) or not np.all(np.isfinite(v2)) or not np.all(np.isfinite(v3)):
        return {"spice_metric_error": "non_finite_samples"}, []

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
    phase_stable = np.median(np.abs(z3[:min_len])) > 1e-12 and np.median(np.abs(z2[:min_len])) > 1e-12
    if phase_stable:
        phase_error = np.unwrap(np.angle(z1[:min_len]) + np.angle(z2[:min_len]) - np.angle(z3[:min_len]))
        wrapped = (phase_error + np.pi) % (2.0 * np.pi) - np.pi
        lock = float(abs(np.mean(np.exp(1j * wrapped))))
        phase_step = np.abs(np.diff(phase_error)) if len(phase_error) >= 2 else np.asarray([])
        near_slips = coalesced_indices(np.where(phase_step > 1.0)[0] + 1)
    else:
        phase_error = np.full(min_len, np.nan)
        wrapped = np.full(min_len, np.nan)
        lock = float("nan")
        phase_step = np.asarray([])
        near_slips = []

    target_amp = complex_projection(v3[mask], tm, export.nominal_target_frequency_hz)
    generated_amp = complex_projection(v2[mask], tm, export.nominal_generated_frequency_hz)
    target_power = 0.5 * abs(target_amp) ** 2
    purity = float(min(1.0, target_power / (float(np.mean(v3[mask] ** 2)) + 1e-18)))
    bridge_ratio = float("nan")
    if reference_data is not None and export.scale_name == REFERENCE_SCALE:
        rt = reference_data["time"]
        rv3 = reference_data["v3"]
        rmask = (rt >= 0.35 * drive_until) & (rt < drive_until)
        if int(np.sum(rmask)) >= 32:
            ref_amp = complex_projection(rv3[rmask], rt[rmask], export.nominal_target_frequency_hz)
            ref_power = 0.5 * abs(ref_amp) ** 2
            bridge_ratio = float(target_power / max(ref_power, 1e-30))

    early = t < 0.20 * drive_until
    late = (t >= 0.60 * drive_until) & (t < drive_until)
    target_growth = rms(v3[late]) / max(rms(v3[early]), 1e-30)
    source_peak_hz, source_peak_amp = fft_peak(v1[mask], tm, min_hz=0.25 * export.source_frequency_hz)
    generated_peak_hz, generated_peak_amp = fft_peak(v2[mask], tm, min_hz=0.25 * export.source_frequency_hz)
    target_peak_hz, target_peak_amp = fft_peak(v3[mask], tm, min_hz=0.25 * export.source_frequency_hz)

    rows: List[Dict[str, float | str]] = []
    for idx in range(min_len):
        rows.append({
            "row_type": "spice_phase_window",
            "circuit": export.circuit_name,
            "scale_preset": export.scale_name,
            "nonlinear_variant": export.nonlinear_variant,
            "time_s": float(mids[idx]),
            "phase_error_target": float(wrapped[idx]) if np.isfinite(wrapped[idx]) else "",
            "unwrapped_phase_error_target": float(phase_error[idx]) if np.isfinite(phase_error[idx]) else "",
            "generated_envelope": float(abs(z2[idx])),
            "target_envelope": float(abs(z3[idx])),
        })
    return {
        "spice_phase_lock_target": lock,
        "spice_phase_extraction_stable": str(phase_stable),
        "spice_bridge_ratio": bridge_ratio,
        "spice_spectral_purity_target": purity,
        "spice_generated_envelope_cv": envelope_cv(z2[:min_len]),
        "spice_target_envelope_cv": envelope_cv(z3[:min_len]),
        "spice_max_phase_jump": float(np.max(phase_step)) if len(phase_step) else 0.0,
        "spice_near_slip_count": float(len(near_slips)),
        "spice_target_rms_v": rms(v3[mask]),
        "spice_generated_rms_v": rms(v2[mask]),
        "spice_target_projection_power": float(target_power),
        "spice_target_voltage_growth_ratio": float(target_growth),
        "spice_fft_peak_source_hz": source_peak_hz,
        "spice_fft_peak_source_amp": source_peak_amp,
        "spice_fft_peak_generated_hz": generated_peak_hz,
        "spice_fft_peak_generated_amp": generated_peak_amp,
        "spice_fft_peak_target_hz": target_peak_hz,
        "spice_fft_peak_target_amp": target_peak_amp,
    }, rows


def rough_python_match(metrics: Dict[str, float | str]) -> str:
    lock = float(metrics.get("spice_phase_lock_target", float("nan")))
    purity = float(metrics.get("spice_spectral_purity_target", float("nan")))
    bridge = float(metrics.get("spice_bridge_ratio", float("nan")))
    lock_ok = np.isfinite(lock) and abs(lock - PYTHON_BASELINE["phase_lock_target"]) < 0.20
    purity_ok = np.isfinite(purity) and abs(purity - PYTHON_BASELINE["spectral_purity_target"]) < 0.25
    bridge_ok = not np.isfinite(bridge) or abs(bridge - PYTHON_BASELINE["bridge_ratio"]) < 0.75
    return str(lock_ok and purity_ok and bridge_ok)


def summarize_export(export: SpiceExport, variant: NonlinearVariant, run_requested: bool,
                     ngspice_available: bool, ngspice_path: str | None,
                     run_result: RunResult, metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    preset = phys.SCALE_PRESETS[export.scale_name]
    params = phys.build_lc_params(phys.DIRECT_REFERENCE if export.role == "ceiling_reference" else phys.CANDIDATE, preset)
    coupling = phys.coupling_summary(phys.CANDIDATE)
    row: Dict[str, float | str] = {
        "row_type": "spice_export",
        "circuit": export.circuit_name,
        "scale_preset": export.scale_name,
        "role": export.role,
        "nonlinear_variant": export.nonlinear_variant,
        "nonlinear_variant_description": variant.description,
        "netlist_path": str(export.netlist_path),
        "csv_path": str(export.csv_path) if run_result.success else "",
        "raw_path": str(export.raw_path) if run_result.success else "",
        "valid_spice_netlist_generated": str(export.netlist_path.exists()),
        "execution_status": run_result.execution_status,
        "execution_status_allowed": str(run_result.execution_status in EXECUTION_STATUSES),
        "failure_reason": "" if run_result.success else run_result.reason,
        "ngspice_run_message": run_result.reason,
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "ngspice_path": ngspice_path or "",
        "ngspice_run_succeeded": str(run_result.success),
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
        "nonlinear_realism_score": variant.realism_score,
        "nonlinear_element_assessment": variant.realism_label,
        "recommended_next_step": "component refinement, parameter sweep, then spatial phase-matching model",
    }
    if metrics:
        row.update(metrics)
        row["rough_python_behavior_match"] = rough_python_match(metrics)
    return row


def aggregate_summary(rows: List[Dict[str, float | str]], run_requested: bool, ngspice_available: bool) -> Dict[str, float | str]:
    exports = [r for r in rows if str(r.get("row_type")) == "spice_export"]
    discovery = [r for r in exports if str(r.get("role")) == "discovery"]
    ran = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    source_only = all(
        str(r["direct_8_drive_present"]) == "False"
        and str(r["direct_12_drive_present"]) == "False"
        and str(r["target_frequency_injection_present"]) == "False"
        for r in discovery
    )
    target_build_rows = [
        r for r in ran
        if float(r.get("spice_target_voltage_growth_ratio", 0.0) or 0.0) > 1.10
        or float(r.get("spice_target_rms_v", 0.0) or 0.0) > 1e-12
    ]
    matching_rows = [r for r in ran if str(r.get("rough_python_behavior_match")) == "True"]
    linear_rows = [r for r in ran if str(r.get("nonlinear_variant")) == "linear_no_nonlinearity_control"]
    linear_failed = "not_run"
    if linear_rows:
        linear_failed = str(all(float(r.get("spice_target_voltage_growth_ratio", 0.0) or 0.0) < 1.25 for r in linear_rows))
    statuses = sorted(set(str(r.get("execution_status")) for r in exports))
    return {
        "row_type": "aggregate",
        "valid_spice_netlists_generated": str(all(str(r["valid_spice_netlist_generated"]) == "True" for r in exports)),
        "canonical_required_netlists_present": str(all((OUT_DIR / name).exists() for name in REQUIRED_CANONICAL_FILES)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "ngspice_runs_completed": str(bool(ran)),
        "execution_statuses": ";".join(statuses),
        "discovery_rows_source_only": str(source_only),
        "reference_direct_4plus8_separated": str(any(str(r.get("role")) == "ceiling_reference" for r in exports)),
        "spice_target_build_up_observed": str(bool(target_build_rows)) if ran else "not_run",
        "target_build_up_circuits": ";".join(str(r["circuit"]) for r in target_build_rows),
        "rough_python_match_available": str(bool(matching_rows)) if ran else "not_run",
        "rough_python_match_circuits": ";".join(str(r["circuit"]) for r in matching_rows),
        "linear_no_nonlinearity_control_failed_as_expected": linear_failed,
        "nonlinear_element_assessment": "behavioral proxy remains aggressive; diode/varactor/saturable variants are first-pass realism checks",
        "recommended_next_step": "Run ngspice if available, then component refinement, parameter sweep, and spatial phase-matching modeling",
    }


def write_report(out_dir: Path, summary_rows: List[Dict[str, float | str]], aggregate: Dict[str, float | str]) -> None:
    rows = [r for r in summary_rows if str(r.get("row_type")) == "spice_export"]
    ran = [r for r in rows if str(r.get("execution_status")) == "ran_successfully"]
    lines = [
        "# SPICE 4->8->12 Bridge Export",
        "",
        "This track exports the physical 4->8->12 LC bridge into ngspice-compatible netlists. Discovery netlists drive only resonator 1. The direct 4+8 netlist is separated as a ceiling/reference denominator and is not a discovery row.",
        "",
        "## Direct Answers",
        f"1. Which netlists ran successfully under ngspice? {aggregate.get('rough_python_match_circuits') if ran else 'none in this run'}; execution_statuses={aggregate.get('execution_statuses')}.",
        f"2. Did any source-only SPICE netlist show target build-up near 12? {aggregate.get('spice_target_build_up_observed')}; circuits={aggregate.get('target_build_up_circuits')}.",
        f"3. Did any nonlinear model variant roughly reproduce the Python LC behavior? {aggregate.get('rough_python_match_available')}; circuits={aggregate.get('rough_python_match_circuits')}.",
        f"4. Did the linear-no-nonlinearity control fail as expected? {aggregate.get('linear_no_nonlinearity_control_failed_as_expected')}.",
        f"5. Is the required nonlinear element plausible, aggressive, or unrealistic? {aggregate.get('nonlinear_element_assessment')}.",
        f"6. Next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Exported Netlists",
    ]
    for row in rows:
        lines.append(
            f"- {row['circuit']}: status={row['execution_status']}, role={row['role']}, scale={row['scale_preset']}, "
            f"variant={row['nonlinear_variant']}, netlist={Path(str(row['netlist_path'])).name}."
        )
        lines.append(
            f"  Drive flags: direct_8={row['direct_8_drive_present']}, direct_12={row['direct_12_drive_present']}, target_injection={row['target_frequency_injection_present']}."
        )
        if str(row.get("execution_status")) == "ran_successfully":
            lines.append(
                f"  SPICE metrics: target_growth={float(row.get('spice_target_voltage_growth_ratio', 0.0)):.6g}, "
                f"lock={float(row.get('spice_phase_lock_target', 0.0)):.6g}, "
                f"bridge={float(row.get('spice_bridge_ratio', 0.0)):.6g}, purity={float(row.get('spice_spectral_purity_target', 0.0)):.6g}, "
                f"gen_cv={float(row.get('spice_generated_envelope_cv', 0.0)):.6g}, max_jump={float(row.get('spice_max_phase_jump', 0.0)):.6g}."
            )
        else:
            lines.append(f"  Execution note: {row['failure_reason'] or row['ngspice_run_message']}.")
    lines.extend([
        "",
        "## Circuit Notes",
        "",
        "- Each resonator is a capacitor in parallel with an inductor branch whose series resistance matches the physical Q.",
        "- Weak linear coupling is exported as mutual inductive coupling between adjacent resonators.",
        "- Nonlinear variants include behavioral current mixing, voltage-dependent capacitance, diode pairs, varactor-diode models, saturable-inductor proxies, and a linear no-nonlinearity control.",
        "- The behavioral current variant remains the most aggressive and closest to the Python LC abstraction.",
        "- The diode/varactor/saturable variants are first-pass realism checks, not yet tuned component implementations.",
    ])
    (out_dir / "README_SPICE_412_EXPORT.md").write_text("\n".join(lines), encoding="utf-8")


def parse_variants(raw: str) -> List[str]:
    if raw.strip().lower() == "all":
        return list(NONLINEAR_VARIANTS.keys())
    names = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in names if name not in NONLINEAR_VARIANTS]
    if unknown:
        raise ValueError(f"Unknown nonlinear variant(s): {', '.join(unknown)}. Valid: {', '.join(NONLINEAR_VARIANTS)}")
    return names


def resolve_ngspice_path(raw_path: str | None) -> str | None:
    if raw_path:
        if raw_path.startswith("wsl:"):
            tool = raw_path.split(":", 1)[1] or "ngspice"
            probe = subprocess.run(
                ["wsl", "-e", "sh", "-lc", f"command -v {sh_quote(tool)} >/dev/null 2>&1"],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            return raw_path if probe.returncode == 0 else None
        candidate = Path(raw_path)
        if candidate.exists():
            return str(candidate)
        found = shutil.which(raw_path)
        return found
    native = shutil.which("ngspice")
    if native:
        return native
    probe = subprocess.run(
        ["wsl", "-e", "sh", "-lc", "command -v ngspice >/dev/null 2>&1"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if probe.returncode == 0:
        return "wsl:ngspice"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and optionally run ngspice validation for the physical 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice. Export only unless this flag is set.")
    parser.add_argument("--ngspice-path", default="", help="Explicit path to ngspice executable.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per ngspice netlist in seconds.")
    parser.add_argument("--variants", default="all", help="Comma-separated nonlinear variants or 'all'.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    variant_names = parse_variants(args.variants)
    exports = export_netlists(out_dir, variant_names)
    ngspice_path = resolve_ngspice_path(args.ngspice_path or None)
    ngspice_available = ngspice_path is not None

    parsed_data: Dict[str, Dict[str, np.ndarray]] = {}
    run_results: Dict[str, RunResult] = {}
    if args.run and not ngspice_available:
        for export in exports:
            run_results[export.circuit_name] = RunResult("skipped_no_ngspice", False, "ngspice not found; pass --ngspice-path or add ngspice to PATH")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed_data[export.circuit_name] = read_ngspice_csv(export.csv_path)
                except Exception as exc:
                    result = RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            run_results[export.circuit_name] = result
    else:
        for export in exports:
            run_results[export.circuit_name] = RunResult("exported", False, "export only; use --run to execute ngspice")

    reference_data = parsed_data.get("reference_direct_4plus8")
    summary_rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    for export in exports:
        variant = NONLINEAR_VARIANTS[export.nonlinear_variant]
        result = run_results[export.circuit_name]
        metrics: Dict[str, float | str] | None = None
        phase_rows: List[Dict[str, float | str]] = []
        if result.success and export.circuit_name in parsed_data:
            metrics, phase_rows = spice_metrics(export, parsed_data[export.circuit_name], reference_data)
            data = parsed_data[export.circuit_name]
            for idx in range(len(data["time"])):
                item: Dict[str, float | str] = {
                    "row_type": "spice_timeseries",
                    "circuit": export.circuit_name,
                    "scale_preset": export.scale_name,
                    "nonlinear_variant": export.nonlinear_variant,
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
        summary_rows.append(summarize_export(export, variant, args.run, ngspice_available, ngspice_path, result, metrics))

    aggregate = aggregate_summary(summary_rows, args.run, ngspice_available)
    all_summary_rows = [aggregate] + summary_rows
    write_csv(out_dir / "spice_412_summary.csv", all_summary_rows)
    timeseries_path = out_dir / "spice_412_timeseries.csv"
    if timeseries_rows:
        write_csv(timeseries_path, timeseries_rows)
    elif timeseries_path.exists():
        timeseries_path.unlink()
    (out_dir / "spice_412_summary.json").write_text(json.dumps({
        "aggregate": aggregate,
        "rows": all_summary_rows,
        "python_lc_baseline": PYTHON_BASELINE,
        "execution_statuses": EXECUTION_STATUSES,
        "nonlinear_variants": {name: asdict(variant) for name, variant in NONLINEAR_VARIANTS.items()},
        "netlists": [{
            **asdict(export),
            "netlist_path": str(export.netlist_path),
            "csv_path": str(export.csv_path),
            "raw_path": str(export.raw_path),
        } for export in exports],
    }, indent=2), encoding="utf-8")
    write_report(out_dir, all_summary_rows, aggregate)

    print(f"SPICE 4->8->12 export written to: {out_dir.resolve()}")
    print(f"valid_spice_netlists_generated={aggregate['valid_spice_netlists_generated']}")
    print(f"run_requested={aggregate['run_requested']}")
    print(f"ngspice_available={aggregate['ngspice_available']}")
    print(f"execution_statuses={aggregate['execution_statuses']}")
    print(f"discovery_rows_source_only={aggregate['discovery_rows_source_only']}")


if __name__ == "__main__":
    main()
