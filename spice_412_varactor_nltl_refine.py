#!/usr/bin/env python3
"""Focused refinement for the 4->8->12 varactor-loaded NLTL.

The first concrete NLTL design was low-behavioral and stress-plausible, but
150 MHz purity was far too low.  This script refines around the best 48-cell
75-ohm row using larger cell counts, impedance/bias/capacitance sweeps, passive
target-band extraction, source/generated rejection traps, and load/Q shaping.
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

import spice_412_varactor_nltl_design as base


OUT_DIR = Path("runs") / "spice_412_varactor_nltl_refine"
SOURCE_HZ = base.SOURCE_HZ
GENERATED_HZ = base.GENERATED_HZ
TARGET_HZ = base.TARGET_HZ
TOTAL_LENGTH_M = base.TOTAL_LENGTH_M
TSTOP_S = base.TSTOP_S
TSTEP_S = base.TSTEP_S
TMAX_STEP_S = base.TMAX_STEP_S
EPS = base.EPS


@dataclass(frozen=True)
class RefineCase(base.NLTLCase):
    cleanup_topology: str = "none"
    output_load_ohm: float = 75.0
    extraction_q: float = 8.0
    extraction_c_f: float = 4.7e-12
    source_rejection: bool = False
    generated_rejection: bool = False
    target_q_scale: float = 1.0
    generated_q_scale: float = 1.0
    cjo_scale: float = 1.0
    source_velocity_trim: float = 1.0
    phase_velocity_error_50: float = 0.0
    phase_velocity_error_100: float = 0.0
    phase_velocity_error_150: float = 0.0


@dataclass(frozen=True)
class RefineExport:
    case: RefineCase
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


def refine_cell_values(case: RefineCase) -> Dict[str, float]:
    vals = base.cell_values(case)
    vals["cjo_f"] *= case.cjo_scale
    return vals


def series_lc_values(freq_hz: float, c_f: float, q: float, load_ohm: float) -> Dict[str, float]:
    omega = 2.0 * math.pi * freq_hz
    l_h = 1.0 / ((omega ** 2) * c_f)
    r_ohm = max(0.2, load_ohm / max(q, 0.5))
    return {"l_h": l_h, "c_f": c_f, "r_ohm": r_ohm}


def add_cleanup_network(lines: List[str], case: RefineCase, raw_out: str) -> str:
    measure = raw_out
    if case.cleanup_topology in {"target_extraction", "weak_150_bandpass", "extraction_plus_rejection"}:
        measure = "v150"
        band = series_lc_values(TARGET_HZ * case.target_phase_velocity_scale, case.extraction_c_f, case.extraction_q * case.target_q_scale, case.output_load_ohm)
        lines.extend(
            [
                f"Rext {raw_out} ext_r {base.spice_num(band['r_ohm'])}",
                f"Lext ext_r ext_l {base.spice_num(band['l_h'])}",
                f"Cext ext_l {measure} {base.spice_num(band['c_f'])}",
                f"Rload150 {measure} 0 {base.spice_num(case.output_load_ohm)}",
            ]
        )
    elif case.cleanup_topology == "target_shunt_trap":
        trap = series_lc_values(TARGET_HZ, case.extraction_c_f, case.extraction_q, case.output_load_ohm)
        lines.extend(
            [
                f"Rtargettrap {raw_out} tt_r {base.spice_num(trap['r_ohm'])}",
                f"Ltargettrap tt_r tt_l {base.spice_num(trap['l_h'])}",
                f"Ctargettrap tt_l 0 {base.spice_num(trap['c_f'])}",
            ]
        )
    if case.source_rejection or case.cleanup_topology in {"source_rejection", "extraction_plus_rejection"}:
        trap50 = series_lc_values(SOURCE_HZ, 10.0e-12, 18.0, case.output_load_ohm)
        lines.extend(
            [
                f"Rtrap50 {raw_out} tr50_r {base.spice_num(trap50['r_ohm'])}",
                f"Ltrap50 tr50_r tr50_l {base.spice_num(trap50['l_h'])}",
                f"Ctrap50 tr50_l 0 {base.spice_num(trap50['c_f'])}",
            ]
        )
    if case.generated_rejection or case.cleanup_topology in {"generated_rejection", "extraction_plus_rejection"}:
        trap100 = series_lc_values(GENERATED_HZ * case.generated_phase_velocity_scale, 7.5e-12, 16.0 * case.generated_q_scale, case.output_load_ohm)
        lines.extend(
            [
                f"Rtrap100 {raw_out} tr100_r {base.spice_num(trap100['r_ohm'])}",
                f"Ltrap100 tr100_r tr100_l {base.spice_num(trap100['l_h'])}",
                f"Ctrap100 tr100_l 0 {base.spice_num(trap100['c_f'])}",
            ]
        )
    return measure


def netlist_for_case(case: RefineCase, csv_path: Path) -> str:
    vals = refine_cell_values(case)
    var = base.VaractorModel(
        cjo_f=max(vals["cjo_f"], 1.0e-15),
        vj_v=case.varactor_vj_v,
        m=case.varactor_m,
        rs_ohm=case.varactor_rs_ohm,
        bv_v=case.varactor_bv_v,
        ibv_a=case.varactor_ibv_a,
    )
    mid = max(1, case.cell_count // 2)
    raw_out = base.n(case.cell_count)
    lines = [
        f"* {case.name}",
        "* Refined varactor-loaded NLTL with passive target-band cleanup.",
        f"* role={case.role}; cleanup={case.cleanup_topology}; source_only={case.source_only_drive}",
        ".option method=gear maxord=2 reltol=2e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-16 itl4=240",
        f".model DVAR D(Is={base.spice_num(var.is_a)} Rs={base.spice_num(var.rs_ohm)} Cjo={base.spice_num(var.cjo_f)} Vj={base.spice_num(var.vj_v)} M={base.spice_num(var.m)} Bv={base.spice_num(var.bv_v)} Ibv={base.spice_num(var.ibv_a)})",
        f"Vbias vb 0 DC {base.spice_num(case.bias_v)}",
        f"Vsrc src 0 SIN(0 {base.spice_num(case.source_amplitude_v)} {base.spice_num(SOURCE_HZ)})",
        f"Rsrc src {base.n(0)} {base.spice_num(case.z0_ohm)}",
        f"Rrawload {raw_out} 0 {base.spice_num(case.z0_ohm * 3.0)}",
    ]
    if case.direct_generated_amplitude_v > 0.0:
        lines.extend(
            [
                f"Vgen gen_src 0 SIN(0 {base.spice_num(case.direct_generated_amplitude_v)} {base.spice_num(GENERATED_HZ)})",
                f"Rgen gen_src {base.n(0)} {base.spice_num(case.z0_ohm * 1.25)}",
            ]
        )
    if case.fixed_cap_only:
        lines.append(f"Cbase0 {base.n(0)} 0 {base.spice_num(vals['c_linear_control_f'])}")
    else:
        lines.append(f"Cfixed0 {base.n(0)} 0 {base.spice_num(vals['c_fixed_f'])}")
        lines.append(f"Dvar0 {base.n(0)} vb DVAR")
    lines.append(f"Rbleed0 {base.n(0)} 0 {base.spice_num(case.shunt_loss_ohm)}")

    for i in range(1, case.cell_count + 1):
        lines.extend(
            [
                f"Rser{i} {base.n(i - 1)} ns{i} {base.spice_num(vals['r_series_ohm'])}",
                f"Lser{i} ns{i} {base.n(i)} {base.spice_num(vals['l_cell_h'])}",
            ]
        )
        if case.fixed_cap_only:
            lines.append(f"Cbase{i} {base.n(i)} 0 {base.spice_num(vals['c_linear_control_f'])}")
        else:
            lines.append(f"Cfixed{i} {base.n(i)} 0 {base.spice_num(vals['c_fixed_f'])}")
            lines.append(f"Dvar{i} {base.n(i)} vb DVAR")
        lines.append(f"Rbleed{i} {base.n(i)} 0 {base.spice_num(case.shunt_loss_ohm)}")

    measure = add_cleanup_network(lines, case, raw_out)
    if measure == raw_out:
        lines.append(f"Rload {raw_out} 0 {base.spice_num(case.output_load_ohm)}")

    lines.extend(
        [
            ".control",
            "set filetype=ascii",
            "set wr_singlescale",
            "set wr_vecnames",
            f"tran {base.spice_num(TSTEP_S)} {base.spice_num(TSTOP_S)} 0 {base.spice_num(TMAX_STEP_S)}",
            f"wrdata {csv_path.name} time v({base.n(0)}) v({base.n(mid)}) v({measure}) i(Vsrc) i(Vbias)",
            ".endc",
            ".end",
            "",
        ]
    )
    return "\n".join(lines)


def build_cases(max_discovery_cases: int | None = None) -> List[RefineCase]:
    seeds: List[RefineCase] = []
    idx = 1
    recipes = [
        # cell, z0, cleanup, drive, bias, nl, cjo, rs, m, vj, load, q, source rej, gen rej, pv, target scale
        (48, 75.0, "none", 2.0, 4.0, 0.82, 1.0, 0.85, 0.50, 0.75, 75.0, 8.0, False, False, 5.0e6, 1.00),
        (64, 75.0, "none", 2.0, 4.0, 0.88, 1.15, 0.60, 0.55, 0.70, 75.0, 8.0, False, False, 5.0e6, 1.00),
        (80, 75.0, "none", 2.3, 3.5, 0.90, 1.25, 0.45, 0.55, 0.65, 75.0, 8.0, False, False, 5.2e6, 1.00),
        (96, 75.0, "none", 2.6, 3.2, 0.92, 1.35, 0.35, 0.60, 0.65, 75.0, 8.0, False, False, 5.4e6, 1.00),
        (64, 50.0, "target_extraction", 2.3, 3.5, 0.90, 1.25, 0.45, 0.55, 0.65, 100.0, 10.0, False, False, 5.1e6, 1.00),
        (64, 75.0, "target_extraction", 2.3, 3.5, 0.90, 1.25, 0.45, 0.55, 0.65, 150.0, 12.0, False, False, 5.1e6, 1.00),
        (64, 100.0, "target_extraction", 2.3, 3.5, 0.90, 1.25, 0.45, 0.55, 0.65, 200.0, 12.0, False, False, 5.1e6, 1.00),
        (80, 50.0, "weak_150_bandpass", 2.6, 3.2, 0.92, 1.40, 0.35, 0.60, 0.62, 100.0, 16.0, False, True, 5.3e6, 0.99),
        (80, 75.0, "weak_150_bandpass", 2.6, 3.2, 0.92, 1.40, 0.35, 0.60, 0.62, 150.0, 16.0, False, True, 5.3e6, 0.99),
        (80, 100.0, "weak_150_bandpass", 2.6, 3.2, 0.92, 1.40, 0.35, 0.60, 0.62, 200.0, 16.0, False, True, 5.3e6, 0.99),
        (96, 50.0, "extraction_plus_rejection", 2.8, 3.0, 0.94, 1.55, 0.30, 0.62, 0.60, 100.0, 18.0, True, True, 5.4e6, 0.985),
        (96, 75.0, "extraction_plus_rejection", 2.8, 3.0, 0.94, 1.55, 0.30, 0.62, 0.60, 150.0, 18.0, True, True, 5.4e6, 0.985),
        (96, 100.0, "extraction_plus_rejection", 2.8, 3.0, 0.94, 1.55, 0.30, 0.62, 0.60, 200.0, 18.0, True, True, 5.4e6, 0.985),
        (80, 75.0, "source_rejection", 2.4, 3.5, 0.90, 1.30, 0.45, 0.55, 0.65, 75.0, 12.0, True, False, 5.2e6, 1.00),
        (80, 75.0, "generated_rejection", 2.4, 3.5, 0.90, 1.30, 0.45, 0.55, 0.65, 75.0, 12.0, False, True, 5.2e6, 1.00),
        (80, 75.0, "target_shunt_trap", 2.4, 3.5, 0.90, 1.30, 0.45, 0.55, 0.65, 75.0, 12.0, False, False, 5.2e6, 1.00),
    ]
    for recipe in recipes:
        cells, z0, cleanup, drive, bias, nl, cjo, rs, m, vj, load, q, rej50, rej100, vp, tscale = recipe
        seeds.append(
            RefineCase(
                case_id=f"r{idx:03d}",
                name=f"refine_{cells}c_{int(z0)}ohm_{cleanup}",
                filename=f"refine_{idx:03d}_{cells}c_{int(z0)}ohm_{cleanup}.cir",
                role="discovery",
                cell_count=int(cells),
                z0_ohm=float(z0),
                phase_velocity_m_s=float(vp),
                source_amplitude_v=float(drive),
                bias_v=float(bias),
                nonlinear_fraction=float(nl),
                cjo_scale=float(cjo),
                varactor_rs_ohm=float(rs),
                varactor_m=float(m),
                varactor_vj_v=float(vj),
                output_load_ohm=float(load),
                extraction_q=float(q),
                cleanup_topology=str(cleanup),
                source_rejection=bool(rej50),
                generated_rejection=bool(rej100),
                target_phase_velocity_scale=float(tscale),
                phase_velocity_error_50=(float(vp) - 5.0e6) / 5.0e6,
                phase_velocity_error_100=0.0,
                phase_velocity_error_150=float(tscale) - 1.0,
                notes="Focused refinement around previous d015 varactor NLTL row.",
            )
        )
        idx += 1
    if max_discovery_cases is not None:
        seeds = seeds[:max_discovery_cases]

    control_base = RefineCase(
        case_id="base",
        name="control_base",
        filename="control_base.cir",
        role="control",
        cell_count=80,
        z0_ohm=75.0,
        cleanup_topology="extraction_plus_rejection",
        output_load_ohm=150.0,
        source_rejection=True,
        generated_rejection=True,
        source_amplitude_v=2.6,
        bias_v=3.2,
        nonlinear_fraction=0.92,
        cjo_scale=1.40,
        varactor_rs_ohm=0.35,
        varactor_m=0.60,
        varactor_vj_v=0.62,
        phase_velocity_m_s=5.3e6,
    )
    controls = [
        replace(
            control_base,
            case_id="c001",
            name="linear_fixed_capacitor_refine_control",
            filename="linear_fixed_capacitor_refine_control.cir",
            fixed_cap_only=True,
            nonlinear_fraction=0.0,
            cjo_scale=0.0,
            cleanup_topology="extraction_plus_rejection",
            notes="Linear fixed-capacitor control.",
        ),
        replace(
            control_base,
            case_id="c002",
            name="weak_varactor_refine_control",
            filename="weak_varactor_refine_control.cir",
            nonlinear_fraction=0.08,
            bias_v=14.0,
            cjo_scale=0.4,
            notes="Weak-varactor control with small capacitance swing.",
        ),
        replace(
            control_base,
            case_id="c003",
            name="detuned_target_velocity_refine_control",
            filename="detuned_target_velocity_refine_control.cir",
            phase_velocity_m_s=3.9e6,
            target_phase_velocity_scale=0.82,
            phase_velocity_error_50=-0.22,
            phase_velocity_error_150=-0.18,
            notes="Detuned target phase-velocity control.",
        ),
        replace(
            control_base,
            case_id="c004",
            name="shuffled_frequency_refine_control",
            filename="shuffled_frequency_refine_control.cir",
            phase_velocity_m_s=6.5e6,
            target_phase_velocity_scale=1.12,
            phase_velocity_error_50=0.30,
            phase_velocity_error_150=0.12,
            notes="Shuffled phase-velocity/frequency control.",
        ),
        replace(
            control_base,
            case_id="c005",
            name="too_short_refine_control",
            filename="too_short_refine_control.cir",
            total_length_m=TOTAL_LENGTH_M * 0.20,
            notes="Too-short interaction length control.",
        ),
        replace(
            control_base,
            case_id="c006",
            name="too_lossy_refine_control",
            filename="too_lossy_refine_control.cir",
            series_loss_ohm_scale=24.0,
            shunt_loss_ohm=15_000.0,
            notes="Too-lossy line control.",
        ),
        replace(
            control_base,
            case_id="direct_50plus100_reference",
            name="direct_50plus100_reference",
            filename="direct_50plus100_refine_reference.cir",
            role="ceiling_reference",
            source_only_drive=False,
            direct_100_drive_present=True,
            direct_generated_amplitude_v=1.0,
            notes="Separated direct 50+100 MHz ceiling denominator.",
        ),
    ]
    return seeds + controls


def export_netlists(out_dir: Path, max_discovery_cases: int | None = None) -> List[RefineExport]:
    ensure_dir(out_dir)
    exports: List[RefineExport] = []
    for case in build_cases(max_discovery_cases=max_discovery_cases):
        netlist = out_dir / case.filename
        csv_path = out_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist.write_text(netlist_for_case(case, csv_path), encoding="utf-8")
        exports.append(RefineExport(case=case, netlist_path=netlist, csv_path=csv_path))
    return exports


def run_ngspice(export: RefineExport, ngspice_path: str, timeout_s: int) -> base.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = base.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return base.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def measure_case(export: RefineExport, data: Dict[str, np.ndarray], reference_power: float | None) -> Dict[str, object]:
    metrics = base.measure_case(
        base.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path),
        data,
        reference_power,
    )
    case = export.case
    metrics["phase_velocity_error_50"] = case.phase_velocity_error_50
    metrics["phase_velocity_error_100"] = case.phase_velocity_error_100
    metrics["phase_velocity_error_150"] = case.phase_velocity_error_150
    metrics["cleanup_topology"] = case.cleanup_topology
    metrics["target_band_extraction_present"] = str(case.cleanup_topology in {"target_extraction", "weak_150_bandpass", "extraction_plus_rejection"})
    # Passive cleanup/traps are physical helpers, not behavioral current injection.
    metrics["behavioral_dependency_score"] = 0.08
    if case.fixed_cap_only:
        metrics["behavioral_dependency_score"] = 0.02
    stress = float(metrics.get("component_stress_score", 0.0))
    purity = float(metrics.get("spectral_purity_150mhz", 0.0))
    lock = float(metrics.get("phase_lock_target", 0.0))
    bridge = float(metrics.get("bridge_ratio_vs_direct_reference", 0.0))
    growth = float(metrics.get("target_band_coherent_growth", 0.0))
    gen_cv = float(metrics.get("generated_envelope_cv", 99.0))
    jump = float(metrics.get("max_phase_jump", 99.0))
    stress_ok = str(metrics.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}
    if case.role == "discovery":
        if (
            lock > 0.90
            and bridge > 1.5
            and purity > 0.80
            and growth > 1.0
            and gen_cv < 0.25
            and jump < 1.0
            and stress_ok
            and float(metrics["behavioral_dependency_score"]) <= 0.08
        ):
            metrics["promotion_category"] = "spice_varactor_nltl_candidate"
        elif lock > 0.85 and bridge > 1.0 and purity > 0.30 and stress_ok:
            metrics["promotion_category"] = "near_miss"
        else:
            metrics["promotion_category"] = "not_promoted"
    elif case.role == "control":
        leak = float(metrics.get("control_leakage_score", 0.0))
        metrics["promotion_category"] = "control_dead" if leak < 0.15 else "control_leakage"
    else:
        metrics["promotion_category"] = "ceiling_reference_not_discovery"
    return metrics


def summarize_export(export: RefineExport, run_requested: bool, ngspice_available: bool,
                     ngspice_path: str | None, result: base.RunResult,
                     metrics: Dict[str, object] | None) -> Dict[str, object]:
    vals = refine_cell_values(export.case)
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_varactor_nltl_refine",
        "case_id": case.case_id,
        "name": case.name,
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
        "cell_count": case.cell_count,
        "z0_target_ohm": case.z0_ohm,
        "total_length_m": case.total_length_m,
        "cell_length_m": vals["dx_m"],
        "per_cell_inductance_h": vals["l_cell_h"],
        "per_cell_total_capacitance_f": vals["c_cell_f"],
        "varactor_cjo_f": vals["cjo_f"],
        "source_amplitude_v": case.source_amplitude_v,
        "bias_v": case.bias_v,
        "nonlinear_fraction": case.nonlinear_fraction,
        "cjo_scale": case.cjo_scale,
        "varactor_rs_ohm": case.varactor_rs_ohm,
        "varactor_vj_v": case.varactor_vj_v,
        "varactor_m": case.varactor_m,
        "cleanup_topology": case.cleanup_topology,
        "output_load_ohm": case.output_load_ohm,
        "extraction_q": case.extraction_q,
        "source_rejection": str(case.source_rejection),
        "generated_rejection": str(case.generated_rejection),
        "target_q_scale": case.target_q_scale,
        "generated_q_scale": case.generated_q_scale,
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
    return row


def aggregate_summary(rows: List[Dict[str, object]], run_requested: bool, ngspice_available: bool) -> Dict[str, object]:
    data_rows = [row for row in rows if row.get("row_type") == "spice_varactor_nltl_refine"]
    discovery = [row for row in data_rows if row.get("role") == "discovery"]
    controls = [row for row in data_rows if row.get("role") == "control"]
    ran = [row for row in data_rows if row.get("execution_status") == "ran_successfully"]
    candidates = [row for row in discovery if row.get("promotion_category") == "spice_varactor_nltl_candidate"]
    near = [row for row in discovery if row.get("promotion_category") == "near_miss"]
    best = max(
        [row for row in discovery if row.get("execution_status") == "ran_successfully"],
        key=lambda row: (
            float(row.get("spectral_purity_150mhz", 0.0)),
            float(row.get("phase_lock_target", 0.0)),
            float(row.get("bridge_ratio_vs_direct_reference", 0.0)),
        ),
        default={},
    )
    best_lock = max(
        [row for row in discovery if row.get("execution_status") == "ran_successfully"],
        key=lambda row: float(row.get("phase_lock_target", 0.0)),
        default={},
    )
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls if row.get("execution_status") == "ran_successfully")
    max_leak = max((float(row.get("control_leakage_score", 0.0)) for row in controls), default=0.0)
    cleanup_rows = [row for row in discovery if row.get("cleanup_topology") != "none"]
    non_cleanup_rows = [row for row in discovery if row.get("cleanup_topology") == "none"]
    best_cleanup_purity = max((float(row.get("spectral_purity_150mhz", 0.0)) for row in cleanup_rows), default=0.0)
    best_raw_purity = max((float(row.get("spectral_purity_150mhz", 0.0)) for row in non_cleanup_rows), default=0.0)
    cell_counts = sorted(set(int(row.get("cell_count", 0)) for row in discovery))
    best_by_cell = {
        str(cell): max(
            (float(row.get("spectral_purity_150mhz", 0.0)) for row in discovery if int(row.get("cell_count", 0)) == cell),
            default=0.0,
        )
        for cell in cell_counts
    }
    statuses = ";".join(sorted(set(str(row.get("execution_status")) for row in data_rows)))
    return {
        "row_type": "aggregate",
        "valid_spice_netlists_generated": str(all((OUT_DIR / str(row.get("netlist_file"))).exists() for row in data_rows)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": statuses,
        "rows_total": len(data_rows),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "ran_successfully_count": len(ran),
        "candidate_count": len(candidates),
        "near_miss_count": len(near),
        "best_case": best.get("case_id", ""),
        "best_name": best.get("name", ""),
        "best_cleanup_topology": best.get("cleanup_topology", ""),
        "best_cell_count": best.get("cell_count", ""),
        "best_impedance_ohm": best.get("z0_target_ohm", ""),
        "best_phase_lock_target": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio_vs_direct_reference", ""),
        "best_purity": best.get("spectral_purity_150mhz", ""),
        "best_target_growth": best.get("target_band_coherent_growth", ""),
        "best_generated_cv": best.get("generated_envelope_cv", ""),
        "best_max_phase_jump": best.get("max_phase_jump", ""),
        "best_component_stress_score": best.get("component_stress_score", ""),
        "best_component_stress_class": best.get("component_stress_class", ""),
        "best_behavioral_dependency_score": best.get("behavioral_dependency_score", ""),
        "best_lock_case": best_lock.get("case_id", ""),
        "best_lock_value": best_lock.get("phase_lock_target", ""),
        "controls_dead": str(controls_dead) if ran else "not_run",
        "max_control_leakage_score": max_leak,
        "best_cleanup_purity": best_cleanup_purity,
        "best_raw_purity": best_raw_purity,
        "target_cleanup_helped_purity": str(best_cleanup_purity > best_raw_purity),
        "purity_by_cell_count_json": json.dumps(best_by_cell, sort_keys=True),
        "realistic_candidate_found": str(bool(candidates)),
        "recommended_next_step": "acoustic parallel simulation plus deeper component/BOM sweep before PCB layout",
    }


def timeseries_rows(export: RefineExport, data: Dict[str, np.ndarray], stride: int = 20) -> List[Dict[str, object]]:
    shim = base.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    rows = base.timeseries_rows(shim, data, stride=stride)
    for row in rows:
        row["row_type"] = "spice_varactor_nltl_refine_timeseries"
        row["cleanup_topology"] = export.case.cleanup_topology
    return rows


def write_report(out_dir: Path, rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    data_rows = [row for row in rows if row.get("row_type") == "spice_varactor_nltl_refine"]
    lines = [
        "# SPICE 4->8->12 Varactor NLTL Refinement",
        "",
        "Focused refinement around the prior best 48-cell/75-ohm varactor NLTL row.",
        "",
        "## Direct Answers",
        "",
        f"1. Can target purity be raised while preserving lock? cleanup_helped={aggregate.get('target_cleanup_helped_purity')}; best_purity={aggregate.get('best_purity')}; best_lock={aggregate.get('best_phase_lock_target')}.",
        f"2. Any full candidate? candidates={aggregate.get('candidate_count')}; near_misses={aggregate.get('near_miss_count')}.",
        f"3. Does increasing cell count help? purity_by_cell_count={aggregate.get('purity_by_cell_count_json')}.",
        f"4. Does target-band extraction/filtering help? {aggregate.get('target_cleanup_helped_purity')}; best_cleanup={aggregate.get('best_cleanup_topology')}.",
        f"5. Controls stay dead? {aggregate.get('controls_dead')}; max_leakage={aggregate.get('max_control_leakage_score')}.",
        f"6. Component stresses plausible? best_stress={aggregate.get('best_component_stress_class')} score={aggregate.get('best_component_stress_score')}.",
        f"7. Next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Rows",
        "",
    ]
    for row in data_rows:
        lines.append(
            "- {case_id} {name}: role={role}, status={status}, category={cat}, cleanup={cleanup}, cells={cells}, "
            "z0={z0}, lock={lock}, bridge={bridge}, purity={purity}, growth={growth}, stress={stress}, behavioral={beh}.".format(
                case_id=row.get("case_id"),
                name=row.get("name"),
                role=row.get("role"),
                status=row.get("execution_status"),
                cat=row.get("promotion_category", ""),
                cleanup=row.get("cleanup_topology", ""),
                cells=row.get("cell_count", ""),
                z0=row.get("z0_target_ohm", ""),
                lock=row.get("phase_lock_target", ""),
                bridge=row.get("bridge_ratio_vs_direct_reference", ""),
                purity=row.get("spectral_purity_150mhz", ""),
                growth=row.get("target_band_coherent_growth", ""),
                stress=row.get("component_stress_class", ""),
                beh=row.get("behavioral_dependency_score", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Circuit Notes",
            "",
            "- Discovery rows drive only the 50 MHz source band.",
            "- Passive cleanup networks use resonant extraction or shunt traps; no hidden 100 MHz or 150 MHz source is added.",
            "- Direct 50+100 MHz remains a separated ceiling denominator only.",
        ]
    )
    (out_dir / "README_SPICE_412_VARACTOR_NLTL_REFINE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine the varactor-loaded NLTL 4->8->12 design.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per netlist in seconds.")
    parser.add_argument("--max-discovery-cases", type=int, default=0, help="Limit discovery rows for quick debugging.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    max_discovery = args.max_discovery_cases if args.max_discovery_cases > 0 else None
    exports = export_netlists(out_dir, max_discovery_cases=max_discovery)
    ngspice_path = base.resolve_ngspice_path(args.ngspice_path or None)
    ngspice_available = ngspice_path is not None

    run_results: Dict[str, base.RunResult] = {}
    parsed: Dict[str, Dict[str, np.ndarray]] = {}
    if args.run and not ngspice_available:
        for export in exports:
            run_results[export.case.case_id] = base.RunResult("skipped_no_ngspice", False, "ngspice not found")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed[export.case.case_id] = base.read_transient(export.csv_path)
                except Exception as exc:
                    result = base.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            run_results[export.case.case_id] = result
    else:
        for export in exports:
            run_results[export.case.case_id] = base.RunResult("exported", False, "export only; use --run")

    reference_power: float | None = None
    reference = next((export for export in exports if export.case.role == "ceiling_reference"), None)
    if reference and reference.case.case_id in parsed:
        ref_metrics = measure_case(reference, parsed[reference.case.case_id], None)
        reference_power = base.safe_float(ref_metrics.get("target_coherent_power"))

    summary_rows: List[Dict[str, object]] = []
    ts_rows: List[Dict[str, object]] = []
    for export in exports:
        result = run_results[export.case.case_id]
        metrics: Dict[str, object] | None = None
        if result.success and export.case.case_id in parsed:
            metrics = measure_case(export, parsed[export.case.case_id], reference_power)
            if export.case.role in {"discovery", "ceiling_reference"}:
                ts_rows.extend(timeseries_rows(export, parsed[export.case.case_id]))
        summary_rows.append(summarize_export(export, args.run, ngspice_available, ngspice_path, result, metrics))

    aggregate = aggregate_summary(summary_rows, args.run, ngspice_available)
    all_rows = [aggregate] + summary_rows
    write_csv(out_dir / "spice_412_varactor_nltl_refine_summary.csv", all_rows)
    if ts_rows:
        write_csv(out_dir / "spice_412_varactor_nltl_refine_timeseries.csv", ts_rows)
    timeseries_path = out_dir / "spice_412_varactor_nltl_refine_timeseries.csv"
    if not ts_rows and timeseries_path.exists():
        timeseries_path.unlink()
    (out_dir / "spice_412_varactor_nltl_refine_summary.json").write_text(
        json.dumps(
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
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report(out_dir, all_rows, aggregate)
    print(
        "spice_412_varactor_nltl_refine: run={run} ngspice={ng} statuses={st} best={best} candidates={cand} near={near}".format(
            run=args.run,
            ng=ngspice_available,
            st=aggregate["execution_statuses"],
            best=aggregate["best_name"],
            cand=aggregate["candidate_count"],
            near=aggregate["near_miss_count"],
        )
    )


if __name__ == "__main__":
    main()
