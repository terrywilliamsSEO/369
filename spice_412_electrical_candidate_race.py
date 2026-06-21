#!/usr/bin/env python3
"""Electrical implementation race for the distributed 4->8->12 bridge.

This script compares several realistic or component-adjacent electrical
transmission-line families at 50/100/150 MHz.  It intentionally keeps the race
bounded: each row is a representative candidate covering the requested sweep
axes rather than a full combinatorial search.  Discovery rows drive only the
50 MHz source band; direct 50+100 MHz appears only as a separated ceiling
reference.
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

import spice_412_varactor_nltl_design as design
import spice_412_varactor_nltl_refine as refine


OUT_DIR = Path("runs") / "spice_412_electrical_candidate_race"
SOURCE_HZ = design.SOURCE_HZ
GENERATED_HZ = design.GENERATED_HZ
TARGET_HZ = design.TARGET_HZ
EPS = 1e-30


@dataclass(frozen=True)
class RaceCase(refine.RefineCase):
    family: str = "varactor_loaded_nltl"
    phase_velocity_trim_50: float = 0.0
    phase_velocity_trim_100: float = 0.0
    phase_velocity_trim_150: float = 0.0
    source_generator_rejection_strength: float = 0.0
    target_bandpass_coupling: float = 0.0
    terminal_matching_scale: float = 1.0
    nonlinear_strength_scale: float = 1.0
    component_stress_limit: float = 1.35
    step_recovery_charge_proxy: float = 0.0
    step_recovery_sharpness: float = 0.0
    magnetic_strength: float = 0.0
    magnetic_saturation_current_a: float = 0.0
    magnetic_hysteresis_loss: float = 0.0
    hybrid_relative_phase: float = 0.0
    alternating_nonlinear_sections: bool = False
    qpm_sign_flip: bool = False
    varactor_stack: str = "single"
    anti_series_varactors: bool = False
    distributed_bias_feed: bool = True


@dataclass(frozen=True)
class RaceExport:
    case: RaceCase
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
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def spice_num(value: float) -> str:
    if value == 0.0:
        return "0"
    return f"{value:.12g}"


def clean_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def race_cell_values(case: RaceCase) -> Dict[str, float]:
    return refine.refine_cell_values(case)


def additional_family_lines(case: RaceCase) -> List[str]:
    """Return component-adjacent nonlinear helper lines for non-varactor rows.

    The prior varactor tracks already use real diode capacitance models.  Step
    recovery and magnetic families still need first-pass SPICE proxies here, so
    they are counted in behavioral_dependency_score and labeled in each netlist.
    """
    lines: List[str] = []
    active_nodes = list(range(1, case.cell_count + 1, max(1, case.cell_count // 16)))
    if case.family in {
        "step_recovery_diode_line",
        "dual_path_phase_matched_line",
    }:
        k2 = 1.2e-5 * case.step_recovery_charge_proxy * case.nonlinear_strength_scale
        k3 = 3.0e-6 * case.step_recovery_sharpness * case.nonlinear_strength_scale
        lines.extend(
            [
                "* Step-recovery charge-storage proxy: nonlinear current from local line voltage.",
                f".param kstep2={spice_num(k2)}",
                f".param kstep3={spice_num(k3)}",
            ]
        )
        for i in active_nodes:
            sign = -1.0 if case.qpm_sign_flip and (i // max(1, case.cell_count // 8)) % 2 else 1.0
            lines.append(
                f"Bstep{i} {design.n(i)} 0 I={{({spice_num(sign)})*(kstep2*V({design.n(i)})*V({design.n(i)}) + kstep3*V({design.n(i)})*V({design.n(i)})*V({design.n(i)}))}}"
            )
    if case.family in {
        "nonlinear_magnetic_transmission_line",
        "magnetic_line_with_target_extraction",
        "hybrid_varactor_plus_magnetic_line",
        "dual_path_phase_matched_line",
    }:
        kmag = 2.4e-6 * case.magnetic_strength * case.nonlinear_strength_scale
        gcore = 4.0e-7 * max(case.magnetic_hysteresis_loss, 0.0)
        lines.extend(
            [
                "* Nonlinear magnetic core proxy: cubic shunt current plus small hysteretic loss.",
                f".param kmag={spice_num(kmag)}",
                f".param gcore={spice_num(gcore)}",
            ]
        )
        for i in active_nodes:
            sign = -1.0 if case.alternating_nonlinear_sections and (i // max(1, case.cell_count // 8)) % 2 else 1.0
            phase = 1.0 + 0.15 * math.sin(case.hybrid_relative_phase)
            lines.append(
                f"Bmag{i} {design.n(i)} 0 I={{({spice_num(sign * phase)})*kmag*V({design.n(i)})*V({design.n(i)})*V({design.n(i)}) + gcore*V({design.n(i)})}}"
            )
    return lines


def netlist_for_case(case: RaceCase, csv_path: Path) -> str:
    text = refine.netlist_for_case(case, csv_path)
    additions = additional_family_lines(case)
    header = [
        f"* electrical_family={case.family}",
        f"* behavioral helpers are scored; no direct 100 MHz or 150 MHz source appears in discovery rows.",
        f"* qpm_sign_flip={case.qpm_sign_flip}; alternating_sections={case.alternating_nonlinear_sections}; varactor_stack={case.varactor_stack}",
    ]
    text = text.replace("* Refined varactor-loaded NLTL with passive target-band cleanup.", "\n".join(header))
    if additions:
        text = text.replace(".control", "\n".join(additions) + "\n.control")
    return text


def case(
    case_id: str,
    family: str,
    cells: int,
    z0: float,
    length_m: float,
    cleanup: str,
    drive_v: float,
    nonlinear: float,
    phase_velocity_m_s: float = 5.0e6,
    bias_v: float = 3.4,
    cjo_scale: float = 1.2,
    rs: float = 0.45,
    vj: float = 0.65,
    m: float = 0.58,
    extraction_q: float = 14.0,
    output_load: float | None = None,
    source_rej: bool = False,
    gen_rej: bool = False,
    target_scale: float = 1.0,
    generated_scale: float = 1.0,
    fixed_cap_only: bool = False,
    band_shunts: bool = False,
    behavioral_helper: bool = False,
    series_loss_scale: float = 1.0,
    shunt_loss: float = 200_000.0,
    step_charge: float = 0.0,
    step_sharpness: float = 0.0,
    magnetic_strength: float = 0.0,
    magnetic_sat_i: float = 0.0,
    magnetic_loss: float = 0.0,
    hybrid_phase: float = 0.0,
    alternating: bool = False,
    qpm: bool = False,
    varactor_stack: str = "single",
    anti_series: bool = False,
    notes: str = "",
) -> RaceCase:
    name = f"{case_id}_{family}_{cells}c_{int(z0)}ohm_{cleanup}"
    return RaceCase(
        case_id=case_id,
        name=name,
        filename=f"{clean_name(name)}.cir",
        role="discovery",
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
        output_load_ohm=output_load if output_load is not None else z0 * 1.8,
        extraction_q=extraction_q,
        cleanup_topology=cleanup,
        source_rejection=source_rej,
        generated_rejection=gen_rej,
        target_phase_velocity_scale=target_scale,
        generated_phase_velocity_scale=generated_scale,
        fixed_cap_only=fixed_cap_only,
        band_shunts=band_shunts,
        behavioral_helper=behavioral_helper,
        series_loss_ohm_scale=series_loss_scale,
        shunt_loss_ohm=shunt_loss,
        phase_velocity_error_50=(phase_velocity_m_s - 5.0e6) / 5.0e6,
        phase_velocity_error_100=generated_scale - 1.0,
        phase_velocity_error_150=target_scale - 1.0,
        phase_velocity_trim_50=(phase_velocity_m_s - 5.0e6) / 5.0e6,
        phase_velocity_trim_100=generated_scale - 1.0,
        phase_velocity_trim_150=target_scale - 1.0,
        source_generator_rejection_strength=(0.45 if source_rej else 0.0) + (0.45 if gen_rej else 0.0),
        target_bandpass_coupling=extraction_q / 30.0 if cleanup != "none" else 0.0,
        terminal_matching_scale=(output_load if output_load is not None else z0 * 1.8) / max(z0, EPS),
        nonlinear_strength_scale=nonlinear,
        step_recovery_charge_proxy=step_charge,
        step_recovery_sharpness=step_sharpness,
        magnetic_strength=magnetic_strength,
        magnetic_saturation_current_a=magnetic_sat_i,
        magnetic_hysteresis_loss=magnetic_loss,
        hybrid_relative_phase=hybrid_phase,
        alternating_nonlinear_sections=alternating,
        qpm_sign_flip=qpm,
        varactor_stack=varactor_stack,
        anti_series_varactors=anti_series,
        notes=notes or f"Electrical candidate race row for {family}.",
    )


def build_cases(max_discovery_cases: int | None = None) -> List[RaceCase]:
    discovery = [
        case("e001", "varactor_loaded_nltl", 80, 75.0, 0.38, "none", 2.3, 0.90, cjo_scale=1.25, notes="Baseline realistic varactor NLTL."),
        case("e002", "varactor_loaded_nltl", 128, 100.0, 0.50, "none", 2.2, 0.88, cjo_scale=1.15, rs=0.35, bias_v=4.2, varactor_stack="series_stack"),
        case("e003", "step_recovery_diode_line", 64, 50.0, 0.38, "target_extraction", 2.5, 0.35, fixed_cap_only=True, behavioral_helper=True, step_charge=0.9, step_sharpness=1.2, extraction_q=12.0, notes="Step-recovery diode transit-time proxy plus target extraction."),
        case("e004", "step_recovery_diode_line", 96, 75.0, 0.50, "extraction_plus_rejection", 2.8, 0.40, fixed_cap_only=True, behavioral_helper=True, step_charge=1.2, step_sharpness=1.6, extraction_q=20.0, source_rej=True, gen_rej=True, qpm=True),
        case("e005", "nonlinear_magnetic_transmission_line", 80, 75.0, 0.75, "target_extraction", 2.8, 0.0, fixed_cap_only=True, behavioral_helper=True, magnetic_strength=1.0, magnetic_sat_i=0.08, magnetic_loss=0.35, extraction_q=14.0, series_loss_scale=2.0),
        case("e006", "nonlinear_magnetic_transmission_line", 128, 100.0, 0.75, "extraction_plus_rejection", 2.6, 0.0, fixed_cap_only=True, behavioral_helper=True, magnetic_strength=1.5, magnetic_sat_i=0.11, magnetic_loss=0.45, extraction_q=18.0, source_rej=True, gen_rej=True, alternating=True, series_loss_scale=2.6),
        case("e007", "hybrid_varactor_plus_magnetic_line", 96, 75.0, 0.50, "extraction_plus_rejection", 2.5, 0.82, cjo_scale=1.35, rs=0.34, magnetic_strength=0.55, magnetic_sat_i=0.10, magnetic_loss=0.25, extraction_q=18.0, source_rej=True, gen_rej=True, behavioral_helper=True, hybrid_phase=0.4),
        case("e008", "hybrid_varactor_plus_magnetic_line", 128, 100.0, 0.75, "extraction_plus_rejection", 2.3, 0.78, cjo_scale=1.20, rs=0.30, magnetic_strength=0.75, magnetic_sat_i=0.12, magnetic_loss=0.30, extraction_q=22.0, source_rej=True, gen_rej=True, behavioral_helper=True, alternating=True, qpm=True, hybrid_phase=1.2),
        case("e009", "varactor_line_with_high_q_target_extraction", 96, 100.0, 0.38, "extraction_plus_rejection", 2.45, 0.92, cjo_scale=1.45, rs=0.30, bias_v=3.2, extraction_q=26.0, output_load=180.0, source_rej=True, gen_rej=True, target_scale=0.985, varactor_stack="anti_series_pair", anti_series=True),
        case("e010", "varactor_line_with_high_q_target_extraction", 128, 100.0, 0.50, "extraction_plus_rejection", 2.2, 0.86, cjo_scale=1.20, rs=0.28, bias_v=4.0, extraction_q=30.0, output_load=220.0, source_rej=True, gen_rej=True, target_scale=0.990, varactor_stack="series_stack"),
        case("e011", "varactor_line_with_distributed_bandpass_sections", 80, 75.0, 0.38, "weak_150_bandpass", 2.4, 0.90, cjo_scale=1.30, rs=0.40, extraction_q=16.0, gen_rej=True, band_shunts=True, behavioral_helper=False),
        case("e012", "varactor_line_with_distributed_bandpass_sections", 96, 100.0, 0.50, "weak_150_bandpass", 2.2, 0.84, cjo_scale=1.18, rs=0.32, extraction_q=20.0, source_rej=True, gen_rej=True, band_shunts=True, target_scale=0.990),
        case("e013", "magnetic_line_with_target_extraction", 96, 75.0, 0.75, "extraction_plus_rejection", 2.6, 0.0, fixed_cap_only=True, behavioral_helper=True, magnetic_strength=1.7, magnetic_sat_i=0.10, magnetic_loss=0.35, extraction_q=24.0, source_rej=True, gen_rej=True, alternating=True),
        case("e014", "dual_path_phase_matched_line", 96, 75.0, 0.50, "extraction_plus_rejection", 2.4, 0.78, cjo_scale=1.20, rs=0.34, step_charge=0.6, step_sharpness=0.8, magnetic_strength=0.35, magnetic_sat_i=0.10, magnetic_loss=0.18, extraction_q=22.0, source_rej=True, gen_rej=True, behavioral_helper=True, hybrid_phase=0.8, qpm=True),
        case("e015", "dual_path_phase_matched_line", 128, 100.0, 0.75, "extraction_plus_rejection", 2.2, 0.72, cjo_scale=1.05, rs=0.30, step_charge=0.7, step_sharpness=1.0, magnetic_strength=0.45, magnetic_sat_i=0.12, magnetic_loss=0.22, extraction_q=26.0, source_rej=True, gen_rej=True, behavioral_helper=True, alternating=True, qpm=True, hybrid_phase=1.6),
        case("e016", "varactor_loaded_nltl", 48, 50.0, 0.25, "none", 2.0, 0.82, cjo_scale=1.0, rs=0.55, bias_v=4.5, notes="Short varactor line screening row."),
    ]
    if max_discovery_cases is not None:
        discovery = discovery[:max_discovery_cases]

    control_base = case(
        "base",
        "control",
        80,
        75.0,
        0.38,
        "extraction_plus_rejection",
        2.4,
        0.80,
        cjo_scale=1.25,
        rs=0.38,
        extraction_q=18.0,
        source_rej=True,
        gen_rej=True,
    )
    controls = [
        replace(control_base, case_id="c001", name="linear_fixed_component_line", filename="linear_fixed_component_line.cir", role="control", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, family="linear_fixed_component_line", notes="Linear fixed-component control."),
        replace(control_base, case_id="c002", name="weak_nonlinearity_line", filename="weak_nonlinearity_line.cir", role="control", nonlinear_fraction=0.08, bias_v=14.0, cjo_scale=0.35, family="weak_nonlinearity_line", notes="Weak nonlinearity control."),
        replace(control_base, case_id="c003", name="detuned_target_velocity_line", filename="detuned_target_velocity_line.cir", role="control", phase_velocity_m_s=3.9e6, target_phase_velocity_scale=0.82, phase_velocity_error_50=-0.22, phase_velocity_error_150=-0.18, family="detuned_target_velocity_line"),
        replace(control_base, case_id="c004", name="shuffled_frequency_line", filename="shuffled_frequency_line.cir", role="control", phase_velocity_m_s=6.5e6, target_phase_velocity_scale=1.12, generated_phase_velocity_scale=0.88, phase_velocity_error_50=0.30, phase_velocity_error_100=-0.12, phase_velocity_error_150=0.12, family="shuffled_frequency_line"),
        replace(control_base, case_id="c005", name="too_short_line", filename="too_short_line.cir", role="control", total_length_m=0.05, family="too_short_line"),
        replace(control_base, case_id="c006", name="too_lossy_line", filename="too_lossy_line.cir", role="control", series_loss_ohm_scale=28.0, shunt_loss_ohm=12_000.0, family="too_lossy_line"),
        replace(control_base, case_id="c007", name="phase_mismatched_line", filename="phase_mismatched_line.cir", role="control", phase_velocity_m_s=4.1e6, target_phase_velocity_scale=1.22, generated_phase_velocity_scale=0.91, phase_velocity_error_50=-0.18, phase_velocity_error_100=-0.09, phase_velocity_error_150=0.22, family="phase_mismatched_line"),
        replace(control_base, case_id="c008", name="target_extraction_only_no_nonlinearity", filename="target_extraction_only_no_nonlinearity.cir", role="control", fixed_cap_only=True, nonlinear_fraction=0.0, cjo_scale=0.0, family="target_extraction_only_no_nonlinearity"),
        replace(control_base, case_id="c009", name="nonlinearity_only_no_target_extraction", filename="nonlinearity_only_no_target_extraction.cir", role="control", cleanup_topology="none", source_rejection=False, generated_rejection=False, family="nonlinearity_only_no_target_extraction"),
        replace(
            control_base,
            case_id="direct_50plus100_reference",
            name="direct_50plus100_reference",
            filename="direct_50plus100_reference.cir",
            role="ceiling_reference",
            source_only_drive=False,
            direct_100_drive_present=True,
            direct_generated_amplitude_v=1.0,
            family="direct_50plus100_reference",
            notes="Separated direct 50+100 MHz ceiling denominator only.",
        ),
    ]
    return discovery + controls


def export_netlists(out_dir: Path, max_discovery_cases: int | None = None) -> List[RaceExport]:
    ensure_dir(out_dir)
    exports: List[RaceExport] = []
    for race_case in build_cases(max_discovery_cases=max_discovery_cases):
        netlist_path = out_dir / race_case.filename
        csv_path = out_dir / f"{Path(race_case.filename).stem}_tran.csv"
        netlist_path.write_text(netlist_for_case(race_case, csv_path), encoding="utf-8")
        exports.append(RaceExport(race_case, netlist_path, csv_path))
    return exports


def run_ngspice(export: RaceExport, ngspice_path: str, timeout_s: int) -> design.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = design.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return design.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def accumulated_phase_mismatch(case: RaceCase) -> float:
    wavelength = case.phase_velocity_m_s / SOURCE_HZ
    trim = abs(case.phase_velocity_error_50) + abs(case.phase_velocity_error_100) + abs(case.phase_velocity_error_150)
    return float(2.0 * math.pi * case.total_length_m / max(wavelength, EPS) * trim)


def behavioral_dependency(case: RaceCase) -> float:
    score = 0.08
    if case.fixed_cap_only:
        score = 0.02
    if case.family in {"step_recovery_diode_line", "nonlinear_magnetic_transmission_line", "magnetic_line_with_target_extraction"}:
        score = 0.16
    if case.family in {"hybrid_varactor_plus_magnetic_line", "dual_path_phase_matched_line"}:
        score = 0.18
    if case.band_shunts:
        score += 0.04
    if case.behavioral_helper:
        score += 0.02
    return min(score, 0.30)


def measure_case(export: RaceExport, data: Dict[str, np.ndarray], reference_power: float | None) -> Dict[str, object]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    metrics = design.measure_case(shim, data, reference_power)
    case = export.case
    beh = behavioral_dependency(case)
    metrics["family"] = case.family
    metrics["phase_velocity_error_50"] = case.phase_velocity_error_50
    metrics["phase_velocity_error_100"] = case.phase_velocity_error_100
    metrics["phase_velocity_error_150"] = case.phase_velocity_error_150
    metrics["accumulated_phase_mismatch"] = accumulated_phase_mismatch(case)
    metrics["cleanup_topology"] = case.cleanup_topology
    metrics["target_extraction_q"] = case.extraction_q
    metrics["target_extraction_gain"] = safe_float(metrics.get("target_fft_power")) / max(
        safe_float(metrics.get("source_fft_power")) + safe_float(metrics.get("generated_fft_power")),
        EPS,
    )
    metrics["target_rejection_source_generated_db"] = 10.0 * math.log10(
        max(safe_float(metrics.get("target_fft_power")), EPS)
        / max(safe_float(metrics.get("source_fft_power")) + safe_float(metrics.get("generated_fft_power")), EPS)
    )
    metrics["peak_voltage_v"] = metrics.get("varactor_peak_voltage_v", 0.0)
    metrics["peak_current_a"] = max(safe_float(metrics.get("source_peak_current_a")), safe_float(metrics.get("varactor_peak_current_a")))
    metrics["reverse_bias_margin_v"] = metrics.get("reverse_bias_margin_v", 0.0)
    metrics["dissipation_estimate_j"] = metrics.get("dissipation_estimate_j", 0.0)
    metrics["behavioral_dependency_score"] = beh
    metrics["source_generator_rejection_strength"] = case.source_generator_rejection_strength
    metrics["target_bandpass_output_coupling"] = case.target_bandpass_coupling
    metrics["terminal_matching_scale"] = case.terminal_matching_scale
    metrics["nonlinear_strength_scale"] = case.nonlinear_strength_scale
    metrics["step_recovery_charge_proxy"] = case.step_recovery_charge_proxy
    metrics["step_recovery_sharpness"] = case.step_recovery_sharpness
    metrics["magnetic_strength"] = case.magnetic_strength
    metrics["magnetic_saturation_current_a"] = case.magnetic_saturation_current_a
    metrics["magnetic_hysteresis_loss"] = case.magnetic_hysteresis_loss
    metrics["component_stress_limit"] = case.component_stress_limit

    stress = str(metrics.get("component_stress_class"))
    lock = safe_float(metrics.get("phase_lock_target"))
    bridge = safe_float(metrics.get("bridge_ratio_vs_direct_reference"))
    purity = safe_float(metrics.get("spectral_purity_150mhz"))
    growth = safe_float(metrics.get("target_band_coherent_growth"))
    gen_cv = safe_float(metrics.get("generated_envelope_cv"), 99.0)
    max_jump = safe_float(metrics.get("max_phase_jump"), 99.0)
    stress_ok = stress in {"plausible", "aggressive-but-testable"}
    if case.role == "discovery":
        if (
            lock > 0.90
            and bridge > 1.5
            and purity > 0.80
            and growth > 1.0
            and gen_cv < 0.25
            and max_jump < 1.0
            and stress_ok
            and beh <= 0.10
        ):
            promotion = "spice_electrical_412_candidate"
        elif lock > 0.85 and bridge > 1.0 and purity > 0.30 and stress_ok:
            promotion = "spice_electrical_412_near_miss"
        elif not stress_ok:
            promotion = "reject_due_to_component_stress"
        elif purity <= 0.30:
            promotion = "reject_due_to_low_purity"
        elif lock <= 0.85 or max_jump >= 1.0:
            promotion = "reject_due_to_phase_mismatch"
        else:
            promotion = "not_promoted"
    elif case.role == "control":
        material_leak = 0.0
        if purity > 0.20 and bridge > 1.0 and growth > 1.0 and lock > 0.50:
            material_leak = min(1.0, max(bridge - 1.0, 0.0) / 2.0 + max(purity - 0.20, 0.0))
        metrics["control_leakage_score"] = material_leak
        leak = material_leak
        promotion = "control_dead" if leak < 0.15 else "reject_due_to_control_leakage"
    else:
        promotion = "ceiling_reference_not_discovery"
    metrics["promotion_category"] = promotion
    return metrics


def summarize_export(
    export: RaceExport,
    run_requested: bool,
    ngspice_available: bool,
    ngspice_path: str | None,
    result: design.RunResult,
    metrics: Dict[str, object] | None,
) -> Dict[str, object]:
    vals = race_cell_values(export.case)
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_electrical_412_race",
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
        "varactor_stack": case.varactor_stack,
        "anti_series_varactors": str(case.anti_series_varactors),
        "distributed_bias_feed": str(case.distributed_bias_feed),
        "cleanup_topology": case.cleanup_topology,
        "output_load_ohm": case.output_load_ohm,
        "target_extraction_q": case.extraction_q,
        "source_rejection": str(case.source_rejection),
        "generated_rejection": str(case.generated_rejection),
        "band_shunts": str(case.band_shunts),
        "fixed_cap_only": str(case.fixed_cap_only),
        "behavioral_helper_present": str(case.behavioral_helper),
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
    elif result.execution_status in {"failed_to_converge", "parser_failed"} and case.role == "discovery":
        row["promotion_category"] = "reject_due_to_convergence"
    return row


def family_best(rows: List[Dict[str, object]], family: str) -> Dict[str, object]:
    candidates = [r for r in rows if r.get("family") == family and r.get("execution_status") == "ran_successfully"]
    return max(
        candidates,
        key=lambda r: (
            safe_float(r.get("spectral_purity_150mhz")),
            safe_float(r.get("bridge_ratio_vs_direct_reference")),
            safe_float(r.get("phase_lock_target")),
            safe_float(r.get("bench_feasibility_score")),
        ),
        default={},
    )


def aggregate_summary(rows: List[Dict[str, object]], run_requested: bool, ngspice_available: bool) -> Dict[str, object]:
    data = [r for r in rows if r.get("row_type") == "spice_electrical_412_race"]
    discovery = [r for r in data if r.get("role") == "discovery"]
    controls = [r for r in data if r.get("role") == "control"]
    ran = [r for r in data if r.get("execution_status") == "ran_successfully"]
    successful_discovery = [r for r in discovery if r.get("execution_status") == "ran_successfully"]
    controls_dead = all(r.get("promotion_category") == "control_dead" for r in controls if r.get("execution_status") == "ran_successfully")
    max_leak = max((safe_float(r.get("control_leakage_score")) for r in controls), default=0.0)
    candidates = [r for r in successful_discovery if r.get("promotion_category") == "spice_electrical_412_candidate"] if controls_dead else []
    near = [r for r in successful_discovery if r.get("promotion_category") == "spice_electrical_412_near_miss"] if controls_dead else []
    plausible = [r for r in successful_discovery if str(r.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}]
    best_overall = max(
        successful_discovery,
        key=lambda r: (
            safe_float(r.get("spectral_purity_150mhz")),
            safe_float(r.get("bridge_ratio_vs_direct_reference")),
            safe_float(r.get("phase_lock_target")),
            -safe_float(r.get("behavioral_dependency_score"), 1.0),
            safe_float(r.get("bench_feasibility_score")),
        ),
        default={},
    )
    best_purity_plausible = max(plausible, key=lambda r: safe_float(r.get("spectral_purity_150mhz")), default={})
    best_bridge = max(successful_discovery, key=lambda r: safe_float(r.get("bridge_ratio_vs_direct_reference")), default={})
    extraction_rows = [r for r in successful_discovery if r.get("cleanup_topology") != "none"]
    raw_rows = [r for r in successful_discovery if r.get("cleanup_topology") == "none"]
    extraction_best = max((safe_float(r.get("spectral_purity_150mhz")) for r in extraction_rows), default=0.0)
    raw_best = max((safe_float(r.get("spectral_purity_150mhz")) for r in raw_rows), default=0.0)
    families = sorted(set(str(r.get("family")) for r in discovery))
    family_rows = {
        fam: {
            "best_case": family_best(successful_discovery, fam).get("case_id", ""),
            "best_purity": family_best(successful_discovery, fam).get("spectral_purity_150mhz", 0.0),
            "best_bridge": family_best(successful_discovery, fam).get("bridge_ratio_vs_direct_reference", 0.0),
            "best_feasibility": family_best(successful_discovery, fam).get("bench_feasibility_score", 0.0),
        }
        for fam in families
    }
    statuses = ";".join(sorted(set(str(r.get("execution_status")) for r in data)))
    recommended = "BOM/component selection and PCB layout model" if candidates else "nonlinear magnetic/hybrid refinement plus acoustic demo branch"
    primary = str(best_overall.get("family", ""))
    if primary == "varactor_loaded_nltl" and not candidates:
        primary_route = "varactor remains a baseline but should be challenged by extraction/hybrid families"
    elif primary:
        primary_route = f"replace pure varactor as primary with {primary} for the next electrical refinement"
    else:
        primary_route = "insufficient SPICE data"
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "aggregate",
        "valid_spice_netlists_generated": str(all((OUT_DIR / str(r.get("netlist_file"))).exists() for r in data)),
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": statuses,
        "rows_total": len(data),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "ran_successfully_count": len(ran),
        "candidate_count": len(candidates),
        "near_miss_count": len(near),
        "strongest_family_overall": best_overall.get("family", ""),
        "strongest_case": best_overall.get("case_id", ""),
        "strongest_name": best_overall.get("name", ""),
        "strongest_feasibility": best_overall.get("bench_feasibility_score", ""),
        "strongest_lock": best_overall.get("phase_lock_target", ""),
        "strongest_bridge_ratio": best_overall.get("bridge_ratio_vs_direct_reference", ""),
        "strongest_purity": best_overall.get("spectral_purity_150mhz", ""),
        "strongest_stress_class": best_overall.get("component_stress_class", ""),
        "strongest_behavioral_dependency": best_overall.get("behavioral_dependency_score", ""),
        "best_purity_plausible_case": best_purity_plausible.get("case_id", ""),
        "best_purity_plausible_family": best_purity_plausible.get("family", ""),
        "best_purity_plausible_value": best_purity_plausible.get("spectral_purity_150mhz", ""),
        "best_bridge_case": best_bridge.get("case_id", ""),
        "best_bridge_family": best_bridge.get("family", ""),
        "best_bridge_ratio": best_bridge.get("bridge_ratio_vs_direct_reference", ""),
        "controls_dead": str(controls_dead) if ran else "not_run",
        "max_control_leakage_score": max_leak,
        "target_extraction_best_purity": extraction_best,
        "raw_line_best_purity": raw_best,
        "target_extraction_and_rejection_helped": str(extraction_best > raw_best),
        "family_summary_json": json.dumps(family_rows, sort_keys=True),
        "recommended_next_step": recommended,
        "primary_electrical_route_recommendation": primary_route,
    }


def timeseries_rows(export: RaceExport, data: Dict[str, np.ndarray], stride: int = 24) -> List[Dict[str, object]]:
    shim = design.NLTLExport(case=export.case, netlist_path=export.netlist_path, csv_path=export.csv_path)
    rows = design.timeseries_rows(shim, data, stride=stride)
    for row in rows:
        row["row_type"] = "spice_electrical_412_race_timeseries"
        row["family"] = export.case.family
        row["cleanup_topology"] = export.case.cleanup_topology
    return rows


def write_report(out_dir: Path, rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    data = [r for r in rows if r.get("row_type") == "spice_electrical_412_race"]
    lines = [
        "# SPICE 4->8->12 Electrical Candidate Race",
        "",
        "Bounded electrical family race at 50/100/150 MHz.",
        "",
        "## Direct Answers",
        "",
        f"1. Strongest electrical family overall: {aggregate.get('strongest_family_overall')} via {aggregate.get('strongest_case')} ({aggregate.get('strongest_name')}).",
        f"2. Any realistic electrical row promoted? candidates={aggregate.get('candidate_count')}.",
        f"3. Any near miss promoted? near_misses={aggregate.get('near_miss_count')}.",
        f"4. Best 150 MHz purity under plausible/aggressive stress: family={aggregate.get('best_purity_plausible_family')}, case={aggregate.get('best_purity_plausible_case')}, purity={aggregate.get('best_purity_plausible_value')}.",
        f"5. Best bridge ratio under clean controls: family={aggregate.get('best_bridge_family')}, case={aggregate.get('best_bridge_case')}, bridge={aggregate.get('best_bridge_ratio')}.",
        f"6. Do target extraction and rejection traps solve purity? helped={aggregate.get('target_extraction_and_rejection_helped')}; extraction_best={aggregate.get('target_extraction_best_purity')}; raw_best={aggregate.get('raw_line_best_purity')}.",
        f"7. Do controls stay dead? {aggregate.get('controls_dead')}; max_leakage={aggregate.get('max_control_leakage_score')}.",
        f"8. Next step: {aggregate.get('recommended_next_step')}.",
        f"9. Electrical route recommendation: {aggregate.get('primary_electrical_route_recommendation')}.",
        "",
        "## Rows",
        "",
    ]
    for row in data:
        lines.append(
            "- {case_id} {family}: role={role}, status={status}, category={cat}, cells={cells}, z0={z0}, "
            "length={length}, lock={lock}, bridge={bridge}, purity={purity}, growth={growth}, "
            "gen_cv={gen_cv}, stress={stress}, behavioral={behavioral}.".format(
                case_id=row.get("case_id"),
                family=row.get("family"),
                role=row.get("role"),
                status=row.get("execution_status"),
                cat=row.get("promotion_category", ""),
                cells=row.get("cell_count", ""),
                z0=row.get("z0_target_ohm", ""),
                length=row.get("total_length_m", ""),
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
            "- Direct 50+100 MHz is separated as a ceiling denominator only.",
            "- Step-recovery and magnetic rows use first-pass nonlinear current/inductance proxies and report higher behavioral dependency than the pure varactor rows.",
            "- This is a bounded race, not a full combinatorial sweep across every axis.",
        ]
    )
    (out_dir / "README_SPICE_412_ELECTRICAL_CANDIDATE_RACE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Race electrical 4->8->12 implementation families.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=160, help="Timeout per netlist in seconds.")
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
    write_csv(out_dir / "spice_412_electrical_candidate_race_summary.csv", all_rows)
    if timeseries:
        write_csv(out_dir / "spice_412_electrical_candidate_race_timeseries.csv", timeseries)
    elif (out_dir / "spice_412_electrical_candidate_race_timeseries.csv").exists():
        (out_dir / "spice_412_electrical_candidate_race_timeseries.csv").unlink()
    (out_dir / "spice_412_electrical_candidate_race_summary.json").write_text(
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
        "spice_412_electrical_candidate_race: run={run} ngspice={ng} statuses={statuses} strongest={strongest} candidates={candidates} near={near}".format(
            run=args.run,
            ng=ngspice_available,
            statuses=aggregate["execution_statuses"],
            strongest=aggregate["strongest_name"],
            candidates=aggregate["candidate_count"],
            near=aggregate["near_miss_count"],
        )
    )


if __name__ == "__main__":
    main()
