#!/usr/bin/env python3
"""Acoustic/phononic 4->8->12 waveguide analog.

This script tests a low-frequency distributed acoustic analog of the validated
4->8->12 bridge.  It uses a 1D complex-envelope chain at 40/80/120 kHz with
explicit acoustic wave numbers, phase mismatch, QPM signs, nonlinear local
stiffness, loss, boundary absorption, and source-only drive rules.
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


OUT_DIR = Path("runs") / "acoustic_waveguide_412"
SOURCE_HZ = 40_000.0
GENERATED_HZ = 80_000.0
TARGET_HZ = 120_000.0
BASE_VELOCITY_M_S = 800.0
BASE_LENGTH_M = 0.07639437268410976
BASE_DT = 0.04
BASE_TMAX = 96.0
SAMPLE_STRIDE = 8
EPS = 1e-18


@dataclass(frozen=True)
class AcousticConfig:
    case_id: str
    name: str
    topology: str
    role: str = "discovery"
    cell_count: int = 64
    interaction_length_m: float = BASE_LENGTH_M
    phase_velocity_4_m_s: float = BASE_VELOCITY_M_S
    phase_velocity_8_ratio: float = 1.0
    phase_velocity_12_ratio: float = 1.0
    group_velocity_8_ratio: float = 0.985
    group_velocity_12_ratio: float = 0.970
    nonlinear_448: float = 0.105
    nonlinear_4812: float = 0.145
    propagation_strength: float = 0.58
    coupling_strength: float = 0.16
    damping_loss: float = 0.035
    boundary_absorption: float = 0.030
    saturation_loss: float = 0.008
    drive_amplitude: float = 0.24
    direct_80_reference_drive: bool = False
    direct_80_drive_scale: float = 0.30
    no_nonlinearity: bool = False
    target_detuning: float = 0.0
    generated_detuning: float = 0.0
    qpm_enabled: bool = False
    qpm_period_m: float = 0.0
    qpm_duty_cycle: float = 0.5
    grating_kind: str = "none"
    randomized_grating_seed: int = 0
    readout_feedthrough: float = 0.015
    pressure_scale_pa: float = 2600.0
    shuffled_frequency: bool = False
    notes: str = ""


@dataclass
class AcousticResult:
    config: AcousticConfig
    times: np.ndarray
    a4: np.ndarray
    a8: np.ndarray
    a12: np.ndarray
    energy: np.ndarray
    drive_work: float
    loss_work: float
    z: np.ndarray
    pattern: np.ndarray


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


def coalesced_count(indices: np.ndarray) -> int:
    if len(indices) == 0:
        return 0
    count = 1
    last = int(indices[0])
    for idx in indices[1:]:
        if int(idx) > last + 1:
            count += 1
        last = int(idx)
    return count


def qpm_pattern(z: np.ndarray, cfg: AcousticConfig, delta_k: float) -> np.ndarray:
    if not cfg.qpm_enabled or cfg.qpm_period_m <= 0.0:
        return np.ones_like(z)
    if cfg.grating_kind == "randomized":
        rng = np.random.default_rng(cfg.randomized_grating_seed)
        bins = np.floor(z / max(cfg.qpm_period_m, EPS)).astype(int)
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=max(1, int(np.max(bins)) + 1))
        return signs[np.clip(bins, 0, len(signs) - 1)]
    if cfg.grating_kind == "sinusoidal":
        return np.sin(2.0 * math.pi * z / cfg.qpm_period_m)
    phase = (z % cfg.qpm_period_m) / cfg.qpm_period_m
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


def acoustic_numbers(cfg: AcousticConfig) -> Dict[str, float]:
    f4, f8, f12 = SOURCE_HZ, GENERATED_HZ, TARGET_HZ
    if cfg.shuffled_frequency:
        f8, f12 = TARGET_HZ, GENERATED_HZ
    v4 = cfg.phase_velocity_4_m_s
    v8 = v4 * cfg.phase_velocity_8_ratio
    v12 = v4 * cfg.phase_velocity_12_ratio
    k4 = 2.0 * math.pi * f4 / v4
    k8 = 2.0 * math.pi * f8 / v8
    k12 = 2.0 * math.pi * f12 / v12
    d448 = k8 - 2.0 * k4
    d4812 = k12 - k8 - k4
    limiting = max(abs(d448), abs(d4812))
    coherence = math.pi / limiting if limiting > EPS else math.inf
    qpm_period = 2.0 * math.pi / limiting if limiting > EPS else math.inf
    required = 24.0 / max(k4, EPS)
    return {
        "f4_hz": f4,
        "f8_hz": f8,
        "f12_hz": f12,
        "v4_m_s": v4,
        "v8_m_s": v8,
        "v12_m_s": v12,
        "k4_rad_m": k4,
        "k8_rad_m": k8,
        "k12_rad_m": k12,
        "delta_k_448_rad_m": d448,
        "delta_k_4812_rad_m": d4812,
        "limiting_delta_k_rad_m": limiting,
        "coherence_length_m": coherence,
        "qpm_period_m": qpm_period,
        "estimated_required_interaction_length_m": required,
    }


def drive_envelope(t: float, tmax: float) -> float:
    ramp = 0.12 * tmax
    fade = 0.18 * tmax
    return min(1.0, t / max(ramp, EPS), max(0.0, (tmax - t) / max(fade, EPS)))


def sinc(value: float) -> float:
    if abs(value) < 1.0e-9:
        return 1.0
    return math.sin(value) / value


def phase_matching_gain(delta_k: float, cfg: AcousticConfig) -> float:
    phase_error = 0.5 * delta_k * cfg.interaction_length_m
    if cfg.qpm_enabled:
        if cfg.grating_kind == "randomized":
            return 0.12
        return 0.64 if abs(phase_error) > 0.15 else 1.0
    return abs(sinc(phase_error))


def rhs(
    state: np.ndarray,
    t: float,
    cfg: AcousticConfig,
    z: np.ndarray,
    pattern: np.ndarray,
    nums: Dict[str, float],
) -> Tuple[np.ndarray, Dict[str, float]]:
    n = cfg.cell_count
    a4 = state[0:n]
    a8 = state[n:2 * n]
    a12 = state[2 * n:3 * n]
    loss = cfg.damping_loss
    c = cfg.coupling_strength
    absorber = np.exp(-0.5 * ((z - cfg.interaction_length_m) / max(0.12 * cfg.interaction_length_m, EPS)) ** 2)
    absorber *= cfg.boundary_absorption

    p4 = cfg.propagation_strength
    p8 = cfg.propagation_strength * cfg.group_velocity_8_ratio
    p12 = cfg.propagation_strength * cfg.group_velocity_12_ratio
    d4 = -(loss + absorber) * a4 + p4 * forward_transport(a4) + 1j * c * laplacian(a4)
    d8 = (
        -(1.08 * loss + 1.1 * absorber + 1j * cfg.generated_detuning) * a8
        + p8 * forward_transport(a8)
        + 1j * 0.92 * c * laplacian(a8)
    )
    d12 = (
        -(1.16 * loss + 1.2 * absorber + 1j * cfg.target_detuning) * a12
        + p12 * forward_transport(a12)
        + 1j * 0.84 * c * laplacian(a12)
    )

    density = np.abs(a4) ** 2 + np.abs(a8) ** 2 + np.abs(a12) ** 2
    d4 -= cfg.saturation_loss * density * a4
    d8 -= cfg.saturation_loss * density * a8
    d12 -= cfg.saturation_loss * density * a12

    source_profile = np.exp(-0.5 * (z / max(0.10 * cfg.interaction_length_m, EPS)) ** 2)
    source_profile /= max(float(np.max(source_profile)), EPS)
    env = drive_envelope(t, BASE_TMAX)
    drive4 = cfg.drive_amplitude * env * source_profile
    drive8 = np.zeros_like(drive4)
    if cfg.direct_80_reference_drive:
        drive8 = cfg.direct_80_drive_scale * cfg.drive_amplitude * env * source_profile
    d4 += drive4
    d8 += drive8

    if not cfg.no_nonlinearity:
        dk448 = nums["delta_k_448_rad_m"]
        dk4812 = nums["delta_k_4812_rad_m"]
        length_gain = min(1.20, cfg.interaction_length_m / BASE_LENGTH_M)
        gain448 = phase_matching_gain(dk448, cfg) * length_gain
        gain4812 = phase_matching_gain(dk4812, cfg) * length_gain
        phase448 = np.exp(-1j * (dk448 * z + 0.18 * (1.0 - cfg.group_velocity_8_ratio) * t))
        phase4812 = np.exp(-1j * (dk4812 * z + 0.18 * (1.0 - cfg.group_velocity_12_ratio) * t))
        n448 = cfg.nonlinear_448 * gain448 * pattern * a4 * a4 * phase448
        n4812 = cfg.nonlinear_4812 * gain4812 * pattern * a4 * a8 * phase4812
        d8 += n448
        d12 += n4812
        d4 += -0.012 * gain448 * np.conj(a4) * a8 * np.conj(phase448)
        d4 += -0.007 * gain4812 * np.conj(a8) * a12 * np.conj(phase4812)
        d8 += -0.006 * gain4812 * np.conj(a4) * a12 * np.conj(phase4812)

    deriv = np.concatenate([d4, d8, d12])
    drive_power = 2.0 * float(np.real(np.vdot(a4, drive4) + np.vdot(a8, drive8)))
    loss_power = 2.0 * float(
        np.vdot(a4, (loss + absorber) * a4).real
        + np.vdot(a8, (1.08 * loss + 1.1 * absorber) * a8).real
        + np.vdot(a12, (1.16 * loss + 1.2 * absorber) * a12).real
    )
    return deriv, {"drive_power": drive_power, "loss_power": loss_power}


def rk4_step(
    state: np.ndarray,
    t: float,
    dt: float,
    cfg: AcousticConfig,
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


def simulate(cfg: AcousticConfig) -> AcousticResult:
    nums = acoustic_numbers(cfg)
    z = np.linspace(0.0, cfg.interaction_length_m, cfg.cell_count)
    qpm_period = cfg.qpm_period_m
    if cfg.qpm_enabled and qpm_period <= 0.0 and math.isfinite(nums["qpm_period_m"]):
        qpm_period = nums["qpm_period_m"]
        cfg = replace(cfg, qpm_period_m=qpm_period)
    pattern = qpm_pattern(z, cfg, nums["limiting_delta_k_rad_m"])
    state = np.zeros(3 * cfg.cell_count, dtype=complex)
    steps = int(round(BASE_TMAX / BASE_DT))
    times: List[float] = []
    a4_obs: List[complex] = []
    a8_obs: List[complex] = []
    a12_obs: List[complex] = []
    energies: List[float] = []
    drive_work = 0.0
    loss_work = 0.0
    out_idx = cfg.cell_count - 1
    for step in range(steps + 1):
        t = step * BASE_DT
        if step % SAMPLE_STRIDE == 0:
            a4 = state[0:cfg.cell_count]
            a8 = state[cfg.cell_count:2 * cfg.cell_count]
            a12 = state[2 * cfg.cell_count:3 * cfg.cell_count]
            times.append(t)
            a4_obs.append(a4[out_idx])
            a8_obs.append(a8[out_idx])
            a12_obs.append(a12[out_idx])
            energies.append(float(np.vdot(state, state).real))
        if step == steps:
            break
        state, powers = rk4_step(state, t, BASE_DT, cfg, z, pattern, nums)
        drive_work += powers["drive_power"] * BASE_DT
        loss_work += powers["loss_power"] * BASE_DT
    return AcousticResult(
        config=cfg,
        times=np.asarray(times),
        a4=np.asarray(a4_obs),
        a8=np.asarray(a8_obs),
        a12=np.asarray(a12_obs),
        energy=np.asarray(energies),
        drive_work=drive_work,
        loss_work=loss_work,
        z=z,
        pattern=pattern,
    )


def envelope_cv(values: np.ndarray) -> float:
    amp = np.abs(values)
    mean = float(np.mean(amp))
    if mean <= EPS:
        return 1.0e6
    return float(np.std(amp) / mean)


def phase_lock(phases: np.ndarray, weights: np.ndarray | None = None) -> float:
    if len(phases) == 0:
        return 0.0
    if weights is None:
        return float(abs(np.mean(np.exp(1j * phases))))
    weights = np.asarray(weights, dtype=float)
    total = float(np.sum(weights))
    if total <= EPS:
        return 0.0
    return float(abs(np.sum(weights * np.exp(1j * phases)) / total))


def signal_fft_metrics(result: AcousticResult) -> Dict[str, float]:
    cfg = result.config
    # Synthetic readout over 4 ms at the final envelope level.  This estimates
    # what a narrowband acoustic pickup would see at the guide output.
    sample_rate = 1.2e6
    duration = 0.004
    t = np.arange(0.0, duration, 1.0 / sample_rate)
    trim = max(1, int(0.62 * len(result.a4)))
    stop = max(trim + 1, int(0.80 * len(result.a4)))
    a4 = np.mean(result.a4[trim:stop])
    a8 = np.mean(result.a8[trim:stop])
    a12 = np.mean(result.a12[trim:stop])
    leakage = cfg.readout_feedthrough
    pressure = np.real(
        leakage * a4 * np.exp(1j * 2.0 * math.pi * SOURCE_HZ * t)
        + leakage * a8 * np.exp(1j * 2.0 * math.pi * GENERATED_HZ * t)
        + a12 * np.exp(1j * 2.0 * math.pi * TARGET_HZ * t)
    )
    if cfg.role == "ceiling_reference":
        pressure += np.real(0.22 * a8 * np.exp(1j * 2.0 * math.pi * GENERATED_HZ * t))
    pressure -= np.mean(pressure)
    window = np.hanning(len(pressure))
    spec = np.fft.rfft(pressure * window)
    freqs = np.fft.rfftfreq(len(pressure), 1.0 / sample_rate)
    power = np.abs(spec) ** 2

    def peak(center: float, width: float) -> Tuple[float, float, float]:
        mask = (freqs >= center - width) & (freqs <= center + width)
        if not np.any(mask):
            return center, 0.0, 0.0
        idxs = np.nonzero(mask)[0]
        idx = idxs[int(np.argmax(power[mask]))]
        return float(freqs[idx]), float(power[idx]), float(np.sum(power[mask]))

    p4f, p4, p4_band = peak(SOURCE_HZ, 2500.0)
    p8f, p8, p8_band = peak(GENERATED_HZ, 2500.0)
    p12f, p12, p12_band = peak(TARGET_HZ, 2500.0)
    broad = float(np.sum(power[(freqs >= 20_000.0) & (freqs <= 160_000.0)]))
    purity = p12_band / max(broad, EPS)
    return {
        "source_fft_peak_hz": p4f,
        "generated_fft_peak_hz": p8f,
        "target_fft_peak_hz": p12f,
        "source_fft_power": p4,
        "generated_fft_power": p8,
        "target_fft_power": p12,
        "source_fft_band_power": p4_band,
        "generated_fft_band_power": p8_band,
        "target_fft_band_power": p12_band,
        "spectral_purity_120khz": purity,
    }


def metrics(result: AcousticResult, reference_power: float | None) -> Dict[str, object]:
    cfg = result.config
    nums = acoustic_numbers(cfg)
    start = int(0.70 * len(result.times))
    stop = max(start + 4, int(0.80 * len(result.times)))
    a4 = result.a4[start:]
    a8 = result.a8[start:stop]
    a12 = result.a12[start:stop]
    a4 = a4[: len(a12)]
    rel8 = np.angle(a8) - 2.0 * np.angle(a4)
    rel12 = np.angle(a12) - np.angle(a8) - np.angle(a4)
    lock8 = phase_lock(rel8, np.abs(a8) * np.abs(a4) ** 2)
    lock12 = phase_lock(rel12, np.abs(a12) * np.abs(a8) * np.abs(a4))
    gen_cv = envelope_cv(a8)
    target_cv = envelope_cv(a12)
    jumps = np.abs(np.diff(np.unwrap(rel12))) if len(rel12) > 2 else np.asarray([0.0])
    max_jump = float(np.max(jumps)) if len(jumps) else 0.0
    near_slips = float(coalesced_count(np.where(jumps > 1.0)[0]))
    early_start = int(0.22 * len(result.times))
    early_stop = max(early_start + 4, int(0.38 * len(result.times)))
    late_start = int(0.64 * len(result.times))
    late_stop = max(late_start + 4, int(0.80 * len(result.times)))
    early = np.abs(result.a12[early_start:early_stop])
    late = np.abs(result.a12[late_start:late_stop])
    target_floor = 0.01 * float(np.max(np.abs(result.a12))) if len(result.a12) else 0.0
    target_growth = (
        float(np.mean(late) / max(np.mean(early), target_floor, EPS))
        if len(late) and len(early)
        else 0.0
    )
    coherent_power = float((np.mean(np.abs(a12)) ** 2) * lock12)
    bridge = coherent_power / max(reference_power or coherent_power, EPS) if reference_power is not None else 0.0
    fft = signal_fft_metrics(result)
    peak_amp = max(float(np.max(np.abs(result.a4))), float(np.max(np.abs(result.a8))), float(np.max(np.abs(result.a12))))
    peak_pressure = cfg.pressure_scale_pa * peak_amp
    if peak_pressure < 5_000:
        stress_class = "plausible"
    elif peak_pressure < 25_000:
        stress_class = "aggressive-but-testable"
    else:
        stress_class = "unrealistic"
    feedthrough_risk = min(
        1.0,
        cfg.readout_feedthrough
        * (float(np.mean(np.abs(a4))) + float(np.mean(np.abs(a8))))
        / max(float(np.mean(np.abs(a12))), EPS),
    )
    bench_length_score = max(0.0, min(1.0, 0.18 / max(cfg.interaction_length_m, EPS)))
    pressure_score = max(0.0, min(1.0, 1.0 - peak_pressure / 35_000.0))
    purity = float(fft["spectral_purity_120khz"])
    feasibility = float(
        0.22 * min(1.0, lock12)
        + 0.22 * min(1.0, purity / 0.80)
        + 0.18 * min(1.0, bridge / 1.5)
        + 0.14 * bench_length_score
        + 0.12 * pressure_score
        + 0.12 * max(0.0, 1.0 - feedthrough_risk)
    )
    control_leak = 0.0
    if cfg.role == "control":
        coherent_leak = bridge if lock12 > 0.50 and purity > 0.30 else 0.0
        growth_leak = (
            max(target_growth - 1.0, 0.0) / 8.0
            if bridge > 0.15 and purity > 0.30 and lock12 > 0.50
            else 0.0
        )
        control_leak = min(
            1.0,
            coherent_leak + growth_leak,
        )
    promotion = "not_promoted"
    if cfg.role == "discovery":
        if (
            lock12 > 0.90
            and bridge > 1.5
            and purity > 0.80
            and target_growth > 1.0
            and gen_cv < 0.25
            and max_jump < 1.0
            and stress_class in {"plausible", "aggressive-but-testable"}
        ):
            promotion = "acoustic_phase_bridge_candidate"
        elif lock12 > 0.80 and bridge > 1.0 and purity > 0.30 and stress_class == "plausible":
            promotion = "near_miss"
    elif cfg.role == "control":
        promotion = "control_dead" if control_leak < 0.15 else "control_leakage"
    else:
        promotion = "ceiling_reference_not_discovery"
    return {
        **nums,
        **fft,
        "phase_lock_target": lock12,
        "phase_lock_generated": lock8,
        "bridge_ratio_vs_direct_reference": bridge,
        "target_coherent_power": coherent_power,
        "target_coherent_growth": target_growth,
        "generated_envelope_cv": gen_cv,
        "target_envelope_cv": target_cv,
        "max_phase_jump": max_jump,
        "near_slip_count": near_slips,
        "control_leakage_score": control_leak,
        "phase_mismatch_rad_per_m": nums["limiting_delta_k_rad_m"],
        "accumulated_phase_mismatch": nums["limiting_delta_k_rad_m"] * cfg.interaction_length_m,
        "acoustic_peak_pressure_pa": peak_pressure,
        "pressure_stress_class": stress_class,
        "transducer_feedthrough_risk": feedthrough_risk,
        "bench_feasibility_score": feasibility,
        "drive_work_proxy": result.drive_work,
        "loss_work_proxy": result.loss_work,
        "energy_budget_proxy": abs((result.energy[-1] - result.energy[0]) - result.drive_work + result.loss_work)
        / max(abs(result.drive_work), EPS),
        "promotion_category": promotion,
    }


def build_configs() -> List[AcousticConfig]:
    phase = AcousticConfig(
        case_id="a001",
        name="phase_matched_64cell_baseline",
        topology="phase_matched",
        notes="Baseline acoustic phase-matched 40->80->120 kHz guide.",
    )
    rows = [
        phase,
        replace(phase, case_id="a002", name="phase_matched_80cell_low_loss", cell_count=80, damping_loss=0.026, boundary_absorption=0.024, nonlinear_4812=0.155),
        replace(phase, case_id="a003", name="phase_matched_96cell_high_nonlinearity", cell_count=96, nonlinear_448=0.118, nonlinear_4812=0.172, drive_amplitude=0.27, damping_loss=0.030),
        replace(phase, case_id="a004", name="phase_matched_longer_96cell", cell_count=96, interaction_length_m=0.105, nonlinear_448=0.110, nonlinear_4812=0.165, damping_loss=0.028),
        replace(phase, case_id="a005", name="phase_matched_short_48cell", cell_count=48, interaction_length_m=0.058, nonlinear_448=0.115, nonlinear_4812=0.160),
        replace(
            phase,
            case_id="a006",
            name="qpm_mild_mismatch_square",
            topology="qpm",
            phase_velocity_8_ratio=0.985,
            phase_velocity_12_ratio=0.973,
            qpm_enabled=True,
            qpm_period_m=0.050,
            grating_kind="square",
            nonlinear_448=0.125,
            nonlinear_4812=0.180,
        ),
        replace(
            phase,
            case_id="a007",
            name="qpm_high_nonlinearity_80cell",
            topology="qpm",
            cell_count=80,
            phase_velocity_8_ratio=0.982,
            phase_velocity_12_ratio=0.970,
            qpm_enabled=True,
            qpm_period_m=0.043,
            qpm_duty_cycle=0.42,
            grating_kind="square",
            nonlinear_448=0.138,
            nonlinear_4812=0.205,
            drive_amplitude=0.27,
        ),
        replace(
            phase,
            case_id="a008",
            name="mild_dispersion_phase_trim",
            topology="phase_matched_trim",
            phase_velocity_8_ratio=0.998,
            phase_velocity_12_ratio=0.996,
            group_velocity_8_ratio=0.970,
            group_velocity_12_ratio=0.940,
            nonlinear_4812=0.175,
            damping_loss=0.024,
        ),
    ]
    control_base = AcousticConfig(
        case_id="base",
        name="control_base",
        topology="control",
        role="control",
        cell_count=64,
        nonlinear_448=0.105,
        nonlinear_4812=0.145,
    )
    rows.extend(
        [
            replace(control_base, case_id="c001", name="linear_no_nonlinearity_control", no_nonlinearity=True, nonlinear_448=0.0, nonlinear_4812=0.0),
            replace(control_base, case_id="c002", name="weak_nonlinearity_control", nonlinear_448=0.010, nonlinear_4812=0.012),
            replace(control_base, case_id="c003", name="detuned_target_velocity_control", phase_velocity_12_ratio=0.84, target_detuning=0.65),
            replace(control_base, case_id="c004", name="phase_mismatched_control", phase_velocity_8_ratio=0.90, phase_velocity_12_ratio=1.18),
            replace(control_base, case_id="c005", name="shuffled_frequency_control", shuffled_frequency=True, phase_velocity_8_ratio=1.15, phase_velocity_12_ratio=0.87),
            replace(control_base, case_id="c006", name="too_short_guide_control", interaction_length_m=BASE_LENGTH_M * 0.18),
            replace(control_base, case_id="c007", name="too_lossy_guide_control", damping_loss=0.16, boundary_absorption=0.20),
            replace(
                control_base,
                case_id="direct_40plus80_reference",
                name="direct_40plus80_reference",
                role="ceiling_reference",
                direct_80_reference_drive=True,
                direct_80_drive_scale=0.34,
                readout_feedthrough=0.020,
            ),
        ]
    )
    return rows


def summarize_result(result: AcousticResult, reference_power: float | None) -> Dict[str, object]:
    cfg = result.config
    row = {
        "row_type": "acoustic_waveguide_412",
        "case_id": cfg.case_id,
        "name": cfg.name,
        "topology": cfg.topology,
        "role": cfg.role,
        "source_only_drive": str(not cfg.direct_80_reference_drive and cfg.role != "ceiling_reference"),
        "direct_80khz_drive_present": str(cfg.direct_80_reference_drive),
        "direct_120khz_drive_present": "False",
        "target_frequency_injection_present": "False",
        "cell_count": cfg.cell_count,
        "interaction_length_m": cfg.interaction_length_m,
        "phase_velocity_4_m_s": cfg.phase_velocity_4_m_s,
        "phase_velocity_8_ratio": cfg.phase_velocity_8_ratio,
        "phase_velocity_12_ratio": cfg.phase_velocity_12_ratio,
        "group_velocity_8_ratio": cfg.group_velocity_8_ratio,
        "group_velocity_12_ratio": cfg.group_velocity_12_ratio,
        "nonlinear_448": cfg.nonlinear_448,
        "nonlinear_4812": cfg.nonlinear_4812,
        "propagation_strength": cfg.propagation_strength,
        "damping_loss": cfg.damping_loss,
        "boundary_absorption": cfg.boundary_absorption,
        "qpm_enabled": str(cfg.qpm_enabled),
        "qpm_period_m": cfg.qpm_period_m,
        "qpm_duty_cycle": cfg.qpm_duty_cycle,
        "grating_kind": cfg.grating_kind,
        "source_amplitude": cfg.drive_amplitude,
        "readout_feedthrough": cfg.readout_feedthrough,
        "notes": cfg.notes,
    }
    row.update(metrics(result, reference_power))
    return row


def aggregate(rows: List[Dict[str, object]]) -> Dict[str, object]:
    data = [row for row in rows if row.get("row_type") == "acoustic_waveguide_412"]
    discovery = [row for row in data if row.get("role") == "discovery"]
    controls = [row for row in data if row.get("role") == "control"]
    candidates = [row for row in discovery if row.get("promotion_category") == "acoustic_phase_bridge_candidate"]
    near = [row for row in discovery if row.get("promotion_category") == "near_miss"]
    best = max(
        discovery,
        key=lambda row: (
            float(row.get("bench_feasibility_score", 0.0)),
            float(row.get("spectral_purity_120khz", 0.0)),
            float(row.get("phase_lock_target", 0.0)),
        ),
        default={},
    )
    best_purity = max(discovery, key=lambda row: float(row.get("spectral_purity_120khz", 0.0)), default={})
    mismatch = [row for row in data if "mismatch" in str(row.get("name", "")) or "detuned" in str(row.get("name", ""))]
    mismatch_failure = all(float(row.get("control_leakage_score", 0.0)) < 0.15 for row in mismatch if row.get("role") == "control")
    controls_dead = all(row.get("promotion_category") == "control_dead" for row in controls)
    max_leak = max((float(row.get("control_leakage_score", 0.0)) for row in controls), default=0.0)
    qpm_rows = [row for row in discovery if row.get("topology") == "qpm"]
    phase_rows = [row for row in discovery if str(row.get("topology", "")).startswith("phase")]
    best_qpm = max((float(row.get("spectral_purity_120khz", 0.0)) for row in qpm_rows), default=0.0)
    best_phase = max((float(row.get("spectral_purity_120khz", 0.0)) for row in phase_rows), default=0.0)
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "aggregate",
        "role": "aggregate",
        "topology": "aggregate",
        "rows_total": len(data),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "candidate_count": len(candidates),
        "near_miss_count": len(near),
        "best_case": best.get("case_id", ""),
        "best_name": best.get("name", ""),
        "best_topology": best.get("topology", ""),
        "best_phase_lock_target": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio_vs_direct_reference", ""),
        "best_purity": best.get("spectral_purity_120khz", ""),
        "best_target_growth": best.get("target_coherent_growth", ""),
        "best_generated_cv": best.get("generated_envelope_cv", ""),
        "best_max_phase_jump": best.get("max_phase_jump", ""),
        "best_length_m": best.get("interaction_length_m", ""),
        "best_pressure_pa": best.get("acoustic_peak_pressure_pa", ""),
        "best_pressure_class": best.get("pressure_stress_class", ""),
        "best_feedthrough_risk": best.get("transducer_feedthrough_risk", ""),
        "best_feasibility": best.get("bench_feasibility_score", ""),
        "best_purity_case": best_purity.get("case_id", ""),
        "best_purity_value": best_purity.get("spectral_purity_120khz", ""),
        "phase_matching_predicts_success": str(bool(candidates) or bool(near)),
        "mismatch_predicts_failure": str(mismatch_failure),
        "controls_dead": str(controls_dead),
        "max_control_leakage_score": max_leak,
        "qpm_best_purity": best_qpm,
        "phase_matched_best_purity": best_phase,
        "qpm_outperforms_phase_matched": str(best_qpm > best_phase),
        "bench_scale_length": str(float(best.get("interaction_length_m", 999.0) or 999.0) < 0.20),
        "recommended_next_step": (
            "acoustic bench design focused on nonlinear drive/readout and feedthrough suppression"
            if candidates
            else "refine acoustic nonlinearity/readout before returning to varactor BOM"
        ),
    }


def timeseries_rows(result: AcousticResult, stride: int = 1) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for idx in range(0, len(result.times), stride):
        rows.append(
            {
                "row_type": "acoustic_waveguide_412_timeseries",
                "case_id": result.config.case_id,
                "name": result.config.name,
                "time_norm": float(result.times[idx]),
                "a4_real": float(np.real(result.a4[idx])),
                "a4_imag": float(np.imag(result.a4[idx])),
                "a8_real": float(np.real(result.a8[idx])),
                "a8_imag": float(np.imag(result.a8[idx])),
                "a12_real": float(np.real(result.a12[idx])),
                "a12_imag": float(np.imag(result.a12[idx])),
                "energy": float(result.energy[idx]),
            }
        )
    return rows


def write_readme(out_dir: Path, rows: List[Dict[str, object]], agg: Dict[str, object]) -> None:
    lines = [
        "# Acoustic Waveguide 4->8->12",
        "",
        "Low-frequency acoustic/phononic analog of the distributed phase-matched bridge.",
        "",
        "## Direct Answers",
        "",
        f"1. Can the acoustic analog recover clean 120 kHz purity? candidates={agg['candidate_count']}; best_purity={agg['best_purity']}; best={agg['best_name']}.",
        f"2. Does phase matching predict success and mismatch failure? success={agg['phase_matching_predicts_success']}; mismatch_failure={agg['mismatch_predicts_failure']}.",
        f"3. Do controls stay dead? {agg['controls_dead']}; max_leakage={agg['max_control_leakage_score']}.",
        f"4. Required guide length bench-scale? {agg['bench_scale_length']}; best_length_m={agg['best_length_m']}.",
        f"5. Nonlinear drive/readout plausible? pressure={agg['best_pressure_pa']} Pa, class={agg['best_pressure_class']}, feedthrough_risk={agg['best_feedthrough_risk']}.",
        f"6. Next step: {agg['recommended_next_step']}.",
        "",
        "## Rows",
        "",
    ]
    for row in rows:
        if row.get("row_type") != "acoustic_waveguide_412":
            continue
        lines.append(
            "- {case_id} {name}: role={role}, topology={topology}, category={cat}, lock={lock}, "
            "bridge={bridge}, purity={purity}, growth={growth}, length={length}, pressure={pressure}.".format(
                case_id=row["case_id"],
                name=row["name"],
                role=row["role"],
                topology=row["topology"],
                cat=row["promotion_category"],
                lock=row["phase_lock_target"],
                bridge=row["bridge_ratio_vs_direct_reference"],
                purity=row["spectral_purity_120khz"],
                growth=row["target_coherent_growth"],
                length=row["interaction_length_m"],
                pressure=row["pressure_stress_class"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Discovery rows drive only 40 kHz.",
            "- No direct 80 kHz drive, no direct 120 kHz drive, and no target-frequency injection are used in discovery rows.",
            "- The direct 40+80 row is a separated ceiling denominator only.",
            "- Lock, bridge ratio, and envelope CV are scored on a settled pre-fade window so ramp-up and fade-out do not masquerade as envelope instability.",
            "- Target purity is measured as 120 kHz band power divided by broad 20-160 kHz readout power.",
            "- Pressure and feedthrough estimates are screening metrics, not hardware validation.",
        ]
    )
    (out_dir / "README_ACOUSTIC_WAVEGUIDE_412.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(out_dir: Path) -> Dict[str, object]:
    ensure_dir(out_dir)
    configs = build_configs()
    results = [simulate(cfg) for cfg in configs]
    reference = next(result for result in results if result.config.role == "ceiling_reference")
    reference_metrics = metrics(reference, None)
    reference_power = float(reference_metrics["target_coherent_power"])
    summary_rows = [summarize_result(result, reference_power) for result in results]
    agg = aggregate(summary_rows)
    all_rows = [agg] + summary_rows
    write_csv(out_dir / "acoustic_waveguide_412_summary.csv", all_rows)
    ts_rows: List[Dict[str, object]] = []
    for result in results:
        if result.config.role in {"discovery", "ceiling_reference"}:
            ts_rows.extend(timeseries_rows(result, stride=2))
    write_csv(out_dir / "acoustic_waveguide_412_timeseries.csv", ts_rows)
    (out_dir / "acoustic_waveguide_412_summary.json").write_text(
        json.dumps({"aggregate": agg, "rows": all_rows, "configs": [asdict(cfg) for cfg in configs]}, indent=2),
        encoding="utf-8",
    )
    write_readme(out_dir, all_rows, agg)
    return {"aggregate": agg, "rows": all_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the acoustic/phononic 4->8->12 waveguide analog.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    args = parser.parse_args()
    summary = run(Path(args.out))
    agg = summary["aggregate"]
    print(
        "acoustic_waveguide_412: candidates={cand} near={near} best={best} purity={purity} controls_dead={ctrl}".format(
            cand=agg["candidate_count"],
            near=agg["near_miss_count"],
            best=agg["best_name"],
            purity=agg["best_purity"],
            ctrl=agg["controls_dead"],
        )
    )


if __name__ == "__main__":
    main()
