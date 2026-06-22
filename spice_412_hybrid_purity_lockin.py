#!/usr/bin/env python3
"""Purity lock-in refinement for the hybrid 4->8->12 electrical route.

This script refines the h024/h025 hybrid varactor-plus-magnetic near-miss
basin.  It keeps discovery source-only at 50 MHz and focuses on passive
150 MHz extraction, phase-delay lock-in, and convergence/stress-managed
hybrid placement.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np

import spice_412_electrical_candidate_race as race
import spice_412_hybrid_magnetic_refine as hybrid
import spice_412_varactor_nltl_design as design
import spice_412_varactor_nltl_refine as refine


OUT_DIR = Path("runs") / "spice_412_hybrid_purity_lockin"
SOURCE_HZ = design.SOURCE_HZ
GENERATED_HZ = design.GENERATED_HZ
TARGET_HZ = design.TARGET_HZ
EPS = 1.0e-30


@dataclass(frozen=True)
class LockinCase(hybrid.HybridMagneticCase):
    extraction_topology: str = "single_high_q"
    extraction_stage_count: int = 1
    distributed_extraction_spacing: int = 0
    distributed_extraction_strength: float = 0.0
    pre_notch_50: bool = True
    pre_notch_100: bool = True
    notch_q_scale: float = 1.0
    extraction_q_label: str = "medium"
    phase_delay_cells_between_blocks: int = 0
    phase_delay_cells_before_extraction: int = 0
    phase_delay_scale: float = 1.0
    varactor_block_fraction: float = 0.50
    magnetic_block_start_fraction: float = 0.50
    magnetic_block_end_fraction: float = 1.00
    overlap_fraction: float = 0.06
    alternating_overlap_only: bool = False
    target_extraction_after_magnetic_block: bool = False
    source_rejection_db_proxy: float = 0.0
    generated_rejection_db_proxy: float = 0.0


@dataclass(frozen=True)
class LockinExport:
    case: LockinCase
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


def series_lc_values(freq_hz: float, c_f: float, q: float, r_floor: float = 0.35) -> Dict[str, float]:
    omega = 2.0 * math.pi * freq_hz
    l_h = 1.0 / max((omega ** 2) * c_f, EPS)
    r_ohm = max(r_floor, math.sqrt(max(l_h, EPS) / max(c_f, EPS)) / max(q, 0.5))
    return {"l_h": l_h, "c_f": c_f, "r_ohm": r_ohm}


def lockin_cell_values(case: LockinCase) -> Dict[str, float]:
    return refine.refine_cell_values(case)


def section_indices(case: LockinCase, kind: str) -> List[int]:
    cells = list(range(1, case.cell_count + 1))
    v_end = max(1, int(round(case.cell_count * case.varactor_block_fraction)))
    m_start = max(1, int(round(case.cell_count * case.magnetic_block_start_fraction)))
    m_end = min(case.cell_count, int(round(case.cell_count * case.magnetic_block_end_fraction)))
    overlap = max(0, int(round(case.cell_count * case.overlap_fraction)))
    if kind == "varactor":
        hi = min(case.cell_count, v_end + overlap)
        selected = [i for i in cells if i <= hi]
        selected = selected[:: max(1, case.varactor_section_spacing)]
        return selected[: max(1, case.varactor_section_count)]
    selected = [i for i in cells if m_start - overlap <= i <= m_end]
    selected = selected[:: max(1, case.magnetic_section_spacing)]
    if case.alternating_overlap_only:
        selected = [i for i in selected if i <= v_end + overlap or (i // max(1, case.magnetic_section_spacing)) % 2 == 0]
    return selected[: max(1, case.magnetic_section_count)]


def add_delay_section(lines: List[str], start_node: str, prefix: str, case: LockinCase, count: int) -> str:
    if count <= 0:
        return start_node
    vals = lockin_cell_values(case)
    prev = start_node
    l_delay = vals["l_cell_h"] * case.phase_delay_scale
    c_delay = vals["c_cell_f"] / max(case.phase_delay_scale, 0.2)
    r_delay = vals["r_series_ohm"] * 1.8
    for idx in range(1, count + 1):
        mid = f"{prefix}r{idx}"
        node = f"{prefix}n{idx}"
        lines.extend(
            [
                f"R{prefix}{idx} {prev} {mid} {spice_num(r_delay)}",
                f"L{prefix}{idx} {mid} {node} {spice_num(l_delay)}",
                f"C{prefix}{idx} {node} 0 {spice_num(c_delay)}",
                f"Rbleed{prefix}{idx} {node} 0 {spice_num(case.shunt_loss_ohm * 2.0)}",
            ]
        )
        prev = node
    return prev


def add_notches(lines: List[str], node: str, case: LockinCase) -> None:
    if case.pre_notch_50:
        notch = series_lc_values(SOURCE_HZ, 8.2e-12, 18.0 * case.notch_q_scale, 0.3)
        lines.extend(
            [
                f"Rlock50 {node} lk50r {spice_num(notch['r_ohm'])}",
                f"Llock50 lk50r lk50l {spice_num(notch['l_h'])}",
                f"Clock50 lk50l 0 {spice_num(notch['c_f'])}",
            ]
        )
    if case.pre_notch_100:
        notch = series_lc_values(GENERATED_HZ * case.generated_phase_velocity_scale, 6.2e-12, 18.0 * case.notch_q_scale, 0.3)
        lines.extend(
            [
                f"Rlock100 {node} lk100r {spice_num(notch['r_ohm'])}",
                f"Llock100 lk100r lk100l {spice_num(notch['l_h'])}",
                f"Clock100 lk100l 0 {spice_num(notch['c_f'])}",
            ]
        )


def add_lockin_cleanup(lines: List[str], case: LockinCase, raw_out: str) -> str:
    """Add passive 150 MHz extraction and purity-sharpening sections."""
    if case.cleanup_topology == "none":
        return raw_out

    if case.target_extraction_after_magnetic_block:
        tap_idx = min(case.cell_count, max(1, int(round(case.cell_count * case.magnetic_block_end_fraction))))
        tap = design.n(tap_idx)
    elif case.target_extraction_position == "before_final_absorber":
        tap = design.n(max(1, case.cell_count - max(2, case.cell_count // 12)))
    else:
        tap = raw_out

    tap = add_delay_section(lines, tap, "dpre", case, case.phase_delay_cells_before_extraction)
    add_notches(lines, tap, case)

    entry = tap
    if case.extraction_topology == "distributed":
        bus = "v150bus"
        spacing = max(4, case.distributed_extraction_spacing or 16)
        start = max(1, int(round(case.cell_count * 0.35)))
        nodes = list(range(start, case.cell_count + 1, spacing))
        q = max(8.0, case.extraction_q)
        c_base = case.extraction_c_f * max(0.18, case.distributed_extraction_strength)
        for idx, node_idx in enumerate(nodes, start=1):
            band = series_lc_values(TARGET_HZ * case.target_phase_velocity_scale, c_base, q, 0.45)
            lines.extend(
                [
                    f"Rdist150_{idx} {design.n(node_idx)} d150r{idx} {spice_num(band['r_ohm'])}",
                    f"Ldist150_{idx} d150r{idx} d150l{idx} {spice_num(band['l_h'])}",
                    f"Cdist150_{idx} d150l{idx} {bus} {spice_num(band['c_f'])}",
                ]
            )
        lines.append(f"Rload150bus {bus} 0 {spice_num(case.output_load_ohm * 1.5)}")
        entry = bus

    stages = max(1, case.extraction_stage_count)
    if case.extraction_topology == "single_high_q":
        stages = 1
    elif case.extraction_topology == "cascaded":
        stages = max(2, stages)
    elif case.extraction_topology == "distributed":
        stages = max(1, stages)

    current = entry
    for stage in range(1, stages + 1):
        out = "v150" if stage == stages else f"v150s{stage}"
        q_scale = 1.0 + 0.28 * (stage - 1)
        cap_scale = max(0.30, 1.0 - 0.13 * (stage - 1))
        if case.extraction_q_label == "very_high":
            q_scale *= 1.35
        elif case.extraction_q_label == "high":
            q_scale *= 1.15
        elif case.extraction_q_label == "low":
            q_scale *= 0.65
        band = series_lc_values(
            TARGET_HZ * case.target_phase_velocity_scale,
            case.extraction_c_f * cap_scale,
            case.extraction_q * q_scale,
            0.35,
        )
        lines.extend(
            [
                f"Rext{stage} {current} ext{stage}r {spice_num(band['r_ohm'])}",
                f"Lext{stage} ext{stage}r ext{stage}l {spice_num(band['l_h'])}",
                f"Cext{stage} ext{stage}l {out} {spice_num(band['c_f'])}",
                f"Rload150_{stage} {out} 0 {spice_num(case.output_load_ohm * (1.0 + 0.35 * (stage - 1)))}",
            ]
        )
        current = out

    if case.post_filter_strength > 0.0:
        post = series_lc_values(
            TARGET_HZ,
            case.extraction_c_f * 0.38,
            case.extraction_q * (1.5 + case.post_filter_strength),
            0.35,
        )
        lines.extend(
            [
                f"Rpost150 {current} post150r {spice_num(post['r_ohm'])}",
                f"Lpost150 post150r post150l {spice_num(post['l_h'])}",
                f"Cpost150 post150l v150f {spice_num(post['c_f'])}",
                f"Rload150f v150f 0 {spice_num(case.output_load_ohm * (1.4 + 0.45 * case.post_filter_strength))}",
            ]
        )
        current = "v150f"
    return current


def qpm_sign(case: LockinCase, idx: int) -> float:
    if case.hybrid_section_placement != "qpm_sign_flipped_hybrid_sections":
        return 1.0
    period = max(2, case.cell_count // 8)
    return -1.0 if (idx // period) % 2 else 1.0


def netlist_for_case(case: LockinCase, csv_path: Path) -> str:
    stable_families = {
        "varactor_only_tuned_extraction",
        "detuned_150mhz_phase_velocity_line",
        "shuffled_frequency_line",
        "direct_50plus100_reference",
    }
    if case.role == "ceiling_reference" or case.family in stable_families:
        return race.netlist_for_case(case, csv_path)

    vals = lockin_cell_values(case)
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
    magnetic_curve = 1.0 if case.magnetic_saturation_curve == "soft" else 1.55
    kmag = 2.25e-6 * case.magnetic_strength * case.nonlinear_strength_scale * magnetic_curve
    gcore = 2.7e-7 * max(case.magnetic_core_loss_proxy + case.magnetic_hysteresis_loss, 0.0)
    bias_shift = 1.0 + 0.25 * math.tanh(case.magnetic_dc_bias_proxy)
    lines = [
        f"* {case.name}",
        "* Hybrid purity lock-in: source-only 50 MHz, passive 150 MHz extraction.",
        f"* role={case.role}; source_only={case.source_only_drive}; no direct 100/150 MHz discovery drive.",
        f"* extraction={case.extraction_topology}; stages={case.extraction_stage_count}; q_label={case.extraction_q_label}",
        ".option method=gear maxord=2 reltol=2e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-16 itl4=320",
        f".model DVAR D(Is={spice_num(var.is_a)} Rs={spice_num(var.rs_ohm)} Cjo={spice_num(var.cjo_f)} Vj={spice_num(var.vj_v)} M={spice_num(var.m)} Bv={spice_num(var.bv_v)} Ibv={spice_num(var.ibv_a)})",
        f".param kmag={spice_num(kmag)}",
        f".param gcore={spice_num(gcore)}",
        f"Vbias vb 0 DC {spice_num(case.bias_v)}",
        f"Vsrc src 0 SIN(0 {spice_num(case.source_amplitude_v)} {spice_num(SOURCE_HZ)})",
        f"Rsrc src {design.n(0)} {spice_num(case.z0_ohm)}",
        f"Rrawload {raw_out} 0 {spice_num(case.z0_ohm * 4.0)}",
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

    delay_start = max(1, int(round(case.cell_count * case.varactor_block_fraction)))
    delay_end = delay_start + case.phase_delay_cells_between_blocks
    for i in range(1, case.cell_count + 1):
        l_scale = case.phase_delay_scale if delay_start <= i <= delay_end else 1.0
        c_scale = 1.0 / max(l_scale, 0.2) if delay_start <= i <= delay_end else 1.0
        lines.extend(
            [
                f"Rser{i} {design.n(i - 1)} ns{i} {spice_num(vals['r_series_ohm'])}",
                f"Lser{i} ns{i} {design.n(i)} {spice_num(vals['l_cell_h'] * l_scale)}",
            ]
        )
        if case.fixed_cap_only or i not in varactor_nodes:
            cap = vals["c_linear_control_f"] if case.fixed_cap_only else vals["c_cell_f"] * c_scale
            lines.append(f"Cbase{i} {design.n(i)} 0 {spice_num(cap)}")
        else:
            lines.append(f"Cfixed{i} {design.n(i)} 0 {spice_num(vals['c_fixed_f'] * c_scale)}")
            if case.stacked_varactor_pairs > 1:
                lines.append(f"Dvar{i}a {design.n(i)} vst{i} DVAR")
                lines.append(f"Dvar{i}b vst{i} vb DVAR")
                lines.append(f"Rstack{i} vst{i} vb {spice_num(2.0e6)}")
            else:
                lines.append(f"Dvar{i} {design.n(i)} vb DVAR")
        lines.append(f"Rbleed{i} {design.n(i)} 0 {spice_num(case.shunt_loss_ohm)}")

    for i in magnetic_nodes:
        sign = qpm_sign(case, i)
        phase = 1.0 + 0.14 * math.sin(case.hybrid_relative_phase + i / max(case.cell_count, 1))
        sat = max(case.magnetic_saturation_current_a, 0.025)
        node = design.n(i)
        lines.append(
            f"Bmag{i} {node} 0 I={{({spice_num(sign * phase * bias_shift)})*kmag*V({node})*V({node})*V({node})/(1+(V({node})/{spice_num(sat * case.z0_ohm)})**2) + gcore*V({node})}}"
        )

    measure = add_lockin_cleanup(lines, case, raw_out)
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
    seed: str = "h024",
    extraction_topology: str = "single_high_q",
    extraction_stage_count: int = 1,
    extraction_q: float = 22.0,
    q_label: str = "medium",
    output_load: float = 150.0,
    post_filter: float = 0.0,
    target_scale: float = 0.995,
    generated_scale: float = 1.003,
    phase_velocity_m_s: float = 5.08e6,
    phase_delay_cells_between_blocks: int = 0,
    phase_delay_cells_before_extraction: int = 0,
    phase_delay_scale: float = 1.0,
    cells: int = 96,
    z0: float = 75.0,
    length_m: float = 0.50,
    drive_v: float | None = None,
    cjo_scale: float | None = None,
    bias_v: float | None = None,
    magnetic_strength: float | None = None,
    magnetic_sat_i: float = 0.10,
    magnetic_loss: float = 0.25,
    varactor_fraction: float = 0.50,
    magnetic_start: float = 0.50,
    magnetic_end: float = 1.00,
    overlap: float = 0.06,
    magnetic_spacing: int = 4,
    magnetic_count: int = 18,
    stacked_pairs: int = 1,
    distributed_spacing: int = 0,
    distributed_strength: float = 0.0,
    notch50: bool = True,
    notch100: bool = True,
    notch_q: float = 1.0,
    after_magnetic: bool = False,
    extraction_position: str = "end",
    family: str = "hybrid_varactor_plus_magnetic_line",
    role: str = "discovery",
    fixed_cap_only: bool = False,
    direct_100_v: float = 0.0,
    source_only: bool = True,
    cleanup: str = "extraction_plus_rejection",
    notes: str = "",
) -> LockinCase:
    if seed == "h025":
        drive_v = 2.7 if drive_v is None else drive_v
        cjo_scale = 1.35 if cjo_scale is None else cjo_scale
        bias_v = 3.4 if bias_v is None else bias_v
        magnetic_strength = 0.55 if magnetic_strength is None else magnetic_strength
    else:
        drive_v = 2.6 if drive_v is None else drive_v
        cjo_scale = 1.50 if cjo_scale is None else cjo_scale
        bias_v = 3.1 if bias_v is None else bias_v
        magnetic_strength = 0.65 if magnetic_strength is None else magnetic_strength

    base_case = hybrid.make_case(
        case_id,
        "varactor_first_then_magnetic",
        cells=cells,
        z0=z0,
        length_m=length_m,
        drive_v=drive_v,
        bias_v=bias_v,
        cjo_scale=cjo_scale,
        rs=0.30,
        vj=0.62,
        m=0.60,
        magnetic_strength=magnetic_strength,
        magnetic_sat_i=magnetic_sat_i,
        magnetic_loss=magnetic_loss,
        cleanup=cleanup,
        extraction_q=extraction_q,
        output_load=output_load,
        target_scale=target_scale,
        generated_scale=generated_scale,
        phase_velocity_m_s=phase_velocity_m_s,
        source_rej=notch50,
        gen_rej=notch100,
        post_filter=post_filter,
        extraction_position=extraction_position,
        magnetic_spacing=magnetic_spacing,
        magnetic_count=magnetic_count,
        stacked_pairs=stacked_pairs,
        fixed_cap_only=fixed_cap_only,
        source_only=source_only,
        direct_100_v=direct_100_v,
        role=role,
        family=family,
        notes=notes or "Focused purity lock-in row.",
    )
    data = asdict(base_case)
    data.update(
        {
            "name": clean_name(f"{case_id}_{seed}_{extraction_topology}_{cells}c_{int(z0)}ohm"),
            "filename": f"{clean_name(f'{case_id}_{seed}_{extraction_topology}_{cells}c_{int(z0)}ohm')}.cir",
            "extraction_topology": extraction_topology,
            "extraction_stage_count": extraction_stage_count,
            "distributed_extraction_spacing": distributed_spacing,
            "distributed_extraction_strength": distributed_strength,
            "pre_notch_50": notch50,
            "pre_notch_100": notch100,
            "notch_q_scale": notch_q,
            "extraction_q_label": q_label,
            "phase_delay_cells_between_blocks": phase_delay_cells_between_blocks,
            "phase_delay_cells_before_extraction": phase_delay_cells_before_extraction,
            "phase_delay_scale": phase_delay_scale,
            "varactor_block_fraction": varactor_fraction,
            "magnetic_block_start_fraction": magnetic_start,
            "magnetic_block_end_fraction": magnetic_end,
            "overlap_fraction": overlap,
            "alternating_overlap_only": overlap > 0.08,
            "target_extraction_after_magnetic_block": after_magnetic,
            "source_rejection_db_proxy": 0.0,
            "generated_rejection_db_proxy": 0.0,
        }
    )
    return LockinCase(**data)


def build_cases(max_discovery_cases: int | None = None) -> List[LockinCase]:
    discovery = [
        make_case("p001", "h024", extraction_topology="single_high_q", extraction_q=18.0, q_label="medium", notes="h024 reproduction with lock-in generator."),
        make_case("p002", "h025", extraction_topology="single_high_q", extraction_q=18.0, q_label="medium", notes="h025 growth-preserving reproduction."),
        make_case("p003", "h024", extraction_topology="single_high_q", extraction_q=28.0, q_label="high", output_load=180.0, post_filter=0.5, notes="Single high-Q 150 MHz extraction."),
        make_case("p004", "h024", extraction_topology="single_high_q", extraction_q=38.0, q_label="very_high", output_load=220.0, post_filter=0.8, notes="Very high-Q single extraction."),
        make_case("p005", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=24.0, q_label="high", output_load=170.0, post_filter=0.4, notes="Two-stage cascaded extraction."),
        make_case("p006", "h025", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=22.0, q_label="high", output_load=160.0, post_filter=0.3, notes="Two-stage cascaded extraction around growth-preserving seed."),
        make_case("p007", "h024", extraction_topology="cascaded", extraction_stage_count=3, extraction_q=20.0, q_label="high", output_load=180.0, post_filter=0.6, notes="Three-stage cascaded extraction."),
        make_case("p008", "h025", extraction_topology="cascaded", extraction_stage_count=3, extraction_q=18.0, q_label="medium", output_load=160.0, post_filter=0.4, notes="Three-stage cascaded extraction with h025 growth seed."),
        make_case("p009", "h024", extraction_topology="distributed", extraction_stage_count=1, extraction_q=18.0, q_label="medium", distributed_spacing=24, distributed_strength=0.35, output_load=180.0, notes="Distributed extraction every 24 cells."),
        make_case("p010", "h025", extraction_topology="distributed", extraction_stage_count=2, extraction_q=16.0, q_label="medium", distributed_spacing=16, distributed_strength=0.28, output_load=160.0, notes="Distributed extraction every 16 cells plus stage cleanup."),
        make_case("p011", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, output_load=150.0, notch50=True, notch100=False, notes="50 MHz notch before extraction."),
        make_case("p012", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, output_load=150.0, notch50=False, notch100=True, notes="100 MHz notch before extraction."),
        make_case("p013", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, output_load=150.0, notch_q=1.8, notes="Combined stronger 50/100 MHz rejection."),
        make_case("p014", "h024", extraction_topology="single_high_q", extraction_q=20.0, phase_delay_cells_between_blocks=3, phase_delay_scale=1.08, notes="Phase delay between varactor and magnetic regions."),
        make_case("p015", "h025", extraction_topology="single_high_q", extraction_q=18.0, phase_delay_cells_between_blocks=4, phase_delay_scale=1.10, notes="Phase delay between blocks on h025 seed."),
        make_case("p016", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=20.0, phase_delay_cells_before_extraction=3, phase_delay_scale=1.12, output_load=170.0, notes="Delay section before target extraction."),
        make_case("p017", "h025", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, phase_delay_cells_before_extraction=4, phase_delay_scale=1.10, output_load=160.0, notes="Delay before extraction on growth seed."),
        make_case("p018", "h024", extraction_topology="single_high_q", extraction_q=20.0, varactor_fraction=0.20, magnetic_start=0.24, magnetic_end=0.82, overlap=0.04, notes="Varactor block in first 20 percent."),
        make_case("p019", "h024", extraction_topology="single_high_q", extraction_q=20.0, varactor_fraction=0.25, magnetic_start=0.30, magnetic_end=0.84, overlap=0.06, notes="Varactor block in first 25 percent."),
        make_case("p020", "h024", extraction_topology="single_high_q", extraction_q=20.0, varactor_fraction=0.40, magnetic_start=0.45, magnetic_end=0.88, overlap=0.08, notes="Varactor block in first 40 percent."),
        make_case("p021", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=20.0, varactor_fraction=0.33, magnetic_start=0.30, overlap=0.12, output_load=165.0, notes="Long overlap with alternating overlap only."),
        make_case("p022", "h024", extraction_topology="single_high_q", extraction_q=20.0, target_scale=0.992, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Independent phase velocity trim."),
        make_case("p023", "h025", extraction_topology="single_high_q", extraction_q=18.0, target_scale=0.993, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Growth seed phase velocity trim."),
        make_case("p024", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, cells=80, length_m=0.44, output_load=145.0, notes="80-cell line length trim."),
        make_case("p025", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, cells=112, length_m=0.58, output_load=170.0, notes="112-cell line length trim."),
        make_case("p026", "h025", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, cells=128, length_m=0.70, output_load=190.0, drive_v=2.25, stacked_pairs=2, notes="128-cell stacked stress-reduction row."),
        make_case("p027", "h024", extraction_topology="single_high_q", extraction_q=20.0, magnetic_strength=0.48, magnetic_sat_i=0.08, magnetic_loss=0.18, magnetic_count=22, notes="Mild magnetic saturation."),
        make_case("p028", "h024", extraction_topology="single_high_q", extraction_q=20.0, magnetic_strength=0.78, magnetic_sat_i=0.14, magnetic_loss=0.30, magnetic_count=22, notes="Medium magnetic saturation."),
        make_case("p029", "h025", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, drive_v=2.35, magnetic_strength=0.85, magnetic_sat_i=0.18, magnetic_loss=0.35, notes="Harder magnetic saturation with lower drive."),
        make_case("p030", "h024", extraction_topology="cascaded", extraction_stage_count=2, extraction_q=18.0, cjo_scale=1.35, bias_v=3.8, stacked_pairs=2, drive_v=2.75, output_load=160.0, notes="Stacked varactor stress reduction with drive compensation."),
        make_case("p031", "h025", extraction_topology="cascaded", extraction_stage_count=4, extraction_q=50.0, q_label="very_high", output_load=220.0, post_filter=1.0, target_scale=0.993, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Aggressive four-stage purity filter from probe."),
        make_case("p032", "h025", extraction_topology="cascaded", extraction_stage_count=5, extraction_q=70.0, q_label="very_high", output_load=220.0, post_filter=1.0, target_scale=0.993, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Aggressive five-stage high-Q purity filter from probe."),
        make_case("p033", "h025", extraction_topology="single_high_q", extraction_q=24.0, q_label="high", output_load=100.0, post_filter=1.5, target_scale=0.993, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Low-load weak post-filter purity probe."),
        make_case("p034", "h025", extraction_topology="single_high_q", extraction_q=24.0, q_label="high", output_load=130.0, post_filter=1.5, target_scale=0.993, generated_scale=1.004, phase_velocity_m_s=5.10e6, notes="Moderate-load weak post-filter purity probe."),
    ]
    if max_discovery_cases is not None:
        discovery = discovery[:max_discovery_cases]

    base = make_case("base", "h024", role="control", notes="Lock-in control base.")
    controls = [
        replace(base, case_id="c001", name="linear_fixed_component_line", filename="linear_fixed_component_line.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.0, family="linear_fixed_component_line", notes="Linear fixed-component control."),
        replace(base, case_id="c002", name="varactor_only_tuned_extraction", filename="varactor_only_tuned_extraction.cir", magnetic_strength=0.0, magnetic_section_count=0, behavioral_helper=False, family="varactor_only_tuned_extraction", notes="Varactor-only tuned extraction control."),
        replace(base, case_id="c003", name="magnetic_only_tuned_extraction", filename="magnetic_only_tuned_extraction.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.85, family="magnetic_only_tuned_extraction", notes="Magnetic-only tuned extraction control."),
        replace(base, case_id="c004", name="weak_hybrid_line", filename="weak_hybrid_line.cir", nonlinear_fraction=0.10, cjo_scale=0.35, bias_v=14.0, magnetic_strength=0.08, magnetic_saturation_current_a=0.25, family="weak_hybrid_line", notes="Weak hybrid control."),
        replace(base, case_id="c005", name="detuned_150mhz_phase_velocity_line", filename="detuned_150mhz_phase_velocity_line.cir", target_phase_velocity_scale=0.82, phase_velocity_m_s=3.9e6, phase_velocity_error_50=-0.22, phase_velocity_error_150=-0.18, family="detuned_150mhz_phase_velocity_line", notes="Detuned 150 MHz phase-velocity control."),
        replace(base, case_id="c006", name="shuffled_frequency_line", filename="shuffled_frequency_line.cir", generated_phase_velocity_scale=0.88, target_phase_velocity_scale=1.12, phase_velocity_m_s=6.5e6, phase_velocity_error_50=0.30, phase_velocity_error_100=-0.12, phase_velocity_error_150=0.12, family="shuffled_frequency_line", notes="Shuffled frequency control."),
        replace(base, case_id="c007", name="too_short_line", filename="too_short_line.cir", total_length_m=0.05, family="too_short_line", notes="Too-short interaction control."),
        replace(base, case_id="c008", name="too_lossy_line", filename="too_lossy_line.cir", series_loss_ohm_scale=30.0, shunt_loss_ohm=10_000.0, magnetic_core_loss_proxy=2.0, magnetic_hysteresis_loss=1.0, family="too_lossy_line", notes="Too-lossy control."),
        replace(base, case_id="c009", name="phase_mismatched_hybrid_line", filename="phase_mismatched_hybrid_line.cir", generated_phase_velocity_scale=0.91, target_phase_velocity_scale=1.22, phase_velocity_m_s=4.1e6, phase_velocity_error_50=-0.18, phase_velocity_error_100=-0.09, phase_velocity_error_150=0.22, family="phase_mismatched_hybrid_line", notes="Phase-mismatched hybrid control."),
        replace(base, case_id="c010", name="target_extraction_no_nonlinearity", filename="target_extraction_no_nonlinearity.cir", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, magnetic_strength=0.0, family="target_extraction_no_nonlinearity", notes="Target extraction with no nonlinearity."),
        replace(base, case_id="c011", name="hybrid_nonlinearity_no_target_extraction", filename="hybrid_nonlinearity_no_target_extraction.cir", cleanup_topology="none", extraction_topology="none", pre_notch_50=False, pre_notch_100=False, source_rejection=False, generated_rejection=False, post_filter_strength=0.0, source_amplitude_v=1.8, nonlinear_fraction=0.55, cjo_scale=0.90, magnetic_strength=0.30, family="hybrid_nonlinearity_no_target_extraction", notes="Hybrid nonlinearity with target extraction removed and absorber loading retained."),
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


def export_netlists(out_dir: Path, max_discovery_cases: int | None = None) -> List[LockinExport]:
    ensure_dir(out_dir)
    exports: List[LockinExport] = []
    for case in build_cases(max_discovery_cases=max_discovery_cases):
        netlist_path = out_dir / case.filename
        csv_path = out_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist_path.write_text(netlist_for_case(case, csv_path), encoding="utf-8")
        exports.append(LockinExport(case, netlist_path, csv_path))
    return exports


def run_ngspice(export: LockinExport, ngspice_path: str, timeout_s: int) -> design.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = design.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return design.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def accumulated_phase_mismatch(case: LockinCase) -> float:
    wavelength = case.phase_velocity_m_s / SOURCE_HZ
    trim = abs(case.phase_velocity_error_50) + abs(case.phase_velocity_error_100) + abs(case.phase_velocity_error_150)
    delay = 0.012 * (case.phase_delay_cells_between_blocks + case.phase_delay_cells_before_extraction)
    return float(2.0 * math.pi * case.total_length_m / max(wavelength, EPS) * trim + delay)


def behavioral_dependency(case: LockinCase) -> float:
    if case.fixed_cap_only and case.magnetic_strength == 0.0:
        return 0.02
    score = 0.08
    if case.magnetic_strength > 0.0:
        score += 0.10
    if case.extraction_stage_count > 1 or case.distributed_extraction_spacing:
        score += 0.01
    if case.post_filter_strength > 0.0:
        score += 0.005
    if case.behavioral_helper:
        score += 0.01
    return min(score, 0.20)


def measure_case(export: LockinExport, data: Dict[str, np.ndarray], reference_power: float | None) -> Dict[str, object]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    metrics = design.measure_case(shim, data, reference_power)
    case = export.case
    target_power = safe_float(metrics.get("target_fft_power"))
    source_power = safe_float(metrics.get("source_fft_power"))
    generated_power = safe_float(metrics.get("generated_fft_power"))
    source_rejection_db = 10.0 * math.log10(max(target_power, EPS) / max(source_power, EPS))
    generated_rejection_db = 10.0 * math.log10(max(target_power, EPS) / max(generated_power, EPS))
    target_outcoupling = target_power / max(source_power + generated_power + target_power, EPS)
    magnetic_current = max(safe_float(metrics.get("source_peak_current_a")), safe_float(metrics.get("varactor_peak_current_a"))) / max(1, case.magnetic_section_count)
    saturation_margin = case.magnetic_saturation_current_a / max(magnetic_current, EPS) if case.magnetic_strength else 999.0
    beh = behavioral_dependency(case)
    metrics.update(
        {
            "family": case.family,
            "hybrid_section_placement": case.hybrid_section_placement,
            "extraction_topology": case.extraction_topology,
            "extraction_stage_count": case.extraction_stage_count,
            "distributed_extraction_spacing": case.distributed_extraction_spacing,
            "distributed_extraction_strength": case.distributed_extraction_strength,
            "extraction_q_label": case.extraction_q_label,
            "target_extraction_q": case.extraction_q,
            "post_filter_strength": case.post_filter_strength,
            "pre_notch_50": str(case.pre_notch_50),
            "pre_notch_100": str(case.pre_notch_100),
            "notch_q_scale": case.notch_q_scale,
            "phase_delay_cells_between_blocks": case.phase_delay_cells_between_blocks,
            "phase_delay_cells_before_extraction": case.phase_delay_cells_before_extraction,
            "phase_delay_scale": case.phase_delay_scale,
            "varactor_block_fraction": case.varactor_block_fraction,
            "magnetic_block_start_fraction": case.magnetic_block_start_fraction,
            "magnetic_block_end_fraction": case.magnetic_block_end_fraction,
            "overlap_fraction": case.overlap_fraction,
            "target_extraction_after_magnetic_block": str(case.target_extraction_after_magnetic_block),
            "source_rejection_at_50mhz_db": source_rejection_db,
            "generated_rejection_at_100mhz_db": generated_rejection_db,
            "target_rejection_outcoupling_150mhz": target_outcoupling,
            "target_extraction_gain": target_power / max(source_power + generated_power, EPS),
            "phase_velocity_error_50": case.phase_velocity_error_50,
            "phase_velocity_error_100": case.phase_velocity_error_100,
            "phase_velocity_error_150": case.phase_velocity_error_150,
            "accumulated_phase_mismatch": accumulated_phase_mismatch(case),
            "group_delay_match_score": case.group_delay_match_score,
            "magnetic_strength": case.magnetic_strength,
            "magnetic_peak_current_a": magnetic_current,
            "saturation_margin": saturation_margin,
            "hysteresis_loss_proxy": case.magnetic_hysteresis_loss,
            "magnetic_core_loss_proxy": case.magnetic_core_loss_proxy,
            "varactor_peak_voltage_v": metrics.get("varactor_peak_voltage_v", 0.0),
            "varactor_peak_current_a": metrics.get("varactor_peak_current_a", 0.0),
            "reverse_bias_margin_v": metrics.get("reverse_bias_margin_v", 0.0),
            "behavioral_dependency_score": beh,
        }
    )

    stress_score = safe_float(metrics.get("component_stress_score"))
    if case.stacked_varactor_pairs > 1:
        stress_score *= 0.82
    if case.phase_delay_cells_between_blocks or case.phase_delay_cells_before_extraction:
        stress_score *= 0.97
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
            promotion = "spice_hybrid_purity_412_candidate"
        elif lock > 0.90 and bridge > 1.5 and purity > 0.60 and growth > 0.9 and stress_ok:
            promotion = "spice_hybrid_purity_412_near_miss"
        elif purity <= 0.60:
            promotion = "reject_due_to_low_purity"
        elif growth <= 0.9:
            promotion = "reject_due_to_low_growth"
        elif lock <= 0.90 or jump >= 1.0:
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
    export: LockinExport,
    run_requested: bool,
    ngspice_available: bool,
    ngspice_path: str | None,
    result: design.RunResult,
    metrics: Dict[str, object] | None,
) -> Dict[str, object]:
    vals = lockin_cell_values(export.case)
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_hybrid_purity_412_lockin",
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
        "extraction_topology": case.extraction_topology,
        "extraction_stage_count": case.extraction_stage_count,
        "extraction_q_label": case.extraction_q_label,
        "output_load_ohm": case.output_load_ohm,
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
    elif result.execution_status in {"failed_to_converge", "parser_failed"} and case.role == "discovery":
        row["promotion_category"] = "reject_due_to_convergence"
    return row


def category_best(rows: List[Dict[str, object]], key: str, value: str, score_key: str = "spectral_purity_150mhz") -> Dict[str, object]:
    selected = [row for row in rows if row.get("execution_status") == "ran_successfully" and str(row.get(key)) == value]
    return max(selected, key=lambda row: safe_float(row.get(score_key)), default={})


def aggregate_summary(rows: List[Dict[str, object]], run_requested: bool, ngspice_available: bool) -> Dict[str, object]:
    data = [row for row in rows if row.get("row_type") == "spice_hybrid_purity_412_lockin"]
    discovery = [row for row in data if row.get("role") == "discovery"]
    controls = [row for row in data if row.get("role") == "control"]
    ran = [row for row in data if row.get("execution_status") == "ran_successfully"]
    successful_discovery = [row for row in discovery if row.get("execution_status") == "ran_successfully"]
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls if row.get("execution_status") == "ran_successfully")
    max_leak = max((safe_float(row.get("control_leakage_score")) for row in controls), default=0.0)
    candidates = [row for row in successful_discovery if row.get("promotion_category") == "spice_hybrid_purity_412_candidate"] if controls_dead else []
    near = [row for row in successful_discovery if row.get("promotion_category") == "spice_hybrid_purity_412_near_miss"] if controls_dead else []
    plausible = [row for row in successful_discovery if str(row.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}]
    best = max(
        successful_discovery,
        key=lambda row: (
            safe_float(row.get("spectral_purity_150mhz")),
            min(safe_float(row.get("target_band_coherent_growth")), 1.5),
            safe_float(row.get("phase_lock_target")),
            safe_float(row.get("bridge_ratio_vs_direct_reference")),
            -safe_float(row.get("component_stress_score"), 9.0),
        ),
        default={},
    )
    balanced = max(
        plausible,
        key=lambda row: (
            min(safe_float(row.get("spectral_purity_150mhz")) / 0.80, 1.3)
            + min(safe_float(row.get("target_band_coherent_growth")) / 1.0, 1.2)
            + min(safe_float(row.get("phase_lock_target")) / 0.90, 1.1)
            + min(safe_float(row.get("bridge_ratio_vs_direct_reference")) / 1.5, 1.1)
            - 0.25 * safe_float(row.get("component_stress_score"), 1.0)
        ),
        default={},
    )
    pure_varactor = category_best(data, "family", "varactor_only_tuned_extraction")
    pure_magnetic = category_best(data, "family", "magnetic_only_tuned_extraction")
    extraction_topologies = sorted(set(str(row.get("extraction_topology")) for row in successful_discovery))
    extraction_summary = {
        topology: {
            "best_case": category_best(successful_discovery, "extraction_topology", topology).get("case_id", ""),
            "best_purity": category_best(successful_discovery, "extraction_topology", topology).get("spectral_purity_150mhz", 0.0),
            "best_growth": category_best(successful_discovery, "extraction_topology", topology, "target_band_coherent_growth").get("target_band_coherent_growth", 0.0),
        }
        for topology in extraction_topologies
    }
    phase_delay_rows = [row for row in plausible if safe_float(row.get("phase_delay_cells_between_blocks")) > 0 or safe_float(row.get("phase_delay_cells_before_extraction")) > 0]
    no_delay_rows = [row for row in plausible if safe_float(row.get("phase_delay_cells_between_blocks")) == 0 and safe_float(row.get("phase_delay_cells_before_extraction")) == 0]
    phase_delay_best = max((safe_float(row.get("spectral_purity_150mhz")) for row in phase_delay_rows), default=0.0)
    no_delay_best = max((safe_float(row.get("spectral_purity_150mhz")) for row in no_delay_rows), default=0.0)
    hybrid_beats_controls = bool(
        safe_float(best.get("spectral_purity_150mhz")) > max(
            safe_float(pure_varactor.get("spectral_purity_150mhz")),
            safe_float(pure_magnetic.get("spectral_purity_150mhz")),
        )
    )
    statuses = ";".join(sorted(set(str(row.get("execution_status")) for row in data)))
    recommended = (
        "component/BOM selection and PCB layout model"
        if candidates
        else "another hybrid topology refinement plus acoustic bench demo"
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
        "best_purity": best.get("spectral_purity_150mhz", ""),
        "best_lock": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio_vs_direct_reference", ""),
        "best_target_growth": best.get("target_band_coherent_growth", ""),
        "best_generated_cv": best.get("generated_envelope_cv", ""),
        "best_max_phase_jump": best.get("max_phase_jump", ""),
        "best_stress_class": best.get("component_stress_class", ""),
        "best_stress_score": best.get("component_stress_score", ""),
        "best_behavioral_dependency": best.get("behavioral_dependency_score", ""),
        "best_balanced_case": balanced.get("case_id", ""),
        "best_balanced_purity": balanced.get("spectral_purity_150mhz", ""),
        "best_balanced_growth": balanced.get("target_band_coherent_growth", ""),
        "purity_above_0p60_count": len([row for row in plausible if safe_float(row.get("spectral_purity_150mhz")) > 0.60]),
        "purity_above_0p80_count": len([row for row in plausible if safe_float(row.get("spectral_purity_150mhz")) > 0.80]),
        "candidate_with_growth_above_1_count": len([row for row in candidates if safe_float(row.get("target_band_coherent_growth")) > 1.0]),
        "controls_dead": str(controls_dead) if ran else "not_run",
        "max_control_leakage_score": max_leak,
        "extraction_summary_json": json.dumps(extraction_summary, sort_keys=True),
        "cascaded_or_distributed_best_purity": max(
            (safe_float(row.get("spectral_purity_150mhz")) for row in plausible if str(row.get("extraction_topology")) in {"cascaded", "distributed"}),
            default=0.0,
        ),
        "phase_delay_best_purity": phase_delay_best,
        "no_phase_delay_best_purity": no_delay_best,
        "phase_delay_helped": str(phase_delay_best > no_delay_best),
        "hybrid_beats_pure_varactor_and_pure_magnetic": str(hybrid_beats_controls),
        "pure_varactor_control_purity": pure_varactor.get("spectral_purity_150mhz", ""),
        "pure_magnetic_control_purity": pure_magnetic.get("spectral_purity_150mhz", ""),
        "recommended_next_step": recommended,
    }


def timeseries_rows(export: LockinExport, data: Dict[str, np.ndarray], stride: int = 24) -> List[Dict[str, object]]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    rows = design.timeseries_rows(shim, data, stride=stride)
    for row in rows:
        row["row_type"] = "spice_hybrid_purity_412_lockin_timeseries"
        row["family"] = export.case.family
        row["extraction_topology"] = export.case.extraction_topology
    return rows


def write_report(out_dir: Path, rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    data = [row for row in rows if row.get("row_type") == "spice_hybrid_purity_412_lockin"]
    lines = [
        "# SPICE 4->8->12 Hybrid Purity Lock-In",
        "",
        "Focused lock-in refinement around h024/h025 hybrid varactor-plus-magnetic near misses.",
        "",
        "## Direct Answers",
        "",
        f"1. Can purity be raised above 0.60? count={aggregate.get('purity_above_0p60_count')}; best_purity={aggregate.get('best_purity')}.",
        f"2. Can purity exceed 0.80 while growth stays above 1.0? candidates={aggregate.get('candidate_count')}; candidate_growth_count={aggregate.get('candidate_with_growth_above_1_count')}.",
        f"3. Does cascaded/distributed extraction solve purity? best_cascade_or_distributed={aggregate.get('cascaded_or_distributed_best_purity')}; extraction_summary={aggregate.get('extraction_summary_json')}.",
        f"4. Does phase delay help? {aggregate.get('phase_delay_helped')}; phase_delay_best={aggregate.get('phase_delay_best_purity')}; no_delay_best={aggregate.get('no_phase_delay_best_purity')}.",
        f"5. Best balanced row: {aggregate.get('best_balanced_case')} purity={aggregate.get('best_balanced_purity')} growth={aggregate.get('best_balanced_growth')}.",
        f"6. Do controls stay dead? {aggregate.get('controls_dead')}; max_leakage={aggregate.get('max_control_leakage_score')}.",
        f"7. Does hybrid beat pure tuned controls? {aggregate.get('hybrid_beats_pure_varactor_and_pure_magnetic')}; varactor={aggregate.get('pure_varactor_control_purity')}; magnetic={aggregate.get('pure_magnetic_control_purity')}.",
        f"8. Next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Best Row",
        "",
        (
            "- {case} {name}: lock={lock}, bridge={bridge}, purity={purity}, growth={growth}, "
            "gen_cv={gen_cv}, max_jump={jump}, stress={stress}, behavioral={beh}."
        ).format(
            case=aggregate.get("best_case"),
            name=aggregate.get("best_name"),
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
            "- {case_id} {family}: role={role}, status={status}, category={cat}, extraction={extraction}, "
            "stages={stages}, cells={cells}, lock={lock}, bridge={bridge}, purity={purity}, growth={growth}, "
            "gen_cv={gen_cv}, stress={stress}, behavioral={behavioral}.".format(
                case_id=row.get("case_id"),
                family=row.get("family"),
                role=row.get("role"),
                status=row.get("execution_status"),
                cat=row.get("promotion_category", ""),
                extraction=row.get("extraction_topology", ""),
                stages=row.get("extraction_stage_count", ""),
                cells=row.get("cell_count", ""),
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
            "- No discovery row uses direct 100 MHz drive, direct 150 MHz drive, target-frequency injection, or hidden behavioral target source.",
            "- Direct 50+100 MHz is separated as a ceiling denominator only.",
            "- Cascaded/distributed extraction, notches, and phase-delay sections are passive LC/RLC networks.",
            "- Magnetic nonlinearity remains a labeled core proxy and is counted in behavioral dependency.",
        ]
    )
    (out_dir / "README_SPICE_412_HYBRID_PURITY_LOCKIN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Run hybrid 4->8->12 purity lock-in SPICE refinement.")
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
    write_csv(out_dir / "spice_412_hybrid_purity_lockin_summary.csv", all_rows)
    if timeseries:
        write_csv(out_dir / "spice_412_hybrid_purity_lockin_timeseries.csv", timeseries)
    elif (out_dir / "spice_412_hybrid_purity_lockin_timeseries.csv").exists():
        (out_dir / "spice_412_hybrid_purity_lockin_timeseries.csv").unlink()
    (out_dir / "spice_412_hybrid_purity_lockin_summary.json").write_text(
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
        "spice_412_hybrid_purity_lockin: run={run} ngspice={ng} statuses={statuses} best={best} candidates={candidates} near={near}".format(
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
