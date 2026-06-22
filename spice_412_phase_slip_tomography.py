#!/usr/bin/env python3
"""Phase-slip tomography for the 4->8->12 differential witness line.

This pass does not run a new broad sweep.  It reads the latest local
`spice_412_differential_witness_line` artifacts, reconstructs tap-by-tap
phasors at 50/100/150 MHz, and diagnoses where coherent 50->100->150 transfer
breaks before extraction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import spice_412_differential_witness_line as witness
import spice_412_varactor_nltl_design as design


SOURCE_DIR = Path("runs") / "spice_412_differential_witness_line"
OUT_DIR = Path("runs") / "spice_412_phase_slip_tomography"
SOURCE_HZ = witness.SOURCE_HZ
GENERATED_HZ = witness.GENERATED_HZ
TARGET_HZ = witness.TARGET_HZ
EPS = 1.0e-30

REQUIRED_ARTIFACTS = (
    "spice_412_differential_witness_line_summary.json",
    "spice_412_differential_witness_line_summary.csv",
    "spice_412_differential_witness_line_tap_timeseries.csv",
)

RERUN_COMMAND = "python spice_412_differential_witness_line.py --run --ngspice-path wsl:ngspice --timeout 180"


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


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def wrap_pi(value: float) -> float:
    return float((value + math.pi) % (2.0 * math.pi) - math.pi)


def phase_lock(errors: np.ndarray, weights: np.ndarray | None = None) -> float:
    if len(errors) == 0:
        return 0.0
    phasors = np.exp(1j * errors)
    if weights is None or np.sum(weights) <= EPS:
        return float(abs(np.mean(phasors)))
    return float(abs(np.sum(np.asarray(weights, dtype=float) * phasors) / np.sum(weights)))


def envelope_cv(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    return float(np.std(values) / max(np.mean(values), EPS)) if len(values) else 0.0


def artifact_error_message(missing: Iterable[Path]) -> str:
    missing_text = "\n".join(f"- {path}" for path in missing)
    return (
        "Missing differential witness-line artifacts.\n"
        f"{missing_text}\n\n"
        "Run this first:\n"
        f"{RERUN_COMMAND}"
    )


def check_required_artifacts(source_dir: Path) -> None:
    missing = [source_dir / name for name in REQUIRED_ARTIFACTS if not (source_dir / name).exists()]
    if missing:
        print(artifact_error_message(missing), file=sys.stderr)
        raise SystemExit(2)


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def count_csv_data_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        count = sum(1 for _ in f)
    return max(0, count - 1)


def case_map_from_witness() -> Dict[str, witness.WitnessCase]:
    _trials, cases = witness.build_all_cases()
    return {case.case_id: case for case in cases}


def qpm_sign_for_tap(case: witness.WitnessCase | None, tap_fraction: float) -> float:
    if case is None:
        return 1.0
    idx = min(case.cell_count, max(0, int(round(tap_fraction * case.cell_count))))
    if idx == 0:
        return 1.0
    return witness.bmag_sign(case, idx)


def phasors_for_case(
    case_row: Dict[str, object],
    case_obj: witness.WitnessCase | None,
    source_dir: Path,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]]:
    csv_file = str(case_row.get("csv_file") or "")
    if not csv_file:
        raise ValueError(f"case {case_row.get('case_id')} has no csv_file")
    data = witness.read_transient(source_dir / csv_file)
    d = witness.uniform_resample(data)
    t = d["time"]
    start = int(0.25 * len(t))
    t2 = t[start:]

    tap_rows: List[Dict[str, object]] = []
    amps50: List[float] = []
    amps100: List[float] = []
    amps150: List[float] = []
    phi50: List[float] = []
    phi100: List[float] = []
    phi150: List[float] = []
    qpm_signs: List[float] = []

    for tap_label, tap_fraction in witness.TAP_FRACTIONS:
        signal = d[tap_label][start:]
        z50 = witness.complex_projection(signal, t2, SOURCE_HZ)
        z100 = witness.complex_projection(signal, t2, GENERATED_HZ)
        z150 = witness.complex_projection(signal, t2, TARGET_HZ)
        amps50.append(float(abs(z50)))
        amps100.append(float(abs(z100)))
        amps150.append(float(abs(z150)))
        phi50.append(float(np.angle(z50)))
        phi100.append(float(np.angle(z100)))
        phi150.append(float(np.angle(z150)))
        qpm_signs.append(qpm_sign_for_tap(case_obj, tap_fraction))

    ph50 = np.unwrap(np.asarray(phi50, dtype=float))
    ph100 = np.unwrap(np.asarray(phi100, dtype=float))
    ph150 = np.unwrap(np.asarray(phi150, dtype=float))
    amp50 = np.asarray(amps50, dtype=float)
    amp100 = np.asarray(amps100, dtype=float)
    amp150 = np.asarray(amps150, dtype=float)
    qpm = np.asarray(qpm_signs, dtype=float)
    generated_error = ph100 - 2.0 * ph50
    target_error = ph150 - ph100 - ph50
    target_3f_error = ph150 - 3.0 * ph50
    qpm_alignment_raw = qpm * np.cos(target_error)
    qpm_alignment_01 = 0.5 * (qpm_alignment_raw + 1.0)
    positions = np.asarray([frac for _, frac in witness.TAP_FRACTIONS], dtype=float)
    non_input = slice(1, None)
    gen_lock = phase_lock(generated_error[non_input], amp100[non_input] + EPS)
    target_lock = phase_lock(target_error[non_input], amp150[non_input] + EPS)
    lock_3f = phase_lock(target_3f_error[non_input], amp150[non_input] + EPS)
    phase_jump_target = np.abs(np.diff(np.unwrap(target_error)))
    phase_jump_generated = np.abs(np.diff(np.unwrap(generated_error)))
    ripple50 = (float(np.max(amp50)) - float(np.min(amp50))) / max(float(np.mean(amp50)), EPS)
    ripple100 = (float(np.max(amp100)) - float(np.min(amp100))) / max(float(np.mean(amp100)), EPS)
    ripple150 = (float(np.max(amp150)) - float(np.min(amp150))) / max(float(np.mean(amp150)), EPS)
    local_log150 = np.diff(np.log(amp150 + EPS))
    local_log100 = np.diff(np.log(amp100 + EPS))
    sign_changes_150 = int(np.sum(np.sign(local_log150[1:]) != np.sign(local_log150[:-1]))) if len(local_log150) > 1 else 0
    sign_changes_100 = int(np.sum(np.sign(local_log100[1:]) != np.sign(local_log100[:-1]))) if len(local_log100) > 1 else 0
    reflection_indicator = clamp(0.20 * ripple50 + 0.20 * ripple100 + 0.25 * ripple150 + 0.06 * (sign_changes_100 + sign_changes_150))
    generated_stability = clamp(gen_lock / (1.0 + envelope_cv(amp100[non_input])) / (1.0 + float(np.max(phase_jump_generated)) / math.pi if len(phase_jump_generated) else 1.0))
    target_stability = clamp(target_lock / (1.0 + envelope_cv(amp150[non_input])) / (1.0 + float(np.max(phase_jump_target)) / math.pi if len(phase_jump_target) else 1.0))

    for idx, (tap_label, tap_fraction) in enumerate(witness.TAP_FRACTIONS):
        z50 = amp50[idx] * np.exp(1j * ph50[idx])
        z100 = amp100[idx] * np.exp(1j * ph100[idx])
        z150 = amp150[idx] * np.exp(1j * ph150[idx])
        tap_rows.append(
            {
                "row_type": "tap_phase_error",
                "case_id": case_row.get("case_id", ""),
                "trial_id": case_row.get("trial_id", ""),
                "paired_trial_name": case_row.get("paired_trial_name", ""),
                "side": case_row.get("side", ""),
                "object_family": case_row.get("object_family", ""),
                "reference_transform": case_row.get("reference_transform", ""),
                "tap_label": tap_label,
                "tap_fraction": tap_fraction,
                "phasor_50_real": float(np.real(z50)),
                "phasor_50_imag": float(np.imag(z50)),
                "phasor_100_real": float(np.real(z100)),
                "phasor_100_imag": float(np.imag(z100)),
                "phasor_150_real": float(np.real(z150)),
                "phasor_150_imag": float(np.imag(z150)),
                "amp_50mhz": float(amp50[idx]),
                "amp_100mhz": float(amp100[idx]),
                "amp_150mhz": float(amp150[idx]),
                "phase_50mhz_rad": float(phi50[idx]),
                "phase_100mhz_rad": float(phi100[idx]),
                "phase_150mhz_rad": float(phi150[idx]),
                "unwrapped_phase_50mhz_rad": float(ph50[idx]),
                "unwrapped_phase_100mhz_rad": float(ph100[idx]),
                "unwrapped_phase_150mhz_rad": float(ph150[idx]),
                "local_100mhz_lock_error_rad": wrap_pi(float(generated_error[idx])),
                "local_150mhz_lock_error_rad": wrap_pi(float(target_error[idx])),
                "local_qpm_sign": float(qpm[idx]),
                "local_qpm_sign_alignment_score": float(qpm_alignment_raw[idx]),
                "local_qpm_sign_alignment_0to1": float(qpm_alignment_01[idx]),
                "reflection_standing_wave_indicator": reflection_indicator,
                "generated_path_stability_score": generated_stability,
                "target_path_stability_score": target_stability,
            }
        )

    local_rows: List[Dict[str, object]] = []
    for idx in range(1, len(witness.TAP_FRACTIONS)):
        prev_label, prev_frac = witness.TAP_FRACTIONS[idx - 1]
        tap_label, tap_frac = witness.TAP_FRACTIONS[idx]
        local_100_growth = float(amp100[idx] / max(amp100[idx - 1], EPS))
        local_150_growth = float(amp150[idx] / max(amp150[idx - 1], EPS))
        local_alignment = float(0.5 * (qpm_alignment_raw[idx] + qpm_alignment_raw[idx - 1]))
        local_coherent = float(math.log(max(local_150_growth, EPS)) * local_alignment)
        local_rows.append(
            {
                "row_type": "local_growth_by_tap",
                "case_id": case_row.get("case_id", ""),
                "trial_id": case_row.get("trial_id", ""),
                "paired_trial_name": case_row.get("paired_trial_name", ""),
                "side": case_row.get("side", ""),
                "object_family": case_row.get("object_family", ""),
                "reference_transform": case_row.get("reference_transform", ""),
                "from_tap_label": prev_label,
                "to_tap_label": tap_label,
                "from_tap_fraction": prev_frac,
                "to_tap_fraction": tap_frac,
                "local_phase_jump_50mhz_rad": wrap_pi(float(ph50[idx] - ph50[idx - 1])),
                "local_phase_jump_100mhz_rad": wrap_pi(float(ph100[idx] - ph100[idx - 1])),
                "local_phase_jump_150mhz_rad": wrap_pi(float(ph150[idx] - ph150[idx - 1])),
                "local_100mhz_lock_error_jump_rad": wrap_pi(float(generated_error[idx] - generated_error[idx - 1])),
                "local_150mhz_lock_error_jump_rad": wrap_pi(float(target_error[idx] - target_error[idx - 1])),
                "local_50mhz_amplitude_growth": float(amp50[idx] / max(amp50[idx - 1], EPS)),
                "local_100mhz_amplitude_growth": local_100_growth,
                "local_150mhz_amplitude_growth": local_150_growth,
                "local_coherent_growth_contribution": local_coherent,
                "local_qpm_sign_alignment_score": local_alignment,
                "reflection_standing_wave_indicator": reflection_indicator,
            }
        )

    total_length_m = safe_float(case_row.get("total_length_m"), 1.0)
    pos_m = positions * total_length_m
    gen_slope = float(np.polyfit(pos_m, generated_error, 1)[0]) if len(pos_m) > 1 and total_length_m > 0 else 0.0
    target_slope = float(np.polyfit(pos_m, target_error, 1)[0]) if len(pos_m) > 1 and total_length_m > 0 else 0.0
    first_bad_100 = first_bad_tap(generated_error, limit=0.80)
    first_bad_150 = first_bad_tap(target_error, limit=0.80)
    summary = {
        "case_id": case_row.get("case_id", ""),
        "trial_id": case_row.get("trial_id", ""),
        "paired_trial_name": case_row.get("paired_trial_name", ""),
        "side": case_row.get("side", ""),
        "object_family": case_row.get("object_family", ""),
        "reference_transform": case_row.get("reference_transform", ""),
        "phase_lock_generated_tomography": gen_lock,
        "phase_lock_target_tomography": target_lock,
        "phase_lock_150_to_3f_tomography": lock_3f,
        "generated_path_stability_score": generated_stability,
        "target_path_stability_score": target_stability,
        "qpm_sign_alignment_mean": float(np.mean(qpm_alignment_raw[non_input])),
        "qpm_sign_alignment_abs_mean": float(np.mean(np.abs(qpm_alignment_raw[non_input]))),
        "qpm_sign_alignment_0to1_mean": float(np.mean(qpm_alignment_01[non_input])),
        "reflection_standing_wave_indicator": reflection_indicator,
        "amp_100mhz_cv_by_tap": envelope_cv(amp100[non_input]),
        "amp_150mhz_cv_by_tap": envelope_cv(amp150[non_input]),
        "amp_100mhz_growth_tap_end_over_first": float(amp100[-1] / max(amp100[1], EPS)),
        "amp_150mhz_growth_tap_end_over_first": float(amp150[-1] / max(amp150[1], EPS)),
        "max_generated_lock_error_jump_rad": float(np.max(phase_jump_generated)) if len(phase_jump_generated) else 0.0,
        "max_target_lock_error_jump_rad": float(np.max(phase_jump_target)) if len(phase_jump_target) else 0.0,
        "generated_lock_error_slope_rad_per_m": gen_slope,
        "target_lock_error_slope_rad_per_m": target_slope,
        "first_100mhz_coherence_fail_tap": first_bad_100,
        "first_150mhz_coherence_fail_tap": first_bad_150,
    }
    return tap_rows, local_rows, summary


def first_bad_tap(errors: np.ndarray, limit: float) -> str:
    for idx, value in enumerate(errors):
        if idx == 0:
            continue
        if abs(wrap_pi(float(value))) > limit:
            return witness.TAP_FRACTIONS[idx][0]
    return "not_within_measured_taps"


def failure_modes(pair: Dict[str, object], obj_tomo: Dict[str, object] | None, ref_tomo: Dict[str, object] | None) -> Tuple[str, List[str]]:
    if pair.get("object_execution_status") != "ran_successfully" or pair.get("reference_execution_status") != "ran_successfully":
        return "convergence_limited", ["convergence_limited"]
    obj_tomo = obj_tomo or {}
    ref_tomo = ref_tomo or {}
    modes: List[str] = []
    gain = safe_float(pair.get("pre_extraction_object_reference_gain_150mhz"))
    target_lock = safe_float(pair.get("phase_lock_target_pre"))
    gen_lock = safe_float(pair.get("phase_lock_generated_pre"))
    coherent = safe_float(pair.get("distributed_150mhz_coherent_growth"))
    leakage = safe_float(pair.get("differential_control_leakage_score"))
    extraction_dependency = safe_float(pair.get("extraction_dependency_score"))
    max_jump = safe_float(pair.get("max_phase_jump_pre"))
    qpm_alignment = safe_float(obj_tomo.get("qpm_sign_alignment_0to1_mean"), 0.5)
    reflection = max(
        safe_float(obj_tomo.get("reflection_standing_wave_indicator")),
        safe_float(ref_tomo.get("reflection_standing_wave_indicator")),
    )
    generated_stability = safe_float(obj_tomo.get("generated_path_stability_score"))
    target_stability = safe_float(obj_tomo.get("target_path_stability_score"))
    magnetic_strength = safe_float(pair.get("magnetic_strength"), 0.0)

    if gen_lock < 0.75 or generated_stability < 0.35:
        modes.append("generated_100_unstable")
    if target_lock < 0.85 or max_jump > 0.50 or target_stability < 0.35:
        modes.append("target_150_phase_walkoff")
    if qpm_alignment < 0.45:
        modes.append("qpm_sign_misaligned")
    if magnetic_strength > 0.0 and target_lock < 0.85 and safe_float(obj_tomo.get("target_lock_error_slope_rad_per_m")) > 1.0:
        modes.append("magnetic_lag_or_hysteresis_phase_error")
    if reflection > 0.70:
        modes.append("reflection_or_load_standing_wave")
    if leakage >= 0.15:
        modes.append("reference_shadow_leakage")
    if extraction_dependency > 0.35:
        modes.append("extraction_artifact_only")
    if gain >= 3.0 and (target_lock < 0.85 or coherent < 1.5):
        modes.append("raw_gain_without_coherence")
    if not modes:
        modes.append("genuinely_blocked_current_topology")

    priority = [
        "convergence_limited",
        "reference_shadow_leakage",
        "raw_gain_without_coherence",
        "target_150_phase_walkoff",
        "generated_100_unstable",
        "qpm_sign_misaligned",
        "magnetic_lag_or_hysteresis_phase_error",
        "reflection_or_load_standing_wave",
        "extraction_artifact_only",
        "genuinely_blocked_current_topology",
    ]
    primary = next(mode for mode in priority if mode in modes)
    return primary, modes


def promotion_label(pair: Dict[str, object]) -> str:
    source_clean = (
        str(pair.get("source_only_drive")) == "True"
        and str(pair.get("direct_100mhz_drive_present")) == "False"
        and str(pair.get("direct_150mhz_drive_present")) == "False"
        and str(pair.get("target_frequency_injection_present")) == "False"
    )
    stress_ok = str(pair.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}
    leakage = safe_float(pair.get("differential_control_leakage_score"))
    candidate = (
        source_clean
        and safe_float(pair.get("pre_extraction_object_reference_gain_150mhz")) >= 10.0
        and safe_float(pair.get("phase_lock_generated_pre")) >= 0.80
        and safe_float(pair.get("phase_lock_target_pre")) >= 0.90
        and safe_float(pair.get("distributed_150mhz_coherent_growth")) >= 2.0
        and safe_float(pair.get("distributed_150mhz_growth_slope")) > 0.0
        and safe_float(pair.get("max_phase_jump_pre")) <= 0.50
        and safe_float(pair.get("target_envelope_cv_pre"), 99.0) <= 0.25
        and safe_float(pair.get("generated_path_dependency_score")) >= 0.80
        and safe_float(pair.get("phase_mismatch_kill_score")) >= 0.80
        and leakage < 0.15
        and safe_float(pair.get("extraction_dependency_score"), 99.0) <= 0.25
        and stress_ok
    )
    near = (
        source_clean
        and safe_float(pair.get("pre_extraction_object_reference_gain_150mhz")) >= 3.0
        and safe_float(pair.get("phase_lock_target_pre")) >= 0.85
        and safe_float(pair.get("phase_lock_generated_pre")) >= 0.75
        and safe_float(pair.get("distributed_150mhz_coherent_growth")) >= 1.5
        and leakage < 0.15
        and safe_float(pair.get("extraction_dependency_score"), 99.0) <= 0.35
    )
    if candidate:
        return "electrical_phase_rescue_candidate"
    if near:
        return "electrical_phase_rescue_near_miss"
    return "not_promoted"


def build_pair_summaries(
    pairs: List[Dict[str, object]],
    case_tomography: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for pair in pairs:
        obj = case_tomography.get(str(pair.get("object_case_id")), {})
        ref = case_tomography.get(str(pair.get("reference_case_id")), {})
        primary, modes = failure_modes(pair, obj, ref)
        row = {
            "row_type": "tomography_pair_summary",
            "trial_id": pair.get("trial_id", ""),
            "paired_trial_name": pair.get("paired_trial_name", ""),
            "object_case_id": pair.get("object_case_id", ""),
            "reference_case_id": pair.get("reference_case_id", ""),
            "object_family": pair.get("object_family", ""),
            "reference_transform": pair.get("reference_transform", ""),
            "object_execution_status": pair.get("object_execution_status", ""),
            "reference_execution_status": pair.get("reference_execution_status", ""),
            "pre_extraction_object_reference_gain_150mhz": pair.get("pre_extraction_object_reference_gain_150mhz", ""),
            "phase_lock_generated_pre": pair.get("phase_lock_generated_pre", ""),
            "phase_lock_target_pre": pair.get("phase_lock_target_pre", ""),
            "distributed_150mhz_coherent_growth": pair.get("distributed_150mhz_coherent_growth", ""),
            "distributed_150mhz_growth_slope": pair.get("distributed_150mhz_growth_slope", ""),
            "target_envelope_cv_pre": pair.get("target_envelope_cv_pre", ""),
            "max_phase_jump_pre": pair.get("max_phase_jump_pre", ""),
            "differential_control_leakage_score": pair.get("differential_control_leakage_score", ""),
            "extraction_dependency_score": pair.get("extraction_dependency_score", ""),
            "object_generated_path_stability_score": obj.get("generated_path_stability_score", ""),
            "object_target_path_stability_score": obj.get("target_path_stability_score", ""),
            "object_qpm_sign_alignment_0to1_mean": obj.get("qpm_sign_alignment_0to1_mean", ""),
            "object_reflection_standing_wave_indicator": obj.get("reflection_standing_wave_indicator", ""),
            "object_first_100mhz_coherence_fail_tap": obj.get("first_100mhz_coherence_fail_tap", ""),
            "object_first_150mhz_coherence_fail_tap": obj.get("first_150mhz_coherence_fail_tap", ""),
            "reference_reflection_standing_wave_indicator": ref.get("reflection_standing_wave_indicator", ""),
            "primary_failure_mode": primary,
            "failure_modes_json": json.dumps(modes),
            "promotion_label": promotion_label(pair),
        }
        rows.append(row)
    return rows


def coherence_length_from_slope(slope: float, total_length_m: float) -> float:
    if abs(slope) < 1.0e-9:
        return total_length_m
    return min(max(math.pi / abs(slope), total_length_m / 32.0), total_length_m * 2.0)


def recommended_flip_positions(tap_rows: List[Dict[str, object]], total_length_m: float) -> List[Dict[str, float]]:
    rows = [row for row in tap_rows if str(row.get("side")) == "object"]
    if not rows:
        return []
    rows = sorted(rows, key=lambda row: safe_float(row.get("tap_fraction")))
    signs = [1 if safe_float(row.get("local_qpm_sign_alignment_score")) >= 0.0 else -1 for row in rows]
    flips: List[Dict[str, float]] = []
    for idx in range(1, len(rows)):
        if signs[idx] == signs[idx - 1]:
            continue
        frac = 0.5 * (safe_float(rows[idx - 1].get("tap_fraction")) + safe_float(rows[idx].get("tap_fraction")))
        flips.append({"fraction": frac, "position_m": frac * total_length_m})
    return flips


def velocity_trim_direction(target_slope: float, generated_slope: float) -> str:
    if abs(target_slope) < 1.0 and abs(generated_slope) < 1.0:
        return "no large velocity trim indicated by measured phase slope"
    if target_slope > 0.0:
        return "increase target-phase velocity or slightly slow the generated path"
    return "decrease target-phase velocity or slightly speed the generated path"


def load_taper_direction(reflection: float, amp_growth: float) -> str:
    if reflection > 0.70:
        return "improve output match and add a gentle impedance/load taper to suppress standing waves"
    if amp_growth < 1.0:
        return "reduce distributed loss or shorten the line to stay within measured coherence length"
    return "keep broadband load; avoid high-Q extraction and only use mild tapering"


def layout_recommendation(row: Dict[str, object], tomo: Dict[str, object]) -> str:
    gen_stability = safe_float(tomo.get("generated_path_stability_score"))
    target_stability = safe_float(tomo.get("target_path_stability_score"))
    qpm = safe_float(tomo.get("qpm_sign_alignment_0to1_mean"), 0.5)
    family = str(row.get("object_family", ""))
    if gen_stability < 0.35:
        return "varactor-first layout is most consistent; stabilize generated 100 MHz before magnetic target mixing"
    if target_stability < 0.40 and qpm < 0.50:
        return "chirped or measured-QPM retimed braided layout is most consistent"
    if "magnetic" in family and target_stability < 0.55:
        return "braided layout with magnetic-lag compensation is most consistent"
    return "braided broadband layout is most consistent; do not add high-Q extraction"


def build_rescue_plan(
    pair_rows: List[Dict[str, object]],
    tap_rows: List[Dict[str, object]],
    case_tomography: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    successful = [
        row
        for row in pair_rows
        if row.get("object_execution_status") == "ran_successfully" and row.get("reference_execution_status") == "ran_successfully"
    ]
    top = sorted(successful, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), reverse=True)[:3]
    plans: List[Dict[str, object]] = []
    for row in top:
        obj_id = str(row.get("object_case_id"))
        tomo = case_tomography.get(obj_id, {})
        total_length = safe_float(tomo.get("total_length_m"), 0.50)
        gen_lc = coherence_length_from_slope(safe_float(tomo.get("generated_lock_error_slope_rad_per_m")), total_length)
        target_lc = coherence_length_from_slope(safe_float(tomo.get("target_lock_error_slope_rad_per_m")), total_length)
        segment = max(total_length / 32.0, min(gen_lc, target_lc) / 2.0)
        obj_taps = [tap for tap in tap_rows if tap.get("case_id") == obj_id]
        flips = recommended_flip_positions(obj_taps, total_length)
        reflection = safe_float(tomo.get("reflection_standing_wave_indicator"))
        amp_growth = safe_float(tomo.get("amp_150mhz_growth_tap_end_over_first"))
        worth_trying = (
            safe_float(row.get("phase_lock_target_pre")) >= 0.70
            and safe_float(row.get("distributed_150mhz_coherent_growth")) >= 0.70
            and safe_float(row.get("differential_control_leakage_score")) < 0.15
        )
        plans.append(
            {
                "trial_id": row.get("trial_id", ""),
                "paired_trial_name": row.get("paired_trial_name", ""),
                "object_case_id": obj_id,
                "object_family": row.get("object_family", ""),
                "raw_pre_extraction_gain": row.get("pre_extraction_object_reference_gain_150mhz", ""),
                "estimated_100mhz_coherence_length_m": gen_lc,
                "estimated_150mhz_coherence_length_m": target_lc,
                "recommended_segment_length_m": segment,
                "recommended_qpm_sign_flip_positions": flips,
                "recommended_magnetic_bias_sign_flip_positions": flips,
                "recommended_velocity_trim_direction": velocity_trim_direction(
                    safe_float(tomo.get("target_lock_error_slope_rad_per_m")),
                    safe_float(tomo.get("generated_lock_error_slope_rad_per_m")),
                ),
                "recommended_impedance_load_taper_direction": load_taper_direction(reflection, amp_growth),
                "layout_most_consistent_with_phase_errors": layout_recommendation(row, tomo),
                "worth_trying_as_mini_validation": worth_trying,
                "why": (
                    "bounded retiming smoke only; current data still misses target lock/coherent-growth gates"
                    if worth_trying
                    else "no high-confidence rescue path in measured taps"
                ),
            }
        )
    worth_any = any(bool(plan.get("worth_trying_as_mini_validation")) for plan in plans)
    return {
        "top_plans": plans,
        "measured_qpm_retiming_path_worth_trying": worth_any,
        "global_rescue_read": (
            "only a bounded mini-validation is justified"
            if worth_any
            else "no coherent rescue path is supported by the measured tap data"
        ),
    }


def write_rescue_plan_markdown(path: Path, plan: Dict[str, object]) -> None:
    lines = [
        "# SPICE 4->8->12 Phase-Slip Tomography Rescue Plan",
        "",
        f"Global read: {plan.get('global_rescue_read')}.",
        "",
    ]
    for item in plan.get("top_plans", []):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"## {item.get('paired_trial_name')}",
                "",
                f"- Object family: {item.get('object_family')}.",
                f"- Raw pre-extraction gain: {item.get('raw_pre_extraction_gain')}.",
                f"- Estimated 100 MHz coherence length: {item.get('estimated_100mhz_coherence_length_m')} m.",
                f"- Estimated 150 MHz coherence length: {item.get('estimated_150mhz_coherence_length_m')} m.",
                f"- Recommended segment length: {item.get('recommended_segment_length_m')} m.",
                f"- Recommended QPM flips: {json.dumps(item.get('recommended_qpm_sign_flip_positions'))}.",
                f"- Recommended magnetic-bias flips: {json.dumps(item.get('recommended_magnetic_bias_sign_flip_positions'))}.",
                f"- Velocity trim: {item.get('recommended_velocity_trim_direction')}.",
                f"- Load/impedance taper: {item.get('recommended_impedance_load_taper_direction')}.",
                f"- Layout read: {item.get('layout_most_consistent_with_phase_errors')}.",
                f"- Worth trying: {item.get('worth_trying_as_mini_validation')} ({item.get('why')}).",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def aggregate_read(pair_rows: List[Dict[str, object]], rescue_plan: Dict[str, object]) -> Dict[str, object]:
    promoted = [row for row in pair_rows if row.get("promotion_label") == "electrical_phase_rescue_candidate"]
    near = [row for row in pair_rows if row.get("promotion_label") == "electrical_phase_rescue_near_miss"]
    successful = [row for row in pair_rows if row.get("object_execution_status") == "ran_successfully" and row.get("reference_execution_status") == "ran_successfully"]
    top = max(successful, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), default={})
    failure_counts: Dict[str, int] = {}
    for row in pair_rows:
        mode = str(row.get("primary_failure_mode", "unknown"))
        failure_counts[mode] = failure_counts.get(mode, 0) + 1
    common_failure = max(failure_counts.items(), key=lambda item: item[1], default=("unknown", 0))[0]
    blocked = not promoted
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "paired_trials_total": len(pair_rows),
        "successful_pairs": len(successful),
        "electrical_phase_rescue_candidate_count": len(promoted),
        "electrical_phase_rescue_near_miss_count": len(near),
        "closest_pair": top.get("paired_trial_name", ""),
        "closest_object_family": top.get("object_family", ""),
        "closest_pair_gain": top.get("pre_extraction_object_reference_gain_150mhz", ""),
        "closest_pair_phase_lock_target_pre": top.get("phase_lock_target_pre", ""),
        "closest_pair_coherent_growth": top.get("distributed_150mhz_coherent_growth", ""),
        "dominant_failure_mode": common_failure,
        "failure_mode_counts_json": json.dumps(failure_counts, sort_keys=True),
        "measured_qpm_retiming_path_worth_trying": str(rescue_plan.get("measured_qpm_retiming_path_worth_trying")),
        "electrical_topology_blocked": str(blocked),
        "recommended_next_step": (
            "keep current electrical topology blocked behind acoustic/waveguide physicalization; optional rescue is bounded mini-validation only"
            if blocked and near
            else "keep current electrical topology blocked behind acoustic/waveguide physicalization"
            if blocked
            else "run only the bounded rescue mini-validation before any broader sweep"
        ),
    }


def rescue_variants(best_case: witness.WitnessCase, plan: Dict[str, object]) -> List[witness.WitnessCase]:
    top_plan = (plan.get("top_plans") or [{}])[0]
    if not isinstance(top_plan, dict):
        top_plan = {}
    velocity = str(top_plan.get("recommended_velocity_trim_direction", ""))
    target_trim = 1.025 if "increase target" in velocity else 0.975
    generated_trim = 0.990 if "slow the generated" in velocity else 1.010
    segment = safe_float(top_plan.get("recommended_segment_length_m"), best_case.total_length_m / 4.0)
    shorter_length = max(0.08, min(best_case.total_length_m, 4.0 * segment))
    variants = [
        witness.clone_case(best_case, case_id="rescue_001", name="best_object_measured_qpm_retimed", filename="best_object_measured_qpm_retimed.cir", qpm_pattern_mode="chirped", notes="Measured phase-slip tomography rescue: chirped QPM retiming."),
        witness.clone_case(best_case, case_id="rescue_002", name="best_object_measured_velocity_trimmed", filename="best_object_measured_velocity_trimmed.cir", target_phase_velocity_scale=best_case.target_phase_velocity_scale * target_trim, generated_phase_velocity_scale=best_case.generated_phase_velocity_scale * generated_trim, notes="Measured phase-slip tomography rescue: velocity trim."),
        witness.clone_case(best_case, case_id="rescue_003", name="best_object_impedance_tapered", filename="best_object_impedance_tapered.cir", output_load_ohm=best_case.z0_ohm * 1.25, notes="Measured phase-slip tomography rescue: broadband load/impedance taper proxy."),
        witness.clone_case(best_case, case_id="rescue_004", name="best_object_magnetic_lag_compensated", filename="best_object_magnetic_lag_compensated.cir", magnetic_dc_bias_proxy=best_case.magnetic_dc_bias_proxy + 0.35, hybrid_relative_phase=best_case.hybrid_relative_phase - 0.45, notes="Measured phase-slip tomography rescue: magnetic lag compensation proxy."),
        witness.clone_case(best_case, case_id="rescue_005", name="best_object_low_loss_longer_line", filename="best_object_low_loss_longer_line.cir", total_length_m=best_case.total_length_m * 1.18, series_loss_ohm_scale=best_case.series_loss_ohm_scale * 0.70, shunt_loss_ohm=best_case.shunt_loss_ohm * 1.5, notes="Measured phase-slip tomography rescue: low-loss longer line."),
        witness.clone_case(best_case, case_id="rescue_006", name="best_object_shorter_coherence_length_line", filename="best_object_shorter_coherence_length_line.cir", total_length_m=shorter_length, notes="Measured phase-slip tomography rescue: shorter coherence-length line."),
    ]
    return variants


def run_rescue(
    out_dir: Path,
    source_dir: Path,
    plan: Dict[str, object],
    case_map: Dict[str, witness.WitnessCase],
    ngspice_path_raw: str | None,
    timeout_s: int,
) -> Dict[str, object]:
    top_plans = plan.get("top_plans") or []
    if not top_plans or not isinstance(top_plans[0], dict):
        return {"run_rescue_requested": True, "rescue_rows": [], "reason": "no top plan available"}
    best_case_id = str(top_plans[0].get("object_case_id"))
    best_case = case_map.get(best_case_id)
    if best_case is None:
        return {"run_rescue_requested": True, "rescue_rows": [], "reason": f"could not find {best_case_id}"}
    ngspice_path = design.resolve_ngspice_path(ngspice_path_raw)
    if ngspice_path is None:
        return {"run_rescue_requested": True, "rescue_rows": [], "reason": "ngspice not found"}
    rescue_dir = ensure_dir(out_dir / "rescue_netlists")
    rows: List[Dict[str, object]] = []
    for case in rescue_variants(best_case, plan):
        netlist_path = rescue_dir / case.filename
        csv_path = rescue_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist_path.write_text(witness.instrument_netlist(case, csv_path), encoding="utf-8")
        export = witness.WitnessExport(case, netlist_path, csv_path)
        result = witness.run_ngspice(export, ngspice_path, timeout_s)
        metrics: Dict[str, object] = {}
        if result.success:
            try:
                data = witness.read_transient(csv_path)
                _tap_rows, _local_rows, metrics = phasors_for_case(
                    {
                        **asdict(case),
                        "csv_file": csv_path.name,
                        "side": "object",
                        "execution_status": "ran_successfully",
                    },
                    case,
                    rescue_dir,
                )
            except Exception as exc:
                result = design.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
        rows.append(
            {
                "row_type": "phase_slip_rescue_row",
                "case_id": case.case_id,
                "name": case.name,
                "netlist_file": str(netlist_path.name),
                "csv_file": str(csv_path.name) if result.success else "",
                "execution_status": result.execution_status,
                "reason": result.reason,
                "source_only_drive": str(case.source_only_drive),
                "direct_100mhz_drive_present": str(case.direct_100_drive_present),
                "direct_150mhz_drive_present": str(case.direct_150_drive_present),
                "target_frequency_injection_present": str(case.target_frequency_injection_present),
                "pre_extraction_150mhz_purity": metrics.get("pre_extraction_150mhz_purity", ""),
                "target_fft_power_pre": metrics.get("target_fft_power_pre", ""),
                "phase_lock_generated_tomography": metrics.get("phase_lock_generated_tomography", ""),
                "phase_lock_target_tomography": metrics.get("phase_lock_target_tomography", ""),
                "target_path_stability_score": metrics.get("target_path_stability_score", ""),
            }
        )
    write_csv(out_dir / "rescue_summary.csv", rows)
    (out_dir / "rescue_summary.json").write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"run_rescue_requested": True, "rescue_rows": rows, "reason": ""}


def write_readme(
    out_dir: Path,
    aggregate: Dict[str, object],
    pair_rows: List[Dict[str, object]],
    rescue_plan: Dict[str, object],
) -> None:
    successful = [row for row in pair_rows if row.get("object_execution_status") == "ran_successfully" and row.get("reference_execution_status") == "ran_successfully"]
    top = max(successful, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), default={})
    modes = json.loads(str(aggregate.get("failure_mode_counts_json", "{}")))
    top_plans = rescue_plan.get("top_plans") or []
    first_plan = top_plans[0] if top_plans and isinstance(top_plans[0], dict) else {}
    lines = [
        "# SPICE 4->8->12 Phase-Slip Tomography",
        "",
        "Focused forensic pass over the existing differential witness-line artifacts. No broad sweep or high-Q extraction promotion is used.",
        "",
        "## Direct Answers",
        "",
        f"- Where does 100 MHz coherence fail? In the closest raw-gain pair, first failure is {top.get('object_first_100mhz_coherence_fail_tap', '')}; aggregate dominant mode: {aggregate.get('dominant_failure_mode')}. See `tap_phase_error.csv` for tap-level `local_100mhz_lock_error_rad`.",
        f"- Where does 150 MHz coherence fail? In the closest raw-gain pair, first failure is {top.get('object_first_150mhz_coherence_fail_tap', '')}; target lock={top.get('phase_lock_target_pre', '')}, coherent growth={top.get('distributed_150mhz_coherent_growth', '')}.",
        f"- Blocker classification: {aggregate.get('dominant_failure_mode')} with counts {modes}.",
        f"- Closest object family: {aggregate.get('closest_object_family')} via {aggregate.get('closest_pair')}.",
        f"- Is there a measured QPM retiming path worth trying? {aggregate.get('measured_qpm_retiming_path_worth_trying')}; {rescue_plan.get('global_rescue_read')}.",
        f"- Should electrical continue? {aggregate.get('recommended_next_step')}.",
        "",
        "## Results",
        "",
        f"- Paired trials: total={aggregate.get('paired_trials_total')}, successful={aggregate.get('successful_pairs')}.",
        f"- Phase rescue candidates: {aggregate.get('electrical_phase_rescue_candidate_count')}.",
        f"- Phase rescue near misses: {aggregate.get('electrical_phase_rescue_near_miss_count')}.",
        f"- Closest pair raw gain: {aggregate.get('closest_pair_gain')}.",
        f"- Closest pair target lock: {aggregate.get('closest_pair_phase_lock_target_pre')}.",
        f"- Closest pair coherent growth: {aggregate.get('closest_pair_coherent_growth')}.",
        "",
        "## Top Pairs",
        "",
    ]
    for row in sorted(pair_rows, key=lambda item: safe_float(item.get("pre_extraction_object_reference_gain_150mhz")), reverse=True)[:10]:
        lines.append(
            "- {name}: label={label}, failure={failure}, gain={gain}, target_lock={lock}, coherent_growth={growth}, "
            "first_100_fail={fail100}, first_150_fail={fail150}.".format(
                name=row.get("paired_trial_name"),
                label=row.get("promotion_label"),
                failure=row.get("primary_failure_mode"),
                gain=row.get("pre_extraction_object_reference_gain_150mhz"),
                lock=row.get("phase_lock_target_pre"),
                growth=row.get("distributed_150mhz_coherent_growth"),
                fail100=row.get("object_first_100mhz_coherence_fail_tap"),
                fail150=row.get("object_first_150mhz_coherence_fail_tap"),
            )
        )
    lines.extend(
        [
            "",
            "## Conservative Read",
            "",
            "The data show raw 150 MHz gain without enough coherent phase accumulation. Current electrical topology remains blocked behind the acoustic/waveguide route unless a tightly bounded rescue mini-validation is explicitly requested with `--run-rescue`.",
        ]
    )
    (out_dir / "README_SPICE_412_PHASE_SLIP_TOMOGRAPHY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Analyze phase-slip tomography for the differential witness line.")
    parser.add_argument("--source-dir", default=str(SOURCE_DIR), help="Existing differential witness-line run directory.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run-rescue", action="store_true", help="Generate and run at most six measured rescue netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice for --run-rescue.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per rescue netlist.")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    check_required_artifacts(source_dir)
    out_dir = ensure_dir(Path(args.out))
    summary_json = read_json(source_dir / "spice_412_differential_witness_line_summary.json")
    summary_csv_rows = read_csv_rows(source_dir / "spice_412_differential_witness_line_summary.csv")
    tap_timeseries_rows = count_csv_data_rows(source_dir / "spice_412_differential_witness_line_tap_timeseries.csv")
    pairs = [dict(row) for row in summary_json.get("pairs", []) if isinstance(row, dict)]
    cases = [dict(row) for row in summary_json.get("cases", []) if isinstance(row, dict)]
    case_rows = {str(row.get("case_id")): row for row in cases}
    case_objects = case_map_from_witness()

    tap_rows_all: List[Dict[str, object]] = []
    local_rows_all: List[Dict[str, object]] = []
    case_tomography: Dict[str, Dict[str, object]] = {}
    for case in cases:
        if case.get("execution_status") != "ran_successfully":
            continue
        case_id = str(case.get("case_id"))
        tap_rows, local_rows, summary = phasors_for_case(case, case_objects.get(case_id), source_dir)
        summary["total_length_m"] = safe_float(case.get("total_length_m"), 0.50)
        tap_rows_all.extend(tap_rows)
        local_rows_all.extend(local_rows)
        case_tomography[case_id] = summary

    pair_rows = build_pair_summaries(pairs, case_tomography)
    rescue_plan = build_rescue_plan(pair_rows, tap_rows_all, case_tomography)
    aggregate = aggregate_read(pair_rows, rescue_plan)
    aggregate["source_summary_csv_rows"] = len(summary_csv_rows)
    aggregate["source_tap_timeseries_rows"] = tap_timeseries_rows
    aggregate["source_dir"] = str(source_dir)

    rescue_result: Dict[str, object] = {"run_rescue_requested": False, "rescue_rows": []}
    if args.run_rescue:
        rescue_result = run_rescue(
            out_dir,
            source_dir,
            rescue_plan,
            case_objects,
            args.ngspice_path or None,
            args.timeout,
        )

    write_csv(out_dir / "tomography_summary.csv", [aggregate] + pair_rows)
    write_csv(out_dir / "tap_phase_error.csv", tap_rows_all)
    write_csv(out_dir / "local_growth_by_tap.csv", local_rows_all)
    (out_dir / "tomography_summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": aggregate,
                    "pairs": pair_rows,
                    "case_tomography": case_tomography,
                    "source_summary_csv_rows": len(summary_csv_rows),
                    "source_tap_timeseries_rows": tap_timeseries_rows,
                    "rescue_result": rescue_result,
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "rescue_plan.json").write_text(json.dumps(sanitize(rescue_plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_rescue_plan_markdown(out_dir / "rescue_plan.md", rescue_plan)
    write_readme(out_dir, aggregate, pair_rows, rescue_plan)
    print(
        json.dumps(
            sanitize(
                {
                    "paired_trials_total": aggregate.get("paired_trials_total"),
                    "successful_pairs": aggregate.get("successful_pairs"),
                    "phase_rescue_candidates": aggregate.get("electrical_phase_rescue_candidate_count"),
                    "phase_rescue_near_misses": aggregate.get("electrical_phase_rescue_near_miss_count"),
                    "dominant_failure_mode": aggregate.get("dominant_failure_mode"),
                    "electrical_topology_blocked": aggregate.get("electrical_topology_blocked"),
                    "recommended_next_step": aggregate.get("recommended_next_step"),
                    "summary": str(out_dir / "tomography_summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
