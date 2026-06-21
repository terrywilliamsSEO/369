"""Focused ngspice nonlinear-refinement sweep for the 4->8->12 LC bridge.

This script refines the SPICE physicalization after the first ngspice run.  It
keeps discovery rows source-only and uses direct 4+8 rows only as separated
ceiling/reference denominators.
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
import spice_412_export as base


OUT_DIR = Path("runs") / "spice_412_refine_nonlinearity"
SCALE_NAME = "arbitrary-normalized-scale"
NONLINEAR_STRENGTH_SCALES = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
LIMITER_CONDUCTANCE_SCALES = (0.25, 0.5, 1.0, 2.0, 4.0)
COUPLING_SCALES = (0.5, 0.75, 1.0, 1.25, 1.5)
DRIVE_AMPLITUDE_SCALES = (0.5, 1.0, 1.5, 2.0)
MAXSTEP_SCALES = (0.5, 1.0, 2.0)
PYTHON_LC = base.PYTHON_BASELINE

SOLVER_PROFILES: Dict[str, str] = {
    "conservative": "method=gear reltol=1e-6 abstol=1e-13 vntol=1e-9 chgtol=1e-16 maxord=2",
    "default": "method=gear reltol=1e-5 abstol=1e-12 vntol=1e-8 maxord=2",
    "relaxed": "method=gear reltol=5e-5 abstol=1e-10 vntol=1e-6 chgtol=1e-14 maxord=2",
}


@dataclass(frozen=True)
class RefineVariant:
    name: str
    short: str
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
class SweepCase:
    case_id: str
    variant_name: str
    nonlinear_strength_scale: float
    limiter_conductance_scale: float
    coupling_scale: float
    drive_amplitude_scale: float
    solver_profile: str
    maxstep_scale: float
    priority: int
    scale_name: str = SCALE_NAME

    @property
    def reference_key(self) -> Tuple[float, float, float, float, str, float]:
        return (
            self.nonlinear_strength_scale,
            self.limiter_conductance_scale,
            self.coupling_scale,
            self.drive_amplitude_scale,
            self.solver_profile,
            self.maxstep_scale,
        )


VARIANTS: Dict[str, RefineVariant] = {
    "behavioral_proxy_current": RefineVariant(
        name="behavioral_proxy_current",
        short="beh",
        description="Behavioral current mixer plus voltage-dependent capacitance proxy.",
        realism_label="aggressive behavioral proxy",
        realism_score=0.52,
        include_behavioral_mix=True,
        include_vdep_cap=True,
        include_soft_limiter=True,
    ),
    "voltage_dependent_capacitance_proxy": RefineVariant(
        name="voltage_dependent_capacitance_proxy",
        short="vcap",
        description="Voltage-dependent capacitance cross-terms without explicit sum-frequency current injection.",
        realism_label="aggressive but component-adjacent",
        realism_score=0.62,
        include_vdep_cap=True,
        include_soft_limiter=True,
    ),
    "diode_pair_proxy": RefineVariant(
        name="diode_pair_proxy",
        short="dpair",
        description="Anti-parallel diode-pair nonlinear coupling proxy.",
        realism_label="physically plausible component proxy, likely weak",
        realism_score=0.74,
        include_diode_pair=True,
        include_soft_limiter=True,
    ),
    "varactor_diode_model_proxy": RefineVariant(
        name="varactor_diode_model_proxy",
        short="vdiode",
        description="Junction-capacitance varactor-diode proxy between adjacent resonators.",
        realism_label="plausible but parameter-sensitive",
        realism_score=0.70,
        include_varactor_diode=True,
        include_soft_limiter=True,
    ),
    "saturable_inductor_proxy": RefineVariant(
        name="saturable_inductor_proxy",
        short="sat",
        description="Cubic restoring-current proxy for saturable magnetic branches.",
        realism_label="aggressive magnetic saturation proxy",
        realism_score=0.58,
        include_saturable_inductor=True,
        include_soft_limiter=True,
    ),
    "hybrid_varactor_plus_saturable_inductor": RefineVariant(
        name="hybrid_varactor_plus_saturable_inductor",
        short="hybrid",
        description="Component-adjacent hybrid of varactor diode coupling and saturable magnetic branches.",
        realism_label="component-plausible hybrid proxy, still parameter-sensitive",
        realism_score=0.66,
        include_varactor_diode=True,
        include_saturable_inductor=True,
        include_soft_limiter=True,
    ),
    "linear_no_nonlinearity_control": RefineVariant(
        name="linear_no_nonlinearity_control",
        short="linear",
        description="Linear LC and weak coupling only; should stay dead at the target band.",
        realism_label="linear control",
        realism_score=1.0,
    ),
}

COMPONENT_VARIANTS = {
    "diode_pair_proxy",
    "varactor_diode_model_proxy",
    "saturable_inductor_proxy",
    "hybrid_varactor_plus_saturable_inductor",
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


def token(value: float) -> str:
    text = f"{value:g}".replace(".", "p").replace("-", "m")
    return text


def case_name(case: SweepCase) -> str:
    variant = VARIANTS[case.variant_name]
    return (
        f"{case.case_id}_{variant.short}_ns{token(case.nonlinear_strength_scale)}"
        f"_lim{token(case.limiter_conductance_scale)}"
        f"_k{token(case.coupling_scale)}_drv{token(case.drive_amplitude_scale)}"
        f"_{case.solver_profile}_m{token(case.maxstep_scale)}"
    )


def reference_name(key: Tuple[float, float, float, float, str, float]) -> str:
    ns, lim, k, drv, solver, maxstep = key
    return (
        f"ref_direct_4plus8_ns{token(ns)}_lim{token(lim)}"
        f"_k{token(k)}_drv{token(drv)}_{solver}_m{token(maxstep)}"
    )


def scaled_config(case: SweepCase, reference: bool = False) -> phys.BridgeConfig:
    source = phys.DIRECT_REFERENCE if reference else phys.CANDIDATE
    return replace(
        source,
        stage_a_nonlinear_strength=source.stage_a_nonlinear_strength * case.nonlinear_strength_scale,
        stage_b_nonlinear_strength=source.stage_b_nonlinear_strength * case.nonlinear_strength_scale,
        stage_a_to_stage_b_coupling=source.stage_a_to_stage_b_coupling * case.coupling_scale,
        stage_b_to_receiver_coupling=source.stage_b_to_receiver_coupling * case.coupling_scale,
        drive_amp=source.drive_amp * case.drive_amplitude_scale,
        varactor_coefficient=source.varactor_coefficient * case.nonlinear_strength_scale,
        spark_strength=source.spark_strength * case.limiter_conductance_scale,
    )


def nonlinear_mix_coefficients(scale_name: str, config: phys.BridgeConfig, strength_scale: float) -> Dict[str, float]:
    values = base.nonlinear_mix_coefficients(scale_name, config)
    return {key: value * strength_scale for key, value in values.items()}


def soft_limiter_params(scale_name: str, config: phys.BridgeConfig, limiter_scale: float) -> Dict[str, float]:
    values = base.soft_limiter_params(scale_name, config)
    return {
        **values,
        "gsoft12": values["gsoft12"] * limiter_scale,
        "gsoft23": values["gsoft23"] * limiter_scale,
    }


def variant_lines(scale_name: str, config: phys.BridgeConfig, variant: RefineVariant, case: SweepCase) -> List[str]:
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[scale_name])
    mix = nonlinear_mix_coefficients(scale_name, config, case.nonlinear_strength_scale)
    limiter = soft_limiter_params(scale_name, config, case.limiter_conductance_scale)
    c = [p.capacitance_f for p in params]
    vscale = [p.voltage_scale_v for p in params]
    lines: List[str] = [
        "",
        f"* Nonlinear refinement variant: {variant.name}",
        f"* {variant.description}",
        f"* nonlinear_strength_scale={base.spice_num(case.nonlinear_strength_scale)}",
        f"* limiter_conductance_scale={base.spice_num(case.limiter_conductance_scale)}",
    ]
    if variant.include_vdep_cap:
        lines.append("* Voltage-dependent capacitance terms.")
        for idx, p_lc in enumerate(params, start=1):
            beta = p_lc.varactor_beta_per_v2 * case.nonlinear_strength_scale
            lines.append(f".param beta{idx}={base.spice_num(beta)}")
            lines.append(f"Bvar{idx} n{idx} 0 I={{c{idx}*beta{idx}*V(n{idx})*V(n{idx})*ddt(V(n{idx}))}}")
        bx12 = case.nonlinear_strength_scale * 0.15 * abs(mix["mixa_00_to_2"]) / max(c[1], 1e-30)
        bx23 = case.nonlinear_strength_scale * 0.08 * abs(mix["mixb_01_to_3"]) / max(c[2], 1e-30)
        lines.extend([
            f".param betax12={base.spice_num(bx12)}",
            f".param betax23={base.spice_num(bx23)}",
            "Bxcap12 n2 0 I={c2*betax12*V(n1)*V(n1)*ddt(V(n2))}",
            "Bxcap23 n3 0 I={c3*betax23*V(n2)*V(n2)*ddt(V(n3))}",
        ])
    if variant.include_behavioral_mix:
        lines.extend([
            "* Explicit behavioral nonlinear mixing currents.",
            f".param mixa_01_to_1={base.spice_num(mix['mixa_01_to_1'])}",
            f".param mixa_00_to_2={base.spice_num(mix['mixa_00_to_2'])}",
            f".param mixb_12_to_1={base.spice_num(mix['mixb_12_to_1'])}",
            f".param mixb_02_to_2={base.spice_num(mix['mixb_02_to_2'])}",
            f".param mixb_01_to_3={base.spice_num(mix['mixb_01_to_3'])}",
            "Bmix1 n1 0 I={-(mixa_01_to_1*V(n1)*V(n2) + mixb_12_to_1*V(n2)*V(n3))}",
            "Bmix2 n2 0 I={-(mixa_00_to_2*V(n1)*V(n1) + mixb_02_to_2*V(n1)*V(n3))}",
            "Bmix3 n3 0 I={-(mixb_01_to_3*V(n1)*V(n2))}",
        ])
    if variant.include_diode_pair:
        rs = max(0.05, 0.05 * math.sqrt(params[0].resistance_ohm * params[1].resistance_ohm))
        cjo = case.nonlinear_strength_scale * 0.002 * min(c)
        lines.extend([
            "* Anti-parallel diode-pair nonlinear coupling proxy.",
            f".model DPAIR D(Is={base.spice_num(1e-12 * case.nonlinear_strength_scale)} N=1.7 Rs={base.spice_num(rs)} Cjo={base.spice_num(cjo)} Vj=0.25 M=0.45)",
            "Dpair12a n1 n2 DPAIR",
            "Dpair12b n2 n1 DPAIR",
            "Dpair23a n2 n3 DPAIR",
            "Dpair23b n3 n2 DPAIR",
        ])
    if variant.include_varactor_diode:
        cjo = case.nonlinear_strength_scale * 0.015 * min(c)
        lines.extend([
            "* Junction-capacitance varactor-diode proxy between adjacent resonators.",
            f".model DVAR D(Is={base.spice_num(1e-14)} N=1.2 Rs=0.5 Cjo={base.spice_num(cjo)} Vj=1.0 M=0.5 Fc=0.5)",
            "Dvar12a n1 n2 DVAR",
            "Dvar12b n2 n1 DVAR",
            "Dvar23a n2 n3 DVAR",
            "Dvar23b n3 n2 DVAR",
        ])
    if variant.include_saturable_inductor:
        for idx, p_lc in enumerate(params, start=1):
            ksat = (
                case.nonlinear_strength_scale
                * 0.012
                * c[idx - 1]
                * (2.0 * math.pi * p_lc.frequency_hz) ** 2
                / max(vscale[idx - 1] ** 2, 1e-30)
            )
            lines.append(f".param ksat{idx}={base.spice_num(ksat)}")
        lines.extend([
            "* Cubic restoring-current proxy for saturable magnetic branches.",
            "Bsat1 n1 0 I={ksat1*V(n1)*V(n1)*V(n1)}",
            "Bsat2 n2 0 I={ksat2*V(n2)*V(n2)*V(n2)}",
            "Bsat3 n3 0 I={ksat3*V(n3)*V(n3)*V(n3)}",
        ])
    if variant.include_soft_limiter:
        lines.extend([
            "* Passive soft limiter / loss proxy.",
            f".param gsoft12={base.spice_num(limiter['gsoft12'])}",
            f".param gsoft23={base.spice_num(limiter['gsoft23'])}",
            f".param vlim12={base.spice_num(limiter['vlim12'])}",
            f".param vlim23={base.spice_num(limiter['vlim23'])}",
            "Bsoft12 n1 n2 I={gsoft12*V(n1,n2)*0.5*(1+tanh((abs(V(n1,n2))-vlim12)/(0.3*vlim12+1e-30)))}",
            "Bsoft23 n2 n3 I={gsoft23*V(n2,n3)*0.5*(1+tanh((abs(V(n2,n3))-vlim23)/(0.3*vlim23+1e-30)))}",
        ])
    if variant.name == "linear_no_nonlinearity_control":
        lines.append("* Linear control: no nonlinear capacitance, diode, saturable, limiter, or behavioral mixing elements.")
    return lines


def export_case_netlist(out_dir: Path, case: SweepCase, reference: bool = False) -> base.SpiceExport:
    config = scaled_config(case, reference=reference)
    scale_name = case.scale_name
    variant = VARIANTS["behavioral_proxy_current"] if reference else VARIANTS[case.variant_name]
    role = "ceiling_reference" if reference else "discovery"
    circuit_name = reference_name(case.reference_key) if reference else case_name(case)
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[scale_name])
    coupling = phys.coupling_summary(config)
    flags = base.direct_drive_flags(config)
    tstop, tstep, drive_until, ramp = base.physical_timing(scale_name)
    maxstep = tstep * case.maxstep_scale
    hold_time = max(ramp, drive_until - ramp)
    netlist_path = out_dir / f"{circuit_name}.cir"
    csv_path = out_dir / f"{circuit_name}_tran.csv"
    raw_path = out_dir / f"{circuit_name}.raw"

    drive_lines: List[str] = []
    drive_count = max(1, len(config.drive_freqs))
    for drive_idx, (freq_ratio, mode_idx) in enumerate(zip(config.drive_freqs, config.drive_modes), start=1):
        node = f"n{mode_idx + 1}"
        drive_frequency = phys.BASE_HZ * freq_ratio * phys.scale_factor(phys.SCALE_PRESETS[scale_name])
        amp = base.drive_current_for_mode(scale_name, config, mode_idx, drive_count)
        role_note = "source-only discovery drive" if role == "discovery" else "direct reference drive"
        drive_lines.extend([
            f"* {role_note}: mode {mode_idx + 1}, f={base.spice_num(drive_frequency)} Hz",
            f".param idrive{drive_idx}={base.spice_num(amp)}",
            f".param fdrive{drive_idx}={base.spice_num(drive_frequency)}",
            f"Bdrive{drive_idx} {node} 0 I={{-idrive{drive_idx}*V(env)*sin(2*pi*fdrive{drive_idx}*time)}}",
        ])

    lines = [
        f"* {circuit_name}: refined physical 4->8->12 nonlinear LC bridge",
        f"* scale={scale_name}; role={role}; nonlinear_variant={variant.name}",
        "* Generated by spice_412_refine_nonlinearity.py.",
        "* Discovery rule: no direct generated/target drive and no target-frequency injection.",
        "* Direct 4+8 files are separated ceiling/reference denominators only.",
        f".option {SOLVER_PROFILES[case.solver_profile]}",
        ".param pi=3.141592653589793",
        f".param tstop={base.spice_num(tstop)}",
        f".param tstep={base.spice_num(tstep)}",
        f".param maxstep={base.spice_num(maxstep)}",
        f".param drive_until={base.spice_num(drive_until)}",
        f".param drive_ramp={base.spice_num(ramp)}",
        f".param nonlinear_strength_scale={base.spice_num(case.nonlinear_strength_scale)}",
        f".param limiter_conductance_scale={base.spice_num(case.limiter_conductance_scale)}",
        f".param coupling_scale={base.spice_num(case.coupling_scale)}",
        f".param drive_amplitude_scale={base.spice_num(case.drive_amplitude_scale)}",
        "",
        "* Drive envelope.",
        f"Venv env 0 PWL(0 0 {base.spice_num(ramp)} 1 {base.spice_num(hold_time)} 1 {base.spice_num(drive_until)} 0 {base.spice_num(tstop)} 0)",
        "",
        "* Three lossy LC resonators.",
    ]
    for idx, p_lc in enumerate(params, start=1):
        lines.extend([
            f".param c{idx}={base.spice_num(p_lc.capacitance_f)}",
            f".param l{idx}={base.spice_num(p_lc.inductance_h)}",
            f".param r{idx}={base.spice_num(p_lc.resistance_ohm)}",
            f"C{idx} n{idx} 0 {{c{idx}}}",
            f"R{idx} n{idx} n{idx}l {{r{idx}}}",
            f"L{idx} n{idx}l 0 {{l{idx}}} IC=0",
        ])
    lines.extend([
        "",
        "* Weak linear coupling.",
        f"K12 L1 L2 {base.spice_num(float(coupling['linear_k01_fraction_of_omega_product']))}",
        f"K23 L2 L3 {base.spice_num(float(coupling['linear_k12_fraction_of_omega_product']))}",
    ])
    lines.extend(variant_lines(scale_name, config, variant, case))
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


def add_case(cases: Dict[Tuple[str, float, float, float, float, str, float], SweepCase],
             variant_name: str, ns: float, lim: float, k: float, drv: float,
             solver: str, maxstep: float, priority: int) -> None:
    key = (variant_name, ns, lim, k, drv, solver, maxstep)
    if key not in cases:
        cases[key] = SweepCase(
            case_id=f"r{len(cases) + 1:03d}",
            variant_name=variant_name,
            nonlinear_strength_scale=ns,
            limiter_conductance_scale=lim,
            coupling_scale=k,
            drive_amplitude_scale=drv,
            solver_profile=solver,
            maxstep_scale=maxstep,
            priority=priority,
        )


def focused_cases(max_discovery_cases: int) -> List[SweepCase]:
    cases: Dict[Tuple[str, float, float, float, float, str, float], SweepCase] = {}
    for variant_name in VARIANTS:
        add_case(cases, variant_name, 1.0, 1.0, 1.0, 1.0, "default", 1.0, 0)
    for variant_name in VARIANTS:
        if variant_name == "linear_no_nonlinearity_control":
            for drv in DRIVE_AMPLITUDE_SCALES:
                add_case(cases, variant_name, 1.0, 1.0, 1.0, drv, "default", 1.0, 1)
            add_case(cases, variant_name, 1.0, 1.0, 1.5, 2.0, "relaxed", 2.0, 2)
            continue
        for ns, lim, k, drv, solver, maxstep in (
            (2.0, 1.0, 1.25, 1.5, "default", 1.0),
            (4.0, 1.0, 1.25, 1.5, "default", 1.0),
            (8.0, 0.5, 1.25, 2.0, "relaxed", 2.0),
            (2.0, 0.5, 1.5, 1.5, "default", 1.0),
        ):
            add_case(cases, variant_name, ns, lim, k, drv, solver, maxstep, 1)
    for variant_name in ("behavioral_proxy_current", "hybrid_varactor_plus_saturable_inductor"):
        for ns in NONLINEAR_STRENGTH_SCALES:
            add_case(cases, variant_name, ns, 1.0, 1.25, 1.5, "default", 1.0, 2)
        for lim in LIMITER_CONDUCTANCE_SCALES:
            add_case(cases, variant_name, 2.0, lim, 1.25, 1.5, "default", 1.0, 2)
        for k in COUPLING_SCALES:
            add_case(cases, variant_name, 2.0, 1.0, k, 1.5, "default", 1.0, 2)
        for drv in DRIVE_AMPLITUDE_SCALES:
            add_case(cases, variant_name, 2.0, 1.0, 1.25, drv, "default", 1.0, 2)
        for solver in SOLVER_PROFILES:
            add_case(cases, variant_name, 2.0, 1.0, 1.25, 1.5, solver, 1.0, 2)
        for maxstep in MAXSTEP_SCALES:
            add_case(cases, variant_name, 2.0, 1.0, 1.25, 1.5, "relaxed", maxstep, 2)
    ordered = sorted(cases.values(), key=lambda c: (c.priority, c.case_id))
    return ordered[:max_discovery_cases]


def row_float(row: Dict[str, float | str], key: str, default: float = float("nan")) -> float:
    return base.row_float(row, key, default)


def target_band_growth(row: Dict[str, float | str]) -> float:
    if base.has_target_band_component(row):
        return row_float(row, "spice_target_voltage_growth_ratio", 0.0)
    return 0.0


def leakage_score(row: Dict[str, float | str]) -> float:
    if str(row.get("execution_status")) != "ran_successfully":
        return 0.0
    bridge = max(0.0, row_float(row, "spice_bridge_ratio", 0.0))
    purity = max(0.0, row_float(row, "spice_spectral_purity_target", 0.0))
    growth = max(0.0, target_band_growth(row))
    near = 1.0 if base.target_peak_near_12(row) else 0.0
    return float(near * (0.4 * min(bridge / 1.5, 1.0) + 0.4 * min(purity / 0.8, 1.0) + 0.2 * min(growth, 1.0)))


def python_distance(row: Dict[str, float | str]) -> float:
    if str(row.get("execution_status")) != "ran_successfully":
        return float("inf")
    values = {
        "spice_phase_lock_target": (PYTHON_LC["phase_lock_target"], 0.20),
        "spice_bridge_ratio": (PYTHON_LC["bridge_ratio"], 1.0),
        "spice_spectral_purity_target": (PYTHON_LC["spectral_purity_target"], 0.25),
        "spice_generated_envelope_cv": (PYTHON_LC["generated_envelope_cv"], 0.50),
        "spice_max_phase_jump": (PYTHON_LC["max_phase_jump"], 1.0),
    }
    total = 0.0
    for key, (target, scale) in values.items():
        value = row_float(row, key)
        if not np.isfinite(value):
            return float("inf")
        total += abs(value - float(target)) / scale
    return float(total)


def promotion_category(row: Dict[str, float | str], linear_dead: bool) -> str:
    if str(row.get("nonlinear_variant")) == "linear_no_nonlinearity_control":
        return "linear_control_dead" if leakage_score(row) < 0.10 else "reject_due_to_control_leakage"
    if not linear_dead:
        return "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "ran_successfully":
        return "not_promoted"
    lock = row_float(row, "spice_phase_lock_target", 0.0)
    purity = row_float(row, "spice_spectral_purity_target", 0.0)
    bridge = row_float(row, "spice_bridge_ratio", 0.0)
    growth = target_band_growth(row)
    source_only = (
        str(row.get("direct_8_drive_present")) == "False"
        and str(row.get("direct_12_drive_present")) == "False"
        and str(row.get("target_frequency_injection_present")) == "False"
    )
    crosses = source_only and lock > 0.90 and purity > 0.80 and bridge > 1.50 and growth > 1.0
    if not crosses:
        return "not_promoted"
    variant = str(row.get("nonlinear_variant"))
    if variant == "behavioral_proxy_current":
        return "spice_behavioral_bridge_candidate"
    if variant in COMPONENT_VARIANTS:
        return "spice_component_candidate"
    return "spice_behavioral_bridge_candidate"


def summarize_case(case: SweepCase, export: base.SpiceExport, run_result: base.RunResult,
                   metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    variant = VARIANTS[case.variant_name]
    flags = {
        "direct_8_drive_present": str(export.direct_8_drive),
        "direct_12_drive_present": str(export.direct_12_drive),
        "target_frequency_injection_present": str(export.target_frequency_injection),
    }
    row: Dict[str, float | str] = {
        "row_type": "spice_refine",
        "case_id": case.case_id,
        "circuit": export.circuit_name,
        "scale_preset": case.scale_name,
        "role": export.role,
        "nonlinear_variant": case.variant_name,
        "nonlinear_variant_description": variant.description,
        "nonlinear_realism_score": variant.realism_score,
        "nonlinear_realism_label": variant.realism_label,
        "nonlinear_strength_scale": case.nonlinear_strength_scale,
        "limiter_conductance_scale": case.limiter_conductance_scale,
        "coupling_scale": case.coupling_scale,
        "drive_amplitude_scale": case.drive_amplitude_scale,
        "solver_profile": case.solver_profile,
        "maxstep_scale": case.maxstep_scale,
        "netlist_path": str(export.netlist_path),
        "csv_path": str(export.csv_path) if run_result.success else "",
        "raw_path": str(export.raw_path) if run_result.success else "",
        "execution_status": run_result.execution_status,
        "convergence_failure_reason": "" if run_result.success else run_result.reason,
        "ngspice_run_message": run_result.reason,
        "source_frequency_hz": export.source_frequency_hz,
        "generated_frequency_hz": export.generated_frequency_hz,
        "target_frequency_hz": export.target_frequency_hz,
        "nominal_generated_frequency_hz": export.nominal_generated_frequency_hz,
        "nominal_target_frequency_hz": export.nominal_target_frequency_hz,
        **flags,
    }
    if metrics:
        row.update(metrics)
        row["target_band_growth"] = target_band_growth(row)
        row["source_fft_peak"] = row.get("spice_fft_peak_source_hz", "")
        row["generated_fft_peak"] = row.get("spice_fft_peak_generated_hz", "")
        row["target_fft_peak"] = row.get("spice_fft_peak_target_hz", "")
        row["phase_lock_target"] = row.get("spice_phase_lock_target", "")
        row["spectral_purity_target"] = row.get("spice_spectral_purity_target", "")
        row["generated_envelope_CV"] = row.get("spice_generated_envelope_cv", "")
        row["max_phase_jump"] = row.get("spice_max_phase_jump", "")
        row["bridge_ratio_vs_direct_4plus8_reference"] = row.get("spice_bridge_ratio", "")
        row["row_target_band_score"] = leakage_score(row)
        row["linear_control_leakage_score"] = ""
        row["python_lc_distance"] = python_distance(row)
    else:
        row["target_band_growth"] = ""
        row["row_target_band_score"] = ""
        row["linear_control_leakage_score"] = ""
        row["python_lc_distance"] = ""
    return row


def downsample_timeseries(circuit: str, case: SweepCase, data: Dict[str, np.ndarray], limit: int) -> List[Dict[str, float | str]]:
    if limit <= 0:
        return []
    n = len(data["time"])
    if n == 0:
        return []
    indices = np.unique(np.linspace(0, n - 1, min(limit, n), dtype=int))
    rows: List[Dict[str, float | str]] = []
    for idx in indices:
        row: Dict[str, float | str] = {
            "row_type": "spice_refine_timeseries",
            "circuit": circuit,
            "case_id": case.case_id,
            "nonlinear_variant": case.variant_name,
            "time_s": float(data["time"][idx]),
            "v_source": float(data["v1"][idx]),
            "v_generated": float(data["v2"][idx]),
            "v_target": float(data["v3"][idx]),
        }
        if "i1" in data:
            row.update({
                "i_source": float(data["i1"][idx]),
                "i_generated": float(data["i2"][idx]),
                "i_target": float(data["i3"][idx]),
            })
        rows.append(row)
    return rows


def aggregate_summary(rows: List[Dict[str, float | str]]) -> Dict[str, float | str]:
    discovery = [r for r in rows if str(r.get("row_type")) == "spice_refine" and str(r.get("role")) == "discovery"]
    linear_rows = [r for r in discovery if str(r.get("nonlinear_variant")) == "linear_no_nonlinearity_control"]
    max_linear_leakage = max((leakage_score(r) for r in linear_rows), default=0.0)
    linear_dead = all(
        leakage_score(r) < 0.10
        and (
            not np.isfinite(row_float(r, "spice_bridge_ratio"))
            or row_float(r, "spice_bridge_ratio", 0.0) < 0.10
        )
        for r in linear_rows
    )
    for row in discovery:
        row["linear_control_leakage_score"] = max_linear_leakage
        row["promotion_category"] = promotion_category(row, linear_dead)
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    bridge_crossers = [r for r in successful if row_float(r, "bridge_ratio_vs_direct_4plus8_reference", 0.0) > 1.5]
    behavioral_candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_behavioral_bridge_candidate"]
    component_candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_component_candidate"]
    failures = [r for r in discovery if str(r.get("execution_status")) == "failed_to_converge"]
    closest = min(successful, key=python_distance) if successful else {}
    statuses = sorted(set(str(r.get("execution_status")) for r in discovery))
    if component_candidates:
        next_step = "physical parameter sweep around the component-plausible candidates, then spatial phase-matching modeling"
    elif behavioral_candidates:
        next_step = "component-level refinement to replace behavioral mixing, then parameter sweep"
    else:
        next_step = "component-level refinement and spatial phase-matching model before wider physical parameter sweeps"
    return {
        "row_type": "aggregate",
        "scale_preset": SCALE_NAME,
        "discovery_cases_run": len(discovery),
        "successful_discovery_cases": len(successful),
        "failed_to_converge_cases": len(failures),
        "execution_statuses": ";".join(statuses),
        "bridge_ratio_gt_1p5_found": str(bool(bridge_crossers)),
        "bridge_ratio_gt_1p5_cases": ";".join(str(r.get("case_id")) for r in bridge_crossers),
        "linear_no_nonlinearity_control_remained_dead": str(linear_dead),
        "max_linear_control_leakage_score": max_linear_leakage,
        "behavioral_candidate_count": len(behavioral_candidates),
        "component_candidate_count": len(component_candidates),
        "reject_due_to_control_leakage": str(not linear_dead),
        "closest_python_lc_case": str(closest.get("case_id", "")),
        "closest_python_lc_variant": str(closest.get("nonlinear_variant", "")),
        "closest_python_lc_distance": python_distance(closest) if closest else "",
        "closest_python_lc_bridge_ratio": closest.get("bridge_ratio_vs_direct_4plus8_reference", ""),
        "closest_python_lc_lock": closest.get("phase_lock_target", ""),
        "closest_python_lc_purity": closest.get("spectral_purity_target", ""),
        "successful_variants_are": (
            "component-plausible" if component_candidates else
            "behavioral-only" if behavioral_candidates else
            "none_promoted"
        ),
        "failed_convergence_cases": ";".join(str(r.get("case_id")) for r in failures),
        "recommended_next_step": next_step,
    }


def write_report(out_dir: Path, aggregate: Dict[str, float | str], rows: List[Dict[str, float | str]]) -> None:
    discovery = [r for r in rows if str(r.get("row_type")) == "spice_refine" and str(r.get("role")) == "discovery"]
    failures = [r for r in discovery if str(r.get("execution_status")) == "failed_to_converge"]
    top = sorted(
        [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"],
        key=lambda r: python_distance(r),
    )[:10]
    lines = [
        "# SPICE 4->8->12 Nonlinearity Refinement",
        "",
        "Focused ngspice parameter sweep for nonlinear component implementations of the physical 4->8->12 LC bridge.",
        "Discovery rows drive only resonator 1. Direct 4+8 rows are separated ceiling/reference denominators.",
        "",
        "## Direct Answers",
        "",
        f"1. Did any SPICE nonlinear variant cross bridge ratio >1.5? {aggregate['bridge_ratio_gt_1p5_found']}; cases={aggregate['bridge_ratio_gt_1p5_cases']}.",
        f"2. Did the linear no-nonlinearity control remain dead? {aggregate['linear_no_nonlinearity_control_remained_dead']}.",
        f"3. Which nonlinear model is closest to Python LC behavior? case={aggregate['closest_python_lc_case']}, variant={aggregate['closest_python_lc_variant']}, distance={aggregate['closest_python_lc_distance']}.",
        f"4. Are successful variants behavioral-only or component-plausible? {aggregate['successful_variants_are']}.",
        f"5. Which rows failed convergence and why? {aggregate['failed_convergence_cases']}. See summary CSV failure reasons.",
        f"6. Next step: {aggregate['recommended_next_step']}.",
        "",
        "## Sweep Axes",
        "",
        f"- nonlinear strength scale: {', '.join(str(x) for x in NONLINEAR_STRENGTH_SCALES)}",
        f"- limiter/conductance scale: {', '.join(str(x) for x in LIMITER_CONDUCTANCE_SCALES)}",
        f"- coupling scale: {', '.join(str(x) for x in COUPLING_SCALES)}",
        f"- drive amplitude scale: {', '.join(str(x) for x in DRIVE_AMPLITUDE_SCALES)}",
        f"- solver tolerances: {', '.join(SOLVER_PROFILES)}",
        f"- max timestep scale: {', '.join(str(x) for x in MAXSTEP_SCALES)}",
        "",
        "## Top Rows By Python-LC Distance",
        "",
    ]
    for row in top:
        lines.append(
            f"- {row['case_id']} {row['nonlinear_variant']}: status={row['execution_status']}, "
            f"lock={row.get('phase_lock_target', '')}, purity={row.get('spectral_purity_target', '')}, "
            f"bridge={row.get('bridge_ratio_vs_direct_4plus8_reference', '')}, "
            f"target_band_growth={row.get('target_band_growth', '')}, category={row.get('promotion_category', '')}."
        )
    lines.extend(["", "## Convergence Failures", ""])
    if failures:
        for row in failures:
            lines.append(f"- {row['case_id']} {row['nonlinear_variant']}: {row.get('convergence_failure_reason', '')}")
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Notes",
        "",
        "- Bridge ratios are measured against matching separated direct 4+8 references for each swept parameter bundle.",
        "- Target-band growth is counted only when the target FFT peak is near the nominal 12 band.",
        "- Linear control leakage is rejected if the linear rows show target-band build-up or high bridge ratio.",
    ])
    (out_dir / "README_SPICE_412_REFINE_NONLINEARITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run focused ngspice nonlinear refinement for the 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--ngspice-path", default="wsl:ngspice", help="ngspice path; supports wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per ngspice run in seconds.")
    parser.add_argument("--max-discovery-cases", type=int, default=56, help="Focused discovery-row limit.")
    parser.add_argument("--timeseries-samples", type=int, default=160, help="Downsampled timeseries rows per successful discovery case.")
    parser.add_argument("--export-only", action="store_true", help="Write netlists and summaries without running ngspice.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    cases = focused_cases(args.max_discovery_cases)
    ngspice_path = base.resolve_ngspice_path(args.ngspice_path)
    ngspice_available = ngspice_path is not None

    reference_exports: Dict[Tuple[float, float, float, float, str, float], base.SpiceExport] = {}
    reference_data: Dict[Tuple[float, float, float, float, str, float], Dict[str, np.ndarray]] = {}
    reference_results: Dict[Tuple[float, float, float, float, str, float], base.RunResult] = {}
    for key in sorted({case.reference_key for case in cases}):
        pseudo = SweepCase("ref", "behavioral_proxy_current", key[0], key[1], key[2], key[3], key[4], key[5], 0)
        export = export_case_netlist(out_dir, pseudo, reference=True)
        reference_exports[key] = export
        if args.export_only:
            reference_results[key] = base.RunResult("exported", False, "export only")
        elif not ngspice_available:
            reference_results[key] = base.RunResult("skipped_no_ngspice", False, "ngspice not found")
        else:
            result = base.run_ngspice(export, ngspice_path, args.timeout)
            reference_results[key] = result
            if result.success:
                try:
                    reference_data[key] = base.read_ngspice_csv(export.csv_path)
                except Exception as exc:
                    reference_results[key] = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)

    rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    for case in cases:
        export = export_case_netlist(out_dir, case, reference=False)
        if args.export_only:
            result = base.RunResult("exported", False, "export only")
            metrics = None
        elif not ngspice_available:
            result = base.RunResult("skipped_no_ngspice", False, "ngspice not found")
            metrics = None
        else:
            result = base.run_ngspice(export, ngspice_path, args.timeout)
            metrics = None
            if result.success:
                try:
                    data = base.read_ngspice_csv(export.csv_path)
                    metrics, phase_rows = base.spice_metrics(export, data, reference_data.get(case.reference_key))
                    timeseries_rows.extend(downsample_timeseries(export.circuit_name, case, data, args.timeseries_samples))
                    for row in phase_rows:
                        row["case_id"] = case.case_id
                        row["row_type"] = "spice_refine_phase_window"
                    timeseries_rows.extend(phase_rows)
                except Exception as exc:
                    result = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
        rows.append(summarize_case(case, export, result, metrics))

    aggregate = aggregate_summary(rows)
    all_rows = [aggregate] + rows
    write_csv(out_dir / "spice_412_refine_summary.csv", all_rows)
    if timeseries_rows:
        write_csv(out_dir / "spice_412_refine_timeseries.csv", timeseries_rows)
    else:
        timeseries_path = out_dir / "spice_412_refine_timeseries.csv"
        if timeseries_path.exists():
            timeseries_path.unlink()
    write_report(out_dir, aggregate, rows)
    (out_dir / "spice_412_refine_summary.json").write_text(json.dumps({
        "aggregate": aggregate,
        "rows": all_rows,
        "sweep_axes": {
            "nonlinear_strength_scale": NONLINEAR_STRENGTH_SCALES,
            "limiter_conductance_scale": LIMITER_CONDUCTANCE_SCALES,
            "coupling_scale": COUPLING_SCALES,
            "drive_amplitude_scale": DRIVE_AMPLITUDE_SCALES,
            "solver_profiles": list(SOLVER_PROFILES),
            "maxstep_scale": MAXSTEP_SCALES,
        },
        "python_lc_reference": PYTHON_LC,
        "variants": {name: asdict(variant) for name, variant in VARIANTS.items()},
        "references": [{
            "reference_key": list(key),
            "circuit": export.circuit_name,
            "netlist_path": str(export.netlist_path),
            "execution_status": reference_results[key].execution_status,
            "reason": reference_results[key].reason,
        } for key, export in reference_exports.items()],
        "ngspice_available": ngspice_available,
        "ngspice_path": ngspice_path or "",
    }, indent=2), encoding="utf-8")

    print(f"SPICE 4->8->12 nonlinear refinement written to: {out_dir.resolve()}")
    print(f"ngspice_available={ngspice_available}")
    print(f"discovery_cases_run={aggregate['discovery_cases_run']}")
    print(f"successful_discovery_cases={aggregate['successful_discovery_cases']}")
    print(f"bridge_ratio_gt_1p5_found={aggregate['bridge_ratio_gt_1p5_found']}")
    print(f"linear_no_nonlinearity_control_remained_dead={aggregate['linear_no_nonlinearity_control_remained_dead']}")


if __name__ == "__main__":
    main()
