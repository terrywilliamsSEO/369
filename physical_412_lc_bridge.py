#!/usr/bin/env python3
"""Physical LC translation of the independently validated 4->8->12 bridge.

This script keeps the validated 4->8->12 trajectory normalized, but maps it
onto three physically interpretable nonlinear LC resonators.  It does not
import the main lab harness.  The dimensional layer reports L/C/R/Q values,
coupling coefficients, varactor-like nonlinear strength, joule-scale energy
accounting, and peak voltages/currents for several absolute frequency scales.
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


BASE_HZ = 0.045
BASE_DT = 0.090
BASE_TMAX = 54.0 * 1.25 * 4.0
SAMPLE_EVERY = 1
SUBSTEPS_PER_MAIN_STEP = 4
OUT_DIR = Path("runs") / "physical_412_lc_bridge"

EXPECTED_INDEPENDENT = {
    "phase_lock_target": 0.992108,
    "bridge_ratio": 1.606971,
    "spectral_purity_target": 0.922789,
    "energy_budget_error": 0.0000510,
    "generated_envelope_cv": 0.134693,
    "max_phase_jump": 0.971944,
    "near_slip_count": 0.0,
}


@dataclass(frozen=True)
class BridgeConfig:
    name: str
    mode_freqs: Tuple[float, float, float]
    drive_freqs: Tuple[float, ...]
    drive_modes: Tuple[int, ...]
    drive_phases: Tuple[float, ...] = (0.0,)
    target_6: float = 8.0
    target_9: float = 12.0
    stage_a_nonlinear_strength: float = 0.50
    stage_b_nonlinear_strength: float = 0.8959006451612903
    stage_a_to_stage_b_coupling: float = 1.2201290322580647
    stage_b_to_receiver_coupling: float = 1.200483870967742
    stage_a_damping: float = 0.70
    stage_b_damping: float = 0.9800000000000001
    receiver_damping: float = 0.8140000000000001
    drive_amp: float = 0.070
    varactor_coefficient: float = 0.19
    spark_strength: float = 0.079568
    spark_threshold: float = 0.035
    stage_b_phase_bias_deg: float = 24.8
    reference_role: str = "discovery_candidate"
    note: str = ""


@dataclass(frozen=True)
class ScalePreset:
    name: str
    source_frequency_hz: float
    capacitances_f: Tuple[float, float, float]
    energy_scale_j: float
    description: str


@dataclass(frozen=True)
class LCParams:
    mode: str
    frequency_hz: float
    nominal_ratio_frequency_hz: float
    capacitance_f: float
    inductance_h: float
    resistance_ohm: float
    q_factor: float
    q_class: str
    voltage_scale_v: float
    current_scale_a_per_model_velocity: float
    drive_voltage_peak_v: float
    varactor_beta_per_v2: float


CANDIDATE = BridgeConfig(
    name="physicalized_independent_412_candidate",
    mode_freqs=(4.0, 8.0354, 11.907835129474883),
    drive_freqs=(4.0,),
    drive_modes=(0,),
    drive_phases=(0.0,),
    note=(
        "Physicalization of the independent strict 4->8->12 candidate: target detuning -0.08, "
        "Stage A offset +0.040, generated damping factor 1.05, A->B coupling 0.90, limiter 0.03. "
        "Discovery drive is source-only; no direct 8 drive, no direct 12 drive, no target-frequency injection."
    ),
)

DIRECT_REFERENCE = replace(
    CANDIDATE,
    name="direct_source_plus_generated_reference_ceiling",
    drive_freqs=(4.0, 8.0),
    drive_modes=(0, 1),
    drive_phases=(0.0, 0.0),
    stage_a_nonlinear_strength=0.0,
    reference_role="ceiling_reference",
    note=(
        "Ceiling denominator only. This row uses direct 8 drive and is not a discovery candidate."
    ),
)

SCALE_PRESETS: Dict[str, ScalePreset] = {
    "audio-scale": ScalePreset(
        name="audio-scale",
        source_frequency_hz=440.0,
        capacitances_f=(10.0e-6, 4.7e-6, 3.3e-6),
        energy_scale_j=1.0e-3,
        description="Audio-band source near A4 with mH coils, microfarad capacitors, and millijoule-scale storage.",
    ),
    "low-RF-scale": ScalePreset(
        name="low-RF-scale",
        source_frequency_hz=1.0e6,
        capacitances_f=(1.0e-9, 470.0e-12, 330.0e-12),
        energy_scale_j=1.0e-9,
        description="Low-RF source near 1 MHz with nF/pF capacitors, microhenry coils, and nanojoule-scale storage.",
    ),
    "arbitrary-normalized-scale": ScalePreset(
        name="arbitrary-normalized-scale",
        source_frequency_hz=BASE_HZ * 4.0,
        capacitances_f=(1.0, 1.0, 1.0),
        energy_scale_j=1.0,
        description="Dimensioned version of the normalized validation scale; useful for audit math, not hardware sizing.",
    ),
}

MODE_NAMES = ("source_4", "generated_8", "target_12")


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


def metric_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / max(denominator, 1e-18))


def wrap_angle(x: np.ndarray | float) -> np.ndarray | float:
    return (np.asarray(x) + np.pi) % (2.0 * np.pi) - np.pi


def complex_projection(signal: np.ndarray, t: np.ndarray, freq_hz: float) -> complex:
    phase = np.exp(-1j * 2.0 * np.pi * freq_hz * t)
    return 2.0 * np.mean(signal * phase)


def sliding_phase(signal: np.ndarray, t: np.ndarray, freq_hz: float, window: int, step: int) -> np.ndarray:
    phases: List[float] = []
    for start in range(0, len(signal) - window, step):
        stop = start + window
        z = complex_projection(signal[start:stop], t[start:stop], freq_hz)
        phases.append(float(np.angle(z)))
    return np.asarray(phases)


def spark_gate(delta_q: np.ndarray | float, threshold: float = 0.035) -> np.ndarray | float:
    width = 0.30 * threshold
    return 0.5 * (1.0 + np.tanh((np.abs(delta_q) - threshold) / (width + 1e-12)))


def clean_modal_energy(q: np.ndarray, v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    return 0.5 * (v ** 2) + 0.5 * (omega ** 2) * (q ** 2)


def bridge_route_strengths(config: BridgeConfig) -> Tuple[float, float]:
    phase_factor = math.cos(math.radians(config.stage_b_phase_bias_deg))
    return config.stage_a_nonlinear_strength, config.stage_b_nonlinear_strength * phase_factor


def bridge_potentials(q: np.ndarray, v: np.ndarray, omega: np.ndarray, config: BridgeConfig) -> Dict[str, float]:
    linear = float(np.sum(0.5 * (v ** 2) + 0.5 * (omega ** 2) * (q ** 2)))
    k01 = 0.0035 * config.stage_a_to_stage_b_coupling * omega[0] * omega[1]
    k12 = 0.0035 * config.stage_b_to_receiver_coupling * omega[1] * omega[2]
    coupling = 0.5 * k01 * float((q[0] - q[1]) ** 2) + 0.5 * k12 * float((q[1] - q[2]) ** 2)
    varactor = 0.25 * config.varactor_coefficient * float(np.sum(q ** 4))
    gamma_a, gamma_b = bridge_route_strengths(config)
    mix_a = -0.5 * gamma_a * float(q[0] * q[0] * q[1])
    mix_b = -gamma_b * float(q[0] * q[1] * q[2])
    nonlinear_total = varactor + mix_a + mix_b
    return {
        "linear": linear,
        "coupling": coupling,
        "varactor": varactor,
        "mix_a": mix_a,
        "mix_b": mix_b,
        "nonlinear_total": nonlinear_total,
        "total": linear + coupling + nonlinear_total,
    }


def drive_forces(config: BridgeConfig, t: float, drive_start: float, drive_until: float, n_modes: int) -> np.ndarray:
    forces = np.zeros(n_modes)
    if t < drive_start or t >= drive_until:
        return forces
    tau = t - drive_start
    ramp_in = min(1.0, tau / 10.0)
    ramp_out = min(1.0, max(0.0, (drive_until - t) / 10.0))
    envelope = ramp_in * ramp_out
    norm = math.sqrt(max(1, len(config.drive_freqs)))
    phases = list(config.drive_phases) + [0.0] * max(0, len(config.drive_freqs) - len(config.drive_phases))
    for freq, mode_idx, phase in zip(config.drive_freqs, config.drive_modes, phases):
        forces[mode_idx] += envelope * config.drive_amp * math.sin(2.0 * np.pi * BASE_HZ * freq * tau + phase) / norm
    return forces


def derivative(y: np.ndarray, t: float, omega: np.ndarray, config: BridgeConfig,
               drive_start: float, drive_until: float, zeta: np.ndarray) -> np.ndarray:
    q = y[:3]
    v = y[3:]
    a = -(omega ** 2) * q

    k01 = 0.0035 * config.stage_a_to_stage_b_coupling * omega[0] * omega[1]
    k12 = 0.0035 * config.stage_b_to_receiver_coupling * omega[1] * omega[2]
    d01 = q[0] - q[1]
    d12 = q[1] - q[2]
    a[0] += -k01 * d01
    a[1] += k01 * d01 - k12 * d12
    a[2] += k12 * d12

    if config.varactor_coefficient:
        a += -config.varactor_coefficient * q ** 3

    gamma_a, gamma_b = bridge_route_strengths(config)
    if gamma_a:
        a[0] += gamma_a * q[0] * q[1]
        a[1] += 0.5 * gamma_a * q[0] * q[0]
    if gamma_b:
        a[0] += gamma_b * q[1] * q[2]
        a[1] += gamma_b * q[0] * q[2]
        a[2] += gamma_b * q[0] * q[1]

    if config.spark_strength:
        for i, j in ((0, 1), (1, 2)):
            gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
            c = 0.030 * config.spark_strength * gate
            spark_force = c * (v[i] - v[j])
            a[i] += -spark_force
            a[j] += spark_force

    a += -2.0 * zeta * omega * v
    a += drive_forces(config, t, drive_start, drive_until, 3)
    return np.concatenate([v, a])


def limiter_loss(_config: BridgeConfig, _q: np.ndarray, _v: np.ndarray, _omega: np.ndarray) -> float:
    # The validated limiter is represented here as passive spark/saturation loss.
    # There is no active adaptive limiter work term.
    return 0.0


def power_terms(config: BridgeConfig, omega: np.ndarray, zeta: np.ndarray,
                y: np.ndarray, t: float, drive_start: float, drive_until: float) -> Dict[str, float]:
    q = y[:3]
    v = y[3:]
    forces = drive_forces(config, t, drive_start, drive_until, 3)
    drive_power = float(np.dot(forces, v))
    damping_power = float(np.sum(2.0 * zeta * omega * (v ** 2)))
    limiter_power = limiter_loss(config, q, v, omega)
    spark_power = 0.0
    if config.spark_strength:
        for i, j in ((0, 1), (1, 2)):
            gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
            c = 0.030 * config.spark_strength * gate
            spark_power += float(c * ((v[i] - v[j]) ** 2))
    return {
        "drive": drive_power,
        "positive_drive": max(0.0, drive_power),
        "damping": damping_power,
        "limiter": limiter_power,
        "adaptive_damping": limiter_power,
        "spark": spark_power,
    }


def add_weighted_terms(accum: Dict[str, float], terms: Dict[str, float], weight: float) -> None:
    for key in ("drive", "positive_drive", "damping", "limiter", "adaptive_damping", "spark"):
        accum[key] = accum.get(key, 0.0) + weight * float(terms.get(key, 0.0))


def simulate(config: BridgeConfig, seed: int, main_dt: float, t_max: float,
             sample_every: int = SAMPLE_EVERY, substeps: int = SUBSTEPS_PER_MAIN_STEP
             ) -> Tuple[Dict[str, object], List[Dict[str, float | str]]]:
    rng = np.random.default_rng(seed)
    substeps = max(1, int(substeps))
    audit_dt = main_dt / substeps
    drive_start = 0.0
    drive_until = 0.74 * t_max
    omega = 2.0 * np.pi * BASE_HZ * np.asarray(config.mode_freqs, dtype=float)
    zeta = zeta_values(config)

    y = np.zeros(6)
    y[:3] = 1e-4 * rng.normal(size=3)
    y[3:] = 1e-4 * rng.normal(size=3)
    initial_total = float(bridge_potentials(y[:3], y[3:], omega, config)["total"])
    accum = {"drive": 0.0, "positive_drive": 0.0, "damping": 0.0, "limiter": 0.0, "adaptive_damping": 0.0, "spark": 0.0}

    times: List[float] = [0.0]
    qs: List[np.ndarray] = [y[:3].copy()]
    vs: List[np.ndarray] = [y[3:].copy()]
    energies: List[np.ndarray] = [clean_modal_energy(y[:3], y[3:], omega)]
    ledger: List[Dict[str, float | str]] = []

    n_steps = int(t_max / audit_dt)
    sample_stride = max(1, int(sample_every) * substeps)
    for step in range(n_steps):
        t = step * audit_dt
        k1 = derivative(y, t, omega, config, drive_start, drive_until, zeta)
        y2 = y + 0.5 * audit_dt * k1
        k2 = derivative(y2, t + 0.5 * audit_dt, omega, config, drive_start, drive_until, zeta)
        y3 = y + 0.5 * audit_dt * k2
        k3 = derivative(y3, t + 0.5 * audit_dt, omega, config, drive_start, drive_until, zeta)
        y4 = y + audit_dt * k3
        k4 = derivative(y4, t + audit_dt, omega, config, drive_start, drive_until, zeta)

        stage_terms = (
            power_terms(config, omega, zeta, y, t, drive_start, drive_until),
            power_terms(config, omega, zeta, y2, t + 0.5 * audit_dt, drive_start, drive_until),
            power_terms(config, omega, zeta, y3, t + 0.5 * audit_dt, drive_start, drive_until),
            power_terms(config, omega, zeta, y4, t + audit_dt, drive_start, drive_until),
        )
        for terms, weight in zip(stage_terms, (audit_dt / 6.0, audit_dt / 3.0, audit_dt / 3.0, audit_dt / 6.0)):
            add_weighted_terms(accum, terms, weight)

        y = y + (audit_dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e6:
            break

        if (step + 1) % sample_stride == 0 or step == n_steps - 1:
            now = float((step + 1) * audit_dt)
            qn = y[:3].copy()
            vn = y[3:].copy()
            after = bridge_potentials(qn, vn, omega, config)
            total_accounted = initial_total + accum["drive"] - accum["damping"] - accum["limiter"] - accum["spark"]
            error_abs = float(after["total"]) - total_accounted
            error_rel = abs(error_abs) / (abs(float(after["total"])) + abs(total_accounted) + 1e-18)
            times.append(now)
            qs.append(qn)
            vs.append(vn)
            energies.append(clean_modal_energy(qn, vn, omega))
            ledger.append({
                "time": now,
                "run": config.name,
                "main_dt": main_dt,
                "effective_dt": audit_dt,
                "drive_input_work": accum["drive"],
                "positive_input_work": accum["positive_drive"],
                "damping_loss": accum["damping"],
                "limiter_work": accum["limiter"],
                "adaptive_damping_work": accum["adaptive_damping"],
                "spark_loss": accum["spark"],
                "total_stored_energy": float(after["total"]),
                "total_accounted_energy": total_accounted,
                "energy_budget_error_abs": error_abs,
                "energy_budget_error_rel": error_rel,
            })

    final = ledger[-1] if ledger else {}
    sim: Dict[str, object] = {
        "times": np.asarray(times),
        "qs": np.asarray(qs),
        "vs": np.asarray(vs),
        "energy": np.asarray(energies),
        "omega": omega,
        "drive_until": drive_until,
        "dt_sample": main_dt * sample_every,
        "effective_dt": audit_dt,
        "positive_input_work": accum["positive_drive"],
        "net_input_work": accum["drive"],
        "damping_loss": accum["damping"],
        "limiter_work": accum["limiter"],
        "adaptive_damping_work": accum["adaptive_damping"],
        "spark_loss": accum["spark"],
        "energy_budget_error_rel": float(final.get("energy_budget_error_rel", 1.0)),
        "energy_budget_error_abs": float(final.get("energy_budget_error_abs", 0.0)),
        "max_energy_budget_error_rel": max((float(r["energy_budget_error_rel"]) for r in ledger), default=1.0),
        "config": config,
    }
    return sim, ledger


def target_mode_energy(q: np.ndarray, current: np.ndarray, times: np.ndarray,
                       target_hz: float, omega_target: float) -> float:
    q_amp = complex_projection(q, times, target_hz)
    current_amp = complex_projection(current, times, target_hz)
    return float(0.25 * ((abs(current_amp) ** 2) + (omega_target ** 2) * (abs(q_amp) ** 2)))


def phase_lock(times: np.ndarray, qs: np.ndarray, config: BridgeConfig, sample_dt: float) -> Tuple[float, float]:
    window = max(24, int(6.0 / max(sample_dt, 1e-9)))
    step = max(8, window // 5)
    if len(times) <= window + step:
        return 0.0, float("nan")
    p_i = sliding_phase(qs[:, 0], times, BASE_HZ * config.mode_freqs[0], window, step)
    p_j = sliding_phase(qs[:, 1], times, BASE_HZ * config.target_6, window, step)
    p_k = sliding_phase(qs[:, 2], times, BASE_HZ * config.target_9, window, step)
    min_len = min(len(p_i), len(p_j), len(p_k))
    mismatch = wrap_angle(p_i[:min_len] + p_j[:min_len] - p_k[:min_len])
    if len(mismatch) == 0:
        return 0.0, float("nan")
    return float(np.abs(np.mean(np.exp(1j * mismatch)))), float(np.std(mismatch))


def peak_frequency(config: BridgeConfig, t_win: np.ndarray, q_win: np.ndarray, v_win: np.ndarray,
                   omega_target: float, span_fraction: float = 0.025, n_grid: int = 51) -> Tuple[float, float]:
    target = float(config.target_9)
    freqs = np.linspace(target * (1.0 - span_fraction), target * (1.0 + span_fraction), n_grid)
    scores = []
    for freq in freqs:
        q_amp = abs(complex_projection(q_win, t_win, BASE_HZ * freq))
        v_amp = abs(complex_projection(v_win, t_win, BASE_HZ * freq))
        scores.append(q_amp * q_amp + (v_amp / max(float(omega_target), 1e-12)) ** 2)
    score_arr = np.asarray(scores)
    best_idx = int(np.argmax(score_arr))
    best = float(freqs[best_idx])
    if 0 < best_idx < len(freqs) - 1:
        y0, y1, y2 = score_arr[best_idx - 1], score_arr[best_idx], score_arr[best_idx + 1]
        denom = y0 - 2.0 * y1 + y2
        if abs(float(denom)) > 1e-18:
            offset = 0.5 * float(y0 - y2) / float(denom)
            best = float(np.clip(freqs[best_idx] + offset * (freqs[1] - freqs[0]), freqs[0], freqs[-1]))
    fitted_energy = target_mode_energy(q_win, v_win, t_win, BASE_HZ * best, omega_target)
    return best, fitted_energy


def phase_cv(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    mean_abs = float(np.mean(np.abs(values)))
    if mean_abs <= 1e-18:
        return 0.0
    return float(np.std(values) / mean_abs)


def coalesced_indices(indices: np.ndarray, min_separation: int = 2) -> List[int]:
    events: List[int] = []
    last = -1000000
    for raw_idx in indices:
        idx = int(raw_idx)
        if idx - last >= min_separation:
            events.append(idx)
            last = idx
        elif events and idx > events[-1]:
            events[-1] = idx
            last = idx
    return events


def sliding_phase_diagnostics(config: BridgeConfig, sim: Dict[str, object],
                              direct_sim: Dict[str, object] | None) -> Tuple[List[Dict[str, float | str]], Dict[str, float]]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    dt_sample = float(sim["dt_sample"])
    if len(times) < 40:
        return [], {"generated_envelope_cv": 0.0, "target_envelope_cv": 0.0, "max_phase_jump": 0.0, "near_slip_count": 0.0}

    start_idx = int(np.searchsorted(times, 0.50 * drive_until))
    stop_idx = int(np.searchsorted(times, 1.00 * drive_until))
    start_idx = max(0, min(start_idx, len(times) - 2))
    stop_idx = max(start_idx + 2, min(stop_idx, len(times)))
    window = max(30, int(6.0 / max(dt_sample, 1e-9)))
    step = max(6, window // 5)

    direct_times = direct_sim["times"] if direct_sim else None  # type: ignore[index]
    direct_qs = direct_sim["qs"] if direct_sim else None  # type: ignore[index]
    direct_vs = direct_sim["vs"] if direct_sim else None  # type: ignore[index]
    direct_omega = direct_sim["omega"] if direct_sim else None  # type: ignore[index]

    rows: List[Dict[str, float | str]] = []
    for start in range(start_idx, max(start_idx + 1, stop_idx - window), step):
        stop = min(start + window, stop_idx)
        if stop - start < 12:
            continue
        t_win = times[start:stop]
        q_win = qs[start:stop]
        v_win = vs[start:stop]
        e_win = energy[start:stop]
        fitted, target_energy = peak_frequency(config, t_win, q_win[:, 2], v_win[:, 2], float(omega[2]))
        source_amp = complex_projection(q_win[:, 0], t_win, BASE_HZ * config.mode_freqs[0])
        generated_amp = complex_projection(q_win[:, 1], t_win, BASE_HZ * config.target_6)
        target_amp = complex_projection(q_win[:, 2], t_win, BASE_HZ * fitted)
        direct_target_energy = 0.0
        if direct_sim is not None and direct_times is not None and direct_qs is not None and direct_vs is not None and direct_omega is not None:
            dmask = (direct_times >= float(t_win[0])) & (direct_times <= float(t_win[-1]))
            if int(np.sum(dmask)) >= 4:
                direct_target_energy = target_mode_energy(
                    direct_qs[dmask, 2],
                    direct_vs[dmask, 2],
                    direct_times[dmask],
                    BASE_HZ * fitted,
                    float(direct_omega[2]),
                )
        rows.append({
            "time_mid": float(np.mean(t_win)),
            "phase_error_generated_2f": float(wrap_angle(2.0 * float(np.angle(source_amp)) - float(np.angle(generated_amp)))),
            "phase_error_target_3f": float(wrap_angle(float(np.angle(source_amp)) + float(np.angle(generated_amp)) - float(np.angle(target_amp)))),
            "fitted_effective_target_frequency": fitted,
            "target_frequency_delta": fitted - float(config.target_9),
            "generated_2f_amplitude_envelope": float(abs(generated_amp)),
            "target_3f_amplitude_envelope": float(abs(target_amp)),
            "spectral_purity_target": float(min(1.0, target_energy / (float(np.mean(e_win[:, 2])) + 1e-18))),
            "bridge_ratio": metric_ratio(target_energy, direct_target_energy),
        })

    if not rows:
        return [], {"generated_envelope_cv": 0.0, "target_envelope_cv": 0.0, "max_phase_jump": 0.0, "near_slip_count": 0.0}

    target_phase = np.asarray([float(r["phase_error_target_3f"]) for r in rows])
    generated_phase = np.asarray([float(r["phase_error_generated_2f"]) for r in rows])
    unwrapped_target = np.unwrap(target_phase)
    unwrapped_generated = np.unwrap(generated_phase)
    phase_step = np.abs(np.diff(unwrapped_target)) if len(unwrapped_target) >= 2 else np.asarray([])
    generated_step = np.abs(np.diff(unwrapped_generated)) if len(unwrapped_generated) >= 2 else np.asarray([])
    median_step = float(np.median(phase_step)) if len(phase_step) else 0.0
    slip_threshold = max(1.05, 3.0 * median_step + 0.05)
    slip_events = coalesced_indices(np.where(phase_step > slip_threshold)[0] + 1)
    near_slips = coalesced_indices(np.where(phase_step > 1.0)[0] + 1)
    gen_median = float(np.median(generated_step)) if len(generated_step) else 0.0
    gen_slips = coalesced_indices(np.where(generated_step > max(1.05, 3.0 * gen_median + 0.05))[0] + 1)
    generated_amp = np.asarray([float(r["generated_2f_amplitude_envelope"]) for r in rows])
    target_amp = np.asarray([float(r["target_3f_amplitude_envelope"]) for r in rows])
    for idx, row in enumerate(rows):
        row["unwrapped_phase_error_target"] = float(unwrapped_target[idx])
        row["unwrapped_phase_error_generated_2f"] = float(unwrapped_generated[idx])
        row["phase_slip_event"] = str(idx in set(slip_events))
    return rows, {
        "generated_envelope_cv": phase_cv(generated_amp),
        "target_envelope_cv": phase_cv(target_amp),
        "max_phase_jump": float(np.max(phase_step)) if len(phase_step) else 0.0,
        "near_slip_count": float(len(near_slips)),
        "phase_slip_count": float(len(slip_events)),
        "generated_phase_slip_count": float(len(gen_slips)),
    }


def global_metrics(config: BridgeConfig, sim: Dict[str, object],
                   direct_sim: Dict[str, object]) -> Dict[str, float]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    direct_times = direct_sim["times"]  # type: ignore[index]
    direct_qs = direct_sim["qs"]  # type: ignore[index]
    direct_vs = direct_sim["vs"]  # type: ignore[index]
    direct_omega = direct_sim["omega"]  # type: ignore[index]
    drive_until = float(sim["drive_until"])
    mask = (times >= 0.35 * drive_until) & (times < drive_until)
    if int(np.sum(mask)) < 20:
        mask = times >= 0.45 * times[-1]
    dmask = (direct_times >= 0.35 * float(direct_sim["drive_until"])) & (direct_times < float(direct_sim["drive_until"]))
    if int(np.sum(dmask)) < 20:
        dmask = direct_times >= 0.45 * direct_times[-1]

    if int(np.sum(mask)) >= 4 and int(np.sum(dmask)) >= 4:
        energy_at_target = target_mode_energy(qs[mask, 2], vs[mask, 2], times[mask], BASE_HZ * config.target_9, float(omega[2]))
        direct_energy_at_target = target_mode_energy(direct_qs[dmask, 2], direct_vs[dmask, 2], direct_times[dmask], BASE_HZ * config.target_9, float(direct_omega[2]))
        total_target = float(np.mean(energy[mask, 2]) + 1e-18)
        lock, lock_std = phase_lock(times[mask], qs[mask], config, float(sim["dt_sample"]))
    else:
        energy_at_target = 0.0
        direct_energy_at_target = 0.0
        total_target = 1e-18
        lock = 0.0
        lock_std = float("nan")
    return {
        "phase_lock_target": lock,
        "phase_lock_target_std": lock_std,
        "spectral_purity_target": float(min(1.0, energy_at_target / total_target)),
        "energy_at_target": energy_at_target,
        "direct_reference_energy_at_target": direct_energy_at_target,
        "bridge_ratio": metric_ratio(energy_at_target, direct_energy_at_target),
    }


def zeta_values(config: BridgeConfig) -> np.ndarray:
    return np.asarray([
        0.018 * config.stage_a_damping,
        0.012 * config.stage_b_damping,
        0.008 * config.receiver_damping,
    ])


def q_class(q_factor: float) -> str:
    if q_factor < 100.0:
        return "mild"
    if q_factor < 1000.0:
        return "high"
    return "extreme"


def scale_factor(preset: ScalePreset) -> float:
    return preset.source_frequency_hz / (BASE_HZ * CANDIDATE.mode_freqs[0])


def build_lc_params(config: BridgeConfig, preset: ScalePreset) -> List[LCParams]:
    omega_model = 2.0 * np.pi * BASE_HZ * np.asarray(config.mode_freqs, dtype=float)
    zeta = zeta_values(config)
    s = scale_factor(preset)
    params: List[LCParams] = []
    drive_peak_by_mode = [0.0, 0.0, 0.0]
    norm = math.sqrt(max(1, len(config.drive_freqs)))
    for freq, mode_idx in zip(config.drive_freqs, config.drive_modes):
        drive_peak_by_mode[mode_idx] += config.drive_amp / norm / max((2.0 * np.pi * BASE_HZ * freq) ** 2, 1e-18)

    for idx, name in enumerate(MODE_NAMES):
        f_abs = BASE_HZ * config.mode_freqs[idx] * s
        nominal_abs = preset.source_frequency_hz * ((4.0, 8.0, 12.0)[idx] / 4.0)
        omega_abs = 2.0 * np.pi * f_abs
        capacitance = preset.capacitances_f[idx]
        inductance = 1.0 / ((omega_abs ** 2) * capacitance)
        q_factor = 1.0 / (2.0 * float(zeta[idx]))
        resistance = omega_abs * inductance / q_factor
        voltage_scale = math.sqrt(preset.energy_scale_j * (float(omega_model[idx]) ** 2) / capacitance)
        current_scale = capacitance * voltage_scale * s
        drive_voltage_peak = drive_peak_by_mode[idx] * voltage_scale
        varactor_beta = config.varactor_coefficient * preset.energy_scale_j / max(capacitance * (voltage_scale ** 4), 1e-30)
        params.append(LCParams(
            mode=name,
            frequency_hz=f_abs,
            nominal_ratio_frequency_hz=nominal_abs,
            capacitance_f=capacitance,
            inductance_h=inductance,
            resistance_ohm=resistance,
            q_factor=q_factor,
            q_class=q_class(q_factor),
            voltage_scale_v=voltage_scale,
            current_scale_a_per_model_velocity=current_scale,
            drive_voltage_peak_v=drive_voltage_peak,
            varactor_beta_per_v2=varactor_beta,
        ))
    return params


def coupling_summary(config: BridgeConfig) -> Dict[str, float]:
    omega = 2.0 * np.pi * BASE_HZ * np.asarray(config.mode_freqs, dtype=float)
    gamma_a, gamma_b = bridge_route_strengths(config)
    return {
        "linear_k01_accel": 0.0035 * config.stage_a_to_stage_b_coupling * float(omega[0] * omega[1]),
        "linear_k12_accel": 0.0035 * config.stage_b_to_receiver_coupling * float(omega[1] * omega[2]),
        "linear_k01_fraction_of_omega_product": 0.0035 * config.stage_a_to_stage_b_coupling,
        "linear_k12_fraction_of_omega_product": 0.0035 * config.stage_b_to_receiver_coupling,
        "stage_a_mixing_gamma": gamma_a,
        "stage_b_mixing_gamma_effective": gamma_b,
        "stage_b_phase_bias_deg": config.stage_b_phase_bias_deg,
    }


def physical_metrics(config: BridgeConfig, sim: Dict[str, object], preset: ScalePreset) -> Dict[str, float | str]:
    params = build_lc_params(config, preset)
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    e0 = preset.energy_scale_j
    s = scale_factor(preset)
    final_p = bridge_potentials(qs[-1], vs[-1], omega, config)
    all_p = [bridge_potentials(q, v, omega, config) for q, v in zip(qs, vs)]
    v_scales = np.asarray([p.voltage_scale_v for p in params])
    i_scales = np.asarray([p.current_scale_a_per_model_velocity for p in params])
    voltages = qs * v_scales
    currents = vs * i_scales
    varactor_beta = np.asarray([p.varactor_beta_per_v2 for p in params])
    peak_fractional_cap_shift = float(np.max(varactor_beta * (voltages ** 2)))
    physical_time_final = float(sim["times"][-1]) / s  # type: ignore[index]
    return {
        "physical_duration_s": physical_time_final,
        "energy_scale_j": e0,
        "stored_energy_final_j": float(final_p["total"]) * e0,
        "stored_energy_peak_j": max(float(p["total"]) for p in all_p) * e0,
        "linear_stored_energy_final_j": float(final_p["linear"]) * e0,
        "coupling_stored_energy_final_j": float(final_p["coupling"]) * e0,
        "nonlinear_stored_energy_final_j": float(final_p["nonlinear_total"]) * e0,
        "varactor_energy_final_j": float(final_p["varactor"]) * e0,
        "mixing_energy_final_j": (float(final_p["mix_a"]) + float(final_p["mix_b"])) * e0,
        "drive_work_j": float(sim["net_input_work"]) * e0,
        "positive_drive_work_j": float(sim["positive_input_work"]) * e0,
        "resistive_loss_j": float(sim["damping_loss"]) * e0,
        "soft_limiter_loss_j": float(sim["spark_loss"]) * e0,
        "active_limiter_work_j": float(sim["limiter_work"]) * e0,
        "nonlinear_limiter_work_j": (float(sim["limiter_work"]) + float(sim["spark_loss"])) * e0,
        "energy_budget_error_abs_j": abs(float(sim["energy_budget_error_abs"])) * e0,
        "energy_budget_error_rel": float(sim["energy_budget_error_rel"]),
        "max_energy_budget_error_rel": float(sim["max_energy_budget_error_rel"]),
        "peak_voltage_source_v": float(np.max(np.abs(voltages[:, 0]))),
        "peak_voltage_generated_v": float(np.max(np.abs(voltages[:, 1]))),
        "peak_voltage_target_v": float(np.max(np.abs(voltages[:, 2]))),
        "peak_current_source_a": float(np.max(np.abs(currents[:, 0]))),
        "peak_current_generated_a": float(np.max(np.abs(currents[:, 1]))),
        "peak_current_target_a": float(np.max(np.abs(currents[:, 2]))),
        "source_frequency_hz": params[0].frequency_hz,
        "generated_frequency_hz": params[1].frequency_hz,
        "target_frequency_hz": params[2].frequency_hz,
        "nominal_target_frequency_hz": params[2].nominal_ratio_frequency_hz,
        "required_nonlinear_capacitance_strength_max_1_per_v2": float(np.max(varactor_beta)),
        "peak_fractional_capacitance_shift": peak_fractional_cap_shift,
        "direct_8_drive_present": str(False),
        "direct_12_drive_present": str(False),
        "target_frequency_injection_present": str(False),
    }


def physical_timeseries_rows(scale_name: str, dt_level: str, config: BridgeConfig, sim: Dict[str, object],
                             ledger: List[Dict[str, float | str]], preset: ScalePreset,
                             stride: int = 1) -> List[Dict[str, float | str]]:
    params = build_lc_params(config, preset)
    s = scale_factor(preset)
    v_scales = np.asarray([p.voltage_scale_v for p in params])
    i_scales = np.asarray([p.current_scale_a_per_model_velocity for p in params])
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    ledger_by_time = {float(item["time"]): item for item in ledger}
    rows: List[Dict[str, float | str]] = []
    stride = max(1, int(stride))
    for idx in range(0, len(times), stride):
        t = float(times[idx])
        led = ledger_by_time.get(t, {})
        q = qs[idx]
        vel = vs[idx]
        voltages = q * v_scales
        currents = vel * i_scales
        rows.append({
            "row_type": "candidate_timeseries",
            "scale_preset": scale_name,
            "dt_level": dt_level,
            "time_model": t,
            "time_seconds": t / s,
            "x_source": float(q[0]),
            "x_generated": float(q[1]),
            "x_target": float(q[2]),
            "voltage_source_v": float(voltages[0]),
            "voltage_generated_v": float(voltages[1]),
            "voltage_target_v": float(voltages[2]),
            "current_source_a": float(currents[0]),
            "current_generated_a": float(currents[1]),
            "current_target_a": float(currents[2]),
            "modal_energy_source_j": float(energy[idx, 0]) * preset.energy_scale_j,
            "modal_energy_generated_j": float(energy[idx, 1]) * preset.energy_scale_j,
            "modal_energy_target_j": float(energy[idx, 2]) * preset.energy_scale_j,
            "stored_energy_j": float(led.get("total_stored_energy", "")) * preset.energy_scale_j if led else "",
            "drive_work_j": float(led.get("drive_input_work", "")) * preset.energy_scale_j if led else "",
            "resistive_loss_j": float(led.get("damping_loss", "")) * preset.energy_scale_j if led else "",
            "soft_limiter_loss_j": float(led.get("spark_loss", "")) * preset.energy_scale_j if led else "",
            "energy_budget_error_rel": float(led.get("energy_budget_error_rel", "")) if led else "",
        })
    return rows


def direct_drive_flags(config: BridgeConfig) -> Dict[str, str]:
    direct_8 = any(abs(freq - config.target_6) < 1e-9 and mode == 1 for freq, mode in zip(config.drive_freqs, config.drive_modes))
    direct_12 = any(abs(freq - config.target_9) < 1e-9 and mode == 2 for freq, mode in zip(config.drive_freqs, config.drive_modes))
    target_injection = any(abs(freq - config.target_9) < 1e-9 for freq in config.drive_freqs)
    return {
        "candidate_no_direct_8_drive": str(not direct_8),
        "candidate_no_direct_12_drive": str(not direct_12),
        "candidate_no_target_frequency_injection": str(not target_injection),
    }


def gate_row(row: Dict[str, float | str]) -> bool:
    return (
        float(row["phase_lock_target"]) > 0.90
        and float(row["bridge_ratio"]) > 1.5
        and float(row["spectral_purity_target"]) > 0.80
        and float(row["physical_energy_budget_error"]) < 0.005
        and float(row["generated_envelope_cv"]) < 0.25
        and float(row["max_phase_jump"]) < 1.0
        and float(row["near_slip_count"]) == 0.0
        and str(row["candidate_no_direct_8_drive"]) == "True"
        and str(row["candidate_no_direct_12_drive"]) == "True"
        and str(row["candidate_no_target_frequency_injection"]) == "True"
    )


def realism_score(row: Dict[str, float | str], params: List[LCParams], coupling: Dict[str, float]) -> Tuple[float, str]:
    max_q = max(p.q_factor for p in params)
    q_score = 1.0 if max_q < 100.0 else 0.75 if max_q < 1000.0 else 0.25
    max_linear_coupling = max(
        abs(float(coupling["linear_k01_fraction_of_omega_product"])),
        abs(float(coupling["linear_k12_fraction_of_omega_product"])),
    )
    coupling_score = 1.0 if max_linear_coupling < 0.02 else 0.75 if max_linear_coupling < 0.10 else 0.35
    nonlinear_mix = max(abs(float(coupling["stage_a_mixing_gamma"])), abs(float(coupling["stage_b_mixing_gamma_effective"])))
    mix_score = 0.9 if nonlinear_mix < 0.5 else 0.65 if nonlinear_mix < 1.0 else 0.30
    cap_shift = abs(float(row["peak_fractional_capacitance_shift"]))
    cap_score = 0.95 if cap_shift < 0.10 else 0.70 if cap_shift < 0.50 else 0.35 if cap_shift < 1.0 else 0.10
    max_voltage = max(float(row["peak_voltage_source_v"]), float(row["peak_voltage_generated_v"]), float(row["peak_voltage_target_v"]))
    max_current = max(float(row["peak_current_source_a"]), float(row["peak_current_generated_a"]), float(row["peak_current_target_a"]))
    scale_name = str(row["scale_preset"])
    if scale_name == "arbitrary-normalized-scale":
        hardware_score = 0.65
    elif scale_name == "audio-scale":
        hardware_score = 1.0 if max_voltage < 100.0 and max_current < 1.0 else 0.65 if max_voltage < 400.0 and max_current < 5.0 else 0.25
    else:
        hardware_score = 1.0 if max_voltage < 100.0 and max_current < 0.25 else 0.65 if max_voltage < 300.0 and max_current < 1.0 else 0.25
    budget_score = 1.0 if float(row["physical_energy_budget_error"]) < 0.001 else 0.8 if float(row["physical_energy_budget_error"]) < 0.005 else 0.2
    score = float(np.mean([q_score, coupling_score, mix_score, cap_score, hardware_score, budget_score]))
    if score >= 0.78:
        label = "physically plausible but needs circuit validation"
    elif score >= 0.55:
        label = "aggressive but not ruled out"
    else:
        label = "unrealistic without parameter refinement"
    return score, label


def aggregate_rows(rows: List[Dict[str, float | str]]) -> Dict[str, float | str]:
    discovery = [r for r in rows if str(r.get("row_type")) == "candidate_summary"]
    return {
        "row_type": "aggregate",
        "scale_presets": ";".join(sorted(set(str(r["scale_preset"]) for r in discovery))),
        "dt_levels": ";".join(sorted(set(str(r["dt_level"]) for r in discovery))),
        "physical_lc_bridge_expressed": str(True),
        "all_dt_all_scales_passed": str(all(str(r["passed_physical_lc_gates"]) == "True" for r in discovery)),
        "phase_lock_target": min(float(r["phase_lock_target"]) for r in discovery),
        "bridge_ratio": min(float(r["bridge_ratio"]) for r in discovery),
        "spectral_purity_target": min(float(r["spectral_purity_target"]) for r in discovery),
        "generated_envelope_cv": max(float(r["generated_envelope_cv"]) for r in discovery),
        "target_envelope_cv": max(float(r["target_envelope_cv"]) for r in discovery),
        "max_phase_jump": max(float(r["max_phase_jump"]) for r in discovery),
        "near_slip_count": max(float(r["near_slip_count"]) for r in discovery),
        "physical_energy_budget_error": max(float(r["physical_energy_budget_error"]) for r in discovery),
        "stored_energy_peak_j_min": min(float(r["stored_energy_peak_j"]) for r in discovery),
        "stored_energy_peak_j_max": max(float(r["stored_energy_peak_j"]) for r in discovery),
        "drive_work_j_min": min(float(r["drive_work_j"]) for r in discovery),
        "drive_work_j_max": max(float(r["drive_work_j"]) for r in discovery),
        "resistive_loss_j_min": min(float(r["resistive_loss_j"]) for r in discovery),
        "resistive_loss_j_max": max(float(r["resistive_loss_j"]) for r in discovery),
        "soft_limiter_loss_j_min": min(float(r["soft_limiter_loss_j"]) for r in discovery),
        "soft_limiter_loss_j_max": max(float(r["soft_limiter_loss_j"]) for r in discovery),
        "candidate_no_direct_8_drive": str(all(str(r["candidate_no_direct_8_drive"]) == "True" for r in discovery)),
        "candidate_no_direct_12_drive": str(all(str(r["candidate_no_direct_12_drive"]) == "True" for r in discovery)),
        "candidate_no_target_frequency_injection": str(all(str(r["candidate_no_target_frequency_injection"]) == "True" for r in discovery)),
        "realism_score_min": min(float(r["realism_score"]) for r in discovery),
        "realism_score_max": max(float(r["realism_score"]) for r in discovery),
        "realism_label": "; ".join(sorted(set(str(r["realism_label"]) for r in discovery))),
        "recommended_next_step": "SPICE/ngspice validation first, then physical parameter refinement and spatial phase-matching modeling",
    }


def run_physicalization(preset_names: Iterable[str], include_eighth: bool, seed: int,
                        include_all_timeseries: bool, timeseries_stride: int
                        ) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]], Dict[str, float | str], Dict[str, object]]:
    dt_levels = [("baseline_dt", BASE_DT), ("half_dt", BASE_DT * 0.5), ("quarter_dt", BASE_DT * 0.25)]
    if include_eighth:
        dt_levels.append(("eighth_dt", BASE_DT * 0.125))

    summary_rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    diagnostic_rows_by_dt: Dict[str, List[Dict[str, float | str]]] = {}
    sim_cache: Dict[str, Tuple[Dict[str, object], List[Dict[str, float | str]], Dict[str, object], Dict[str, float], Dict[str, float]]] = {}

    for idx, (dt_level, main_dt) in enumerate(dt_levels):
        row_seed = seed + idx * 337
        candidate_sim, candidate_ledger = simulate(CANDIDATE, row_seed, main_dt, BASE_TMAX)
        reference_sim, _reference_ledger = simulate(DIRECT_REFERENCE, row_seed + 13100, main_dt, BASE_TMAX)
        base_metrics = global_metrics(CANDIDATE, candidate_sim, reference_sim)
        diag_series, diag_summary = sliding_phase_diagnostics(CANDIDATE, candidate_sim, reference_sim)
        base_metrics.update(diag_summary)
        sim_cache[dt_level] = (candidate_sim, candidate_ledger, reference_sim, base_metrics, diag_summary)
        diagnostic_rows_by_dt[dt_level] = diag_series

    flags = direct_drive_flags(CANDIDATE)
    coupling = coupling_summary(CANDIDATE)

    for preset_name in preset_names:
        preset = SCALE_PRESETS[preset_name]
        lc_params = build_lc_params(CANDIDATE, preset)
        params_flat: Dict[str, float | str] = {}
        for idx, p in enumerate(lc_params, start=1):
            params_flat[f"f{idx}_hz"] = p.frequency_hz
            params_flat[f"L{idx}_h"] = p.inductance_h
            params_flat[f"C{idx}_f"] = p.capacitance_f
            params_flat[f"R{idx}_ohm"] = p.resistance_ohm
            params_flat[f"Q{idx}"] = p.q_factor
            params_flat[f"Q{idx}_class"] = p.q_class
            params_flat[f"voltage_scale_{idx}_v"] = p.voltage_scale_v
            params_flat[f"current_scale_{idx}_a_per_model_velocity"] = p.current_scale_a_per_model_velocity
            params_flat[f"drive_voltage_peak_{idx}_v"] = p.drive_voltage_peak_v
            params_flat[f"varactor_beta_{idx}_per_v2"] = p.varactor_beta_per_v2

        for dt_idx, (dt_level, main_dt) in enumerate(dt_levels):
            candidate_sim, candidate_ledger, _reference_sim, base_metrics, _diag_summary = sim_cache[dt_level]
            row: Dict[str, float | str] = {
                "row_type": "candidate_summary",
                "scale_preset": preset.name,
                "scale_description": preset.description,
                "dt_level": dt_level,
                "main_dt": main_dt,
                "effective_dt": main_dt / SUBSTEPS_PER_MAIN_STEP,
                "seed": seed + dt_idx * 337,
                "candidate_family": "4->8->12",
                "source_mode": 4,
                "generated_mode": 8,
                "target_mode": 12,
                "target_detuning": -0.08,
                "stage_A_offset": 0.040,
                "generated_damping_factor": 1.05,
                "A_to_B_coupling": 0.90,
                "limiter": 0.03,
                "substeps_per_main_step": SUBSTEPS_PER_MAIN_STEP,
                "bridge_ratio_reference_policy": "direct_source_plus_generated_ceiling_denominator_not_discovery",
            }
            row.update(flags)
            row.update(base_metrics)
            physical = physical_metrics(CANDIDATE, candidate_sim, preset)
            row.update(physical)
            row["physical_energy_budget_error"] = row["energy_budget_error_rel"]
            row["required_linear_coupling_k01_fraction"] = coupling["linear_k01_fraction_of_omega_product"]
            row["required_linear_coupling_k12_fraction"] = coupling["linear_k12_fraction_of_omega_product"]
            row["required_stage_a_mixing_gamma"] = coupling["stage_a_mixing_gamma"]
            row["required_stage_b_mixing_gamma_effective"] = coupling["stage_b_mixing_gamma_effective"]
            row["stage_b_phase_bias_deg"] = coupling["stage_b_phase_bias_deg"]
            row.update(params_flat)
            score, label = realism_score(row, lc_params, coupling)
            row["realism_score"] = score
            row["realism_label"] = label
            row["passed_physical_lc_gates"] = str(gate_row(row))
            summary_rows.append(row)

            if include_all_timeseries or dt_level == "baseline_dt":
                timeseries_rows.extend(physical_timeseries_rows(
                    preset.name,
                    dt_level,
                    CANDIDATE,
                    candidate_sim,
                    candidate_ledger,
                    preset,
                    stride=timeseries_stride,
                ))

        for diag_dt, diag_rows in diagnostic_rows_by_dt.items():
            for diag in diag_rows:
                item = dict(diag)
                item["row_type"] = "candidate_phase_window"
                item["scale_preset"] = preset.name
                item["dt_level"] = diag_dt
                item["time_seconds"] = float(item["time_mid"]) / scale_factor(preset)
                timeseries_rows.append(item)

    aggregate = aggregate_rows(summary_rows)
    report_context = {
        "candidate": asdict(CANDIDATE),
        "direct_reference": asdict(DIRECT_REFERENCE),
        "scale_presets": {name: asdict(SCALE_PRESETS[name]) for name in preset_names},
        "lc_params": {name: [asdict(p) for p in build_lc_params(CANDIDATE, SCALE_PRESETS[name])] for name in preset_names},
        "coupling": coupling,
        "expected_independent_metrics": EXPECTED_INDEPENDENT,
    }
    return [aggregate] + summary_rows, timeseries_rows, aggregate, report_context


def fmt(value: float | str, digits: int = 6) -> str:
    try:
        return f"{float(value):.{digits}g}"
    except (TypeError, ValueError):
        return str(value)


def write_report(out_dir: Path, rows: List[Dict[str, float | str]], aggregate: Dict[str, float | str],
                 report_context: Dict[str, object]) -> None:
    dt_rows = [r for r in rows if str(r.get("row_type")) == "candidate_summary"]
    baseline_by_scale = [r for r in dt_rows if str(r.get("dt_level")) == "baseline_dt"]
    lines = [
        "# Physical 4->8->12 LC Bridge",
        "",
        "This run translates the independently validated abstract 4->8->12 bridge into a three-resonator nonlinear LC interpretation. The simulated state remains normalized, while each preset supplies absolute resonant frequencies, capacitances, inductances, resistances, voltage/current scales, and joule-scale energy accounting.",
        "",
        "## Direct Answers",
        f"1. Can the independent 4->8->12 bridge be expressed as a nonlinear LC resonator system? yes, as a normalized three-LC model with conservative nonlinear capacitance/mixing terms and passive saturation loss; physical_lc_bridge_expressed={aggregate.get('physical_lc_bridge_expressed')}.",
        "2. Required L, C, R, Q, coupling, and nonlinear parameters are listed below for each scale preset; the summary CSV/JSON carry the exact numeric fields.",
        f"3. Plausibility: Q values are mild; linear coupling fractions are about {fmt(report_context['coupling']['linear_k01_fraction_of_omega_product'])} and {fmt(report_context['coupling']['linear_k12_fraction_of_omega_product'])}; nonlinear mixing is the aggressive part. Realism labels: {aggregate.get('realism_label')}.",
        f"4. Does the physical LC version preserve lock >0.90? {'yes' if float(aggregate.get('phase_lock_target', 0.0)) > 0.90 else 'no'}; worst lock={fmt(aggregate.get('phase_lock_target', 0.0))}.",
        f"5. Does bridge ratio remain >1.5? {'yes' if float(aggregate.get('bridge_ratio', 0.0)) > 1.5 else 'no'}; worst bridge ratio={fmt(aggregate.get('bridge_ratio', 0.0))}.",
        f"6. Does purity remain >0.80? {'yes' if float(aggregate.get('spectral_purity_target', 0.0)) > 0.80 else 'no'}; worst purity={fmt(aggregate.get('spectral_purity_target', 0.0))}.",
        f"7. Does budget remain <0.005? {'yes' if float(aggregate.get('physical_energy_budget_error', 1.0)) < 0.005 else 'no'}; worst budget={fmt(aggregate.get('physical_energy_budget_error', 0.0))}.",
        f"8. Are direct 8 drive, direct 12 drive, and target-frequency injection still absent? direct_8_absent={aggregate.get('candidate_no_direct_8_drive')}, direct_12_absent={aggregate.get('candidate_no_direct_12_drive')}, target_injection_absent={aggregate.get('candidate_no_target_frequency_injection')}.",
        f"9. Recommended next step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Baseline Presets",
    ]
    for row in baseline_by_scale:
        lines.append(
            f"- {row['scale_preset']}: f=({fmt(row['f1_hz'])}, {fmt(row['f2_hz'])}, {fmt(row['f3_hz'])}) Hz, "
            f"L=({fmt(row['L1_h'], 4)}, {fmt(row['L2_h'], 4)}, {fmt(row['L3_h'], 4)}) H, "
            f"C=({fmt(row['C1_f'], 4)}, {fmt(row['C2_f'], 4)}, {fmt(row['C3_f'], 4)}) F, "
            f"R=({fmt(row['R1_ohm'], 4)}, {fmt(row['R2_ohm'], 4)}, {fmt(row['R3_ohm'], 4)}) ohm, "
            f"Q=({fmt(row['Q1'], 4)}, {fmt(row['Q2'], 4)}, {fmt(row['Q3'], 4)}) "
            f"[{row['Q1_class']}, {row['Q2_class']}, {row['Q3_class']}], realism={fmt(row['realism_score'], 3)} ({row['realism_label']})."
        )
        lines.append(
            f"  Metrics: lock={fmt(row['phase_lock_target'])}, bridge={fmt(row['bridge_ratio'])}, purity={fmt(row['spectral_purity_target'])}, "
            f"budget={fmt(row['physical_energy_budget_error'])}, gen_cv={fmt(row['generated_envelope_cv'])}, target_cv={fmt(row['target_envelope_cv'])}, "
            f"max_jump={fmt(row['max_phase_jump'])}, near_slips={fmt(row['near_slip_count'])}."
        )
        lines.append(
            f"  Energy/peaks: stored_peak={fmt(row['stored_energy_peak_j'])} J, drive_work={fmt(row['drive_work_j'])} J, "
            f"resistive_loss={fmt(row['resistive_loss_j'])} J, soft_limiter_loss={fmt(row['soft_limiter_loss_j'])} J, "
            f"peak_V=({fmt(row['peak_voltage_source_v'])}, {fmt(row['peak_voltage_generated_v'])}, {fmt(row['peak_voltage_target_v'])}) V, "
            f"peak_I=({fmt(row['peak_current_source_a'])}, {fmt(row['peak_current_generated_a'])}, {fmt(row['peak_current_target_a'])}) A."
        )
    lines.extend([
        "",
        "## Model Notes",
        "",
        "- Each resonator is represented by `L_i`, `C_i`, and `R_i` with `f_i = 1 / (2*pi*sqrt(L_i*C_i))` and `Q_i = omega_i*L_i/R_i`.",
        "- The source drive is a voltage/current-equivalent force applied only to resonator 1. The generated and target resonators receive no direct drive.",
        "- The linear coupling coefficients are weak normalized LC coupling terms. The nonlinear varactor and mixing coefficients are the intentionally aggressive bridge mechanism.",
        "- The soft limiter is passive saturation/loss; there is no active limiter work term in this first physicalization.",
        "- `direct_source_plus_generated_reference_ceiling` is used only as the bridge-ratio denominator and is never a discovery row.",
        "",
        "## Candidate Constants",
        "```json",
        json.dumps(report_context["candidate"], indent=2),
        "```",
    ])
    (out_dir / "README_PHYSICAL_412_LC_BRIDGE.md").write_text("\n".join(lines), encoding="utf-8")


def parse_presets(raw: str) -> List[str]:
    if raw.strip().lower() == "all":
        return list(SCALE_PRESETS.keys())
    names = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in names if name not in SCALE_PRESETS]
    if unknown:
        raise ValueError(f"Unknown scale preset(s): {', '.join(unknown)}. Valid: {', '.join(SCALE_PRESETS)}")
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Physical nonlinear LC interpretation of the independent 4->8->12 bridge.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--seed", type=int, default=151369, help="Baseline deterministic seed; half/quarter add fixed offsets.")
    parser.add_argument("--presets", default="all", help="Comma-separated presets or 'all'.")
    parser.add_argument("--eighth", action="store_true", help="Also run eighth-dt validation.")
    parser.add_argument("--all-timeseries", action="store_true", help="Write all dt levels to the timeseries CSV. By default, full physical samples are baseline-only plus all phase windows.")
    parser.add_argument("--timeseries-stride", type=int, default=1, help="Stride for sampled physical timeseries rows.")
    args = parser.parse_args()

    presets = parse_presets(args.presets)
    out_dir = ensure_dir(Path(args.out))
    summary_rows, timeseries_rows, aggregate, report_context = run_physicalization(
        presets,
        include_eighth=args.eighth,
        seed=args.seed,
        include_all_timeseries=args.all_timeseries,
        timeseries_stride=args.timeseries_stride,
    )
    write_csv(out_dir / "physical_412_summary.csv", summary_rows)
    write_csv(out_dir / "physical_412_timeseries.csv", timeseries_rows)
    (out_dir / "physical_412_summary.json").write_text(json.dumps({
        "aggregate": aggregate,
        "rows": summary_rows,
        "context": report_context,
    }, indent=2), encoding="utf-8")
    write_report(out_dir, summary_rows, aggregate, report_context)
    print(f"Physical 4->8->12 LC bridge written to: {out_dir.resolve()}")
    print(f"all_dt_all_scales_passed={aggregate['all_dt_all_scales_passed']}")
    print(f"worst_lock={float(aggregate['phase_lock_target']):.6g}")
    print(f"worst_bridge_ratio={float(aggregate['bridge_ratio']):.6g}")
    print(f"worst_purity={float(aggregate['spectral_purity_target']):.6g}")
    print(f"worst_budget={float(aggregate['physical_energy_budget_error']):.6g}")
    print(f"realism={aggregate['realism_label']}")


if __name__ == "__main__":
    main()
