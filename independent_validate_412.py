#!/usr/bin/env python3
"""Independent validator for the strict 4->8->12 harmonic bridge candidate.

This script intentionally does not import tesla_369_lab.py or call any
experiment mode. It reimplements only the three-mode oscillator, the fixed
4->8->12 candidate constants, RK4 substep integration, and the metrics needed
to audit the candidate.
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


BASE_HZ = 0.045
BASE_DT = 0.090
BASE_TMAX = 54.0 * 1.25 * 4.0
SAMPLE_EVERY = 1
SUBSTEPS_PER_MAIN_STEP = 4
OUT_DIR = Path("runs") / "independent_validate_412"

EXPECTED_MAIN = {
    "phase_lock_target": 0.992,
    "bridge_ratio": 1.589,
    "spectral_purity_target": 0.923,
    "energy_budget_error": 0.0000510,
    "generated_envelope_cv": 0.135,
    "max_phase_jump": 0.972,
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


CANDIDATE = BridgeConfig(
    name="independent_412_candidate",
    mode_freqs=(4.0, 8.0354, 11.907835129474883),
    drive_freqs=(4.0,),
    drive_modes=(0,),
    drive_phases=(0.0,),
    note=(
        "Explicit effective constants for target detuning -0.08, Stage A offset +0.040, "
        "generated damping factor 1.05, A->B coupling 0.90, limiter 0.03. "
        "Candidate drive is source-only: no direct 8 drive, no direct 12 drive."
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
        "Ceiling denominator for bridge ratio only. This row uses direct 8 drive and "
        "is never a discovery candidate."
    ),
)


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
    # The validated limiter is a static passive soft-limiter proxy already folded
    # into varactor, damping, and spark constants. It has no adaptive work term.
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
    zeta = np.asarray([
        0.018 * config.stage_a_damping,
        0.012 * config.stage_b_damping,
        0.008 * config.receiver_damping,
    ])

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


def gate_row(row: Dict[str, float | str]) -> bool:
    return (
        float(row["phase_lock_target"]) > 0.90
        and float(row["bridge_ratio"]) > 1.5
        and float(row["spectral_purity_target"]) > 0.80
        and float(row["energy_budget_error"]) < 0.005
        and float(row["generated_envelope_cv"]) < 0.25
        and float(row["max_phase_jump"]) < 1.0
        and float(row["near_slip_count"]) == 0.0
        and str(row["candidate_no_direct_2f_drive"]) == "True"
        and str(row["candidate_no_direct_3f_drive"]) == "True"
        and str(row["candidate_no_target_frequency_injection"]) == "True"
    )


def material_differences(aggregate: Dict[str, float | str]) -> List[str]:
    thresholds = {
        "phase_lock_target": 0.02,
        "bridge_ratio": 0.12,
        "spectral_purity_target": 0.05,
        "energy_budget_error": 0.001,
        "generated_envelope_cv": 0.04,
        "max_phase_jump": 0.12,
        "near_slip_count": 0.1,
    }
    diffs: List[str] = []
    for key, threshold in thresholds.items():
        observed = float(aggregate.get(key, 0.0))
        expected = float(EXPECTED_MAIN[key])
        if abs(observed - expected) > threshold:
            diffs.append(f"{key}: observed={observed:.6g}, expected~={expected:.6g}, delta={observed - expected:.6g}")
    return diffs


def run_validation(include_eighth: bool, out_dir: Path, seed: int) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]], Dict[str, float | str]]:
    dt_levels = [("baseline_dt", BASE_DT), ("half_dt", BASE_DT * 0.5), ("quarter_dt", BASE_DT * 0.25)]
    if include_eighth:
        dt_levels.append(("eighth_dt", BASE_DT * 0.125))

    summary_rows: List[Dict[str, float | str]] = []
    timeseries_rows: List[Dict[str, float | str]] = []
    diagnostic_rows: List[Dict[str, float | str]] = []

    for idx, (dt_level, main_dt) in enumerate(dt_levels):
        row_seed = seed + idx * 337
        candidate_sim, candidate_ledger = simulate(CANDIDATE, row_seed, main_dt, BASE_TMAX)
        reference_sim, _reference_ledger = simulate(DIRECT_REFERENCE, row_seed + 13100, main_dt, BASE_TMAX)
        row: Dict[str, float | str] = {
            "dt_level": dt_level,
            "main_dt": main_dt,
            "effective_dt": main_dt / SUBSTEPS_PER_MAIN_STEP,
            "seed": row_seed,
            "candidate_family": "4->8->12",
            "target_detuning": -0.08,
            "stage_A_offset": 0.040,
            "generated_damping_factor": 1.05,
            "A_to_B_coupling": 0.90,
            "limiter": 0.03,
            "substeps_per_main_step": SUBSTEPS_PER_MAIN_STEP,
            "candidate_no_direct_2f_drive": str(not any(abs(freq - CANDIDATE.target_6) < 1e-9 and mode == 1 for freq, mode in zip(CANDIDATE.drive_freqs, CANDIDATE.drive_modes))),
            "candidate_no_direct_3f_drive": str(not any(abs(freq - CANDIDATE.target_9) < 1e-9 and mode == 2 for freq, mode in zip(CANDIDATE.drive_freqs, CANDIDATE.drive_modes))),
            "candidate_no_target_frequency_injection": str(not any(abs(freq - CANDIDATE.target_9) < 1e-9 and mode == 2 for freq, mode in zip(CANDIDATE.drive_freqs, CANDIDATE.drive_modes))),
            "bridge_ratio_reference_policy": "direct_source_plus_generated_ceiling_denominator_not_discovery",
        }
        row.update(global_metrics(CANDIDATE, candidate_sim, reference_sim))
        diag_series, diag_summary = sliding_phase_diagnostics(CANDIDATE, candidate_sim, reference_sim)
        row.update(diag_summary)
        row["energy_budget_error"] = float(candidate_sim["energy_budget_error_rel"])
        row["absolute_budget_error"] = abs(float(candidate_sim["energy_budget_error_abs"]))
        row["max_energy_budget_error"] = float(candidate_sim["max_energy_budget_error_rel"])
        row["damping_loss"] = float(candidate_sim["damping_loss"])
        row["limiter_work"] = float(candidate_sim["limiter_work"])
        row["adaptive_damping_work"] = float(candidate_sim["adaptive_damping_work"])
        row["spark_loss"] = float(candidate_sim["spark_loss"])
        row["net_drive_work"] = float(candidate_sim["net_input_work"])
        row["positive_input_work"] = float(candidate_sim["positive_input_work"])
        row["passed_gates"] = str(gate_row(row))
        summary_rows.append(row)

        ledger_by_time = {float(item["time"]): item for item in candidate_ledger}
        times = candidate_sim["times"]  # type: ignore[index]
        energy = candidate_sim["energy"]  # type: ignore[index]
        qs = candidate_sim["qs"]  # type: ignore[index]
        for sample_idx, t in enumerate(times):
            ledger = ledger_by_time.get(float(t), {})
            timeseries_rows.append({
                "dt_level": dt_level,
                "run": "candidate",
                "time": float(t),
                "q_source": float(qs[sample_idx, 0]),
                "q_generated": float(qs[sample_idx, 1]),
                "q_target": float(qs[sample_idx, 2]),
                "energy_source": float(energy[sample_idx, 0]),
                "energy_generated": float(energy[sample_idx, 1]),
                "energy_target": float(energy[sample_idx, 2]),
                "energy_budget_error": float(ledger.get("energy_budget_error_rel", "")) if ledger else "",
                "drive_input_work": float(ledger.get("drive_input_work", "")) if ledger else "",
                "damping_loss": float(ledger.get("damping_loss", "")) if ledger else "",
                "limiter_work": float(ledger.get("limiter_work", "")) if ledger else "",
                "spark_loss": float(ledger.get("spark_loss", "")) if ledger else "",
            })
        for diag in diag_series:
            item = dict(diag)
            item["dt_level"] = dt_level
            item["run"] = "candidate_phase_windows"
            diagnostic_rows.append(item)

    aggregate: Dict[str, float | str] = {
        "dt_level": "aggregate",
        "candidate_family": "4->8->12",
        "target_detuning": -0.08,
        "stage_A_offset": 0.040,
        "generated_damping_factor": 1.05,
        "A_to_B_coupling": 0.90,
        "limiter": 0.03,
        "phase_lock_target": min(float(r["phase_lock_target"]) for r in summary_rows),
        "bridge_ratio": min(float(r["bridge_ratio"]) for r in summary_rows),
        "spectral_purity_target": min(float(r["spectral_purity_target"]) for r in summary_rows),
        "energy_budget_error": max(float(r["energy_budget_error"]) for r in summary_rows),
        "absolute_budget_error": max(float(r["absolute_budget_error"]) for r in summary_rows),
        "generated_envelope_cv": max(float(r["generated_envelope_cv"]) for r in summary_rows),
        "target_envelope_cv": max(float(r["target_envelope_cv"]) for r in summary_rows),
        "max_phase_jump": max(float(r["max_phase_jump"]) for r in summary_rows),
        "near_slip_count": max(float(r["near_slip_count"]) for r in summary_rows),
        "phase_slip_count": max(float(r["phase_slip_count"]) for r in summary_rows),
        "all_dt_passed": str(all(str(r["passed_gates"]) == "True" for r in summary_rows)),
        "dt_levels": ";".join(str(r["dt_level"]) for r in summary_rows),
        "candidate_no_direct_2f_drive": str(all(str(r["candidate_no_direct_2f_drive"]) == "True" for r in summary_rows)),
        "candidate_no_direct_3f_drive": str(all(str(r["candidate_no_direct_3f_drive"]) == "True" for r in summary_rows)),
        "candidate_no_target_frequency_injection": str(all(str(r["candidate_no_target_frequency_injection"]) == "True" for r in summary_rows)),
        "bridge_ratio_reference_policy": "direct_source_plus_generated_ceiling_denominator_not_discovery",
    }
    diffs = material_differences(aggregate)
    aggregate["material_differences_from_main_harness"] = "; ".join(diffs) if diffs else "none"
    aggregate["independent_validation_passed"] = str(str(aggregate["all_dt_passed"]) == "True" and not diffs)
    return [aggregate] + summary_rows, timeseries_rows + diagnostic_rows, aggregate


def write_report(out_dir: Path, rows: List[Dict[str, float | str]], aggregate: Dict[str, float | str]) -> None:
    dt_rows = [r for r in rows if str(r.get("dt_level")) != "aggregate"]
    passed = str(aggregate.get("independent_validation_passed")) == "True"
    lines = [
        "# Independent 4->8->12 Validation",
        "",
        "This standalone script reimplements the three-mode equations and RK4 substep ledger for the strict 4->8->12 candidate. It does not import or call `tesla_369_lab.py` or any experiment mode.",
        "",
        "## Direct Answers",
        f"1. Does the independent script reproduce the 4->8->12 candidate? {'yes' if passed else 'partly/no'}; independent_validation_passed={aggregate.get('independent_validation_passed')}.",
        f"2. Are budget, lock, bridge ratio, purity, CV, and max jump all preserved? all_dt_passed={aggregate.get('all_dt_passed')}; lock={float(aggregate.get('phase_lock_target', 0.0)):.6g}, bridge={float(aggregate.get('bridge_ratio', 0.0)):.6g}, purity={float(aggregate.get('spectral_purity_target', 0.0)):.6g}, budget={float(aggregate.get('energy_budget_error', 0.0)):.6g}, gen_cv={float(aggregate.get('generated_envelope_cv', 0.0)):.6g}, jump={float(aggregate.get('max_phase_jump', 0.0)):.6g}.",
        f"3. Does the result survive dt refinement? {'yes' if aggregate.get('all_dt_passed') == 'True' else 'no'}; dt_levels={aggregate.get('dt_levels')}.",
        f"4. Does any metric differ materially from the main harness? {aggregate.get('material_differences_from_main_harness')}.",
        f"5. Should the candidate be marked independent_validation_passed? {aggregate.get('independent_validation_passed')}.",
        "",
        "## Candidate Constants",
        "```json",
        json.dumps(asdict(CANDIDATE), indent=2),
        "```",
        "",
        "Discovery candidate drive policy: source-only 4 drive. No direct 8 drive, no direct 12 drive, no target-frequency injection.",
        "Bridge ratio denominator policy: a direct source+generated reference is simulated only as a ceiling denominator, never as a discovery row.",
        "",
        "## Dt Rows",
    ]
    for row in dt_rows:
        lines.append(
            f"- {row.get('dt_level')}: passed={row.get('passed_gates')}, lock={float(row.get('phase_lock_target', 0.0)):.6g}, "
            f"bridge={float(row.get('bridge_ratio', 0.0)):.6g}, purity={float(row.get('spectral_purity_target', 0.0)):.6g}, "
            f"budget={float(row.get('energy_budget_error', 0.0)):.6g}, abs_budget={float(row.get('absolute_budget_error', 0.0)):.6g}, "
            f"gen_cv={float(row.get('generated_envelope_cv', 0.0)):.6g}, target_cv={float(row.get('target_envelope_cv', 0.0)):.6g}, "
            f"jump={float(row.get('max_phase_jump', 0.0)):.6g}, near_slips={float(row.get('near_slip_count', 0.0)):.6g}, "
            f"limiter_work={float(row.get('limiter_work', 0.0)):.6g}, adaptive_work={float(row.get('adaptive_damping_work', 0.0)):.6g}"
        )
    (out_dir / "README_INDEPENDENT_412_VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone independent validation for the 4->8->12 harmonic bridge candidate.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--seed", type=int, default=151369, help="Baseline deterministic seed; half/quarter add fixed offsets.")
    parser.add_argument("--eighth", action="store_true", help="Also run eighth-dt validation.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    summary_rows, timeseries_rows, aggregate = run_validation(args.eighth, out_dir, args.seed)
    write_csv(out_dir / "independent_412_summary.csv", summary_rows)
    write_csv(out_dir / "independent_412_timeseries.csv", timeseries_rows)
    (out_dir / "independent_412_summary.json").write_text(json.dumps({
        "aggregate": aggregate,
        "rows": summary_rows,
        "expected_main_harness_metrics": EXPECTED_MAIN,
    }, indent=2), encoding="utf-8")
    write_report(out_dir, summary_rows, aggregate)
    print(f"Independent 4->8->12 validation written to: {out_dir.resolve()}")
    print(f"independent_validation_passed={aggregate['independent_validation_passed']}")
    print(f"all_dt_passed={aggregate['all_dt_passed']}")


if __name__ == "__main__":
    main()
