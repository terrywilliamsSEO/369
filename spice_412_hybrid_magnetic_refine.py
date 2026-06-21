#!/usr/bin/env python3
"""Hybrid varactor-plus-magnetic refinement for the 4->8->12 bridge.

This track focuses on the strongest row from the electrical candidate race:
the hybrid varactor-plus-magnetic transmission line.  It keeps the same
50/100/150 MHz bench-scale framing, drives only the 50 MHz source band in
discovery rows, and explores section placement, nonlinear strength, phase
velocity trim, passive 150 MHz cleanup, and stress-reduction variants.
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

import spice_412_electrical_candidate_race as race
import spice_412_varactor_nltl_design as design
import spice_412_varactor_nltl_refine as refine


OUT_DIR = Path("runs") / "spice_412_hybrid_magnetic_refine"
SOURCE_HZ = design.SOURCE_HZ
GENERATED_HZ = design.GENERATED_HZ
TARGET_HZ = design.TARGET_HZ
TOTAL_LENGTH_M = design.TOTAL_LENGTH_M
EPS = 1.0e-30


@dataclass(frozen=True)
class HybridMagneticCase(race.RaceCase):
    hybrid_section_placement: str = "alternating_varactor_magnetic_cells"
    magnetic_saturation_curve: str = "soft"
    magnetic_section_count: int = 16
    magnetic_section_spacing: int = 4
    magnetic_dc_bias_proxy: float = 0.0
    magnetic_core_loss_proxy: float = 0.25
    varactor_capacitance_swing_ratio: float = 1.35
    varactor_reverse_bias_v: float = 3.4
    varactor_section_count: int = 96
    varactor_section_spacing: int = 1
    stacked_varactor_pairs: int = 1
    phase_trim_family: str = "baseline"
    group_delay_match_score: float = 0.0
    target_extraction_position: str = "end"
    post_filter_strength: float = 0.0
    source_rejection_trap_strength: float = 1.0
    generated_rejection_trap_strength: float = 1.0
    stress_reduction_strategy: str = "baseline"


@dataclass(frozen=True)
class HybridMagneticExport:
    case: HybridMagneticCase
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


def clean_name(value: str) -> str:
    return race.clean_name(value)


def spice_num(value: float) -> str:
    return design.spice_num(value)


def section_indices(case: HybridMagneticCase, kind: str) -> List[int]:
    """Return cell indices for varactor/magnetic nonlinear sections."""
    cells = list(range(1, case.cell_count + 1))
    spacing = max(1, case.magnetic_section_spacing if kind == "magnetic" else case.varactor_section_spacing)
    if case.hybrid_section_placement == "varactor_first_then_magnetic":
        if kind == "varactor":
            candidates = [i for i in cells if i <= case.cell_count // 2]
        else:
            candidates = [i for i in cells if i > case.cell_count // 2]
    elif case.hybrid_section_placement == "magnetic_first_then_varactor":
        if kind == "magnetic":
            candidates = [i for i in cells if i <= case.cell_count // 2]
        else:
            candidates = [i for i in cells if i > case.cell_count // 2]
    elif case.hybrid_section_placement == "grouped_varactor_then_magnetic":
        split = int(case.cell_count * 0.62)
        candidates = [i for i in cells if (i <= split if kind == "varactor" else i > split)]
    elif case.hybrid_section_placement == "grouped_magnetic_then_varactor":
        split = int(case.cell_count * 0.38)
        candidates = [i for i in cells if (i <= split if kind == "magnetic" else i > split)]
    elif case.hybrid_section_placement == "qpm_sign_flipped_hybrid_sections":
        candidates = cells
    elif case.hybrid_section_placement == "middle_third_only":
        lo = case.cell_count // 3
        hi = 2 * case.cell_count // 3
        candidates = [i for i in cells if lo <= i <= hi]
    elif case.hybrid_section_placement == "near_target_extraction_only":
        lo = int(case.cell_count * 0.62)
        candidates = [i for i in cells if i >= lo]
    else:
        offset = 0 if kind == "varactor" else max(1, spacing // 2)
        candidates = [i for i in cells if (i + offset) % spacing == 0]

    if kind == "magnetic":
        limit = max(1, case.magnetic_section_count)
    else:
        limit = max(1, case.varactor_section_count)
    selected = candidates[::spacing]
    if not selected:
        selected = candidates[:]
    return selected[:limit]


def qpm_sign(case: HybridMagneticCase, idx: int) -> float:
    if case.hybrid_section_placement != "qpm_sign_flipped_hybrid_sections":
        return 1.0
    period = max(2, case.cell_count // 8)
    return -1.0 if (idx // period) % 2 else 1.0


def hybrid_cell_values(case: HybridMagneticCase) -> Dict[str, float]:
    return refine.refine_cell_values(case)


def series_lc_values(freq_hz: float, c_f: float, q: float, r_floor: float = 0.25) -> Dict[str, float]:
    omega = 2.0 * math.pi * freq_hz
    l_h = 1.0 / max((omega ** 2) * c_f, EPS)
    r_ohm = max(r_floor, math.sqrt(max(l_h, EPS) / max(c_f, EPS)) / max(q, 0.5))
    return {"l_h": l_h, "c_f": c_f, "r_ohm": r_ohm}


def add_hybrid_cleanup(lines: List[str], case: HybridMagneticCase, raw_out: str) -> str:
    """Add passive output extraction/rejection cleanup networks."""
    measure = raw_out
    target_c = case.extraction_c_f * max(0.25, 1.0 + 0.10 * case.post_filter_strength)
    if case.cleanup_topology in {"target_extraction", "weak_150_bandpass", "extraction_plus_rejection"}:
        measure = "v150"
        band = series_lc_values(TARGET_HZ * case.target_phase_velocity_scale, target_c, case.extraction_q, 0.2)
        if case.target_extraction_position == "before_final_absorber":
            tap = design.n(max(1, case.cell_count - max(2, case.cell_count // 12)))
        else:
            tap = raw_out
        lines.extend(
            [
                f"Rext {tap} ext_r {spice_num(band['r_ohm'])}",
                f"Lext ext_r ext_l {spice_num(band['l_h'])}",
                f"Cext ext_l {measure} {spice_num(band['c_f'])}",
                f"Rload150 {measure} 0 {spice_num(case.output_load_ohm)}",
            ]
        )
        if case.post_filter_strength > 0.0:
            post = series_lc_values(TARGET_HZ, target_c * 0.55, case.extraction_q * (1.2 + case.post_filter_strength), 0.2)
            lines.extend(
                [
                    f"Rpost150 {measure} post_r {spice_num(post['r_ohm'])}",
                    f"Lpost150 post_r post_l {spice_num(post['l_h'])}",
                    f"Cpost150 post_l v150f {spice_num(post['c_f'])}",
                    f"Rload150f v150f 0 {spice_num(case.output_load_ohm * (1.0 + 0.4 * case.post_filter_strength))}",
                ]
            )
            measure = "v150f"
    if case.source_rejection or case.cleanup_topology in {"source_rejection", "extraction_plus_rejection"}:
        q = 12.0 + 8.0 * case.source_rejection_trap_strength
        trap50 = series_lc_values(SOURCE_HZ, 9.0e-12, q, 0.2)
        lines.extend(
            [
                f"Rtrap50 {raw_out} tr50_r {spice_num(trap50['r_ohm'])}",
                f"Ltrap50 tr50_r tr50_l {spice_num(trap50['l_h'])}",
                f"Ctrap50 tr50_l 0 {spice_num(trap50['c_f'])}",
            ]
        )
    if case.generated_rejection or case.cleanup_topology in {"generated_rejection", "extraction_plus_rejection"}:
        q = 10.0 + 9.0 * case.generated_rejection_trap_strength
        trap100 = series_lc_values(GENERATED_HZ * case.generated_phase_velocity_scale, 6.8e-12, q, 0.2)
        lines.extend(
            [
                f"Rtrap100 {raw_out} tr100_r {spice_num(trap100['r_ohm'])}",
                f"Ltrap100 tr100_r tr100_l {spice_num(trap100['l_h'])}",
                f"Ctrap100 tr100_l 0 {spice_num(trap100['c_f'])}",
            ]
        )
    return measure


def netlist_for_case(case: HybridMagneticCase, csv_path: Path) -> str:
    stable_race_families = {
        "varactor_only_line",
        "detuned_150mhz_phase_velocity_line",
        "shuffled_frequency_line",
        "direct_50plus100_reference",
    }
    if case.role == "ceiling_reference" or case.family in stable_race_families:
        return race.netlist_for_case(case, csv_path)

    vals = hybrid_cell_values(case)
    var = design.VaractorModel(
        cjo_f=max(vals["cjo_f"], 1.0e-15),
        vj_v=case.varactor_vj_v,
        m=case.varactor_m,
        rs_ohm=case.varactor_rs_ohm,
        bv_v=case.varactor_bv_v,
        ibv_a=case.varactor_ibv_a,
    )
    raw_out = design.n(case.cell_count)
    mid = max(1, case.cell_count // 2)
    varactor_nodes = set(section_indices(case, "varactor"))
    magnetic_nodes = section_indices(case, "magnetic")
    magnetic_curve = 1.0 if case.magnetic_saturation_curve == "soft" else 1.7
    kmag = 2.5e-6 * case.magnetic_strength * case.nonlinear_strength_scale * magnetic_curve
    gcore = 3.0e-7 * max(case.magnetic_core_loss_proxy + case.magnetic_hysteresis_loss, 0.0)
    bias_shift = 1.0 + 0.25 * math.tanh(case.magnetic_dc_bias_proxy)
    lines = [
        f"* {case.name}",
        "* Hybrid varactor-plus-magnetic 50/100/150 MHz refinement track.",
        f"* role={case.role}; source_only={case.source_only_drive}; no direct 100/150 MHz discovery drive.",
        f"* placement={case.hybrid_section_placement}; magnetic_curve={case.magnetic_saturation_curve}; cleanup={case.cleanup_topology}",
        ".option method=gear maxord=2 reltol=2e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-16 itl4=280",
        f".model DVAR D(Is={spice_num(var.is_a)} Rs={spice_num(var.rs_ohm)} Cjo={spice_num(var.cjo_f)} Vj={spice_num(var.vj_v)} M={spice_num(var.m)} Bv={spice_num(var.bv_v)} Ibv={spice_num(var.ibv_a)})",
        f".param kmag={spice_num(kmag)}",
        f".param gcore={spice_num(gcore)}",
        f"Vbias vb 0 DC {spice_num(case.bias_v)}",
        f"Vsrc src 0 SIN(0 {spice_num(case.source_amplitude_v)} {spice_num(SOURCE_HZ)})",
        f"Rsrc src {design.n(0)} {spice_num(case.z0_ohm)}",
        f"Rrawload {raw_out} 0 {spice_num(case.z0_ohm * 3.0)}",
    ]
    if case.direct_generated_amplitude_v > 0.0:
        lines.extend(
            [
                f"Vgen gen_src 0 SIN(0 {spice_num(case.direct_generated_amplitude_v)} {spice_num(GENERATED_HZ)})",
                f"Rgen gen_src {design.n(0)} {spice_num(case.z0_ohm * 1.25)}",
            ]
        )
    if case.fixed_cap_only or 0 not in varactor_nodes:
        lines.append(f"Cbase0 {design.n(0)} 0 {spice_num(vals['c_linear_control_f'])}")
    else:
        lines.append(f"Cfixed0 {design.n(0)} 0 {spice_num(vals['c_fixed_f'])}")
        lines.append(f"Dvar0 {design.n(0)} vb DVAR")
    lines.append(f"Rbleed0 {design.n(0)} 0 {spice_num(case.shunt_loss_ohm)}")

    for i in range(1, case.cell_count + 1):
        lines.extend(
            [
                f"Rser{i} {design.n(i - 1)} ns{i} {spice_num(vals['r_series_ohm'])}",
                f"Lser{i} ns{i} {design.n(i)} {spice_num(vals['l_cell_h'])}",
            ]
        )
        if case.fixed_cap_only or i not in varactor_nodes:
            cap = vals["c_linear_control_f"] if case.fixed_cap_only else vals["c_cell_f"]
            lines.append(f"Cbase{i} {design.n(i)} 0 {spice_num(cap)}")
        else:
            fixed_scale = 0.95 if case.stacked_varactor_pairs > 1 else 1.0
            lines.append(f"Cfixed{i} {design.n(i)} 0 {spice_num(vals['c_fixed_f'] * fixed_scale)}")
            if case.stacked_varactor_pairs > 1:
                lines.append(f"Dvar{i}a {design.n(i)} vst{i} DVAR")
                lines.append(f"Dvar{i}b vst{i} vb DVAR")
                lines.append(f"Rstack{i} vst{i} vb {spice_num(2.0e6)}")
            else:
                lines.append(f"Dvar{i} {design.n(i)} vb DVAR")
        lines.append(f"Rbleed{i} {design.n(i)} 0 {spice_num(case.shunt_loss_ohm)}")

    for i in magnetic_nodes:
        sign = qpm_sign(case, i)
        phase = 1.0 + 0.18 * math.sin(case.hybrid_relative_phase + i / max(case.cell_count, 1))
        sat = max(case.magnetic_saturation_current_a, 0.02)
        node = design.n(i)
        lines.append(
            f"Bmag{i} {node} 0 I={{({spice_num(sign * phase * bias_shift)})*kmag*V({node})*V({node})*V({node})/(1+(V({node})/{spice_num(sat * case.z0_ohm)})**2) + gcore*V({node})}}"
        )

    measure = add_hybrid_cleanup(lines, case, raw_out)
    if measure == raw_out:
        lines.append(f"Rload {raw_out} 0 {spice_num(case.output_load_ohm)}")

    lines.extend(
        [
            ".control",
            "set filetype=ascii",
            "set wr_singlescale",
            "set wr_vecnames",
            f"tran {spice_num(design.TSTEP_S)} {spice_num(design.TSTOP_S)} 0 {spice_num(design.TMAX_STEP_S)}",
            f"wrdata {csv_path.name} time v({design.n(0)}) v({design.n(mid)}) v({measure}) i(Vsrc) i(Vbias)",
            ".endc",
            ".end",
            "",
        ]
    )
    return "\n".join(lines)


def make_case(
    case_id: str,
    placement: str,
    cells: int = 96,
    z0: float = 75.0,
    length_m: float = 0.50,
    drive_v: float = 2.5,
    bias_v: float = 3.4,
    nonlinear: float = 0.82,
    cjo_scale: float = 1.35,
    rs: float = 0.34,
    vj: float = 0.65,
    m: float = 0.58,
    magnetic_strength: float = 0.55,
    magnetic_sat_i: float = 0.10,
    magnetic_loss: float = 0.25,
    curve: str = "soft",
    cleanup: str = "extraction_plus_rejection",
    extraction_q: float = 18.0,
    output_load: float | None = None,
    target_scale: float = 1.0,
    generated_scale: float = 1.0,
    phase_velocity_m_s: float = 5.0e6,
    source_rej: bool = True,
    gen_rej: bool = True,
    post_filter: float = 0.0,
    extraction_position: str = "end",
    varactor_spacing: int = 1,
    magnetic_spacing: int = 4,
    magnetic_count: int = 18,
    stacked_pairs: int = 1,
    stress_strategy: str = "baseline",
    source_trap: float = 1.0,
    generated_trap: float = 1.0,
    fixed_cap_only: bool = False,
    source_only: bool = True,
    direct_100_v: float = 0.0,
    role: str = "discovery",
    family: str = "hybrid_varactor_plus_magnetic_line",
    notes: str = "",
) -> HybridMagneticCase:
    name = f"{case_id}_{placement}_{cells}c_{int(z0)}ohm"
    return HybridMagneticCase(
        case_id=case_id,
        name=clean_name(name),
        filename=f"{clean_name(name)}.cir",
        role=role,
        family=family,
        cell_count=cells,
        z0_ohm=z0,
        total_length_m=length_m,
        phase_velocity_m_s=phase_velocity_m_s,
        source_amplitude_v=drive_v,
        bias_v=bias_v,
        nonlinear_fraction=nonlinear,
        cjo_scale=cjo_scale,
        varactor_rs_ohm=rs,
        varactor_vj_v=vj,
        varactor_m=m,
        output_load_ohm=output_load if output_load is not None else z0 * 2.0,
        extraction_q=extraction_q,
        cleanup_topology=cleanup,
        source_rejection=source_rej,
        generated_rejection=gen_rej,
        target_phase_velocity_scale=target_scale,
        generated_phase_velocity_scale=generated_scale,
        fixed_cap_only=fixed_cap_only,
        source_only_drive=source_only,
        direct_100_drive_present=direct_100_v > 0.0,
        direct_generated_amplitude_v=direct_100_v,
        behavioral_helper=not fixed_cap_only and magnetic_strength > 0.0,
        series_loss_ohm_scale=1.0 + 0.35 * max(magnetic_loss, 0.0),
        shunt_loss_ohm=200_000.0 / max(1.0, 1.0 + magnetic_loss),
        phase_velocity_error_50=(phase_velocity_m_s - 5.0e6) / 5.0e6,
        phase_velocity_error_100=generated_scale - 1.0,
        phase_velocity_error_150=target_scale - 1.0,
        phase_velocity_trim_50=(phase_velocity_m_s - 5.0e6) / 5.0e6,
        phase_velocity_trim_100=generated_scale - 1.0,
        phase_velocity_trim_150=target_scale - 1.0,
        source_generator_rejection_strength=source_trap + generated_trap,
        target_bandpass_coupling=extraction_q / 30.0 if cleanup != "none" else 0.0,
        terminal_matching_scale=(output_load if output_load is not None else z0 * 2.0) / max(z0, EPS),
        nonlinear_strength_scale=nonlinear,
        magnetic_strength=magnetic_strength,
        magnetic_saturation_current_a=magnetic_sat_i,
        magnetic_hysteresis_loss=magnetic_loss,
        hybrid_relative_phase=0.45,
        alternating_nonlinear_sections=placement == "alternating_varactor_magnetic_cells",
        qpm_sign_flip=placement == "qpm_sign_flipped_hybrid_sections",
        varactor_stack="stacked_pairs" if stacked_pairs > 1 else "single",
        anti_series_varactors=stacked_pairs > 1,
        notes=notes or "Focused hybrid varactor-plus-magnetic refinement row.",
        hybrid_section_placement=placement,
        magnetic_saturation_curve=curve,
        magnetic_section_count=magnetic_count,
        magnetic_section_spacing=magnetic_spacing,
        magnetic_dc_bias_proxy=0.15 if stress_strategy == "magnetic_bias_shift" else 0.0,
        magnetic_core_loss_proxy=magnetic_loss,
        varactor_capacitance_swing_ratio=cjo_scale,
        varactor_reverse_bias_v=bias_v,
        varactor_section_count=cells // max(1, varactor_spacing),
        varactor_section_spacing=varactor_spacing,
        stacked_varactor_pairs=stacked_pairs,
        phase_trim_family="trimmed" if any(abs(x - 1.0) > 1.0e-9 for x in (target_scale, generated_scale)) else "baseline",
        group_delay_match_score=max(0.0, 1.0 - (abs(generated_scale - 1.0) + abs(target_scale - 1.0) + abs((phase_velocity_m_s - 5.0e6) / 5.0e6))),
        target_extraction_position=extraction_position,
        post_filter_strength=post_filter,
        source_rejection_trap_strength=source_trap,
        generated_rejection_trap_strength=generated_trap,
        stress_reduction_strategy=stress_strategy,
    )


def build_cases(max_discovery_cases: int | None = None) -> List[HybridMagneticCase]:
    discovery = [
        make_case("h001", "varactor_first_then_magnetic", notes="Placement sweep: varactor section before magnetic section."),
        make_case("h002", "magnetic_first_then_varactor", magnetic_strength=0.65, notes="Placement sweep: magnetic section before varactor section."),
        make_case("h003", "alternating_varactor_magnetic_cells", magnetic_spacing=3, magnetic_count=28, notes="Placement sweep: alternating cells."),
        make_case("h004", "grouped_varactor_then_magnetic", cells=128, z0=100.0, length_m=0.62, drive_v=2.25, magnetic_strength=0.75, magnetic_count=24, notes="Grouped varactor cells followed by magnetic cells."),
        make_case("h005", "grouped_magnetic_then_varactor", cells=128, z0=100.0, length_m=0.62, drive_v=2.25, magnetic_strength=0.75, magnetic_count=24, notes="Grouped magnetic cells followed by varactor cells."),
        make_case("h006", "qpm_sign_flipped_hybrid_sections", cells=96, z0=75.0, magnetic_strength=0.70, magnetic_count=32, post_filter=0.6, notes="QPM-like sign-flipped hybrid sections."),
        make_case("h007", "middle_third_only", cells=96, magnetic_strength=0.95, magnetic_count=18, drive_v=2.7, notes="Nonlinear sections only in the middle third."),
        make_case("h008", "near_target_extraction_only", cells=96, magnetic_strength=0.90, magnetic_count=18, post_filter=1.0, extraction_position="before_final_absorber", notes="Nonlinear sections concentrated near target extraction."),
        make_case("h009", "alternating_varactor_magnetic_cells", cells=64, z0=50.0, magnetic_strength=0.45, curve="soft", magnetic_sat_i=0.06, cjo_scale=1.50, drive_v=2.7, notes="Magnetic saturation sweep: lower saturation current."),
        make_case("h010", "alternating_varactor_magnetic_cells", cells=80, z0=75.0, magnetic_strength=1.10, curve="hard", magnetic_sat_i=0.14, magnetic_loss=0.35, notes="Magnetic saturation sweep: harder saturation curve."),
        make_case("h011", "alternating_varactor_magnetic_cells", cells=96, z0=75.0, magnetic_strength=0.85, curve="soft", magnetic_sat_i=0.12, magnetic_loss=0.55, notes="Magnetic loss/hysteresis proxy sweep."),
        make_case("h012", "alternating_varactor_magnetic_cells", cells=96, z0=75.0, magnetic_strength=0.70, magnetic_sat_i=0.12, stress_strategy="magnetic_bias_shift", notes="Magnetic DC bias proxy sweep."),
        make_case("h013", "alternating_varactor_magnetic_cells", cells=96, z0=75.0, cjo_scale=1.70, bias_v=2.7, rs=0.28, m=0.62, notes="Varactor sweep: larger capacitance swing."),
        make_case("h014", "alternating_varactor_magnetic_cells", cells=96, z0=75.0, cjo_scale=1.10, bias_v=5.5, rs=0.42, m=0.48, magnetic_strength=0.80, notes="Varactor sweep: lower swing and higher reverse bias."),
        make_case("h015", "alternating_varactor_magnetic_cells", cells=128, z0=100.0, length_m=0.72, drive_v=2.0, cjo_scale=1.35, stacked_pairs=2, magnetic_strength=0.80, post_filter=0.8, stress_strategy="stacked_varactors_longer_line", notes="Stress reduction with stacked varactors and longer line."),
        make_case("h016", "alternating_varactor_magnetic_cells", cells=64, z0=50.0, target_scale=0.990, generated_scale=1.005, phase_velocity_m_s=5.12e6, extraction_q=22.0, post_filter=0.8, notes="Phase velocity trim sweep: 64-cell low-Z line."),
        make_case("h017", "alternating_varactor_magnetic_cells", cells=80, z0=75.0, target_scale=0.985, generated_scale=1.010, phase_velocity_m_s=5.20e6, extraction_q=24.0, post_filter=1.0, notes="Phase velocity trim sweep: 80-cell line."),
        make_case("h018", "alternating_varactor_magnetic_cells", cells=96, z0=75.0, target_scale=0.982, generated_scale=1.012, phase_velocity_m_s=5.25e6, extraction_q=28.0, output_load=180.0, post_filter=1.2, source_trap=1.4, generated_trap=1.4, notes="Target cleanup sweep: stronger extraction/rejection."),
        make_case("h019", "alternating_varactor_magnetic_cells", cells=128, z0=100.0, length_m=0.76, target_scale=0.986, generated_scale=1.006, phase_velocity_m_s=5.18e6, extraction_q=30.0, output_load=240.0, post_filter=1.4, stacked_pairs=2, drive_v=2.15, magnetic_strength=0.78, notes="Long high-impedance phase/purity cleanup row."),
        make_case("h020", "near_target_extraction_only", cells=128, z0=75.0, length_m=0.68, target_scale=0.980, generated_scale=1.008, extraction_q=34.0, output_load=200.0, post_filter=1.6, source_trap=1.8, generated_trap=1.8, magnetic_strength=0.95, magnetic_count=24, notes="Aggressive target extraction and rejection cleanup."),
        make_case("h021", "qpm_sign_flipped_hybrid_sections", cells=128, z0=75.0, length_m=0.70, target_scale=0.984, generated_scale=1.004, extraction_q=30.0, output_load=190.0, post_filter=1.4, magnetic_strength=0.90, magnetic_count=36, notes="QPM sign-flip plus target cleanup."),
        make_case("h022", "middle_third_only", cells=128, z0=100.0, length_m=0.80, drive_v=1.9, cjo_scale=1.45, stacked_pairs=2, magnetic_strength=0.95, magnetic_count=22, target_scale=0.990, extraction_q=26.0, post_filter=1.0, stress_strategy="lower_drive_longer_line", notes="Stress reduction: lower drive and longer line."),
        make_case("h023", "varactor_first_then_magnetic", drive_v=2.5, cjo_scale=1.45, bias_v=3.2, target_scale=0.995, generated_scale=1.003, phase_velocity_m_s=5.08e6, extraction_q=20.0, output_load=160.0, magnetic_strength=0.60, notes="Targeted near-miss probe: mild phase trim and varactor-first placement."),
        make_case("h024", "varactor_first_then_magnetic", drive_v=2.6, cjo_scale=1.50, bias_v=3.1, target_scale=0.995, generated_scale=1.003, phase_velocity_m_s=5.08e6, extraction_q=18.0, output_load=150.0, magnetic_strength=0.65, notes="Targeted purity probe: stronger swing with mild phase trim."),
        make_case("h025", "varactor_first_then_magnetic", drive_v=2.7, cjo_scale=1.35, bias_v=3.4, target_scale=0.995, generated_scale=1.003, phase_velocity_m_s=5.08e6, extraction_q=18.0, output_load=150.0, magnetic_strength=0.55, notes="Targeted growth probe: preserves coherent growth with mild phase trim."),
    ]
    if max_discovery_cases is not None:
        discovery = discovery[:max_discovery_cases]

    base = make_case(
        "base",
        "alternating_varactor_magnetic_cells",
        role="control",
        notes="Control base derived from race winner.",
    )
    controls = [
        replace(base, case_id="c001", name="linear_fixed_component_line", filename="linear_fixed_component_line.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.0, family="linear_fixed_component_line", notes="Linear fixed-component line control."),
        replace(base, case_id="c002", name="varactor_only_line", filename="varactor_only_line.cir", magnetic_strength=0.0, magnetic_section_count=0, behavioral_helper=False, family="varactor_only_line", notes="Varactor-only control."),
        replace(base, case_id="c003", name="magnetic_only_line", filename="magnetic_only_line.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.85, family="magnetic_only_line", notes="Magnetic-only control."),
        replace(base, case_id="c004", name="weak_hybrid_line", filename="weak_hybrid_line.cir", nonlinear_fraction=0.10, cjo_scale=0.35, bias_v=14.0, magnetic_strength=0.08, magnetic_saturation_current_a=0.25, family="weak_hybrid_line", notes="Weak hybrid nonlinearity control."),
        replace(base, case_id="c005", name="detuned_150mhz_phase_velocity_line", filename="detuned_150mhz_phase_velocity_line.cir", target_phase_velocity_scale=0.82, phase_velocity_m_s=3.9e6, phase_velocity_error_50=-0.22, phase_velocity_error_150=-0.18, family="detuned_150mhz_phase_velocity_line", notes="Detuned 150 MHz phase-velocity control."),
        replace(base, case_id="c006", name="shuffled_frequency_line", filename="shuffled_frequency_line.cir", generated_phase_velocity_scale=0.88, target_phase_velocity_scale=1.12, phase_velocity_m_s=6.5e6, phase_velocity_error_50=0.30, phase_velocity_error_100=-0.12, phase_velocity_error_150=0.12, family="shuffled_frequency_line", notes="Shuffled frequency mapping control."),
        replace(base, case_id="c007", name="too_short_line", filename="too_short_line.cir", total_length_m=0.05, family="too_short_line", notes="Too-short interaction length control."),
        replace(base, case_id="c008", name="too_lossy_line", filename="too_lossy_line.cir", series_loss_ohm_scale=30.0, shunt_loss_ohm=10_000.0, magnetic_core_loss_proxy=2.0, magnetic_hysteresis_loss=1.0, family="too_lossy_line", notes="Too-lossy line control."),
        replace(base, case_id="c009", name="phase_mismatched_hybrid_line", filename="phase_mismatched_hybrid_line.cir", generated_phase_velocity_scale=0.91, target_phase_velocity_scale=1.22, phase_velocity_m_s=4.1e6, phase_velocity_error_50=-0.18, phase_velocity_error_100=-0.09, phase_velocity_error_150=0.22, family="phase_mismatched_hybrid_line", notes="Phase-mismatched hybrid control."),
        replace(base, case_id="c010", name="target_extraction_no_nonlinearity", filename="target_extraction_no_nonlinearity.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.0, family="target_extraction_no_nonlinearity", notes="Target extraction with no nonlinearity control."),
        replace(base, case_id="c011", name="hybrid_nonlinearity_no_target_extraction", filename="hybrid_nonlinearity_no_target_extraction.cir", cleanup_topology="none", source_rejection=False, generated_rejection=False, post_filter_strength=0.0, family="hybrid_nonlinearity_no_target_extraction", notes="Hybrid nonlinearity with target extraction removed."),
        replace(
            base,
            case_id="direct_50plus100_reference",
            name="direct_50plus100_reference",
            filename="direct_50plus100_reference.cir",
            role="ceiling_reference",
            source_only_drive=False,
            direct_100_drive_present=True,
            direct_generated_amplitude_v=1.0,
            magnetic_strength=0.0,
            magnetic_section_count=0,
            behavioral_helper=False,
            family="direct_50plus100_reference",
            notes="Separated direct 50+100 MHz ceiling denominator only.",
        ),
    ]
    return discovery + controls


def export_netlists(out_dir: Path, max_discovery_cases: int | None = None) -> List[HybridMagneticExport]:
    ensure_dir(out_dir)
    exports: List[HybridMagneticExport] = []
    for case in build_cases(max_discovery_cases=max_discovery_cases):
        netlist_path = out_dir / case.filename
        csv_path = out_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist_path.write_text(netlist_for_case(case, csv_path), encoding="utf-8")
        exports.append(HybridMagneticExport(case, netlist_path, csv_path))
    return exports


def run_ngspice(export: HybridMagneticExport, ngspice_path: str, timeout_s: int) -> design.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = design.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return design.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def accumulated_phase_mismatch(case: HybridMagneticCase) -> float:
    wavelength = case.phase_velocity_m_s / SOURCE_HZ
    trim = abs(case.phase_velocity_error_50) + abs(case.phase_velocity_error_100) + abs(case.phase_velocity_error_150)
    return float(2.0 * math.pi * case.total_length_m / max(wavelength, EPS) * trim)


def behavioral_dependency(case: HybridMagneticCase) -> float:
    if case.fixed_cap_only and case.magnetic_strength == 0.0:
        return 0.02
    score = 0.08
    if case.magnetic_strength > 0.0:
        score += 0.10
    if case.post_filter_strength > 0.0:
        score += 0.01
    if case.band_shunts:
        score += 0.03
    if case.behavioral_helper:
        score += 0.02
    return min(score, 0.28)


def measure_case(export: HybridMagneticExport, data: Dict[str, np.ndarray], reference_power: float | None) -> Dict[str, object]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    metrics = design.measure_case(shim, data, reference_power)
    case = export.case
    beh = behavioral_dependency(case)
    magnetic_current = max(safe_float(metrics.get("source_peak_current_a")), safe_float(metrics.get("varactor_peak_current_a"))) / max(1, case.magnetic_section_count)
    saturation_margin = case.magnetic_saturation_current_a / max(magnetic_current, EPS) if case.magnetic_strength else 999.0
    varactor_voltage = safe_float(metrics.get("varactor_peak_voltage_v"))
    varactor_current = safe_float(metrics.get("varactor_peak_current_a"))
    target_power = safe_float(metrics.get("target_fft_power"))
    source_power = safe_float(metrics.get("source_fft_power"))
    generated_power = safe_float(metrics.get("generated_fft_power"))
    target_rejection_db = 10.0 * math.log10(max(target_power, EPS) / max(source_power + generated_power, EPS))
    extraction_gain = target_power / max(source_power + generated_power, EPS)

    metrics.update(
        {
            "family": case.family,
            "hybrid_section_placement": case.hybrid_section_placement,
            "magnetic_saturation_curve": case.magnetic_saturation_curve,
            "magnetic_section_count": case.magnetic_section_count,
            "magnetic_section_spacing": case.magnetic_section_spacing,
            "magnetic_strength": case.magnetic_strength,
            "magnetic_saturation_current_a": case.magnetic_saturation_current_a,
            "magnetic_peak_current_a": magnetic_current,
            "saturation_margin": saturation_margin,
            "hysteresis_loss_proxy": case.magnetic_hysteresis_loss,
            "magnetic_core_loss_proxy": case.magnetic_core_loss_proxy,
            "magnetic_dc_bias_proxy": case.magnetic_dc_bias_proxy,
            "varactor_capacitance_swing_ratio": case.varactor_capacitance_swing_ratio,
            "varactor_reverse_bias_v": case.varactor_reverse_bias_v,
            "varactor_peak_voltage_v": varactor_voltage,
            "varactor_peak_current_a": varactor_current,
            "stacked_varactor_pairs": case.stacked_varactor_pairs,
            "varactor_section_count": case.varactor_section_count,
            "varactor_section_spacing": case.varactor_section_spacing,
            "phase_velocity_error_50": case.phase_velocity_error_50,
            "phase_velocity_error_100": case.phase_velocity_error_100,
            "phase_velocity_error_150": case.phase_velocity_error_150,
            "accumulated_phase_mismatch": accumulated_phase_mismatch(case),
            "group_delay_match_score": case.group_delay_match_score,
            "target_extraction_gain": extraction_gain,
            "target_rejection_source_generated_db": target_rejection_db,
            "target_extraction_position": case.target_extraction_position,
            "post_filter_strength": case.post_filter_strength,
            "source_rejection_trap_strength": case.source_rejection_trap_strength,
            "generated_rejection_trap_strength": case.generated_rejection_trap_strength,
            "behavioral_dependency_score": beh,
            "stress_reduction_strategy": case.stress_reduction_strategy,
        }
    )

    stress_score = safe_float(metrics.get("component_stress_score"))
    if case.stacked_varactor_pairs > 1:
        stress_score *= 0.82
    if case.stress_reduction_strategy in {"lower_drive_longer_line", "stacked_varactors_longer_line"}:
        stress_score *= 0.90
    metrics["component_stress_score"] = stress_score
    if stress_score < 0.75 and safe_float(metrics.get("reverse_bias_margin_v")) > 0.25:
        metrics["component_stress_class"] = "plausible"
    elif stress_score < 1.35 and safe_float(metrics.get("reverse_bias_margin_v")) > -0.5:
        metrics["component_stress_class"] = "aggressive-but-testable"
    else:
        metrics["component_stress_class"] = "unrealistic"

    stress_ok = str(metrics.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}
    lock = safe_float(metrics.get("phase_lock_target"))
    bridge = safe_float(metrics.get("bridge_ratio_vs_direct_reference"))
    purity = safe_float(metrics.get("spectral_purity_150mhz"))
    growth = safe_float(metrics.get("target_band_coherent_growth"))
    gen_cv = safe_float(metrics.get("generated_envelope_cv"), 99.0)
    jump = safe_float(metrics.get("max_phase_jump"), 99.0)
    if case.role == "discovery":
        if not stress_ok:
            promotion = "reject_due_to_component_stress"
        elif lock > 0.90 and bridge > 1.5 and purity > 0.80 and growth > 1.0 and gen_cv < 0.25 and jump < 1.0 and beh <= 0.20:
            promotion = "spice_hybrid_magnetic_412_candidate"
        elif lock > 0.85 and bridge > 1.0 and purity > 0.30 and stress_ok:
            promotion = "spice_hybrid_magnetic_412_near_miss"
        elif purity <= 0.30:
            promotion = "reject_due_to_low_purity"
        elif lock <= 0.85 or jump >= 1.0:
            promotion = "reject_due_to_phase_mismatch"
        else:
            promotion = "not_promoted"
    elif case.role == "control":
        material_leak = 0.0
        if purity > 0.20 and bridge > 1.0 and growth > 1.0 and lock > 0.50:
            material_leak = min(1.0, max(bridge - 1.0, 0.0) / 2.0 + max(purity - 0.20, 0.0))
        metrics["control_leakage_score"] = material_leak
        promotion = "control_dead" if material_leak < 0.15 else "reject_due_to_control_leakage"
    else:
        promotion = "ceiling_reference_not_discovery"
    metrics["promotion_category"] = promotion
    return metrics


def summarize_export(
    export: HybridMagneticExport,
    run_requested: bool,
    ngspice_available: bool,
    ngspice_path: str | None,
    result: design.RunResult,
    metrics: Dict[str, object] | None,
) -> Dict[str, object]:
    vals = hybrid_cell_values(export.case)
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_hybrid_magnetic_412_refine",
        "case_id": case.case_id,
        "name": case.name,
        "family": case.family,
        "role": case.role,
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
        "cell_count": case.cell_count,
        "z0_target_ohm": case.z0_ohm,
        "total_length_m": case.total_length_m,
        "cell_length_m": vals["dx_m"],
        "per_cell_inductance_h": vals["l_cell_h"],
        "per_cell_total_capacitance_f": vals["c_cell_f"],
        "source_frequency_hz": SOURCE_HZ,
        "generated_frequency_hz": GENERATED_HZ,
        "target_frequency_hz": TARGET_HZ,
        "source_amplitude_v": case.source_amplitude_v,
        "bias_v": case.bias_v,
        "nonlinear_fraction": case.nonlinear_fraction,
        "varactor_cjo_f": vals["cjo_f"],
        "varactor_rs_ohm": case.varactor_rs_ohm,
        "varactor_vj_v": case.varactor_vj_v,
        "varactor_m": case.varactor_m,
        "stacked_varactor_pairs": case.stacked_varactor_pairs,
        "hybrid_section_placement": case.hybrid_section_placement,
        "magnetic_saturation_curve": case.magnetic_saturation_curve,
        "cleanup_topology": case.cleanup_topology,
        "target_extraction_position": case.target_extraction_position,
        "post_filter_strength": case.post_filter_strength,
        "output_load_ohm": case.output_load_ohm,
        "target_extraction_q": case.extraction_q,
        "source_rejection": str(case.source_rejection),
        "generated_rejection": str(case.generated_rejection),
        "fixed_cap_only": str(case.fixed_cap_only),
        "behavioral_helper_present": str(case.behavioral_helper),
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
    elif result.execution_status in {"failed_to_converge", "parser_failed"} and case.role == "discovery":
        row["promotion_category"] = "reject_due_to_convergence"
    return row


def best_by(rows: Iterable[Dict[str, object]], *keys: str) -> Dict[str, object]:
    return max(rows, key=lambda row: tuple(safe_float(row.get(k)) for k in keys), default={})


def category_best(
    rows: List[Dict[str, object]],
    selector_key: str,
    selector_value: str,
    score_key: str = "spectral_purity_150mhz",
) -> Dict[str, object]:
    selected = [
        row
        for row in rows
        if row.get("execution_status") == "ran_successfully" and str(row.get(selector_key)) == selector_value
    ]
    return max(selected, key=lambda row: safe_float(row.get(score_key)), default={})


def aggregate_summary(rows: List[Dict[str, object]], run_requested: bool, ngspice_available: bool) -> Dict[str, object]:
    data = [row for row in rows if row.get("row_type") == "spice_hybrid_magnetic_412_refine"]
    discovery = [row for row in data if row.get("role") == "discovery"]
    controls = [row for row in data if row.get("role") == "control"]
    ran = [row for row in data if row.get("execution_status") == "ran_successfully"]
    successful_discovery = [row for row in discovery if row.get("execution_status") == "ran_successfully"]
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls if row.get("execution_status") == "ran_successfully")
    max_leak = max((safe_float(row.get("control_leakage_score")) for row in controls), default=0.0)
    candidates = [row for row in successful_discovery if row.get("promotion_category") == "spice_hybrid_magnetic_412_candidate"] if controls_dead else []
    near = [row for row in successful_discovery if row.get("promotion_category") == "spice_hybrid_magnetic_412_near_miss"] if controls_dead else []
    plausible = [row for row in successful_discovery if str(row.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}]
    best = max(
        successful_discovery,
        key=lambda row: (
            safe_float(row.get("spectral_purity_150mhz")),
            safe_float(row.get("bridge_ratio_vs_direct_reference")),
            safe_float(row.get("phase_lock_target")),
            -safe_float(row.get("behavioral_dependency_score"), 1.0),
        ),
        default={},
    )
    best_purity_plausible = max(plausible, key=lambda row: safe_float(row.get("spectral_purity_150mhz")), default={})
    best_bridge_clean = max(plausible, key=lambda row: safe_float(row.get("bridge_ratio_vs_direct_reference")), default={})
    best_lock = max(successful_discovery, key=lambda row: safe_float(row.get("phase_lock_target")), default={})
    extraction_rows = [row for row in successful_discovery if row.get("cleanup_topology") != "none"]
    no_extraction_rows = [row for row in successful_discovery if row.get("cleanup_topology") == "none"]
    extraction_best = max((safe_float(row.get("spectral_purity_150mhz")) for row in extraction_rows), default=0.0)
    no_extraction_best = max((safe_float(row.get("spectral_purity_150mhz")) for row in no_extraction_rows), default=0.0)

    placements = sorted(set(str(row.get("hybrid_section_placement")) for row in successful_discovery))
    placement_summary = {
        placement: {
            "best_case": category_best(successful_discovery, "hybrid_section_placement", placement).get("case_id", ""),
            "best_purity": category_best(successful_discovery, "hybrid_section_placement", placement).get("spectral_purity_150mhz", 0.0),
            "best_bridge": category_best(successful_discovery, "hybrid_section_placement", placement, "bridge_ratio_vs_direct_reference").get("bridge_ratio_vs_direct_reference", 0.0),
        }
        for placement in placements
    }
    pure_varactor = category_best(data, "family", "varactor_only_line")
    pure_magnetic = category_best(data, "family", "magnetic_only_line")
    hybrid_beats_controls = bool(
        safe_float(best.get("spectral_purity_150mhz")) > max(
            safe_float(pure_varactor.get("spectral_purity_150mhz")),
            safe_float(pure_magnetic.get("spectral_purity_150mhz")),
        )
        and safe_float(best.get("bridge_ratio_vs_direct_reference")) > max(
            safe_float(pure_varactor.get("bridge_ratio_vs_direct_reference")),
            safe_float(pure_magnetic.get("bridge_ratio_vs_direct_reference")),
        )
    )
    factor_scores = {
        "hybrid_section_placement": max((safe_float(v.get("best_purity")) for v in placement_summary.values()), default=0.0),
        "magnetic_saturation_curve": max((safe_float(row.get("spectral_purity_150mhz")) for row in successful_discovery if str(row.get("notes", "")).lower().find("magnetic") >= 0), default=0.0),
        "varactor_swing": max((safe_float(row.get("spectral_purity_150mhz")) for row in successful_discovery if str(row.get("notes", "")).lower().find("varactor") >= 0), default=0.0),
        "phase_velocity_trim": max((safe_float(row.get("spectral_purity_150mhz")) for row in successful_discovery if str(row.get("phase_trim_family")) == "trimmed"), default=0.0),
        "target_extraction": extraction_best,
    }
    most_important = max(factor_scores, key=factor_scores.get) if factor_scores else "unknown"
    statuses = ";".join(sorted(set(str(row.get("execution_status")) for row in data)))
    recommended = (
        "component/BOM selection and PCB layout model"
        if candidates
        else "hybrid magnetic component refinement plus acoustic demo branch before PCB layout"
    )
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
        "candidate_count": len(candidates),
        "near_miss_count": len(near),
        "best_case": best.get("case_id", ""),
        "best_name": best.get("name", ""),
        "best_placement": best.get("hybrid_section_placement", ""),
        "best_lock": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio_vs_direct_reference", ""),
        "best_purity": best.get("spectral_purity_150mhz", ""),
        "best_target_growth": best.get("target_band_coherent_growth", ""),
        "best_generated_cv": best.get("generated_envelope_cv", ""),
        "best_max_phase_jump": best.get("max_phase_jump", ""),
        "best_stress_class": best.get("component_stress_class", ""),
        "best_stress_score": best.get("component_stress_score", ""),
        "best_behavioral_dependency": best.get("behavioral_dependency_score", ""),
        "best_purity_plausible_case": best_purity_plausible.get("case_id", ""),
        "best_purity_plausible_value": best_purity_plausible.get("spectral_purity_150mhz", ""),
        "best_bridge_clean_case": best_bridge_clean.get("case_id", ""),
        "best_bridge_clean_value": best_bridge_clean.get("bridge_ratio_vs_direct_reference", ""),
        "best_lock_case": best_lock.get("case_id", ""),
        "best_lock_value": best_lock.get("phase_lock_target", ""),
        "purity_above_0p30_count": len([row for row in plausible if safe_float(row.get("spectral_purity_150mhz")) > 0.30]),
        "purity_above_0p80_count": len([row for row in plausible if safe_float(row.get("spectral_purity_150mhz")) > 0.80]),
        "controls_dead": str(controls_dead) if ran else "not_run",
        "max_control_leakage_score": max_leak,
        "target_extraction_best_purity": extraction_best,
        "no_target_extraction_best_purity": no_extraction_best,
        "target_extraction_helped_purity": str(extraction_best > no_extraction_best),
        "hybrid_beats_pure_varactor_and_pure_magnetic": str(hybrid_beats_controls),
        "pure_varactor_control_purity": pure_varactor.get("spectral_purity_150mhz", ""),
        "pure_varactor_control_bridge": pure_varactor.get("bridge_ratio_vs_direct_reference", ""),
        "pure_magnetic_control_purity": pure_magnetic.get("spectral_purity_150mhz", ""),
        "pure_magnetic_control_bridge": pure_magnetic.get("bridge_ratio_vs_direct_reference", ""),
        "placement_summary_json": json.dumps(placement_summary, sort_keys=True),
        "factor_scores_json": json.dumps(factor_scores, sort_keys=True),
        "most_important_factor_first_pass": most_important,
        "recommended_next_step": recommended,
    }


def timeseries_rows(export: HybridMagneticExport, data: Dict[str, np.ndarray], stride: int = 24) -> List[Dict[str, object]]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    rows = design.timeseries_rows(shim, data, stride=stride)
    for row in rows:
        row["row_type"] = "spice_hybrid_magnetic_412_refine_timeseries"
        row["family"] = export.case.family
        row["hybrid_section_placement"] = export.case.hybrid_section_placement
        row["cleanup_topology"] = export.case.cleanup_topology
    return rows


def write_report(out_dir: Path, rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    data = [row for row in rows if row.get("row_type") == "spice_hybrid_magnetic_412_refine"]
    lines = [
        "# SPICE 4->8->12 Hybrid Magnetic Refinement",
        "",
        "Focused refinement around the hybrid varactor-plus-magnetic race winner at 50/100/150 MHz.",
        "",
        "## Direct Answers",
        "",
        f"1. Can hybrid varactor-plus-magnetic raise 150 MHz purity above 0.30? count={aggregate.get('purity_above_0p30_count')}; best_purity={aggregate.get('best_purity')}.",
        f"2. Any full candidate with purity above 0.80? candidates={aggregate.get('candidate_count')}; purity_above_0.80_rows={aggregate.get('purity_above_0p80_count')}.",
        f"3. Most important first-pass factor: {aggregate.get('most_important_factor_first_pass')}; factor_scores={aggregate.get('factor_scores_json')}.",
        f"4. Do controls stay dead? {aggregate.get('controls_dead')}; max_leakage={aggregate.get('max_control_leakage_score')}.",
        f"5. Stress class: best={aggregate.get('best_stress_class')} score={aggregate.get('best_stress_score')}.",
        f"6. Does hybrid beat pure varactor and pure magnetic controls? {aggregate.get('hybrid_beats_pure_varactor_and_pure_magnetic')}; varactor_purity={aggregate.get('pure_varactor_control_purity')}; magnetic_purity={aggregate.get('pure_magnetic_control_purity')}.",
        f"7. Next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Best Row",
        "",
        (
            "- {case} {name}: placement={placement}, lock={lock}, bridge={bridge}, purity={purity}, "
            "growth={growth}, gen_cv={gen_cv}, max_jump={jump}, stress={stress}, behavioral={beh}."
        ).format(
            case=aggregate.get("best_case"),
            name=aggregate.get("best_name"),
            placement=aggregate.get("best_placement"),
            lock=aggregate.get("best_lock"),
            bridge=aggregate.get("best_bridge_ratio"),
            purity=aggregate.get("best_purity"),
            growth=aggregate.get("best_target_growth"),
            gen_cv=aggregate.get("best_generated_cv"),
            jump=aggregate.get("best_max_phase_jump"),
            stress=aggregate.get("best_stress_class"),
            beh=aggregate.get("best_behavioral_dependency"),
        ),
        "",
        "## Rows",
        "",
    ]
    for row in data:
        lines.append(
            "- {case_id} {family}: role={role}, status={status}, category={cat}, placement={placement}, "
            "cells={cells}, z0={z0}, lock={lock}, bridge={bridge}, purity={purity}, growth={growth}, "
            "gen_cv={gen_cv}, stress={stress}, behavioral={behavioral}.".format(
                case_id=row.get("case_id"),
                family=row.get("family"),
                role=row.get("role"),
                status=row.get("execution_status"),
                cat=row.get("promotion_category", ""),
                placement=row.get("hybrid_section_placement", ""),
                cells=row.get("cell_count", ""),
                z0=row.get("z0_target_ohm", ""),
                lock=row.get("phase_lock_target", ""),
                bridge=row.get("bridge_ratio_vs_direct_reference", ""),
                purity=row.get("spectral_purity_150mhz", ""),
                growth=row.get("target_band_coherent_growth", ""),
                gen_cv=row.get("generated_envelope_cv", ""),
                stress=row.get("component_stress_class", ""),
                behavioral=row.get("behavioral_dependency_score", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Circuit Notes",
            "",
            "- Discovery rows drive only the 50 MHz source band.",
            "- No discovery row uses direct 100 MHz drive, direct 150 MHz drive, target-frequency injection, or a hidden behavioral target source.",
            "- The direct 50+100 MHz reference is separated and used only as the bridge-ratio ceiling denominator.",
            "- Magnetic nonlinearity remains a labeled behavioral core proxy in this track and is included in the behavioral dependency score.",
            "- Passive 150 MHz extraction/rejection networks are cleanup/readout networks, not target-band sources.",
        ]
    )
    (out_dir / "README_SPICE_412_HYBRID_MAGNETIC_REFINE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Refine hybrid varactor-plus-magnetic 4->8->12 SPICE rows.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per netlist in seconds.")
    parser.add_argument("--max-discovery-cases", type=int, default=0, help="Limit discovery rows for debugging.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    max_discovery = args.max_discovery_cases if args.max_discovery_cases > 0 else None
    exports = export_netlists(out_dir, max_discovery_cases=max_discovery)
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
                    parsed[export.case.case_id] = design.read_transient(export.csv_path)
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
        reference_power = safe_float(ref_metrics.get("target_coherent_power"))

    summary_rows: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for export in exports:
        result = run_results[export.case.case_id]
        metrics: Dict[str, object] | None = None
        if result.success and export.case.case_id in parsed:
            metrics = measure_case(export, parsed[export.case.case_id], reference_power)
            if export.case.role in {"discovery", "ceiling_reference"}:
                timeseries.extend(timeseries_rows(export, parsed[export.case.case_id]))
        summary_rows.append(summarize_export(export, args.run, ngspice_available, ngspice_path, result, metrics))

    aggregate = aggregate_summary(summary_rows, args.run, ngspice_available)
    all_rows = [aggregate] + summary_rows
    write_csv(out_dir / "spice_412_hybrid_magnetic_refine_summary.csv", all_rows)
    if timeseries:
        write_csv(out_dir / "spice_412_hybrid_magnetic_refine_timeseries.csv", timeseries)
    elif (out_dir / "spice_412_hybrid_magnetic_refine_timeseries.csv").exists():
        (out_dir / "spice_412_hybrid_magnetic_refine_timeseries.csv").unlink()
    (out_dir / "spice_412_hybrid_magnetic_refine_summary.json").write_text(
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
        ),
        encoding="utf-8",
    )
    write_report(out_dir, all_rows, aggregate)
    print(
        "spice_412_hybrid_magnetic_refine: run={run} ngspice={ng} statuses={statuses} best={best} candidates={candidates} near={near}".format(
            run=args.run,
            ng=ngspice_available,
            statuses=aggregate["execution_statuses"],
            best=aggregate["best_name"],
            candidates=aggregate["candidate_count"],
            near=aggregate["near_miss_count"],
        )
    )


if __name__ == "__main__":
    main()
