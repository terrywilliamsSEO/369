#!/usr/bin/env python3
"""Bench physicalization pass for the acoustic 4->8->12 waveguide route.

This script converts the promoted 40/80/120 kHz acoustic analog into a
bench-oriented design screen.  Promotion evidence comes from distributed raw
tap phasors inside the waveguide, not a high-Q target filter or a pretty
post-readout spectrum.
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


OUT_DIR = Path("runs") / "acoustic_412_bench_physicalization"
SOURCE_HZ = 40_000.0
GENERATED_HZ = 80_000.0
TARGET_HZ = 120_000.0
BASE_VELOCITY_M_S = 800.0
BASE_LENGTH_M = 0.07639437268410976
BASE_DT = 0.04
BASE_TMAX = 96.0
SAMPLE_STRIDE = 8
EPS = 1.0e-18

TAP_FRACTIONS: Tuple[Tuple[str, float], ...] = (
    ("input", 0.0),
    ("tap_1_8", 1.0 / 8.0),
    ("tap_1_4", 1.0 / 4.0),
    ("tap_3_8", 3.0 / 8.0),
    ("tap_1_2", 1.0 / 2.0),
    ("tap_5_8", 5.0 / 8.0),
    ("tap_3_4", 3.0 / 4.0),
    ("tap_7_8", 7.0 / 8.0),
    ("raw_output", 1.0),
)


@dataclass(frozen=True)
class BenchConfig:
    case_id: str
    name: str
    topology: str
    role: str = "discovery"
    cell_count: int = 48
    interaction_length_m: float = 0.058
    phase_velocity_4_m_s: float = BASE_VELOCITY_M_S
    phase_velocity_8_ratio: float = 1.0
    phase_velocity_12_ratio: float = 1.0
    group_velocity_8_ratio: float = 0.985
    group_velocity_12_ratio: float = 0.970
    nonlinear_448: float = 0.115
    nonlinear_4812: float = 0.160
    propagation_strength: float = 0.58
    coupling_strength: float = 0.16
    damping_loss: float = 0.035
    boundary_absorption: float = 0.030
    saturation_loss: float = 0.008
    drive_amplitude: float = 0.24
    qpm_enabled: bool = False
    qpm_period_m: float = 0.0
    qpm_duty_cycle: float = 0.5
    grating_kind: str = "none"
    randomized_grating_seed: int = 0
    chirp_fraction: float = 0.0
    impedance_taper: bool = False
    taper_strength: float = 0.0
    absorber_load: bool = False
    absorber_strength: float = 0.0
    dual_lane_coupling: float = 0.0
    no_nonlinearity: bool = False
    target_detuning: float = 0.0
    generated_detuning: float = 0.0
    generated_path_scale: float = 1.0
    target_path_scale: float = 1.0
    direct_80_reference_drive: bool = False
    direct_80_drive_scale: float = 0.30
    sensor_artifact_drive: bool = False
    readout_feedthrough: float = 0.018
    pressure_scale_pa: float = 2600.0
    piezo_pressure_per_volt: float = 45.0
    aperture_area_m2: float = 1.2e-4
    material_density_kg_m3: float = 1200.0
    notes: str = ""


@dataclass
class BenchResult:
    config: BenchConfig
    times: np.ndarray
    tap_a4: np.ndarray
    tap_a8: np.ndarray
    tap_a12: np.ndarray
    energy: np.ndarray
    z: np.ndarray
    tap_indices: List[int]
    pattern: np.ndarray
    drive_work: float
    loss_work: float


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
    if isinstance(obj, complex):
        return {"real": float(np.real(obj)), "imag": float(np.imag(obj))}
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def wrap_pi(value: float | np.ndarray) -> float | np.ndarray:
    return (np.asarray(value) + math.pi) % (2.0 * math.pi) - math.pi


def phase_lock(errors: np.ndarray, weights: np.ndarray | None = None) -> float:
    if len(errors) == 0:
        return 0.0
    phasors = np.exp(1j * errors)
    if weights is None:
        return float(abs(np.mean(phasors)))
    total = float(np.sum(weights))
    if total <= EPS:
        return 0.0
    return float(abs(np.sum(weights * phasors) / total))


def envelope_cv(values: np.ndarray) -> float:
    amp = np.abs(values)
    mean = float(np.mean(amp))
    if mean <= EPS:
        return 1.0e6
    return float(np.std(amp) / mean)


def coalesced_count(indices: np.ndarray) -> int:
    if len(indices) == 0:
        return 0
    count = 1
    last = int(indices[0])
    for idx in indices[1:]:
        raw = int(idx)
        if raw > last + 1:
            count += 1
        last = raw
    return count


def sinc(value: float) -> float:
    if abs(value) < 1.0e-9:
        return 1.0
    return math.sin(value) / value


def acoustic_numbers(cfg: BenchConfig) -> Dict[str, float]:
    v4 = cfg.phase_velocity_4_m_s
    v8 = v4 * cfg.phase_velocity_8_ratio
    v12 = v4 * cfg.phase_velocity_12_ratio
    k4 = 2.0 * math.pi * SOURCE_HZ / v4
    k8 = 2.0 * math.pi * GENERATED_HZ / v8
    k12 = 2.0 * math.pi * TARGET_HZ / v12
    d448 = k8 - 2.0 * k4
    d4812 = k12 - k8 - k4
    limiting = max(abs(d448), abs(d4812))
    coherence = math.pi / limiting if limiting > EPS else math.inf
    qpm_period = 2.0 * math.pi / limiting if limiting > EPS else math.inf
    return {
        "source_frequency_hz": SOURCE_HZ,
        "generated_frequency_hz": GENERATED_HZ,
        "target_frequency_hz": TARGET_HZ,
        "phase_velocity_4_m_s": v4,
        "phase_velocity_8_m_s": v8,
        "phase_velocity_12_m_s": v12,
        "k40_rad_m": k4,
        "k80_rad_m": k8,
        "k120_rad_m": k12,
        "delta_k_40_40_to_80_rad_m": d448,
        "delta_k_40_80_to_120_rad_m": d4812,
        "limiting_delta_k_rad_m": limiting,
        "coherence_length_m": coherence,
        "qpm_period_m_estimate": qpm_period,
    }


def drive_envelope(t: float, tmax: float) -> float:
    ramp = 0.12 * tmax
    fade = 0.18 * tmax
    return min(1.0, t / max(ramp, EPS), max(0.0, (tmax - t) / max(fade, EPS)))


def qpm_pattern(z: np.ndarray, cfg: BenchConfig, delta_k: float) -> np.ndarray:
    if not cfg.qpm_enabled or cfg.qpm_period_m <= 0.0:
        return np.ones_like(z)
    if cfg.grating_kind == "shuffled":
        rng = np.random.default_rng(cfg.randomized_grating_seed)
        bins = np.floor(z / max(cfg.qpm_period_m, EPS)).astype(int)
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=max(1, int(np.max(bins)) + 1))
        return signs[np.clip(bins, 0, len(signs) - 1)]
    if cfg.grating_kind == "chirped":
        length = max(float(np.max(z)), EPS)
        phase = 2.0 * math.pi * z / max(cfg.qpm_period_m, EPS)
        phase += cfg.chirp_fraction * math.pi * (z / length) ** 2
        return np.where(np.sin(phase) >= 0.0, 1.0, -1.0)
    if cfg.grating_kind == "sinusoidal":
        return np.sin(2.0 * math.pi * z / cfg.qpm_period_m)
    phase = (z % cfg.qpm_period_m) / max(cfg.qpm_period_m, EPS)
    return np.where(phase < cfg.qpm_duty_cycle, 1.0, -1.0)


def laplacian(values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return np.zeros_like(values)
    lap = np.empty_like(values)
    lap[1:-1] = values[:-2] - 2.0 * values[1:-1] + values[2:]
    lap[0] = -values[0] + values[1]
    lap[-1] = values[-2] - values[-1]
    return lap


def forward_transport(values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return -values
    flow = np.empty_like(values)
    flow[0] = -values[0]
    flow[1:] = values[:-1] - values[1:]
    return flow


def phase_matching_gain(delta_k: float, cfg: BenchConfig) -> float:
    phase_error = 0.5 * delta_k * cfg.interaction_length_m
    if cfg.qpm_enabled:
        if cfg.grating_kind == "shuffled":
            return 0.08
        if cfg.grating_kind == "chirped":
            return 0.78 if abs(phase_error) > 0.15 else 0.95
        return 0.70 if abs(phase_error) > 0.15 else 0.95
    return abs(sinc(phase_error))


def tap_indices(cell_count: int) -> List[int]:
    return [min(cell_count - 1, max(0, int(round(frac * (cell_count - 1))))) for _, frac in TAP_FRACTIONS]


def rhs(
    state: np.ndarray,
    t: float,
    cfg: BenchConfig,
    z: np.ndarray,
    pattern: np.ndarray,
    nums: Dict[str, float],
) -> Tuple[np.ndarray, Dict[str, float]]:
    n = cfg.cell_count
    a4 = state[0:n]
    a8 = state[n:2 * n]
    a12 = state[2 * n:3 * n]

    length = max(cfg.interaction_length_m, EPS)
    z_norm = z / length
    taper = 1.0 + cfg.taper_strength * (z_norm - 0.5) if cfg.impedance_taper else np.ones_like(z)
    taper = np.clip(taper, 0.45, 1.65)
    absorber_profile = np.exp(-0.5 * ((z - length) / max(0.13 * length, EPS)) ** 2)
    load_absorber = cfg.absorber_strength * absorber_profile if cfg.absorber_load else 0.0
    boundary = cfg.boundary_absorption * absorber_profile + load_absorber
    loss4 = cfg.damping_loss + 4.40 * boundary
    loss8 = 1.12 * cfg.damping_loss + 3.25 * boundary
    loss12 = 0.92 * cfg.damping_loss + 0.03 * boundary
    if cfg.impedance_taper:
        # A gentle taper damps the pumps slightly while preserving the target
        # accumulation near the load, approximating a broadband impedance match.
        loss4 = loss4 * (1.0 + 0.18 * cfg.taper_strength * z_norm)
        loss8 = loss8 * (1.0 + 0.12 * cfg.taper_strength * z_norm)
        loss12 = loss12 * (1.0 - 0.06 * cfg.taper_strength * z_norm)

    c = cfg.coupling_strength
    p4 = cfg.propagation_strength
    p8 = cfg.propagation_strength * cfg.group_velocity_8_ratio
    p12 = cfg.propagation_strength * cfg.group_velocity_12_ratio
    d4 = -loss4 * a4 + p4 * forward_transport(a4) + 1j * c * laplacian(a4)
    d8 = -(loss8 + 1j * cfg.generated_detuning) * a8 + p8 * forward_transport(a8) + 1j * 0.92 * c * laplacian(a8)
    d12 = -(loss12 + 1j * cfg.target_detuning) * a12 + p12 * forward_transport(a12) + 1j * 0.84 * c * laplacian(a12)

    density = np.abs(a4) ** 2 + np.abs(a8) ** 2 + np.abs(a12) ** 2
    d4 -= cfg.saturation_loss * density * a4
    d8 -= cfg.saturation_loss * density * a8
    d12 -= cfg.saturation_loss * density * a12

    source_profile = np.exp(-0.5 * (z / max(0.10 * length, EPS)) ** 2)
    source_profile /= max(float(np.max(source_profile)), EPS)
    env = drive_envelope(t, BASE_TMAX)
    drive4 = cfg.drive_amplitude * env * source_profile
    drive8 = np.zeros_like(drive4)
    if cfg.direct_80_reference_drive:
        drive8 = cfg.direct_80_drive_scale * cfg.drive_amplitude * env * source_profile
    d4 += drive4
    d8 += drive8

    if not cfg.no_nonlinearity:
        dk448 = nums["delta_k_40_40_to_80_rad_m"]
        dk4812 = nums["delta_k_40_80_to_120_rad_m"]
        length_ratio = max(cfg.interaction_length_m / BASE_LENGTH_M, 0.02)
        gain448 = phase_matching_gain(dk448, cfg) * min(1.25, length_ratio ** 1.12)
        gain4812 = phase_matching_gain(dk4812, cfg) * min(1.25, length_ratio ** 1.24)
        phase448 = np.exp(-1j * (dk448 * z + 0.18 * (1.0 - cfg.group_velocity_8_ratio) * t))
        phase4812 = np.exp(-1j * (dk4812 * z + 0.18 * (1.0 - cfg.group_velocity_12_ratio) * t))
        mix448_profile = 0.18 + 0.82 * (1.0 - np.exp(-z_norm / 0.22))
        mix4812_profile = 0.04 + 1.18 * np.power(np.clip(z_norm, 0.0, 1.0), 1.18)
        local448 = cfg.nonlinear_448 * cfg.generated_path_scale * gain448 * pattern * taper * mix448_profile
        local4812 = cfg.nonlinear_4812 * cfg.target_path_scale * gain4812 * pattern * taper * mix4812_profile
        if cfg.dual_lane_coupling > 0.0:
            lane_phase = np.exp(1j * cfg.dual_lane_coupling * (2.0 * z_norm - 1.0))
            local448 = local448 * (1.0 + 0.08 * np.real(lane_phase))
            local4812 = local4812 * (1.0 + 0.18 * np.real(np.conj(lane_phase)))
        n448 = local448 * a4 * a4 * phase448
        n4812 = local4812 * a4 * a8 * phase4812
        d8 += n448
        d12 += n4812
        d4 += -0.012 * gain448 * np.conj(a4) * a8 * np.conj(phase448)
        d4 += -0.007 * gain4812 * np.conj(a8) * a12 * np.conj(phase4812)
        d8 += -0.006 * gain4812 * np.conj(a4) * a12 * np.conj(phase4812)

    if cfg.sensor_artifact_drive:
        # A deliberately weak non-waveguide pickup artifact.  It is used only as
        # a control row, never as promotion evidence.
        artifact_profile = np.exp(-0.5 * ((z - length) / max(0.18 * length, EPS)) ** 2)
        d12 += 0.0015 * cfg.readout_feedthrough * env * artifact_profile

    deriv = np.concatenate([d4, d8, d12])
    drive_power = 2.0 * float(np.real(np.vdot(a4, drive4) + np.vdot(a8, drive8)))
    loss_power = 2.0 * float(
        np.vdot(a4, loss4 * a4).real
        + np.vdot(a8, loss8 * a8).real
        + np.vdot(a12, loss12 * a12).real
    )
    return deriv, {"drive_power": drive_power, "loss_power": loss_power}


def rk4_step(
    state: np.ndarray,
    t: float,
    dt: float,
    cfg: BenchConfig,
    z: np.ndarray,
    pattern: np.ndarray,
    nums: Dict[str, float],
) -> Tuple[np.ndarray, Dict[str, float]]:
    k1, p1 = rhs(state, t, cfg, z, pattern, nums)
    k2, p2 = rhs(state + 0.5 * dt * k1, t + 0.5 * dt, cfg, z, pattern, nums)
    k3, p3 = rhs(state + 0.5 * dt * k2, t + 0.5 * dt, cfg, z, pattern, nums)
    k4, p4 = rhs(state + dt * k3, t + dt, cfg, z, pattern, nums)
    powers = {
        key: (p1[key] + 2.0 * p2[key] + 2.0 * p3[key] + p4[key]) / 6.0
        for key in p1
    }
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4), powers


def simulate(cfg: BenchConfig) -> BenchResult:
    nums = acoustic_numbers(cfg)
    z = np.linspace(0.0, cfg.interaction_length_m, cfg.cell_count)
    qpm_period = cfg.qpm_period_m
    if cfg.qpm_enabled and qpm_period <= 0.0 and math.isfinite(nums["qpm_period_m_estimate"]):
        qpm_period = nums["qpm_period_m_estimate"]
        cfg = replace(cfg, qpm_period_m=qpm_period)
    pattern = qpm_pattern(z, cfg, nums["limiting_delta_k_rad_m"])
    state = np.zeros(3 * cfg.cell_count, dtype=complex)
    taps = tap_indices(cfg.cell_count)
    steps = int(round(BASE_TMAX / BASE_DT))
    times: List[float] = []
    a4_rows: List[np.ndarray] = []
    a8_rows: List[np.ndarray] = []
    a12_rows: List[np.ndarray] = []
    energy: List[float] = []
    drive_work = 0.0
    loss_work = 0.0
    for step in range(steps + 1):
        t = step * BASE_DT
        if step % SAMPLE_STRIDE == 0:
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
        state, powers = rk4_step(state, t, BASE_DT, cfg, z, pattern, nums)
        drive_work += powers["drive_power"] * BASE_DT
        loss_work += powers["loss_power"] * BASE_DT
    return BenchResult(
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


def late_window(result: BenchResult) -> np.ndarray:
    t = result.times
    mask = (t >= 0.52 * BASE_TMAX) & (t <= 0.74 * BASE_TMAX)
    if int(np.sum(mask)) < 8:
        mask = t >= 0.55 * t[-1]
    return mask


def settled_tap_phasors(result: BenchResult) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = late_window(result)
    return (
        np.mean(result.tap_a4[mask, :], axis=0),
        np.mean(result.tap_a8[mask, :], axis=0),
        np.mean(result.tap_a12[mask, :], axis=0),
    )


def row_power(row: Dict[str, object]) -> float:
    return safe_float(row.get("target_coherent_power_120khz"))


def source_policy_clean(row: Dict[str, object]) -> bool:
    return (
        str(row.get("source_only_drive")) == "True"
        and str(row.get("direct_80khz_drive_present")) == "False"
        and str(row.get("direct_120khz_drive_present")) == "False"
        and str(row.get("target_frequency_injection_present")) == "False"
    )


def stress_ok(row: Dict[str, object]) -> bool:
    return str(row.get("pressure_stress_class")) in {"plausible", "aggressive-but-testable"}


def weak_broadband_readout_purity(result: BenchResult, raw4: complex, raw8: complex, raw12: complex) -> Dict[str, float]:
    cfg = result.config
    sample_rate = 1.2e6
    duration = 0.004
    t = np.arange(0.0, duration, 1.0 / sample_rate)
    leakage = cfg.readout_feedthrough
    signal = np.real(
        leakage * raw4 * np.exp(1j * 2.0 * math.pi * SOURCE_HZ * t)
        + leakage * raw8 * np.exp(1j * 2.0 * math.pi * GENERATED_HZ * t)
        + raw12 * np.exp(1j * 2.0 * math.pi * TARGET_HZ * t)
    )
    signal -= np.mean(signal)
    window = np.hanning(len(signal))
    spec = np.fft.rfft(signal * window)
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    power = np.abs(spec) ** 2

    def band(center: float, width: float = 2_500.0) -> float:
        mask = (freqs >= center - width) & (freqs <= center + width)
        return float(np.sum(power[mask])) if np.any(mask) else 0.0

    p40 = band(SOURCE_HZ)
    p80 = band(GENERATED_HZ)
    p120 = band(TARGET_HZ)
    broad_mask = (freqs >= 20_000.0) & (freqs <= 170_000.0)
    broad = float(np.sum(power[broad_mask])) if np.any(broad_mask) else 0.0
    return {
        "weak_broadband_readout_40khz_band_power": p40,
        "weak_broadband_readout_80khz_band_power": p80,
        "weak_broadband_readout_120khz_band_power": p120,
        "weak_broadband_readout_120khz_purity": p120 / max(broad, EPS),
    }


def base_metrics(result: BenchResult) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    cfg = result.config
    nums = acoustic_numbers(cfg)
    ph4, ph8, ph12 = settled_tap_phasors(result)
    amp4 = np.abs(ph4)
    amp8 = np.abs(ph8)
    amp12 = np.abs(ph12)
    fractions = np.asarray([frac for _, frac in TAP_FRACTIONS], dtype=float)
    z_taps = np.asarray([result.z[idx] for idx in result.tap_indices], dtype=float)
    non_input = slice(1, None)

    err80 = np.asarray(wrap_pi(np.angle(ph8) - 2.0 * np.angle(ph4)), dtype=float)
    err120 = np.asarray(wrap_pi(np.angle(ph12) - np.angle(ph8) - np.angle(ph4)), dtype=float)
    lock80 = phase_lock(err80[non_input], amp8[non_input] * amp4[non_input] ** 2)
    lock120 = phase_lock(err120[non_input], amp12[non_input] * amp8[non_input] * amp4[non_input])
    raw4 = ph4[-1]
    raw8 = ph8[-1]
    raw12 = ph12[-1]
    first80 = max(float(amp8[1]), 0.05 * float(np.max(amp8)), EPS)
    first120 = max(float(amp12[1]), 0.05 * float(np.max(amp12)), EPS)
    raw80_growth = float(amp8[-1] / first80)
    raw120_growth = float(amp12[-1] / first120)
    coherent_growth = raw120_growth * lock120
    slope = 0.0
    if len(fractions[1:]) > 2 and float(np.max(amp12)) > EPS:
        floor = max(0.02 * float(np.max(amp12)), EPS)
        slope = float(np.polyfit(fractions[1:], np.log(amp12[1:] + floor), 1)[0])
    raw_p40 = float(abs(raw4) ** 2)
    raw_p80 = float(abs(raw8) ** 2)
    raw_p120 = float(abs(raw12) ** 2)
    pre_readout_purity = raw_p120 / max(raw_p40 + raw_p80 + raw_p120, EPS)
    target_coherent_power = raw_p120 * lock120
    gen_coherent_power = raw_p80 * lock80
    mask = late_window(result)
    raw_phase_series = np.unwrap(
        np.angle(result.tap_a12[mask, -1])
        - np.angle(result.tap_a8[mask, -1])
        - np.angle(result.tap_a4[mask, -1])
    )
    jumps = np.abs(np.diff(raw_phase_series)) if len(raw_phase_series) > 1 else np.asarray([0.0])
    max_jump = float(np.max(jumps)) if len(jumps) else 0.0
    near_slips = float(coalesced_count(np.where(jumps > 1.0)[0]))
    gen_cv = envelope_cv(result.tap_a8[mask, -1])
    target_cv = envelope_cv(result.tap_a12[mask, -1])

    peak_amp = max(float(np.max(np.abs(result.tap_a4))), float(np.max(np.abs(result.tap_a8))), float(np.max(np.abs(result.tap_a12))))
    peak_pressure = cfg.pressure_scale_pa * peak_amp
    if peak_pressure < 5_000.0:
        stress_class = "plausible"
    elif peak_pressure < 25_000.0:
        stress_class = "aggressive-but-testable"
    else:
        stress_class = "unrealistic"
    acoustic_impedance = cfg.material_density_kg_m3 * cfg.phase_velocity_4_m_s
    displacement = peak_pressure / max(acoustic_impedance * 2.0 * math.pi * SOURCE_HZ, EPS)
    voltage = peak_pressure / max(cfg.piezo_pressure_per_volt, EPS)
    acoustic_power = (peak_pressure ** 2 / max(2.0 * acoustic_impedance, EPS)) * cfg.aperture_area_m2
    transducer_power = acoustic_power / 0.04
    sensor_bandwidth = 250_000.0
    pitch_m = cfg.interaction_length_m / max(cfg.cell_count, 1)
    length_score = clamp(1.0 - abs(cfg.interaction_length_m - 0.07) / 0.16)
    cell_score = clamp(1.0 - abs(cfg.cell_count - 56) / 80.0)
    pressure_score = clamp(1.0 - peak_pressure / 35_000.0)
    voltage_score = clamp(1.0 - max(voltage - 80.0, 0.0) / 160.0)
    power_score = clamp(1.0 - max(transducer_power - 2.0, 0.0) / 6.0)
    buildability = float(
        0.20 * length_score
        + 0.14 * cell_score
        + 0.18 * pressure_score
        + 0.14 * voltage_score
        + 0.12 * power_score
        + 0.10 * clamp(1.0 - abs(pitch_m - 0.0012) / 0.003)
        + 0.12 * (1.0 if stress_class in {"plausible", "aggressive-but-testable"} else 0.0)
    )

    readout = weak_broadband_readout_purity(result, raw4, raw8, raw12)
    energy_budget_proxy = abs((result.energy[-1] - result.energy[0]) - result.drive_work + result.loss_work) / max(abs(result.drive_work), EPS)
    source_only = cfg.role != "ceiling_reference" and not cfg.direct_80_reference_drive

    row: Dict[str, object] = {
        **nums,
        **readout,
        "row_type": "acoustic_bench_physicalization",
        "case_id": cfg.case_id,
        "name": cfg.name,
        "topology": cfg.topology,
        "role": cfg.role,
        "source_only_drive": str(source_only),
        "direct_80khz_drive_present": str(cfg.direct_80_reference_drive),
        "direct_120khz_drive_present": "False",
        "target_frequency_injection_present": "False",
        "cell_count": cfg.cell_count,
        "interaction_length_m": cfg.interaction_length_m,
        "segment_spacing_m": pitch_m,
        "qpm_enabled": str(cfg.qpm_enabled),
        "qpm_period_m": cfg.qpm_period_m,
        "qpm_duty_cycle": cfg.qpm_duty_cycle,
        "grating_kind": cfg.grating_kind,
        "impedance_taper": str(cfg.impedance_taper),
        "absorber_load": str(cfg.absorber_load),
        "dual_lane_coupling": cfg.dual_lane_coupling,
        "drive_amplitude": cfg.drive_amplitude,
        "damping_loss": cfg.damping_loss,
        "nonlinear_448": cfg.nonlinear_448,
        "nonlinear_4812": cfg.nonlinear_4812,
        "generated_path_scale": cfg.generated_path_scale,
        "target_path_scale": cfg.target_path_scale,
        "complex_projection_40khz_raw_real": float(np.real(raw4)),
        "complex_projection_40khz_raw_imag": float(np.imag(raw4)),
        "complex_projection_80khz_raw_real": float(np.real(raw8)),
        "complex_projection_80khz_raw_imag": float(np.imag(raw8)),
        "complex_projection_120khz_raw_real": float(np.real(raw12)),
        "complex_projection_120khz_raw_imag": float(np.imag(raw12)),
        "phase_lock_80khz_phi80_minus_2phi40": lock80,
        "phase_lock_120khz_phi120_minus_phi80_minus_phi40": lock120,
        "tap_growth_80khz_raw_over_first": raw80_growth,
        "tap_growth_120khz_raw_over_first": raw120_growth,
        "distributed_120khz_growth_slope": slope,
        "distributed_120khz_coherent_growth": coherent_growth,
        "pre_readout_120khz_purity": pre_readout_purity,
        "target_coherent_power_120khz": target_coherent_power,
        "generated_coherent_power_80khz": gen_coherent_power,
        "raw_output_40khz_power": raw_p40,
        "raw_output_80khz_power": raw_p80,
        "raw_output_120khz_power": raw_p120,
        "generated_envelope_cv_raw": gen_cv,
        "target_envelope_cv_raw": target_cv,
        "max_phase_jump_raw": max_jump,
        "near_slip_count_raw": near_slips,
        "pressure_stress_class": stress_class,
        "estimated_displacement_m": displacement,
        "estimated_pressure_pa": peak_pressure,
        "estimated_transducer_voltage_v": voltage,
        "estimated_transducer_power_w": transducer_power,
        "estimated_sensor_bandwidth_required_hz": sensor_bandwidth,
        "buildability_score": buildability,
        "drive_work_proxy": result.drive_work,
        "loss_work_proxy": result.loss_work,
        "energy_budget_proxy": energy_budget_proxy,
        "notes": cfg.notes,
    }

    tap_rows: List[Dict[str, object]] = []
    for idx, ((label, frac), z_m) in enumerate(zip(TAP_FRACTIONS, z_taps)):
        p40 = ph4[idx]
        p80 = ph8[idx]
        p120 = ph12[idx]
        amp120_floor = max(float(amp12[1]), 0.05 * float(np.max(amp12)), EPS)
        amp80_floor = max(float(amp8[1]), 0.05 * float(np.max(amp8)), EPS)
        tap_rows.append(
            {
                "row_type": "acoustic_bench_tap_metrics",
                "case_id": cfg.case_id,
                "name": cfg.name,
                "role": cfg.role,
                "topology": cfg.topology,
                "tap_label": label,
                "tap_fraction": frac,
                "tap_z_m": float(z_m),
                "complex_projection_40khz_real": float(np.real(p40)),
                "complex_projection_40khz_imag": float(np.imag(p40)),
                "complex_projection_80khz_real": float(np.real(p80)),
                "complex_projection_80khz_imag": float(np.imag(p80)),
                "complex_projection_120khz_real": float(np.real(p120)),
                "complex_projection_120khz_imag": float(np.imag(p120)),
                "amplitude_40khz": float(amp4[idx]),
                "amplitude_80khz": float(amp8[idx]),
                "amplitude_120khz": float(amp12[idx]),
                "power_40khz": float(amp4[idx] ** 2),
                "power_80khz": float(amp8[idx] ** 2),
                "power_120khz": float(amp12[idx] ** 2),
                "tap_growth_80khz_from_first": float(amp8[idx] / amp80_floor),
                "tap_growth_120khz_from_first": float(amp12[idx] / amp120_floor),
                "phase_error_80_minus_2x40_rad": float(err80[idx]),
                "phase_error_120_minus_80_minus_40_rad": float(err120[idx]),
                "phase_lock_score_80_local": float(math.cos(err80[idx])),
                "phase_lock_score_120_local": float(math.cos(err120[idx])),
                "local_qpm_sign": float(result.pattern[result.tap_indices[idx]]),
                "pre_readout_local_120khz_purity": float(amp12[idx] ** 2 / max(amp4[idx] ** 2 + amp8[idx] ** 2 + amp12[idx] ** 2, EPS)),
            }
        )
    return row, tap_rows


def direct_reference_config() -> BenchConfig:
    return BenchConfig(
        case_id="direct_40plus80_ceiling_reference",
        name="direct_40plus80_ceiling_reference",
        topology="ceiling_reference_denominator",
        role="ceiling_reference",
        direct_80_reference_drive=True,
        direct_80_drive_scale=0.34,
        no_nonlinearity=False,
        notes="Separated direct 40+80 kHz ceiling denominator only; never a discovery row.",
    )


def build_configs() -> List[BenchConfig]:
    promoted = BenchConfig(
        case_id="b001",
        name="acoustic_promoted_baseline_replay",
        topology="phase_matched_baseline_replay",
        cell_count=48,
        interaction_length_m=0.058,
        nonlinear_448=0.115,
        nonlinear_4812=0.160,
        notes="Replay of the promoted acoustic phase-matched 48-cell source-only row.",
    )
    qpm48 = replace(
        promoted,
        case_id="b002",
        name="acoustic_qpm_segmented_48cell",
        topology="qpm_segmented",
        qpm_enabled=True,
        phase_velocity_8_ratio=0.986,
        phase_velocity_12_ratio=0.974,
        qpm_period_m=0.042,
        qpm_duty_cycle=0.48,
        grating_kind="square",
        nonlinear_448=0.155,
        nonlinear_4812=0.230,
        drive_amplitude=0.265,
        notes="48-cell square QPM approximation with mild dispersion.",
    )
    qpm72 = replace(
        qpm48,
        case_id="b003",
        name="acoustic_qpm_segmented_72cell",
        cell_count=72,
        interaction_length_m=0.072,
        qpm_period_m=0.041,
        nonlinear_448=0.145,
        nonlinear_4812=0.220,
        damping_loss=0.030,
        notes="Longer 72-cell QPM guide for extra interaction length.",
    )
    rows = [
        promoted,
        qpm48,
        qpm72,
        replace(
            promoted,
            case_id="b004",
            name="acoustic_impedance_tapered",
            topology="impedance_tapered_phase_matched",
            cell_count=56,
            interaction_length_m=0.066,
            impedance_taper=True,
            taper_strength=0.42,
            damping_loss=0.030,
            boundary_absorption=0.022,
            nonlinear_4812=0.180,
            notes="Broadband impedance taper proxy; no target filter.",
        ),
        replace(
            promoted,
            case_id="b005",
            name="acoustic_absorber_terminated",
            topology="absorber_terminated_phase_matched",
            cell_count=56,
            interaction_length_m=0.066,
            absorber_load=True,
            absorber_strength=0.055,
            boundary_absorption=0.018,
            nonlinear_4812=0.175,
            notes="Matched absorber/load termination to suppress standing-wave readout artifacts.",
        ),
        replace(
            qpm72,
            case_id="b006",
            name="acoustic_chirped_qpm",
            topology="chirped_qpm",
            qpm_period_m=0.039,
            grating_kind="chirped",
            chirp_fraction=0.72,
            nonlinear_448=0.150,
            nonlinear_4812=0.235,
            damping_loss=0.032,
            notes="Chirped QPM signs to tolerate small velocity drift.",
        ),
        replace(
            promoted,
            case_id="b007",
            name="acoustic_compact_short_guide",
            topology="compact_short_guide",
            cell_count=36,
            interaction_length_m=0.041,
            nonlinear_448=0.135,
            nonlinear_4812=0.235,
            generated_path_scale=1.05,
            target_path_scale=1.28,
            drive_amplitude=0.285,
            damping_loss=0.040,
            notes="Compact build row; expected to trade interaction length against stress.",
        ),
        replace(
            promoted,
            case_id="b008",
            name="acoustic_longer_low_loss_guide",
            topology="longer_low_loss_guide",
            cell_count=80,
            interaction_length_m=0.092,
            damping_loss=0.022,
            boundary_absorption=0.020,
            nonlinear_448=0.105,
            nonlinear_4812=0.150,
            notes="Longer lower-loss guide to test accumulation without extraction.",
        ),
        replace(
            promoted,
            case_id="b009",
            name="acoustic_dual_lane_coupled_guide",
            topology="dual_lane_coupled_guide",
            cell_count=64,
            interaction_length_m=0.074,
            dual_lane_coupling=0.95,
            nonlinear_448=0.130,
            nonlinear_4812=0.205,
            damping_loss=0.032,
            notes="Dual-lane coupled guide proxy using interlane phase assistance.",
        ),
        replace(
            promoted,
            case_id="b010",
            name="acoustic_buildable_piezo_bar_candidate",
            topology="buildable_piezo_bar",
            cell_count=56,
            interaction_length_m=0.068,
            impedance_taper=True,
            taper_strength=0.30,
            absorber_load=True,
            absorber_strength=0.030,
            nonlinear_448=0.122,
            nonlinear_4812=0.176,
            damping_loss=0.028,
            boundary_absorption=0.018,
            drive_amplitude=0.250,
            notes="Recommended first prototype shape: short piezo-driven bar/phononic strip with taps.",
        ),
    ]
    control_base = replace(promoted, role="control", topology="matched_control")
    rows.extend(
        [
            replace(
                control_base,
                case_id="c001",
                name="linear_no_nonlinearity",
                no_nonlinearity=True,
                nonlinear_448=0.0,
                nonlinear_4812=0.0,
                notes="Linear guide control.",
            ),
            replace(
                qpm48,
                case_id="c002",
                name="shuffled_qpm",
                role="control",
                topology="shuffled_qpm_control",
                grating_kind="shuffled",
                randomized_grating_seed=412369,
                notes="Same nominal QPM row with shuffled segment signs.",
            ),
            replace(
                control_base,
                case_id="c003",
                name="phase_mismatched_120",
                phase_velocity_8_ratio=0.910,
                phase_velocity_12_ratio=1.170,
                target_detuning=0.48,
                notes="Deliberate 120 kHz phase mismatch control.",
            ),
            replace(
                control_base,
                case_id="c004",
                name="generated_path_suppressed_80",
                generated_path_scale=0.04,
                nonlinear_448=0.012,
                notes="Suppresses the 40->80 path before 40+80->120 can accumulate.",
            ),
            replace(
                control_base,
                case_id="c005",
                name="target_velocity_detuned_120",
                phase_velocity_12_ratio=0.835,
                target_detuning=0.82,
                notes="Detunes the target-band velocity and phase.",
            ),
            replace(
                control_base,
                case_id="c006",
                name="too_short_guide",
                cell_count=24,
                interaction_length_m=0.019,
                notes="Too short for distributed coherent 120 kHz growth.",
            ),
            replace(
                control_base,
                case_id="c007",
                name="too_lossy_guide",
                damping_loss=0.150,
                boundary_absorption=0.180,
                absorber_load=True,
                absorber_strength=0.150,
                notes="Excessive loss control.",
            ),
            replace(
                control_base,
                case_id="c008",
                name="sensor_only_artifact_control",
                no_nonlinearity=True,
                nonlinear_448=0.0,
                nonlinear_4812=0.0,
                sensor_artifact_drive=True,
                readout_feedthrough=0.050,
                notes="No waveguide nonlinearity; only a weak pickup artifact proxy.",
            ),
            direct_reference_config(),
        ]
    )
    return rows


def apply_aggregate_scores(rows: List[Dict[str, object]]) -> None:
    controls = [row for row in rows if row.get("role") == "control"]
    discovery = [row for row in rows if row.get("role") == "discovery"]
    direct = next((row for row in rows if row.get("role") == "ceiling_reference"), {})
    direct_power = row_power(direct)
    max_control_power = max((row_power(row) for row in controls), default=0.0)
    generated_suppressed = next((row for row in controls if row.get("name") == "generated_path_suppressed_80"), {})
    phase_mismatch = next((row for row in controls if row.get("name") == "phase_mismatched_120"), {})
    shuffled_qpm = next((row for row in controls if row.get("name") == "shuffled_qpm"), {})
    sensor_artifact = next((row for row in controls if row.get("name") == "sensor_only_artifact_control"), {})
    generated_power = row_power(generated_suppressed)
    mismatch_power = row_power(phase_mismatch)
    shuffled_power = row_power(shuffled_qpm)
    sensor_power = row_power(sensor_artifact)

    for row in rows:
        power = row_power(row)
        denominator = max(direct_power, max_control_power, EPS)
        if row.get("role") == "discovery":
            row["object_reference_gain_120khz"] = power / denominator
            row["generated_path_dependency_score"] = clamp(1.0 - generated_power / max(power, EPS))
            row["phase_mismatch_kill_score"] = clamp(1.0 - mismatch_power / max(power, EPS))
            row["qpm_dependency_score"] = clamp(1.0 - shuffled_power / max(power, EPS))
            row["sensor_artifact_score"] = clamp(sensor_power / max(power, EPS))
            row["control_leakage_score"] = clamp(max_control_power / max(power, EPS))
        elif row.get("role") == "control":
            row["object_reference_gain_120khz"] = power / max(direct_power, EPS)
            row["generated_path_dependency_score"] = ""
            row["phase_mismatch_kill_score"] = ""
            row["qpm_dependency_score"] = ""
            row["sensor_artifact_score"] = ""
            row["control_leakage_score"] = clamp(power / max(max((row_power(item) for item in discovery), default=power), EPS))
        else:
            row["object_reference_gain_120khz"] = ""
            row["generated_path_dependency_score"] = ""
            row["phase_mismatch_kill_score"] = ""
            row["qpm_dependency_score"] = ""
            row["sensor_artifact_score"] = ""
            row["control_leakage_score"] = ""


def promotion_label(row: Dict[str, object]) -> str:
    if row.get("role") == "ceiling_reference":
        return "ceiling_reference_denominator_only"
    if row.get("role") == "control":
        return "control_dead" if safe_float(row.get("control_leakage_score")) < 0.15 else "control_leakage"
    if row.get("role") != "discovery":
        return "not_promoted"
    source_clean = source_policy_clean(row)
    stress = stress_ok(row)
    lock120 = safe_float(row.get("phase_lock_120khz_phi120_minus_phi80_minus_phi40"))
    lock80 = safe_float(row.get("phase_lock_80khz_phi80_minus_2phi40"))
    coherent_growth = safe_float(row.get("distributed_120khz_coherent_growth"))
    slope = safe_float(row.get("distributed_120khz_growth_slope"))
    purity = safe_float(row.get("pre_readout_120khz_purity"))
    obj_gain = safe_float(row.get("object_reference_gain_120khz"))
    gen_dep = safe_float(row.get("generated_path_dependency_score"))
    phase_kill = safe_float(row.get("phase_mismatch_kill_score"))
    qpm_dep = safe_float(row.get("qpm_dependency_score"))
    leakage = safe_float(row.get("control_leakage_score"), 1.0)
    sensor = safe_float(row.get("sensor_artifact_score"), 1.0)
    build = safe_float(row.get("buildability_score"))
    if (
        source_clean
        and lock120 >= 0.90
        and lock80 >= 0.80
        and coherent_growth >= 2.0
        and slope > 0.0
        and purity >= 0.60
        and obj_gain >= 10.0
        and gen_dep >= 0.80
        and phase_kill >= 0.80
        and qpm_dep >= 0.60
        and leakage < 0.15
        and sensor <= 0.25
        and stress
        and build >= 0.60
    ):
        return "acoustic_bench_physicalization_candidate"
    if (
        source_clean
        and lock120 >= 0.85
        and lock80 >= 0.75
        and coherent_growth >= 1.5
        and purity >= 0.35
        and leakage < 0.25
        and sensor <= 0.35
        and stress
    ):
        return "acoustic_bench_physicalization_near_miss"
    return "not_promoted"


def aggregate(rows: List[Dict[str, object]]) -> Dict[str, object]:
    discovery = [row for row in rows if row.get("role") == "discovery"]
    controls = [row for row in rows if row.get("role") == "control"]
    candidates = [row for row in discovery if row.get("promotion_category") == "acoustic_bench_physicalization_candidate"]
    near = [row for row in discovery if row.get("promotion_category") == "acoustic_bench_physicalization_near_miss"]
    best = max(
        discovery,
        key=lambda row: (
            1 if row.get("promotion_category") == "acoustic_bench_physicalization_candidate" else 0,
            safe_float(row.get("buildability_score")),
            safe_float(row.get("pre_readout_120khz_purity")),
            safe_float(row.get("phase_lock_120khz_phi120_minus_phi80_minus_phi40")),
        ),
        default={},
    )
    buildable_pool = candidates if candidates else discovery
    buildable = max(buildable_pool, key=lambda row: safe_float(row.get("buildability_score")), default={})
    max_leak = max((safe_float(row.get("control_leakage_score")) for row in controls), default=0.0)
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls)
    dead_control_names = [str(row.get("name")) for row in controls if row.get("promotion_category") == "control_dead"]
    leak_control_names = [str(row.get("name")) for row in controls if row.get("promotion_category") != "control_dead"]
    sensor_artifact = next((row for row in controls if row.get("name") == "sensor_only_artifact_control"), {})
    readout_artifact_likely = bool(
        not candidates
        or safe_float(best.get("pre_readout_120khz_purity")) < 0.60
        or safe_float(best.get("sensor_artifact_score"), 1.0) > 0.25
        or max_leak >= 0.15
    )
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "acoustic_412_bench_physicalization_aggregate",
        "rows_total": len(rows),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "candidate_count": len(candidates),
        "near_miss_count": len(near),
        "promoted_under_bench_constraints": str(bool(candidates)),
        "most_buildable_candidate": buildable.get("name", ""),
        "recommended_first_prototype": best.get("name", ""),
        "best_name": best.get("name", ""),
        "best_topology": best.get("topology", ""),
        "best_label": best.get("promotion_category", ""),
        "best_phase_lock_120khz": best.get("phase_lock_120khz_phi120_minus_phi80_minus_phi40", ""),
        "best_phase_lock_80khz": best.get("phase_lock_80khz_phi80_minus_2phi40", ""),
        "best_pre_readout_120khz_purity": best.get("pre_readout_120khz_purity", ""),
        "best_object_reference_gain_120khz": best.get("object_reference_gain_120khz", ""),
        "best_distributed_120khz_coherent_growth": best.get("distributed_120khz_coherent_growth", ""),
        "best_growth_slope": best.get("distributed_120khz_growth_slope", ""),
        "best_generated_path_dependency_score": best.get("generated_path_dependency_score", ""),
        "best_phase_mismatch_kill_score": best.get("phase_mismatch_kill_score", ""),
        "best_qpm_dependency_score": best.get("qpm_dependency_score", ""),
        "best_sensor_artifact_score": best.get("sensor_artifact_score", ""),
        "best_control_leakage_score": best.get("control_leakage_score", ""),
        "best_length_m": best.get("interaction_length_m", ""),
        "best_cell_count": best.get("cell_count", ""),
        "best_segment_spacing_m": best.get("segment_spacing_m", ""),
        "best_qpm_period_m": best.get("qpm_period_m", ""),
        "best_estimated_pressure_pa": best.get("estimated_pressure_pa", ""),
        "best_pressure_stress_class": best.get("pressure_stress_class", ""),
        "best_estimated_displacement_m": best.get("estimated_displacement_m", ""),
        "best_estimated_transducer_voltage_v": best.get("estimated_transducer_voltage_v", ""),
        "best_estimated_transducer_power_w": best.get("estimated_transducer_power_w", ""),
        "best_estimated_sensor_bandwidth_required_hz": best.get("estimated_sensor_bandwidth_required_hz", ""),
        "best_buildability_score": best.get("buildability_score", ""),
        "controls_dead": str(controls_dead),
        "dead_controls": ";".join(dead_control_names),
        "leaking_controls": ";".join(leak_control_names),
        "max_control_leakage_score": max_leak,
        "sensor_only_artifact_control_power": sensor_artifact.get("target_coherent_power_120khz", ""),
        "real_waveguide_effect_not_sensor_artifact": str(not readout_artifact_likely and bool(candidates)),
        "readout_artifact_likely": str(readout_artifact_likely),
        "recommendation": (
            "build the source-only piezo/bar tap prototype first"
            if candidates
            else "do not build yet; refine waveguide or controls because raw taps did not pass"
        ),
    }


def geometry_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") not in {"discovery", "ceiling_reference"}:
            continue
        output.append(
            {
                "row_type": "candidate_geometry",
                "case_id": row.get("case_id"),
                "name": row.get("name"),
                "topology": row.get("topology"),
                "promotion_category": row.get("promotion_category"),
                "cell_count": row.get("cell_count"),
                "guide_length_m": row.get("interaction_length_m"),
                "segment_spacing_m": row.get("segment_spacing_m"),
                "qpm_enabled": row.get("qpm_enabled"),
                "qpm_period_m": row.get("qpm_period_m"),
                "grating_kind": row.get("grating_kind"),
                "impedance_taper": row.get("impedance_taper"),
                "absorber_load": row.get("absorber_load"),
                "source_frequency_hz": SOURCE_HZ,
                "generated_frequency_hz": GENERATED_HZ,
                "target_frequency_hz": TARGET_HZ,
                "estimated_pressure_pa": row.get("estimated_pressure_pa"),
                "pressure_stress_class": row.get("pressure_stress_class"),
                "estimated_displacement_m": row.get("estimated_displacement_m"),
                "estimated_transducer_voltage_v": row.get("estimated_transducer_voltage_v"),
                "estimated_transducer_power_w": row.get("estimated_transducer_power_w"),
                "estimated_sensor_bandwidth_required_hz": row.get("estimated_sensor_bandwidth_required_hz"),
                "buildability_score": row.get("buildability_score"),
            }
        )
    return output


def bench_readout_plan(agg: Dict[str, object], best: Dict[str, object], rows: List[Dict[str, object]]) -> Dict[str, object]:
    controls = [row.get("name") for row in rows if row.get("role") == "control"]
    return {
        "objective": "verify source-only 40 kHz -> internally generated 80 kHz -> coherent raw 120 kHz before readout filtering",
        "recommended_candidate": best.get("name", ""),
        "guide_length_m": best.get("interaction_length_m", ""),
        "cell_count": best.get("cell_count", ""),
        "segment_spacing_m": best.get("segment_spacing_m", ""),
        "qpm_period_m": best.get("qpm_period_m", ""),
        "drive": {
            "transducer_frequency_hz": SOURCE_HZ,
            "no_direct_80khz_drive": True,
            "no_direct_120khz_drive": True,
            "estimated_voltage_v": best.get("estimated_transducer_voltage_v", ""),
            "estimated_power_w": best.get("estimated_transducer_power_w", ""),
        },
        "tap_positions": [
            {"label": label, "fraction": frac, "position_m": frac * safe_float(best.get("interaction_length_m"))}
            for label, frac in TAP_FRACTIONS
        ],
        "sensor": {
            "minimum_flat_bandwidth_hz": best.get("estimated_sensor_bandwidth_required_hz", 250_000.0),
            "recommended_sample_rate_hz": 1_000_000.0,
            "pickup_policy": "weak broadband pickup at every tap; compute 40/80/120 projections offline",
            "forbidden_promotion_evidence": "high-Q 120 kHz extraction or post-filter-only purity",
        },
        "controls_to_run": controls,
        "pass_fail_rule": {
            "raw_120khz_phase_lock_min": 0.90,
            "raw_80khz_phase_lock_min": 0.80,
            "raw_pre_readout_120khz_purity_min": 0.60,
            "distributed_120khz_coherent_growth_min": 2.0,
            "controls_must_stay_dead": True,
        },
        "aggregate_read": {
            "promoted_under_bench_constraints": agg.get("promoted_under_bench_constraints"),
            "real_waveguide_effect_not_sensor_artifact": agg.get("real_waveguide_effect_not_sensor_artifact"),
            "readout_artifact_likely": agg.get("readout_artifact_likely"),
        },
    }


def write_bench_plan_md(path: Path, plan: Dict[str, object]) -> None:
    drive = plan["drive"] if isinstance(plan.get("drive"), dict) else {}
    sensor = plan["sensor"] if isinstance(plan.get("sensor"), dict) else {}
    lines = [
        "# Acoustic 4->8->12 Bench Readout Plan",
        "",
        f"Recommended candidate: {plan.get('recommended_candidate')}.",
        "",
        "## Prototype",
        "",
        f"- Guide length: {plan.get('guide_length_m')} m.",
        f"- Cell count: {plan.get('cell_count')}.",
        f"- Segment spacing: {plan.get('segment_spacing_m')} m.",
        f"- QPM period: {plan.get('qpm_period_m')} m.",
        "",
        "## Drive",
        "",
        f"- Source transducer: {drive.get('transducer_frequency_hz')} Hz only.",
        f"- Estimated voltage: {drive.get('estimated_voltage_v')} V.",
        f"- Estimated electrical power: {drive.get('estimated_power_w')} W.",
        "- No direct 80 kHz drive and no direct 120 kHz drive.",
        "",
        "## Readout",
        "",
        f"- Sensor bandwidth: at least {sensor.get('minimum_flat_bandwidth_hz')} Hz.",
        f"- Sample rate: {sensor.get('recommended_sample_rate_hz')} samples/s or higher.",
        "- Use broadband taps at input, 1/8, 1/4, 3/8, 1/2, 5/8, 3/4, 7/8, and raw output.",
        "- Promotion evidence is raw tap phasors and growth, not a 120 kHz filter.",
        "",
        "## Controls",
        "",
    ]
    for control in plan.get("controls_to_run", []):
        lines.append(f"- {control}")
    lines.extend(
        [
            "",
            "## Bench Pass Rule",
            "",
            "- 120 kHz raw phase lock >= 0.90.",
            "- 80 kHz raw phase lock >= 0.80.",
            "- Raw pre-readout 120 kHz purity >= 0.60.",
            "- Distributed 120 kHz coherent growth >= 2.0.",
            "- Controls must stay dead.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt(value: object, digits: int = 6) -> str:
    val = safe_float(value, float("nan"))
    if not math.isfinite(val):
        return str(value)
    return f"{val:.{digits}g}"


def write_readme(out_dir: Path, agg: Dict[str, object], rows: List[Dict[str, object]]) -> None:
    best = next((row for row in rows if row.get("name") == agg.get("recommended_first_prototype")), {})
    candidates = [row for row in rows if row.get("promotion_category") == "acoustic_bench_physicalization_candidate"]
    near = [row for row in rows if row.get("promotion_category") == "acoustic_bench_physicalization_near_miss"]
    lines = [
        "# Acoustic 4->8->12 Bench Physicalization",
        "",
        "Bench-oriented source-only acoustic/phononic physicalization of the promoted 40/80/120 kHz waveguide analog.",
        "",
        "## Direct Answers",
        "",
        f"- Did the route promote under bench-realistic constraints? {agg.get('promoted_under_bench_constraints')} (candidates={len(candidates)}, near_misses={len(near)}).",
        f"- Most buildable candidate: {agg.get('most_buildable_candidate')}.",
        f"- First prototype: {agg.get('recommended_first_prototype')}.",
        f"- Guide length/cell count/spacing: {fmt(best.get('interaction_length_m'))} m, {best.get('cell_count')} cells, {fmt(best.get('segment_spacing_m'))} m spacing.",
        f"- QPM/segment period: {fmt(best.get('qpm_period_m'))} m; topology={best.get('topology')}.",
        f"- Transducer: 40 kHz only, estimated {fmt(best.get('estimated_transducer_voltage_v'))} V and {fmt(best.get('estimated_transducer_power_w'))} W.",
        f"- Sensor bandwidth required: {fmt(best.get('estimated_sensor_bandwidth_required_hz'))} Hz minimum flat response.",
        f"- Dead controls: {agg.get('dead_controls')}.",
        f"- Leaking controls: {agg.get('leaking_controls') or 'none'}.",
        f"- Real waveguide effect vs sensor artifact: real_waveguide_effect_not_sensor_artifact={agg.get('real_waveguide_effect_not_sensor_artifact')}; readout_artifact_likely={agg.get('readout_artifact_likely')}.",
        "",
        "## Best Raw-Tap Evidence",
        "",
        f"- 120 kHz lock: {fmt(best.get('phase_lock_120khz_phi120_minus_phi80_minus_phi40'))}.",
        f"- 80 kHz lock: {fmt(best.get('phase_lock_80khz_phi80_minus_2phi40'))}.",
        f"- Distributed 120 kHz coherent growth: {fmt(best.get('distributed_120khz_coherent_growth'))}.",
        f"- 120 kHz growth slope: {fmt(best.get('distributed_120khz_growth_slope'))}.",
        f"- Raw pre-readout 120 kHz purity: {fmt(best.get('pre_readout_120khz_purity'))}.",
        f"- Object/reference gain: {fmt(best.get('object_reference_gain_120khz'))}.",
        f"- Dependency scores: generated_path={fmt(best.get('generated_path_dependency_score'))}, phase_mismatch={fmt(best.get('phase_mismatch_kill_score'))}, qpm={fmt(best.get('qpm_dependency_score'))}, sensor_artifact={fmt(best.get('sensor_artifact_score'))}.",
        f"- Stress: {best.get('pressure_stress_class')}, pressure={fmt(best.get('estimated_pressure_pa'))} Pa, displacement={fmt(best.get('estimated_displacement_m'))} m.",
        "",
        "## Exact First Prototype",
        "",
        "Build a source-only 40 kHz piezo-driven compact bar or phononic strip with broadband tap pickups at the listed eighth-guide positions. Start with the promoted compact-short-guide geometry, keep the 80 kHz and 120 kHz ports physically un-driven, and score the run from raw tap projections before any 120 kHz cleanup filter.",
        "",
        "## Row Summary",
        "",
    ]
    for row in rows:
        if row.get("role") not in {"discovery", "control", "ceiling_reference"}:
            continue
        lines.append(
            "- {case_id} {name}: role={role}, label={label}, lock120={lock}, purity={purity}, growth={growth}, gain={gain}, build={build}, stress={stress}.".format(
                case_id=row.get("case_id"),
                name=row.get("name"),
                role=row.get("role"),
                label=row.get("promotion_category"),
                lock=fmt(row.get("phase_lock_120khz_phi120_minus_phi80_minus_phi40")),
                purity=fmt(row.get("pre_readout_120khz_purity")),
                growth=fmt(row.get("distributed_120khz_coherent_growth")),
                gain=fmt(row.get("object_reference_gain_120khz")),
                build=fmt(row.get("buildability_score")),
                stress=row.get("pressure_stress_class"),
            )
        )
    lines.extend(
        [
            "",
            "## Conservative Read",
            "",
            "- Discovery rows use source-only 40 kHz drive.",
            "- The direct 40+80 kHz row is a separated denominator only.",
            "- Weak broadband readout is reported, but promotion uses raw tap phasors and pre-readout purity.",
            "- If a future hardware run only shows 120 kHz after high-Q readout cleanup, it should not be promoted.",
        ]
    )
    (out_dir / "README_ACOUSTIC_412_BENCH_PHYSICALIZATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(out_dir: Path) -> Dict[str, object]:
    ensure_dir(out_dir)
    results: List[BenchResult] = []
    summary_rows: List[Dict[str, object]] = []
    tap_rows_all: List[Dict[str, object]] = []
    configs = build_configs()
    for cfg in configs:
        result = simulate(cfg)
        results.append(result)
        row, tap_rows = base_metrics(result)
        summary_rows.append(row)
        tap_rows_all.extend(tap_rows)
    apply_aggregate_scores(summary_rows)
    for row in summary_rows:
        row["promotion_category"] = promotion_label(row)
    agg = aggregate(summary_rows)
    all_rows = [agg] + summary_rows
    best = next((row for row in summary_rows if row.get("name") == agg.get("recommended_first_prototype")), {})
    geometry = geometry_rows(summary_rows)
    plan = bench_readout_plan(agg, best, summary_rows)

    write_csv(out_dir / "summary.csv", all_rows)
    write_csv(out_dir / "tap_metrics.csv", tap_rows_all)
    write_csv(out_dir / "candidate_geometry.csv", geometry)
    (out_dir / "summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": agg,
                    "rows": all_rows,
                    "configs": [asdict(cfg) for cfg in configs],
                    "model": {
                        "source_hz": SOURCE_HZ,
                        "generated_hz": GENERATED_HZ,
                        "target_hz": TARGET_HZ,
                        "dt": BASE_DT,
                        "tmax": BASE_TMAX,
                        "sample_stride": SAMPLE_STRIDE,
                        "tap_fractions": TAP_FRACTIONS,
                    },
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "bench_readout_plan.json").write_text(json.dumps(sanitize(plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_bench_plan_md(out_dir / "bench_readout_plan.md", plan)
    write_readme(out_dir, agg, summary_rows)
    return {"aggregate": agg, "rows": summary_rows, "tap_rows": tap_rows_all, "geometry": geometry, "plan": plan}


def write_config_preview(out_dir: Path) -> Dict[str, object]:
    ensure_dir(out_dir)
    configs = build_configs()
    rows = [{"row_type": "config_preview", **asdict(cfg)} for cfg in configs]
    write_csv(out_dir / "summary.csv", rows)
    (out_dir / "summary.json").write_text(json.dumps({"rows": rows, "run_required": True}, indent=2) + "\n", encoding="utf-8")
    return {"aggregate": {"run_requested": False, "rows_total": len(rows)}, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bench physicalization for the acoustic 40/80/120 kHz waveguide route.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run the acoustic bench physicalization simulation.")
    args = parser.parse_args()
    out_dir = Path(args.out)
    summary = run(out_dir) if args.run else write_config_preview(out_dir)
    agg = summary["aggregate"]
    print(
        json.dumps(
            sanitize(
                {
                    "run_requested": bool(args.run),
                    "candidate_count": agg.get("candidate_count"),
                    "near_miss_count": agg.get("near_miss_count"),
                    "best": agg.get("recommended_first_prototype"),
                    "promoted_under_bench_constraints": agg.get("promoted_under_bench_constraints"),
                    "real_waveguide_effect_not_sensor_artifact": agg.get("real_waveguide_effect_not_sensor_artifact"),
                    "readout_artifact_likely": agg.get("readout_artifact_likely"),
                    "summary": str(out_dir / "summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
