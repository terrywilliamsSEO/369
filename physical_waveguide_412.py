#!/usr/bin/env python3
"""Physical waveguide interpretation for the promoted 4->8->12 TL bridge.

This script maps the promoted normalized transmission-line result into rough
bench-scale waveguide and transmission-line candidates.  It is intentionally a
screening layer: it estimates phase matching, interaction length, loss,
nonlinear gain, stress, and feasibility without claiming hardware validation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional


OUT_DIR = Path("runs") / "physical_waveguide_412"
TL_SUMMARY_PATH = Path("runs") / "spice_412_transmission_line_refine" / "spice_412_tl_summary.json"

SOURCE_RATIO = 4.0
GENERATED_RATIO = 8.0
TARGET_RATIO = 12.0
NORMALIZED_CHAIN_LENGTH = 24.0
NORMALIZED_CELL_COUNT = 32
EPS = 1e-18

DEFAULT_TL_REFERENCE = {
    "lock": 0.997206257893873,
    "bridge_ratio": 8.261740025175394,
    "purity": 0.961441074707597,
    "target_coherent_growth": 3.9559572231806013,
    "generated_envelope_cv": 0.07088951452874445,
    "max_phase_jump": 0.05731592251889578,
    "behavioral_dependency_score": 0.36,
    "envelope_ladder_behavioral_baseline": 0.65,
}


@dataclass(frozen=True)
class PhysicalRealization:
    row_id: str
    name: str
    family: str
    role: str
    frequency_scale_note: str
    source_frequency_hz: float
    phase_velocity_4_m_s: float
    phase_velocity_8_ratio: float
    phase_velocity_12_ratio: float
    group_velocity_4_m_s: float
    group_velocity_8_ratio: float
    group_velocity_12_ratio: float
    loss_db_per_m: float
    q_requirement_note: str
    nonlinear_strength_relative: float
    component_stress_proxy: float
    material_maturity_score: float
    implementation_complexity_score: float
    interaction_length_scale: float = 1.0
    qpm_enabled: bool = False
    conceptual_only: bool = False
    direct_8_drive_present: bool = False
    direct_12_drive_present: bool = False
    target_frequency_injection_present: bool = False
    notes: str = ""


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


def finite_or_none(value: float) -> Optional[float]:
    return value if math.isfinite(value) else None


def sinc(x: float) -> float:
    if abs(x) < 1e-9:
        return 1.0
    return math.sin(x) / x


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def load_tl_reference(path: Path = TL_SUMMARY_PATH) -> Dict[str, float]:
    ref = dict(DEFAULT_TL_REFERENCE)
    if not path.exists():
        return ref
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        promoted = next((row for row in rows if row.get("case_id") == "t001"), None)
        aggregate = data.get("aggregate", {})
        if promoted:
            ref.update(
                {
                    "lock": float(promoted.get("phase_lock_target", ref["lock"])),
                    "bridge_ratio": float(promoted.get("bridge_ratio", ref["bridge_ratio"])),
                    "purity": float(promoted.get("target_spectral_purity", ref["purity"])),
                    "target_coherent_growth": float(
                        promoted.get("target_coherent_growth", ref["target_coherent_growth"])
                    ),
                    "generated_envelope_cv": float(
                        promoted.get("generated_envelope_cv", ref["generated_envelope_cv"])
                    ),
                    "max_phase_jump": float(promoted.get("max_phase_jump", ref["max_phase_jump"])),
                    "behavioral_dependency_score": float(
                        promoted.get("behavioral_dependency_score", ref["behavioral_dependency_score"])
                    ),
                }
            )
        if aggregate:
            ref["envelope_ladder_behavioral_baseline"] = 0.65
    except (OSError, ValueError, TypeError, StopIteration):
        return ref
    return ref


def build_realizations() -> List[PhysicalRealization]:
    varactor = PhysicalRealization(
        row_id="w004",
        name="nonlinear_varactor_loaded_transmission_line",
        family="nonlinear_varactor_loaded_transmission_line",
        role="physical_candidate",
        frequency_scale_note="Low RF electronics; source band near 50 MHz.",
        source_frequency_hz=50.0e6,
        phase_velocity_4_m_s=5.0e6,
        phase_velocity_8_ratio=1.002,
        phase_velocity_12_ratio=0.999,
        group_velocity_4_m_s=4.7e6,
        group_velocity_8_ratio=0.985,
        group_velocity_12_ratio=0.970,
        loss_db_per_m=1.0,
        q_requirement_note="Needs low-loss loaded-line Q in the tens to low hundreds.",
        nonlinear_strength_relative=1.05,
        component_stress_proxy=0.55,
        material_maturity_score=0.95,
        implementation_complexity_score=0.55,
        notes=(
            "Most direct electronics analog: tunable capacitance supplies the nonlinear mixing, "
            "and per-cell loading can tune phase velocity."
        ),
    )

    rows = [
        PhysicalRealization(
            row_id="w001",
            name="pcb_microstrip_or_coaxial_transmission_line_ladder",
            family="pcb_microstrip_or_coaxial_transmission_line_ladder",
            role="physical_candidate",
            frequency_scale_note="RF bench scale; source band near 100 MHz.",
            source_frequency_hz=100.0e6,
            phase_velocity_4_m_s=1.8e8,
            phase_velocity_8_ratio=0.992,
            phase_velocity_12_ratio=0.985,
            group_velocity_4_m_s=1.75e8,
            group_velocity_8_ratio=0.990,
            group_velocity_12_ratio=0.980,
            loss_db_per_m=0.35,
            q_requirement_note="Loss can be acceptable in coax or careful RF PCB, but plain lines lack strong nonlinearity.",
            nonlinear_strength_relative=0.18,
            component_stress_proxy=0.25,
            material_maturity_score=0.80,
            implementation_complexity_score=0.45,
            notes=(
                "Good as a linear phase reference. As a discovery medium it needs loading or active nonlinear "
                "elements; otherwise the required interaction length is several meters."
            ),
        ),
        PhysicalRealization(
            row_id="w002",
            name="acoustic_waveguide_or_phononic_chain",
            family="acoustic_waveguide_or_phononic_chain",
            role="physical_candidate",
            frequency_scale_note="Ultrasonic/acoustic bench scale; source band near 40 kHz.",
            source_frequency_hz=40.0e3,
            phase_velocity_4_m_s=800.0,
            phase_velocity_8_ratio=0.998,
            phase_velocity_12_ratio=0.996,
            group_velocity_4_m_s=760.0,
            group_velocity_8_ratio=0.970,
            group_velocity_12_ratio=0.940,
            loss_db_per_m=1.5,
            q_requirement_note="Length is easy; material damping and transducer bandwidth set the Q limit.",
            nonlinear_strength_relative=0.78,
            component_stress_proxy=0.35,
            material_maturity_score=0.78,
            implementation_complexity_score=0.50,
            notes=(
                "Slow phase velocity makes the interaction length compact. The harder part is clean, calibrated "
                "quadratic/cubic mixing without transducer feedthrough."
            ),
        ),
        PhysicalRealization(
            row_id="w003",
            name="nonlinear_magnetic_transmission_line",
            family="nonlinear_magnetic_transmission_line",
            role="physical_candidate",
            frequency_scale_note="Low RF slow-wave electronics; source band near 10 MHz.",
            source_frequency_hz=10.0e6,
            phase_velocity_4_m_s=2.0e6,
            phase_velocity_8_ratio=0.997,
            phase_velocity_12_ratio=0.994,
            group_velocity_4_m_s=1.8e6,
            group_velocity_8_ratio=0.960,
            group_velocity_12_ratio=0.930,
            loss_db_per_m=0.8,
            q_requirement_note="Requires saturable inductors or ferrite loading with repeatable bias and moderate loss.",
            nonlinear_strength_relative=0.90,
            component_stress_proxy=0.65,
            material_maturity_score=0.86,
            implementation_complexity_score=0.62,
            notes=(
                "Strong nonlinear inductance is realistic, but core loss, bias history, and saturation stress "
                "become the main risks."
            ),
        ),
        varactor,
        PhysicalRealization(
            row_id="w005",
            name="mechanical_or_metamaterial_lattice",
            family="mechanical_or_metamaterial_lattice",
            role="physical_candidate",
            frequency_scale_note="Tabletop mechanical/metamaterial scale; source band near 250 Hz.",
            source_frequency_hz=250.0,
            phase_velocity_4_m_s=80.0,
            phase_velocity_8_ratio=0.990,
            phase_velocity_12_ratio=0.975,
            group_velocity_4_m_s=70.0,
            group_velocity_8_ratio=0.900,
            group_velocity_12_ratio=0.820,
            loss_db_per_m=2.2,
            q_requirement_note="Easy to observe, but damping and cell-to-cell tolerance make coherent 12-band buildup hard.",
            nonlinear_strength_relative=0.55,
            component_stress_proxy=0.45,
            material_maturity_score=0.62,
            implementation_complexity_score=0.68,
            notes=(
                "Useful as a visible analog model. Precision, damping, and repeatable nonlinear coupling are harder "
                "than in electrical lines."
            ),
        ),
        PhysicalRealization(
            row_id="w006",
            name="optical_or_nonlinear_waveguide_conceptual_comparison",
            family="optical_nonlinear_waveguide",
            role="conceptual_comparison",
            frequency_scale_note="Conceptual optical comparison; source near 193.5 THz.",
            source_frequency_hz=193.5e12,
            phase_velocity_4_m_s=2.05e8,
            phase_velocity_8_ratio=0.965,
            phase_velocity_12_ratio=0.930,
            group_velocity_4_m_s=2.0e8,
            group_velocity_8_ratio=0.940,
            group_velocity_12_ratio=0.900,
            loss_db_per_m=0.2,
            q_requirement_note="Waveguide loss can be low, but nonlinear length and transparency dominate.",
            nonlinear_strength_relative=0.08,
            component_stress_proxy=0.20,
            material_maturity_score=0.60,
            implementation_complexity_score=0.95,
            conceptual_only=True,
            notes=(
                "Included only as a conceptual analogy to cascaded frequency conversion; it is not a practical "
                "first 4->8->12 bench analog."
            ),
        ),
    ]

    control_base = replace(
        varactor,
        row_id="c001",
        role="control",
        name="phase_mismatched_physical_mapping_control",
        family="phase_mismatched_control",
        phase_velocity_8_ratio=0.860,
        phase_velocity_12_ratio=1.210,
        group_velocity_8_ratio=0.820,
        group_velocity_12_ratio=1.160,
        notes="Deliberately dispersive mapping to test whether phase mismatch suppresses coherent buildup.",
    )
    rows.extend(
        [
            control_base,
            replace(
                varactor,
                row_id="c002",
                role="control",
                name="too_lossy_mapping_control",
                family="too_lossy_control",
                loss_db_per_m=45.0,
                notes="Same phase matching as the varactor row, but with intentionally excessive distributed loss.",
            ),
            replace(
                varactor,
                row_id="c003",
                role="control",
                name="too_short_interaction_length_control",
                family="too_short_control",
                interaction_length_scale=0.08,
                notes="Uses only a small fraction of the normalized interaction length.",
            ),
            replace(
                varactor,
                row_id="c004",
                role="control",
                name="weak_nonlinearity_mapping_control",
                family="weak_nonlinearity_control",
                nonlinear_strength_relative=0.05,
                notes="Keeps phase velocity but removes most of the nonlinear mixing strength.",
            ),
            replace(
                varactor,
                row_id="c005",
                role="control",
                name="linear_no_nonlinearity_mapping_control",
                family="linear_no_nonlinearity_control",
                nonlinear_strength_relative=0.0,
                notes="Linear control: no nonlinear mixing path.",
            ),
        ]
    )
    return rows


def estimate_row(row: PhysicalRealization, ref: Dict[str, float]) -> Dict[str, object]:
    f4 = row.source_frequency_hz
    f8 = 2.0 * f4
    f12 = 3.0 * f4
    v4 = row.phase_velocity_4_m_s
    v8 = v4 * row.phase_velocity_8_ratio
    v12 = v4 * row.phase_velocity_12_ratio
    vg4 = row.group_velocity_4_m_s
    vg8 = vg4 * row.group_velocity_8_ratio
    vg12 = vg4 * row.group_velocity_12_ratio

    lambda4 = v4 / f4
    lambda8 = v8 / f8
    lambda12 = v12 / f12
    k4 = 2.0 * math.pi / lambda4
    k8 = 2.0 * math.pi / lambda8
    k12 = 2.0 * math.pi / lambda12
    delta448 = k8 - 2.0 * k4
    delta4812 = k12 - k8 - k4
    limiting_delta = max(abs(delta448), abs(delta4812))

    required_length = NORMALIZED_CHAIN_LENGTH / max(k4, EPS)
    used_length = required_length * row.interaction_length_scale
    cell_pitch = used_length / NORMALIZED_CELL_COUNT

    coherence448 = math.pi / abs(delta448) if abs(delta448) > EPS else math.inf
    coherence4812 = math.pi / abs(delta4812) if abs(delta4812) > EPS else math.inf
    coherence_limited = min(coherence448, coherence4812)
    qpm448 = 2.0 * math.pi / abs(delta448) if abs(delta448) > EPS else math.inf
    qpm4812 = 2.0 * math.pi / abs(delta4812) if abs(delta4812) > EPS else math.inf

    phase448 = abs(sinc(0.5 * delta448 * used_length))
    phase4812 = abs(sinc(0.5 * delta4812 * used_length))
    phase_match_factor = clamp(phase448 * phase4812)
    qpm_gain_factor = min(1.0, 0.64 / max(phase_match_factor, 0.12)) if row.qpm_enabled else 0.0
    effective_phase_factor = max(phase_match_factor, qpm_gain_factor)

    alpha_np_per_m = row.loss_db_per_m * math.log(10.0) / 20.0
    loss_factor = math.exp(-alpha_np_per_m * used_length)
    loss_db_over_length = row.loss_db_per_m * used_length
    required_loss_db_per_m_for_3db = 3.0 / max(required_length, EPS)
    equivalent_q4 = k4 / max(2.0 * alpha_np_per_m, EPS)
    group_velocity_mismatch = max(
        abs(vg8 - vg4) / max(abs(vg4), EPS),
        abs(vg12 - vg4) / max(abs(vg4), EPS),
    )

    required_gain_per_m = math.log(max(ref["target_coherent_growth"], 1.000001)) / max(required_length, EPS)
    available_gain_per_m = required_gain_per_m * row.nonlinear_strength_relative
    coherent_exponent = available_gain_per_m * used_length * effective_phase_factor - alpha_np_per_m * used_length
    target_growth = math.exp(max(-30.0, min(30.0, coherent_exponent)))
    growth_fraction = clamp((target_growth - 1.0) / max(ref["target_coherent_growth"] - 1.0, EPS))
    bridge_ratio_estimate = ref["bridge_ratio"] * growth_fraction
    lock_estimate = ref["lock"] * effective_phase_factor * (0.55 + 0.45 * clamp(target_growth / ref["target_coherent_growth"]))
    purity_estimate = ref["purity"] * (0.55 + 0.45 * effective_phase_factor) * (0.65 + 0.35 * clamp(row.nonlinear_strength_relative))
    generated_cv_estimate = ref["generated_envelope_cv"] * (1.0 + 0.7 * group_velocity_mismatch + 0.6 * (1.0 - effective_phase_factor))
    max_phase_jump_estimate = ref["max_phase_jump"] * (1.0 + 10.0 * (1.0 - effective_phase_factor) + 2.0 * group_velocity_mismatch)

    length_score = clamp(1.0 - max(0.0, math.log10(max(used_length, EPS) / 1.5)) * 0.35)
    if used_length < 0.01 and not row.conceptual_only:
        length_score *= 0.80
    loss_score = clamp(loss_factor)
    nonlinear_score = clamp(row.nonlinear_strength_relative / 0.90)
    stress_score = clamp(1.0 - 0.55 * row.component_stress_proxy)
    complexity_score = clamp(1.0 - 0.50 * row.implementation_complexity_score)
    feasibility_score = clamp(
        0.24 * effective_phase_factor
        + 0.18 * loss_score
        + 0.20 * nonlinear_score
        + 0.12 * length_score
        + 0.12 * stress_score
        + 0.08 * row.material_maturity_score
        + 0.06 * complexity_score
    )
    if row.conceptual_only:
        feasibility_class = "conceptual only"
    elif row.role == "control":
        feasibility_class = "control/not_candidate"
    elif feasibility_score >= 0.80:
        feasibility_class = "plausible bench-scale"
    elif feasibility_score >= 0.55:
        feasibility_class = "aggressive but testable"
    else:
        feasibility_class = "unrealistic"

    blockers = {
        "phase_velocity": 1.0 - effective_phase_factor,
        "loss": 1.0 - loss_factor,
        "nonlinearity": 1.0 - nonlinear_score,
        "length": 1.0 - length_score,
        "component_stress": row.component_stress_proxy,
    }
    main_blocker = max(blockers, key=blockers.get)
    leakage_score = growth_fraction
    control_dead = row.role == "control" and leakage_score < 0.15 and bridge_ratio_estimate < 1.0
    discovery_promising = (
        row.role == "physical_candidate"
        and feasibility_class in {"plausible bench-scale", "aggressive but testable"}
        and bridge_ratio_estimate > 1.0
        and lock_estimate > 0.70
    )

    return {
        **asdict(row),
        "source_frequency_hz": f4,
        "generated_frequency_hz": f8,
        "target_frequency_hz": f12,
        "wavelength_4_m": lambda4,
        "wavelength_8_m": lambda8,
        "wavelength_12_m": lambda12,
        "phase_velocity_8_m_s": v8,
        "phase_velocity_12_m_s": v12,
        "group_velocity_8_m_s": vg8,
        "group_velocity_12_m_s": vg12,
        "k4_rad_per_m": k4,
        "k8_rad_per_m": k8,
        "k12_rad_per_m": k12,
        "delta_k_448_rad_per_m": delta448,
        "delta_k_4812_rad_per_m": delta4812,
        "limiting_delta_k_rad_per_m": limiting_delta,
        "coherence_length_448_m": finite_or_none(coherence448),
        "coherence_length_4812_m": finite_or_none(coherence4812),
        "limiting_coherence_length_m": finite_or_none(coherence_limited),
        "qpm_period_448_m": finite_or_none(qpm448),
        "qpm_period_4812_m": finite_or_none(qpm4812),
        "normalized_chain_length": NORMALIZED_CHAIN_LENGTH,
        "normalized_cell_count": NORMALIZED_CELL_COUNT,
        "meters_per_normalized_unit": 1.0 / max(k4, EPS),
        "required_interaction_length_m": required_length,
        "used_interaction_length_m": used_length,
        "cell_pitch_m": cell_pitch,
        "loss_np_per_m": alpha_np_per_m,
        "loss_db_over_used_length": loss_db_over_length,
        "loss_factor_over_used_length": loss_factor,
        "required_loss_db_per_m_for_3db": required_loss_db_per_m_for_3db,
        "equivalent_traveling_wave_q4": equivalent_q4,
        "group_velocity_mismatch_fraction": group_velocity_mismatch,
        "phase_match_factor": phase_match_factor,
        "qpm_gain_factor": qpm_gain_factor,
        "effective_phase_factor": effective_phase_factor,
        "required_nonlinear_gain_per_m": required_gain_per_m,
        "available_nonlinear_gain_per_m": available_gain_per_m,
        "target_coherent_growth_estimate": target_growth,
        "bridge_ratio_estimate": bridge_ratio_estimate,
        "phase_lock_estimate": lock_estimate,
        "purity_estimate": purity_estimate,
        "generated_envelope_cv_estimate": generated_cv_estimate,
        "max_phase_jump_estimate": max_phase_jump_estimate,
        "control_leakage_score": leakage_score if row.role == "control" else 0.0,
        "control_dead": str(control_dead) if row.role == "control" else "",
        "feasibility_score": feasibility_score,
        "feasibility_class": feasibility_class,
        "main_physical_blocker": main_blocker,
        "discovery_promising": str(discovery_promising),
        "source_only_drive": str(not row.direct_8_drive_present and not row.direct_12_drive_present),
        "target_frequency_injection_absent": str(not row.target_frequency_injection_present),
        "tl_reference_lock": ref["lock"],
        "tl_reference_bridge_ratio": ref["bridge_ratio"],
        "tl_reference_behavioral_dependency": ref["behavioral_dependency_score"],
    }


def aggregate(rows: List[Dict[str, object]], ref: Dict[str, float]) -> Dict[str, object]:
    physical = [row for row in rows if row["role"] == "physical_candidate"]
    controls = [row for row in rows if row["role"] == "control"]
    plausible = [row for row in physical if row["feasibility_class"] == "plausible bench-scale"]
    best = max(physical, key=lambda row: float(row["feasibility_score"]))
    best_growth = max(physical, key=lambda row: float(row["target_coherent_growth_estimate"]))
    pcb = next(row for row in rows if row["family"] == "pcb_microstrip_or_coaxial_transmission_line_ladder")
    acoustic = next(row for row in rows if row["family"] == "acoustic_waveguide_or_phononic_chain")
    magnetic = next(row for row in rows if row["family"] == "nonlinear_magnetic_transmission_line")
    varactor = next(row for row in rows if row["family"] == "nonlinear_varactor_loaded_transmission_line")
    control_leakage = max((float(row["control_leakage_score"]) for row in controls), default=0.0)
    controls_dead = all(row.get("control_dead") == "True" for row in controls)

    blocker_counts: Dict[str, int] = {}
    for row in physical:
        blocker = str(row["main_physical_blocker"])
        blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    primary_blocker = max(blocker_counts, key=blocker_counts.get)

    return {
        "row_type": "aggregate",
        "tl_reference_lock": ref["lock"],
        "tl_reference_bridge_ratio": ref["bridge_ratio"],
        "tl_reference_behavioral_dependency": ref["behavioral_dependency_score"],
        "rows_total": len(rows),
        "physical_candidate_rows": len(physical),
        "control_rows": len(controls),
        "plausible_bench_scale_count": len(plausible),
        "best_first_bench_realization": best["name"],
        "best_first_bench_family": best["family"],
        "best_first_bench_feasibility_class": best["feasibility_class"],
        "best_first_bench_frequency_hz": best["source_frequency_hz"],
        "best_first_bench_required_length_m": best["required_interaction_length_m"],
        "best_first_bench_bridge_ratio_estimate": best["bridge_ratio_estimate"],
        "best_growth_realization": best_growth["name"],
        "best_growth_estimate": best_growth["target_coherent_growth_estimate"],
        "pcb_feasibility_class": pcb["feasibility_class"],
        "pcb_required_length_m": pcb["required_interaction_length_m"],
        "pcb_main_blocker": pcb["main_physical_blocker"],
        "pcb_too_lossy_or_weak": "mostly_length_and_nonlinearity_not_loss_alone",
        "acoustic_feasibility_class": acoustic["feasibility_class"],
        "acoustic_required_length_m": acoustic["required_interaction_length_m"],
        "acoustic_easier_for_length": "True",
        "magnetic_feasibility_class": magnetic["feasibility_class"],
        "varactor_feasibility_class": varactor["feasibility_class"],
        "most_realistic_electrical_family": varactor["family"]
        if float(varactor["feasibility_score"]) >= float(magnetic["feasibility_score"])
        else magnetic["family"],
        "main_physical_blocker": primary_blocker,
        "control_rows_dead": str(controls_dead),
        "max_control_leakage_score": control_leakage,
        "recommended_next_step": "PCB/transmission-line SPICE design for a varactor-loaded NLTL, with acoustic simulation as a parallel low-frequency analog",
    }


def write_readme(path: Path, rows: List[Dict[str, object]], agg: Dict[str, object]) -> None:
    best = next(row for row in rows if row["name"] == agg["best_first_bench_realization"])
    pcb = next(row for row in rows if row["family"] == "pcb_microstrip_or_coaxial_transmission_line_ladder")
    acoustic = next(row for row in rows if row["family"] == "acoustic_waveguide_or_phononic_chain")
    magnetic = next(row for row in rows if row["family"] == "nonlinear_magnetic_transmission_line")
    varactor = next(row for row in rows if row["family"] == "nonlinear_varactor_loaded_transmission_line")

    lines = [
        "# Physical Waveguide 4->8->12 Interpretation",
        "",
        "Screening layer for mapping the promoted normalized transmission-line result into physical media.",
        "",
        "## Direct Answers",
        "",
        (
            "1. Most plausible first bench analog: "
            f"{agg['best_first_bench_realization']} "
            f"({agg['best_first_bench_feasibility_class']})."
        ),
        (
            "2. Most practical frequency scale: low-RF electronics around "
            f"{float(best['source_frequency_hz']) / 1.0e6:.3g} MHz for the first electrical analog; "
            "acoustic checks are practical around 20-100 kHz."
        ),
        (
            "3. Required interaction length for the top row: "
            f"{float(best['required_interaction_length_m']):.6g} m "
            f"with cell pitch {float(best['cell_pitch_m']):.6g} m."
        ),
        (
            "4. PCB/microstrip: "
            f"{pcb['feasibility_class']}; required length {float(pcb['required_interaction_length_m']):.6g} m. "
            "The first blocker is length/nonlinearity more than raw loss."
        ),
        (
            "5. Acoustic/phononic: "
            f"{acoustic['feasibility_class']}; length {float(acoustic['required_interaction_length_m']):.6g} m. "
            "It is easier for size and phase-velocity scaling, harder for calibrated nonlinear drive/readout."
        ),
        (
            "6. Electrical realism: "
            f"varactor={varactor['feasibility_class']}, magnetic={magnetic['feasibility_class']}; "
            f"most realistic electrical family is {agg['most_realistic_electrical_family']}."
        ),
        (
            "7. Main blocker: "
            f"{agg['main_physical_blocker']}; in prose, the practical issue is nonlinear strength under "
            "controlled phase velocity and tolerable stress."
        ),
        (
            "8. Recommended next step: "
            f"{agg['recommended_next_step']}."
        ),
        "",
        "## Candidate Rows",
        "",
    ]
    for row in rows:
        lines.append(
            "- {row_id} {name}: role={role}, class={cls}, f4={f4:.6g} Hz, "
            "length={length:.6g} m, bridge_est={bridge:.6g}, growth_est={growth:.6g}, "
            "blocker={blocker}.".format(
                row_id=row["row_id"],
                name=row["name"],
                role=row["role"],
                cls=row["feasibility_class"],
                f4=float(row["source_frequency_hz"]),
                length=float(row["required_interaction_length_m"]),
                bridge=float(row["bridge_ratio_estimate"]),
                growth=float(row["target_coherent_growth_estimate"]),
                blocker=row["main_physical_blocker"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Discovery mappings preserve source-only drive: no direct 8 drive, no direct 12 drive, and no target-frequency injection.",
            "- Optical/nonlinear waveguide is included only as a conceptual comparison.",
            "- These are physical screening estimates, not a completed hardware design.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(out_dir: Path) -> Dict[str, object]:
    ensure_dir(out_dir)
    ref = load_tl_reference()
    rows = [estimate_row(row, ref) for row in build_realizations()]
    agg = aggregate(rows, ref)
    json_rows: List[Dict[str, object]] = [agg] + rows

    summary = {
        "aggregate": agg,
        "rows": json_rows,
    }
    (out_dir / "physical_waveguide_412_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    write_csv(out_dir / "physical_waveguide_412_summary.csv", json_rows)
    write_readme(out_dir / "README_PHYSICAL_WAVEGUIDE_412.md", rows, agg)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory.")
    args = parser.parse_args()
    summary = run(Path(args.out_dir))
    agg = summary["aggregate"]
    print(
        "physical_waveguide_412: best={best} class={cls} length_m={length:.6g} next={next_step}".format(
            best=agg["best_first_bench_realization"],
            cls=agg["best_first_bench_feasibility_class"],
            length=float(agg["best_first_bench_required_length_m"]),
            next_step=agg["recommended_next_step"],
        )
    )


if __name__ == "__main__":
    main()
