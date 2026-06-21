"""Phase-lock refinement sweep for component-plausible 4->8->12 SPICE rows.

This track starts from the component-realism rows that crossed bridge ratio
1.5, then varies detuning, coupling orientation, Q/load shaping, traps, and
limiter loss to see whether a source-only component circuit can recover
coherent 4->8->12 phase lock.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import physical_412_lc_bridge as phys
import spice_412_component_realism as comp
import spice_412_export as base


OUT_DIR = Path("runs") / "spice_412_component_phase_lock"
SCALE_NAME = "arbitrary-normalized-scale"
VT = comp.VT

TARGET_DETUNINGS = (-0.120, -0.100, -0.090, -0.080, -0.070, -0.060, -0.040)
GENERATED_DETUNINGS = (-0.060, -0.040, -0.020, 0.000, 0.020, 0.040, 0.060)
COUPLING_ORIENTATIONS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
COUPLING_STRENGTHS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
SOURCE_Q_SCALES = (0.5, 1.0, 1.5)
GENERATED_Q_SCALES = (0.5, 1.0, 1.5, 2.0)
TARGET_Q_SCALES = (0.5, 1.0, 1.5, 2.0)
TRAP_KINDS = ("none", "weak_target_band_trap", "generated_band_trap", "source_band_rejection_trap")
LIMITER_LOSS_SCALES = (0.5, 1.0, 1.5, 2.0)

SEED_CASE_IDS = ("c008", "c013", "c018", "c023", "c028", "c033")
BASE_TARGET_DETUNING = -0.090
BASE_GENERATED_DETUNING = 0.040


@dataclass(frozen=True)
class PhaseCase:
    case_id: str
    seed_case_id: str
    variant_name: str
    role: str
    sweep_focus: str
    diode_is: float
    diode_n: float
    junction_cap_scale: float
    varactor_c0_scale: float
    varactor_vj: float
    varactor_exponent: float
    saturable_l0_scale: float
    saturation_current_scale: float
    core_exponent: float
    seed_coupling_scale: float
    drive_amplitude_scale: float
    source_load_impedance_scale: float
    target_detuning: float
    generated_detuning: float
    k12_sign: int
    k23_sign: int
    coupling_strength_scale: float
    source_q_scale: float
    generated_q_scale: float
    target_q_scale: float
    trap_kind: str
    limiter_loss_scale: float
    solver_profile: str
    maxstep_scale: float
    config_kind: str = "candidate"

    @property
    def reference_key(self) -> str:
        return self.seed_case_id


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


def token(value: float | int | str) -> str:
    return str(value).replace(".", "p").replace("-", "m").replace("+", "p")


def seed_component_cases() -> Dict[str, comp.ComponentCase]:
    return {case.case_id: case for case in comp.focused_cases(44) if case.case_id in SEED_CASE_IDS}


def component_case(case: PhaseCase) -> comp.ComponentCase:
    return comp.ComponentCase(
        case_id=case.case_id,
        variant_name=case.variant_name,
        role=case.role,
        diode_is=case.diode_is,
        diode_n=case.diode_n,
        junction_cap_scale=case.junction_cap_scale,
        varactor_c0_scale=case.varactor_c0_scale,
        varactor_vj=case.varactor_vj,
        varactor_exponent=case.varactor_exponent,
        saturable_l0_scale=case.saturable_l0_scale,
        saturation_current_scale=case.saturation_current_scale,
        core_exponent=case.core_exponent,
        coupling_scale=case.seed_coupling_scale * case.coupling_strength_scale,
        drive_amplitude_scale=case.drive_amplitude_scale,
        limiter_loss_scale=case.limiter_loss_scale,
        source_load_impedance_scale=case.source_load_impedance_scale,
        solver_profile=case.solver_profile,
        maxstep_scale=case.maxstep_scale,
        config_kind=case.config_kind,
    )


def config_for_case(case: PhaseCase, reference: bool = False) -> phys.BridgeConfig:
    source = phys.DIRECT_REFERENCE if reference else phys.CANDIDATE
    generated = 8.0 + case.generated_detuning
    target = 12.0 + case.target_detuning
    drive_freqs = source.drive_freqs
    drive_modes = source.drive_modes
    if case.config_kind == "detuned_target_control":
        target = 12.72
    elif case.config_kind == "shuffled_frequency_control":
        generated, target = target, generated
    elif case.config_kind == "source_off_resonance_control":
        drive_freqs = (4.35,) if not reference else source.drive_freqs
        drive_modes = (0,) if not reference else source.drive_modes
    return replace(
        source,
        mode_freqs=(4.0, generated, target),
        drive_freqs=drive_freqs,
        drive_modes=drive_modes,
        stage_a_nonlinear_strength=0.0,
        stage_b_nonlinear_strength=0.0,
        stage_a_to_stage_b_coupling=(
            source.stage_a_to_stage_b_coupling
            * case.seed_coupling_scale
            * case.coupling_strength_scale
            * float(case.k12_sign)
        ),
        stage_b_to_receiver_coupling=(
            source.stage_b_to_receiver_coupling
            * case.seed_coupling_scale
            * case.coupling_strength_scale
            * float(case.k23_sign)
        ),
        stage_a_damping=source.stage_a_damping / max(case.source_q_scale, 1e-9),
        stage_b_damping=source.stage_b_damping / max(case.generated_q_scale, 1e-9),
        receiver_damping=source.receiver_damping / max(case.target_q_scale, 1e-9),
        drive_amp=source.drive_amp * case.drive_amplitude_scale,
        varactor_coefficient=0.0,
        spark_strength=source.spark_strength * case.limiter_loss_scale,
    )


def phase_case_name(case: PhaseCase) -> str:
    variant = comp.VARIANTS[case.variant_name]
    return (
        f"{case.case_id}_{case.seed_case_id}_{variant.short}_{case.sweep_focus}"
        f"_td{token(case.target_detuning)}_gd{token(case.generated_detuning)}"
        f"_k{case.k12_sign}{case.k23_sign}_cs{token(case.coupling_strength_scale)}"
        f"_q{token(case.source_q_scale)}-{token(case.generated_q_scale)}-{token(case.target_q_scale)}"
        f"_tr{token(case.trap_kind)}_l{token(case.limiter_loss_scale)}"
    )


def reference_name(seed_case_id: str) -> str:
    return f"ref_direct_4plus8_phase_{seed_case_id}"


def trap_lines(case: PhaseCase, params: List[phys.LCParams]) -> List[str]:
    if case.trap_kind == "none":
        return []
    min_c = min(p.capacitance_f for p in params)
    ctrap = min_c * 0.004

    def branch(node: str, freq_hz: float, tag: str, resistance: str) -> List[str]:
        inductance = 1.0 / max((2.0 * math.pi * freq_hz) ** 2 * ctrap, 1e-30)
        return [
            f"C{tag} {node} {tag} {base.spice_num(ctrap)}",
            f"L{tag} {tag} 0 {base.spice_num(inductance)}",
            f"R{tag} {tag} 0 {resistance}",
        ]

    if case.trap_kind == "weak_target_band_trap":
        return ["* Weak passive target-band trap / phase shaper."] + branch("n3", 3.0 * params[0].frequency_hz, "ptrap3", "50k")
    if case.trap_kind == "generated_band_trap":
        return ["* Passive generated-band trap / phase shaper."] + branch("n2", 2.0 * params[0].frequency_hz, "ptrap2", "35k")
    if case.trap_kind == "source_band_rejection_trap":
        return ["* Passive source-band rejection trap."] + branch("n1", params[0].frequency_hz, "ptrap1", "25k")
    return []


def export_netlist(out_dir: Path, case: PhaseCase, reference: bool = False) -> base.SpiceExport:
    config = config_for_case(case, reference=reference)
    ccase = component_case(case)
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[SCALE_NAME])
    coupling = phys.coupling_summary(config)
    flags = base.direct_drive_flags(config)
    tstop, tstep, drive_until, ramp = base.physical_timing(SCALE_NAME)
    maxstep = tstep * case.maxstep_scale
    hold_time = max(ramp, drive_until - ramp)
    circuit_name = reference_name(case.seed_case_id) if reference else phase_case_name(case)
    netlist_path = out_dir / f"{circuit_name}.cir"
    csv_path = out_dir / f"{circuit_name}_tran.csv"
    raw_path = out_dir / f"{circuit_name}.raw"

    drive_lines: List[str] = []
    drive_count = max(1, len(config.drive_freqs))
    for drive_idx, (freq_ratio, mode_idx) in enumerate(zip(config.drive_freqs, config.drive_modes), start=1):
        node = f"n{mode_idx + 1}"
        drive_frequency = phys.BASE_HZ * freq_ratio * phys.scale_factor(phys.SCALE_PRESETS[SCALE_NAME])
        amp = base.drive_current_for_mode(SCALE_NAME, config, mode_idx, drive_count)
        note = "direct 4+8 ceiling reference drive" if reference else "source-only phase-lock drive"
        drive_lines.extend([
            f"* {note}: mode {mode_idx + 1}, f={base.spice_num(drive_frequency)} Hz",
            f".param idrive{drive_idx}={base.spice_num(amp)}",
            f".param fdrive{drive_idx}={base.spice_num(drive_frequency)}",
            f"Bdrive{drive_idx} {node} 0 I={{-idrive{drive_idx}*V(env)*sin(2*pi*fdrive{drive_idx}*time)}}",
        ])

    lines = [
        f"* {circuit_name}: phase-lock refinement for component 4->8->12 bridge",
        f"* role={'ceiling_reference' if reference else case.role}; seed={case.seed_case_id}; variant={case.variant_name}",
        "* Generated by spice_412_component_phase_lock.py.",
        "* Discovery rows forbid behavioral current mixing, direct 8 drive, direct 12 drive, and target-frequency injection.",
        f".option {comp.SOLVER_PROFILES[case.solver_profile]}",
        ".param pi=3.141592653589793",
        f".param tstop={base.spice_num(tstop)}",
        f".param tstep={base.spice_num(tstep)}",
        f".param maxstep={base.spice_num(maxstep)}",
        f".param drive_until={base.spice_num(drive_until)}",
        f".param drive_ramp={base.spice_num(ramp)}",
        "",
        "* Drive envelope.",
        f"Venv env 0 PWL(0 0 {base.spice_num(ramp)} 1 {base.spice_num(hold_time)} 1 {base.spice_num(drive_until)} 0 {base.spice_num(tstop)} 0)",
        "",
        "* Three lossy LC resonators with Q/load shaping.",
    ]
    for idx, p_lc in enumerate(params, start=1):
        load_r = max(1e-6, case.source_load_impedance_scale * 100.0 * p_lc.resistance_ohm)
        lines.extend([
            f".param c{idx}={base.spice_num(p_lc.capacitance_f)}",
            f".param l{idx}={base.spice_num(p_lc.inductance_h * case.saturable_l0_scale)}",
            f".param r{idx}={base.spice_num(p_lc.resistance_ohm)}",
            f"C{idx} n{idx} 0 {{c{idx}}}",
            f"R{idx} n{idx} n{idx}l {{r{idx}}}",
            f"L{idx} n{idx}l 0 {{l{idx}}} IC=0",
            f"Rload{idx} n{idx} 0 {base.spice_num(load_r)}",
        ])
    lines.extend([
        "",
        "* Signed weak linear coupling.",
        f"K12 L1 L2 {base.spice_num(float(coupling['linear_k01_fraction_of_omega_product']))}",
        f"K23 L2 L3 {base.spice_num(float(coupling['linear_k12_fraction_of_omega_product']))}",
    ])
    lines.extend(comp.component_lines(SCALE_NAME, config, ccase, reference=reference))
    if not reference:
        lines.extend(trap_lines(case, params))
    lines.extend([
        "",
        "* External drives.",
        *drive_lines,
        "",
        ".ic V(n1)=0 V(n2)=0 V(n3)=0",
        f".tran {{tstep}} {{tstop}} 0 {{maxstep}} uic",
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
    netlist_path.write_text("\n".join(lines), encoding="utf-8")
    return base.SpiceExport(
        circuit_name=circuit_name,
        scale_name=SCALE_NAME,
        role="ceiling_reference" if reference else case.role,
        nonlinear_variant=case.variant_name,
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


def make_phase_case(seed: comp.ComponentCase, case_id: str, focus: str, role: str = "discovery",
                    target_detuning: float = BASE_TARGET_DETUNING,
                    generated_detuning: float = BASE_GENERATED_DETUNING,
                    k12_sign: int = 1, k23_sign: int = 1,
                    coupling_strength_scale: float = 1.0,
                    source_q_scale: float = 1.0, generated_q_scale: float = 1.0, target_q_scale: float = 1.0,
                    trap_kind: str = "none", limiter_loss_scale: float | None = None,
                    solver_profile: str | None = None, maxstep_scale: float | None = None,
                    variant_name: str | None = None, config_kind: str = "candidate") -> PhaseCase:
    return PhaseCase(
        case_id=case_id,
        seed_case_id=seed.case_id,
        variant_name=variant_name or seed.variant_name,
        role=role,
        sweep_focus=focus,
        diode_is=seed.diode_is,
        diode_n=seed.diode_n,
        junction_cap_scale=seed.junction_cap_scale,
        varactor_c0_scale=seed.varactor_c0_scale,
        varactor_vj=seed.varactor_vj,
        varactor_exponent=seed.varactor_exponent,
        saturable_l0_scale=seed.saturable_l0_scale,
        saturation_current_scale=seed.saturation_current_scale,
        core_exponent=seed.core_exponent,
        seed_coupling_scale=seed.coupling_scale,
        drive_amplitude_scale=seed.drive_amplitude_scale,
        source_load_impedance_scale=seed.source_load_impedance_scale,
        target_detuning=target_detuning,
        generated_detuning=generated_detuning,
        k12_sign=k12_sign,
        k23_sign=k23_sign,
        coupling_strength_scale=coupling_strength_scale,
        source_q_scale=source_q_scale,
        generated_q_scale=generated_q_scale,
        target_q_scale=target_q_scale,
        trap_kind=trap_kind,
        limiter_loss_scale=seed.limiter_loss_scale if limiter_loss_scale is None else limiter_loss_scale,
        solver_profile=solver_profile or seed.solver_profile,
        maxstep_scale=seed.maxstep_scale if maxstep_scale is None else maxstep_scale,
        config_kind=config_kind,
    )


def focused_cases(max_cases: int) -> List[PhaseCase]:
    seeds = seed_component_cases()
    discovery: List[PhaseCase] = []
    controls: List[PhaseCase] = []

    def add(seed_id: str, focus: str, **kwargs: object) -> None:
        target = controls if kwargs.get("role") == "control" else discovery
        target.append(make_phase_case(seeds[seed_id], f"p{len(discovery) + len(controls) + 1:03d}", focus, **kwargs))

    for seed_id in SEED_CASE_IDS:
        add(seed_id, "seed_baseline")
    for det in TARGET_DETUNINGS:
        add("c008", "target_detuning", target_detuning=det)
        add("c018", "target_detuning", target_detuning=det)
    for det in GENERATED_DETUNINGS:
        add("c008", "generated_detuning", generated_detuning=det)
        add("c018", "generated_detuning", generated_detuning=det)
    for k12, k23 in COUPLING_ORIENTATIONS:
        for seed_id in ("c008", "c013", "c018", "c023", "c028", "c033"):
            add(seed_id, "coupling_orientation", k12_sign=k12, k23_sign=k23)
    for strength in COUPLING_STRENGTHS:
        add("c008", "coupling_strength", coupling_strength_scale=strength)
        add("c018", "coupling_strength", coupling_strength_scale=strength)
    q_patterns = [
        (0.5, 1.0, 1.0), (1.5, 1.0, 1.0),
        (1.0, 0.5, 1.0), (1.0, 1.5, 1.0), (1.0, 2.0, 1.0),
        (1.0, 1.0, 0.5), (1.0, 1.0, 1.5), (1.0, 1.0, 2.0),
        (0.5, 2.0, 1.5), (1.5, 0.5, 2.0),
    ]
    for sq, gq, tq in q_patterns:
        add("c008", "q_load_shaping", source_q_scale=sq, generated_q_scale=gq, target_q_scale=tq)
        add("c018", "q_load_shaping", source_q_scale=sq, generated_q_scale=gq, target_q_scale=tq)
    for trap in TRAP_KINDS:
        add("c008", "resonant_trap", trap_kind=trap)
        add("c018", "resonant_trap", trap_kind=trap)
        add("c013", "resonant_trap", trap_kind=trap)
    for loss in LIMITER_LOSS_SCALES:
        add("c008", "limiter_loss", limiter_loss_scale=loss)
        add("c018", "limiter_loss", limiter_loss_scale=loss)

    # Controls under the coherent-growth criterion.
    add("c008", "linear_control", role="control", variant_name="linear_no_nonlinearity_control", config_kind="linear_no_nonlinearity_control")
    add("c008", "weak_control", role="control", variant_name="weak_nonlinearity_control", config_kind="weak_nonlinearity_control")
    add("c008", "detuned_control", role="control", variant_name="detuned_target_control", config_kind="detuned_target_control")
    add("c008", "shuffled_control", role="control", variant_name="shuffled_frequency_control", config_kind="shuffled_frequency_control")
    add("c008", "off_resonance_control", role="control", variant_name="linear_no_nonlinearity_control", config_kind="source_off_resonance_control")

    selected = discovery[:max_cases]
    # Renumber controls after discovery selection so case ids remain compact and stable.
    renumbered_controls = [
        PhaseCase(**{**asdict(case), "case_id": f"p{len(selected) + idx + 1:03d}"})
        for idx, case in enumerate(controls)
    ]
    return selected + renumbered_controls


def row_float(row: Dict[str, float | str], key: str, default: float = float("nan")) -> float:
    return base.row_float(row, key, default)


def extra_phase_metrics(export: base.SpiceExport, data: Dict[str, np.ndarray]) -> Dict[str, float | str]:
    uniform = base.uniform_resample(data, export.tstep_s)
    t = uniform["time"]
    v1 = uniform["v1"]
    v2 = uniform["v2"]
    v3 = uniform["v3"]
    drive_until = 0.74 * export.tstop_s
    mask = (t >= 0.35 * drive_until) & (t < drive_until)
    if int(np.sum(mask)) < 32:
        mask = t >= 0.45 * float(t[-1])
    tm = t[mask]
    if len(tm) < 32:
        return {"phase_metric_error": "not_enough_window_samples"}
    sample_dt = float(np.median(np.diff(t))) if len(t) > 1 else export.tstep_s
    window = max(24, int((6.0 / phys.scale_factor(phys.SCALE_PRESETS[export.scale_name])) / max(sample_dt, 1e-18)))
    window = min(window, max(24, len(tm) // 2))
    step = max(4, window // 5)
    _, z1 = base.sliding_complex(v1[mask], tm, export.source_frequency_hz, window, step)
    _, z2 = base.sliding_complex(v2[mask], tm, export.nominal_generated_frequency_hz, window, step)
    _, z3 = base.sliding_complex(v3[mask], tm, export.nominal_target_frequency_hz, window, step)
    min_len = min(len(z1), len(z2), len(z3))
    if min_len == 0:
        return {"phase_metric_error": "no_sliding_windows"}
    phase_generated = np.unwrap(2.0 * np.angle(z1[:min_len]) - np.angle(z2[:min_len]))
    wrapped_generated = (phase_generated + np.pi) % (2.0 * np.pi) - np.pi
    generated_lock = float(abs(np.mean(np.exp(1j * wrapped_generated))))
    early = t < 0.20 * drive_until
    late = (t >= 0.60 * drive_until) & (t < drive_until)
    early_amp = abs(base.complex_projection(v3[early], t[early], export.nominal_target_frequency_hz)) if int(np.sum(early)) >= 32 else 0.0
    late_amp = abs(base.complex_projection(v3[late], t[late], export.nominal_target_frequency_hz)) if int(np.sum(late)) >= 32 else 0.0
    target_coherent_growth = float(late_amp / max(early_amp, 1e-15))
    return {
        "phase_lock_generated": generated_lock,
        "target_coherent_growth": target_coherent_growth,
        "target_coherent_late_amp": float(late_amp),
        "target_coherent_early_amp": float(early_amp),
    }


def target_band_growth(row: Dict[str, float | str]) -> float:
    if base.has_target_band_component(row):
        return row_float(row, "spice_target_voltage_growth_ratio", 0.0)
    return 0.0


def coherent_leakage_score(row: Dict[str, float | str]) -> float:
    if str(row.get("execution_status")) != "ran_successfully":
        return 0.0
    if not base.target_peak_near_12(row):
        return 0.0
    lock = max(0.0, row_float(row, "phase_lock_target", 0.0))
    coherent = max(0.0, row_float(row, "target_coherent_growth", 0.0))
    bridge = max(0.0, row_float(row, "bridge_ratio_vs_direct_4plus8_reference", 0.0))
    purity = max(0.0, row_float(row, "spectral_purity_target", 0.0))
    return float(
        0.45 * min(lock / 0.50, 1.0)
        + 0.25 * min(coherent / 1.0, 1.0)
        + 0.20 * min(bridge / 0.50, 1.0)
        + 0.10 * min(purity / 0.80, 1.0)
    )


def component_stress(case: PhaseCase, export: base.SpiceExport, data: Dict[str, np.ndarray]) -> Dict[str, float | str]:
    uniform = base.uniform_resample(data, export.tstep_s)
    v1, v2, v3 = uniform["v1"], uniform["v2"], uniform["v3"]
    vdiff = max(float(np.max(np.abs(v1 - v2))), float(np.max(np.abs(v2 - v3))))
    diode_arg = min(vdiff / max(case.diode_n * VT, 1e-12), 40.0)
    peak_diode_current = float(case.diode_is * math.expm1(diode_arg))
    peak_inductor_current = 0.0
    if "i1" in uniform:
        peak_inductor_current = float(max(np.max(np.abs(uniform["i1"])), np.max(np.abs(uniform["i2"])), np.max(np.abs(uniform["i3"]))))
    params = phys.build_lc_params(config_for_case(case), phys.SCALE_PRESETS[SCALE_NAME])
    required_drive_voltage = abs(params[0].drive_voltage_peak_v)
    stress = max(required_drive_voltage / 50.0, vdiff / 50.0, peak_diode_current / 0.10, peak_inductor_current / 1.0)
    if stress < 0.5:
        label = "plausible"
    elif stress < 1.5:
        label = "aggressive"
    else:
        label = "unrealistic"
    return {
        "required_drive_voltage": required_drive_voltage,
        "peak_diode_current": peak_diode_current,
        "peak_varactor_voltage": vdiff,
        "peak_inductor_current": peak_inductor_current,
        "component_stress_score": stress,
        "component_stress_label": label,
        "passivity_flag": "True",
    }


def summarize_case(case: PhaseCase, export: base.SpiceExport, result: base.RunResult,
                   metrics: Dict[str, float | str] | None,
                   stress: Dict[str, float | str] | None) -> Dict[str, float | str]:
    variant = comp.VARIANTS[case.variant_name]
    row: Dict[str, float | str] = {
        "row_type": "component_phase_lock",
        "case_id": case.case_id,
        "seed_case_id": case.seed_case_id,
        "circuit": export.circuit_name,
        "role": export.role,
        "control_kind": case.config_kind if case.role == "control" else "",
        "sweep_focus": case.sweep_focus,
        "nonlinear_variant": case.variant_name,
        "component_family": variant.family,
        "target_detuning": case.target_detuning,
        "generated_detuning": case.generated_detuning,
        "k12_sign": case.k12_sign,
        "k23_sign": case.k23_sign,
        "coupling_strength_scale": case.coupling_strength_scale,
        "source_q_scale": case.source_q_scale,
        "generated_q_scale": case.generated_q_scale,
        "target_q_scale": case.target_q_scale,
        "trap_kind": case.trap_kind,
        "limiter_loss_scale": case.limiter_loss_scale,
        "drive_amplitude_scale": case.drive_amplitude_scale,
        "source_load_impedance_scale": case.source_load_impedance_scale,
        "solver_tolerance_profile": case.solver_profile,
        "max_timestep_profile": case.maxstep_scale,
        "netlist_path": str(export.netlist_path),
        "execution_status": result.execution_status,
        "convergence_failure_reason": "" if result.success else result.reason,
        "source_frequency_hz": export.source_frequency_hz,
        "generated_frequency_hz": export.generated_frequency_hz,
        "target_frequency_hz": export.target_frequency_hz,
        "nominal_target_frequency_hz": export.nominal_target_frequency_hz,
        "direct_8_drive_present": str(export.direct_8_drive),
        "direct_12_drive_present": str(export.direct_12_drive),
        "target_frequency_injection_present": str(export.target_frequency_injection),
        "component_realism_score": variant.base_realism_score,
    }
    if metrics:
        row.update(metrics)
        row.update({
            "target_band_growth": target_band_growth(row),
            "phase_lock_target": row.get("spice_phase_lock_target", ""),
            "spectral_purity_target": row.get("spice_spectral_purity_target", ""),
            "generated_envelope_CV": row.get("spice_generated_envelope_cv", ""),
            "target_envelope_CV": row.get("spice_target_envelope_cv", ""),
            "max_phase_jump": row.get("spice_max_phase_jump", ""),
            "near_slip_count": row.get("spice_near_slip_count", ""),
            "bridge_ratio_vs_direct_4plus8_reference": row.get("spice_bridge_ratio", ""),
            "source_fft_peak": row.get("spice_fft_peak_source_hz", ""),
            "generated_fft_peak": row.get("spice_fft_peak_generated_hz", ""),
            "target_fft_peak": row.get("spice_fft_peak_target_hz", ""),
        })
    if stress:
        row.update(stress)
    return row


def summarize_reference(export: base.SpiceExport, result: base.RunResult) -> Dict[str, float | str]:
    return {
        "row_type": "component_phase_lock_reference",
        "case_id": "direct_4plus8_ceiling_reference",
        "seed_case_id": export.circuit_name.replace("ref_direct_4plus8_phase_", ""),
        "circuit": export.circuit_name,
        "role": "ceiling_reference",
        "control_kind": "direct_4plus8_ceiling_reference",
        "nonlinear_variant": "direct_4plus8_ceiling_reference",
        "execution_status": result.execution_status,
        "convergence_failure_reason": "" if result.success else result.reason,
        "direct_8_drive_present": str(export.direct_8_drive),
        "direct_12_drive_present": str(export.direct_12_drive),
        "target_frequency_injection_present": str(export.target_frequency_injection),
        "promotion_category": "ceiling_reference_not_discovery",
    }


def promotion_category(row: Dict[str, float | str], controls_dead: bool, controls_mostly_clean: bool) -> str:
    if str(row.get("role")) == "control":
        return "control_dead" if coherent_leakage_score(row) < 0.10 else "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "ran_successfully":
        return "not_promoted"
    if str(row.get("direct_8_drive_present")) != "False" or str(row.get("direct_12_drive_present")) != "False":
        return "not_promoted"
    if str(row.get("target_frequency_injection_present")) != "False":
        return "not_promoted"
    bridge = row_float(row, "bridge_ratio_vs_direct_4plus8_reference", 0.0)
    lock = row_float(row, "phase_lock_target", 0.0)
    purity = row_float(row, "spectral_purity_target", 0.0)
    coherent = row_float(row, "target_coherent_growth", 0.0)
    cv = row_float(row, "generated_envelope_CV", 999.0)
    jump = row_float(row, "max_phase_jump", 999.0)
    stress = row_float(row, "component_stress_score", 0.0)
    if not controls_dead and lock > 0.50 and coherent > 1.0:
        return "reject_due_to_control_leakage"
    if bridge > 1.5 and lock < 0.50:
        return "reject_due_to_phase_incoherence"
    if bridge > 1.5 and lock > 0.90 and purity > 0.80 and coherent > 1.0 and cv < 0.25 and jump < 1.0 and controls_dead and stress <= 1.5:
        return "spice_component_phase_candidate"
    if bridge > 1.0 and lock > 0.50 and purity > 0.80 and controls_mostly_clean:
        return "spice_component_phase_near_miss"
    return "not_promoted"


def aggregate(rows: List[Dict[str, float | str]]) -> Dict[str, float | str]:
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    controls = [r for r in rows if str(r.get("role")) == "control"]
    leakage_by_kind: Dict[str, float] = {}
    for kind in ("linear_no_nonlinearity_control", "weak_nonlinearity_control", "detuned_target_control", "shuffled_frequency_control", "source_off_resonance_control"):
        relevant = [r for r in controls if str(r.get("control_kind")) == kind]
        leakage_by_kind[kind] = max((coherent_leakage_score(r) for r in relevant), default=0.0)
    max_leakage = max(leakage_by_kind.values(), default=0.0)
    controls_dead = max_leakage < 0.10
    controls_mostly_clean = max_leakage < 0.25
    for row in rows:
        row["linear_control_leakage_score"] = leakage_by_kind["linear_no_nonlinearity_control"]
        row["weak_nonlinearity_leakage_score"] = leakage_by_kind["weak_nonlinearity_control"]
        row["detuned_control_leakage_score"] = leakage_by_kind["detuned_target_control"]
        row["shuffled_control_leakage_score"] = leakage_by_kind["shuffled_frequency_control"]
        row["off_resonance_control_leakage_score"] = leakage_by_kind["source_off_resonance_control"]
        row["promotion_category"] = promotion_category(row, controls_dead, controls_mostly_clean)
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    failures = [r for r in rows if str(r.get("execution_status")) == "failed_to_converge"]
    bridge_crossers = [r for r in successful if row_float(r, "bridge_ratio_vs_direct_4plus8_reference", 0.0) > 1.5]
    lock_gt_05 = [r for r in successful if row_float(r, "phase_lock_target", 0.0) > 0.50]
    lock_gt_09 = [r for r in successful if row_float(r, "phase_lock_target", 0.0) > 0.90]
    candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_component_phase_candidate"]
    near = [r for r in discovery if str(r.get("promotion_category")) == "spice_component_phase_near_miss"]
    closest = max(successful, key=lambda r: row_float(r, "phase_lock_target", -1.0), default={})
    best_bridge_lock = max(
        successful,
        key=lambda r: (
            min(row_float(r, "bridge_ratio_vs_direct_4plus8_reference", 0.0) / 1.5, 1.5)
            + row_float(r, "phase_lock_target", 0.0)
        ),
        default={},
    )
    mechanism_scores: Dict[str, float] = {}
    for focus in sorted({str(r.get("sweep_focus")) for r in successful}):
        focus_rows = [r for r in successful if str(r.get("sweep_focus")) == focus]
        mechanism_scores[focus] = max((row_float(r, "phase_lock_target", 0.0) for r in focus_rows), default=0.0)
    best_mechanism = max(mechanism_scores, key=mechanism_scores.get) if mechanism_scores else ""
    if candidates:
        next_step = "physical parameter refinement around phase-locked component candidates, then spatial phase-matching model"
    elif near or lock_gt_05:
        next_step = "deeper component sweep around phase near misses plus spatial phase-matching model"
    else:
        next_step = "spatial phase-matching model or reject current component topology before deeper sweeps"
    return {
        "row_type": "aggregate",
        "discovery_cases_run": len(discovery),
        "successful_discovery_cases": len(successful),
        "failed_to_converge_cases": len(failures),
        "bridge_ratio_gt_1p5_found": str(bool(bridge_crossers)),
        "bridge_ratio_gt_1p5_cases": ";".join(str(r.get("case_id")) for r in bridge_crossers),
        "phase_lock_gt_0p50_found": str(bool(lock_gt_05)),
        "phase_lock_gt_0p50_cases": ";".join(str(r.get("case_id")) for r in lock_gt_05),
        "phase_lock_gt_0p90_found": str(bool(lock_gt_09)),
        "phase_lock_gt_0p90_cases": ";".join(str(r.get("case_id")) for r in lock_gt_09),
        "component_phase_candidate_count": len(candidates),
        "component_phase_near_miss_count": len(near),
        "controls_dead_under_coherent_growth": str(controls_dead),
        "controls_mostly_clean_under_coherent_growth": str(controls_mostly_clean),
        "max_coherent_control_leakage_score": max_leakage,
        "linear_control_leakage_score": leakage_by_kind["linear_no_nonlinearity_control"],
        "weak_nonlinearity_leakage_score": leakage_by_kind["weak_nonlinearity_control"],
        "detuned_control_leakage_score": leakage_by_kind["detuned_target_control"],
        "shuffled_control_leakage_score": leakage_by_kind["shuffled_frequency_control"],
        "off_resonance_control_leakage_score": leakage_by_kind["source_off_resonance_control"],
        "best_phase_lock_case": str(closest.get("case_id", "")),
        "best_phase_lock_variant": str(closest.get("nonlinear_variant", "")),
        "best_phase_lock_value": closest.get("phase_lock_target", ""),
        "best_bridge_lock_case": str(best_bridge_lock.get("case_id", "")),
        "best_bridge_lock_variant": str(best_bridge_lock.get("nonlinear_variant", "")),
        "best_bridge_lock_phase_lock": best_bridge_lock.get("phase_lock_target", ""),
        "best_bridge_lock_bridge_ratio": best_bridge_lock.get("bridge_ratio_vs_direct_4plus8_reference", ""),
        "best_mechanism_by_phase_lock": best_mechanism,
        "mechanism_phase_lock_scores": json.dumps(mechanism_scores, sort_keys=True),
        "failed_convergence_cases": ";".join(str(r.get("case_id")) for r in failures),
        "recommended_next_step": next_step,
    }


def downsample_timeseries(circuit: str, case: PhaseCase, data: Dict[str, np.ndarray], limit: int) -> List[Dict[str, float | str]]:
    if limit <= 0:
        return []
    n = len(data["time"])
    if n == 0:
        return []
    indices = np.unique(np.linspace(0, n - 1, min(limit, n), dtype=int))
    rows: List[Dict[str, float | str]] = []
    for idx in indices:
        row: Dict[str, float | str] = {
            "row_type": "component_phase_lock_timeseries",
            "circuit": circuit,
            "case_id": case.case_id,
            "seed_case_id": case.seed_case_id,
            "role": case.role,
            "sweep_focus": case.sweep_focus,
            "nonlinear_variant": case.variant_name,
            "time_s": float(data["time"][idx]),
            "v_source": float(data["v1"][idx]),
            "v_generated": float(data["v2"][idx]),
            "v_target": float(data["v3"][idx]),
        }
        if "i1" in data and "i2" in data and "i3" in data:
            row.update({
                "i_source": float(data["i1"][idx]),
                "i_generated": float(data["i2"][idx]),
                "i_target": float(data["i3"][idx]),
            })
        rows.append(row)
    return rows


def write_report(out_dir: Path, summary: Dict[str, float | str], rows: List[Dict[str, float | str]]) -> None:
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    top = sorted(
        successful,
        key=lambda r: (
            -row_float(r, "phase_lock_target", 0.0),
            -row_float(r, "bridge_ratio_vs_direct_4plus8_reference", 0.0),
        ),
    )[:12]
    failures = [r for r in rows if str(r.get("execution_status")) == "failed_to_converge"]
    lines = [
        "# SPICE 4->8->12 Component Phase Lock",
        "",
        "Focused phase-lock refinement around component-realism bridge-ratio crossing rows.",
        "",
        "## Direct Answers",
        "",
        f"1. Can any component-plausible row keep bridge ratio >1.5 while raising phase lock? {summary['bridge_ratio_gt_1p5_found']}; best bridge-lock case={summary['best_bridge_lock_case']}, lock={summary['best_bridge_lock_phase_lock']}, bridge={summary['best_bridge_lock_bridge_ratio']}.",
        f"2. Did any row reach phase lock >0.50? {summary['phase_lock_gt_0p50_found']}; cases={summary['phase_lock_gt_0p50_cases']}.",
        f"3. Did any row reach phase lock >0.90? {summary['phase_lock_gt_0p90_found']}; cases={summary['phase_lock_gt_0p90_cases']}.",
        f"4. Did weak-nonlinearity and detuned controls stop leaking under coherent-growth criteria? weak={summary['weak_nonlinearity_leakage_score']}, detuned={summary['detuned_control_leakage_score']}, all_controls_dead={summary['controls_dead_under_coherent_growth']}.",
        f"5. Which mechanism helps most? {summary['best_mechanism_by_phase_lock']}; scores={summary['mechanism_phase_lock_scores']}.",
        f"6. Next step: {summary['recommended_next_step']}.",
        "",
        "## Top Phase-Lock Rows",
        "",
    ]
    for row in top:
        lines.append(
            f"- {row['case_id']} seed={row['seed_case_id']} {row['nonlinear_variant']} focus={row['sweep_focus']}: "
            f"status={row['execution_status']}, lock={row.get('phase_lock_target', '')}, "
            f"generated_lock={row.get('phase_lock_generated', '')}, bridge={row.get('bridge_ratio_vs_direct_4plus8_reference', '')}, "
            f"purity={row.get('spectral_purity_target', '')}, coherent_growth={row.get('target_coherent_growth', '')}, "
            f"category={row.get('promotion_category', '')}."
        )
    lines.extend(["", "## Convergence Failures", ""])
    if failures:
        for row in failures:
            lines.append(f"- {row['case_id']} {row.get('nonlinear_variant', '')}: {row.get('convergence_failure_reason', '')}")
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Notes",
        "",
        "- Discovery rows remain source-only and component-plausible; behavioral current mixing is not used.",
        "- Direct 4+8 references are separated ceiling denominators grouped by seed row.",
        "- Control leakage is scored on coherent target-band build-up, not raw target-band amplitude alone.",
    ])
    (out_dir / "README_SPICE_412_COMPONENT_PHASE_LOCK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_or_skip(export: base.SpiceExport, args: argparse.Namespace, ngspice_path: str | None,
                ngspice_resolution_error: str) -> Tuple[base.RunResult, Dict[str, np.ndarray] | None]:
    if args.export_only:
        return base.RunResult("exported", False, "export only"), None
    if not ngspice_path:
        return base.RunResult("skipped_no_ngspice", False, ngspice_resolution_error or "ngspice not found"), None
    result = base.run_ngspice(export, ngspice_path, args.timeout)
    if not result.success:
        return result, None
    try:
        return result, base.read_ngspice_csv(export.csv_path)
    except Exception as exc:
        return base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path), None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run component phase-lock ngspice refinement for the 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--ngspice-path", default="wsl:ngspice")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-cases", type=int, default=84)
    parser.add_argument("--timeseries-samples", type=int, default=80)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    cases = focused_cases(args.max_cases)
    ngspice_path = None
    ngspice_resolution_error = ""
    if not args.export_only:
        try:
            ngspice_path = base.resolve_ngspice_path(args.ngspice_path)
        except Exception as exc:  # pragma: no cover - local simulator discovery varies.
            ngspice_resolution_error = f"{type(exc).__name__}: {exc}"
    ngspice_available = ngspice_path is not None

    ref_data: Dict[str, Dict[str, np.ndarray]] = {}
    ref_exports: Dict[str, base.SpiceExport] = {}
    ref_results: Dict[str, base.RunResult] = {}
    seeds = seed_component_cases()
    for seed_id in sorted({case.reference_key for case in cases}):
        pseudo = make_phase_case(seeds[seed_id], "ref", "direct_4plus8_reference")
        export = export_netlist(out_dir, pseudo, reference=True)
        ref_exports[seed_id] = export
        result, data = run_or_skip(export, args, ngspice_path, ngspice_resolution_error)
        ref_results[seed_id] = result
        if result.success and data is not None:
            ref_data[seed_id] = data

    rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    for case in cases:
        export = export_netlist(out_dir, case, reference=False)
        result, data = run_or_skip(export, args, ngspice_path, ngspice_resolution_error)
        metrics = None
        stress = None
        if result.success and data is not None:
            try:
                metrics, phase_rows = base.spice_metrics(export, data, ref_data.get(case.reference_key))
                metrics.update(extra_phase_metrics(export, data))
                stress = component_stress(case, export, data)
                timeseries_rows.extend(downsample_timeseries(export.circuit_name, case, data, args.timeseries_samples))
                for phase_row in phase_rows:
                    phase_row["case_id"] = case.case_id
                    phase_row["seed_case_id"] = case.seed_case_id
                    phase_row["row_type"] = "component_phase_lock_phase_window"
                timeseries_rows.extend(phase_rows)
            except Exception as exc:
                result = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
        rows.append(summarize_case(case, export, result, metrics, stress))

    summary = aggregate(rows)
    reference_rows = [summarize_reference(ref_exports[key], ref_results[key]) for key in sorted(ref_exports)]
    all_rows = [summary] + reference_rows + rows
    write_csv(out_dir / "spice_412_component_phase_lock_summary.csv", all_rows)
    if timeseries_rows:
        write_csv(out_dir / "spice_412_component_phase_lock_timeseries.csv", timeseries_rows)
    write_report(out_dir, summary, reference_rows + rows)
    (out_dir / "spice_412_component_phase_lock_summary.json").write_text(json.dumps({
        "aggregate": summary,
        "rows": all_rows,
        "seed_case_ids": SEED_CASE_IDS,
        "sweep_axes": {
            "target_resonator_detuning": TARGET_DETUNINGS,
            "generated_resonator_detuning": GENERATED_DETUNINGS,
            "coupling_orientation": COUPLING_ORIENTATIONS,
            "coupling_strength": COUPLING_STRENGTHS,
            "source_q_scale": SOURCE_Q_SCALES,
            "generated_q_scale": GENERATED_Q_SCALES,
            "target_q_scale": TARGET_Q_SCALES,
            "trap_kind": TRAP_KINDS,
            "limiter_loss_scale": LIMITER_LOSS_SCALES,
        },
        "variants": {name: asdict(variant) for name, variant in comp.VARIANTS.items()},
        "references": [{
            "seed_case_id": key,
            "circuit": export.circuit_name,
            "execution_status": ref_results[key].execution_status,
            "reason": ref_results[key].reason,
        } for key, export in ref_exports.items()],
        "ngspice_available": ngspice_available,
        "ngspice_path": ngspice_path or "",
        "ngspice_resolution_error": ngspice_resolution_error,
    }, indent=2), encoding="utf-8")

    print(f"SPICE 4->8->12 component phase-lock refinement written to: {out_dir.resolve()}")
    print(f"ngspice_available={ngspice_available}")
    print(f"discovery_cases_run={summary['discovery_cases_run']}")
    print(f"successful_discovery_cases={summary['successful_discovery_cases']}")
    print(f"component_phase_candidate_count={summary['component_phase_candidate_count']}")
    print(f"component_phase_near_miss_count={summary['component_phase_near_miss_count']}")
    print(f"phase_lock_gt_0p50_found={summary['phase_lock_gt_0p50_found']}")
    print(f"controls_dead_under_coherent_growth={summary['controls_dead_under_coherent_growth']}")


if __name__ == "__main__":
    main()
