#!/usr/bin/env python3
"""Robustness validator for the frozen acoustic b007 bench candidate.

This script does not search for a better acoustic geometry.  It freezes
`b007 acoustic_compact_short_guide` from `acoustic_412_bench_physicalization`
and tries to break it with numerical, tolerance, material/load, drive/readout,
and matched-control perturbations.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

import acoustic_412_bench_physicalization as bench


OUT_DIR = Path("runs") / "acoustic_412_bench_robustness_validator"
EPS = 1.0e-18


@dataclass(frozen=True)
class TestCase:
    test_id: str
    bucket: str
    subtest: str
    variant: str
    role: str
    config: bench.BenchConfig
    dt: float = bench.BASE_DT
    tmax: float = bench.BASE_TMAX
    sample_stride: int = bench.SAMPLE_STRIDE
    window_start_frac: float = 0.52
    window_end_frac: float = 0.74
    tap_error_fraction: float = 0.0
    spacing_jitter_fraction: float = 0.0
    spacing_jitter_seed: int = 0
    sensor_bandwidth_hz: float = 250_000.0
    sensor_noise_fraction: float = 0.0
    sensor_resonance_artifact: bool = False
    tolerance_kind: str = ""
    tolerance_abs_percent: float = 0.0
    notes: str = ""


@dataclass
class SimContext:
    test: TestCase
    result: bench.BenchResult


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


def sanitize(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(key): sanitize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [sanitize(value) for value in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def physical_config_key(cfg: bench.BenchConfig) -> Tuple[Tuple[str, object], ...]:
    data = asdict(cfg)
    for metadata_key in ("case_id", "name", "role", "notes"):
        data.pop(metadata_key, None)
    return tuple(sorted(data.items()))


def simulation_key(test: TestCase) -> Tuple[object, ...]:
    return (
        physical_config_key(test.config),
        test.dt,
        test.tmax,
        test.sample_stride,
        test.tap_error_fraction,
        test.spacing_jitter_fraction,
        test.spacing_jitter_seed,
    )


def simulate_for_cache(test: TestCase) -> Tuple[Tuple[object, ...], bench.BenchResult]:
    return simulation_key(test), simulate_case(test).result


def frozen_b007() -> bench.BenchConfig:
    configs = bench.build_configs()
    return next(cfg for cfg in configs if cfg.case_id == "b007")


def direct_reference() -> bench.BenchConfig:
    return bench.direct_reference_config()


def with_name(cfg: bench.BenchConfig, case_id: str, name: str, role: str = "discovery", **updates: object) -> bench.BenchConfig:
    data = asdict(cfg)
    data.update(updates)
    data.update({"case_id": case_id, "name": name, "role": role})
    return bench.BenchConfig(**data)


def matched_control_configs(base: bench.BenchConfig, prefix: str) -> List[bench.BenchConfig]:
    return [
        with_name(
            base,
            f"{prefix}_linear",
            "linear_no_nonlinearity",
            role="control",
            no_nonlinearity=True,
            nonlinear_448=0.0,
            nonlinear_4812=0.0,
            generated_path_scale=0.0,
            target_path_scale=0.0,
        ),
        with_name(
            base,
            f"{prefix}_shuffled",
            "shuffled_qpm",
            role="control",
            qpm_enabled=True,
            qpm_period_m=0.042,
            qpm_duty_cycle=0.48,
            grating_kind="shuffled",
            phase_velocity_8_ratio=0.986,
            phase_velocity_12_ratio=0.974,
            randomized_grating_seed=412369,
        ),
        with_name(
            base,
            f"{prefix}_generated_suppressed",
            "generated_path_suppressed_80",
            role="control",
            generated_path_scale=0.04,
            nonlinear_448=0.012,
        ),
        with_name(
            base,
            f"{prefix}_phase_mismatch",
            "phase_mismatched_120",
            role="control",
            phase_velocity_8_ratio=0.910,
            phase_velocity_12_ratio=1.170,
            target_detuning=0.48,
        ),
        with_name(
            base,
            f"{prefix}_target_detuned",
            "target_velocity_detuned_120",
            role="control",
            phase_velocity_12_ratio=0.835,
            target_detuning=0.82,
        ),
        with_name(
            base,
            f"{prefix}_too_short",
            "too_short_guide",
            role="control",
            cell_count=24,
            interaction_length_m=0.019,
        ),
        with_name(
            base,
            f"{prefix}_too_lossy",
            "too_lossy_guide",
            role="control",
            damping_loss=0.150,
            boundary_absorption=0.180,
            absorber_load=True,
            absorber_strength=0.150,
        ),
        with_name(
            base,
            f"{prefix}_sensor_artifact",
            "sensor_artifact_control",
            role="control",
            no_nonlinearity=True,
            nonlinear_448=0.0,
            nonlinear_4812=0.0,
            generated_path_scale=0.0,
            target_path_scale=0.0,
            sensor_artifact_drive=True,
            readout_feedthrough=0.050,
        ),
    ]


def set_bench_globals(dt: float, tmax: float, sample_stride: int) -> Tuple[float, float, int]:
    old = (bench.BASE_DT, bench.BASE_TMAX, bench.SAMPLE_STRIDE)
    bench.BASE_DT = dt
    bench.BASE_TMAX = tmax
    bench.SAMPLE_STRIDE = sample_stride
    return old


def restore_bench_globals(old: Tuple[float, float, int]) -> None:
    bench.BASE_DT, bench.BASE_TMAX, bench.SAMPLE_STRIDE = old


def tap_indices(cell_count: int, tap_error_fraction: float) -> List[int]:
    indices: List[int] = []
    for idx, (_label, frac) in enumerate(bench.TAP_FRACTIONS):
        if idx in (0, len(bench.TAP_FRACTIONS) - 1):
            shifted = frac
        else:
            sign = -1.0 if idx % 2 else 1.0
            shifted = frac + sign * tap_error_fraction
        indices.append(min(cell_count - 1, max(0, int(round(shifted * (cell_count - 1))))))
    return indices


def z_grid(cfg: bench.BenchConfig, jitter_fraction: float, seed: int) -> np.ndarray:
    if jitter_fraction <= 0.0 or cfg.cell_count < 3:
        return np.linspace(0.0, cfg.interaction_length_m, cfg.cell_count)
    rng = np.random.default_rng(seed)
    increments = np.ones(cfg.cell_count - 1)
    increments *= 1.0 + rng.normal(0.0, jitter_fraction, size=cfg.cell_count - 1)
    increments = np.clip(increments, 0.50, 1.50)
    increments *= cfg.interaction_length_m / max(float(np.sum(increments)), EPS)
    return np.concatenate([[0.0], np.cumsum(increments)])


def simulate_case(test: TestCase) -> SimContext:
    cfg = test.config
    nums = bench.acoustic_numbers(cfg)
    z = z_grid(cfg, test.spacing_jitter_fraction, test.spacing_jitter_seed)
    qpm_period = cfg.qpm_period_m
    if cfg.qpm_enabled and qpm_period <= 0.0 and math.isfinite(nums["qpm_period_m_estimate"]):
        cfg = replace(cfg, qpm_period_m=nums["qpm_period_m_estimate"])
    pattern = bench.qpm_pattern(z, cfg, nums["limiting_delta_k_rad_m"])
    taps = tap_indices(cfg.cell_count, test.tap_error_fraction)
    state = np.zeros(3 * cfg.cell_count, dtype=complex)
    steps = int(round(test.tmax / test.dt))
    times: List[float] = []
    a4_rows: List[np.ndarray] = []
    a8_rows: List[np.ndarray] = []
    a12_rows: List[np.ndarray] = []
    energy: List[float] = []
    drive_work = 0.0
    loss_work = 0.0
    old = set_bench_globals(test.dt, test.tmax, test.sample_stride)
    try:
        for step in range(steps + 1):
            t = step * test.dt
            if step % test.sample_stride == 0:
                a4 = state[0:cfg.cell_count]
                a8 = state[cfg.cell_count:2 * cfg.cell_count]
                a12 = state[2 * cfg.cell_count:3 * cfg.cell_count]
                times.append(t)
                a4_rows.append(a4[taps].copy())
                a8_rows.append(a8[taps].copy())
                a12_rows.append(a12[taps].copy())
                energy.append(float(np.vdot(state, state).real))
            if step == steps:
                break
            state, powers = bench.rk4_step(state, t, test.dt, cfg, z, pattern, nums)
            drive_work += powers["drive_power"] * test.dt
            loss_work += powers["loss_power"] * test.dt
    finally:
        restore_bench_globals(old)
    result = bench.BenchResult(
        config=cfg,
        times=np.asarray(times),
        tap_a4=np.asarray(a4_rows),
        tap_a8=np.asarray(a8_rows),
        tap_a12=np.asarray(a12_rows),
        energy=np.asarray(energy),
        z=z,
        tap_indices=taps,
        pattern=pattern,
        drive_work=drive_work,
        loss_work=loss_work,
    )
    return SimContext(test, result)


def window_mask(result: bench.BenchResult, test: TestCase) -> np.ndarray:
    start = test.window_start_frac * test.tmax
    stop = test.window_end_frac * test.tmax
    mask = (result.times >= start) & (result.times <= stop)
    if int(np.sum(mask)) < 8:
        mask = (result.times >= 0.52 * test.tmax) & (result.times <= 0.74 * test.tmax)
    if int(np.sum(mask)) < 8:
        mask = result.times >= 0.55 * result.times[-1]
    return mask


def phasors_for_result(result: bench.BenchResult, test: TestCase) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = window_mask(result, test)
    ph4 = np.mean(result.tap_a4[mask, :], axis=0)
    ph8 = np.mean(result.tap_a8[mask, :], axis=0)
    ph12 = np.mean(result.tap_a12[mask, :], axis=0)
    if test.sensor_noise_fraction > 0.0:
        seed = 8000 + sum((idx + 1) * ord(ch) for idx, ch in enumerate(test.test_id)) % 100_000
        rng = np.random.default_rng(seed)
        scale = test.sensor_noise_fraction * max(float(np.max(np.abs(ph12))), EPS)
        noise = scale * (rng.normal(size=ph12.shape) + 1j * rng.normal(size=ph12.shape))
        ph12 = ph12 + noise
    if test.sensor_resonance_artifact:
        artifact = 0.015 * max(float(np.max(np.abs(ph4))), EPS)
        ph12 = ph12 + artifact * np.exp(1j * np.linspace(0.0, math.pi / 2.0, len(ph12)))
    return ph4, ph8, ph12


def sensor_bandwidth_score(raw12: complex, bandwidth_hz: float) -> float:
    if bandwidth_hz <= bench.SOURCE_HZ:
        return 0.0
    # A simple one-pole pickup response used only as a diagnostic sensitivity
    # score. Raw waveguide metrics remain the promotion basis.
    response = 1.0 / math.sqrt(1.0 + (bench.TARGET_HZ / max(bandwidth_hz, EPS)) ** 4)
    return float(abs(raw12) ** 2 * response * response)


def base_row(ctx: SimContext) -> Dict[str, object]:
    test = ctx.test
    result = ctx.result
    cfg = result.config
    nums = bench.acoustic_numbers(cfg)
    ph4, ph8, ph12 = phasors_for_result(result, test)
    amp4 = np.abs(ph4)
    amp8 = np.abs(ph8)
    amp12 = np.abs(ph12)
    fractions = np.asarray([frac for _label, frac in bench.TAP_FRACTIONS], dtype=float)
    non_input = slice(1, None)
    err80 = np.asarray(bench.wrap_pi(np.angle(ph8) - 2.0 * np.angle(ph4)), dtype=float)
    err120 = np.asarray(bench.wrap_pi(np.angle(ph12) - np.angle(ph8) - np.angle(ph4)), dtype=float)
    lock80 = bench.phase_lock(err80[non_input], amp8[non_input] * amp4[non_input] ** 2)
    lock120 = bench.phase_lock(err120[non_input], amp12[non_input] * amp8[non_input] * amp4[non_input])
    raw4, raw8, raw12 = ph4[-1], ph8[-1], ph12[-1]
    raw_p40 = float(abs(raw4) ** 2)
    raw_p80 = float(abs(raw8) ** 2)
    raw_p120 = float(abs(raw12) ** 2)
    first80 = max(float(amp8[1]), 0.05 * float(np.max(amp8)), EPS)
    first120 = max(float(amp12[1]), 0.05 * float(np.max(amp12)), EPS)
    coherent_growth = float(amp12[-1] / first120) * lock120
    slope = 0.0
    if len(fractions[1:]) > 2 and float(np.max(amp12)) > EPS:
        floor = max(0.02 * float(np.max(amp12)), EPS)
        slope = float(np.polyfit(fractions[1:], np.log(amp12[1:] + floor), 1)[0])
    purity = raw_p120 / max(raw_p40 + raw_p80 + raw_p120, EPS)
    target_power = raw_p120 * lock120
    mask = window_mask(result, test)
    raw_phase_series = np.unwrap(
        np.angle(result.tap_a12[mask, -1])
        - np.angle(result.tap_a8[mask, -1])
        - np.angle(result.tap_a4[mask, -1])
    )
    jumps = np.abs(np.diff(raw_phase_series)) if len(raw_phase_series) > 1 else np.asarray([0.0])
    max_jump = float(np.max(jumps)) if len(jumps) else 0.0
    target_cv = bench.envelope_cv(result.tap_a12[mask, -1])
    peak_amp = max(float(np.max(np.abs(result.tap_a4))), float(np.max(np.abs(result.tap_a8))), float(np.max(np.abs(result.tap_a12))))
    peak_pressure = cfg.pressure_scale_pa * peak_amp
    if peak_pressure < 5_000.0:
        stress_class = "plausible"
    elif peak_pressure < 25_000.0:
        stress_class = "aggressive-but-testable"
    else:
        stress_class = "unrealistic"
    acoustic_impedance = cfg.material_density_kg_m3 * cfg.phase_velocity_4_m_s
    displacement = peak_pressure / max(acoustic_impedance * 2.0 * math.pi * bench.SOURCE_HZ, EPS)
    voltage = peak_pressure / max(cfg.piezo_pressure_per_volt, EPS)
    acoustic_power = (peak_pressure ** 2 / max(2.0 * acoustic_impedance, EPS)) * cfg.aperture_area_m2
    transducer_power = acoustic_power / 0.04
    pitch = cfg.interaction_length_m / max(cfg.cell_count, 1)
    buildability = float(
        0.20 * clamp(1.0 - abs(cfg.interaction_length_m - 0.041) / 0.12)
        + 0.14 * clamp(1.0 - abs(cfg.cell_count - 36) / 64.0)
        + 0.18 * clamp(1.0 - peak_pressure / 35_000.0)
        + 0.14 * clamp(1.0 - max(voltage - 100.0, 0.0) / 180.0)
        + 0.12 * clamp(1.0 - max(transducer_power - 2.0, 0.0) / 6.0)
        + 0.10 * clamp(1.0 - abs(pitch - 0.001139) / 0.003)
        + 0.12 * (1.0 if stress_class in {"plausible", "aggressive-but-testable"} else 0.0)
    )
    source_only = cfg.role != "ceiling_reference" and not cfg.direct_80_reference_drive
    return {
        **nums,
        "row_type": "robustness_row",
        "test_id": test.test_id,
        "bucket": test.bucket,
        "subtest": test.subtest,
        "variant": test.variant,
        "role": test.role,
        "case_id": cfg.case_id,
        "name": cfg.name,
        "topology": cfg.topology,
        "source_only_drive": str(source_only),
        "direct_80khz_drive_present": str(cfg.direct_80_reference_drive),
        "direct_120khz_drive_present": "False",
        "target_frequency_injection_present": "False",
        "cell_count": cfg.cell_count,
        "interaction_length_m": cfg.interaction_length_m,
        "segment_spacing_m": pitch,
        "dt": test.dt,
        "tmax": test.tmax,
        "sample_stride": test.sample_stride,
        "window_start_frac": test.window_start_frac,
        "window_end_frac": test.window_end_frac,
        "tap_error_fraction": test.tap_error_fraction,
        "spacing_jitter_fraction": test.spacing_jitter_fraction,
        "sensor_bandwidth_hz": test.sensor_bandwidth_hz,
        "sensor_noise_fraction": test.sensor_noise_fraction,
        "sensor_resonance_artifact": str(test.sensor_resonance_artifact),
        "tolerance_kind": test.tolerance_kind,
        "tolerance_abs_percent": test.tolerance_abs_percent,
        "phase_lock_80khz": lock80,
        "phase_lock_120khz": lock120,
        "raw_pre_readout_120khz_purity": purity,
        "distributed_120khz_coherent_growth": coherent_growth,
        "distributed_120khz_growth_slope": slope,
        "target_coherent_power_120khz": target_power,
        "raw_output_40khz_power": raw_p40,
        "raw_output_80khz_power": raw_p80,
        "raw_output_120khz_power": raw_p120,
        "sensor_band_limited_120khz_power": sensor_bandwidth_score(raw12, test.sensor_bandwidth_hz),
        "max_phase_jump": max_jump,
        "target_envelope_cv": target_cv,
        "pressure_stress_class": stress_class,
        "estimated_pressure_pa": peak_pressure,
        "estimated_displacement_m": displacement,
        "estimated_transducer_voltage_v": voltage,
        "estimated_transducer_power_w": transducer_power,
        "estimated_sensor_bandwidth_required_hz": test.sensor_bandwidth_hz,
        "buildability_score": buildability,
        "drive_work_proxy": result.drive_work,
        "loss_work_proxy": result.loss_work,
        "notes": test.notes,
    }


def row_pass_fail(row: Dict[str, object]) -> Tuple[bool, str]:
    failures: List[str] = []
    if str(row.get("source_only_drive")) != "True":
        failures.append("not_source_only")
    if str(row.get("direct_80khz_drive_present")) != "False":
        failures.append("direct_80_drive")
    if str(row.get("direct_120khz_drive_present")) != "False":
        failures.append("direct_120_drive")
    if str(row.get("target_frequency_injection_present")) != "False":
        failures.append("target_injection")
    checks = [
        ("phase_lock_120khz", 0.90, ">="),
        ("phase_lock_80khz", 0.80, ">="),
        ("distributed_120khz_coherent_growth", 2.0, ">="),
        ("distributed_120khz_growth_slope", 0.0, ">"),
        ("raw_pre_readout_120khz_purity", 0.60, ">="),
        ("object_reference_gain_120khz", 10.0, ">="),
        ("generated_path_dependency_score", 0.80, ">="),
        ("phase_mismatch_kill_score", 0.80, ">="),
        ("qpm_dependency_score", 0.60, ">="),
        ("sensor_artifact_score", 0.25, "<="),
        ("max_control_leakage", 0.15, "<"),
        ("buildability_score", 0.60, ">="),
    ]
    for key, threshold, op in checks:
        value = safe_float(row.get(key), -1.0 if op in {">=", ">"} else 99.0)
        if op == ">=" and value < threshold:
            failures.append(f"{key}_below_{threshold:g}")
        elif op == ">" and value <= threshold:
            failures.append(f"{key}_not_positive")
        elif op == "<=" and value > threshold:
            failures.append(f"{key}_above_{threshold:g}")
        elif op == "<" and value >= threshold:
            failures.append(f"{key}_not_below_{threshold:g}")
    if str(row.get("pressure_stress_class")) not in {"plausible", "aggressive-but-testable"}:
        failures.append("stress_unrealistic")
    return not failures, "pass" if not failures else ";".join(failures)


def apply_bundle_scores(rows: List[Dict[str, object]], direct_power: float) -> None:
    by_bucket: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        by_bucket.setdefault(str(row.get("bucket")), []).append(row)
    for bucket_rows in by_bucket.values():
        candidates = [row for row in bucket_rows if row.get("role") == "candidate"]
        controls = [row for row in bucket_rows if row.get("role") == "control"]
        max_candidate_power = max((safe_float(row.get("target_coherent_power_120khz")) for row in candidates), default=0.0)
        max_control_power = max((safe_float(row.get("target_coherent_power_120khz")) for row in controls), default=0.0)
        generated = next((row for row in controls if row.get("name") == "generated_path_suppressed_80"), {})
        phase = next((row for row in controls if row.get("name") == "phase_mismatched_120"), {})
        shuffled = next((row for row in controls if row.get("name") == "shuffled_qpm"), {})
        sensor = next((row for row in controls if row.get("name") == "sensor_artifact_control"), {})
        generated_power = safe_float(generated.get("target_coherent_power_120khz"))
        phase_power = safe_float(phase.get("target_coherent_power_120khz"))
        shuffled_power = safe_float(shuffled.get("target_coherent_power_120khz"))
        sensor_power = safe_float(sensor.get("target_coherent_power_120khz"))
        for row in bucket_rows:
            power = safe_float(row.get("target_coherent_power_120khz"))
            if row.get("role") == "candidate":
                row["object_reference_gain_120khz"] = power / max(direct_power, max_control_power, EPS)
                row["generated_path_dependency_score"] = clamp(1.0 - generated_power / max(power, EPS))
                row["phase_mismatch_kill_score"] = clamp(1.0 - phase_power / max(power, EPS))
                row["qpm_dependency_score"] = clamp(1.0 - shuffled_power / max(power, EPS))
                row["sensor_artifact_score"] = clamp(sensor_power / max(power, EPS))
                row["max_control_leakage"] = clamp(max_control_power / max(power, EPS))
                passed, reason = row_pass_fail(row)
                row["row_passed"] = str(passed)
                row["pass_fail_reason"] = reason
                row["promotion_category"] = "row_pass" if passed else "row_fail"
            elif row.get("role") == "control":
                leakage = clamp(power / max(max_candidate_power, EPS))
                row["object_reference_gain_120khz"] = power / max(direct_power, EPS)
                row["generated_path_dependency_score"] = ""
                row["phase_mismatch_kill_score"] = ""
                row["qpm_dependency_score"] = ""
                row["sensor_artifact_score"] = ""
                row["max_control_leakage"] = leakage
                row["row_passed"] = str(leakage < 0.15)
                row["pass_fail_reason"] = "control_dead" if leakage < 0.15 else "control_leakage"
                row["promotion_category"] = "control_dead" if leakage < 0.15 else "control_leakage"


def add_bucket_controls(tests: List[TestCase], bucket: str, base: bench.BenchConfig) -> None:
    prefix = f"ctrl_{bucket}"
    for cfg in matched_control_configs(base, prefix):
        tests.append(
            TestCase(
                test_id=f"{bucket}_{cfg.name}",
                bucket=bucket,
                subtest="matched_control",
                variant=cfg.name,
                role="control",
                config=cfg,
                notes=f"Matched {bucket} control: {cfg.name}",
            )
        )


def build_tests() -> List[TestCase]:
    base = frozen_b007()
    tests: List[TestCase] = []

    numerical_specs = [
        ("nominal", {}, "frozen b007 nominal replay"),
        ("dt_half", {"dt": bench.BASE_DT * 0.5, "sample_stride": bench.SAMPLE_STRIDE * 2}, "half dt"),
        ("dt_quarter", {"dt": bench.BASE_DT * 0.25, "sample_stride": bench.SAMPLE_STRIDE * 4}, "quarter dt"),
        ("dt_double", {"dt": bench.BASE_DT * 2.0, "sample_stride": max(1, bench.SAMPLE_STRIDE // 2)}, "double dt stress"),
        ("early_window", {"window_start_frac": 0.48, "window_end_frac": 0.70}, "earlier projection window"),
        ("late_window", {"window_start_frac": 0.56, "window_end_frac": 0.78}, "later projection window"),
        ("short_window", {"window_start_frac": 0.58, "window_end_frac": 0.68}, "short projection window"),
        ("coarse_sampling", {"sample_stride": bench.SAMPLE_STRIDE * 3}, "coarser tap sampling"),
    ]
    for name, updates, note in numerical_specs:
        tests.append(
            TestCase(
                test_id=f"num_{name}",
                bucket="numerical",
                subtest=name,
                variant=name,
                role="candidate",
                config=base,
                notes=note,
                **updates,
            )
        )
    add_bucket_controls(tests, "numerical", base)

    for kind in ("cell_spacing", "guide_length"):
        for pct in (-5.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 5.0):
            scale = 1.0 + pct / 100.0
            cfg = replace(base, interaction_length_m=base.interaction_length_m * scale)
            tests.append(
                TestCase(
                    test_id=f"tol_{kind}_{pct:+.1f}pct".replace(".", "p"),
                    bucket="tolerance",
                    subtest=kind,
                    variant=f"{pct:+.1f}pct",
                    role="candidate",
                    config=cfg,
                    tolerance_kind=kind,
                    tolerance_abs_percent=abs(pct),
                    notes=f"{kind} perturbation {pct:+.1f}%",
                )
            )
    for pct, seed in ((1.0, 101), (2.0, 202), (5.0, 505)):
        tests.append(
            TestCase(
                test_id=f"tol_random_spacing_jitter_{pct:.1f}pct".replace(".", "p"),
                bucket="tolerance",
                subtest="random_per_cell_spacing_jitter",
                variant=f"{pct:.1f}pct",
                role="candidate",
                config=base,
                spacing_jitter_fraction=pct / 100.0,
                spacing_jitter_seed=seed,
                tolerance_kind="random_spacing_jitter",
                tolerance_abs_percent=pct,
                notes=f"deterministic random per-cell spacing jitter {pct:.1f}%",
            )
        )
    for pct in (-1.0, 1.0, -2.0, 2.0):
        tests.append(
            TestCase(
                test_id=f"tol_tap_position_error_{pct:+.1f}pct".replace(".", "p"),
                bucket="tolerance",
                subtest="tap_position_error",
                variant=f"{pct:+.1f}pct",
                role="candidate",
                config=base,
                tap_error_fraction=pct / 100.0,
                tolerance_kind="tap_position_error",
                tolerance_abs_percent=abs(pct),
                notes=f"alternating tap pickup placement error {pct:+.1f}%",
            )
        )
    tests.append(
        TestCase(
            test_id="tol_qpm_flip_position_jitter_noop",
            bucket="tolerance",
            subtest="qpm_flip_position_jitter",
            variant="not_applicable_no_qpm",
            role="candidate",
            config=base,
            tolerance_kind="qpm_flip_position_jitter",
            tolerance_abs_percent=0.0,
            notes="Frozen b007 has no QPM flips; this row confirms the no-QPM layout is unaffected.",
        )
    )
    add_bucket_controls(tests, "tolerance", base)

    for factor in (0.75, 1.00, 1.25, 1.50, 2.00):
        tests.append(
            TestCase(
                test_id=f"mat_damping_{factor:.2f}x".replace(".", "p"),
                bucket="material_load",
                subtest="damping_loss_sweep",
                variant=f"{factor:.2f}x",
                role="candidate",
                config=replace(base, damping_loss=base.damping_loss * factor),
                notes=f"damping/loss factor {factor:.2f}x",
            )
        )
    for absorber in (0.0, 0.02, 0.05, 0.10):
        tests.append(
            TestCase(
                test_id=f"mat_absorber_{absorber:.2f}".replace(".", "p"),
                bucket="material_load",
                subtest="absorber_load_sweep",
                variant=f"{absorber:.2f}",
                role="candidate",
                config=replace(base, absorber_load=absorber > 0.0, absorber_strength=absorber),
                notes=f"absorber/load termination strength {absorber:.2f}",
            )
        )
    tests.extend(
        [
            TestCase(
                test_id="mat_impedance_taper_removed",
                bucket="material_load",
                subtest="impedance_taper_removed",
                variant="removed",
                role="candidate",
                config=replace(base, impedance_taper=False, taper_strength=0.0),
                notes="b007 nominal has no taper; removal is a no-op control.",
            ),
            TestCase(
                test_id="mat_impedance_taper_over_applied",
                bucket="material_load",
                subtest="impedance_taper_over_applied",
                variant="0.60",
                role="candidate",
                config=replace(base, impedance_taper=True, taper_strength=0.60),
                notes="over-applied taper stress.",
            ),
        ]
    )
    for pct in (-2.0, -1.0, 1.0, 2.0):
        scale = 1.0 + pct / 100.0
        tests.append(
            TestCase(
                test_id=f"mat_speed_{pct:+.1f}pct".replace(".", "p"),
                bucket="material_load",
                subtest="propagation_speed_perturbation",
                variant=f"{pct:+.1f}pct",
                role="candidate",
                config=replace(base, phase_velocity_4_m_s=base.phase_velocity_4_m_s * scale),
                tolerance_kind="propagation_speed",
                tolerance_abs_percent=abs(pct),
                notes=f"propagation speed perturbation {pct:+.1f}%",
            )
        )
    for factor in (0.80, 0.90, 1.10, 1.20):
        tests.append(
            TestCase(
                test_id=f"mat_nonlinear_{factor:.2f}x".replace(".", "p"),
                bucket="material_load",
                subtest="nonlinear_coupling_perturbation",
                variant=f"{factor:.2f}x",
                role="candidate",
                config=replace(
                    base,
                    nonlinear_448=base.nonlinear_448 * factor,
                    nonlinear_4812=base.nonlinear_4812 * factor,
                ),
                notes=f"nonlinear coupling factor {factor:.2f}x",
            )
        )
    add_bucket_controls(tests, "material_load", base)

    for factor in (0.50, 0.75, 1.00, 1.25, 1.50):
        tests.append(
            TestCase(
                test_id=f"drive_amp_{factor:.2f}x".replace(".", "p"),
                bucket="drive_readout",
                subtest="drive_amplitude_sweep",
                variant=f"{factor:.2f}x",
                role="candidate",
                config=replace(base, drive_amplitude=base.drive_amplitude * factor),
                notes=f"drive amplitude factor {factor:.2f}x",
            )
        )
    for pct in (-1.0, -0.5, 0.5, 1.0):
        tests.append(
            TestCase(
                test_id=f"drive_freq_detune_{pct:+.1f}pct".replace(".", "p"),
                bucket="drive_readout",
                subtest="drive_frequency_detune",
                variant=f"{pct:+.1f}pct",
                role="candidate",
                config=replace(
                    base,
                    phase_velocity_4_m_s=base.phase_velocity_4_m_s / (1.0 + pct / 100.0),
                    generated_detuning=0.05 * pct,
                    target_detuning=0.08 * pct,
                ),
                notes=f"40 kHz drive detune proxy {pct:+.1f}%",
            )
        )
    for bandwidth in (150_000.0, 200_000.0, 250_000.0, 500_000.0):
        tests.append(
            TestCase(
                test_id=f"sensor_bandwidth_{int(bandwidth/1000)}khz",
                bucket="drive_readout",
                subtest="sensor_bandwidth_limit",
                variant=f"{int(bandwidth)}hz",
                role="candidate",
                config=base,
                sensor_bandwidth_hz=bandwidth,
                notes=f"sensor bandwidth limit {bandwidth:g} Hz",
            )
        )
    for noise in (0.01, 0.03, 0.05):
        tests.append(
            TestCase(
                test_id=f"sensor_noise_{noise:.2f}".replace(".", "p"),
                bucket="drive_readout",
                subtest="additive_sensor_noise",
                variant=f"{noise:.2f}",
                role="candidate",
                config=base,
                sensor_noise_fraction=noise,
                notes=f"complex tap-projection noise at {noise:.2f} of target amplitude",
            )
        )
    tests.append(
        TestCase(
            test_id="sensor_weak_resonance_artifact_candidate_stress",
            bucket="drive_readout",
            subtest="weak_sensor_resonance_artifact",
            variant="candidate_plus_artifact",
            role="candidate",
            config=base,
            sensor_resonance_artifact=True,
            notes="adds weak coherent sensor resonance to candidate readout projection.",
        )
    )
    add_bucket_controls(tests, "drive_readout", base)
    return tests


def direct_reference_test() -> TestCase:
    return TestCase(
        test_id="direct_reference",
        bucket="reference",
        subtest="direct_40plus80_ceiling",
        variant="nominal",
        role="ceiling_reference",
        config=direct_reference(),
    )


def direct_power_from_result(result: bench.BenchResult) -> float:
    test = direct_reference_test()
    row = base_row(SimContext(test, replace(result, config=test.config)))
    return safe_float(row.get("target_coherent_power_120khz"))


def summarize(rows: List[Dict[str, object]]) -> Dict[str, object]:
    candidates = [row for row in rows if row.get("role") == "candidate"]
    controls = [row for row in rows if row.get("role") == "control"]
    nominal = next((row for row in candidates if row.get("test_id") == "num_nominal"), {})
    numerical = [row for row in candidates if row.get("bucket") == "numerical"]
    tolerance = [row for row in candidates if row.get("bucket") == "tolerance"]
    material = [row for row in candidates if row.get("bucket") == "material_load"]
    sensor = [row for row in candidates if row.get("bucket") == "drive_readout"]
    tolerance_1 = [
        row for row in tolerance
        if safe_float(row.get("tolerance_abs_percent")) > 0.0 and safe_float(row.get("tolerance_abs_percent")) <= 1.0
    ]
    tolerance_2 = [
        row for row in tolerance
        if safe_float(row.get("tolerance_abs_percent")) > 0.0 and safe_float(row.get("tolerance_abs_percent")) <= 2.0
    ]
    pass_rate_1 = sum(str(row.get("row_passed")) == "True" for row in tolerance_1) / max(len(tolerance_1), 1)
    pass_rate_2 = sum(str(row.get("row_passed")) == "True" for row in tolerance_2) / max(len(tolerance_2), 1)
    numerical_pass = all(str(row.get("row_passed")) == "True" for row in numerical)
    controls_dead = all(str(row.get("promotion_category")) == "control_dead" for row in controls)
    sensor_artifact_controls_dead = all(
        str(row.get("promotion_category")) == "control_dead"
        for row in controls
        if "sensor" in str(row.get("name", ""))
    )
    viable_damping_load = any(
        str(row.get("row_passed")) == "True"
        and str(row.get("subtest")) in {"damping_loss_sweep", "absorber_load_sweep"}
        for row in material
    )
    viable_sensor_250 = any(
        str(row.get("row_passed")) == "True"
        and str(row.get("subtest")) == "sensor_bandwidth_limit"
        and safe_float(row.get("sensor_bandwidth_hz")) <= 250_000.0
        for row in sensor
    )
    nominal_pass = str(nominal.get("row_passed")) == "True"
    strict = (
        nominal_pass
        and numerical_pass
        and sensor_artifact_controls_dead
        and controls_dead
        and pass_rate_1 >= 0.80
        and pass_rate_2 >= 0.60
        and viable_damping_load
        and viable_sensor_250
    )
    tolerance_main_failure = nominal_pass and numerical_pass and controls_dead and (pass_rate_1 < 0.80 or pass_rate_2 < 0.60)
    near = (
        not strict
        and controls_dead
        and numerical_pass
        and tolerance_main_failure
        and pass_rate_1 >= 0.50
    )
    if strict:
        label = "acoustic_bench_robust_candidate"
        decision = "build_ready"
        next_step = "physical build of compact acoustic tap prototype"
    elif near:
        label = "acoustic_bench_robust_near_miss"
        decision = "geometry_retiming_before_build"
        next_step = "tighten geometry/manufacturing tolerance or retime the compact guide before build"
    else:
        label = "not_robust"
        decision = "no_go"
        next_step = "route pause or robustness retiming before build"

    first_fail = next((row for row in tolerance if str(row.get("row_passed")) != "True"), {})
    counts: Dict[str, int] = {}
    for row in candidates:
        if str(row.get("row_passed")) == "True":
            continue
        reason = str(row.get("pass_fail_reason", "unknown")).split(";")[0]
        counts[reason] = counts.get(reason, 0) + 1
    dominant_failure = max(counts, key=counts.get) if counts else "none"
    leaking_controls = [row for row in controls if str(row.get("promotion_category")) == "control_leakage"]
    worst_control = max(leaking_controls, key=lambda row: safe_float(row.get("max_control_leakage")), default={})
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "acoustic_412_bench_robustness_validator",
        "strict_pass_label": label,
        "go_no_go_decision": decision,
        "recommended_next_step": next_step,
        "candidate_rows": len(candidates),
        "control_rows": len(controls),
        "nominal_pass": str(nominal_pass),
        "numerical_checks_pass": str(numerical_pass),
        "all_matched_controls_dead": str(controls_dead),
        "sensor_artifact_controls_dead": str(sensor_artifact_controls_dead),
        "tolerance_1pct_pass_rate": pass_rate_1,
        "tolerance_2pct_pass_rate": pass_rate_2,
        "viable_damping_or_load_setting": str(viable_damping_load),
        "viable_sensor_bandwidth_at_or_below_250khz": str(viable_sensor_250),
        "first_tolerance_failure": first_fail.get("test_id", ""),
        "first_tolerance_failure_reason": first_fail.get("pass_fail_reason", ""),
        "dominant_failure_mode": dominant_failure,
        "failure_mode_counts_json": json.dumps(counts, sort_keys=True),
        "leaking_control_count": len(leaking_controls),
        "leaking_control_ids": ",".join(str(row.get("test_id", "")) for row in leaking_controls),
        "worst_control_leakage": worst_control.get("max_control_leakage", ""),
        "worst_control_leakage_id": worst_control.get("test_id", ""),
        "worst_control_leakage_name": worst_control.get("name", ""),
        "nominal_phase_lock_120khz": nominal.get("phase_lock_120khz", ""),
        "nominal_phase_lock_80khz": nominal.get("phase_lock_80khz", ""),
        "nominal_raw_pre_readout_120khz_purity": nominal.get("raw_pre_readout_120khz_purity", ""),
        "nominal_coherent_growth": nominal.get("distributed_120khz_coherent_growth", ""),
        "nominal_object_reference_gain_120khz": nominal.get("object_reference_gain_120khz", ""),
        "nominal_max_control_leakage": nominal.get("max_control_leakage", ""),
        "nominal_pressure_stress_class": nominal.get("pressure_stress_class", ""),
        "manufacturing_tolerance_required": (
            "at least +/-2% practical tolerance passed"
            if pass_rate_2 >= 0.60
            else "requires tighter than +/-2%; see tolerance_matrix.csv"
        ),
    }


def failure_mode_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") == "candidate" and str(row.get("row_passed")) != "True":
            out.append(
                {
                    "row_type": "failure_mode",
                    "test_id": row.get("test_id"),
                    "bucket": row.get("bucket"),
                    "subtest": row.get("subtest"),
                    "variant": row.get("variant"),
                    "pass_fail_reason": row.get("pass_fail_reason"),
                    "phase_lock_120khz": row.get("phase_lock_120khz"),
                    "raw_pre_readout_120khz_purity": row.get("raw_pre_readout_120khz_purity"),
                    "coherent_growth": row.get("distributed_120khz_coherent_growth"),
                    "object_reference_gain_120khz": row.get("object_reference_gain_120khz"),
                    "max_control_leakage": row.get("max_control_leakage"),
                }
            )
    return out


def write_go_no_go(path: Path, agg: Dict[str, object]) -> None:
    lines = [
        "# Acoustic 4->8->12 Bench Robustness Go/No-Go",
        "",
        f"Decision: {agg.get('go_no_go_decision')}.",
        f"Strict label: {agg.get('strict_pass_label')}.",
        f"Next step: {agg.get('recommended_next_step')}.",
        "",
        "## Gate Summary",
        "",
        f"- Nominal pass: {agg.get('nominal_pass')}.",
        f"- Numerical checks pass: {agg.get('numerical_checks_pass')}.",
        f"- All matched controls dead: {agg.get('all_matched_controls_dead')}.",
        f"- Leaking control count: {agg.get('leaking_control_count')}.",
        f"- Worst leaking control: {agg.get('worst_control_leakage_id')} ({agg.get('worst_control_leakage_name')}) at {agg.get('worst_control_leakage')}.",
        f"- Sensor artifact controls dead: {agg.get('sensor_artifact_controls_dead')}.",
        f"- +/-1% tolerance pass rate: {agg.get('tolerance_1pct_pass_rate')}.",
        f"- +/-2% tolerance pass rate: {agg.get('tolerance_2pct_pass_rate')}.",
        f"- Viable damping/load setting: {agg.get('viable_damping_or_load_setting')}.",
        f"- Viable sensor bandwidth <=250 kHz: {agg.get('viable_sensor_bandwidth_at_or_below_250khz')}.",
        "",
        "## Bench Fixture If Green",
        "",
        "- Source-only 40 kHz drive.",
        "- Compact guide: 36 cells, 0.041 m length, about 1.139 mm spacing.",
        "- Broadband taps at input, 1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8, and raw output.",
        "- No direct 80 kHz drive, no direct 120 kHz drive, and no target-frequency injection.",
        "- Sensor bandwidth must include a viable setting at or below 250 kHz.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path, agg: Dict[str, object], rows: List[Dict[str, object]]) -> None:
    failures = failure_mode_rows(rows)
    tolerance_fail = next((row for row in failures if row.get("bucket") == "tolerance"), {})
    numerical_fails = [row for row in failures if row.get("bucket") == "numerical"]
    sensor_fails = [row for row in failures if row.get("bucket") == "drive_readout" and "sensor" in str(row.get("subtest"))]
    control_leaks = [row for row in rows if row.get("role") == "control" and row.get("promotion_category") != "control_dead"]
    lines = [
        "# Acoustic 4->8->12 Bench Robustness Validator",
        "",
        "Frozen-candidate robustness pass for `b007 acoustic_compact_short_guide`. No new discovery sweep or geometry search is performed.",
        "",
        "## Direct Answers",
        "",
        f"- Does frozen b007 survive independent robustness validation? {agg.get('strict_pass_label')}.",
        f"- Which tolerance breaks it first? {tolerance_fail.get('test_id', 'none')} {tolerance_fail.get('pass_fail_reason', '')}.",
        f"- Is the result sensitive to numerical settings? {'yes' if numerical_fails else 'no'}; numerical_checks_pass={agg.get('numerical_checks_pass')} and the dominant issue is {agg.get('dominant_failure_mode')}.",
        f"- Is it sensitive to tap placement? see `tolerance_matrix.csv`; first tolerance failure={agg.get('first_tolerance_failure')}.",
        f"- Is it sensitive to sensor bandwidth or sensor resonance? {'yes' if sensor_fails else 'no'}; viable_sensor_bandwidth_at_or_below_250khz={agg.get('viable_sensor_bandwidth_at_or_below_250khz')}.",
        f"- Do matched controls remain dead? {agg.get('all_matched_controls_dead')}; leaking_controls={', '.join(str(row.get('test_id')) for row in control_leaks) or 'none'}.",
        f"- Worst control leakage: {agg.get('worst_control_leakage_id')} ({agg.get('worst_control_leakage_name')}) at {agg.get('worst_control_leakage')}.",
        f"- Manufacturing tolerance required: {agg.get('manufacturing_tolerance_required')}.",
        f"- Exact bench go/no-go decision: {agg.get('go_no_go_decision')}.",
        f"- Next step: {agg.get('recommended_next_step')}.",
        "",
        "## Nominal Frozen Candidate",
        "",
        f"- 120 kHz lock: {agg.get('nominal_phase_lock_120khz')}.",
        f"- 80 kHz lock: {agg.get('nominal_phase_lock_80khz')}.",
        f"- Raw pre-readout 120 kHz purity: {agg.get('nominal_raw_pre_readout_120khz_purity')}.",
        f"- Coherent growth: {agg.get('nominal_coherent_growth')}.",
        f"- Object/reference gain: {agg.get('nominal_object_reference_gain_120khz')}.",
        f"- Max control leakage: {agg.get('nominal_max_control_leakage')}.",
        "",
        "## Aggregate Gates",
        "",
        f"- +/-1% tolerance pass rate: {agg.get('tolerance_1pct_pass_rate')}.",
        f"- +/-2% tolerance pass rate: {agg.get('tolerance_2pct_pass_rate')}.",
        f"- Viable damping/load setting: {agg.get('viable_damping_or_load_setting')}.",
        f"- Viable sensor bandwidth <=250 kHz: {agg.get('viable_sensor_bandwidth_at_or_below_250khz')}.",
        f"- Dominant failure mode: {agg.get('dominant_failure_mode')} counts={agg.get('failure_mode_counts_json')}.",
        f"- Leaking control ids: {agg.get('leaking_control_ids') or 'none'}.",
        "",
        "## Conservative Rule",
        "",
        "If the final label is not `acoustic_bench_robust_candidate`, do not build directly from b007; retime or pause first.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def simulate_unique_tests(tests: Sequence[TestCase], workers: int) -> Dict[Tuple[object, ...], bench.BenchResult]:
    unique: Dict[Tuple[object, ...], TestCase] = {}
    for test in tests:
        unique.setdefault(simulation_key(test), test)
    if workers <= 1 or len(unique) <= 1:
        return {key: simulate_case(test).result for key, test in unique.items()}

    result_cache: Dict[Tuple[object, ...], bench.BenchResult] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(simulate_for_cache, test) for test in unique.values()]
        for future in as_completed(futures):
            key, result = future.result()
            result_cache[key] = result
    return result_cache


def run(out_dir: Path, workers: int | None = None) -> Dict[str, object]:
    ensure_dir(out_dir)
    tests = build_tests()
    reference_test = direct_reference_test()
    all_sim_tests = [reference_test] + tests
    worker_count = workers if workers is not None else min(8, max(1, (os.cpu_count() or 2) - 1))
    cache = simulate_unique_tests(all_sim_tests, worker_count)
    d_power = direct_power_from_result(cache[simulation_key(reference_test)])
    rows: List[Dict[str, object]] = []
    for test in tests:
        cached = cache[simulation_key(test)]
        ctx = SimContext(test, replace(cached, config=test.config))
        rows.append(base_row(ctx))
    apply_bundle_scores(rows, d_power)
    agg = summarize(rows)
    all_rows = [agg] + rows

    write_csv(out_dir / "robustness_summary.csv", all_rows)
    write_csv(out_dir / "tolerance_matrix.csv", [row for row in rows if row.get("bucket") == "tolerance"])
    write_csv(out_dir / "numerical_sensitivity.csv", [row for row in rows if row.get("bucket") == "numerical"])
    write_csv(out_dir / "sensor_sensitivity.csv", [row for row in rows if row.get("bucket") == "drive_readout"])
    write_csv(out_dir / "matched_controls.csv", [row for row in rows if row.get("role") == "control"])
    write_csv(out_dir / "failure_modes.csv", failure_mode_rows(rows))
    (out_dir / "robustness_summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": agg,
                    "rows": all_rows,
                    "tests": [asdict(test) for test in tests],
                    "direct_reference_target_power": d_power,
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    go = {"aggregate": agg, "fixture": {"cells": 36, "length_m": 0.041, "spacing_m": 0.041 / 36.0, "source_hz": bench.SOURCE_HZ}}
    (out_dir / "build_go_no_go.json").write_text(json.dumps(sanitize(go), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_go_no_go(out_dir / "build_go_no_go.md", agg)
    write_readme(out_dir / "README_ACOUSTIC_412_BENCH_ROBUSTNESS_VALIDATOR.md", agg, rows)
    return {"aggregate": agg, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate robustness of frozen acoustic b007 bench candidate.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel simulation workers; defaults to up to 8.")
    parser.add_argument("--run", action="store_true", help="Run the bounded robustness validator.")
    args = parser.parse_args()
    if not args.run:
        print("Use --run to execute the frozen b007 robustness validator.")
        return
    summary = run(Path(args.out), workers=args.workers)
    agg = summary["aggregate"]
    print(
        json.dumps(
            sanitize(
                {
                    "strict_pass_label": agg.get("strict_pass_label"),
                    "go_no_go_decision": agg.get("go_no_go_decision"),
                    "nominal_pass": agg.get("nominal_pass"),
                    "numerical_checks_pass": agg.get("numerical_checks_pass"),
                    "all_matched_controls_dead": agg.get("all_matched_controls_dead"),
                    "tolerance_1pct_pass_rate": agg.get("tolerance_1pct_pass_rate"),
                    "tolerance_2pct_pass_rate": agg.get("tolerance_2pct_pass_rate"),
                    "recommended_next_step": agg.get("recommended_next_step"),
                    "summary": str(Path(args.out) / "robustness_summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
