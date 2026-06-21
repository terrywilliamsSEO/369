"""Component-realism ngspice sweep for the 4->8->12 LC bridge.

This track tries to replace the behavioral-current SPICE winner with more
component-plausible nonlinear networks.  Discovery rows forbid behavioral
current mixing, direct 8 drive, direct 12 drive, and target-frequency injection.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

import physical_412_lc_bridge as phys
import spice_412_export as base
import spice_412_refine_nonlinearity as refine


OUT_DIR = Path("runs") / "spice_412_component_realism"
SCALE_NAME = "arbitrary-normalized-scale"
VT = 0.02585

DIODE_IS_VALUES = (1e-14, 1e-12, 1e-10)
DIODE_N_VALUES = (1.2, 1.7, 2.2)
JUNCTION_CAP_SCALES = (0.5, 1.0, 2.0, 4.0)
VARACTOR_C0_SCALES = (0.5, 1.0, 2.0, 4.0)
VARACTOR_VJ_VALUES = (0.5, 1.0, 2.0)
VARACTOR_EXPONENTS = (0.33, 0.5, 0.75)
SATURABLE_L0_SCALES = (0.75, 1.0, 1.25)
SATURATION_CURRENT_SCALES = (0.5, 1.0, 2.0)
CORE_EXPONENTS = (3.0, 5.0)
COUPLING_SCALES = (0.75, 1.0, 1.25, 1.5)
DRIVE_SCALES = (1.0, 1.5, 2.0)
LIMITER_LOSS_SCALES = (0.5, 1.0, 2.0)
SOURCE_LOAD_IMPEDANCE_SCALES = (20.0, 100.0, 500.0)
MAXSTEP_SCALES = (0.5, 1.0, 2.0)

SOLVER_PROFILES = refine.SOLVER_PROFILES
PYTHON_LC = base.PYTHON_BASELINE
BEHAVIORAL_CALIBRATION = {
    "case_id": "r042",
    "variant": "behavioral_proxy_current",
    "lock": 0.9961927017977427,
    "purity": 0.9816579363872546,
    "bridge_ratio": 1.5631690074282802,
    "target_band_growth": 1.2767135824822675,
    "generated_envelope_cv": 0.09153270273356962,
    "max_phase_jump": 0.2899697271745275,
}


@dataclass(frozen=True)
class ComponentVariant:
    name: str
    short: str
    description: str
    base_realism_score: float
    family: str


@dataclass(frozen=True)
class ComponentCase:
    case_id: str
    variant_name: str
    role: str
    diode_is: float
    diode_n: float
    junction_cap_scale: float
    varactor_c0_scale: float
    varactor_vj: float
    varactor_exponent: float
    saturable_l0_scale: float
    saturation_current_scale: float
    core_exponent: float
    coupling_scale: float
    drive_amplitude_scale: float
    limiter_loss_scale: float
    source_load_impedance_scale: float
    solver_profile: str
    maxstep_scale: float
    config_kind: str = "candidate"

    @property
    def reference_key(self) -> Tuple[float, float, float, float, float, str, float]:
        return (
            self.coupling_scale,
            self.drive_amplitude_scale,
            self.limiter_loss_scale,
            self.source_load_impedance_scale,
            self.varactor_c0_scale,
            self.solver_profile,
            self.maxstep_scale,
        )


VARIANTS: Dict[str, ComponentVariant] = {
    "anti_parallel_diode_mixer": ComponentVariant(
        "anti_parallel_diode_mixer", "apd", "Anti-parallel diode mixers between adjacent tanks.", 0.76, "diode"
    ),
    "diode_bridge_mixer": ComponentVariant(
        "diode_bridge_mixer", "bridge", "Floating diode-bridge mixers with high-value leakage references.", 0.72, "diode"
    ),
    "varactor_pair_mixer": ComponentVariant(
        "varactor_pair_mixer", "vpair", "Opposed varactor diode pairs between adjacent tanks.", 0.78, "varactor"
    ),
    "back_to_back_varactor_stack": ComponentVariant(
        "back_to_back_varactor_stack", "vstack", "Back-to-back varactor stacks with floating midpoint references.", 0.80, "varactor"
    ),
    "saturable_inductor_core": ComponentVariant(
        "saturable_inductor_core", "satcore", "Nonlinear magnetic-core proxy on each tank inductor branch.", 0.68, "magnetic"
    ),
    "coupled_saturable_transformer": ComponentVariant(
        "coupled_saturable_transformer", "xfsat", "Coupled saturable transformer proxy between adjacent tanks.", 0.64, "magnetic"
    ),
    "hybrid_varactor_plus_saturable_inductor": ComponentVariant(
        "hybrid_varactor_plus_saturable_inductor", "hybrid", "Varactor stack plus saturable inductor proxy.", 0.70, "hybrid"
    ),
    "diode_plus_resonant_trap_network": ComponentVariant(
        "diode_plus_resonant_trap_network", "trap", "Diode mixers with passive resonant trap branches near generated and target bands.", 0.66, "diode_trap"
    ),
    "linear_no_nonlinearity_control": ComponentVariant(
        "linear_no_nonlinearity_control", "linear", "Linear LC and weak coupling only.", 1.0, "control"
    ),
    "weak_nonlinearity_control": ComponentVariant(
        "weak_nonlinearity_control", "weak", "Very weak diode/varactor nonlinearities as a leakage control.", 0.92, "control"
    ),
    "detuned_target_control": ComponentVariant(
        "detuned_target_control", "detuned", "Source-only component network with target tank detuned away from 12.", 0.80, "control"
    ),
    "shuffled_frequency_control": ComponentVariant(
        "shuffled_frequency_control", "shuffled", "Source-only component network with generated/target tank frequencies shuffled.", 0.78, "control"
    ),
}

DISCOVERY_VARIANTS = (
    "anti_parallel_diode_mixer",
    "diode_bridge_mixer",
    "varactor_pair_mixer",
    "back_to_back_varactor_stack",
    "saturable_inductor_core",
    "coupled_saturable_transformer",
    "hybrid_varactor_plus_saturable_inductor",
    "diode_plus_resonant_trap_network",
)
CONTROL_VARIANTS = (
    "linear_no_nonlinearity_control",
    "weak_nonlinearity_control",
    "detuned_target_control",
    "shuffled_frequency_control",
)


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
    return f"{value:g}".replace(".", "p").replace("-", "m")


def case_name(case: ComponentCase) -> str:
    variant = VARIANTS[case.variant_name]
    return (
        f"{case.case_id}_{variant.short}_c{token(case.coupling_scale)}"
        f"_d{token(case.drive_amplitude_scale)}_l{token(case.limiter_loss_scale)}"
        f"_z{token(case.source_load_impedance_scale)}_{case.solver_profile}_m{token(case.maxstep_scale)}"
    )


def reference_name(key: Tuple[float, float, float, float, float, str, float]) -> str:
    coupling, drive, loss, zscale, vc0, solver, maxstep = key
    return (
        f"ref_direct_4plus8_c{token(coupling)}_d{token(drive)}_l{token(loss)}"
        f"_z{token(zscale)}_vc{token(vc0)}_{solver}_m{token(maxstep)}"
    )


def config_for_case(case: ComponentCase, reference: bool = False) -> phys.BridgeConfig:
    source = phys.DIRECT_REFERENCE if reference else phys.CANDIDATE
    mode_freqs = source.mode_freqs
    if case.config_kind == "detuned_target":
        mode_freqs = (source.mode_freqs[0], source.mode_freqs[1], 12.72)
    elif case.config_kind == "shuffled_frequency":
        mode_freqs = (source.mode_freqs[0], source.mode_freqs[2], source.mode_freqs[1])
    return replace(
        source,
        mode_freqs=mode_freqs,
        stage_a_nonlinear_strength=0.0,
        stage_b_nonlinear_strength=0.0,
        stage_a_to_stage_b_coupling=source.stage_a_to_stage_b_coupling * case.coupling_scale,
        stage_b_to_receiver_coupling=source.stage_b_to_receiver_coupling * case.coupling_scale,
        drive_amp=source.drive_amp * case.drive_amplitude_scale,
        varactor_coefficient=0.0,
        spark_strength=source.spark_strength * case.limiter_loss_scale,
    )


def soft_limiter_lines(scale_name: str, config: phys.BridgeConfig, case: ComponentCase) -> List[str]:
    values = base.soft_limiter_params(scale_name, config)
    return [
        "* Passive loss limiter.",
        f".param gsoft12={base.spice_num(values['gsoft12'] * case.limiter_loss_scale)}",
        f".param gsoft23={base.spice_num(values['gsoft23'] * case.limiter_loss_scale)}",
        f".param vlim12={base.spice_num(values['vlim12'])}",
        f".param vlim23={base.spice_num(values['vlim23'])}",
        "Bsoft12 n1 n2 I={gsoft12*V(n1,n2)*0.5*(1+tanh((abs(V(n1,n2))-vlim12)/(0.3*vlim12+1e-30)))}",
        "Bsoft23 n2 n3 I={gsoft23*V(n2,n3)*0.5*(1+tanh((abs(V(n2,n3))-vlim23)/(0.3*vlim23+1e-30)))}",
    ]


def saturable_current_lines(case: ComponentCase, scale_name: str, config: phys.BridgeConfig, prefix: str = "core") -> List[str]:
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[scale_name])
    lines: List[str] = [f"* Saturable magnetic {prefix} proxy."]
    exp = int(case.core_exponent)
    for idx, p_lc in enumerate(params, start=1):
        sat_i = max(1e-9, case.saturation_current_scale * p_lc.current_scale_a_per_model_velocity)
        ksat = case.saturable_l0_scale * p_lc.capacitance_f * (2.0 * math.pi * p_lc.frequency_hz) ** 2 / max(sat_i ** (exp - 1), 1e-30)
        lines.append(f".param ksat{prefix}{idx}={base.spice_num(0.004 * ksat)}")
    if exp == 5:
        lines.extend([
            f"Bsat{prefix}1 n1 0 I={{ksat{prefix}1*V(n1)*V(n1)*V(n1)*V(n1)*V(n1)}}",
            f"Bsat{prefix}2 n2 0 I={{ksat{prefix}2*V(n2)*V(n2)*V(n2)*V(n2)*V(n2)}}",
            f"Bsat{prefix}3 n3 0 I={{ksat{prefix}3*V(n3)*V(n3)*V(n3)*V(n3)*V(n3)}}",
        ])
    else:
        lines.extend([
            f"Bsat{prefix}1 n1 0 I={{ksat{prefix}1*V(n1)*V(n1)*V(n1)}}",
            f"Bsat{prefix}2 n2 0 I={{ksat{prefix}2*V(n2)*V(n2)*V(n2)}}",
            f"Bsat{prefix}3 n3 0 I={{ksat{prefix}3*V(n3)*V(n3)*V(n3)}}",
        ])
    return lines


def component_lines(scale_name: str, config: phys.BridgeConfig, case: ComponentCase, reference: bool = False) -> List[str]:
    variant = VARIANTS[case.variant_name]
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[scale_name])
    min_c = min(p.capacitance_f for p in params)
    cjo = case.junction_cap_scale * min_c * 0.004
    cvar = case.varactor_c0_scale * min_c * 0.015
    rs = max(0.05, 0.05 * math.sqrt(params[0].resistance_ohm * params[1].resistance_ohm))
    lines: List[str] = [
        "",
        f"* Component realism variant: {variant.name}",
        f"* {variant.description}",
        f"* diode_is={base.spice_num(case.diode_is)}, diode_n={base.spice_num(case.diode_n)}, cjo={base.spice_num(cjo)}",
        f"* varactor_c0={base.spice_num(cvar)}, varactor_vj={base.spice_num(case.varactor_vj)}, varactor_m={base.spice_num(case.varactor_exponent)}",
    ]
    if variant.name in ("linear_no_nonlinearity_control",):
        lines.append("* Linear control: no nonlinear component network.")
        return lines
    if variant.name == "weak_nonlinearity_control":
        cjo *= 0.02
        cvar *= 0.02
    if variant.name in ("anti_parallel_diode_mixer", "weak_nonlinearity_control", "diode_plus_resonant_trap_network"):
        lines.extend([
            "* Anti-parallel diode mixer.",
            f".model DCOMP D(Is={base.spice_num(case.diode_is)} N={base.spice_num(case.diode_n)} Rs={base.spice_num(rs)} Cjo={base.spice_num(cjo)} Vj=0.35 M=0.45)",
            "Dap12a n1 n2 DCOMP",
            "Dap12b n2 n1 DCOMP",
            "Dap23a n2 n3 DCOMP",
            "Dap23b n3 n2 DCOMP",
        ])
    if variant.name == "diode_bridge_mixer":
        lines.extend([
            "* Floating diode-bridge mixer with high-value leakage references.",
            f".model DBRIDGE D(Is={base.spice_num(case.diode_is)} N={base.spice_num(case.diode_n)} Rs={base.spice_num(rs)} Cjo={base.spice_num(cjo)} Vj=0.35 M=0.45)",
            "Rb12p b12p 0 1e9",
            "Rb12n b12n 0 1e9",
            "Db12a n1 b12p DBRIDGE",
            "Db12b n2 b12p DBRIDGE",
            "Db12c b12n n1 DBRIDGE",
            "Db12d b12n n2 DBRIDGE",
            "Rb23p b23p 0 1e9",
            "Rb23n b23n 0 1e9",
            "Db23a n2 b23p DBRIDGE",
            "Db23b n3 b23p DBRIDGE",
            "Db23c b23n n2 DBRIDGE",
            "Db23d b23n n3 DBRIDGE",
        ])
    if variant.name in ("varactor_pair_mixer", "hybrid_varactor_plus_saturable_inductor"):
        lines.extend([
            "* Opposed varactor pair mixer.",
            f".model DVARP D(Is=1e-14 N=1.2 Rs=0.5 Cjo={base.spice_num(cvar)} Vj={base.spice_num(case.varactor_vj)} M={base.spice_num(case.varactor_exponent)} Fc=0.5)",
            "Dvp12a n1 n2 DVARP",
            "Dvp12b n2 n1 DVARP",
            "Dvp23a n2 n3 DVARP",
            "Dvp23b n3 n2 DVARP",
        ])
    if variant.name == "back_to_back_varactor_stack":
        lines.extend([
            "* Back-to-back varactor stacks.",
            f".model DVSTACK D(Is=1e-14 N=1.2 Rs=0.5 Cjo={base.spice_num(cvar)} Vj={base.spice_num(case.varactor_vj)} M={base.spice_num(case.varactor_exponent)} Fc=0.5)",
            "Rm12 m12 0 1e9",
            "Dv12a n1 m12 DVSTACK",
            "Dv12b n2 m12 DVSTACK",
            "Rm23 m23 0 1e9",
            "Dv23a n2 m23 DVSTACK",
            "Dv23b n3 m23 DVSTACK",
        ])
    if variant.name in ("saturable_inductor_core", "hybrid_varactor_plus_saturable_inductor"):
        lines.extend(saturable_current_lines(case, scale_name, config, "core"))
    if variant.name == "coupled_saturable_transformer":
        lines.extend(saturable_current_lines(case, scale_name, config, "xf"))
        lines.extend([
            "* Additional passive transformer coupling already represented by K12/K23; nonlinear core proxy above.",
        ])
    if variant.name == "diode_plus_resonant_trap_network":
        f2 = 2.0 * params[0].frequency_hz
        f3 = 3.0 * params[0].frequency_hz
        ctr = min_c * 0.01
        l2 = 1.0 / ((2.0 * math.pi * f2) ** 2 * ctr)
        l3 = 1.0 / ((2.0 * math.pi * f3) ** 2 * ctr)
        lines.extend([
            "* Passive resonant trap branches near generated and target bands.",
            f"Ctrap2 n2 trap2 {base.spice_num(ctr)}",
            f"Ltrap2 trap2 0 {base.spice_num(l2)}",
            "Rtrap2 trap2 0 10k",
            f"Ctrap3 n3 trap3 {base.spice_num(ctr)}",
            f"Ltrap3 trap3 0 {base.spice_num(l3)}",
            "Rtrap3 trap3 0 10k",
        ])
    if not reference:
        lines.extend(soft_limiter_lines(scale_name, config, case))
    return lines


def export_netlist(out_dir: Path, case: ComponentCase, reference: bool = False) -> base.SpiceExport:
    config = config_for_case(case, reference=reference)
    scale_name = SCALE_NAME
    params = phys.build_lc_params(config, phys.SCALE_PRESETS[scale_name])
    coupling = phys.coupling_summary(config)
    flags = base.direct_drive_flags(config)
    tstop, tstep, drive_until, ramp = base.physical_timing(scale_name)
    maxstep = tstep * case.maxstep_scale
    hold_time = max(ramp, drive_until - ramp)
    circuit_name = reference_name(case.reference_key) if reference else case_name(case)
    netlist_path = out_dir / f"{circuit_name}.cir"
    csv_path = out_dir / f"{circuit_name}_tran.csv"
    raw_path = out_dir / f"{circuit_name}.raw"

    drive_count = max(1, len(config.drive_freqs))
    drive_lines: List[str] = []
    for drive_idx, (freq_ratio, mode_idx) in enumerate(zip(config.drive_freqs, config.drive_modes), start=1):
        node = f"n{mode_idx + 1}"
        drive_frequency = phys.BASE_HZ * freq_ratio * phys.scale_factor(phys.SCALE_PRESETS[scale_name])
        amp = base.drive_current_for_mode(scale_name, config, mode_idx, drive_count)
        role_note = "source-only discovery/control drive" if not reference else "direct 4+8 ceiling reference drive"
        drive_lines.extend([
            f"* {role_note}: mode {mode_idx + 1}, f={base.spice_num(drive_frequency)} Hz",
            f".param idrive{drive_idx}={base.spice_num(amp)}",
            f".param fdrive{drive_idx}={base.spice_num(drive_frequency)}",
            f"Bdrive{drive_idx} {node} 0 I={{-idrive{drive_idx}*V(env)*sin(2*pi*fdrive{drive_idx}*time)}}",
        ])

    lines = [
        f"* {circuit_name}: component-realism 4->8->12 LC bridge",
        f"* scale={scale_name}; role={'ceiling_reference' if reference else case.role}; variant={case.variant_name}",
        "* Generated by spice_412_component_realism.py.",
        "* Discovery rows forbid behavioral current mixing and direct target/generated drive.",
        f".option {SOLVER_PROFILES[case.solver_profile]}",
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
        "* Three lossy LC resonators.",
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
        "* Weak linear coupling.",
        f"K12 L1 L2 {base.spice_num(float(coupling['linear_k01_fraction_of_omega_product']))}",
        f"K23 L2 L3 {base.spice_num(float(coupling['linear_k12_fraction_of_omega_product']))}",
    ])
    lines.extend(component_lines(scale_name, config, case, reference=reference))
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


def add_case(cases: List[ComponentCase], variant_name: str, role: str = "discovery",
             diode_is: float = 1e-12, diode_n: float = 1.7, junction_cap_scale: float = 1.0,
             varactor_c0_scale: float = 1.0, varactor_vj: float = 1.0, varactor_exponent: float = 0.5,
             saturable_l0_scale: float = 1.0, saturation_current_scale: float = 1.0, core_exponent: float = 3.0,
             coupling_scale: float = 1.0, drive_amplitude_scale: float = 1.0, limiter_loss_scale: float = 1.0,
             source_load_impedance_scale: float = 100.0, solver_profile: str = "default", maxstep_scale: float = 1.0,
             config_kind: str = "candidate") -> None:
    cases.append(ComponentCase(
        case_id=f"c{len(cases) + 1:03d}",
        variant_name=variant_name,
        role=role,
        diode_is=diode_is,
        diode_n=diode_n,
        junction_cap_scale=junction_cap_scale,
        varactor_c0_scale=varactor_c0_scale,
        varactor_vj=varactor_vj,
        varactor_exponent=varactor_exponent,
        saturable_l0_scale=saturable_l0_scale,
        saturation_current_scale=saturation_current_scale,
        core_exponent=core_exponent,
        coupling_scale=coupling_scale,
        drive_amplitude_scale=drive_amplitude_scale,
        limiter_loss_scale=limiter_loss_scale,
        source_load_impedance_scale=source_load_impedance_scale,
        solver_profile=solver_profile,
        maxstep_scale=maxstep_scale,
        config_kind=config_kind,
    ))


def focused_cases(max_cases: int) -> List[ComponentCase]:
    cases: List[ComponentCase] = []
    for variant in DISCOVERY_VARIANTS:
        add_case(cases, variant)
        add_case(cases, variant, coupling_scale=1.25, drive_amplitude_scale=1.5, limiter_loss_scale=2.0)
        add_case(cases, variant, diode_is=1e-10, junction_cap_scale=4.0, varactor_c0_scale=4.0,
                 varactor_vj=0.5, coupling_scale=1.25, drive_amplitude_scale=1.5, limiter_loss_scale=2.0)
        add_case(cases, variant, diode_n=1.2, junction_cap_scale=2.0, varactor_c0_scale=2.0,
                 saturable_l0_scale=0.75, saturation_current_scale=0.5, core_exponent=5.0,
                 coupling_scale=1.5, drive_amplitude_scale=2.0, limiter_loss_scale=1.0,
                 source_load_impedance_scale=500.0, solver_profile="relaxed", maxstep_scale=2.0)
        add_case(cases, variant, diode_is=1e-14, diode_n=2.2, junction_cap_scale=0.5,
                 varactor_c0_scale=0.5, varactor_vj=2.0, coupling_scale=0.75,
                 drive_amplitude_scale=1.5, limiter_loss_scale=0.5, source_load_impedance_scale=20.0,
                 solver_profile="conservative", maxstep_scale=0.5)
    add_case(cases, "linear_no_nonlinearity_control", role="control")
    add_case(cases, "weak_nonlinearity_control", role="control", diode_is=1e-14, junction_cap_scale=0.02,
             varactor_c0_scale=0.02, coupling_scale=1.5, drive_amplitude_scale=2.0)
    add_case(cases, "detuned_target_control", role="control",
             coupling_scale=1.25, drive_amplitude_scale=1.5, limiter_loss_scale=2.0, config_kind="detuned_target")
    add_case(cases, "shuffled_frequency_control", role="control",
             coupling_scale=1.25, drive_amplitude_scale=1.5, limiter_loss_scale=2.0, config_kind="shuffled_frequency")
    return cases[:max_cases]


def row_float(row: Dict[str, float | str], key: str, default: float = float("nan")) -> float:
    return base.row_float(row, key, default)


def component_stress(case: ComponentCase, export: base.SpiceExport, data: Dict[str, np.ndarray]) -> Dict[str, float | str]:
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
    stress = max(
        required_drive_voltage / 50.0,
        vdiff / 50.0,
        peak_diode_current / 0.10,
        peak_inductor_current / 1.0,
    )
    if stress < 0.5:
        stress_label = "plausible"
    elif stress < 1.5:
        stress_label = "aggressive"
    else:
        stress_label = "unrealistic"
    return {
        "required_drive_voltage": required_drive_voltage,
        "peak_diode_current": peak_diode_current,
        "peak_varactor_voltage": vdiff,
        "peak_inductor_current": peak_inductor_current,
        "estimated_component_stress": stress,
        "component_stress_label": stress_label,
        "passivity_flag": "True",
    }


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
    return float(near * (0.4 * min(bridge / 1.0, 1.0) + 0.4 * min(purity / 0.8, 1.0) + 0.2 * min(growth, 1.0)))


def python_distance(row: Dict[str, float | str]) -> float:
    if str(row.get("execution_status")) != "ran_successfully":
        return float("inf")
    total = 0.0
    for key, target, scale in (
        ("spice_phase_lock_target", PYTHON_LC["phase_lock_target"], 0.20),
        ("spice_bridge_ratio", PYTHON_LC["bridge_ratio"], 1.0),
        ("spice_spectral_purity_target", PYTHON_LC["spectral_purity_target"], 0.25),
        ("spice_generated_envelope_cv", PYTHON_LC["generated_envelope_cv"], 0.50),
        ("spice_max_phase_jump", PYTHON_LC["max_phase_jump"], 1.0),
    ):
        value = row_float(row, key)
        if not np.isfinite(value):
            return float("inf")
        total += abs(value - float(target)) / scale
    return float(total)


def behavioral_proxy_distance(row: Dict[str, float | str]) -> float:
    if str(row.get("execution_status")) != "ran_successfully":
        return float("inf")
    total = 0.0
    for key, target, scale in (
        ("spice_phase_lock_target", BEHAVIORAL_CALIBRATION["lock"], 0.20),
        ("spice_bridge_ratio", BEHAVIORAL_CALIBRATION["bridge_ratio"], 1.0),
        ("spice_spectral_purity_target", BEHAVIORAL_CALIBRATION["purity"], 0.25),
        ("target_band_growth", BEHAVIORAL_CALIBRATION["target_band_growth"], 1.0),
        ("spice_generated_envelope_cv", BEHAVIORAL_CALIBRATION["generated_envelope_cv"], 0.50),
        ("spice_max_phase_jump", BEHAVIORAL_CALIBRATION["max_phase_jump"], 1.0),
    ):
        value = row_float(row, key)
        if not np.isfinite(value):
            return float("inf")
        total += abs(value - float(target)) / scale
    return float(total)


def summarize_case(case: ComponentCase, export: base.SpiceExport, result: base.RunResult,
                   metrics: Dict[str, float | str] | None,
                   stress: Dict[str, float | str] | None) -> Dict[str, float | str]:
    variant = VARIANTS[case.variant_name]
    row: Dict[str, float | str] = {
        "row_type": "component_realism",
        "case_id": case.case_id,
        "circuit": export.circuit_name,
        "role": export.role,
        "control_kind": case.config_kind if case.role == "control" else "",
        "nonlinear_variant": case.variant_name,
        "component_family": variant.family,
        "variant_description": variant.description,
        "diode_saturation_current": case.diode_is,
        "diode_emission_coefficient": case.diode_n,
        "junction_capacitance_scale": case.junction_cap_scale,
        "varactor_C0_scale": case.varactor_c0_scale,
        "varactor_voltage_coefficient": case.varactor_vj,
        "varactor_exponent": case.varactor_exponent,
        "saturable_inductor_L0_scale": case.saturable_l0_scale,
        "saturation_current_scale": case.saturation_current_scale,
        "core_nonlinearity_exponent": case.core_exponent,
        "coupling_scale": case.coupling_scale,
        "drive_amplitude_scale": case.drive_amplitude_scale,
        "limiter_loss_scale": case.limiter_loss_scale,
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
            "source_fft_peak": row.get("spice_fft_peak_source_hz", ""),
            "generated_fft_peak": row.get("spice_fft_peak_generated_hz", ""),
            "target_fft_peak": row.get("spice_fft_peak_target_hz", ""),
            "phase_lock_target": row.get("spice_phase_lock_target", ""),
            "spectral_purity_target": row.get("spice_spectral_purity_target", ""),
            "generated_envelope_CV": row.get("spice_generated_envelope_cv", ""),
            "max_phase_jump": row.get("spice_max_phase_jump", ""),
            "bridge_ratio_vs_direct_4plus8_reference": row.get("spice_bridge_ratio", ""),
        })
        row["python_lc_distance"] = python_distance(row)
        row["behavioral_proxy_distance"] = behavioral_proxy_distance(row)
    if stress:
        row.update(stress)
    return row


def summarize_reference(export: base.SpiceExport, result: base.RunResult,
                        metrics: Dict[str, float | str] | None) -> Dict[str, float | str]:
    row: Dict[str, float | str] = {
        "row_type": "component_realism_reference",
        "case_id": "direct_4plus8_ceiling_reference",
        "circuit": export.circuit_name,
        "role": "ceiling_reference",
        "control_kind": "direct_4plus8_ceiling_reference",
        "nonlinear_variant": "direct_4plus8_ceiling_reference",
        "component_family": "reference",
        "variant_description": "Separated direct 4+8 drive reference used only as the bridge-ratio denominator.",
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
        "component_realism_score": "",
        "promotion_category": "ceiling_reference_not_discovery",
    }
    if metrics:
        row.update(metrics)
        row.update({
            "target_band_growth": target_band_growth(row),
            "source_fft_peak": row.get("spice_fft_peak_source_hz", ""),
            "generated_fft_peak": row.get("spice_fft_peak_generated_hz", ""),
            "target_fft_peak": row.get("spice_fft_peak_target_hz", ""),
            "phase_lock_target": row.get("spice_phase_lock_target", ""),
            "spectral_purity_target": row.get("spice_spectral_purity_target", ""),
            "generated_envelope_CV": row.get("spice_generated_envelope_cv", ""),
            "max_phase_jump": row.get("spice_max_phase_jump", ""),
        })
    return row


def promotion_category(row: Dict[str, float | str], controls_dead: bool) -> str:
    if str(row.get("role")) == "control":
        return "control_dead" if leakage_score(row) < 0.10 else "reject_due_to_control_leakage"
    if not controls_dead:
        return "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "ran_successfully":
        return "not_promoted"
    if str(row.get("direct_8_drive_present")) != "False" or str(row.get("direct_12_drive_present")) != "False":
        return "not_promoted"
    if str(row.get("target_frequency_injection_present")) != "False":
        return "not_promoted"
    stress = row_float(row, "estimated_component_stress", 0.0)
    lock = row_float(row, "phase_lock_target", 0.0)
    purity = row_float(row, "spectral_purity_target", 0.0)
    bridge = row_float(row, "bridge_ratio_vs_direct_4plus8_reference", 0.0)
    growth = row_float(row, "target_band_growth", 0.0)
    cv = row_float(row, "generated_envelope_CV", 999.0)
    jump = row_float(row, "max_phase_jump", 999.0)
    if stress > 1.5 and lock > 0.90 and purity > 0.80 and bridge > 1.0:
        return "reject_due_to_component_stress"
    if lock > 0.90 and purity > 0.80 and bridge > 1.5 and growth > 1.0 and cv < 0.25 and jump < 1.0 and stress <= 1.5:
        return "spice_component_bridge_candidate"
    if lock > 0.90 and purity > 0.80 and bridge > 1.0 and stress <= 1.5:
        return "spice_component_near_miss"
    return "not_promoted"


def aggregate(rows: List[Dict[str, float | str]]) -> Dict[str, float | str]:
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    controls = [r for r in rows if str(r.get("role")) == "control"]
    max_control_leakage = max((leakage_score(r) for r in controls), default=0.0)
    controls_dead = max_control_leakage < 0.10
    for row in rows:
        row["linear_control_leakage_score"] = max_control_leakage
        row["promotion_category"] = promotion_category(row, controls_dead)
    successful = [r for r in discovery if str(r.get("execution_status")) == "ran_successfully"]
    candidates = [r for r in discovery if str(r.get("promotion_category")) == "spice_component_bridge_candidate"]
    near = [r for r in discovery if str(r.get("promotion_category")) == "spice_component_near_miss"]
    bridge_crossers = [r for r in successful if row_float(r, "bridge_ratio_vs_direct_4plus8_reference", 0.0) > 1.5]
    failures = [r for r in rows if str(r.get("execution_status")) == "failed_to_converge"]
    closest = min(successful, key=behavioral_proxy_distance) if successful else {}
    closest_python = min(successful, key=python_distance) if successful else {}
    if candidates:
        next_step = "physical parameter refinement around component candidates, then spatial phase-matching model"
    elif near:
        next_step = "deeper component sweep around near misses, then physical parameter refinement"
    else:
        next_step = "deeper component sweep and spatial phase-matching model before physical parameter refinement"
    return {
        "row_type": "aggregate",
        "discovery_cases_run": len(discovery),
        "successful_discovery_cases": len(successful),
        "failed_to_converge_cases": len(failures),
        "component_bridge_candidate_count": len(candidates),
        "component_near_miss_count": len(near),
        "bridge_ratio_gt_1p5_found": str(bool(bridge_crossers)),
        "bridge_ratio_gt_1p5_cases": ";".join(str(r.get("case_id")) for r in bridge_crossers),
        "controls_remained_dead": str(controls_dead),
        "max_control_leakage_score": max_control_leakage,
        "closest_component_case": str(closest.get("case_id", "")),
        "closest_component_variant": str(closest.get("nonlinear_variant", "")),
        "closest_component_bridge_ratio": closest.get("bridge_ratio_vs_direct_4plus8_reference", ""),
        "closest_component_lock": closest.get("phase_lock_target", ""),
        "closest_component_purity": closest.get("spectral_purity_target", ""),
        "closest_component_stress": closest.get("component_stress_label", ""),
        "closest_component_behavioral_proxy_distance": closest.get("behavioral_proxy_distance", ""),
        "closest_python_lc_case": str(closest_python.get("case_id", "")),
        "closest_python_lc_variant": str(closest_python.get("nonlinear_variant", "")),
        "closest_python_lc_distance": closest_python.get("python_lc_distance", ""),
        "successful_or_near_miss_realism": (
            "plausible_or_aggressive" if candidates or near else "none_promoted"
        ),
        "failed_convergence_cases": ";".join(str(r.get("case_id")) for r in failures),
        "recommended_next_step": next_step,
    }


def downsample_timeseries(circuit: str, case: ComponentCase, data: Dict[str, np.ndarray], limit: int) -> List[Dict[str, float | str]]:
    if limit <= 0:
        return []
    n = len(data["time"])
    if n == 0:
        return []
    indices = np.unique(np.linspace(0, n - 1, min(limit, n), dtype=int))
    rows: List[Dict[str, float | str]] = []
    for idx in indices:
        row: Dict[str, float | str] = {
            "row_type": "component_realism_timeseries",
            "circuit": circuit,
            "case_id": case.case_id,
            "role": case.role,
            "control_kind": case.config_kind if case.role == "control" else "",
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
    references = [r for r in rows if str(r.get("role")) == "ceiling_reference"]
    top = sorted([r for r in discovery if str(r.get("execution_status")) == "ran_successfully"], key=behavioral_proxy_distance)[:10]
    failures = [r for r in rows if str(r.get("execution_status")) == "failed_to_converge"]
    lines = [
        "# SPICE 4->8->12 Component Realism",
        "",
        "Component-only refinement track. Behavioral current mixing is forbidden for discovery rows.",
        "",
        "## Direct Answers",
        "",
        f"1. Did any component-plausible SPICE row cross bridge ratio >1.5? {summary['bridge_ratio_gt_1p5_found']}; cases={summary['bridge_ratio_gt_1p5_cases']}.",
        f"2. Did any component-plausible row become a near miss with bridge ratio >1.0? {summary['component_near_miss_count']}.",
        f"3. Did linear, weak-nonlinearity, detuned, and shuffled controls stay dead? {summary['controls_remained_dead']}; max_control_leakage={summary['max_control_leakage_score']}.",
        f"4. Which component family was closest to the behavioral proxy? case={summary['closest_component_case']}, variant={summary['closest_component_variant']}.",
        f"5. Were successful or near-miss rows physically plausible, aggressive, or unrealistic? {summary['successful_or_near_miss_realism']}; closest_stress={summary['closest_component_stress']}.",
        f"6. Next step: {summary['recommended_next_step']}.",
        "",
        "## Top Component Rows",
        "",
    ]
    for row in top:
        lines.append(
            f"- {row['case_id']} {row['nonlinear_variant']}: status={row['execution_status']}, "
            f"lock={row.get('phase_lock_target', '')}, purity={row.get('spectral_purity_target', '')}, "
            f"bridge={row.get('bridge_ratio_vs_direct_4plus8_reference', '')}, "
            f"growth={row.get('target_band_growth', '')}, stress={row.get('component_stress_label', '')}, "
            f"category={row.get('promotion_category', '')}."
        )
    lines.extend(["", "## Direct 4+8 Ceiling References", ""])
    if references:
        for row in references:
            lines.append(
                f"- {row['circuit']}: status={row['execution_status']}, "
                f"direct_8_drive={row.get('direct_8_drive_present', '')}, "
                f"direct_12_drive={row.get('direct_12_drive_present', '')}, "
                f"target_frequency_injection={row.get('target_frequency_injection_present', '')}."
            )
    else:
        lines.append("- None.")
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
        "- Discovery rows use component-plausible diode, varactor, saturable, hybrid, or trap networks only.",
        "- Behavioral current mixing is present only as historical calibration metadata.",
        "- Direct 4+8 references are separated ceiling denominators and are not discovery rows.",
    ])
    (out_dir / "README_SPICE_412_COMPONENT_REALISM.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run component-realism ngspice refinement for the 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--ngspice-path", default="wsl:ngspice")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-cases", type=int, default=44)
    parser.add_argument("--timeseries-samples", type=int, default=120)
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

    ref_data: Dict[Tuple[float, float, float, float, float, str, float], Dict[str, np.ndarray]] = {}
    ref_results: Dict[Tuple[float, float, float, float, float, str, float], base.RunResult] = {}
    ref_exports: Dict[Tuple[float, float, float, float, float, str, float], base.SpiceExport] = {}
    ref_metrics: Dict[Tuple[float, float, float, float, float, str, float], Dict[str, float | str]] = {}
    for key in sorted({case.reference_key for case in cases}):
        pseudo = ComponentCase("ref", "varactor_pair_mixer", "ceiling_reference", 1e-12, 1.7, 1.0, key[4], 1.0, 0.5, 1.0, 1.0, 3.0, key[0], key[1], key[2], key[3], key[5], key[6])
        export = export_netlist(out_dir, pseudo, reference=True)
        ref_exports[key] = export
        if args.export_only:
            result = base.RunResult("exported", False, "export only")
        elif not ngspice_available:
            result = base.RunResult("skipped_no_ngspice", False, ngspice_resolution_error or "ngspice not found")
        else:
            result = base.run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    ref_data[key] = base.read_ngspice_csv(export.csv_path)
                except Exception as exc:
                    result = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
        ref_results[key] = result
        if result.success and key in ref_data:
            try:
                ref_metrics[key], _ = base.spice_metrics(export, ref_data[key], None)
            except Exception as exc:
                ref_metrics[key] = {"spice_metric_error": f"{type(exc).__name__}: {exc}"}

    rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    for case in cases:
        export = export_netlist(out_dir, case, reference=False)
        metrics = None
        stress = None
        if args.export_only:
            result = base.RunResult("exported", False, "export only")
        elif not ngspice_available:
            result = base.RunResult("skipped_no_ngspice", False, ngspice_resolution_error or "ngspice not found")
        else:
            result = base.run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    data = base.read_ngspice_csv(export.csv_path)
                    metrics, phase_rows = base.spice_metrics(export, data, ref_data.get(case.reference_key))
                    stress = component_stress(case, export, data)
                    timeseries_rows.extend(downsample_timeseries(export.circuit_name, case, data, args.timeseries_samples))
                    for row in phase_rows:
                        row["case_id"] = case.case_id
                        row["row_type"] = "component_realism_phase_window"
                    timeseries_rows.extend(phase_rows)
                except Exception as exc:
                    result = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
        rows.append(summarize_case(case, export, result, metrics, stress))

    summary = aggregate(rows)
    reference_rows = [
        summarize_reference(export, ref_results[key], ref_metrics.get(key))
        for key, export in ref_exports.items()
    ]
    all_rows = [summary] + reference_rows + rows
    write_csv(out_dir / "spice_412_component_realism_summary.csv", all_rows)
    if timeseries_rows:
        write_csv(out_dir / "spice_412_component_realism_timeseries.csv", timeseries_rows)
    write_report(out_dir, summary, reference_rows + rows)
    (out_dir / "spice_412_component_realism_summary.json").write_text(json.dumps({
        "aggregate": summary,
        "rows": all_rows,
        "behavioral_calibration_reference": BEHAVIORAL_CALIBRATION,
        "sweep_axes": {
            "diode_saturation_current": DIODE_IS_VALUES,
            "diode_emission_coefficient": DIODE_N_VALUES,
            "junction_capacitance_scale": JUNCTION_CAP_SCALES,
            "varactor_C0_scale": VARACTOR_C0_SCALES,
            "varactor_voltage_coefficient": VARACTOR_VJ_VALUES,
            "varactor_exponent": VARACTOR_EXPONENTS,
            "saturable_inductor_L0_scale": SATURABLE_L0_SCALES,
            "saturation_current_scale": SATURATION_CURRENT_SCALES,
            "core_nonlinearity_exponent": CORE_EXPONENTS,
            "coupling_scale": COUPLING_SCALES,
            "drive_amplitude_scale": DRIVE_SCALES,
            "limiter_loss_scale": LIMITER_LOSS_SCALES,
            "source_load_impedance_scale": SOURCE_LOAD_IMPEDANCE_SCALES,
            "solver_tolerance_profile": list(SOLVER_PROFILES),
            "max_timestep_profile": MAXSTEP_SCALES,
        },
        "variants": {name: asdict(variant) for name, variant in VARIANTS.items()},
        "references": [{
            "reference_key": list(key),
            "circuit": export.circuit_name,
            "execution_status": ref_results[key].execution_status,
            "reason": ref_results[key].reason,
        } for key, export in ref_exports.items()],
        "ngspice_available": ngspice_available,
        "ngspice_path": ngspice_path or "",
        "ngspice_resolution_error": ngspice_resolution_error,
    }, indent=2), encoding="utf-8")

    print(f"SPICE 4->8->12 component realism written to: {out_dir.resolve()}")
    print(f"ngspice_available={ngspice_available}")
    print(f"discovery_cases_run={summary['discovery_cases_run']}")
    print(f"successful_discovery_cases={summary['successful_discovery_cases']}")
    print(f"component_bridge_candidate_count={summary['component_bridge_candidate_count']}")
    print(f"component_near_miss_count={summary['component_near_miss_count']}")
    print(f"controls_remained_dead={summary['controls_remained_dead']}")


if __name__ == "__main__":
    main()
