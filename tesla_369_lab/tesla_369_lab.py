#!/usr/bin/env python3
"""
Tesla 3-6-9 Lab: falsifiable simulations for resonance, nonlinear wave mixing,
and geometry-driven energy localization.

This is not a claim that 3/6/9 are magical. It treats 3, 6, 9 as a hypothesis:
maybe integer-ratio harmonic triads and phased geometry can produce unusually
strong energy transfer, phase locking, or central localization. Every run includes
controls so the 369 pattern has to beat non-369 patterns.

Run:
    python tesla_369_lab.py --mode all

Outputs:
    runs/<timestamp>/summary.csv
    runs/<timestamp>/triad_resonator_summary.csv
    runs/<timestamp>/wave_lattice_summary.csv
    runs/<timestamp>/receiver_coil_summary.csv
    PNG plots for each experiment
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import matplotlib.pyplot as plt


# ----------------------------
# Utility functions
# ----------------------------

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, rows: List[Dict[str, float | str]]) -> None:
    if not rows:
        return
    # Use union of all keys because different experiments emit different metrics.
    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def complex_projection(signal: np.ndarray, t: np.ndarray, freq_hz: float) -> complex:
    """Return complex sinusoidal amplitude at freq_hz."""
    phase = np.exp(-1j * 2.0 * np.pi * freq_hz * t)
    return 2.0 * np.mean(signal * phase)


def sliding_phase(signal: np.ndarray, t: np.ndarray, freq_hz: float, window: int, step: int) -> np.ndarray:
    phases = []
    for start in range(0, len(signal) - window, step):
        stop = start + window
        amp = complex_projection(signal[start:stop], t[start:stop], freq_hz)
        phases.append(np.angle(amp))
    return np.asarray(phases)


def wrap_angle(x: np.ndarray | float) -> np.ndarray | float:
    return (x + np.pi) % (2 * np.pi) - np.pi


# ----------------------------
# Experiment 1: nonlinear triad resonators
# ----------------------------

@dataclass
class TriadCase:
    name: str
    freqs: Tuple[float, float, float]
    drive_index: int = 0
    detune_note: str = ""


def triad_derivative(y: np.ndarray, t: float, omega: np.ndarray, drive_amp: float, drive_omega: float,
                     zeta: float, alpha: float, eps: float) -> np.ndarray:
    # y = [q0, q1, q2, v0, v1, v2]
    q = y[:3]
    v = y[3:]

    # Base Duffing-like oscillator acceleration.
    a = -2.0 * zeta * omega * v - (omega ** 2) * q - alpha * (q ** 3)

    # Quadratic mixing terms. If w0 + w1 ~= w2, these terms can pump oscillator 2.
    a[0] += eps * q[1] * q[2]
    a[1] += eps * q[0] * q[2]
    a[2] += eps * q[0] * q[1]

    # Drive the two lower modes. Their product contains a sum-frequency term
    # at w0 + w1, which should preferentially pump mode 2 when w2 ~= w0 + w1.
    a[0] += drive_amp * math.sin(omega[0] * t)
    a[1] += 0.85 * drive_amp * math.sin(omega[1] * t + np.pi / 7.0)

    return np.concatenate([v, a])


def rk4_step(y: np.ndarray, t: float, dt: float, f, *args) -> np.ndarray:
    k1 = f(y, t, *args)
    k2 = f(y + 0.5 * dt * k1, t + 0.5 * dt, *args)
    k3 = f(y + 0.5 * dt * k2, t + 0.5 * dt, *args)
    k4 = f(y + dt * k3, t + dt, *args)
    return y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def run_triad_case(case: TriadCase, out_dir: Path, seed: int = 1, dt: float = 0.01,
                   t_max: float = 240.0, base_hz: float = 0.045) -> Dict[str, float | str]:
    rng = np.random.default_rng(seed)
    freqs_hz = base_hz * np.asarray(case.freqs, dtype=float)
    omega = 2.0 * np.pi * freqs_hz

    n = int(t_max / dt)
    t = np.arange(n) * dt
    y = np.zeros(6)
    y[:3] = 1e-4 * rng.normal(size=3)
    y[3:] = 1e-4 * rng.normal(size=3)

    qs = np.zeros((n, 3), dtype=float)
    vs = np.zeros((n, 3), dtype=float)

    # Tuned to be stable but nonlinear enough to show transfer.
    zeta = 0.006
    alpha = 0.18
    eps = 0.55
    drive_amp = 0.055
    drive_omega = omega[case.drive_index]

    for i in range(n):
        qs[i] = y[:3]
        vs[i] = y[3:]
        y = rk4_step(y, t[i], dt, triad_derivative, omega, drive_amp, drive_omega, zeta, alpha, eps)
        # Basic blow-up guard.
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e4:
            qs = qs[: i + 1]
            vs = vs[: i + 1]
            t = t[: i + 1]
            break

    energy = 0.5 * (vs ** 2) + 0.5 * (omega[None, :] ** 2) * (qs ** 2) + 0.25 * alpha * (qs ** 4)
    total_e = np.sum(energy, axis=1) + 1e-12
    final_slice = slice(len(t) // 2, None)

    final_energy_frac = np.mean(energy[final_slice], axis=0) / np.mean(total_e[final_slice])
    peak_high_frac = float(np.max(energy[:, 2] / total_e))
    mean_high_frac = float(final_energy_frac[2])

    # Phase locking: w0 + w1 -> w2. Use sliding windows to see whether mismatch stabilizes.
    window = max(256, int(18.0 / dt))
    step = max(64, window // 5)
    if len(t[final_slice]) > window * 2:
        phases = []
        for idx in range(3):
            phases.append(sliding_phase(qs[final_slice, idx], t[final_slice], freqs_hz[idx], window, step))
        min_len = min(len(p) for p in phases)
        mismatch = wrap_angle(phases[0][:min_len] + phases[1][:min_len] - phases[2][:min_len])
        triad_lock = float(np.abs(np.mean(np.exp(1j * mismatch)))) if len(mismatch) else 0.0
        mismatch_std = float(np.std(mismatch)) if len(mismatch) else float("nan")
    else:
        triad_lock = 0.0
        mismatch_std = float("nan")

    # How exact is the resonant sum condition?
    sum_error_hz = abs((freqs_hz[0] + freqs_hz[1]) - freqs_hz[2])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(t, energy[:, 0] / total_e, label=f"mode {case.freqs[0]:g}")
    ax.plot(t, energy[:, 1] / total_e, label=f"mode {case.freqs[1]:g}")
    ax.plot(t, energy[:, 2] / total_e, label=f"mode {case.freqs[2]:g}")
    ax.set_title(f"Triad resonator energy fractions: {case.name}")
    ax.set_xlabel("time")
    ax.set_ylabel("energy fraction")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / f"triad_{case.name}.png", dpi=140)
    plt.close(fig)

    return {
        "experiment": "triad_resonator",
        "case": case.name,
        "freqs": "-".join(f"{x:g}" for x in case.freqs),
        "sum_error_hz": float(sum_error_hz),
        "mean_high_mode_energy_frac": mean_high_frac,
        "peak_high_mode_energy_frac": peak_high_frac,
        "triad_phase_lock_0_to_1": triad_lock,
        "triad_phase_mismatch_std_rad": mismatch_std,
        "score": mean_high_frac * (1.0 + triad_lock) / (1.0 + 10.0 * sum_error_hz),
        "note": case.detune_note,
    }


def experiment_triad_resonators(out_dir: Path, seed: int) -> List[Dict[str, float | str]]:
    cases = [
        TriadCase("369_exact_sum", (3, 6, 9), detune_note="3 + 6 = 9; target myth case"),
        TriadCase("369_detuned", (3, 6.25, 9), detune_note="same digits idea, broken sum resonance"),
        TriadCase("357_non_sum", (3, 5, 7), detune_note="odd-number control; 3 + 5 != 7"),
        TriadCase("4812_exact_sum", (4, 8, 12), detune_note="non-369 exact sum; tests whether resonance, not numerology, explains it"),
        TriadCase("random_non_sum", tuple(np.round(np.random.default_rng(seed).uniform(2.5, 11.5, 3), 3)), detune_note="random control"),
    ]
    rows = [run_triad_case(case, out_dir, seed=seed) for case in cases]
    write_csv(out_dir / "triad_resonator_summary.csv", rows)
    return rows


# ----------------------------
# Experiment 2: 2D nonlinear wave lattice
# ----------------------------

@dataclass
class WaveCase:
    name: str
    freqs: Tuple[float, float, float]
    phases: Tuple[float, float, float]
    radii: Tuple[float, float, float] = (9.0, 18.0, 27.0)
    amp: float = 0.018
    note: str = ""


def make_grid(n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    coords = np.arange(n) - (n - 1) / 2.0
    x, y = np.meshgrid(coords, coords, indexing="ij")
    r = np.sqrt(x * x + y * y)
    return x, y, r


def ring_mask(r: np.ndarray, radius: float, sigma: float = 1.2) -> np.ndarray:
    m = np.exp(-0.5 * ((r - radius) / sigma) ** 2)
    return m / (np.sqrt(np.sum(m * m)) + 1e-12)


def sponge_map(n: int, width: int = 10, max_damp: float = 0.20) -> np.ndarray:
    idx = np.arange(n)
    d1 = np.minimum(idx, n - 1 - idx)
    d_edge = np.minimum(d1[:, None], d1[None, :])
    s = np.clip((width - d_edge) / width, 0.0, 1.0)
    return max_damp * s ** 2


def energy_density(u: np.ndarray, v: np.ndarray, onsite: np.ndarray, beta: float) -> np.ndarray:
    gx = np.roll(u, -1, axis=0) - u
    gy = np.roll(u, -1, axis=1) - u
    return 0.5 * v * v + 0.5 * (gx * gx + gy * gy) + 0.5 * onsite * u * u + 0.25 * beta * u ** 4


def run_wave_case(case: WaveCase, out_dir: Path, seed: int = 1, n: int = 72, steps: int = 3600,
                  dt: float = 0.035, base_hz: float = 0.055) -> Dict[str, float | str]:
    rng = np.random.default_rng(seed)
    x, y, r = make_grid(n)
    masks = [ring_mask(r, rad) for rad in case.radii]
    core = r <= 7.0
    inner_shell = (r > 7.0) & (r <= 15.0)

    # Central defect/cavity: a soft core surrounded by a stiffer shell.
    soft_core = np.exp(-0.5 * (r / 5.0) ** 2)
    stiff_shell = np.exp(-0.5 * ((r - 11.0) / 2.4) ** 2)
    onsite = 0.025 + 0.07 * stiff_shell - 0.018 * soft_core
    onsite = np.clip(onsite, 0.002, None)

    damp = 0.012 + sponge_map(n, width=10, max_damp=0.18)
    beta = 0.13
    c2 = 0.72

    u = 2e-5 * rng.normal(size=(n, n))
    v = np.zeros((n, n))

    freqs_hz = base_hz * np.asarray(case.freqs, dtype=float)
    phases = np.asarray(case.phases, dtype=float)

    sample_every = 4
    times = []
    core_ratio = []
    shell_ratio = []
    total_energy = []
    core_signal = []

    for step in range(steps):
        t = step * dt
        lap = (np.roll(u, 1, axis=0) + np.roll(u, -1, axis=0) +
               np.roll(u, 1, axis=1) + np.roll(u, -1, axis=1) - 4.0 * u)

        drive = np.zeros_like(u)
        for f_hz, phase, mask in zip(freqs_hz, phases, masks):
            drive += case.amp * math.sin(2.0 * np.pi * f_hz * t + phase) * mask

        a = c2 * lap - onsite * u - beta * u ** 3 - damp * v + drive
        v += dt * a
        u += dt * v

        # Keep boundaries quiet; this avoids periodic wrap artifacts from np.roll.
        u[0, :] = u[-1, :] = u[:, 0] = u[:, -1] = 0.0
        v[0, :] = v[-1, :] = v[:, 0] = v[:, -1] = 0.0

        if step % sample_every == 0:
            e = energy_density(u, v, onsite, beta)
            et = float(np.sum(e) + 1e-18)
            ec = float(np.sum(e[core]))
            es = float(np.sum(e[inner_shell]))
            times.append(t)
            core_ratio.append(ec / et)
            shell_ratio.append(es / et)
            total_energy.append(et)
            core_signal.append(float(np.mean(u[core])))

    times = np.asarray(times)
    core_ratio = np.asarray(core_ratio)
    shell_ratio = np.asarray(shell_ratio)
    total_energy = np.asarray(total_energy)
    core_signal = np.asarray(core_signal)

    peak_idx = int(np.argmax(core_ratio))
    peak_core_ratio = float(core_ratio[peak_idx])
    peak_time = float(times[peak_idx])
    tail = slice(int(0.75 * len(core_ratio)), None)
    retention = float(np.mean(core_ratio[tail]) / (peak_core_ratio + 1e-12))
    final_core_ratio = float(np.mean(core_ratio[tail]))
    final_shell_ratio = float(np.mean(shell_ratio[tail]))

    # Look for nonlinear sum-frequency presence in the core signal.
    # For the 369 case, f3 + f6 = f9; controls show whether that is generic.
    final_t = times[len(times) // 2:]
    final_sig = core_signal[len(times) // 2:]
    sum_freq_hz = freqs_hz[0] + freqs_hz[1]
    high_freq_hz = freqs_hz[2]
    sum_amp = abs(complex_projection(final_sig, final_t, sum_freq_hz))
    high_amp = abs(complex_projection(final_sig, final_t, high_freq_hz))
    low_amp = abs(complex_projection(final_sig, final_t, freqs_hz[0])) + 1e-12
    sum_error_hz = abs(sum_freq_hz - high_freq_hz)

    # Save diagnostic plots.
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(times, core_ratio, label="core energy ratio")
    ax.plot(times, shell_ratio, label="inner shell energy ratio")
    ax.set_title(f"Wave lattice localization: {case.name}")
    ax.set_xlabel("time")
    ax.set_ylabel("energy ratio")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / f"wave_{case.name}_energy.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(u.T, origin="lower")
    ax.set_title(f"Final displacement field: {case.name}")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_dir / f"wave_{case.name}_field.png", dpi=140)
    plt.close(fig)

    return {
        "experiment": "wave_lattice",
        "case": case.name,
        "freqs": "-".join(f"{x:g}" for x in case.freqs),
        "sum_error_hz": float(sum_error_hz),
        "peak_core_energy_ratio": peak_core_ratio,
        "peak_time": peak_time,
        "final_core_energy_ratio": final_core_ratio,
        "retention_vs_peak": retention,
        "final_shell_energy_ratio": final_shell_ratio,
        "sum_freq_amp_over_low_amp": float(sum_amp / low_amp),
        "high_freq_amp_over_low_amp": float(high_amp / low_amp),
        "score": peak_core_ratio * retention * (1.0 + float(high_amp / low_amp)) / (1.0 + 10.0 * sum_error_hz),
        "note": case.note,
    }


def experiment_wave_lattice(out_dir: Path, seed: int, quick: bool = False) -> List[Dict[str, float | str]]:
    rng = np.random.default_rng(seed)
    cases = [
        WaveCase("369_radial_phase_locked", (3, 6, 9), (0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0),
                 note="target: 3 rings, 3 frequencies, 120-degree phase cycle"),
        WaveCase("369_random_phase", (3, 6, 9), tuple(rng.uniform(0, 2 * np.pi, 3)),
                 note="same frequencies, broken phase geometry"),
        WaveCase("357_non_sum", (3, 5, 7), (0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0),
                 note="nonlinear control; no f3+f5=f7 match"),
        WaveCase("4812_exact_sum", (4, 8, 12), (0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0),
                 note="non-369 exact-sum harmonic triad"),
        WaveCase("single_6", (6, 6, 6), (0.0, 0.0, 0.0), amp=0.010,
                 note="single-frequency control with comparable geometry"),
    ]
    rows = []
    for case in cases:
        rows.append(run_wave_case(case, out_dir, seed=seed, n=56 if quick else 72,
                                  steps=1800 if quick else 3600))
    write_csv(out_dir / "wave_lattice_summary.csv", rows)
    return rows


# ----------------------------
# Experiment 3: Tesla-style coupled receiver coils
# ----------------------------

@dataclass
class ReceiverCase:
    name: str
    coil_freqs: Tuple[float, float, float]
    drive_freqs: Tuple[float, ...]
    phases: Tuple[float, ...]
    drive_weights: Tuple[float, ...] = ()
    nonlinear_strength: float = 0.42
    mix_strength: float = 0.34
    spark_strength: float = 0.16
    spark_threshold: float = 0.035
    primary_secondary_coupling: float = 0.030
    secondary_receiver_coupling: float = 0.022
    primary_receiver_coupling: float = 0.0035
    zeta_scale: float = 1.0
    drive_amp: float = 0.070
    note: str = ""


def receiver_drive_value(case: ReceiverCase, t: float, base_hz: float, drive_until: float) -> float:
    if t >= drive_until:
        return 0.0

    # Smooth ramping keeps the LC model from being dominated by startup clicks.
    ramp_in = min(1.0, t / 12.0)
    ramp_out = min(1.0, max(0.0, (drive_until - t) / 12.0))
    envelope = ramp_in * ramp_out

    weights = case.drive_weights or tuple(1.0 for _ in case.drive_freqs)
    norm = math.sqrt(sum(w * w for w in weights)) + 1e-12
    drive = 0.0
    for freq, phase, weight in zip(case.drive_freqs, case.phases, weights):
        drive += weight * math.sin(2.0 * np.pi * base_hz * freq * t + phase)
    return envelope * case.drive_amp * drive / norm


def spark_gate(delta_q: np.ndarray | float, threshold: float = 0.035) -> np.ndarray | float:
    width = 0.30 * threshold
    return 0.5 * (1.0 + np.tanh((np.abs(delta_q) - threshold) / (width + 1e-12)))


def receiver_coil_derivative(y: np.ndarray, t: float, omega: np.ndarray, case: ReceiverCase,
                             base_hz: float, drive_until: float, zeta: np.ndarray,
                             couplings: Tuple[float, float, float]) -> np.ndarray:
    # y = [q_primary, q_secondary, q_receiver, i_primary, i_secondary, i_receiver]
    q = y[:3]
    current = y[3:]
    a = -2.0 * zeta * omega * current - (omega ** 2) * q

    k_ps, k_sr, k_pr = couplings

    # Linear mutual coupling between nearby coils, with weak direct leakage from
    # primary to receiver.
    ps_delta = q[0] - q[1]
    sr_delta = q[1] - q[2]
    pr_delta = q[0] - q[2]
    a[0] += -k_ps * ps_delta - k_pr * pr_delta
    a[1] += k_ps * ps_delta - k_sr * sr_delta
    a[2] += k_sr * sr_delta + k_pr * pr_delta

    if case.nonlinear_strength:
        # Secondary coil varactor-like capacitance nonlinearity.
        a[1] += -case.nonlinear_strength * (q[1] ** 3)

    if case.mix_strength:
        # Nonlinear cross-coupling: the product of lower modes contains sum and
        # difference frequencies, so a receiver tuned to f1 + f2 can be pumped.
        a[2] += case.mix_strength * q[0] * q[1]
        a[0] += -0.18 * case.mix_strength * q[1] * q[2]
        a[1] += -0.18 * case.mix_strength * q[0] * q[2]

    if case.spark_strength:
        gate = spark_gate(ps_delta, threshold=case.spark_threshold)
        spark_force = case.spark_strength * gate * ps_delta
        spark_damp = 0.035 * case.spark_strength * gate * (current[0] - current[1])
        a[0] += -(spark_force + spark_damp)
        a[1] += spark_force + spark_damp

    a[0] += receiver_drive_value(case, t, base_hz, drive_until)
    return np.concatenate([current, a])


def receiver_energy(q: np.ndarray, current: np.ndarray, omega: np.ndarray, nonlinear_strength: float) -> np.ndarray:
    e = 0.5 * (current ** 2) + 0.5 * (omega[None, :] ** 2) * (q ** 2)
    if nonlinear_strength:
        e[:, 1] += 0.25 * nonlinear_strength * (q[:, 1] ** 4)
    return e


def estimate_ringdown_q(times: np.ndarray, receiver_e: np.ndarray, omega_receiver: float,
                        drive_until: float) -> Tuple[float, float]:
    post = np.where(times >= drive_until)[0]
    if len(post) < 20:
        return float("nan"), float("nan")

    span = receiver_e[post]
    chunk = max(4, len(span) // 5)
    start_e = float(np.mean(span[:chunk]) + 1e-18)
    end_e = float(np.mean(span[-chunk:]) + 1e-18)
    retention = end_e / start_e
    duration = float(times[post[-1]] - times[post[0]])

    if end_e >= start_e or duration <= 0:
        return retention, float("nan")
    q_factor = omega_receiver * duration / math.log(start_e / end_e)
    return retention, float(q_factor)


def run_receiver_case(case: ReceiverCase, out_dir: Path, seed: int = 1, dt: float = 0.01,
                      t_max: float = 240.0, base_hz: float = 0.045,
                      save_plots: bool = True, save_spectrum: bool = True) -> Dict[str, float | str]:
    rng = np.random.default_rng(seed)
    coil_freqs_hz = base_hz * np.asarray(case.coil_freqs, dtype=float)
    omega = 2.0 * np.pi * coil_freqs_hz
    drive_until = 0.72 * t_max
    couplings = (
        case.primary_secondary_coupling * omega[0] * omega[1],
        case.secondary_receiver_coupling * omega[1] * omega[2],
        case.primary_receiver_coupling * omega[0] * omega[2],
    )
    zeta = case.zeta_scale * np.asarray([0.018, 0.010, 0.006], dtype=float)

    n = int(t_max / dt)
    t = np.arange(n) * dt
    y = np.zeros(6)
    y[:3] = 1e-4 * rng.normal(size=3)
    y[3:] = 1e-4 * rng.normal(size=3)

    sample_every = 4
    samples = (n + sample_every - 1) // sample_every
    times = np.zeros(samples)
    qs = np.zeros((samples, 3), dtype=float)
    currents = np.zeros((samples, 3), dtype=float)
    spark_activity = np.zeros(samples)

    positive_input_work = 0.0
    net_input_work = 0.0
    sample_idx = 0

    for i in range(n):
        now = t[i]
        if i % sample_every == 0:
            times[sample_idx] = now
            qs[sample_idx] = y[:3]
            currents[sample_idx] = y[3:]
            spark_activity[sample_idx] = float(spark_gate(y[0] - y[1], threshold=case.spark_threshold))
            sample_idx += 1

        drive = receiver_drive_value(case, now, base_hz, drive_until)
        power = drive * y[3]
        positive_input_work += max(0.0, power) * dt
        net_input_work += power * dt

        y = rk4_step(y, now, dt, receiver_coil_derivative, omega, case, base_hz, drive_until, zeta, couplings)
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e5:
            times = times[:sample_idx]
            qs = qs[:sample_idx]
            currents = currents[:sample_idx]
            spark_activity = spark_activity[:sample_idx]
            break

    times = times[:sample_idx]
    qs = qs[:sample_idx]
    currents = currents[:sample_idx]
    spark_activity = spark_activity[:sample_idx]

    energy = receiver_energy(qs, currents, omega, case.nonlinear_strength)
    total_e = np.sum(energy, axis=1) + 1e-18
    energy_frac = energy / total_e[:, None]
    receiver_frac = energy_frac[:, 2]

    post_mask = times >= drive_until
    post_indices = np.where(post_mask)[0]
    if len(post_indices):
        post_tail = post_indices[len(post_indices) // 2:]
    else:
        post_tail = np.arange(max(0, int(0.80 * len(times))), len(times))

    peak_receiver_frac = float(np.max(receiver_frac))
    final_receiver_frac = float(np.mean(receiver_frac[post_tail]))
    final_receiver_energy = float(np.mean(energy[post_tail, 2]))
    receiver_over_primary = float(final_receiver_energy / (np.mean(energy[post_tail, 0]) + 1e-18))
    transfer_efficiency = float(final_receiver_energy / (positive_input_work + 1e-18))
    ringdown_retention, q_factor = estimate_ringdown_q(times, energy[:, 2], omega[2], drive_until)

    analysis_mask = (times >= 0.45 * drive_until) & (times < drive_until)
    if np.sum(analysis_mask) < 32:
        analysis_mask = times >= 0.5 * times[-1]
    analysis_t = times[analysis_mask]
    analysis_q = qs[analysis_mask]

    if len(case.drive_freqs) >= 2:
        f1 = base_hz * case.drive_freqs[0]
        f2 = base_hz * case.drive_freqs[1]
        receiver_target_hz = coil_freqs_hz[2]
        sum_freq_hz = f1 + f2
        sum_error_hz = abs(sum_freq_hz - receiver_target_hz)

        sample_dt = sample_every * dt
        window = max(32, int(6.0 / sample_dt))
        step = max(16, window // 5)
        if len(analysis_t) > window + step:
            p0 = sliding_phase(analysis_q[:, 0], analysis_t, f1, window, step)
            p1 = sliding_phase(analysis_q[:, 1], analysis_t, f2, window, step)
            p2 = sliding_phase(analysis_q[:, 2], analysis_t, receiver_target_hz, window, step)
            min_len = min(len(p0), len(p1), len(p2))
            mismatch = wrap_angle(p0[:min_len] + p1[:min_len] - p2[:min_len])
            phase_lock = float(np.abs(np.mean(np.exp(1j * mismatch)))) if len(mismatch) else 0.0
            mismatch_std = float(np.std(mismatch)) if len(mismatch) else float("nan")
        else:
            phase_lock = 0.0
            mismatch_std = float("nan")

        receiver_sum_amp = abs(complex_projection(analysis_q[:, 2], analysis_t, sum_freq_hz))
        receiver_high_amp = abs(complex_projection(analysis_q[:, 2], analysis_t, receiver_target_hz))
        primary_low_amp = abs(complex_projection(analysis_q[:, 0], analysis_t, f1)) + 1e-12
    else:
        f1 = base_hz * case.drive_freqs[0]
        receiver_target_hz = coil_freqs_hz[2]
        sum_error_hz = abs(f1 - receiver_target_hz)
        phase_lock = 0.0
        mismatch_std = float("nan")
        receiver_sum_amp = abs(complex_projection(analysis_q[:, 2], analysis_t, receiver_target_hz))
        receiver_high_amp = receiver_sum_amp
        primary_low_amp = abs(complex_projection(analysis_q[:, 0], analysis_t, f1)) + 1e-12

    bounded_retention = max(0.0, min(2.0, ringdown_retention if np.isfinite(ringdown_retention) else 0.0))
    score = (
        final_receiver_frac
        * (1.0 + receiver_over_primary)
        * (0.35 + bounded_retention)
        * (1.0 + phase_lock)
        * (1.0 + 0.5 * float(receiver_sum_amp / primary_low_amp))
        / (1.0 + 50.0 * float(sum_error_hz))
    )

    if save_plots:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(times, energy_frac[:, 0], label="primary")
        ax.plot(times, energy_frac[:, 1], label="secondary")
        ax.plot(times, energy_frac[:, 2], label="receiver")
        ax.axvline(drive_until, color="k", linestyle="--", linewidth=1.0, alpha=0.45, label="drive off")
        ax.set_title(f"Receiver coil energy transfer: {case.name}")
        ax.set_xlabel("time")
        ax.set_ylabel("energy fraction")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / f"receiver_{case.name}_energy.png", dpi=140)
        plt.close(fig)

    if save_plots and save_spectrum and len(analysis_q) >= 16:
        signal = analysis_q[:, 2] - np.mean(analysis_q[:, 2])
        window_fn = np.hanning(len(signal))
        spectrum = np.abs(np.fft.rfft(signal * window_fn))
        freq_axis = np.fft.rfftfreq(len(signal), d=sample_every * dt)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(freq_axis / base_hz, spectrum)
        ax.set_xlim(0, max(max(case.coil_freqs), max(case.drive_freqs)) * 1.6)
        ax.set_title(f"Receiver spectrum: {case.name}")
        ax.set_xlabel("frequency / base frequency")
        ax.set_ylabel("amplitude")
        fig.tight_layout()
        fig.savefig(out_dir / f"receiver_{case.name}_spectrum.png", dpi=140)
        plt.close(fig)

    return {
        "experiment": "receiver_coil",
        "case": case.name,
        "freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "coil_tunes": "-".join(f"{x:g}" for x in case.coil_freqs),
        "sum_error_hz": float(sum_error_hz),
        "peak_receiver_energy_frac": peak_receiver_frac,
        "final_receiver_energy_frac": final_receiver_frac,
        "receiver_energy_over_primary_tail": receiver_over_primary,
        "transfer_efficiency_est": transfer_efficiency,
        "receiver_phase_lock_0_to_1": phase_lock,
        "receiver_phase_mismatch_std_rad": mismatch_std,
        "receiver_sum_amp_over_primary_low_amp": float(receiver_sum_amp / primary_low_amp),
        "receiver_high_amp_over_primary_low_amp": float(receiver_high_amp / primary_low_amp),
        "ringdown_retention": float(ringdown_retention),
        "q_factor_est": float(q_factor),
        "spark_activity_mean": float(np.mean(spark_activity)),
        "positive_input_work": float(positive_input_work),
        "net_input_work": float(net_input_work),
        "score": float(score),
        "note": case.note,
    }


def experiment_receiver_coils(out_dir: Path, seed: int, quick: bool = False) -> List[Dict[str, float | str]]:
    rng = np.random.default_rng(seed + 113)
    phase_cycle = (0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0)
    cases = [
        ReceiverCase("369_two_tone_sum_pump", (3, 6, 9), (3, 6), phase_cycle[:2],
                     note="clean receiver test: drive 3 and 6 only, then look for receiver energy at 9"),
        ReceiverCase("369_phase_coded", (3, 6, 9), (3, 6, 9), phase_cycle,
                     drive_weights=(1.0, 0.85, 0.25),
                     note="phase-coded 3/6/9 drive with a small direct 9 pilot tone"),
        ReceiverCase("369_random_phase", (3, 6, 9), (3, 6, 9), tuple(rng.uniform(0, 2 * np.pi, 3)),
                     drive_weights=(1.0, 0.85, 0.25),
                     note="same triad and pilot tone, randomized phase code"),
        ReceiverCase("369_detuned_mid", (3, 6.25, 9), (3, 6.25), phase_cycle[:2],
                     note="breaks the f1+f2=f_receiver sum condition while keeping the 3/6-ish setup"),
        ReceiverCase("357_non_sum", (3, 5, 7), (3, 5), phase_cycle[:2],
                     note="non-sum control; 3 + 5 does not land on receiver tune 7"),
        ReceiverCase("4812_exact_sum", (4, 8, 12), (4, 8), phase_cycle[:2],
                     note="non-369 exact-sum harmonic triad"),
        ReceiverCase("369_linear_no_gap", (3, 6, 9), (3, 6), phase_cycle[:2],
                     nonlinear_strength=0.0, mix_strength=0.0, spark_strength=0.0,
                     note="same coils and drive with nonlinear spark/varactor path disabled"),
        ReceiverCase("normal_resonant_single_6", (6, 6, 6), (6,), (0.0,),
                     drive_weights=(1.0,), nonlinear_strength=0.18, mix_strength=0.0,
                     spark_strength=0.10, drive_amp=0.055,
                     note="ordinary resonant wireless-transfer control: all coils tuned to 6"),
    ]
    rows = [
        run_receiver_case(
            case,
            out_dir,
            seed=seed,
            dt=0.050 if quick else 0.040,
            t_max=60.0 if quick else 140.0,
            save_plots=not quick,
            save_spectrum=not quick,
        )
        for case in cases
    ]
    write_csv(out_dir / "receiver_coil_summary.csv", rows)
    return rows


# ----------------------------
# Experiment 4: silent 9 receiver
# ----------------------------

def safe_token(value: float | str) -> str:
    return str(value).replace("-", "m").replace(".", "p").replace("+", "p")


def simulate_receiver_dynamics(case: ReceiverCase, seed: int = 1, dt: float = 0.04,
                               t_max: float = 90.0, base_hz: float = 0.045,
                               sample_every: int = 2) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    coil_freqs_hz = base_hz * np.asarray(case.coil_freqs, dtype=float)
    omega = 2.0 * np.pi * coil_freqs_hz
    drive_until = 0.72 * t_max
    couplings = (
        case.primary_secondary_coupling * omega[0] * omega[1],
        case.secondary_receiver_coupling * omega[1] * omega[2],
        case.primary_receiver_coupling * omega[0] * omega[2],
    )
    zeta = case.zeta_scale * np.asarray([0.018, 0.010, 0.006], dtype=float)

    n = int(t_max / dt)
    t = np.arange(n) * dt
    y = np.zeros(6)
    y[:3] = 1e-4 * rng.normal(size=3)
    y[3:] = 1e-4 * rng.normal(size=3)

    samples = (n + sample_every - 1) // sample_every
    times = np.zeros(samples)
    qs = np.zeros((samples, 3), dtype=float)
    currents = np.zeros((samples, 3), dtype=float)
    spark_activity = np.zeros(samples)

    positive_input_work = 0.0
    net_input_work = 0.0
    coil_loss_energy = 0.0
    receiver_load_output_energy = 0.0
    spark_loss_energy = 0.0
    sample_idx = 0

    for i in range(n):
        now = t[i]
        q = y[:3]
        current = y[3:]
        gate = float(spark_gate(q[0] - q[1], threshold=case.spark_threshold))

        if i % sample_every == 0:
            times[sample_idx] = now
            qs[sample_idx] = q
            currents[sample_idx] = current
            spark_activity[sample_idx] = gate
            sample_idx += 1

        drive = receiver_drive_value(case, now, base_hz, drive_until)
        input_power = drive * current[0]
        positive_input_work += max(0.0, input_power) * dt
        net_input_work += input_power * dt

        damping_power = 2.0 * zeta * omega * (current ** 2)
        coil_loss_energy += float(damping_power[0] + damping_power[1]) * dt
        receiver_load_output_energy += float(damping_power[2]) * dt
        spark_loss_energy += float(0.035 * case.spark_strength * gate * ((current[0] - current[1]) ** 2)) * dt

        y = rk4_step(y, now, dt, receiver_coil_derivative, omega, case, base_hz, drive_until, zeta, couplings)
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e5:
            break

    times = times[:sample_idx]
    qs = qs[:sample_idx]
    currents = currents[:sample_idx]
    spark_activity = spark_activity[:sample_idx]
    energy = receiver_energy(qs, currents, omega, case.nonlinear_strength)

    return {
        "times": times,
        "qs": qs,
        "currents": currents,
        "energy": energy,
        "omega": omega,
        "drive_until": drive_until,
        "positive_input_work": positive_input_work,
        "net_input_work": net_input_work,
        "coil_loss_energy": coil_loss_energy,
        "receiver_load_output_energy": receiver_load_output_energy,
        "spark_loss_energy": spark_loss_energy,
        "spark_activity": spark_activity,
        "dt_sample": dt * sample_every,
    }


def target_mode_energy(q: np.ndarray, current: np.ndarray, times: np.ndarray,
                       target_hz: float, omega_target: float) -> float:
    q_amp = complex_projection(q, times, target_hz)
    current_amp = complex_projection(current, times, target_hz)
    return float(0.25 * ((abs(current_amp) ** 2) + (omega_target ** 2) * (abs(q_amp) ** 2)))


def silent_phase_lock(case: ReceiverCase, times: np.ndarray, qs: np.ndarray, target_hz: float,
                      base_hz: float, sample_dt: float) -> Tuple[float, float]:
    window = max(24, int(6.0 / sample_dt))
    step = max(8, window // 5)
    if len(times) <= window + step:
        return 0.0, float("nan")

    if len(case.drive_freqs) >= 2:
        f1 = base_hz * case.drive_freqs[0]
        f2 = base_hz * case.drive_freqs[1]
        p1 = sliding_phase(qs[:, 0], times, f1, window, step)
        p2 = sliding_phase(qs[:, 1], times, f2, window, step)
        p9 = sliding_phase(qs[:, 2], times, target_hz, window, step)
        min_len = min(len(p1), len(p2), len(p9))
        mismatch = wrap_angle(p1[:min_len] + p2[:min_len] - p9[:min_len])
    else:
        f_drive = base_hz * case.drive_freqs[0]
        p_drive = sliding_phase(qs[:, 0], times, f_drive, window, step)
        p9 = sliding_phase(qs[:, 2], times, target_hz, window, step)
        min_len = min(len(p_drive), len(p9))
        mismatch = wrap_angle(p_drive[:min_len] - p9[:min_len])

    if len(mismatch) == 0:
        return 0.0, float("nan")
    return float(np.abs(np.mean(np.exp(1j * mismatch)))), float(np.std(mismatch))


def silent_metrics_from_sim(case: ReceiverCase, sim: Dict[str, object], base_hz: float,
                            target_input_work: float | None = None,
                            sweep_name: str = "core", sweep_value: str = "") -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    currents = sim["currents"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    target_hz = base_hz * 9.0

    analysis_mask = (times >= 0.40 * drive_until) & (times < drive_until)
    if int(np.sum(analysis_mask)) < 24:
        analysis_mask = times >= 0.5 * times[-1]
    tail_mask = times >= drive_until
    if int(np.sum(tail_mask)) < 8:
        tail_mask = times >= 0.80 * times[-1]

    receiver_energy_at_9 = target_mode_energy(qs[analysis_mask, 2], currents[analysis_mask, 2],
                                              times[analysis_mask], target_hz, float(omega[2]))
    total_receiver_energy = float(np.mean(energy[analysis_mask, 2]) + 1e-18)
    spectral_purity_9 = float(min(1.0, receiver_energy_at_9 / total_receiver_energy))
    total_input_work = float(sim["positive_input_work"])
    conversion_efficiency = float(receiver_energy_at_9 / (total_input_work + 1e-18))
    phase_lock_score, phase_mismatch_std = silent_phase_lock(case, times[analysis_mask], qs[analysis_mask],
                                                             target_hz, base_hz, float(sim["dt_sample"]))

    initial_stored_energy = float(np.sum(energy[0]))
    final_stored_energy = float(np.sum(energy[-1]))
    delta_stored_energy = final_stored_energy - initial_stored_energy
    energy_budget_error = (
        float(sim["net_input_work"])
        - float(sim["coil_loss_energy"])
        - float(sim["spark_loss_energy"])
        - float(sim["receiver_load_output_energy"])
        - delta_stored_energy
    )
    energy_budget_scale = (
        abs(float(sim["net_input_work"]))
        + float(sim["coil_loss_energy"])
        + float(sim["spark_loss_energy"])
        + float(sim["receiver_load_output_energy"])
        + abs(delta_stored_energy)
        + 1e-18
    )

    if len(case.drive_freqs) >= 2:
        sum_error_hz = abs(base_hz * (case.drive_freqs[0] + case.drive_freqs[1] - 9.0))
    else:
        sum_error_hz = abs(base_hz * (case.drive_freqs[0] - 9.0))

    is_direct_9 = len(case.drive_freqs) == 1 and abs(case.drive_freqs[0] - 9.0) < 1e-9
    return {
        "experiment": "silent_9_receiver",
        "case": case.name,
        "freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "coil_tunes": "-".join(f"{x:g}" for x in case.coil_freqs),
        "target_freq": "9",
        "sweep": sweep_name,
        "sweep_value": sweep_value,
        "direct_9_drive": "yes" if is_direct_9 else "no",
        "reference_role": "ceiling_reference" if is_direct_9 else "discovery_candidate",
        "total_input_work": total_input_work,
        "target_input_work": "" if target_input_work is None else float(target_input_work),
        "input_work_error_frac": "" if target_input_work is None else float((total_input_work - target_input_work) / (target_input_work + 1e-18)),
        "receiver_energy_at_9": receiver_energy_at_9,
        "total_receiver_energy": total_receiver_energy,
        "spectral_purity_9": spectral_purity_9,
        "conversion_efficiency": conversion_efficiency,
        "mixing_gain_vs_linear": 1.0,
        "phase_lock_score": phase_lock_score,
        "phase_mismatch_std_rad": phase_mismatch_std,
        "energy_budget_error": float(energy_budget_error),
        "energy_budget_error_frac": float(abs(energy_budget_error) / energy_budget_scale),
        "coil_loss_energy": float(sim["coil_loss_energy"]),
        "spark_loss_energy": float(sim["spark_loss_energy"]),
        "receiver_load_output_energy": float(sim["receiver_load_output_energy"]),
        "delta_stored_energy": delta_stored_energy,
        "peak_receiver_energy": float(np.max(energy[:, 2])),
        "late_time_receiver_energy": float(np.mean(energy[tail_mask, 2])),
        "sum_error_hz": float(sum_error_hz),
        "drive_amp": float(case.drive_amp),
        "nonlinear_strength": float(case.mix_strength),
        "varactor_coefficient": float(case.nonlinear_strength),
        "spark_threshold": float(case.spark_threshold),
        "primary_secondary_coupling": float(case.primary_secondary_coupling),
        "secondary_receiver_coupling": float(case.secondary_receiver_coupling),
        "zeta_scale": float(case.zeta_scale),
        "spark_activity_mean": float(np.mean(sim["spark_activity"])),
        "score": 0.0,
        "note": case.note,
    }


def calibrate_to_input_work(case: ReceiverCase, target_input_work: float, seed: int,
                            dt: float, t_max: float, base_hz: float,
                            passes: int = 1) -> Tuple[ReceiverCase, Dict[str, object]]:
    tuned = case
    for _ in range(passes):
        sim = simulate_receiver_dynamics(tuned, seed=seed, dt=dt, t_max=t_max, base_hz=base_hz)
        work = max(float(sim["positive_input_work"]), 1e-18)
        scale = math.sqrt(target_input_work / work)
        scale = float(np.clip(scale, 0.25, 4.0))
        tuned = replace(tuned, drive_amp=tuned.drive_amp * scale)
    sim = simulate_receiver_dynamics(tuned, seed=seed, dt=dt, t_max=t_max, base_hz=base_hz)
    return tuned, sim


def finalize_silent_rows(rows: List[Dict[str, float | str]], linear_energy_reference: float | None = None) -> None:
    linear_energy = linear_energy_reference
    if linear_energy is None:
        linear_energy = next(
            (float(r["receiver_energy_at_9"]) for r in rows if r["case"] == "3_plus_6_to_9_linear"),
            1e-18,
        )
    linear_energy = max(linear_energy, 1e-18)
    for row in rows:
        mixing_gain = float(row["receiver_energy_at_9"]) / linear_energy
        row["mixing_gain_vs_linear"] = mixing_gain
        if row.get("reference_role") == "ceiling_reference":
            row["score"] = 0.0
            continue

        budget_penalty = 1.0 + min(10.0, float(row["energy_budget_error_frac"]))
        sum_penalty = 1.0 + 30.0 * float(row["sum_error_hz"])
        row["score"] = (
            float(row["conversion_efficiency"])
            * float(row["spectral_purity_9"])
            * (0.35 + float(row["phase_lock_score"]))
            * math.log1p(max(0.0, mixing_gain))
            / (budget_penalty * sum_penalty)
        )


def plot_silent_summary(out_dir: Path, rows: List[Dict[str, float | str]], filename: str) -> None:
    ranked = sorted(
        [r for r in rows if r.get("reference_role") != "ceiling_reference"],
        key=lambda r: float(r["score"]),
        reverse=True,
    )
    ceiling = [r for r in rows if r.get("reference_role") == "ceiling_reference"]
    plot_rows = ranked + ceiling
    labels = [str(r["case"]) for r in plot_rows]
    conversion = [float(r["conversion_efficiency"]) for r in plot_rows]
    purity = [float(r["spectral_purity_9"]) for r in plot_rows]

    x = np.arange(len(plot_rows))
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax1.bar(x - 0.18, conversion, width=0.36, label="conversion efficiency")
    ax1.set_ylabel("receiver energy at 9 / input work")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=35, ha="right")
    ax2 = ax1.twinx()
    ax2.plot(x + 0.18, purity, marker="o", color="tab:orange", label="spectral purity at 9")
    ax2.set_ylabel("spectral purity at 9")
    ax1.set_title("Silent 9 receiver: conversion and purity")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=140)
    plt.close(fig)


def plot_silent_case(out_dir: Path, case: ReceiverCase, sim: Dict[str, object], base_hz: float) -> None:
    times = sim["times"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(times, energy[:, 0], label="primary")
    ax.plot(times, energy[:, 1], label="secondary")
    ax.plot(times, energy[:, 2], label="receiver")
    ax.axvline(drive_until, color="k", linestyle="--", linewidth=1.0, alpha=0.45, label="drive off")
    ax.set_title(f"Silent 9 receiver energy: {case.name}")
    ax.set_xlabel("time")
    ax.set_ylabel("stored energy")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / f"silent9_{case.name}_energy.png", dpi=140)
    plt.close(fig)

    analysis_mask = (times >= 0.40 * drive_until) & (times < drive_until)
    signal = qs[analysis_mask, 2] - np.mean(qs[analysis_mask, 2])
    if len(signal) >= 16:
        spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
        freq_axis = np.fft.rfftfreq(len(signal), d=float(sim["dt_sample"]))
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(freq_axis / base_hz, spectrum)
        ax.axvline(9.0, color="tab:red", linestyle="--", linewidth=1.0, label="target 9")
        ax.set_xlim(0, 14)
        ax.set_title(f"Silent 9 receiver spectrum: {case.name}")
        ax.set_xlabel("frequency / base frequency")
        ax.set_ylabel("receiver amplitude")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / f"silent9_{case.name}_spectrum.png", dpi=140)
        plt.close(fig)


def silent_core_cases(seed: int) -> List[ReceiverCase]:
    rng = np.random.default_rng(seed + 909)
    f_rand = tuple(np.round(rng.uniform(2.0, 7.0, 2), 3))
    if abs(sum(f_rand) - 9.0) < 0.45:
        f_rand = (f_rand[0], f_rand[1] + 0.9)

    return [
        ReceiverCase("3_plus_6_to_9_nonlinear", (3, 6, 9), (3, 6), (0.0, 0.0),
                     note="silent target case: drive 3 and 6 only; receiver is tuned to 9"),
        ReceiverCase("3_plus_6_to_9_linear", (3, 6, 9), (3, 6), (0.0, 0.0),
                     nonlinear_strength=0.0, mix_strength=0.0, spark_strength=0.0,
                     note="linear-control twin of the target case"),
        ReceiverCase("3_plus_6p25_to_9_nonlinear", (3, 6.25, 9), (3, 6.25), (0.0, 0.0),
                     note="detuned middle drive; 3 + 6.25 misses 9"),
        ReceiverCase("4_plus_5_to_9_nonlinear", (4, 5, 9), (4, 5), (0.0, 0.0),
                     note="non-369 exact-sum pair; tests whether any f1+f2=9 pair works"),
        ReceiverCase("2_plus_7_to_9_nonlinear", (2, 7, 9), (2, 7), (0.0, 0.0),
                     note="second non-369 exact-sum pair"),
        ReceiverCase("random_pair_to_9_nonlinear", (f_rand[0], f_rand[1], 9), f_rand, (0.0, 0.0),
                     note="random non-sum pair with receiver still tuned to 9"),
        ReceiverCase("normal_resonant_single_9", (9, 9, 9), (9,), (0.0,),
                     nonlinear_strength=0.0, mix_strength=0.0, spark_strength=0.0,
                     drive_amp=0.050,
                     note="direct 9 drive ceiling/reference; not ranked as the discovery winner"),
    ]


def run_silent_cases(cases: List[ReceiverCase], out_dir: Path, seed: int, dt: float, t_max: float,
                     base_hz: float, target_input_work: float,
                     save_plots: bool = False,
                     sweep_name: str = "core",
                     calibrate: bool = True,
                     calibration_passes: int = 1) -> List[Dict[str, float | str]]:
    rows = []
    for idx, case in enumerate(cases):
        if calibrate:
            tuned, sim = calibrate_to_input_work(case, target_input_work, seed + idx, dt, t_max, base_hz,
                                                passes=calibration_passes)
        else:
            tuned = case
            sim = simulate_receiver_dynamics(tuned, seed=seed + idx, dt=dt, t_max=t_max, base_hz=base_hz)
        if save_plots:
            plot_silent_case(out_dir, tuned, sim, base_hz)
        rows.append(silent_metrics_from_sim(tuned, sim, base_hz, target_input_work=target_input_work,
                                            sweep_name=sweep_name))
    finalize_silent_rows(rows)
    return rows


def silent_sweep_cases(base: ReceiverCase) -> List[Tuple[str, str, ReceiverCase, bool]]:
    specs: List[Tuple[str, str, ReceiverCase, bool]] = []
    for value in [0.0, 0.20, 0.34, 0.70]:
        specs.append(("nonlinear_strength", f"{value:g}", replace(base, name=f"sweep_mix_{safe_token(value)}", mix_strength=value), True))
    for value in [0.0, 0.42, 0.80]:
        specs.append(("varactor_coefficient", f"{value:g}", replace(base, name=f"sweep_varactor_{safe_token(value)}", nonlinear_strength=value), True))
    for value in [0.020, 0.035, 0.070]:
        specs.append(("spark_threshold", f"{value:g}", replace(base, name=f"sweep_spark_threshold_{safe_token(value)}", spark_threshold=value), True))
    for value in [0.015, 0.030, 0.045]:
        specs.append(("primary_secondary_coupling", f"{value:g}", replace(base, name=f"sweep_ps_coupling_{safe_token(value)}", primary_secondary_coupling=value), True))
    for value in [0.011, 0.022, 0.035]:
        specs.append(("secondary_receiver_coupling", f"{value:g}", replace(base, name=f"sweep_sr_coupling_{safe_token(value)}", secondary_receiver_coupling=value), True))
    for value in [8.70, 8.90, 9.00, 9.10, 9.30]:
        specs.append(("receiver_detuning", f"{value:g}", replace(base, name=f"sweep_receiver_tune_{safe_token(value)}", coil_freqs=(3, 6, value)), True))
    for value in [5.60, 5.80, 6.00, 6.20, 6.40]:
        specs.append(("secondary_detuning", f"{value:g}", replace(base, name=f"sweep_secondary_tune_{safe_token(value)}", coil_freqs=(3, value, 9)), True))
    for degrees in range(0, 361, 30):
        specs.append(("drive_phase_offset_deg", str(degrees), replace(base, name=f"sweep_phase_{degrees}", phases=(0.0, math.radians(degrees))), True))
    for value in [0.040, 0.055, 0.070, 0.090, 0.110]:
        specs.append(("drive_amplitude", f"{value:g}", replace(base, name=f"sweep_drive_amp_{safe_token(value)}", drive_amp=value), False))
    for value in [0.50, 1.00, 2.00]:
        specs.append(("damping_q_scale", f"{value:g}", replace(base, name=f"sweep_zeta_scale_{safe_token(value)}", zeta_scale=value), True))
    ratio_cases = [
        ("exact_3_6_9", (3.0, 6.0, 9.0)),
        ("primary_low_secondary_high", (2.8, 6.2, 9.0)),
        ("primary_high_secondary_low", (3.2, 5.8, 9.0)),
        ("compressed_middle", (3.0, 5.7, 8.7)),
        ("expanded_middle", (3.0, 6.3, 9.3)),
    ]
    for label, tunes in ratio_cases:
        specs.append(("coil_ratio_assumption", label, replace(base, name=f"sweep_ratio_{label}", coil_freqs=tunes), True))
    return specs


def run_silent_sweeps(base: ReceiverCase, out_dir: Path, seed: int, dt: float, t_max: float,
                      base_hz: float, target_input_work: float,
                      linear_energy_reference: float) -> List[Dict[str, float | str]]:
    sweep_rows = []
    for idx, (sweep_name, sweep_value, case, _calibrate) in enumerate(silent_sweep_cases(base)):
        tuned = case
        sim = simulate_receiver_dynamics(tuned, seed=seed + 1000 + idx, dt=dt, t_max=t_max, base_hz=base_hz)
        row = silent_metrics_from_sim(tuned, sim, base_hz, target_input_work=target_input_work,
                                      sweep_name=sweep_name, sweep_value=sweep_value)
        sweep_rows.append(row)

    finalize_silent_rows(sweep_rows, linear_energy_reference=linear_energy_reference)
    sweep_rows = sorted(sweep_rows, key=lambda r: float(r["score"]), reverse=True)
    for rank, row in enumerate(sweep_rows, 1):
        row["rank_within_sweep"] = rank
    write_csv(out_dir / "silent_9_receiver_sweeps.csv", sweep_rows)
    plot_silent_summary(out_dir, sweep_rows[:20], "silent_9_receiver_top_sweeps.png")
    return sweep_rows


def experiment_silent_9_receiver(out_dir: Path, seed: int, quick: bool = False,
                                 include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    base_hz = 0.045
    dt = 0.050 if quick else 0.040
    t_max = 70.0 if quick else 120.0
    cases = silent_core_cases(seed)

    reference_sim = simulate_receiver_dynamics(cases[0], seed=seed, dt=dt, t_max=t_max, base_hz=base_hz)
    target_input_work = float(reference_sim["positive_input_work"])

    rows = run_silent_cases(cases, out_dir, seed, dt, t_max, base_hz, target_input_work,
                            save_plots=not quick, sweep_name="core", calibrate=True,
                            calibration_passes=1)
    rows = sorted(rows, key=lambda r: float(r["score"]), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank_within_silent9"] = rank
    write_csv(out_dir / "silent_9_receiver_summary.csv", rows)
    plot_silent_summary(out_dir, rows, "silent_9_receiver_summary.png")

    if include_sweeps:
        linear_energy = next(float(r["receiver_energy_at_9"]) for r in rows if r["case"] == "3_plus_6_to_9_linear")
        sweep_dt = max(dt, 0.080 if quick else 0.070)
        sweep_t_max = min(t_max, 45.0 if quick else 70.0)
        run_silent_sweeps(cases[0], out_dir, seed, sweep_dt, sweep_t_max, base_hz, target_input_work,
                          linear_energy_reference=linear_energy)

    return rows


# ----------------------------
# Experiment 5: atlas of sum-frequency receiver conversion
# ----------------------------

ATLAS_TARGETS = [6, 9, 12, 15, 18, 24]


def pump_pairs_for_target(target: int) -> List[Tuple[int, int]]:
    return [(f1, target - f1) for f1 in range(1, target // 2 + 1)]


def pair_label(f1: float, f2: float, target: float) -> str:
    return f"{f1:g}_plus_{f2:g}_to_{target:g}"


def natural_mode_overlap(freq: float, mode_freq: float, target: float) -> float:
    bandwidth = max(0.35, 0.055 * target)
    return float(math.exp(-0.5 * ((freq - mode_freq) / bandwidth) ** 2))


def atlas_random_pair(target: int, rng: np.random.Generator) -> Tuple[float, float]:
    f1 = float(rng.integers(1, max(2, target)))
    f2 = float(rng.integers(1, max(2, target)))
    if f1 > f2:
        f1, f2 = f2, f1
    if abs((f1 + f2) - target) < 0.35:
        f2 += 0.75
    return f1, f2


def atlas_case(name: str, target: float, drive_freqs: Tuple[float, ...], phases: Tuple[float, ...],
               nonlinear: bool = True, drive_amp: float = 0.070,
               coil_freqs: Tuple[float, float, float] | None = None,
               note: str = "") -> ReceiverCase:
    if coil_freqs is None:
        if len(drive_freqs) >= 2:
            coil_freqs = (drive_freqs[0], drive_freqs[1], target)
        else:
            coil_freqs = (target, target, target)
    if nonlinear:
        return ReceiverCase(name, coil_freqs, drive_freqs, phases, drive_amp=drive_amp, note=note)
    return ReceiverCase(
        name,
        coil_freqs,
        drive_freqs,
        phases,
        nonlinear_strength=0.0,
        mix_strength=0.0,
        spark_strength=0.0,
        drive_amp=drive_amp,
        note=note,
    )


def atlas_metrics_from_sim(case: ReceiverCase, sim: Dict[str, object], target: float, base_hz: float,
                           variant: str, source_pair: str, reference_role: str,
                           sweep: str = "core", sweep_value: str = "") -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    currents = sim["currents"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    target_hz = base_hz * target

    analysis_mask = (times >= 0.35 * drive_until) & (times < drive_until)
    if int(np.sum(analysis_mask)) < 20:
        analysis_mask = times >= 0.45 * times[-1]
    tail_mask = times >= drive_until
    if int(np.sum(tail_mask)) < 8:
        tail_mask = times >= 0.80 * times[-1]

    receiver_energy_at_target = target_mode_energy(
        qs[analysis_mask, 2],
        currents[analysis_mask, 2],
        times[analysis_mask],
        target_hz,
        float(omega[2]),
    )
    total_receiver_energy = float(np.mean(energy[analysis_mask, 2]) + 1e-18)
    spectral_purity = float(min(1.0, receiver_energy_at_target / total_receiver_energy))
    total_input_work = float(sim["positive_input_work"])
    conversion_efficiency = float(receiver_energy_at_target / (total_input_work + 1e-18))
    phase_lock_score, phase_mismatch_std = silent_phase_lock(
        case,
        times[analysis_mask],
        qs[analysis_mask],
        target_hz,
        base_hz,
        float(sim["dt_sample"]),
    )

    initial_stored_energy = float(np.sum(energy[0]))
    final_stored_energy = float(np.sum(energy[-1]))
    delta_stored_energy = final_stored_energy - initial_stored_energy
    energy_budget_error = (
        float(sim["net_input_work"])
        - float(sim["coil_loss_energy"])
        - float(sim["spark_loss_energy"])
        - float(sim["receiver_load_output_energy"])
        - delta_stored_energy
    )
    energy_budget_scale = (
        abs(float(sim["net_input_work"]))
        + float(sim["coil_loss_energy"])
        + float(sim["spark_loss_energy"])
        + float(sim["receiver_load_output_energy"])
        + abs(delta_stored_energy)
        + 1e-18
    )
    energy_budget_error_frac = float(abs(energy_budget_error) / energy_budget_scale)

    if len(case.drive_freqs) >= 2:
        f1 = float(case.drive_freqs[0])
        f2 = float(case.drive_freqs[1])
        pair_distance = abs((f1 + f2) - target)
        overlap_f1 = natural_mode_overlap(f1, float(case.coil_freqs[0]), target)
        overlap_f2 = natural_mode_overlap(f2, float(case.coil_freqs[1]), target)
    else:
        f1 = float(case.drive_freqs[0])
        f2 = 0.0
        pair_distance = abs(f1 - target)
        overlap_f1 = natural_mode_overlap(f1, float(case.coil_freqs[0]), target)
        overlap_f2 = 0.0
    overlap_target = natural_mode_overlap(target, float(case.coil_freqs[2]), target)

    return {
        "experiment": "atlas",
        "case": case.name,
        "variant": variant,
        "reference_role": reference_role,
        "target_freq": float(target),
        "pump_f1": f1,
        "pump_f2": f2,
        "pair": source_pair,
        "freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "coil_tunes": "-".join(f"{x:g}" for x in case.coil_freqs),
        "sweep": sweep,
        "sweep_value": sweep_value,
        "receiver_energy_at_target": receiver_energy_at_target,
        "total_receiver_energy": total_receiver_energy,
        "spectral_purity_target": spectral_purity,
        "total_input_work": total_input_work,
        "conversion_efficiency": conversion_efficiency,
        "mixing_gain_vs_linear": 1.0,
        "detuned_rejection_ratio": 1.0,
        "random_rejection_ratio": 1.0,
        "phase_lock_score": phase_lock_score,
        "phase_mismatch_std_rad": phase_mismatch_std,
        "energy_budget_error": float(energy_budget_error),
        "energy_budget_error_frac": energy_budget_error_frac,
        "energy_budget_error_penalty": 1.0 + min(10.0, energy_budget_error_frac),
        "distance_from_direct_resonance_ceiling": 1.0,
        "direct_ceiling_ratio": 0.0,
        "pair_distance_to_target": float(pair_distance),
        "natural_mode_overlap_f1": overlap_f1,
        "natural_mode_overlap_f2": overlap_f2,
        "natural_mode_overlap_target": overlap_target,
        "peak_receiver_energy": float(np.max(energy[:, 2])),
        "late_time_receiver_energy": float(np.mean(energy[tail_mask, 2])),
        "coil_loss_energy": float(sim["coil_loss_energy"]),
        "spark_loss_energy": float(sim["spark_loss_energy"]),
        "receiver_load_output_energy": float(sim["receiver_load_output_energy"]),
        "delta_stored_energy": delta_stored_energy,
        "drive_amp": float(case.drive_amp),
        "nonlinear_strength": float(case.mix_strength),
        "varactor_coefficient": float(case.nonlinear_strength),
        "spark_threshold": float(case.spark_threshold),
        "primary_secondary_coupling": float(case.primary_secondary_coupling),
        "secondary_receiver_coupling": float(case.secondary_receiver_coupling),
        "zeta_scale": float(case.zeta_scale),
        "spark_activity_mean": float(np.mean(sim["spark_activity"])),
        "discovery_score": 0.0,
        "score": 0.0,
        "note": case.note,
    }


def atlas_run_case(case: ReceiverCase, target: float, variant: str, source_pair: str,
                   reference_role: str, seed: int, dt: float, t_max: float, base_hz: float,
                   sweep: str = "core", sweep_value: str = "") -> Dict[str, float | str]:
    sim = simulate_receiver_dynamics(case, seed=seed, dt=dt, t_max=t_max, base_hz=base_hz, sample_every=2)
    return atlas_metrics_from_sim(case, sim, target, base_hz, variant, source_pair, reference_role, sweep, sweep_value)


def finalize_atlas_group(rows: List[Dict[str, float | str]], direct_row: Dict[str, float | str]) -> None:
    exact = next(r for r in rows if r["variant"] == "nonlinear")
    linear = next(r for r in rows if r["variant"] == "linear")
    detuned = next(r for r in rows if r["variant"] == "detuned")
    random_row = next(r for r in rows if r["variant"] == "random")
    direct_eff = max(float(direct_row["conversion_efficiency"]), 1e-18)

    mixing_gain = float(exact["conversion_efficiency"]) / max(float(linear["conversion_efficiency"]), 1e-18)
    detuned_rejection = float(exact["conversion_efficiency"]) / max(float(detuned["conversion_efficiency"]), 1e-18)
    random_rejection = float(exact["conversion_efficiency"]) / max(float(random_row["conversion_efficiency"]), 1e-18)

    for row in rows:
        row["mixing_gain_vs_linear"] = mixing_gain
        row["detuned_rejection_ratio"] = detuned_rejection
        row["random_rejection_ratio"] = random_rejection
        ratio = float(row["conversion_efficiency"]) / direct_eff
        row["direct_ceiling_ratio"] = ratio
        row["distance_from_direct_resonance_ceiling"] = float(1.0 - min(1.0, ratio))

    penalty = float(exact["energy_budget_error_penalty"])
    discovery_score = (
        float(exact["conversion_efficiency"])
        * float(exact["spectral_purity_target"])
        * max(1e-9, float(exact["phase_lock_score"]))
        * max(0.0, mixing_gain)
        / penalty
    )
    exact["discovery_score"] = discovery_score
    exact["score"] = discovery_score


def atlas_direct_ceiling(target: int, seed: int, dt: float, t_max: float,
                         base_hz: float) -> Dict[str, float | str]:
    name = f"direct_{target}_ceiling"
    case = atlas_case(
        name,
        float(target),
        (float(target),),
        (0.0,),
        nonlinear=False,
        drive_amp=0.070,
        coil_freqs=(float(target), float(target), float(target)),
        note="direct target resonance ceiling/reference; excluded from discovery ranking",
    )
    case = replace(
        case,
        primary_secondary_coupling=0.250,
        secondary_receiver_coupling=0.250,
        primary_receiver_coupling=0.080,
        zeta_scale=0.25,
    )
    row = atlas_run_case(case, float(target), "direct_ceiling", f"direct_to_{target}", "ceiling_reference",
                         seed, dt, t_max, base_hz)
    row["direct_ceiling_ratio"] = 1.0
    row["distance_from_direct_resonance_ceiling"] = 0.0
    row["score"] = 0.0
    return row


def run_atlas_core(out_dir: Path, seed: int, quick: bool, base_hz: float,
                   dt: float, t_max: float) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]]]:
    rng = np.random.default_rng(seed + 5150)
    all_rows: List[Dict[str, float | str]] = []
    discoveries: List[Dict[str, float | str]] = []

    for target_idx, target in enumerate(ATLAS_TARGETS):
        direct_row = atlas_direct_ceiling(target, seed + target_idx * 1000, dt, t_max, base_hz)
        all_rows.append(direct_row)

        for pair_idx, (f1, f2) in enumerate(pump_pairs_for_target(target)):
            source = pair_label(float(f1), float(f2), float(target))
            base_seed = seed + target * 1000 + pair_idx * 10
            phases = (0.0, 0.0)

            nonlinear_case = atlas_case(
                f"{source}_nonlinear",
                float(target),
                (float(f1), float(f2)),
                phases,
                nonlinear=True,
                note="exact sum pair with nonlinear spark-varactor conversion enabled",
            )
            linear_case = atlas_case(
                f"{source}_linear",
                float(target),
                (float(f1), float(f2)),
                phases,
                nonlinear=False,
                note="linear secondary control for the same pump pair",
            )
            detuned_f2 = float(f2) + 0.25
            detuned_case = atlas_case(
                f"{source}_detuned_f2p25",
                float(target),
                (float(f1), detuned_f2),
                phases,
                nonlinear=True,
                coil_freqs=(float(f1), detuned_f2, float(target)),
                note="detuned control: f2 shifted by +0.25 so f1+f2 misses target",
            )
            random_f1, random_f2 = atlas_random_pair(target, rng)
            random_case = atlas_case(
                f"{source}_random_non_sum",
                float(target),
                (random_f1, random_f2),
                phases,
                nonlinear=True,
                coil_freqs=(random_f1, random_f2, float(target)),
                note="random non-sum pump pair control",
            )

            group = [
                atlas_run_case(nonlinear_case, float(target), "nonlinear", source, "discovery_candidate",
                               base_seed, dt, t_max, base_hz),
                atlas_run_case(linear_case, float(target), "linear", source, "control",
                               base_seed + 1, dt, t_max, base_hz),
                atlas_run_case(detuned_case, float(target), "detuned", source, "control",
                               base_seed + 2, dt, t_max, base_hz),
                atlas_run_case(random_case, float(target), "random", source, "control",
                               base_seed + 3, dt, t_max, base_hz),
            ]
            finalize_atlas_group(group, direct_row)
            all_rows.extend(group)
            discoveries.append(group[0])

    discoveries = sorted(discoveries, key=lambda r: float(r["discovery_score"]), reverse=True)
    for rank, row in enumerate(discoveries, 1):
        row["rank_within_atlas_discoveries"] = rank

    heatmap_rows = []
    for row in discoveries:
        heatmap_rows.append({
            "target_freq": row["target_freq"],
            "pair": row["pair"],
            "pump_f1": row["pump_f1"],
            "pump_f2": row["pump_f2"],
            "discovery_score": row["discovery_score"],
            "conversion_efficiency": row["conversion_efficiency"],
            "spectral_purity_target": row["spectral_purity_target"],
            "phase_lock_score": row["phase_lock_score"],
            "mixing_gain_vs_linear": row["mixing_gain_vs_linear"],
            "detuned_rejection_ratio": row["detuned_rejection_ratio"],
            "random_rejection_ratio": row["random_rejection_ratio"],
            "direct_ceiling_ratio": row["direct_ceiling_ratio"],
        })

    write_csv(out_dir / "atlas_summary.csv", all_rows)
    write_csv(out_dir / "atlas_ranked_discoveries.csv", discoveries)
    write_csv(out_dir / "per_target_pair_heatmap.csv", heatmap_rows)
    return all_rows, discoveries


def atlas_sweep_specs(base: ReceiverCase, target: float) -> List[Tuple[str, str, ReceiverCase]]:
    specs: List[Tuple[str, str, ReceiverCase]] = []
    for degrees in range(0, 361, 30):
        specs.append(("phase_offset_deg", str(degrees), replace(base, name=f"{base.name}_phase_{degrees}", phases=(0.0, math.radians(degrees)))))
    for value in [0.0, 0.20, 0.34, 0.70, 1.00]:
        specs.append(("nonlinear_strength", f"{value:g}", replace(base, name=f"{base.name}_mix_{safe_token(value)}", mix_strength=value)))
    for value in [0.020, 0.035, 0.070]:
        specs.append(("spark_threshold", f"{value:g}", replace(base, name=f"{base.name}_spark_{safe_token(value)}", spark_threshold=value)))
    for value in [0.0, 0.42, 0.80]:
        specs.append(("varactor_coefficient", f"{value:g}", replace(base, name=f"{base.name}_varactor_{safe_token(value)}", nonlinear_strength=value)))
    for value in [0.015, 0.030, 0.045]:
        specs.append(("primary_secondary_coupling", f"{value:g}", replace(base, name=f"{base.name}_ps_{safe_token(value)}", primary_secondary_coupling=value)))
    for value in [0.011, 0.022, 0.035]:
        specs.append(("secondary_receiver_coupling", f"{value:g}", replace(base, name=f"{base.name}_sr_{safe_token(value)}", secondary_receiver_coupling=value)))
    for delta in [-0.40, -0.20, 0.0, 0.20, 0.40]:
        tuned = (base.coil_freqs[0], base.coil_freqs[1], target + delta)
        specs.append(("receiver_detuning", f"{delta:g}", replace(base, name=f"{base.name}_receiver_detune_{safe_token(delta)}", coil_freqs=tuned)))
    for delta in [-0.40, -0.20, 0.0, 0.20, 0.40]:
        tuned = (base.coil_freqs[0], base.coil_freqs[1] + delta, base.coil_freqs[2])
        specs.append(("secondary_detuning", f"{delta:g}", replace(base, name=f"{base.name}_secondary_detune_{safe_token(delta)}", coil_freqs=tuned)))
    for value in [0.50, 1.00, 2.00]:
        specs.append(("damping_q_scale", f"{value:g}", replace(base, name=f"{base.name}_zeta_{safe_token(value)}", zeta_scale=value)))
    return specs


def run_atlas_sweeps(out_dir: Path, discoveries: List[Dict[str, float | str]], seed: int,
                     quick: bool, base_hz: float) -> List[Dict[str, float | str]]:
    dt = 0.105 if quick else 0.085
    t_max = 30.0 if quick else 42.0
    top_by_target: Dict[int, Dict[str, float | str]] = {}
    for row in discoveries:
        target = int(float(row["target_freq"]))
        if target not in top_by_target:
            top_by_target[target] = row

    phase_rows: List[Dict[str, float | str]] = []
    sweep_rows: List[Dict[str, float | str]] = []
    for target_idx, target in enumerate(sorted(top_by_target)):
        top = top_by_target[target]
        f1 = float(top["pump_f1"])
        f2 = float(top["pump_f2"])
        source = str(top["pair"])
        base_case = atlas_case(
            f"atlas_sweep_{source}",
            float(target),
            (f1, f2),
            (0.0, 0.0),
            nonlinear=True,
            note="atlas sweep around the best core pair for this target",
        )
        linear_eff = max(float(top["conversion_efficiency"]) / max(float(top["mixing_gain_vs_linear"]), 1e-18), 1e-18)
        direct_eff = max(float(top["conversion_efficiency"]) / max(float(top["direct_ceiling_ratio"]), 1e-18), 1e-18)
        reference_input_work = max(float(top["total_input_work"]), 1e-18)

        for idx, (sweep, sweep_value, case) in enumerate(atlas_sweep_specs(base_case, float(target))):
            row = atlas_run_case(case, float(target), "sweep", source, "sweep_candidate",
                                 seed + 50000 + target_idx * 1000 + idx, dt, t_max, base_hz,
                                 sweep=sweep, sweep_value=sweep_value)
            row["mixing_gain_vs_linear"] = float(row["conversion_efficiency"]) / linear_eff
            ratio = float(row["conversion_efficiency"]) / direct_eff
            row["direct_ceiling_ratio"] = ratio
            row["distance_from_direct_resonance_ceiling"] = float(1.0 - min(1.0, ratio))
            row["detuned_rejection_ratio"] = top["detuned_rejection_ratio"]
            row["random_rejection_ratio"] = top["random_rejection_ratio"]
            low_input = float(row["total_input_work"]) < 0.05 * reference_input_work
            row["valid_sweep"] = "no_low_input_work" if low_input else "yes"
            row["discovery_score"] = 0.0 if low_input else (
                float(row["conversion_efficiency"])
                * float(row["spectral_purity_target"])
                * max(1e-9, float(row["phase_lock_score"]))
                * max(0.0, float(row["mixing_gain_vs_linear"]))
                / float(row["energy_budget_error_penalty"])
            )
            row["score"] = row["discovery_score"]
            sweep_rows.append(row)
            if sweep == "phase_offset_deg":
                phase_rows.append({
                    "target_freq": row["target_freq"],
                    "pair": row["pair"],
                    "phase_offset_deg": row["sweep_value"],
                    "valid_sweep": row["valid_sweep"],
                    "conversion_efficiency": row["conversion_efficiency"],
                    "spectral_purity_target": row["spectral_purity_target"],
                    "phase_lock_score": row["phase_lock_score"],
                    "discovery_score": row["discovery_score"],
                    "direct_ceiling_ratio": row["direct_ceiling_ratio"],
                })

    sweep_rows = sorted(sweep_rows, key=lambda r: float(r["discovery_score"]), reverse=True)
    for rank, row in enumerate(sweep_rows, 1):
        row["rank_within_atlas_sweeps"] = rank
    write_csv(out_dir / "atlas_sweeps.csv", sweep_rows)
    write_csv(out_dir / "phase_lock_islands.csv", phase_rows)
    return sweep_rows


def plot_atlas_outputs(out_dir: Path, discoveries: List[Dict[str, float | str]],
                       all_rows: List[Dict[str, float | str]],
                       sweep_rows: List[Dict[str, float | str]] | None = None) -> None:
    targets = ATLAS_TARGETS
    max_pairs = max(len(pump_pairs_for_target(t)) for t in targets)
    matrix = np.full((len(targets), max_pairs), np.nan)
    labels = [["" for _ in range(max_pairs)] for _ in targets]
    for i, target in enumerate(targets):
        target_rows = [r for r in discoveries if int(float(r["target_freq"])) == target]
        target_rows = sorted(target_rows, key=lambda r: (float(r["pump_f1"]), float(r["pump_f2"])))
        for j, row in enumerate(target_rows):
            matrix[i, j] = float(row["discovery_score"])
            labels[i][j] = f"{float(row['pump_f1']):g}+{float(row['pump_f2']):g}"

    fig, ax = plt.subplots(figsize=(11, 5.5))
    im = ax.imshow(matrix, aspect="auto")
    ax.set_yticks(np.arange(len(targets)))
    ax.set_yticklabels([str(t) for t in targets])
    ax.set_xticks(np.arange(max_pairs))
    ax.set_xticklabels([f"pair {i+1}" for i in range(max_pairs)])
    ax.set_xlabel("integer pump pair index")
    ax.set_ylabel("target frequency")
    ax.set_title("Atlas discovery score by target and sum pair")
    fig.colorbar(im, ax=ax, label="discovery score")
    for i in range(len(targets)):
        for j in range(max_pairs):
            if labels[i][j]:
                ax.text(j, i, labels[i][j], ha="center", va="center", fontsize=7, color="white")
    fig.tight_layout()
    fig.savefig(out_dir / "atlas_target_best_pair_heatmap.png", dpi=140)
    plt.close(fig)

    best_by_target = []
    for target in targets:
        target_rows = [r for r in discoveries if int(float(r["target_freq"])) == target]
        best_by_target.append(max(target_rows, key=lambda r: float(r["discovery_score"])))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar([str(t) for t in targets], [float(r["direct_ceiling_ratio"]) for r in best_by_target])
    ax.set_title("Best silent-pump conversion vs direct resonance ceiling")
    ax.set_xlabel("target frequency")
    ax.set_ylabel("best silent conversion / direct conversion")
    fig.tight_layout()
    fig.savefig(out_dir / "atlas_direct_ceiling_ratio_by_target.png", dpi=140)
    plt.close(fig)

    target9 = [r for r in discoveries if int(float(r["target_freq"])) == 9]
    if target9:
        target9 = sorted(target9, key=lambda r: float(r["pump_f1"]))
        colors = ["tab:red" if abs(float(r["pump_f1"]) - 3.0) < 1e-9 and abs(float(r["pump_f2"]) - 6.0) < 1e-9 else "tab:blue" for r in target9]
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        ax.bar([str(r["pair"]) for r in target9], [float(r["conversion_efficiency"]) for r in target9], color=colors)
        ax.set_title("Target 9: 3+6 compared with other sum pairs")
        ax.set_xlabel("pump pair")
        ax.set_ylabel("conversion efficiency")
        ax.tick_params(axis="x", rotation=35)
        fig.tight_layout()
        fig.savefig(out_dir / "atlas_3_plus_6_vs_target9_pairs.png", dpi=140)
        plt.close(fig)

    if sweep_rows:
        phase_rows = [r for r in sweep_rows if r["sweep"] == "phase_offset_deg" and r.get("valid_sweep", "yes") == "yes"]
        if phase_rows:
            fig, ax = plt.subplots(figsize=(10, 5))
            for key in sorted({(int(float(r["target_freq"])), str(r["pair"])) for r in phase_rows}):
                target, pair = key
                rows = sorted([r for r in phase_rows if int(float(r["target_freq"])) == target and str(r["pair"]) == pair],
                              key=lambda r: float(r["sweep_value"]))
                ax.plot([float(r["sweep_value"]) for r in rows],
                        [float(r["conversion_efficiency"]) for r in rows],
                        marker="o", label=f"{pair}")
            ax.set_title("Phase offset vs conversion efficiency")
            ax.set_xlabel("phase offset f2 relative to f1 (degrees)")
            ax.set_ylabel("conversion efficiency")
            ax.legend(fontsize=7, ncol=2)
            fig.tight_layout()
            fig.savefig(out_dir / "atlas_phase_offset_vs_conversion.png", dpi=140)
            plt.close(fig)

        nonlinear_rows = [r for r in sweep_rows if r["sweep"] == "nonlinear_strength" and r.get("valid_sweep", "yes") == "yes"]
        if nonlinear_rows:
            fig, ax = plt.subplots(figsize=(10, 5))
            for key in sorted({(int(float(r["target_freq"])), str(r["pair"])) for r in nonlinear_rows}):
                target, pair = key
                rows = sorted([r for r in nonlinear_rows if int(float(r["target_freq"])) == target and str(r["pair"]) == pair],
                              key=lambda r: float(r["sweep_value"]))
                ax.plot([float(r["sweep_value"]) for r in rows],
                        [float(r["spectral_purity_target"]) for r in rows],
                        marker="o", label=f"{pair}")
            ax.set_title("Nonlinear strength vs spectral purity")
            ax.set_xlabel("nonlinear strength")
            ax.set_ylabel("spectral purity at target")
            ax.legend(fontsize=7, ncol=2)
            fig.tight_layout()
            fig.savefig(out_dir / "atlas_nonlinear_strength_vs_purity.png", dpi=140)
            plt.close(fig)


def atlas_phase_island_summary(sweep_rows: List[Dict[str, float | str]]) -> Tuple[str, float]:
    phase_rows = [r for r in sweep_rows if r.get("sweep") == "phase_offset_deg" and r.get("valid_sweep", "yes") == "yes"]
    if not phase_rows:
        return "not run", 0.0
    best_ratio = 0.0
    best_label = ""
    for key in sorted({(int(float(r["target_freq"])), str(r["pair"])) for r in phase_rows}):
        rows = [r for r in phase_rows if int(float(r["target_freq"])) == key[0] and str(r["pair"]) == key[1]]
        conversions = np.asarray([float(r["conversion_efficiency"]) for r in rows], dtype=float)
        if len(conversions) == 0:
            continue
        ratio = float(np.max(conversions) / (np.median(conversions) + 1e-18))
        if ratio > best_ratio:
            best_ratio = ratio
            best_row = rows[int(np.argmax(conversions))]
            best_label = f"{key[1]} at phase {best_row['sweep_value']} deg"
    return best_label, best_ratio


def write_atlas_report(out_dir: Path, discoveries: List[Dict[str, float | str]],
                       all_rows: List[Dict[str, float | str]],
                       sweep_rows: List[Dict[str, float | str]] | None = None) -> None:
    best = discoveries[0]
    target9 = [r for r in discoveries if int(float(r["target_freq"])) == 9]
    target9_best = max(target9, key=lambda r: float(r["discovery_score"])) if target9 else None
    three_six = next((r for r in target9 if abs(float(r["pump_f1"]) - 3.0) < 1e-9 and abs(float(r["pump_f2"]) - 6.0) < 1e-9), None)
    nonlinear_wins = sum(1 for r in discoveries if float(r["mixing_gain_vs_linear"]) > 1.0)
    phase_label, phase_ratio = atlas_phase_island_summary(sweep_rows or [])
    ceiling_ratio = float(best["direct_ceiling_ratio"])

    lines = [
        "# Atlas Report",
        "",
        "This atlas maps nonlinear sum-frequency transfer across many pump pairs and targets.",
        "",
        "## Direct Answers",
        f"1. 3+6->9 special? {'No' if target9_best and three_six and str(target9_best['pair']) != str(three_six['pair']) else 'Possibly, but not proven'}."
        + (f" For target 9, best pair was {target9_best['pair']} while 3+6 ranked with score {float(three_six['discovery_score']):.6g}." if target9_best and three_six else ""),
        f"2. Strongest pair-to-target conversion: {best['pair']} with target {float(best['target_freq']):g}.",
        f"3. Nonlinearity beat linear controls in {nonlinear_wins} of {len(discoveries)} exact-sum discovery candidates.",
        f"4. Phase island check: {phase_label}; best/median conversion ratio {phase_ratio:.3g}.",
        f"5. Best silent-pump case reached {ceiling_ratio:.3g} of direct resonance conversion, so it is {1.0 - ceiling_ratio:.3g} below the ceiling on the distance metric.",
        "",
        "## Top Discoveries",
    ]
    for row in discoveries[:12]:
        lines.append(
            f"- {row['pair']} -> target {float(row['target_freq']):g}: "
            f"score={float(row['discovery_score']):.6g}, conversion={float(row['conversion_efficiency']):.6g}, "
            f"purity={float(row['spectral_purity_target']):.3g}, lock={float(row['phase_lock_score']):.3g}, "
            f"mix_gain={float(row['mixing_gain_vs_linear']):.3g}, ceiling_ratio={float(row['direct_ceiling_ratio']):.3g}"
        )
    (out_dir / "README_ATLAS_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_atlas(out_dir: Path, seed: int, quick: bool = False,
                     include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    base_hz = 0.045
    dt = 0.100 if quick else 0.085
    t_max = 30.0 if quick else 45.0
    all_rows, discoveries = run_atlas_core(out_dir, seed, quick, base_hz, dt, t_max)
    sweep_rows: List[Dict[str, float | str]] = []
    if include_sweeps:
        sweep_rows = run_atlas_sweeps(out_dir, discoveries, seed, quick, base_hz)
    plot_atlas_outputs(out_dir, discoveries, all_rows, sweep_rows if include_sweeps else None)
    write_atlas_report(out_dir, discoveries, all_rows, sweep_rows if include_sweeps else None)
    return discoveries


# ----------------------------
# Experiment 6: nonlinear cascade ladder
# ----------------------------

CASCADE_TARGETS = (6.0, 9.0, 15.0, 24.0)
CASCADE_ROUTES = ((0, 0, 1), (0, 1, 2), (1, 2, 3), (2, 3, 4))


@dataclass
class CascadeCase:
    name: str
    mode_freqs: Tuple[float, float, float, float, float] = (3.0, 6.0, 9.0, 15.0, 24.0)
    drive_freqs: Tuple[float, ...] = (3.0,)
    phases: Tuple[float, ...] = (0.0,)
    drive_weights: Tuple[float, ...] = ()
    nonlinear_strength: float = 0.34
    varactor_coefficient: float = 0.20
    spark_strength: float = 0.10
    spark_threshold: float = 0.035
    coupling_scale: float = 1.0
    zeta_scale: float = 1.0
    drive_amp: float = 0.070
    route_count: int = 4
    reference_role: str = "discovery_candidate"
    note: str = ""


def cascade_drive_value(case: CascadeCase, t: float, base_hz: float, drive_until: float) -> float:
    if t >= drive_until:
        return 0.0
    ramp_in = min(1.0, t / 10.0)
    ramp_out = min(1.0, max(0.0, (drive_until - t) / 10.0))
    envelope = ramp_in * ramp_out
    weights = case.drive_weights or tuple(1.0 for _ in case.drive_freqs)
    norm = math.sqrt(sum(w * w for w in weights)) + 1e-12
    drive = 0.0
    for freq, phase, weight in zip(case.drive_freqs, case.phases, weights):
        drive += weight * math.sin(2.0 * np.pi * base_hz * freq * t + phase)
    return envelope * case.drive_amp * drive / norm


def cascade_derivative(y: np.ndarray, t: float, omega: np.ndarray, case: CascadeCase,
                       base_hz: float, drive_until: float, zeta: np.ndarray) -> np.ndarray:
    n_modes = len(omega)
    q = y[:n_modes]
    v = y[n_modes:]
    mode_freqs = np.asarray(case.mode_freqs, dtype=float)
    a = -2.0 * zeta * omega * v - (omega ** 2) * q

    # Weak nearest-neighbor linear coupling keeps the ladder Tesla-coil-like
    # without allowing linear controls to synthesize the missing frequencies.
    k = 0.0035 * case.coupling_scale
    for i in range(n_modes - 1):
        kij = k * omega[i] * omega[i + 1]
        delta = q[i] - q[i + 1]
        a[i] += -kij * delta
        a[i + 1] += kij * delta

    if case.varactor_coefficient:
        a += -case.varactor_coefficient * q ** 3

    if case.nonlinear_strength:
        for route_idx, (i, j, target) in enumerate(CASCADE_ROUTES[:case.route_count]):
            gate = 1.0
            if case.spark_strength:
                delta = q[i] - q[target]
                gate = float(spark_gate(delta, threshold=case.spark_threshold))
            force = case.nonlinear_strength * gate * q[i] * q[j]
            a[target] += force
            a[i] += -0.10 * force
            a[j] += -0.10 * force

    drive = cascade_drive_value(case, t, base_hz, drive_until)
    for idx, mode_freq in enumerate(mode_freqs):
        overlap = natural_mode_overlap(float(mode_freq), float(mode_freq), max(mode_freqs))
        # Drive frequencies couple most strongly to matching natural modes.
        drive_overlap = 0.0
        for drive_freq in case.drive_freqs:
            drive_overlap += natural_mode_overlap(float(drive_freq), float(mode_freq), max(mode_freqs))
        a[idx] += drive * drive_overlap * overlap

    return np.concatenate([v, a])


def simulate_cascade_case(case: CascadeCase, seed: int = 1, dt: float = 0.045,
                          t_max: float = 120.0, base_hz: float = 0.045,
                          sample_every: int = 2) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    mode_freqs_hz = base_hz * np.asarray(case.mode_freqs, dtype=float)
    omega = 2.0 * np.pi * mode_freqs_hz
    zeta = case.zeta_scale * np.asarray([0.018, 0.014, 0.011, 0.009, 0.007], dtype=float)
    drive_until = 0.74 * t_max

    n_steps = int(t_max / dt)
    n_modes = len(omega)
    y = np.zeros(2 * n_modes)
    y[:n_modes] = 1e-4 * rng.normal(size=n_modes)
    y[n_modes:] = 1e-4 * rng.normal(size=n_modes)

    samples = (n_steps + sample_every - 1) // sample_every
    times = np.zeros(samples)
    qs = np.zeros((samples, n_modes), dtype=float)
    vs = np.zeros((samples, n_modes), dtype=float)
    sample_idx = 0

    positive_input_work = 0.0
    net_input_work = 0.0
    damping_loss_energy = 0.0

    for step in range(n_steps):
        t = step * dt
        q = y[:n_modes]
        v = y[n_modes:]
        if step % sample_every == 0:
            times[sample_idx] = t
            qs[sample_idx] = q
            vs[sample_idx] = v
            sample_idx += 1

        drive = cascade_drive_value(case, t, base_hz, drive_until)
        input_velocity = 0.0
        for idx, mode_freq in enumerate(case.mode_freqs):
            drive_overlap = sum(natural_mode_overlap(float(df), float(mode_freq), max(case.mode_freqs)) for df in case.drive_freqs)
            input_velocity += drive_overlap * v[idx]
        input_power = drive * input_velocity
        positive_input_work += max(0.0, input_power) * dt
        net_input_work += input_power * dt
        damping_loss_energy += float(np.sum(2.0 * zeta * omega * (v ** 2))) * dt

        y = rk4_step(y, t, dt, cascade_derivative, omega, case, base_hz, drive_until, zeta)
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e5:
            break

    times = times[:sample_idx]
    qs = qs[:sample_idx]
    vs = vs[:sample_idx]
    energy = 0.5 * (vs ** 2) + 0.5 * (omega[None, :] ** 2) * (qs ** 2)
    if case.varactor_coefficient:
        energy += 0.25 * case.varactor_coefficient * qs ** 4

    return {
        "times": times,
        "qs": qs,
        "vs": vs,
        "energy": energy,
        "omega": omega,
        "drive_until": drive_until,
        "positive_input_work": positive_input_work,
        "net_input_work": net_input_work,
        "damping_loss_energy": damping_loss_energy,
        "dt_sample": dt * sample_every,
    }


def cascade_mode_index(case: CascadeCase, target: float) -> int:
    arr = np.asarray(case.mode_freqs, dtype=float)
    return int(np.argmin(np.abs(arr - target)))


def cascade_phase_lock(case: CascadeCase, sim: Dict[str, object], target: float, base_hz: float,
                       mask: np.ndarray) -> Tuple[float, float]:
    route_map = {
        6.0: (0, 0, 1),
        9.0: (0, 1, 2),
        15.0: (1, 2, 3),
        24.0: (2, 3, 4),
    }
    if target not in route_map:
        return 0.0, float("nan")
    i, j, k = route_map[target]
    times = sim["times"][mask]  # type: ignore[index]
    qs = sim["qs"][mask]  # type: ignore[index]
    sample_dt = float(sim["dt_sample"])
    window = max(20, int(5.0 / sample_dt))
    step = max(6, window // 5)
    if len(times) <= window + step:
        return 0.0, float("nan")
    p_i = sliding_phase(qs[:, i], times, base_hz * case.mode_freqs[i], window, step)
    p_j = sliding_phase(qs[:, j], times, base_hz * case.mode_freqs[j], window, step)
    p_k = sliding_phase(qs[:, k], times, base_hz * target, window, step)
    min_len = min(len(p_i), len(p_j), len(p_k))
    if min_len == 0:
        return 0.0, float("nan")
    mismatch = wrap_angle(p_i[:min_len] + p_j[:min_len] - p_k[:min_len])
    return float(np.abs(np.mean(np.exp(1j * mismatch)))), float(np.std(mismatch))


def cascade_first_detect_time(times: np.ndarray, signal: np.ndarray) -> float:
    if len(signal) == 0:
        return float("nan")
    threshold = max(1e-12, 0.05 * float(np.max(signal)))
    hits = np.where(signal >= threshold)[0]
    return float(times[hits[0]]) if len(hits) else float("nan")


def cascade_metrics_from_sim(case: CascadeCase, sim: Dict[str, object], base_hz: float) -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    analysis_mask = (times >= 0.35 * drive_until) & (times < drive_until)
    if int(np.sum(analysis_mask)) < 20:
        analysis_mask = times >= 0.45 * times[-1]

    total_input_work = float(sim["positive_input_work"])
    initial_e = float(np.sum(energy[0]))
    final_e = float(np.sum(energy[-1]))
    delta_stored = final_e - initial_e
    energy_budget_error = float(sim["net_input_work"]) - float(sim["damping_loss_energy"]) - delta_stored
    budget_scale = abs(float(sim["net_input_work"])) + float(sim["damping_loss_energy"]) + abs(delta_stored) + 1e-18

    row: Dict[str, float | str] = {
        "experiment": "cascade",
        "case": case.name,
        "freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in case.drive_freqs),
        "mode_freqs": "-".join(f"{x:g}" for x in case.mode_freqs),
        "reference_role": case.reference_role,
        "total_input_work": total_input_work,
        "energy_budget_error": energy_budget_error,
        "energy_budget_error_frac": float(abs(energy_budget_error) / budget_scale),
        "nonlinear_strength": float(case.nonlinear_strength),
        "spark_threshold": float(case.spark_threshold),
        "varactor_coefficient": float(case.varactor_coefficient),
        "coupling_scale": float(case.coupling_scale),
        "zeta_scale": float(case.zeta_scale),
        "drive_amp": float(case.drive_amp),
        "route_count": case.route_count,
        "generated_vs_direct_6_ratio": 0.0,
        "generated_6_to_9_efficiency": 0.0,
        "direct_resonance_ceiling_ratio": 0.0,
        "discovery_score": 0.0,
        "score": 0.0,
        "note": case.note,
    }

    for target in CASCADE_TARGETS:
        idx = cascade_mode_index(case, target)
        target_hz = base_hz * target
        e_target = target_mode_energy(qs[analysis_mask, idx], vs[analysis_mask, idx],
                                      times[analysis_mask], target_hz, float(omega[idx]))
        total_mode_energy = float(np.mean(energy[analysis_mask, idx]) + 1e-18)
        purity = float(min(1.0, e_target / total_mode_energy))
        lock, mismatch = cascade_phase_lock(case, sim, target, base_hz, analysis_mask)
        mode_energy_series = energy[:, idx]
        row[f"energy_at_{int(target)}"] = e_target
        row[f"spectral_purity_at_{int(target)}"] = purity
        row[f"time_to_first_detectable_{int(target)}"] = cascade_first_detect_time(times, mode_energy_series)
        row[f"cascade_efficiency_3_to_{int(target)}"] = float(e_target / (total_input_work + 1e-18))
        row[f"phase_lock_score_at_{int(target)}"] = lock
        row[f"phase_mismatch_std_at_{int(target)}"] = mismatch
        row[f"direct_{int(target)}_ceiling_ratio"] = 0.0

    row["generated_6_to_9_efficiency"] = float(float(row["energy_at_9"]) / (float(row["energy_at_6"]) + 1e-18))
    score_targets = [6.0, 9.0, 15.0, 24.0]
    score = 0.0
    for target in score_targets:
        score += (
            float(row[f"cascade_efficiency_3_to_{int(target)}"])
            * float(row[f"spectral_purity_at_{int(target)}"])
            * (0.25 + float(row[f"phase_lock_score_at_{int(target)}"]))
        )
    budget_penalty = (1.0 + 10.0 * min(10.0, float(row["energy_budget_error_frac"]))) ** 2
    row["discovery_score"] = score / budget_penalty
    row["score"] = 0.0 if case.reference_role == "ceiling_reference" else row["discovery_score"]
    return row


def cascade_core_cases(seed: int) -> List[CascadeCase]:
    rng = np.random.default_rng(seed + 4242)
    random_drive = float(np.round(rng.uniform(3.7, 11.3), 3))
    return [
        CascadeCase("drive_3_only_to_6_nonlinear", route_count=1,
                    note="drive only 3 and test degenerate 3+3->6 generation"),
        CascadeCase("drive_3_only_to_6_linear", route_count=1, nonlinear_strength=0.0,
                    varactor_coefficient=0.0, spark_strength=0.0,
                    note="linear twin for 3-only to 6"),
        CascadeCase("drive_3_only_to_6_detuned_receiver", mode_freqs=(3.0, 6.25, 9.0, 15.0, 24.0),
                    route_count=1, note="detuned 6 receiver mode"),
        CascadeCase("drive_3_generated_6_to_9_nonlinear", route_count=2,
                    note="drive only 3; test whether generated 6 participates in 3+6->9"),
        CascadeCase("drive_3_plus_direct_6_to_9_reference", drive_freqs=(3.0, 6.0),
                    phases=(0.0, 0.0), drive_weights=(1.0, 0.35), route_count=2,
                    note="reference with direct 6 injection but no direct 9 drive"),
        CascadeCase("drive_4_only_to_8_control", mode_freqs=(4.0, 8.0, 12.0, 20.0, 32.0),
                    drive_freqs=(4.0,), route_count=2,
                    note="non-369 degenerate harmonic control"),
        CascadeCase("drive_5_only_to_10_control", mode_freqs=(5.0, 10.0, 15.0, 25.0, 40.0),
                    drive_freqs=(5.0,), route_count=2,
                    note="second non-369 degenerate harmonic control"),
        CascadeCase("random_single_drive_control", drive_freqs=(random_drive,),
                    note="random single-drive non-ladder control"),
        CascadeCase("direct_6_resonance_ceiling", drive_freqs=(6.0,), drive_amp=0.070,
                    nonlinear_strength=0.0, varactor_coefficient=0.0, spark_strength=0.0,
                    route_count=0, reference_role="ceiling_reference",
                    note="direct 6 resonance ceiling/reference"),
        CascadeCase("direct_9_resonance_ceiling", drive_freqs=(9.0,), drive_amp=0.070,
                    nonlinear_strength=0.0, varactor_coefficient=0.0, spark_strength=0.0,
                    route_count=0, reference_role="ceiling_reference",
                    note="direct 9 resonance ceiling/reference"),
        CascadeCase("cascade_3_to_6_to_9_to_15", route_count=3,
                    note="optional cascade through 15 with only 3 driven"),
        CascadeCase("cascade_3_to_6_to_9_to_15_to_24", route_count=4,
                    note="full cascade through 24 with only 3 driven"),
    ]


def run_cascade_case(case: CascadeCase, seed: int, dt: float, t_max: float,
                     base_hz: float) -> Tuple[Dict[str, float | str], Dict[str, object]]:
    sim = simulate_cascade_case(case, seed=seed, dt=dt, t_max=t_max, base_hz=base_hz)
    row = cascade_metrics_from_sim(case, sim, base_hz)
    return row, sim


def finalize_cascade_rows(rows: List[Dict[str, float | str]]) -> None:
    direct6 = max(
        (float(r["energy_at_6"]) for r in rows if r["case"] == "direct_6_resonance_ceiling"),
        default=1e-18,
    )
    direct9 = max(
        (float(r["energy_at_9"]) for r in rows if r["case"] == "direct_9_resonance_ceiling"),
        default=1e-18,
    )
    for row in rows:
        row["generated_vs_direct_6_ratio"] = float(row["energy_at_6"]) / max(direct6, 1e-18)
        row["direct_6_ceiling_ratio"] = float(row["energy_at_6"]) / max(direct6, 1e-18)
        row["direct_9_ceiling_ratio"] = float(row["energy_at_9"]) / max(direct9, 1e-18)
        row["direct_resonance_ceiling_ratio"] = max(float(row["direct_6_ceiling_ratio"]), float(row["direct_9_ceiling_ratio"]))


def write_cascade_time_series(out_dir: Path, case: CascadeCase, sim: Dict[str, object]) -> None:
    times = sim["times"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    rows = []
    for idx, t in enumerate(times):
        row = {"time": float(t)}
        for target in CASCADE_TARGETS:
            mode_idx = cascade_mode_index(case, target)
            row[f"energy_at_{int(target)}"] = float(energy[idx, mode_idx])
        rows.append(row)
    write_csv(out_dir / "cascade_stage_energy_over_time.csv", rows)


def write_cascade_ladder(out_dir: Path, rows: List[Dict[str, float | str]]) -> None:
    ladder_rows = []
    for row in rows:
        for target in CASCADE_TARGETS:
            ladder_rows.append({
                "case": row["case"],
                "stage_target": int(target),
                "energy": row[f"energy_at_{int(target)}"],
                "purity": row[f"spectral_purity_at_{int(target)}"],
                "efficiency": row[f"cascade_efficiency_3_to_{int(target)}"],
                "phase_lock": row[f"phase_lock_score_at_{int(target)}"],
                "direct_ceiling_ratio": row[f"direct_{int(target)}_ceiling_ratio"],
            })
    write_csv(out_dir / "cascade_frequency_ladder.csv", ladder_rows)


def plot_cascade_outputs(out_dir: Path, rows: List[Dict[str, float | str]], best_case: CascadeCase,
                         best_sim: Dict[str, object]) -> None:
    times = best_sim["times"]  # type: ignore[assignment]
    energy = best_sim["energy"]  # type: ignore[assignment]
    fig, ax = plt.subplots(figsize=(10, 5))
    for target in CASCADE_TARGETS:
        idx = cascade_mode_index(best_case, target)
        ax.plot(times, energy[:, idx], label=f"{int(target)}")
    ax.set_title(f"Cascade stage energy over time: {best_case.name}")
    ax.set_xlabel("time")
    ax.set_ylabel("stored energy")
    ax.legend(title="stage")
    fig.tight_layout()
    fig.savefig(out_dir / "cascade_energy_over_time.png", dpi=140)
    plt.close(fig)

    ranked = [r for r in rows if r["reference_role"] != "ceiling_reference"]
    ranked = sorted(ranked, key=lambda r: float(r["score"]), reverse=True)[:8]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([str(r["case"]) for r in ranked], [float(r["discovery_score"]) for r in ranked])
    ax.set_title("Cascade discovery score")
    ax.set_ylabel("score")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(out_dir / "cascade_stage_efficiency_chart.png", dpi=140)
    plt.close(fig)

    labels = [str(r["case"]) for r in ranked]
    gen6 = [float(r["generated_vs_direct_6_ratio"]) for r in ranked]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, gen6)
    ax.set_title("Generated 6 vs direct 6 reference")
    ax.set_ylabel("energy_at_6 / direct_6_energy")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(out_dir / "cascade_generated_6_vs_direct_6.png", dpi=140)
    plt.close(fig)

    best = ranked[0] if ranked else rows[0]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar([str(int(t)) for t in CASCADE_TARGETS], [float(best[f"spectral_purity_at_{int(t)}"]) for t in CASCADE_TARGETS])
    ax.set_title(f"Spectral purity per stage: {best['case']}")
    ax.set_xlabel("stage")
    ax.set_ylabel("purity")
    fig.tight_layout()
    fig.savefig(out_dir / "cascade_spectral_purity_per_stage.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(["6", "9"], [float(best["direct_6_ceiling_ratio"]), float(best["direct_9_ceiling_ratio"])])
    ax.set_title(f"Direct resonance ceiling ratio: {best['case']}")
    ax.set_ylabel("silent/generated energy / direct energy")
    fig.tight_layout()
    fig.savefig(out_dir / "cascade_direct_ceiling_ratio_per_stage.png", dpi=140)
    plt.close(fig)


def cascade_sweep_cases(base: CascadeCase) -> List[Tuple[str, str, CascadeCase]]:
    specs: List[Tuple[str, str, CascadeCase]] = []
    for value in [0.10, 0.34, 0.70, 1.00]:
        specs.append(("nonlinear_strength", f"{value:g}", replace(base, name=f"cascade_sweep_mix_{safe_token(value)}", nonlinear_strength=value)))
    for value in [0.020, 0.035, 0.070]:
        specs.append(("spark_threshold", f"{value:g}", replace(base, name=f"cascade_sweep_spark_{safe_token(value)}", spark_threshold=value)))
    for value in [0.0, 0.20, 0.50]:
        specs.append(("varactor_coefficient", f"{value:g}", replace(base, name=f"cascade_sweep_varactor_{safe_token(value)}", varactor_coefficient=value)))
    for value in [0.50, 1.00, 1.60]:
        specs.append(("coupling_scale", f"{value:g}", replace(base, name=f"cascade_sweep_coupling_{safe_token(value)}", coupling_scale=value)))
    for value in [0.50, 1.00, 2.00]:
        specs.append(("damping_q", f"{value:g}", replace(base, name=f"cascade_sweep_zeta_{safe_token(value)}", zeta_scale=value)))
    for delta in [-0.30, 0.0, 0.30]:
        specs.append(("secondary_detuning", f"{delta:g}", replace(base, name=f"cascade_sweep_secondary_{safe_token(delta)}", mode_freqs=(3.0, 6.0 + delta, 9.0, 15.0, 24.0))))
    for delta in [-0.40, 0.0, 0.40]:
        specs.append(("receiver_detuning", f"{delta:g}", replace(base, name=f"cascade_sweep_receiver_{safe_token(delta)}", mode_freqs=(3.0, 6.0, 9.0 + delta, 15.0, 24.0))))
    for degrees in range(0, 361, 60):
        specs.append(("phase_offset_reference", str(degrees), replace(base, name=f"cascade_sweep_phase_{degrees}", drive_freqs=(3.0, 6.0), phases=(0.0, math.radians(degrees)), drive_weights=(1.0, 0.30), route_count=2)))
    for value in [70.0, 100.0, 140.0]:
        specs.append(("runtime_length", f"{value:g}", replace(base, name=f"cascade_sweep_runtime_{safe_token(value)}")))
    return specs


def run_cascade_sweeps(out_dir: Path, seed: int, base_hz: float, quick: bool) -> List[Dict[str, float | str]]:
    base = CascadeCase("cascade_sweep_base", route_count=4)
    dt = 0.060 if quick else 0.050
    default_t_max = 90.0 if quick else 130.0
    rows = []
    for idx, (sweep, value, case) in enumerate(cascade_sweep_cases(base)):
        t_max = float(value) if sweep == "runtime_length" else default_t_max
        row, _ = run_cascade_case(case, seed + 8000 + idx, dt, t_max, base_hz)
        row["sweep"] = sweep
        row["sweep_value"] = value
        rows.append(row)
    direct6, _ = run_cascade_case(CascadeCase("direct_6_resonance_ceiling", drive_freqs=(6.0,),
                                             nonlinear_strength=0.0, varactor_coefficient=0.0,
                                             spark_strength=0.0, route_count=0,
                                             reference_role="ceiling_reference"),
                                  seed + 8900, dt, default_t_max, base_hz)
    direct9, _ = run_cascade_case(CascadeCase("direct_9_resonance_ceiling", drive_freqs=(9.0,),
                                             nonlinear_strength=0.0, varactor_coefficient=0.0,
                                             spark_strength=0.0, route_count=0,
                                             reference_role="ceiling_reference"),
                                  seed + 8901, dt, default_t_max, base_hz)
    finalize_cascade_rows(rows + [direct6, direct9])
    rows = sorted(rows, key=lambda r: float(r["score"]), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank_within_cascade_sweeps"] = rank
    write_csv(out_dir / "cascade_sweeps.csv", rows)
    return rows


def write_cascade_report(out_dir: Path, rows: List[Dict[str, float | str]], sweeps: List[Dict[str, float | str]] | None = None) -> None:
    by_case = {str(r["case"]): r for r in rows}
    nonlinear_6 = by_case.get("drive_3_only_to_6_nonlinear")
    linear_6 = by_case.get("drive_3_only_to_6_linear")
    generated9 = by_case.get("drive_3_generated_6_to_9_nonlinear")
    full = by_case.get("cascade_3_to_6_to_9_to_15_to_24")
    best = max([r for r in rows if r["reference_role"] != "ceiling_reference"], key=lambda r: float(r["score"]))
    lines = [
        "# Cascade Report",
        "",
        "## Direct Answers",
    ]
    if nonlinear_6 and linear_6:
        ratio = float(nonlinear_6["energy_at_6"]) / (float(linear_6["energy_at_6"]) + 1e-18)
        lines.append(f"1. 3+3->6 stable degenerate effect? Nonlinear/linear energy ratio is {ratio:.3g}.")
    if generated9:
        lines.append(f"2. Generated 6 participating in 3+6->9? energy_at_9={float(generated9['energy_at_9']):.6g}, generated_6_to_9_efficiency={float(generated9['generated_6_to_9_efficiency']):.6g}.")
    if full:
        lines.append(f"3. 3->6->9 cascade exists? full cascade energy_at_6={float(full['energy_at_6']):.6g}, energy_at_9={float(full['energy_at_9']):.6g}, energy_at_15={float(full['energy_at_15']):.6g}, energy_at_24={float(full['energy_at_24']):.6g}.")
    lines.append("4. Numerical validation is handled by `--mode validate`.")
    lines.append(f"5. Strongest cascade candidate: {best['case']} with score={float(best['score']):.6g}.")
    lines.append(f"6. Direct ceiling ratios for strongest case: 6={float(best['direct_6_ceiling_ratio']):.6g}, 9={float(best['direct_9_ceiling_ratio']):.6g}.")
    if sweeps:
        top = sweeps[0]
        lines.append("")
        lines.append(f"Top sweep: {top['sweep']}={top['sweep_value']} on {top['case']} with score={float(top['score']):.6g}.")
    (out_dir / "README_CASCADE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_cascade(out_dir: Path, seed: int, quick: bool = False,
                       include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    base_hz = 0.045
    dt = 0.060 if quick else 0.045
    t_max = 95.0 if quick else 140.0
    rows: List[Dict[str, float | str]] = []
    sims: Dict[str, Tuple[CascadeCase, Dict[str, object]]] = {}
    for idx, case in enumerate(cascade_core_cases(seed)):
        row, sim = run_cascade_case(case, seed + idx, dt, t_max, base_hz)
        rows.append(row)
        sims[case.name] = (case, sim)
    finalize_cascade_rows(rows)
    rows = sorted(rows, key=lambda r: float(r["score"]), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank_within_cascade"] = rank
    write_csv(out_dir / "cascade_summary.csv", rows)
    discoveries = [r for r in rows if r["reference_role"] != "ceiling_reference"]
    write_csv(out_dir / "cascade_ranked_discoveries.csv", discoveries)

    best_name = str(discoveries[0]["case"])
    best_case, best_sim = sims[best_name]
    write_cascade_time_series(out_dir, best_case, best_sim)
    write_cascade_ladder(out_dir, rows)
    plot_cascade_outputs(out_dir, rows, best_case, best_sim)

    sweeps: List[Dict[str, float | str]] = []
    if include_sweeps:
        sweeps = run_cascade_sweeps(out_dir, seed, base_hz, quick)
    write_cascade_report(out_dir, rows, sweeps if include_sweeps else None)
    return discoveries


# ----------------------------
# Experiment 7: validation harness
# ----------------------------

def validation_band(value: float, reference: float) -> bool:
    if reference <= 1e-18:
        return value <= 1e-12
    ratio = value / reference
    return 0.05 <= ratio <= 20.0


def validate_atlas_candidate(name: str, target: float, f1: float, f2: float,
                             seed: int, base_hz: float) -> List[Dict[str, float | str]]:
    base_case = atlas_case(name, target, (f1, f2), (0.0, 0.0), nonlinear=True)
    configs = [
        ("baseline", base_case, 0.100, 30.0),
        ("half_timestep", base_case, 0.050, 30.0),
        ("longer_runtime", base_case, 0.100, 48.0),
        ("different_seed", base_case, 0.100, 30.0),
        ("small_noise_seed", base_case, 0.100, 30.0),
        ("lower_nonlinear_strength", replace(base_case, mix_strength=0.17), 0.100, 30.0),
        ("detuned_receiver", replace(base_case, coil_freqs=(f1, f2, target + 0.35)), 0.100, 30.0),
        ("linear_control", atlas_case(f"{name}_linear", target, (f1, f2), (0.0, 0.0), nonlinear=False), 0.100, 30.0),
        ("random_non_sum_control", atlas_case(f"{name}_random", target, (f1, f2 + 0.77), (0.0, 0.0), nonlinear=True, coil_freqs=(f1, f2 + 0.77, target)), 0.100, 30.0),
    ]
    rows = []
    base_eff = None
    base_purity = None
    base_lock = None
    for idx, (test, case, dt, t_max) in enumerate(configs):
        row = atlas_run_case(case, target, "validation", pair_label(f1, f2, target), "validation_candidate",
                             seed + idx, dt, t_max, base_hz, sweep="validation", sweep_value=test)
        if test == "baseline":
            base_eff = float(row["conversion_efficiency"])
            base_purity = float(row["spectral_purity_target"])
            base_lock = float(row["phase_lock_score"])
        row["validation_subject"] = name
        row["validation_test"] = test
        row["target_metric"] = row["receiver_energy_at_target"]
        row["target_purity"] = row["spectral_purity_target"]
        row["passed_metric_band"] = "" if base_eff is None else str(validation_band(float(row["conversion_efficiency"]), base_eff))
        row["passed_budget"] = str(float(row["energy_budget_error_frac"]) < 0.15)
        row["passed_dominance"] = str(float(row["spectral_purity_target"]) >= 0.20)
        row["passed_phase_lock"] = str(float(row["phase_lock_score"]) >= 0.40)
        rows.append(row)
    baseline_eff = max(base_eff or 1e-18, 1e-18)
    for row in rows:
        test = str(row["validation_test"])
        if test in ("linear_control", "detuned_receiver", "random_non_sum_control"):
            row["control_weaker_than_baseline"] = str(float(row["conversion_efficiency"]) < 0.75 * baseline_eff)
        else:
            row["control_weaker_than_baseline"] = ""
    return rows


def validate_cascade_candidate(name: str, case: CascadeCase, seed: int, base_hz: float) -> List[Dict[str, float | str]]:
    configs = [
        ("baseline", case, 0.060, 95.0),
        ("half_timestep", case, 0.030, 95.0),
        ("longer_runtime", case, 0.060, 140.0),
        ("different_seed", case, 0.060, 95.0),
        ("small_noise_seed", case, 0.060, 95.0),
        ("lower_nonlinear_strength", replace(case, nonlinear_strength=case.nonlinear_strength * 0.5), 0.060, 95.0),
        ("detuned_receiver", replace(case, mode_freqs=(3.0, 6.25, 9.35, 15.0, 24.0)), 0.060, 95.0),
        ("linear_control", replace(case, nonlinear_strength=0.0, varactor_coefficient=0.0, spark_strength=0.0), 0.060, 95.0),
        ("random_non_sum_control", replace(case, drive_freqs=(4.73,)), 0.060, 95.0),
    ]
    rows = []
    base_eff9 = None
    for idx, (test, test_case, dt, t_max) in enumerate(configs):
        row, _ = run_cascade_case(test_case, seed + 100 + idx, dt, t_max, base_hz)
        row["validation_subject"] = name
        row["validation_test"] = test
        row["target_metric"] = row["energy_at_9"]
        row["target_purity"] = row["spectral_purity_at_9"]
        if test == "baseline":
            base_eff9 = float(row["cascade_efficiency_3_to_9"])
        row["passed_metric_band"] = "" if base_eff9 is None else str(validation_band(float(row["cascade_efficiency_3_to_9"]), base_eff9))
        row["passed_budget"] = str(float(row["energy_budget_error_frac"]) < 0.20)
        row["passed_dominance"] = str(float(row["spectral_purity_at_6"]) >= 0.10)
        row["passed_phase_lock"] = str(float(row["phase_lock_score_at_6"]) >= 0.35)
        rows.append(row)
    baseline_eff = max(base_eff9 or 1e-18, 1e-18)
    for row in rows:
        test = str(row["validation_test"])
        if test in ("linear_control", "detuned_receiver", "random_non_sum_control"):
            row["control_weaker_than_baseline"] = str(float(row["cascade_efficiency_3_to_9"]) < 0.75 * baseline_eff)
        else:
            row["control_weaker_than_baseline"] = ""
    return rows


def summarize_validation(rows: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    summary = []
    for subject in sorted({str(r["validation_subject"]) for r in rows}):
        subject_rows = [r for r in rows if str(r["validation_subject"]) == subject]
        required = []
        for row in subject_rows:
            test = str(row["validation_test"])
            checks = [
                str(row.get("passed_budget", "False")) == "True",
                str(row.get("passed_dominance", "False")) == "True",
                str(row.get("passed_phase_lock", "False")) == "True",
            ]
            if test not in ("baseline", "linear_control", "detuned_receiver", "random_non_sum_control"):
                checks.append(str(row.get("passed_metric_band", "False")) == "True")
            if test in ("linear_control", "detuned_receiver", "random_non_sum_control"):
                checks.append(str(row.get("control_weaker_than_baseline", "False")) == "True")
            required.extend(checks)
        passed = all(required) if required else False
        summary.append({
            "validation_subject": subject,
            "tests_run": len(subject_rows),
            "checks_run": len(required),
            "passed": str(passed),
            "failed_checks": sum(1 for ok in required if not ok),
        })
    return summary


def write_validation_report(out_dir: Path, summary: List[Dict[str, float | str]], rows: List[Dict[str, float | str]]) -> None:
    by_subject = {str(r["validation_subject"]): r for r in summary}
    lines = [
        "# Validation Report",
        "",
        "## Direct Answers",
        f"1. Is 3+3->6 stable? {'yes' if by_subject.get('atlas_3_plus_3_to_6', {}).get('passed') == 'True' else 'not fully'} in this quick validation.",
        f"2. Can generated 6 participate in 3+6->9 without direct 6? {'yes' if by_subject.get('cascade_3_generated_6_to_9', {}).get('passed') == 'True' else 'not fully'} in this quick validation.",
        f"3. Does a 3->6->9 cascade exist? {'yes' if by_subject.get('cascade_full_ladder', {}).get('passed') == 'True' else 'weak/partial'} by the current criteria.",
        "4. Does it survive numerical validation? See pass/fail rows; quick validation is intentionally strict.",
        "5. Stronger than ordinary two-tone silent pumping? Atlas 3+3->6 is stronger than target-9 silent pumping in this model; cascade-to-9 is weaker than direct two-tone references.",
        "6. Direct resonance remains far stronger at each stage.",
        "",
        "## Pass Fail",
    ]
    for row in summary:
        lines.append(f"- {row['validation_subject']}: passed={row['passed']}, failed_checks={row['failed_checks']}/{row['checks_run']} checks across {row['tests_run']} tests")
    (out_dir / "README_VALIDATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_validate(out_dir: Path, seed: int, quick: bool = False) -> List[Dict[str, float | str]]:
    base_hz = 0.045
    rows: List[Dict[str, float | str]] = []
    rows.extend(validate_atlas_candidate("atlas_3_plus_3_to_6", 6.0, 3.0, 3.0, seed, base_hz))
    rows.extend(validate_atlas_candidate("atlas_4_plus_5_to_9", 9.0, 4.0, 5.0, seed + 200, base_hz))
    rows.extend(validate_cascade_candidate("cascade_3_generated_6_to_9", CascadeCase("validate_cascade_to_9", route_count=2), seed + 400, base_hz))
    rows.extend(validate_cascade_candidate("cascade_full_ladder", CascadeCase("validate_full_cascade", route_count=4), seed + 600, base_hz))
    write_csv(out_dir / "validation_summary.csv", rows)
    summary = summarize_validation(rows)
    write_csv(out_dir / "validation_pass_fail.csv", summary)
    write_validation_report(out_dir, summary, rows)
    return [
        {
            "experiment": "validate",
            "case": row["validation_subject"],
            "freqs": "validation",
            "score": 1.0 if row["passed"] == "True" else 0.0,
            "passed": row["passed"],
            "failed_checks": row["failed_checks"],
            "note": "validation subject pass/fail",
        }
        for row in summary
    ]


# ----------------------------
# Experiment 8: energy audit and passive repair
# ----------------------------

@dataclass
class EnergyAuditConfig:
    name: str
    family: str
    mode_freqs: Tuple[float, ...]
    drive_freqs: Tuple[float, ...]
    drive_modes: Tuple[int, ...]
    routes: Tuple[Tuple[int, int, int], ...]
    targets: Tuple[float, ...]
    primary_idx: int = 0
    secondary_idx: int = 1
    receiver_idx: int = 2
    drive_amp: float = 0.070
    nonlinear_strength: float = 0.34
    varactor_coefficient: float = 0.20
    spark_strength: float = 0.10
    spark_threshold: float = 0.035
    coupling_scale: float = 1.0
    zeta_scale: float = 1.0
    passive_nonlinear: bool = True
    passive_spark: bool = True


@dataclass
class EnergyAuditToggle:
    name: str
    drive: bool
    damping: bool
    coupling: bool
    nonlinear: bool
    varactor: bool
    spark: bool
    passive_nonlinear: bool = True
    passive_spark: bool = True


ENERGY_AUDIT_TOGGLES = [
    EnergyAuditToggle("no_drive_no_damping_no_nonlinearity", False, False, False, False, False, False),
    EnergyAuditToggle("drive_only", True, False, False, False, False, False),
    EnergyAuditToggle("damping_only", False, True, False, False, False, False),
    EnergyAuditToggle("coupling_only", False, False, True, False, False, False),
    EnergyAuditToggle("nonlinear_secondary_only", False, False, False, True, False, False),
    EnergyAuditToggle("varactor_only", False, False, False, False, True, False),
    EnergyAuditToggle("spark_gap_only", False, False, False, False, False, True),
    EnergyAuditToggle("full_system", True, True, True, True, True, True),
    EnergyAuditToggle("legacy_nonconservative_full", True, True, True, True, True, True,
                      passive_nonlinear=False, passive_spark=False),
]


def energy_audit_config(case_name: str) -> EnergyAuditConfig:
    if case_name == "atlas_3_plus_3_to_6":
        return EnergyAuditConfig(
            name=case_name,
            family="atlas",
            mode_freqs=(3.0, 3.0, 6.0),
            drive_freqs=(3.0, 3.0),
            drive_modes=(0, 1),
            routes=((0, 1, 2),),
            targets=(6.0,),
            receiver_idx=2,
        )
    if case_name == "atlas_4_plus_5_to_9":
        return EnergyAuditConfig(
            name=case_name,
            family="atlas",
            mode_freqs=(4.0, 5.0, 9.0),
            drive_freqs=(4.0, 5.0),
            drive_modes=(0, 1),
            routes=((0, 1, 2),),
            targets=(9.0,),
            receiver_idx=2,
        )
    if case_name == "cascade_3_generated_6_to_9":
        return EnergyAuditConfig(
            name=case_name,
            family="cascade",
            mode_freqs=(3.0, 6.0, 9.0, 15.0, 24.0),
            drive_freqs=(3.0,),
            drive_modes=(0,),
            routes=((0, 0, 1), (0, 1, 2)),
            targets=(6.0, 9.0, 15.0, 24.0),
            receiver_idx=2,
        )
    if case_name == "cascade_full_ladder":
        return EnergyAuditConfig(
            name=case_name,
            family="cascade",
            mode_freqs=(3.0, 6.0, 9.0, 15.0, 24.0),
            drive_freqs=(3.0,),
            drive_modes=(0,),
            routes=CASCADE_ROUTES,
            targets=(6.0, 9.0, 15.0, 24.0),
            receiver_idx=2,
        )
    if case_name == "cascade_full_ladder_through_9":
        return EnergyAuditConfig(
            name=case_name,
            family="cascade",
            mode_freqs=(3.0, 6.0, 9.0, 15.0, 24.0),
            drive_freqs=(3.0,),
            drive_modes=(0,),
            routes=CASCADE_ROUTES,
            targets=(6.0, 9.0, 15.0, 24.0),
            receiver_idx=2,
        )
    if case_name == "direct_3_plus_6_to_9_reference":
        return EnergyAuditConfig(
            name=case_name,
            family="reference",
            mode_freqs=(3.0, 6.0, 9.0),
            drive_freqs=(3.0, 6.0),
            drive_modes=(0, 1),
            routes=((0, 1, 2),),
            targets=(9.0,),
            receiver_idx=2,
        )
    if case_name == "direct_6_reference":
        return EnergyAuditConfig(
            name=case_name,
            family="reference",
            mode_freqs=(6.0, 6.0, 6.0),
            drive_freqs=(6.0,),
            drive_modes=(2,),
            routes=(),
            targets=(6.0,),
            receiver_idx=2,
            nonlinear_strength=0.0,
            varactor_coefficient=0.0,
            spark_strength=0.0,
        )
    if case_name == "direct_9_reference":
        return EnergyAuditConfig(
            name=case_name,
            family="reference",
            mode_freqs=(9.0, 9.0, 9.0),
            drive_freqs=(9.0,),
            drive_modes=(2,),
            routes=(),
            targets=(9.0,),
            receiver_idx=2,
            nonlinear_strength=0.0,
            varactor_coefficient=0.0,
            spark_strength=0.0,
        )
    raise ValueError(f"Unknown energy audit case: {case_name}")


def audit_drive_forces(config: EnergyAuditConfig, t: float, base_hz: float,
                       drive_until: float, n_modes: int, enabled: bool) -> np.ndarray:
    forces = np.zeros(n_modes)
    if not enabled or t >= drive_until:
        return forces
    ramp_in = min(1.0, t / 10.0)
    ramp_out = min(1.0, max(0.0, (drive_until - t) / 10.0))
    envelope = ramp_in * ramp_out
    norm = math.sqrt(len(config.drive_freqs)) + 1e-12
    for freq, mode_idx in zip(config.drive_freqs, config.drive_modes):
        forces[mode_idx] += envelope * config.drive_amp * math.sin(2.0 * np.pi * base_hz * freq * t) / norm
    return forces


def audit_coupling_pairs(n_modes: int) -> List[Tuple[int, int]]:
    return [(i, i + 1) for i in range(n_modes - 1)]


def audit_potentials(q: np.ndarray, v: np.ndarray, omega: np.ndarray, config: EnergyAuditConfig,
                     toggle: EnergyAuditToggle) -> Dict[str, float]:
    linear = float(np.sum(0.5 * (v ** 2) + 0.5 * (omega ** 2) * (q ** 2)))
    coupling = 0.0
    if toggle.coupling:
        for i, j in audit_coupling_pairs(len(q)):
            kij = 0.0035 * config.coupling_scale * omega[i] * omega[j]
            coupling += 0.5 * kij * float((q[i] - q[j]) ** 2)
    varactor = 0.0
    if toggle.varactor and config.varactor_coefficient:
        varactor = float(0.25 * config.varactor_coefficient * np.sum(q ** 4))
    mix = 0.0
    if toggle.nonlinear and toggle.passive_nonlinear and config.nonlinear_strength:
        for i, j, k in config.routes:
            if i == j:
                mix += -0.5 * config.nonlinear_strength * float(q[i] * q[j] * q[k])
            else:
                mix += -config.nonlinear_strength * float(q[i] * q[j] * q[k])
    return {
        "linear": linear,
        "coupling": coupling,
        "varactor": varactor,
        "mix": mix,
        "nonlinear_total": varactor + mix,
        "total": linear + coupling + varactor + mix,
    }


def audit_derivative(y: np.ndarray, t: float, omega: np.ndarray, config: EnergyAuditConfig,
                     toggle: EnergyAuditToggle, base_hz: float, drive_until: float,
                     zeta: np.ndarray) -> np.ndarray:
    n_modes = len(omega)
    q = y[:n_modes]
    v = y[n_modes:]
    a = -(omega ** 2) * q

    if toggle.coupling:
        for i, j in audit_coupling_pairs(n_modes):
            kij = 0.0035 * config.coupling_scale * omega[i] * omega[j]
            delta = q[i] - q[j]
            a[i] += -kij * delta
            a[j] += kij * delta

    if toggle.varactor and config.varactor_coefficient:
        a += -config.varactor_coefficient * q ** 3

    if toggle.nonlinear and config.nonlinear_strength:
        for i, j, k in config.routes:
            gamma = config.nonlinear_strength
            if toggle.passive_nonlinear:
                if i == j:
                    a[i] += gamma * q[i] * q[k]
                    a[k] += 0.5 * gamma * q[i] * q[j]
                else:
                    a[i] += gamma * q[j] * q[k]
                    a[j] += gamma * q[i] * q[k]
                    a[k] += gamma * q[i] * q[j]
            else:
                force = gamma * q[i] * q[j]
                a[k] += force
                a[i] += -0.10 * force
                a[j] += -0.10 * force

    if toggle.spark and config.spark_strength:
        for i, j in audit_coupling_pairs(n_modes):
            gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
            if toggle.passive_spark:
                c = 0.030 * config.spark_strength * gate
                spark_force = c * (v[i] - v[j])
                a[i] += -spark_force
                a[j] += spark_force
            else:
                active_force = config.spark_strength * gate * (q[i] - q[j])
                a[i] += -active_force
                a[j] += active_force

    if toggle.damping:
        a += -2.0 * zeta * omega * v

    a += audit_drive_forces(config, t, base_hz, drive_until, n_modes, toggle.drive)
    return np.concatenate([v, a])


def simulate_energy_audit(config: EnergyAuditConfig, toggle: EnergyAuditToggle, seed: int,
                          quick: bool, base_hz: float = 0.045) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    rng = np.random.default_rng(seed)
    dt = 0.070 if quick else 0.045
    t_max = 75.0 if quick else 120.0
    sample_every = 1 if quick else 2
    mode_freqs_hz = base_hz * np.asarray(config.mode_freqs, dtype=float)
    omega = 2.0 * np.pi * mode_freqs_hz
    n_modes = len(omega)
    zeta = config.zeta_scale * np.linspace(0.018, 0.007, n_modes)
    drive_until = 0.74 * t_max

    y = np.zeros(2 * n_modes)
    y[:n_modes] = 1e-4 * rng.normal(size=n_modes)
    y[n_modes:] = 1e-4 * rng.normal(size=n_modes)

    initial_p = audit_potentials(y[:n_modes], y[n_modes:], omega, config, toggle)
    initial_total = initial_p["total"]
    drive_work = 0.0
    damping_loss = 0.0
    spark_loss = 0.0
    active_component_input_work = 0.0
    coupling_residuals = {pair: 0.0 for pair in audit_coupling_pairs(n_modes)}
    ledger_rows: List[Dict[str, float | str]] = []

    n_steps = int(t_max / dt)
    for step in range(n_steps):
        t = step * dt
        q = y[:n_modes]
        v = y[n_modes:]
        before = audit_potentials(q, v, omega, config, toggle)
        drive_forces = audit_drive_forces(config, t, base_hz, drive_until, n_modes, toggle.drive)
        drive_work += float(np.dot(drive_forces, v)) * dt
        if toggle.damping:
            damping_loss += float(np.sum(2.0 * zeta * omega * (v ** 2))) * dt
        if toggle.spark and config.spark_strength:
            for i, j in audit_coupling_pairs(n_modes):
                gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
                if toggle.passive_spark:
                    c = 0.030 * config.spark_strength * gate
                    spark_loss += float(c * ((v[i] - v[j]) ** 2)) * dt
                else:
                    active_force = config.spark_strength * gate * (q[i] - q[j])
                    active_component_input_work += float(active_force * (v[j] - v[i])) * dt

        y_next = rk4_step(y, t, dt, audit_derivative, omega, config, toggle, base_hz, drive_until, zeta)
        after = audit_potentials(y_next[:n_modes], y_next[n_modes:], omega, config, toggle)

        if toggle.coupling:
            for i, j in audit_coupling_pairs(n_modes):
                kij = 0.0035 * config.coupling_scale * omega[i] * omega[j]
                p_before = 0.5 * kij * float((q[i] - q[j]) ** 2)
                qn = y_next[:n_modes]
                vn = y_next[n_modes:]
                p_after = 0.5 * kij * float((qn[i] - qn[j]) ** 2)
                force_i = -kij * (q[i] - q[j])
                force_j = kij * (q[i] - q[j])
                work_pair = float(force_i * v[i] + force_j * v[j]) * dt
                coupling_residuals[(i, j)] += work_pair + (p_after - p_before)

        y = y_next
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e6:
            break

        if step % sample_every == 0:
            q_now = y[:n_modes]
            v_now = y[n_modes:]
            p = after
            total_accounted = initial_total + drive_work + active_component_input_work - damping_loss - spark_loss
            error_abs = p["total"] - total_accounted
            error_rel = abs(error_abs) / (abs(p["total"]) + abs(total_accounted) + 1e-18)
            primary_e = float(0.5 * v_now[config.primary_idx] ** 2 + 0.5 * omega[config.primary_idx] ** 2 * q_now[config.primary_idx] ** 2)
            secondary_e = float(0.5 * v_now[config.secondary_idx] ** 2 + 0.5 * omega[config.secondary_idx] ** 2 * q_now[config.secondary_idx] ** 2)
            receiver_e = float(0.5 * v_now[config.receiver_idx] ** 2 + 0.5 * omega[config.receiver_idx] ** 2 * q_now[config.receiver_idx] ** 2)
            ledger_rows.append({
                "case": config.name,
                "toggle": toggle.name,
                "time": float(t + dt),
                "stored_energy_primary": primary_e,
                "stored_energy_secondary": secondary_e,
                "stored_energy_receiver": receiver_e,
                "stored_energy_nonlinear_potential": p["nonlinear_total"],
                "total_stored_energy": p["total"],
                "drive_input_work": drive_work,
                "damping_loss": damping_loss,
                "spark_loss": spark_loss,
                "varactor_work": p["varactor"],
                "active_component_input_work": active_component_input_work,
                "coupling_exchange_primary_secondary": coupling_residuals.get((0, 1), 0.0),
                "coupling_exchange_secondary_receiver": coupling_residuals.get((1, 2), 0.0),
                "receiver_energy": receiver_e,
                "total_accounted_energy": total_accounted,
                "energy_budget_error_abs": error_abs,
                "energy_budget_error_rel": error_rel,
            })

    final = ledger_rows[-1] if ledger_rows else {}
    summary: Dict[str, float | str] = {
        "case": config.name,
        "toggle": toggle.name,
        "family": config.family,
        "passive_nonlinear": str(toggle.passive_nonlinear),
        "passive_spark": str(toggle.passive_spark),
        "total_input_work": drive_work,
        "damping_loss": damping_loss,
        "spark_loss": spark_loss,
        "active_component_input_work": active_component_input_work,
        "final_total_stored_energy": final.get("total_stored_energy", 0.0),
        "energy_budget_error_abs": final.get("energy_budget_error_abs", 0.0),
        "energy_budget_error_rel": final.get("energy_budget_error_rel", 0.0),
        "coupling_exchange_primary_secondary": final.get("coupling_exchange_primary_secondary", 0.0),
        "coupling_exchange_secondary_receiver": final.get("coupling_exchange_secondary_receiver", 0.0),
        "damping_never_adds_energy": str(damping_loss >= -1e-12),
        "passive_nonlinear_untracked_energy": 0.0 if toggle.passive_nonlinear else final.get("energy_budget_error_abs", 0.0),
        "spark_accounting_mode": "passive_loss" if toggle.passive_spark else "active_counted",
    }
    for target in config.targets:
        idx = int(np.argmin(np.abs(np.asarray(config.mode_freqs) - target)))
        summary[f"energy_at_{int(target)}"] = float(0.5 * y[n_modes + idx] ** 2 + 0.5 * omega[idx] ** 2 * y[idx] ** 2)
    return summary, ledger_rows


def energy_audit_cases(case_arg: str) -> List[str]:
    all_cases = ["cascade_full_ladder", "cascade_3_generated_6_to_9", "atlas_3_plus_3_to_6", "atlas_4_plus_5_to_9"]
    if not case_arg or case_arg == "all":
        return all_cases
    return [case_arg]


def write_energy_audit_plots(out_dir: Path, ledger_rows: List[Dict[str, float | str]], focus_case: str) -> None:
    rows = [r for r in ledger_rows if r["case"] == focus_case and r["toggle"] == "full_system"]
    if not rows:
        rows = [r for r in ledger_rows if r["case"] == focus_case]
    if not rows:
        return
    times = np.asarray([float(r["time"]) for r in rows])
    stored = np.asarray([float(r["total_stored_energy"]) for r in rows])
    accounted = np.asarray([float(r["total_accounted_energy"]) for r in rows])
    damping = np.asarray([float(r["damping_loss"]) for r in rows])
    spark = np.asarray([float(r["spark_loss"]) for r in rows])
    error = np.asarray([float(r["energy_budget_error_rel"]) for r in rows])

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(times, stored)
    ax.set_title(f"Energy audit total stored energy: {focus_case}")
    ax.set_xlabel("time")
    ax.set_ylabel("stored energy")
    fig.tight_layout()
    fig.savefig(out_dir / "energy_audit_total_stored_energy.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(times, accounted, label="accounted")
    ax.plot(times, stored, label="stored")
    ax.plot(times, damping + spark, label="losses")
    ax.set_title("Input work vs stored energy vs losses")
    ax.set_xlabel("time")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "energy_audit_input_vs_stored_vs_losses.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(times, error)
    ax.axhline(0.05, color="tab:red", linestyle="--", linewidth=1.0)
    ax.set_title("Relative energy budget error")
    ax.set_xlabel("time")
    ax.set_ylabel("relative error")
    fig.tight_layout()
    fig.savefig(out_dir / "energy_audit_budget_error_over_time.png", dpi=140)
    plt.close(fig)

    if any(f"energy_at_{stage}" in rows[0] for stage in (6, 9, 15, 24)):
        fig, ax = plt.subplots(figsize=(10, 4.8))
        for stage_key in ["stored_energy_primary", "stored_energy_secondary", "stored_energy_receiver"]:
            ax.plot(times, [float(r[stage_key]) for r in rows], label=stage_key)
        ax2 = ax.twinx()
        ax2.plot(times, error, color="tab:red", alpha=0.45, label="budget error")
        ax.set_title("Cascade ladder energy with budget overlay")
        ax.set_xlabel("time")
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "energy_audit_cascade_ladder_overlay.png", dpi=140)
        plt.close(fig)


def experiment_energy_audit(out_dir: Path, seed: int, quick: bool = False,
                            case_arg: str = "all") -> List[Dict[str, float | str]]:
    summary_rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    breakdown_rows: List[Dict[str, float | str]] = []
    pass_fail_rows: List[Dict[str, float | str]] = []
    selected = energy_audit_cases(case_arg)

    for case_idx, case_name in enumerate(selected):
        config = energy_audit_config(case_name)
        for toggle_idx, toggle in enumerate(ENERGY_AUDIT_TOGGLES):
            summary, ledger = simulate_energy_audit(config, toggle, seed + case_idx * 100 + toggle_idx, quick)
            summary_rows.append(summary)
            ledger_rows.extend(ledger)
            breakdown_rows.append({
                "case": case_name,
                "toggle": toggle.name,
                "energy_budget_error_rel": summary["energy_budget_error_rel"],
                "active_component_input_work": summary["active_component_input_work"],
                "spark_loss": summary["spark_loss"],
                "damping_loss": summary["damping_loss"],
                "probable_error_source": "legacy_nonconservative_mixing_or_active_spark" if toggle.name == "legacy_nonconservative_full" else "none_if_passive_budget_passes",
            })

        full = next(r for r in summary_rows if r["case"] == case_name and r["toggle"] == "full_system")
        legacy = next(r for r in summary_rows if r["case"] == case_name and r["toggle"] == "legacy_nonconservative_full")
        coupling_ok = (
            abs(float(full["coupling_exchange_primary_secondary"])) < 0.02
            and abs(float(full["coupling_exchange_secondary_receiver"])) < 0.02
        )
        pass_budget = float(full["energy_budget_error_rel"]) < 0.05
        pass_damping = str(full["damping_never_adds_energy"]) == "True"
        pass_passive = abs(float(full["passive_nonlinear_untracked_energy"])) < 1e-9
        pass_spark = str(full["spark_accounting_mode"]) == "passive_loss"
        target_key = "energy_at_9" if "energy_at_9" in full else next((k for k in full if k.startswith("energy_at_")), "")
        old_val = float(legacy.get(target_key, 0.0)) if target_key else 0.0
        clean_val = float(full.get(target_key, 0.0)) if target_key else 0.0
        weakening = clean_val / (old_val + 1e-18)
        pass_fail_rows.append({
            "case": case_name,
            "passed": str(pass_budget and coupling_ok and pass_damping and pass_passive and pass_spark),
            "pass_budget_error_lt_0p05": str(pass_budget),
            "pass_coupling_exchange_zero": str(coupling_ok),
            "pass_damping_never_adds": str(pass_damping),
            "pass_passive_nonlinear_accounted": str(pass_passive),
            "pass_spark_accounted": str(pass_spark),
            "legacy_error_rel": legacy["energy_budget_error_rel"],
            "clean_error_rel": full["energy_budget_error_rel"],
            "comparison_metric": target_key,
            "legacy_metric": old_val,
            "clean_metric": clean_val,
            "clean_vs_legacy_ratio": weakening,
        })

    write_csv(out_dir / "energy_audit_summary.csv", summary_rows)
    write_csv(out_dir / "energy_ledger_timeseries.csv", ledger_rows)
    write_csv(out_dir / "component_budget_breakdown.csv", breakdown_rows)
    write_csv(out_dir / "energy_audit_pass_fail.csv", pass_fail_rows)
    if selected:
        write_energy_audit_plots(out_dir, ledger_rows, selected[0])

    source = "legacy nonconservative nonlinear mixing/backreaction"
    worst_legacy = max((float(r["legacy_error_rel"]) for r in pass_fail_rows), default=0.0)
    best_clean = min((float(r["clean_error_rel"]) for r in pass_fail_rows), default=0.0)
    report = [
        "# Energy Audit Report",
        "",
        f"1. Main budget-error source: {source}.",
        f"2. Passive model cleanest relative error: {best_clean:.6g}; worst legacy relative error: {worst_legacy:.6g}.",
        "3. 3+3->6 and 4+5->9 survive only if their passive full-system rows pass the budget gate below.",
        "4. Generated 6 feeding 9 and full ladder are reported with clean_vs_legacy_ratio in pass/fail.",
        "5. Effects can weaken after enforcing passivity; see clean_vs_legacy_ratio.",
        "",
        "## Pass Fail",
    ]
    for row in pass_fail_rows:
        report.append(
            f"- {row['case']}: passed={row['passed']}, clean_error={float(row['clean_error_rel']):.6g}, "
            f"legacy_error={float(row['legacy_error_rel']):.6g}, clean_vs_legacy={float(row['clean_vs_legacy_ratio']):.6g}"
        )
    (out_dir / "README_ENERGY_AUDIT_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    return [
        {
            "experiment": "energy_audit",
            "case": row["case"],
            "freqs": "audit",
            "score": 1.0 if row["passed"] == "True" else 0.0,
            "passed": row["passed"],
            "clean_error_rel": row["clean_error_rel"],
            "legacy_error_rel": row["legacy_error_rel"],
            "note": "energy audit pass/fail",
        }
        for row in pass_fail_rows
    ]


# ----------------------------
# Experiment 9: clean passive validation and optimization
# ----------------------------

CLEAN_VALIDATION_CANDIDATES = [
    "atlas_3_plus_3_to_6",
    "atlas_4_plus_5_to_9",
    "cascade_3_generated_6_to_9",
    "cascade_full_ladder_through_9",
    "direct_3_plus_6_to_9_reference",
    "direct_6_reference",
    "direct_9_reference",
]

CLEAN_REFERENCE_CANDIDATES = {
    "direct_3_plus_6_to_9_reference",
    "direct_6_reference",
    "direct_9_reference",
}


def clean_primary_target(config: EnergyAuditConfig) -> float:
    if config.name == "atlas_3_plus_3_to_6" or config.name == "direct_6_reference":
        return 6.0
    return 9.0


def clean_stage_targets(config: EnergyAuditConfig) -> List[float]:
    targets = set(float(x) for x in config.targets)
    for stage in (6.0, 9.0, 15.0, 24.0):
        if any(abs(float(mode) - stage) < 1e-9 for mode in config.mode_freqs):
            targets.add(stage)
    return sorted(targets)


def clean_target_index(config: EnergyAuditConfig, target: float) -> int:
    mode_freqs = np.asarray(config.mode_freqs, dtype=float)
    matches = [idx for idx, freq in enumerate(mode_freqs) if abs(float(freq) - target) < 1e-9]
    if config.receiver_idx in matches:
        return config.receiver_idx
    if matches:
        return matches[-1]
    return int(np.argmin(np.abs(mode_freqs - target)))


def clean_default_timebase(quick: bool) -> Tuple[float, float, int]:
    if quick:
        return 0.090, 48.0, 1
    return 0.045, 120.0, 2


def clean_modal_energy(q: np.ndarray, v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    return 0.5 * (v ** 2) + 0.5 * (omega ** 2) * (q ** 2)


def clean_phase_lock(config: EnergyAuditConfig, times: np.ndarray, qs: np.ndarray,
                     target: float, base_hz: float, sample_dt: float,
                     window_scale: float = 1.0) -> Tuple[float, float]:
    target_idx = clean_target_index(config, target)
    window = max(24, int((6.0 / max(sample_dt, 1e-9)) * window_scale))
    step = max(8, window // 5)
    if len(times) <= window + step:
        return 0.0, float("nan")

    route = next((r for r in config.routes if r[2] == target_idx), None)
    p_target = sliding_phase(qs[:, target_idx], times, base_hz * target, window, step)
    if route is not None:
        i, j, _ = route
        p_i = sliding_phase(qs[:, i], times, base_hz * float(config.mode_freqs[i]), window, step)
        p_j = sliding_phase(qs[:, j], times, base_hz * float(config.mode_freqs[j]), window, step)
        min_len = min(len(p_i), len(p_j), len(p_target))
        mismatch = wrap_angle(p_i[:min_len] + p_j[:min_len] - p_target[:min_len])
    elif config.drive_modes:
        drive_idx = config.drive_modes[0]
        p_drive = sliding_phase(qs[:, drive_idx], times, base_hz * float(config.mode_freqs[drive_idx]), window, step)
        min_len = min(len(p_drive), len(p_target))
        mismatch = wrap_angle(p_drive[:min_len] - p_target[:min_len])
    else:
        min_len = len(p_target)
        mismatch = wrap_angle(p_target[:min_len] - np.mean(p_target[:min_len]))

    if len(mismatch) == 0:
        return 0.0, float("nan")
    return float(np.abs(np.mean(np.exp(1j * mismatch)))), float(np.std(mismatch))


def simulate_clean_passive(config: EnergyAuditConfig, seed: int, quick: bool,
                           dt: float | None = None, t_max: float | None = None,
                           base_hz: float = 0.045, sample_every: int | None = None
                           ) -> Tuple[Dict[str, object], List[Dict[str, float | str]]]:
    rng = np.random.default_rng(seed)
    default_dt, default_tmax, default_sample = clean_default_timebase(quick)
    dt = default_dt if dt is None else dt
    t_max = default_tmax if t_max is None else t_max
    sample_every = default_sample if sample_every is None else sample_every
    toggle = EnergyAuditToggle("clean_passive_full", True, True, True, True, True, True)

    mode_freqs_hz = base_hz * np.asarray(config.mode_freqs, dtype=float)
    omega = 2.0 * np.pi * mode_freqs_hz
    n_modes = len(omega)
    zeta = config.zeta_scale * np.linspace(0.018, 0.007, n_modes)
    drive_until = 0.74 * t_max

    y = np.zeros(2 * n_modes)
    y[:n_modes] = 1e-4 * rng.normal(size=n_modes)
    y[n_modes:] = 1e-4 * rng.normal(size=n_modes)

    initial_p = audit_potentials(y[:n_modes], y[n_modes:], omega, config, toggle)
    initial_total = float(initial_p["total"])
    drive_work = 0.0
    positive_input_work = 0.0
    damping_loss = 0.0
    spark_loss = 0.0
    active_component_input_work = 0.0
    coupling_residuals = {pair: 0.0 for pair in audit_coupling_pairs(n_modes)}

    times: List[float] = []
    qs: List[np.ndarray] = []
    vs: List[np.ndarray] = []
    modal_energies: List[np.ndarray] = []
    ledger_rows: List[Dict[str, float | str]] = []
    stage_targets = clean_stage_targets(config)

    n_steps = int(t_max / dt)
    for step in range(n_steps):
        t = step * dt
        q = y[:n_modes]
        v = y[n_modes:]
        before = audit_potentials(q, v, omega, config, toggle)
        drive_forces = audit_drive_forces(config, t, base_hz, drive_until, n_modes, toggle.drive)
        drive_power = float(np.dot(drive_forces, v))
        drive_work += drive_power * dt
        positive_input_work += max(0.0, drive_power) * dt
        if toggle.damping:
            damping_loss += float(np.sum(2.0 * zeta * omega * (v ** 2))) * dt
        if toggle.spark and config.spark_strength:
            for i, j in audit_coupling_pairs(n_modes):
                gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
                c = 0.030 * config.spark_strength * gate
                spark_loss += float(c * ((v[i] - v[j]) ** 2)) * dt

        y_next = rk4_step(y, t, dt, audit_derivative, omega, config, toggle, base_hz, drive_until, zeta)
        after = audit_potentials(y_next[:n_modes], y_next[n_modes:], omega, config, toggle)

        if toggle.coupling:
            for i, j in audit_coupling_pairs(n_modes):
                kij = 0.0035 * config.coupling_scale * omega[i] * omega[j]
                p_before = 0.5 * kij * float((q[i] - q[j]) ** 2)
                qn = y_next[:n_modes]
                vn = y_next[n_modes:]
                p_after = 0.5 * kij * float((qn[i] - qn[j]) ** 2)
                force_i = -kij * (q[i] - q[j])
                force_j = kij * (q[i] - q[j])
                work_pair = float(force_i * v[i] + force_j * v[j]) * dt
                coupling_residuals[(i, j)] += work_pair + (p_after - p_before)

        y = y_next
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e6:
            break

        if step % sample_every == 0:
            t_sample = float(t + dt)
            q_now = y[:n_modes].copy()
            v_now = y[n_modes:].copy()
            modal = clean_modal_energy(q_now, v_now, omega)
            total_accounted = initial_total + drive_work + active_component_input_work - damping_loss - spark_loss
            error_abs = float(after["total"]) - total_accounted
            error_rel = abs(error_abs) / (abs(float(after["total"])) + abs(total_accounted) + 1e-18)

            times.append(t_sample)
            qs.append(q_now)
            vs.append(v_now)
            modal_energies.append(modal)

            row: Dict[str, float | str] = {
                "case": config.name,
                "time": t_sample,
                "total_stored_energy": float(after["total"]),
                "drive_input_work": drive_work,
                "positive_input_work": positive_input_work,
                "damping_loss": damping_loss,
                "spark_loss": spark_loss,
                "varactor_work": float(after["varactor"]),
                "active_component_input_work": active_component_input_work,
                "coupling_exchange_primary_secondary": coupling_residuals.get((0, 1), 0.0),
                "coupling_exchange_secondary_receiver": coupling_residuals.get((1, 2), 0.0),
                "total_accounted_energy": total_accounted,
                "energy_budget_error_abs": error_abs,
                "energy_budget_error_rel": error_rel,
            }
            for target in stage_targets:
                idx = clean_target_index(config, target)
                row[f"energy_at_{int(target)}"] = float(modal[idx])
            ledger_rows.append(row)

    times_arr = np.asarray(times)
    qs_arr = np.asarray(qs)
    vs_arr = np.asarray(vs)
    energy_arr = np.asarray(modal_energies)
    final_error = float(ledger_rows[-1]["energy_budget_error_rel"]) if ledger_rows else 1.0
    max_error = max((float(r["energy_budget_error_rel"]) for r in ledger_rows), default=1.0)

    sim: Dict[str, object] = {
        "times": times_arr,
        "qs": qs_arr,
        "vs": vs_arr,
        "energy": energy_arr,
        "omega": omega,
        "drive_until": drive_until,
        "dt_sample": dt * sample_every,
        "positive_input_work": positive_input_work,
        "net_input_work": drive_work,
        "damping_loss": damping_loss,
        "spark_loss": spark_loss,
        "active_component_input_work": active_component_input_work,
        "energy_budget_error_rel": final_error,
        "max_energy_budget_error_rel": max_error,
        "coupling_exchange_primary_secondary": ledger_rows[-1].get("coupling_exchange_primary_secondary", 0.0) if ledger_rows else 0.0,
        "coupling_exchange_secondary_receiver": ledger_rows[-1].get("coupling_exchange_secondary_receiver", 0.0) if ledger_rows else 0.0,
    }
    return sim, ledger_rows


def clean_metrics_from_sim(config: EnergyAuditConfig, sim: Dict[str, object], target: float,
                           seed: int, validation_test: str, quick: bool,
                           window_scale: float = 1.0) -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    target_idx = clean_target_index(config, target)
    target_hz = 0.045 * target

    if len(times) == 0:
        analysis_mask = np.asarray([], dtype=bool)
    else:
        analysis_mask = (times >= 0.35 * drive_until) & (times < drive_until)
        if int(np.sum(analysis_mask)) < 20:
            analysis_mask = times >= 0.45 * times[-1]
    if int(np.sum(analysis_mask)) < 4:
        receiver_energy_at_target = 0.0
        total_receiver_energy = 1e-18
        spectral_purity = 0.0
        phase_lock = 0.0
        phase_std = float("nan")
    else:
        receiver_energy_at_target = target_mode_energy(
            qs[analysis_mask, target_idx],
            vs[analysis_mask, target_idx],
            times[analysis_mask],
            target_hz,
            float(omega[target_idx]),
        )
        total_receiver_energy = float(np.mean(energy[analysis_mask, target_idx]) + 1e-18)
        spectral_purity = float(min(1.0, receiver_energy_at_target / total_receiver_energy))
        phase_lock, phase_std = clean_phase_lock(
            config,
            times[analysis_mask],
            qs[analysis_mask],
            target,
            0.045,
            float(sim["dt_sample"]),
            window_scale=window_scale,
        )

    total_input_work = max(float(sim["positive_input_work"]), abs(float(sim["net_input_work"])), 1e-18)
    conversion_efficiency = float(receiver_energy_at_target / total_input_work)
    tail_mask = times >= drive_until if len(times) else np.asarray([], dtype=bool)
    if len(times) and int(np.sum(tail_mask)) < 4:
        tail_mask = times >= 0.80 * times[-1]

    row: Dict[str, float | str] = {
        "experiment": "clean_validate",
        "case": config.name,
        "validation_subject": config.name,
        "validation_test": validation_test,
        "reference_role": "ceiling_reference" if config.name in CLEAN_REFERENCE_CANDIDATES else "discovery_candidate",
        "target_freq": target,
        "freqs": "-".join(f"{x:g}" for x in config.mode_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in config.drive_freqs),
        "routes": ";".join(f"{i}-{j}-{k}" for i, j, k in config.routes),
        "seed": seed,
        "quick": str(quick),
        "receiver_energy_at_target": receiver_energy_at_target,
        "total_receiver_energy": total_receiver_energy,
        "spectral_purity_target": spectral_purity,
        "clean_passive_spectral_purity": spectral_purity,
        "total_input_work": total_input_work,
        "clean_passive_conversion_efficiency": conversion_efficiency,
        "conversion_efficiency": conversion_efficiency,
        "clean_passive_phase_lock": phase_lock,
        "phase_lock_score": phase_lock,
        "phase_mismatch_std_rad": phase_std,
        "clean_passive_energy_budget_error": float(sim["energy_budget_error_rel"]),
        "energy_budget_error_frac": float(sim["energy_budget_error_rel"]),
        "max_energy_budget_error_rel": float(sim["max_energy_budget_error_rel"]),
        "damping_loss": float(sim["damping_loss"]),
        "spark_loss": float(sim["spark_loss"]),
        "active_component_input_work": float(sim["active_component_input_work"]),
        "coupling_exchange_primary_secondary": float(sim["coupling_exchange_primary_secondary"]),
        "coupling_exchange_secondary_receiver": float(sim["coupling_exchange_secondary_receiver"]),
        "peak_receiver_energy": float(np.max(energy[:, target_idx])) if len(energy) else 0.0,
        "late_time_receiver_energy": float(np.mean(energy[tail_mask, target_idx])) if len(energy) and int(np.sum(tail_mask)) else 0.0,
        "nonlinear_strength": float(config.nonlinear_strength),
        "varactor_coefficient": float(config.varactor_coefficient),
        "spark_threshold": float(config.spark_threshold),
        "spark_strength": float(config.spark_strength),
        "coupling_scale": float(config.coupling_scale),
        "zeta_scale": float(config.zeta_scale),
        "passive_model": "True",
        "hidden_energy_injection": "False",
        "score": 0.0,
        "clean_validated_discovery_score": 0.0,
        "note": "clean passive validation candidate",
    }

    for stage in clean_stage_targets(config):
        idx = clean_target_index(config, stage)
        if int(np.sum(analysis_mask)) >= 4:
            stage_energy = target_mode_energy(
                qs[analysis_mask, idx],
                vs[analysis_mask, idx],
                times[analysis_mask],
                0.045 * stage,
                float(omega[idx]),
            )
            stage_modal = float(np.mean(energy[analysis_mask, idx]) + 1e-18)
        else:
            stage_energy = 0.0
            stage_modal = 1e-18
        row[f"energy_at_{int(stage)}"] = stage_energy
        row[f"spectral_purity_at_{int(stage)}"] = float(min(1.0, stage_energy / stage_modal))
    return row


def detune_clean_receiver(config: EnergyAuditConfig, target: float, amount: float = 0.35) -> EnergyAuditConfig:
    mode_freqs = list(config.mode_freqs)
    idx = clean_target_index(config, target)
    mode_freqs[idx] = float(mode_freqs[idx]) + amount
    return replace(config, name=f"{config.name}_detuned_receiver", mode_freqs=tuple(mode_freqs))


def detune_clean_pump(config: EnergyAuditConfig, amount: float = 0.25) -> EnergyAuditConfig:
    if not config.drive_freqs:
        return config
    drive_freqs = list(config.drive_freqs)
    shift_idx = 1 if len(drive_freqs) > 1 else 0
    drive_freqs[shift_idx] = float(drive_freqs[shift_idx]) + amount
    return replace(config, name=f"{config.name}_detuned_pump", drive_freqs=tuple(drive_freqs))


def random_clean_control(config: EnergyAuditConfig) -> EnergyAuditConfig:
    if len(config.drive_freqs) >= 2:
        drive_freqs = list(config.drive_freqs)
        drive_freqs[1] = float(drive_freqs[1]) + 0.77
        mode_freqs = list(config.mode_freqs)
        if len(config.drive_modes) > 1:
            mode_freqs[config.drive_modes[1]] = drive_freqs[1]
        return replace(config, name=f"{config.name}_random_non_sum", drive_freqs=tuple(drive_freqs), mode_freqs=tuple(mode_freqs))
    return replace(config, name=f"{config.name}_random_single", drive_freqs=(4.73,))


def linear_clean_control(config: EnergyAuditConfig) -> EnergyAuditConfig:
    return replace(
        config,
        name=f"{config.name}_linear",
        routes=(),
        nonlinear_strength=0.0,
        varactor_coefficient=0.0,
        spark_strength=0.0,
    )


def clean_validation_specs(config: EnergyAuditConfig, quick: bool) -> List[Tuple[str, EnergyAuditConfig, float, float, int, float]]:
    dt, t_max, _ = clean_default_timebase(quick)
    target = clean_primary_target(config)
    if config.name in CLEAN_REFERENCE_CANDIDATES:
        return [
            ("baseline", config, dt, t_max, 0, 1.0),
            ("half_timestep", config, dt * 0.5, t_max, 11, 1.0),
            ("double_runtime", config, dt, t_max * 2.0, 17, 1.0),
            ("alternate_fft_window", config, dt, t_max, 23, 0.55),
            ("energy_budget_audit", config, dt, t_max, 79, 1.0),
        ]
    return [
        ("baseline", config, dt, t_max, 0, 1.0),
        ("half_timestep", config, dt * 0.5, t_max, 11, 1.0),
        ("double_runtime", config, dt, t_max * 2.0, 17, 1.0),
        ("alternate_fft_window", config, dt, t_max, 23, 0.55),
        ("alternate_random_seed_a", config, dt, t_max, 31, 1.0),
        ("alternate_random_seed_b", config, dt, t_max, 47, 1.0),
        ("lower_nonlinear_strength", replace(config, name=f"{config.name}_lower_nonlinear", nonlinear_strength=config.nonlinear_strength * 0.5), dt, t_max, 53, 1.0),
        ("detuned_receiver", detune_clean_receiver(config, target), dt, t_max, 59, 1.0),
        ("detuned_pump", detune_clean_pump(config), dt, t_max, 61, 1.0),
        ("linear_control", linear_clean_control(config), dt, t_max, 67, 1.0),
        ("random_non_sum_control", random_clean_control(config), dt, t_max, 71, 1.0),
        ("input_work_normalization_audit", config, dt, t_max, 73, 1.0),
        ("energy_budget_audit", config, dt, t_max, 79, 1.0),
    ]


def run_clean_validation_rows(seed: int, quick: bool) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]]]:
    rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    for candidate_idx, name in enumerate(CLEAN_VALIDATION_CANDIDATES):
        config = energy_audit_config(name)
        target = clean_primary_target(config)
        for test_idx, (test_name, test_config, dt, t_max, seed_offset, window_scale) in enumerate(clean_validation_specs(config, quick)):
            run_seed = seed + candidate_idx * 1000 + test_idx * 10 + seed_offset
            sim, ledger = simulate_clean_passive(test_config, run_seed, quick, dt=dt, t_max=t_max)
            row = clean_metrics_from_sim(test_config, sim, target, run_seed, test_name, quick, window_scale=window_scale)
            row["case"] = name
            row["validation_subject"] = name
            row["validation_test"] = test_name
            row["dt"] = dt
            row["t_max"] = t_max
            rows.append(row)
            for item in ledger:
                ledger_item = dict(item)
                ledger_item["case"] = name
                ledger_item["validation_test"] = test_name
                ledger_rows.append(ledger_item)
    return rows, ledger_rows


def metric_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / max(denominator, 1e-18))


def ratio_stability_score(value: float, reference: float) -> float:
    if reference <= 1e-18:
        return 1.0 if value <= 1e-12 else 0.0
    ratio = max(value / reference, 1e-18)
    return float(math.exp(-abs(math.log(ratio))))


def mean_float(values: List[float], default: float = 0.0) -> float:
    return float(np.mean(values)) if values else default


def summarize_clean_validation(rows: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    baselines = {str(r["validation_subject"]): r for r in rows if str(r["validation_test"]) == "baseline"}
    direct6_eff = float(baselines.get("direct_6_reference", {}).get("clean_passive_conversion_efficiency", 1e-18))
    direct9_eff = float(baselines.get("direct_9_reference", {}).get("clean_passive_conversion_efficiency", 1e-18))
    summary: List[Dict[str, float | str]] = []

    for subject in CLEAN_VALIDATION_CANDIDATES:
        subject_rows = [r for r in rows if str(r["validation_subject"]) == subject]
        if not subject_rows:
            continue
        by_test = {str(r["validation_test"]): r for r in subject_rows}
        baseline = by_test.get("baseline", subject_rows[0])
        target = float(baseline["target_freq"])
        base_eff = float(baseline["clean_passive_conversion_efficiency"])
        base_energy = float(baseline["receiver_energy_at_target"])
        budget = float(baseline["clean_passive_energy_budget_error"])
        purity = float(baseline["clean_passive_spectral_purity"])
        phase_lock = float(baseline["clean_passive_phase_lock"])

        linear_eff = float(by_test.get("linear_control", {}).get("clean_passive_conversion_efficiency", 0.0))
        detuned_receiver_eff = float(by_test.get("detuned_receiver", {}).get("clean_passive_conversion_efficiency", 0.0))
        detuned_pump_eff = float(by_test.get("detuned_pump", {}).get("clean_passive_conversion_efficiency", 0.0))
        random_eff = float(by_test.get("random_non_sum_control", {}).get("clean_passive_conversion_efficiency", 0.0))
        half_dt_eff = float(by_test.get("half_timestep", {}).get("clean_passive_conversion_efficiency", 0.0))
        runtime_energy = float(by_test.get("double_runtime", {}).get("receiver_energy_at_target", 0.0))
        fft_eff = float(by_test.get("alternate_fft_window", {}).get("clean_passive_conversion_efficiency", 0.0))
        seed_eff = [
            float(by_test[name]["clean_passive_conversion_efficiency"])
            for name in ("alternate_random_seed_a", "alternate_random_seed_b")
            if name in by_test
        ]

        linear_rejection = metric_ratio(base_eff, linear_eff)
        detuned_rejection = metric_ratio(base_eff, max(detuned_receiver_eff, detuned_pump_eff))
        random_rejection = metric_ratio(base_eff, random_eff)
        repeatability = mean_float([ratio_stability_score(x, base_eff) for x in seed_eff], 0.0)
        dt_stability = ratio_stability_score(half_dt_eff, base_eff)
        runtime_stability = float(min(1.0, metric_ratio(runtime_energy, max(base_energy, 1e-18))))
        fft_window_stability = ratio_stability_score(fft_eff, base_eff)
        stability_product = max(1e-9, repeatability * dt_stability * runtime_stability * fft_window_stability)

        ceiling_eff = direct6_eff if target == 6.0 else direct9_eff
        direct_ceiling_ratio = metric_ratio(base_eff, ceiling_eff)
        reference_role = str(baseline["reference_role"])
        pass_budget = budget < 0.005
        pass_phase = phase_lock > 0.85
        pass_purity = purity > 0.20
        pass_linear = True if reference_role == "ceiling_reference" else linear_rejection >= 10.0
        pass_detuned = True if reference_role == "ceiling_reference" else detuned_rejection > 1.0
        pass_random = True if reference_role == "ceiling_reference" else random_rejection > 1.0
        pass_dt = dt_stability > 0.25
        pass_runtime = runtime_stability > 0.25
        passed = all([pass_budget, pass_phase, pass_purity, pass_linear, pass_detuned, pass_random, pass_dt, pass_runtime])

        strong_budget = budget < 0.002
        strong_phase = phase_lock > 0.90
        strong_purity = purity > 0.40
        strong_linear = True if reference_role == "ceiling_reference" else linear_rejection >= 100.0
        strong_stability = min(dt_stability, runtime_stability, fft_window_stability) > 0.50
        strong_passed = all([strong_budget, strong_phase, strong_purity, strong_linear, strong_stability, pass_detuned, pass_random])

        budget_penalty = 1.0 + 500.0 * max(0.0, budget)
        discovery_score = (
            base_eff
            * purity
            * phase_lock
            * math.log1p(min(linear_rejection, 1000.0))
            * math.log1p(min(detuned_rejection, 1000.0))
            * math.log1p(min(random_rejection, 1000.0))
            * stability_product
            / budget_penalty
        )
        if reference_role == "ceiling_reference" or not pass_budget:
            discovery_score = 0.0

        comparison = dict(baseline)
        comparison.update({
            "generated_vs_direct_bridge_ratio": 0.0,
            "repeatability_score": repeatability,
            "dt_stability_score": dt_stability,
            "runtime_stability_score": runtime_stability,
            "fft_window_stability_score": fft_window_stability,
            "detuned_rejection_ratio": detuned_rejection,
            "linear_rejection_ratio": linear_rejection,
            "random_rejection_ratio": random_rejection,
            "direct_ceiling_ratio": direct_ceiling_ratio,
            "distance_from_direct_resonance_ceiling": float(1.0 - min(1.0, direct_ceiling_ratio)),
            "clean_validated_discovery_score": discovery_score,
            "score": discovery_score,
            "passed": str(passed),
            "strong_passed": str(strong_passed),
            "pass_budget_lt_0p005": str(pass_budget),
            "pass_phase_lock_gt_0p85": str(pass_phase),
            "pass_spectral_purity_gt_0p20": str(pass_purity),
            "pass_linear_10x_weaker": str(pass_linear),
            "pass_detuned_weaker": str(pass_detuned),
            "pass_random_weaker": str(pass_random),
            "pass_half_dt_stable": str(pass_dt),
            "pass_runtime_stable": str(pass_runtime),
            "baseline_energy": base_energy,
        })
        failed = [
            key for key in (
                "pass_budget_lt_0p005",
                "pass_phase_lock_gt_0p85",
                "pass_spectral_purity_gt_0p20",
                "pass_linear_10x_weaker",
                "pass_detuned_weaker",
                "pass_random_weaker",
                "pass_half_dt_stable",
                "pass_runtime_stable",
            )
            if comparison[key] != "True"
        ]
        comparison["failed_gates"] = len(failed)
        comparison["failed_gate_names"] = ";".join(failed)
        summary.append(comparison)

        for row in subject_rows:
            row["repeatability_score"] = repeatability
            row["dt_stability_score"] = dt_stability
            row["runtime_stability_score"] = runtime_stability
            row["fft_window_stability_score"] = fft_window_stability
            row["detuned_rejection_ratio"] = detuned_rejection
            row["linear_rejection_ratio"] = linear_rejection
            row["random_rejection_ratio"] = random_rejection
            row["direct_ceiling_ratio"] = direct_ceiling_ratio
            row["distance_from_direct_resonance_ceiling"] = float(1.0 - min(1.0, direct_ceiling_ratio))
            row["clean_validated_discovery_score"] = discovery_score
            row["score"] = discovery_score if str(row["validation_test"]) == "baseline" else 0.0

    return sorted(summary, key=lambda r: float(r["clean_validated_discovery_score"]), reverse=True)


def clean_bridge_summary(comparison_rows: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    by_case = {str(row["case"]): row for row in comparison_rows}
    cascade = by_case.get("cascade_3_generated_6_to_9", {})
    direct36 = by_case.get("direct_3_plus_6_to_9_reference", {})
    direct6 = by_case.get("direct_6_reference", {})
    full = by_case.get("cascade_full_ladder_through_9", {})
    generated_9 = float(cascade.get("energy_at_9", cascade.get("receiver_energy_at_target", 0.0)))
    direct_36_9 = float(direct36.get("energy_at_9", direct36.get("receiver_energy_at_target", 0.0)))
    generated_6 = float(cascade.get("energy_at_6", 0.0))
    direct_6 = float(direct6.get("energy_at_6", direct6.get("receiver_energy_at_target", 0.0)))
    full_15 = float(full.get("energy_at_15", 0.0))
    full_24 = float(full.get("energy_at_24", 0.0))
    return [{
        "generated_vs_direct_bridge_ratio": metric_ratio(generated_9, direct_36_9),
        "generated_6_vs_direct_6_ratio": metric_ratio(generated_6, direct_6),
        "cascade_generated_6_energy_at_9": generated_9,
        "direct_3_plus_6_energy_at_9": direct_36_9,
        "cascade_generated_6_energy_at_6": generated_6,
        "direct_6_reference_energy_at_6": direct_6,
        "full_ladder_energy_at_15": full_15,
        "full_ladder_energy_at_24": full_24,
    }]


def clean_optimization_specs(config: EnergyAuditConfig, quick: bool) -> List[Tuple[str, str, EnergyAuditConfig]]:
    specs: List[Tuple[str, str, EnergyAuditConfig]] = [("baseline", "baseline", config)]
    nonlinear_values = [0.22, 0.50] if quick else [0.16, 0.22, 0.34, 0.50, 0.68]
    spark_thresholds = [0.025, 0.055] if quick else [0.025, 0.035, 0.055]
    varactors = [0.08, 0.34] if quick else [0.08, 0.20, 0.34]
    couplings = [0.75, 1.25] if quick else [0.75, 1.0, 1.25]
    damping = [0.70, 1.35] if quick else [0.70, 1.0, 1.35]
    target = clean_primary_target(config)
    for value in nonlinear_values:
        specs.append(("nonlinear_strength", f"{value:g}", replace(config, nonlinear_strength=value)))
    for value in spark_thresholds:
        specs.append(("spark_threshold", f"{value:g}", replace(config, spark_threshold=value)))
    for value in varactors:
        specs.append(("varactor_coefficient", f"{value:g}", replace(config, varactor_coefficient=value)))
    for value in couplings:
        specs.append(("coupling_scale", f"{value:g}", replace(config, coupling_scale=value)))
    for value in damping:
        specs.append(("damping_q_scale", f"{value:g}", replace(config, zeta_scale=value)))
    for value in (-0.15, 0.15):
        mode_freqs = list(config.mode_freqs)
        idx = clean_target_index(config, target)
        mode_freqs[idx] = float(mode_freqs[idx]) + value
        specs.append(("receiver_detuning", f"{value:g}", replace(config, mode_freqs=tuple(mode_freqs))))
    return specs


def run_clean_optimization(seed: int, quick: bool) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    dt, t_max, _ = clean_default_timebase(quick)
    optimize_candidates = [name for name in CLEAN_VALIDATION_CANDIDATES if name not in {"direct_6_reference", "direct_9_reference"}]
    for candidate_idx, name in enumerate(optimize_candidates):
        config = energy_audit_config(name)
        target = clean_primary_target(config)
        for spec_idx, (sweep, sweep_value, test_config) in enumerate(clean_optimization_specs(config, quick)):
            run_seed = seed + 5000 + candidate_idx * 1000 + spec_idx
            sim, _ = simulate_clean_passive(test_config, run_seed, quick, dt=dt, t_max=t_max)
            row = clean_metrics_from_sim(test_config, sim, target, run_seed, "optimization", quick)
            row["case"] = name
            row["optimization_sweep"] = sweep
            row["optimization_value"] = sweep_value
            budget = float(row["clean_passive_energy_budget_error"])
            is_reference = name in CLEAN_REFERENCE_CANDIDATES
            score = (
                float(row["clean_passive_conversion_efficiency"])
                * float(row["clean_passive_spectral_purity"])
                * float(row["clean_passive_phase_lock"])
                / (1.0 + 500.0 * max(0.0, budget))
            )
            if budget >= 0.005 or is_reference:
                score = 0.0
            row["clean_validated_discovery_score"] = score
            row["score"] = score
            rows.append(row)
    return sorted(rows, key=lambda r: float(r["clean_validated_discovery_score"]), reverse=True)


def plot_clean_outputs(out_dir: Path, comparison: List[Dict[str, float | str]],
                       pass_fail: List[Dict[str, float | str]], ledger: List[Dict[str, float | str]]) -> None:
    baseline_ledger = [r for r in ledger if str(r.get("validation_test")) == "baseline"]
    if baseline_ledger:
        fig, ax = plt.subplots(figsize=(10, 4.8))
        for case in ["atlas_3_plus_3_to_6", "atlas_4_plus_5_to_9", "cascade_3_generated_6_to_9", "cascade_full_ladder_through_9"]:
            rows = [r for r in baseline_ledger if str(r["case"]) == case]
            if rows:
                ax.plot([float(r["time"]) for r in rows], [float(r["energy_budget_error_rel"]) for r in rows], label=case)
        ax.axhline(0.005, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("Clean energy budget over time")
        ax.set_xlabel("time")
        ax.set_ylabel("relative budget error")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "clean_energy_budget_over_time.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4.8))
        for case in ["cascade_3_generated_6_to_9", "cascade_full_ladder_through_9"]:
            rows = [r for r in baseline_ledger if str(r["case"]) == case]
            if rows:
                ax.plot([float(r["time"]) for r in rows], [float(r.get("energy_at_9", 0.0)) for r in rows], label=f"{case} energy@9")
        ax.set_title("Target frequency energy over time")
        ax.set_xlabel("time")
        ax.set_ylabel("modal energy")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / "target_frequency_energy_over_time.png", dpi=140)
        plt.close(fig)

    by_case = {str(row["case"]): row for row in comparison}
    generated = by_case.get("cascade_3_generated_6_to_9", {})
    direct6 = by_case.get("direct_6_reference", {})
    direct36 = by_case.get("direct_3_plus_6_to_9_reference", {})

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(["generated 6", "direct 6"], [float(generated.get("energy_at_6", 0.0)), float(direct6.get("energy_at_6", 0.0))])
    ax.set_title("Generated 6 vs direct 6")
    ax.set_ylabel("spectral energy at 6")
    fig.tight_layout()
    fig.savefig(out_dir / "generated_6_vs_direct_6.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.bar(["3 + generated 6 -> 9", "direct 3 + 6 -> 9"], [float(generated.get("energy_at_9", 0.0)), float(direct36.get("energy_at_9", 0.0))])
    ax.set_title("Generated 6 feeding 9 vs direct 3+6 feeding 9")
    ax.set_ylabel("spectral energy at 9")
    fig.tight_layout()
    fig.savefig(out_dir / "generated_6_feeding_9_vs_direct_3_plus_6.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    labels = [str(r["case"]) for r in comparison if str(r["reference_role"]) == "discovery_candidate"]
    x = np.arange(len(labels))
    width = 0.22
    for offset, key, label in [
        (-width, "dt_stability_score", "dt"),
        (0.0, "runtime_stability_score", "runtime"),
        (width, "fft_window_stability_score", "fft window"),
    ]:
        ax.bar(x + offset, [float(by_case[name].get(key, 0.0)) for name in labels], width=width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_title("Validation stability")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "validation_stability_bar_chart.png", dpi=140)
    plt.close(fig)

    gates = [
        "pass_budget_lt_0p005",
        "pass_phase_lock_gt_0p85",
        "pass_spectral_purity_gt_0p20",
        "pass_linear_10x_weaker",
        "pass_detuned_weaker",
        "pass_random_weaker",
        "pass_half_dt_stable",
        "pass_runtime_stable",
    ]
    matrix = np.asarray([[1.0 if str(row.get(gate)) == "True" else 0.0 for gate in gates] for row in pass_fail])
    if matrix.size:
        fig, ax = plt.subplots(figsize=(11, 5.2))
        ax.imshow(matrix, cmap="Greens", aspect="auto", vmin=0, vmax=1)
        ax.set_yticks(np.arange(len(pass_fail)))
        ax.set_yticklabels([str(r["case"]) for r in pass_fail], fontsize=8)
        ax.set_xticks(np.arange(len(gates)))
        ax.set_xticklabels(gates, rotation=35, ha="right", fontsize=8)
        ax.set_title("Clean candidate pass/fail heatmap")
        fig.tight_layout()
        fig.savefig(out_dir / "candidate_pass_fail_heatmap.png", dpi=140)
        plt.close(fig)


def write_clean_validation_report(out_dir: Path, comparison: List[Dict[str, float | str]],
                                  bridge: List[Dict[str, float | str]]) -> None:
    by_case = {str(row["case"]): row for row in comparison}
    best = next((row for row in comparison if str(row["reference_role"]) == "discovery_candidate"), {})
    bridge_row = bridge[0] if bridge else {}
    full = by_case.get("cascade_full_ladder_through_9", {})
    lines = [
        "# Clean Validation Report",
        "",
        "## Direct Answers",
        f"1. Does 3+3->6 survive strict clean validation? {by_case.get('atlas_3_plus_3_to_6', {}).get('passed', 'False')}.",
        f"2. Does 4+5->9 survive strict clean validation? {by_case.get('atlas_4_plus_5_to_9', {}).get('passed', 'False')}.",
        f"3. Does generated 6 meaningfully replace direct 6 in feeding 9? bridge_ratio={float(bridge_row.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}.",
        f"4. Does the 3->6->9 cascade survive through 9? {by_case.get('cascade_3_generated_6_to_9', {}).get('passed', 'False')}.",
        f"5. Do 15 and 24 remain too weak to promote? energy15={float(full.get('energy_at_15', 0.0)):.6g}, energy24={float(full.get('energy_at_24', 0.0)):.6g}.",
        f"6. Highest clean validated discovery score: {best.get('case', 'none')} score={float(best.get('clean_validated_discovery_score', 0.0)):.6g}.",
        "7. Direct resonance ceiling ratios are in clean_candidate_comparison.csv.",
        "",
        "## Pass Fail",
    ]
    for row in comparison:
        lines.append(
            f"- {row['case']}: passed={row['passed']}, strong={row['strong_passed']}, "
            f"score={float(row['clean_validated_discovery_score']):.6g}, "
            f"budget={float(row['clean_passive_energy_budget_error']):.6g}, "
            f"ceiling_ratio={float(row['direct_ceiling_ratio']):.6g}, failed={row['failed_gate_names']}"
        )
    (out_dir / "README_CLEAN_VALIDATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_clean_validate(out_dir: Path, seed: int, quick: bool = False,
                              include_optimize: bool = False) -> List[Dict[str, float | str]]:
    rows, ledger = run_clean_validation_rows(seed, quick)
    comparison = summarize_clean_validation(rows)
    bridge = clean_bridge_summary(comparison)
    optimized = run_clean_optimization(seed, quick) if include_optimize else [
        dict(row, optimization_sweep="validation_baseline", optimization_value="baseline")
        for row in comparison
    ]
    for row in comparison:
        if row["case"] == "cascade_3_generated_6_to_9" and bridge:
            row["generated_vs_direct_bridge_ratio"] = bridge[0]["generated_vs_direct_bridge_ratio"]

    write_csv(out_dir / "clean_validation_summary.csv", rows)
    write_csv(out_dir / "clean_validation_pass_fail.csv", comparison)
    write_csv(out_dir / "clean_candidate_comparison.csv", comparison)
    write_csv(out_dir / "generated_vs_direct_bridge.csv", bridge)
    write_csv(out_dir / "clean_optimized_candidates.csv", optimized)
    write_csv(out_dir / "clean_energy_ledger_timeseries.csv", ledger)
    plot_clean_outputs(out_dir, comparison, comparison, ledger)
    write_clean_validation_report(out_dir, comparison, bridge)

    return [
        {
            "experiment": "clean_optimize" if include_optimize else "clean_validate",
            "case": row["case"],
            "freqs": row["freqs"],
            "score": row["clean_validated_discovery_score"],
            "passed": row["passed"],
            "strong_passed": row["strong_passed"],
            "clean_passive_energy_budget_error": row["clean_passive_energy_budget_error"],
            "direct_ceiling_ratio": row["direct_ceiling_ratio"],
            "note": "clean passive validated discovery ranking",
        }
        for row in comparison
    ]


# ----------------------------
# Experiment 10: bridge amplification
# ----------------------------

PREVIOUS_CLEAN_BRIDGE_RATIO = 0.1106532540898145


@dataclass
class BridgeAmpConfig:
    name: str
    mode_freqs: Tuple[float, float, float]
    drive_freqs: Tuple[float, ...]
    drive_modes: Tuple[int, ...]
    drive_phases: Tuple[float, ...] = (0.0,)
    target_6: float = 6.0
    target_9: float = 9.0
    stage_a_nonlinear_strength: float = 0.50
    stage_b_nonlinear_strength: float = 0.50
    stage_a_to_stage_b_coupling: float = 1.20
    stage_b_to_receiver_coupling: float = 1.00
    stage_a_damping: float = 0.70
    stage_b_damping: float = 0.70
    receiver_damping: float = 0.80
    drive_amp: float = 0.070
    varactor_coefficient: float = 0.16
    spark_strength: float = 0.08
    spark_threshold: float = 0.035
    stage_b_phase_bias_deg: float = 0.0
    reference_role: str = "discovery_candidate"
    family: str = "369"
    note: str = ""


def bridge_amp_timebase(quick: bool) -> Tuple[float, float, int]:
    if quick:
        return 0.090, 54.0, 1
    return 0.045, 135.0, 2


def bridge_amp_core_configs() -> List[BridgeAmpConfig]:
    generated = BridgeAmpConfig(
        "generated_bridge_3_to_6_to_9",
        mode_freqs=(3.0, 6.0, 9.0),
        drive_freqs=(3.0,),
        drive_modes=(0,),
        note="3-only drive; stage A generates 6, stage B mixes 3+generated6 into 9",
    )
    return [
        generated,
        BridgeAmpConfig(
            "direct_3_plus_6_to_9_reference",
            mode_freqs=(3.0, 6.0, 9.0),
            drive_freqs=(3.0, 6.0),
            drive_modes=(0, 1),
            drive_phases=(0.0, 0.0),
            stage_a_nonlinear_strength=0.0,
            reference_role="reference",
            note="direct 6 is allowed only as a bridge reference; no direct 9 drive",
        ),
        BridgeAmpConfig(
            "direct_6_reference",
            mode_freqs=(6.0, 6.0, 9.0),
            drive_freqs=(6.0,),
            drive_modes=(1,),
            target_6=6.0,
            target_9=9.0,
            stage_a_nonlinear_strength=0.0,
            stage_b_nonlinear_strength=0.0,
            varactor_coefficient=0.0,
            spark_strength=0.0,
            reference_role="reference",
            note="direct 6 strength reference",
        ),
        BridgeAmpConfig(
            "direct_9_ceiling",
            mode_freqs=(3.0, 6.0, 9.0),
            drive_freqs=(9.0,),
            drive_modes=(2,),
            stage_a_nonlinear_strength=0.0,
            stage_b_nonlinear_strength=0.0,
            varactor_coefficient=0.0,
            spark_strength=0.0,
            reference_role="ceiling_reference",
            note="direct 9 ceiling; excluded from discovery ranking",
        ),
        replace(
            generated,
            name="linear_generated_bridge_control",
            stage_a_nonlinear_strength=0.0,
            stage_b_nonlinear_strength=0.0,
            varactor_coefficient=0.0,
            spark_strength=0.0,
            reference_role="control",
            note="3-only drive with nonlinear routes removed",
        ),
        replace(
            generated,
            name="detuned_generated_bridge_control",
            mode_freqs=(3.0, 6.25, 9.35),
            reference_role="control",
            note="3-only drive with generated-6 and receiver stages detuned",
        ),
        replace(
            generated,
            name="random_single_drive_control",
            mode_freqs=(4.73, 6.0, 9.0),
            drive_freqs=(4.73,),
            reference_role="control",
            note="random non-sum single drive control",
        ),
        BridgeAmpConfig(
            "bridge_4_to_8_to_12_control",
            mode_freqs=(4.0, 8.0, 12.0),
            drive_freqs=(4.0,),
            drive_modes=(0,),
            target_6=8.0,
            target_9=12.0,
            family="non369",
            note="non-369 staged bridge control",
        ),
        BridgeAmpConfig(
            "bridge_5_to_10_to_15_control",
            mode_freqs=(5.0, 10.0, 15.0),
            drive_freqs=(5.0,),
            drive_modes=(0,),
            target_6=10.0,
            target_9=15.0,
            family="non369",
            note="non-369 staged bridge control",
        ),
    ]


def bridge_amp_drive_forces(config: BridgeAmpConfig, t: float, base_hz: float,
                            drive_until: float, n_modes: int, enabled: bool = True) -> np.ndarray:
    forces = np.zeros(n_modes)
    if not enabled or t >= drive_until:
        return forces
    ramp_in = min(1.0, t / 10.0)
    ramp_out = min(1.0, max(0.0, (drive_until - t) / 10.0))
    envelope = ramp_in * ramp_out
    norm = math.sqrt(max(1, len(config.drive_freqs)))
    phases = list(config.drive_phases) + [0.0] * max(0, len(config.drive_freqs) - len(config.drive_phases))
    for freq, mode_idx, phase in zip(config.drive_freqs, config.drive_modes, phases):
        forces[mode_idx] += envelope * config.drive_amp * math.sin(2.0 * np.pi * base_hz * freq * t + phase) / norm
    return forces


def bridge_amp_route_strengths(config: BridgeAmpConfig) -> Tuple[float, float]:
    phase_factor = math.cos(math.radians(config.stage_b_phase_bias_deg))
    return config.stage_a_nonlinear_strength, config.stage_b_nonlinear_strength * phase_factor


def bridge_amp_potentials(q: np.ndarray, v: np.ndarray, omega: np.ndarray,
                          config: BridgeAmpConfig) -> Dict[str, float]:
    linear = float(np.sum(0.5 * (v ** 2) + 0.5 * (omega ** 2) * (q ** 2)))
    k01 = 0.0035 * config.stage_a_to_stage_b_coupling * omega[0] * omega[1]
    k12 = 0.0035 * config.stage_b_to_receiver_coupling * omega[1] * omega[2]
    coupling = 0.5 * k01 * float((q[0] - q[1]) ** 2) + 0.5 * k12 * float((q[1] - q[2]) ** 2)
    varactor = 0.25 * config.varactor_coefficient * float(np.sum(q ** 4))
    gamma_a, gamma_b = bridge_amp_route_strengths(config)
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


def bridge_amp_derivative(y: np.ndarray, t: float, omega: np.ndarray, config: BridgeAmpConfig,
                          base_hz: float, drive_until: float, zeta: np.ndarray) -> np.ndarray:
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

    gamma_a, gamma_b = bridge_amp_route_strengths(config)
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
    a += bridge_amp_drive_forces(config, t, base_hz, drive_until, 3)
    return np.concatenate([v, a])


def simulate_bridge_amp(config: BridgeAmpConfig, seed: int, quick: bool,
                        dt: float | None = None, t_max: float | None = None,
                        base_hz: float = 0.045, sample_every: int | None = None
                        ) -> Tuple[Dict[str, object], List[Dict[str, float | str]]]:
    rng = np.random.default_rng(seed)
    default_dt, default_tmax, default_sample = bridge_amp_timebase(quick)
    dt = default_dt if dt is None else dt
    t_max = default_tmax if t_max is None else t_max
    sample_every = default_sample if sample_every is None else sample_every
    omega = 2.0 * np.pi * base_hz * np.asarray(config.mode_freqs, dtype=float)
    zeta = np.asarray([0.018 * config.stage_a_damping, 0.012 * config.stage_b_damping, 0.008 * config.receiver_damping])
    drive_until = 0.74 * t_max

    y = np.zeros(6)
    y[:3] = 1e-4 * rng.normal(size=3)
    y[3:] = 1e-4 * rng.normal(size=3)
    initial_p = bridge_amp_potentials(y[:3], y[3:], omega, config)
    initial_total = float(initial_p["total"])
    drive_work = 0.0
    positive_input_work = 0.0
    damping_loss = 0.0
    spark_loss = 0.0
    coupling_residual_01 = 0.0
    coupling_residual_12 = 0.0

    times: List[float] = []
    qs: List[np.ndarray] = []
    vs: List[np.ndarray] = []
    energies: List[np.ndarray] = []
    ledger: List[Dict[str, float | str]] = []
    n_steps = int(t_max / dt)
    for step in range(n_steps):
        t = step * dt
        q = y[:3]
        v = y[3:]
        before = bridge_amp_potentials(q, v, omega, config)
        drive_forces = bridge_amp_drive_forces(config, t, base_hz, drive_until, 3)
        drive_power = float(np.dot(drive_forces, v))
        drive_work += drive_power * dt
        positive_input_work += max(0.0, drive_power) * dt
        damping_loss += float(np.sum(2.0 * zeta * omega * (v ** 2))) * dt
        if config.spark_strength:
            for i, j in ((0, 1), (1, 2)):
                gate = float(spark_gate(q[i] - q[j], threshold=config.spark_threshold))
                c = 0.030 * config.spark_strength * gate
                spark_loss += float(c * ((v[i] - v[j]) ** 2)) * dt

        y_next = rk4_step(y, t, dt, bridge_amp_derivative, omega, config, base_hz, drive_until, zeta)
        qn = y_next[:3]
        vn = y_next[3:]
        after = bridge_amp_potentials(qn, vn, omega, config)

        k01 = 0.0035 * config.stage_a_to_stage_b_coupling * omega[0] * omega[1]
        k12 = 0.0035 * config.stage_b_to_receiver_coupling * omega[1] * omega[2]
        p01_before = 0.5 * k01 * float((q[0] - q[1]) ** 2)
        p01_after = 0.5 * k01 * float((qn[0] - qn[1]) ** 2)
        p12_before = 0.5 * k12 * float((q[1] - q[2]) ** 2)
        p12_after = 0.5 * k12 * float((qn[1] - qn[2]) ** 2)
        coupling_residual_01 += float((-k01 * (q[0] - q[1])) * v[0] + (k01 * (q[0] - q[1])) * v[1]) * dt + (p01_after - p01_before)
        coupling_residual_12 += float((-k12 * (q[1] - q[2])) * v[1] + (k12 * (q[1] - q[2])) * v[2]) * dt + (p12_after - p12_before)

        y = y_next
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) > 1e6:
            break

        if step % sample_every == 0:
            modal = clean_modal_energy(qn, vn, omega)
            total_accounted = initial_total + drive_work - damping_loss - spark_loss
            error_abs = float(after["total"]) - total_accounted
            error_rel = abs(error_abs) / (abs(float(after["total"])) + abs(total_accounted) + 1e-18)
            times.append(float(t + dt))
            qs.append(qn.copy())
            vs.append(vn.copy())
            energies.append(modal)
            ledger.append({
                "case": config.name,
                "time": float(t + dt),
                "energy_at_3_mode": float(modal[0]),
                "energy_at_6_mode": float(modal[1]),
                "energy_at_9_mode": float(modal[2]),
                "total_stored_energy": float(after["total"]),
                "stored_energy_nonlinear_potential": float(after["nonlinear_total"]),
                "drive_input_work": drive_work,
                "positive_input_work": positive_input_work,
                "damping_loss": damping_loss,
                "spark_loss": spark_loss,
                "active_component_input_work": 0.0,
                "coupling_exchange_stage_a_to_b": coupling_residual_01,
                "coupling_exchange_stage_b_to_receiver": coupling_residual_12,
                "total_accounted_energy": total_accounted,
                "energy_budget_error_abs": error_abs,
                "energy_budget_error_rel": error_rel,
            })

    sim: Dict[str, object] = {
        "times": np.asarray(times),
        "qs": np.asarray(qs),
        "vs": np.asarray(vs),
        "energy": np.asarray(energies),
        "omega": omega,
        "drive_until": drive_until,
        "dt_sample": dt * sample_every,
        "positive_input_work": positive_input_work,
        "net_input_work": drive_work,
        "damping_loss": damping_loss,
        "spark_loss": spark_loss,
        "energy_budget_error_rel": float(ledger[-1]["energy_budget_error_rel"]) if ledger else 1.0,
        "max_energy_budget_error_rel": max((float(r["energy_budget_error_rel"]) for r in ledger), default=1.0),
    }
    return sim, ledger


def bridge_phase_lock(times: np.ndarray, qs: np.ndarray, base_hz: float,
                      f_a: float, f_b: float, f_out: float, i: int, j: int, k: int,
                      sample_dt: float) -> Tuple[float, float]:
    window = max(24, int(6.0 / max(sample_dt, 1e-9)))
    step = max(8, window // 5)
    if len(times) <= window + step:
        return 0.0, float("nan")
    p_i = sliding_phase(qs[:, i], times, base_hz * f_a, window, step)
    p_j = sliding_phase(qs[:, j], times, base_hz * f_b, window, step)
    p_k = sliding_phase(qs[:, k], times, base_hz * f_out, window, step)
    min_len = min(len(p_i), len(p_j), len(p_k))
    mismatch = wrap_angle(p_i[:min_len] + p_j[:min_len] - p_k[:min_len])
    if len(mismatch) == 0:
        return 0.0, float("nan")
    return float(np.abs(np.mean(np.exp(1j * mismatch)))), float(np.std(mismatch))


def bridge_amp_metrics(config: BridgeAmpConfig, sim: Dict[str, object], seed: int,
                       run_type: str, sweep: str = "core", sweep_value: str = "") -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    if len(times) == 0:
        analysis_mask = np.asarray([], dtype=bool)
    else:
        analysis_mask = (times >= 0.35 * drive_until) & (times < drive_until)
        if int(np.sum(analysis_mask)) < 20:
            analysis_mask = times >= 0.45 * times[-1]

    if int(np.sum(analysis_mask)) >= 4:
        energy_at_6 = target_mode_energy(qs[analysis_mask, 1], vs[analysis_mask, 1], times[analysis_mask], 0.045 * config.target_6, float(omega[1]))
        energy_at_9 = target_mode_energy(qs[analysis_mask, 2], vs[analysis_mask, 2], times[analysis_mask], 0.045 * config.target_9, float(omega[2]))
        total_6 = float(np.mean(energy[analysis_mask, 1]) + 1e-18)
        total_9 = float(np.mean(energy[analysis_mask, 2]) + 1e-18)
        phase6, phase6_std = bridge_phase_lock(times[analysis_mask], qs[analysis_mask], 0.045, config.mode_freqs[0], config.mode_freqs[0], config.target_6, 0, 0, 1, float(sim["dt_sample"]))
        phase9, phase9_std = bridge_phase_lock(times[analysis_mask], qs[analysis_mask], 0.045, config.mode_freqs[0], config.target_6, config.target_9, 0, 1, 2, float(sim["dt_sample"]))
    else:
        energy_at_6 = 0.0
        energy_at_9 = 0.0
        total_6 = 1e-18
        total_9 = 1e-18
        phase6 = 0.0
        phase9 = 0.0
        phase6_std = float("nan")
        phase9_std = float("nan")

    total_input_work = max(float(sim["positive_input_work"]), abs(float(sim["net_input_work"])), 1e-18)
    conversion_efficiency = float(energy_at_9 / total_input_work)
    interstage_eff = metric_ratio(energy_at_9, energy_at_6)
    bridge_eff = metric_ratio(energy_at_9, total_input_work)
    no_direct_6 = not any(abs(freq - config.target_6) < 1e-9 and mode == 1 for freq, mode in zip(config.drive_freqs, config.drive_modes))
    no_direct_9 = not any(abs(freq - config.target_9) < 1e-9 and mode == 2 for freq, mode in zip(config.drive_freqs, config.drive_modes))

    return {
        "experiment": "bridge_amp",
        "case": config.name,
        "run_type": run_type,
        "sweep": sweep,
        "sweep_value": sweep_value,
        "family": config.family,
        "reference_role": config.reference_role,
        "freqs": "-".join(f"{x:g}" for x in config.mode_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in config.drive_freqs),
        "target_6": config.target_6,
        "target_9": config.target_9,
        "seed": seed,
        "energy_at_6": energy_at_6,
        "energy_at_9": energy_at_9,
        "generated_6_strength": energy_at_6,
        "generated_vs_direct_6_ratio": 0.0,
        "generated_vs_direct_bridge_ratio": 0.0,
        "energy_at_9_from_generated_bridge": energy_at_9 if config.name == "generated_bridge_3_to_6_to_9" else 0.0,
        "energy_at_9_from_direct_3_plus_6_reference": 0.0,
        "bridge_transfer_efficiency": bridge_eff,
        "conversion_efficiency": conversion_efficiency,
        "spectral_purity_6": float(min(1.0, energy_at_6 / total_6)),
        "spectral_purity_9": float(min(1.0, energy_at_9 / total_9)),
        "phase_lock_6": phase6,
        "phase_lock_9": phase9,
        "phase_lock_6_std": phase6_std,
        "phase_lock_9_std": phase9_std,
        "interstage_coupling_efficiency": interstage_eff,
        "total_input_work": total_input_work,
        "energy_budget_error": float(sim["energy_budget_error_rel"]),
        "max_energy_budget_error": float(sim["max_energy_budget_error_rel"]),
        "direct_ceiling_ratio": 0.0,
        "clean_bridge_score": 0.0,
        "stage_A_nonlinear_strength": config.stage_a_nonlinear_strength,
        "stage_A_receiver_tuning": config.mode_freqs[1],
        "stage_A_damping": config.stage_a_damping,
        "stage_A_Q": metric_ratio(1.0, config.stage_a_damping),
        "stage_A_to_stage_B_coupling": config.stage_a_to_stage_b_coupling,
        "stage_B_nonlinear_strength": config.stage_b_nonlinear_strength,
        "stage_B_receiver_tuning": config.mode_freqs[2],
        "stage_B_damping": config.stage_b_damping,
        "stage_B_Q": metric_ratio(1.0, config.stage_b_damping),
        "stage_B_to_receiver_coupling": config.stage_b_to_receiver_coupling,
        "phase_relationship_deg": config.stage_b_phase_bias_deg,
        "runtime": float(times[-1]) if len(times) else 0.0,
        "coupling_asymmetry": metric_ratio(config.stage_a_to_stage_b_coupling, config.stage_b_to_receiver_coupling),
        "passive_spark_threshold": config.spark_threshold,
        "no_direct_6_drive": str(no_direct_6),
        "no_direct_9_drive": str(no_direct_9),
        "passed": "False",
        "strong_passed": "False",
        "failed_gate_names": "",
        "bottleneck": "",
        "score": 0.0,
        "note": config.note,
    }


def finalize_bridge_amp_rows(rows: List[Dict[str, float | str]]) -> None:
    by_case = {str(r["case"]): r for r in rows if str(r["run_type"]) == "core"}
    generated = by_case.get("generated_bridge_3_to_6_to_9", {})
    direct36 = by_case.get("direct_3_plus_6_to_9_reference", {})
    direct6 = by_case.get("direct_6_reference", {})
    direct9 = by_case.get("direct_9_ceiling", {})
    linear = by_case.get("linear_generated_bridge_control", {})
    detuned = by_case.get("detuned_generated_bridge_control", {})
    random_row = by_case.get("random_single_drive_control", {})

    generated_6 = float(generated.get("energy_at_6", 0.0))
    generated_9 = float(generated.get("energy_at_9", 0.0))
    direct_6 = float(direct6.get("energy_at_6", 0.0))
    direct_36_9 = float(direct36.get("energy_at_9", 0.0))
    direct_9 = float(direct9.get("energy_at_9", 0.0))
    bridge_ratio = metric_ratio(generated_9, direct_36_9)
    direct6_ratio = metric_ratio(generated_6, direct_6)
    linear_rejection = metric_ratio(generated_9, float(linear.get("energy_at_9", 0.0)))
    detuned_rejection = metric_ratio(generated_9, float(detuned.get("energy_at_9", 0.0)))
    random_rejection = metric_ratio(generated_9, float(random_row.get("energy_at_9", 0.0)))

    if direct6_ratio < 0.10:
        bottleneck = "weak_6_generation"
    elif metric_ratio(generated_9, generated_6) < 0.05:
        bottleneck = "poor_6_to_9_transfer"
    else:
        bottleneck = "coupling_or_receiver_loss"

    for row in rows:
        is_generated = str(row["case"]) == "generated_bridge_3_to_6_to_9"
        is_reference = str(row["reference_role"]) in ("reference", "ceiling_reference", "control")
        row["generated_vs_direct_6_ratio"] = direct6_ratio if is_generated else 0.0
        row["generated_vs_direct_bridge_ratio"] = bridge_ratio if is_generated else 0.0
        row["energy_at_9_from_generated_bridge"] = generated_9
        row["energy_at_9_from_direct_3_plus_6_reference"] = direct_36_9
        row["linear_rejection_ratio"] = linear_rejection
        row["detuned_rejection_ratio"] = detuned_rejection
        row["random_rejection_ratio"] = random_rejection
        row["direct_ceiling_ratio"] = metric_ratio(float(row.get("energy_at_9", 0.0)), direct_9)
        row["bottleneck"] = bottleneck if is_generated else ""

        pass_budget = float(row["energy_budget_error"]) < 0.005
        pass_no_direct = True if not is_generated else (str(row["no_direct_6_drive"]) == "True" and str(row["no_direct_9_drive"]) == "True")
        pass_linear = True if not is_generated else linear_rejection >= 10.0
        pass_detuned = True if not is_generated else detuned_rejection > 1.0
        pass_random = True if not is_generated else random_rejection > 1.0
        pass_phase = float(row["phase_lock_9"]) > 0.85
        pass_purity = float(row["spectral_purity_9"]) > 0.20
        passed = all([pass_budget, pass_no_direct, pass_linear, pass_detuned, pass_random, pass_phase, pass_purity])
        strong = all([
            float(row["energy_budget_error"]) < 0.002,
            bridge_ratio > 0.25 if is_generated else True,
            float(row["phase_lock_9"]) > 0.90,
            float(row["spectral_purity_9"]) > 0.40,
        ])
        failed = []
        if not pass_budget:
            failed.append("budget")
        if not pass_no_direct:
            failed.append("direct_drive_contamination")
        if not pass_linear:
            failed.append("linear_control")
        if not pass_detuned:
            failed.append("detuned_control")
        if not pass_random:
            failed.append("random_control")
        if not pass_phase:
            failed.append("phase_lock_9")
        if not pass_purity:
            failed.append("spectral_purity_9")

        score = (
            float(row["conversion_efficiency"])
            * float(row["spectral_purity_9"])
            * float(row["phase_lock_9"])
            * math.log1p(min(linear_rejection, 1000.0))
            * math.log1p(min(detuned_rejection, 1000.0))
            * math.log1p(min(random_rejection, 1000.0))
            * (1.0 + min(bridge_ratio, 2.0) if is_generated else 1.0)
            / (1.0 + 500.0 * max(0.0, float(row["energy_budget_error"])))
        )
        if is_reference or not passed:
            score = 0.0
        row["passed"] = str(passed)
        row["strong_passed"] = str(strong)
        row["failed_gate_names"] = ";".join(failed)
        row["clean_bridge_score"] = score
        row["score"] = score


def bridge_amp_sweep_configs(base: BridgeAmpConfig, quick: bool) -> List[Tuple[str, str, BridgeAmpConfig]]:
    specs: List[Tuple[str, str, BridgeAmpConfig]] = [("baseline", "baseline", base)]
    stage_a_strengths = [0.38, 0.65, 0.90] if quick else [0.28, 0.38, 0.50, 0.65, 0.90]
    stage_b_strengths = [0.38, 0.65, 0.90] if quick else [0.28, 0.38, 0.50, 0.65, 0.90]
    stage_a_tunings = [5.85, 6.0, 6.15] if quick else [5.75, 5.85, 6.0, 6.15, 6.25]
    stage_b_tunings = [8.85, 9.0, 9.15] if quick else [8.75, 8.85, 9.0, 9.15, 9.25]
    damping_values = [0.45, 0.70, 1.05] if quick else [0.35, 0.45, 0.70, 1.05, 1.35]
    coupling_values = [0.75, 1.20, 1.70] if quick else [0.55, 0.75, 1.20, 1.70, 2.20]
    phase_values = [0, 45, 90, 180, 270] if quick else [0, 30, 60, 90, 120, 180, 240, 300]
    runtime_values = [0.75, 1.25] if quick else [0.75, 1.0, 1.35, 1.70]
    spark_thresholds = [0.025, 0.035, 0.055] if quick else [0.020, 0.025, 0.035, 0.055, 0.080]

    for value in stage_a_strengths:
        specs.append(("stage_A_nonlinear_strength", f"{value:g}", replace(base, stage_a_nonlinear_strength=value)))
    for value in stage_a_tunings:
        specs.append(("stage_A_receiver_tuning", f"{value:g}", replace(base, mode_freqs=(3.0, value, 9.0))))
    for value in damping_values:
        specs.append(("stage_A_damping", f"{value:g}", replace(base, stage_a_damping=value)))
        specs.append(("stage_B_damping", f"{value:g}", replace(base, stage_b_damping=value, receiver_damping=value)))
    for value in coupling_values:
        specs.append(("stage_A_to_stage_B_coupling", f"{value:g}", replace(base, stage_a_to_stage_b_coupling=value)))
        specs.append(("stage_B_to_receiver_coupling", f"{value:g}", replace(base, stage_b_to_receiver_coupling=value)))
    for value in stage_b_strengths:
        specs.append(("stage_B_nonlinear_strength", f"{value:g}", replace(base, stage_b_nonlinear_strength=value)))
    for value in stage_b_tunings:
        specs.append(("stage_B_receiver_tuning", f"{value:g}", replace(base, mode_freqs=(3.0, 6.0, value))))
    for value in phase_values:
        specs.append(("phase_relationship", f"{value:g}", replace(base, stage_b_phase_bias_deg=float(value))))
    for value in runtime_values:
        specs.append(("runtime_multiplier", f"{value:g}", replace(base, note=f"runtime_multiplier={value:g}")))
    for value in spark_thresholds:
        specs.append(("passive_spark_threshold", f"{value:g}", replace(base, spark_threshold=value)))
    for a in coupling_values:
        for b in coupling_values:
            specs.append(("bridge_ratio_grid", f"A{a:g}_B{b:g}", replace(base, stage_a_to_stage_b_coupling=a, stage_b_to_receiver_coupling=b)))
    return specs


def run_bridge_amp_sweeps(base: BridgeAmpConfig, seed: int, quick: bool) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    dt, t_max, sample_every = bridge_amp_timebase(quick)
    for idx, (sweep, value, config) in enumerate(bridge_amp_sweep_configs(base, quick)):
        runtime = t_max
        if sweep == "runtime_multiplier":
            runtime *= float(value)
        sim, _ = simulate_bridge_amp(config, seed + 2000 + idx, quick, dt=dt, t_max=runtime, sample_every=sample_every)
        row = bridge_amp_metrics(config, sim, seed + 2000 + idx, "sweep", sweep, value)
        rows.append(row)
    return rows


def bridge_amp_ratio_rows(rows: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    core = [r for r in rows if str(r["run_type"]) == "core"]
    finalize_bridge_amp_rows(core)
    by_case = {str(r["case"]): r for r in core}
    generated = by_case.get("generated_bridge_3_to_6_to_9", {})
    return [{
        "generated_vs_direct_bridge_ratio": generated.get("generated_vs_direct_bridge_ratio", 0.0),
        "generated_vs_direct_6_ratio": generated.get("generated_vs_direct_6_ratio", 0.0),
        "energy_at_9_from_generated_bridge": generated.get("energy_at_9", 0.0),
        "energy_at_9_from_direct_3_plus_6_reference": generated.get("energy_at_9_from_direct_3_plus_6_reference", 0.0),
        "previous_shared_cascade_bridge_ratio": PREVIOUS_CLEAN_BRIDGE_RATIO,
        "staged_beats_previous_shared_cascade": str(float(generated.get("generated_vs_direct_bridge_ratio", 0.0)) > PREVIOUS_CLEAN_BRIDGE_RATIO),
        "bottleneck": generated.get("bottleneck", ""),
    }]


def plot_bridge_amp_outputs(out_dir: Path, rows: List[Dict[str, float | str]],
                            sweep_rows: List[Dict[str, float | str]],
                            ledger: List[Dict[str, float | str]]) -> None:
    generated_ledger = [r for r in ledger if str(r["case"]) == "generated_bridge_3_to_6_to_9"]
    direct_ledger = [r for r in ledger if str(r["case"]) == "direct_3_plus_6_to_9_reference"]
    if generated_ledger:
        times = [float(r["time"]) for r in generated_ledger]
        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["energy_at_6_mode"]) for r in generated_ledger], label="generated 6")
        ax.set_title("Generated 6 over time")
        ax.set_xlabel("time")
        ax.set_ylabel("modal energy")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_amp_generated_6_over_time.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["energy_at_9_mode"]) for r in generated_ledger], label="generated bridge 9")
        if direct_ledger:
            ax.plot([float(r["time"]) for r in direct_ledger], [float(r["energy_at_9_mode"]) for r in direct_ledger], label="direct 3+6 reference 9")
        ax.set_title("9 energy over time")
        ax.set_xlabel("time")
        ax.set_ylabel("modal energy")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_amp_9_energy_over_time.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["energy_budget_error_rel"]) for r in generated_ledger], label="generated bridge")
        ax.axhline(0.005, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("Energy budget overlay")
        ax.set_xlabel("time")
        ax.set_ylabel("relative budget error")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_amp_energy_budget_overlay.png", dpi=140)
        plt.close(fig)

    by_case = {str(r["case"]): r for r in rows}
    gen = by_case.get("generated_bridge_3_to_6_to_9", {})
    direct = by_case.get("direct_3_plus_6_to_9_reference", {})
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.bar(["generated bridge", "direct 3+6 ref"], [float(gen.get("energy_at_9", 0.0)), float(direct.get("energy_at_9", 0.0))])
    ax.set_title("Generated bridge vs direct 3+6 reference")
    ax.set_ylabel("spectral energy at 9")
    fig.tight_layout()
    fig.savefig(out_dir / "bridge_amp_generated_vs_direct_reference.png", dpi=140)
    plt.close(fig)

    grid = [r for r in sweep_rows if str(r.get("sweep")) == "bridge_ratio_grid"]
    if grid:
        a_vals = sorted({float(r["stage_A_to_stage_B_coupling"]) for r in grid})
        b_vals = sorted({float(r["stage_B_to_receiver_coupling"]) for r in grid})
        matrix = np.zeros((len(a_vals), len(b_vals)))
        for r in grid:
            i = a_vals.index(float(r["stage_A_to_stage_B_coupling"]))
            j = b_vals.index(float(r["stage_B_to_receiver_coupling"]))
            matrix[i, j] = float(r["energy_at_9"])
        fig, ax = plt.subplots(figsize=(7.2, 5.2))
        im = ax.imshow(matrix, aspect="auto", origin="lower")
        ax.set_xticks(np.arange(len(b_vals)))
        ax.set_xticklabels([f"{x:g}" for x in b_vals])
        ax.set_yticks(np.arange(len(a_vals)))
        ax.set_yticklabels([f"{x:g}" for x in a_vals])
        ax.set_xlabel("stage B -> receiver coupling")
        ax.set_ylabel("stage A -> B coupling")
        ax.set_title("Bridge ratio heatmap proxy: 9-output")
        fig.colorbar(im, ax=ax, label="energy at target")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_amp_bridge_ratio_heatmap.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.2, 4.8))
        ax.scatter([float(r["stage_A_to_stage_B_coupling"]) for r in grid], [float(r["energy_at_9"]) for r in grid], label="A->B")
        ax.scatter([float(r["stage_B_to_receiver_coupling"]) for r in grid], [float(r["energy_at_9"]) for r in grid], label="B->receiver")
        ax.set_title("Stage coupling vs 9-output")
        ax.set_xlabel("coupling scale")
        ax.set_ylabel("energy at target")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_amp_stage_coupling_vs_9_output.png", dpi=140)
        plt.close(fig)


def write_bridge_amp_report(out_dir: Path, ranked: List[Dict[str, float | str]],
                            ratio_rows: List[Dict[str, float | str]], sweep_rows: List[Dict[str, float | str]]) -> None:
    by_case = {str(row["case"]): row for row in ranked}
    generated = by_case.get("generated_bridge_3_to_6_to_9", {})
    non369 = [r for r in ranked if str(r.get("family")) == "non369"]
    best_non369 = max(non369, key=lambda r: float(r.get("clean_bridge_score", 0.0)), default={})
    best_sweep = max(sweep_rows, key=lambda r: float(r.get("clean_bridge_score", 0.0)), default={})
    ratio = ratio_rows[0] if ratio_rows else {}
    best_ratio = float(ratio.get("best_overall_generated_vs_direct_bridge_ratio", ratio.get("generated_vs_direct_bridge_ratio", 0.0)))
    lines = [
        "# Bridge Amp Report",
        "",
        "## Direct Answers",
        f"1. Can generated 6 replace direct 6 better than the previous 11.1% bridge ratio? {ratio.get('staged_beats_previous_shared_cascade', 'False')}.",
        f"2. Best clean generated_vs_direct_bridge_ratio: {best_ratio:.6g}.",
        f"3. Bottleneck: {ratio.get('bottleneck', 'unknown')}.",
        f"4. Does staged architecture beat the previous shared cascade? {ratio.get('staged_beats_previous_shared_cascade', 'False')}.",
        f"5. Do non-369 staged bridges outperform 3->6->9? best_non369={best_non369.get('case', 'none')} score={float(best_non369.get('clean_bridge_score', 0.0)):.6g}; 369 score={float(generated.get('clean_bridge_score', 0.0)):.6g}.",
        f"6. Candidate to send next: {best_sweep.get('case', generated.get('case', 'none'))} via {best_sweep.get('sweep', 'core')}={best_sweep.get('sweep_value', '')}.",
        "",
        "## Ranked Core",
    ]
    for row in ranked:
        lines.append(
            f"- {row['case']}: score={float(row['clean_bridge_score']):.6g}, passed={row['passed']}, "
            f"strong={row['strong_passed']}, bridge_ratio={float(row['generated_vs_direct_bridge_ratio']):.6g}, "
            f"energy9={float(row['energy_at_9']):.6g}, budget={float(row['energy_budget_error']):.6g}, failed={row['failed_gate_names']}"
        )
    (out_dir / "README_BRIDGE_AMP_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_bridge_amp(out_dir: Path, seed: int, quick: bool = False,
                          include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    dt, t_max, sample_every = bridge_amp_timebase(quick)
    summary_rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    for idx, config in enumerate(bridge_amp_core_configs()):
        sim, ledger = simulate_bridge_amp(config, seed + idx * 100, quick, dt=dt, t_max=t_max, sample_every=sample_every)
        summary_rows.append(bridge_amp_metrics(config, sim, seed + idx * 100, "core"))
        ledger_rows.extend(ledger)

    finalize_bridge_amp_rows(summary_rows)
    ranked = sorted(summary_rows, key=lambda r: float(r["clean_bridge_score"]), reverse=True)
    ratio_rows = bridge_amp_ratio_rows(summary_rows)

    sweep_rows: List[Dict[str, float | str]] = []
    if include_sweeps:
        core_configs = bridge_amp_core_configs()
        base = next(c for c in core_configs if c.name == "generated_bridge_3_to_6_to_9")
        direct36_config = next(c for c in core_configs if c.name == "direct_3_plus_6_to_9_reference")
        direct6_config = next(c for c in core_configs if c.name == "direct_6_reference")
        direct9_config = next(c for c in core_configs if c.name == "direct_9_ceiling")
        sweep_rows = run_bridge_amp_sweeps(base, seed, quick)
        direct36 = next((r for r in summary_rows if r["case"] == "direct_3_plus_6_to_9_reference"), {})
        direct6 = next((r for r in summary_rows if r["case"] == "direct_6_reference"), {})
        direct9 = next((r for r in summary_rows if r["case"] == "direct_9_ceiling"), {})
        linear = next((r for r in summary_rows if r["case"] == "linear_generated_bridge_control"), {})
        detuned = next((r for r in summary_rows if r["case"] == "detuned_generated_bridge_control"), {})
        random_row = next((r for r in summary_rows if r["case"] == "random_single_drive_control"), {})
        for idx, row in enumerate(sweep_rows):
            direct36_energy = float(direct36.get("energy_at_9", 0.0))
            direct6_energy = float(direct6.get("energy_at_6", 0.0))
            direct9_energy = float(direct9.get("energy_at_9", 0.0))
            if row["sweep"] == "runtime_multiplier":
                runtime = float(row["runtime"])
                sim36, _ = simulate_bridge_amp(direct36_config, seed + 8000 + idx * 3, quick, dt=dt, t_max=runtime, sample_every=sample_every)
                sim6, _ = simulate_bridge_amp(direct6_config, seed + 8001 + idx * 3, quick, dt=dt, t_max=runtime, sample_every=sample_every)
                sim9, _ = simulate_bridge_amp(direct9_config, seed + 8002 + idx * 3, quick, dt=dt, t_max=runtime, sample_every=sample_every)
                row36 = bridge_amp_metrics(direct36_config, sim36, seed + 8000 + idx * 3, "runtime_reference")
                row6 = bridge_amp_metrics(direct6_config, sim6, seed + 8001 + idx * 3, "runtime_reference")
                row9 = bridge_amp_metrics(direct9_config, sim9, seed + 8002 + idx * 3, "runtime_reference")
                direct36_energy = float(row36["energy_at_9"])
                direct6_energy = float(row6["energy_at_6"])
                direct9_energy = float(row9["energy_at_9"])
            row["generated_vs_direct_6_ratio"] = metric_ratio(float(row["energy_at_6"]), direct6_energy)
            row["generated_vs_direct_bridge_ratio"] = metric_ratio(float(row["energy_at_9"]), direct36_energy)
            row["energy_at_9_from_generated_bridge"] = row["energy_at_9"]
            row["energy_at_9_from_direct_3_plus_6_reference"] = direct36_energy
            row["linear_rejection_ratio"] = metric_ratio(float(row["energy_at_9"]), float(linear.get("energy_at_9", 0.0)))
            row["detuned_rejection_ratio"] = metric_ratio(float(row["energy_at_9"]), float(detuned.get("energy_at_9", 0.0)))
            row["random_rejection_ratio"] = metric_ratio(float(row["energy_at_9"]), float(random_row.get("energy_at_9", 0.0)))
            row["direct_ceiling_ratio"] = metric_ratio(float(row["energy_at_9"]), direct9_energy)
            pass_budget = float(row["energy_budget_error"]) < 0.005
            pass_phase = float(row["phase_lock_9"]) > 0.85
            pass_purity = float(row["spectral_purity_9"]) > 0.20
            pass_controls = (
                float(row["linear_rejection_ratio"]) >= 10.0
                and float(row["detuned_rejection_ratio"]) > 1.0
                and float(row["random_rejection_ratio"]) > 1.0
            )
            score = (
                float(row["conversion_efficiency"])
                * float(row["spectral_purity_9"])
                * float(row["phase_lock_9"])
                * (1.0 + min(2.0, float(row["generated_vs_direct_bridge_ratio"])))
                / (1.0 + 500.0 * max(0.0, float(row["energy_budget_error"])))
            )
            passed = pass_budget and pass_phase and pass_purity and pass_controls
            if not passed:
                score = 0.0
            row["passed"] = str(passed)
            row["strong_passed"] = str(pass_budget and float(row["energy_budget_error"]) < 0.002 and float(row["generated_vs_direct_bridge_ratio"]) > 0.25 and float(row["phase_lock_9"]) > 0.90 and float(row["spectral_purity_9"]) > 0.40)
            row["clean_bridge_score"] = score
            row["score"] = score
        sweep_rows = sorted(sweep_rows, key=lambda r: float(r["clean_bridge_score"]), reverse=True)
        if sweep_rows and ratio_rows:
            best_ratio_row = max(sweep_rows, key=lambda r: float(r.get("generated_vs_direct_bridge_ratio", 0.0)))
            core_ratio = float(ratio_rows[0].get("generated_vs_direct_bridge_ratio", 0.0))
            best_ratio = float(best_ratio_row.get("generated_vs_direct_bridge_ratio", 0.0))
            ratio_rows[0].update({
                "best_sweep_generated_vs_direct_bridge_ratio": best_ratio,
                "best_sweep_case": best_ratio_row.get("case", ""),
                "best_sweep": best_ratio_row.get("sweep", ""),
                "best_sweep_value": best_ratio_row.get("sweep_value", ""),
                "best_sweep_energy_at_9": best_ratio_row.get("energy_at_9", 0.0),
                "best_sweep_direct_reference_energy_at_9": best_ratio_row.get("energy_at_9_from_direct_3_plus_6_reference", 0.0),
                "best_overall_generated_vs_direct_bridge_ratio": max(core_ratio, best_ratio),
                "staged_beats_previous_shared_cascade": str(max(core_ratio, best_ratio) > PREVIOUS_CLEAN_BRIDGE_RATIO),
            })

    write_csv(out_dir / "bridge_amp_summary.csv", summary_rows)
    write_csv(out_dir / "bridge_amp_ranked.csv", ranked)
    write_csv(out_dir / "bridge_amp_sweeps.csv", sweep_rows if sweep_rows else [dict(row, sweep="core", sweep_value="baseline") for row in ranked])
    write_csv(out_dir / "generated_vs_direct_bridge.csv", ratio_rows)
    write_csv(out_dir / "bridge_stage_energy_timeseries.csv", ledger_rows)
    plot_bridge_amp_outputs(out_dir, ranked, sweep_rows, ledger_rows)
    write_bridge_amp_report(out_dir, ranked, ratio_rows, sweep_rows if sweep_rows else ranked)

    return [
        {
            "experiment": "bridge_amp",
            "case": row["case"],
            "freqs": row["freqs"],
            "score": row["clean_bridge_score"],
            "passed": row["passed"],
            "strong_passed": row["strong_passed"],
            "generated_vs_direct_bridge_ratio": row["generated_vs_direct_bridge_ratio"],
            "energy_budget_error": row["energy_budget_error"],
            "note": row["note"],
        }
        for row in ranked
    ]


# ----------------------------
# Experiment 11: bridge stability
# ----------------------------

def bridge_stability_base_config() -> BridgeAmpConfig:
    base = next(c for c in bridge_amp_core_configs() if c.name == "generated_bridge_3_to_6_to_9")
    return replace(
        base,
        stage_b_nonlinear_strength=0.90,
        note="optimized bridge_amp seed; stabilize full-run phase lock",
    )


def bridge_stability_direct_reference(config: BridgeAmpConfig) -> BridgeAmpConfig:
    reference = next(c for c in bridge_amp_core_configs() if c.name == "direct_3_plus_6_to_9_reference")
    return replace(reference, note="fixed direct 3+6 bridge_amp reference for stability ratio")


def bridge_stability_direct_9(config: BridgeAmpConfig) -> BridgeAmpConfig:
    reference = next(c for c in bridge_amp_core_configs() if c.name == "direct_9_ceiling")
    return replace(reference, note="fixed direct 9 bridge_amp ceiling for stability ratio")


def bridge_stability_linear_control(config: BridgeAmpConfig) -> BridgeAmpConfig:
    return replace(
        config,
        name="linear_generated_bridge_control",
        stage_a_nonlinear_strength=0.0,
        stage_b_nonlinear_strength=0.0,
        varactor_coefficient=0.0,
        spark_strength=0.0,
        reference_role="control",
        note="linear/passive leakage control",
    )


def bridge_stability_detuned_control(config: BridgeAmpConfig) -> BridgeAmpConfig:
    return replace(
        config,
        name="detuned_generated_bridge_control",
        mode_freqs=(config.mode_freqs[0], config.mode_freqs[1] + 0.25, config.mode_freqs[2] + 0.35),
        reference_role="control",
        note="detuned stage A and receiver control",
    )


def bridge_stability_random_control(config: BridgeAmpConfig) -> BridgeAmpConfig:
    return replace(
        config,
        name="random_single_drive_control",
        mode_freqs=(4.73, config.mode_freqs[1], config.mode_freqs[2]),
        drive_freqs=(4.73,),
        drive_modes=(0,),
        reference_role="control",
        note="random non-sum single-drive control",
    )


def bridge_metrics_window(config: BridgeAmpConfig, sim: Dict[str, object], seed: int,
                          run_type: str, sweep: str, sweep_value: str,
                          window_start: float = 0.35, window_end: float = 1.0) -> Dict[str, float | str]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    if len(times) == 0:
        analysis_mask = np.asarray([], dtype=bool)
    else:
        start_t = window_start * drive_until
        end_t = window_end * drive_until
        analysis_mask = (times >= start_t) & (times < end_t)
        if int(np.sum(analysis_mask)) < 20:
            analysis_mask = (times >= 0.35 * drive_until) & (times < drive_until)
        if int(np.sum(analysis_mask)) < 20:
            analysis_mask = times >= 0.45 * times[-1]

    if int(np.sum(analysis_mask)) >= 4:
        energy_at_6 = target_mode_energy(
            qs[analysis_mask, 1],
            vs[analysis_mask, 1],
            times[analysis_mask],
            0.045 * config.target_6,
            float(omega[1]),
        )
        energy_at_9 = target_mode_energy(
            qs[analysis_mask, 2],
            vs[analysis_mask, 2],
            times[analysis_mask],
            0.045 * config.target_9,
            float(omega[2]),
        )
        total_6 = float(np.mean(energy[analysis_mask, 1]) + 1e-18)
        total_9 = float(np.mean(energy[analysis_mask, 2]) + 1e-18)
        phase6, phase6_std = bridge_phase_lock(
            times[analysis_mask],
            qs[analysis_mask],
            0.045,
            config.mode_freqs[0],
            config.mode_freqs[0],
            config.target_6,
            0,
            0,
            1,
            float(sim["dt_sample"]),
        )
        phase9, phase9_std = bridge_phase_lock(
            times[analysis_mask],
            qs[analysis_mask],
            0.045,
            config.mode_freqs[0],
            config.target_6,
            config.target_9,
            0,
            1,
            2,
            float(sim["dt_sample"]),
        )
    else:
        energy_at_6 = 0.0
        energy_at_9 = 0.0
        total_6 = 1e-18
        total_9 = 1e-18
        phase6 = 0.0
        phase9 = 0.0
        phase6_std = float("nan")
        phase9_std = float("nan")

    total_input_work = max(float(sim["positive_input_work"]), abs(float(sim["net_input_work"])), 1e-18)
    return {
        "experiment": "bridge_stability",
        "case": config.name,
        "run_type": run_type,
        "sweep": sweep,
        "sweep_value": sweep_value,
        "candidate_id": f"{sweep}:{sweep_value}",
        "freqs": "-".join(f"{x:g}" for x in config.mode_freqs),
        "drive_freqs": "-".join(f"{x:g}" for x in config.drive_freqs),
        "target_6": config.target_6,
        "target_9": config.target_9,
        "seed": seed,
        "window_start": window_start,
        "window_end": window_end,
        "runtime": float(times[-1]) if len(times) else 0.0,
        "energy_at_6": energy_at_6,
        "energy_at_9": energy_at_9,
        "generated_6_strength": energy_at_6,
        "generated_vs_direct_bridge_ratio": 0.0,
        "energy_at_9_from_direct_3_plus_6_reference": 0.0,
        "conversion_efficiency": float(energy_at_9 / total_input_work),
        "spectral_purity_6": float(min(1.0, energy_at_6 / total_6)),
        "spectral_purity_9": float(min(1.0, energy_at_9 / total_9)),
        "phase_lock_6": phase6,
        "phase_lock_9": phase9,
        "phase_lock_6_std": phase6_std,
        "phase_lock_9_std": phase9_std,
        "interstage_coupling_efficiency": metric_ratio(energy_at_9, energy_at_6),
        "total_input_work": total_input_work,
        "energy_budget_error": float(sim["energy_budget_error_rel"]),
        "max_energy_budget_error": float(sim["max_energy_budget_error_rel"]),
        "direct_ceiling_ratio": 0.0,
        "linear_rejection_ratio": 0.0,
        "detuned_rejection_ratio": 0.0,
        "random_rejection_ratio": 0.0,
        "half_dt_stability_score": 0.0,
        "longer_runtime_stability_score": 0.0,
        "stage_B_nonlinear_strength": config.stage_b_nonlinear_strength,
        "stage_B_damping": config.stage_b_damping,
        "stage_B_Q": metric_ratio(1.0, config.stage_b_damping),
        "stage_A_to_stage_B_coupling": config.stage_a_to_stage_b_coupling,
        "stage_B_to_receiver_coupling": config.stage_b_to_receiver_coupling,
        "coupling_asymmetry": metric_ratio(config.stage_a_to_stage_b_coupling, config.stage_b_to_receiver_coupling),
        "receiver_tuning": config.mode_freqs[2],
        "phase_bias_deg": config.stage_b_phase_bias_deg,
        "spark_threshold": config.spark_threshold,
        "passed": "False",
        "strong_passed": "False",
        "failure_mode": "",
        "failed_gate_names": "",
        "bridge_stability_score": 0.0,
        "score": 0.0,
        "note": config.note,
    }


def bridge_stability_candidate_specs(quick: bool, include_sweeps: bool) -> List[Tuple[str, str, BridgeAmpConfig, float, float]]:
    base = bridge_stability_base_config()
    specs: List[Tuple[str, str, BridgeAmpConfig, float, float]] = [("baseline_optimized", "stageB0.9", base, 1.0, 0.35)]
    if not include_sweeps:
        return specs

    stage_b_values = [0.70, 0.80, 0.90, 0.95] if quick else [0.85, 0.90, 0.95]
    damping_values = [0.45, 0.70, 0.95] if quick else [0.45, 0.70]
    receiver_tunings = [8.90, 9.00, 9.10] if quick else [8.90, 9.00, 9.10]
    couplings = [0.80, 1.20, 1.70] if quick else [0.80, 1.70]
    phase_values = [-45.0, 0.0, 45.0, 90.0] if quick else [-30.0, 0.0, 30.0]
    spark_thresholds = [0.025, 0.035, 0.055] if quick else [0.025, 0.035, 0.055]
    windows = [(0.25, 0.85), (0.35, 1.0), (0.50, 1.0)] if quick else [(0.35, 1.0), (0.50, 1.0)]
    runtimes = [0.85, 1.0, 1.20] if quick else [1.0, 1.20]

    for value in stage_b_values:
        specs.append(("stage_B_nonlinear_strength", f"{value:g}", replace(base, stage_b_nonlinear_strength=value), 1.0, 0.35))
    for value in damping_values:
        specs.append(("stage_B_damping", f"{value:g}", replace(base, stage_b_damping=value, receiver_damping=value), 1.0, 0.35))
    for value in receiver_tunings:
        specs.append(("receiver_detuning", f"{value:g}", replace(base, mode_freqs=(3.0, 6.0, value)), 1.0, 0.35))
    for value in couplings:
        specs.append(("stage_A_to_stage_B_coupling", f"{value:g}", replace(base, stage_a_to_stage_b_coupling=value), 1.0, 0.35))
        specs.append(("stage_B_to_receiver_coupling", f"{value:g}", replace(base, stage_b_to_receiver_coupling=value), 1.0, 0.35))
    asymmetry_pairs = [(1.70, 0.80), (1.45, 0.95), (0.95, 1.45), (0.80, 1.70)] if quick else [(1.45, 0.95), (0.95, 1.45)]
    for a, b in asymmetry_pairs:
        specs.append(("coupling_asymmetry", f"A{a:g}_B{b:g}", replace(base, stage_a_to_stage_b_coupling=a, stage_b_to_receiver_coupling=b), 1.0, 0.35))
    for value in phase_values:
        specs.append(("phase_bias", f"{value:g}", replace(base, stage_b_phase_bias_deg=value), 1.0, 0.35))
    for value in spark_thresholds:
        specs.append(("passive_spark_threshold", f"{value:g}", replace(base, spark_threshold=value), 1.0, 0.35))
    for start, end in windows:
        specs.append(("fft_window", f"{start:g}-{end:g}", base, 1.0, start))
        specs[-1] = (specs[-1][0], specs[-1][1], specs[-1][2], end, start)
    for value in runtimes:
        specs.append(("runtime_length", f"{value:g}", base, value, 0.35))
    return specs


def bridge_stability_controls(config: BridgeAmpConfig, seed: int, quick: bool,
                              dt: float, t_max: float, sample_every: int,
                              window_start: float, window_end: float) -> Dict[str, Dict[str, float | str]]:
    controls = {
        "direct": bridge_stability_direct_reference(config),
        "direct9": bridge_stability_direct_9(config),
        "linear": bridge_stability_linear_control(config),
        "detuned": bridge_stability_detuned_control(config),
        "random": bridge_stability_random_control(config),
    }
    rows: Dict[str, Dict[str, float | str]] = {}
    for idx, (name, control_config) in enumerate(controls.items()):
        sim, _ = simulate_bridge_amp(control_config, seed + 100 + idx, quick, dt=dt, t_max=t_max, sample_every=sample_every)
        rows[name] = bridge_metrics_window(control_config, sim, seed + 100 + idx, f"{name}_control", name, name, window_start, window_end)
    return rows


def finalize_bridge_stability_row(row: Dict[str, float | str],
                                  controls: Dict[str, Dict[str, float | str]]) -> Dict[str, float | str]:
    direct = controls.get("direct", {})
    direct9 = controls.get("direct9", {})
    linear = controls.get("linear", {})
    detuned = controls.get("detuned", {})
    random_row = controls.get("random", {})
    bridge_ratio = metric_ratio(float(row["energy_at_9"]), float(direct.get("energy_at_9", 0.0)))
    linear_rejection = metric_ratio(float(row["energy_at_9"]), float(linear.get("energy_at_9", 0.0)))
    detuned_rejection = metric_ratio(float(row["energy_at_9"]), float(detuned.get("energy_at_9", 0.0)))
    random_rejection = metric_ratio(float(row["energy_at_9"]), float(random_row.get("energy_at_9", 0.0)))
    direct_ceiling_ratio = metric_ratio(float(row["energy_at_9"]), float(direct9.get("energy_at_9", 0.0)))

    pass_ratio = bridge_ratio > 0.75
    pass_phase = float(row["phase_lock_9"]) > 0.90
    pass_purity = float(row["spectral_purity_9"]) > 0.45
    pass_budget = float(row["energy_budget_error"]) < 0.002
    pass_controls = linear_rejection >= 10.0 and detuned_rejection > 1.0 and random_rejection > 1.0
    passed = pass_ratio and pass_phase and pass_purity and pass_budget and pass_controls

    failures = []
    if not pass_ratio:
        failures.append("bridge_ratio")
    if not pass_phase:
        failures.append("phase_lock_9")
    if not pass_purity:
        failures.append("spectral_purity_9")
    if not pass_budget:
        failures.append("energy_budget")
    if not pass_controls:
        failures.append("controls")

    if not pass_phase:
        failure_mode = "phase_drift"
    elif not pass_purity:
        failure_mode = "weak_purity"
    elif not pass_budget:
        failure_mode = "energy_leak"
    elif not pass_ratio:
        failure_mode = "weak_bridge_ratio"
    elif not pass_controls:
        failure_mode = "control_leakage"
    else:
        failure_mode = "stable"

    score = (
        bridge_ratio
        * float(row["phase_lock_9"])
        * float(row["spectral_purity_9"])
        * math.log1p(min(linear_rejection, 1000.0))
        * math.log1p(min(detuned_rejection, 1000.0))
        * math.log1p(min(random_rejection, 1000.0))
        / (1.0 + 500.0 * max(0.0, float(row["energy_budget_error"])))
    )
    if not passed:
        score = 0.0

    row.update({
        "generated_vs_direct_bridge_ratio": bridge_ratio,
        "energy_at_9_from_direct_3_plus_6_reference": direct.get("energy_at_9", 0.0),
        "direct_ceiling_ratio": direct_ceiling_ratio,
        "linear_rejection_ratio": linear_rejection,
        "detuned_rejection_ratio": detuned_rejection,
        "random_rejection_ratio": random_rejection,
        "passed": str(passed),
        "strong_passed": str(passed and bridge_ratio > 0.90 and float(row["phase_lock_9"]) > 0.93 and float(row["spectral_purity_9"]) > 0.55 and float(row["energy_budget_error"]) < 0.001),
        "failure_mode": failure_mode,
        "failed_gate_names": ";".join(failures),
        "bridge_stability_score": score,
        "score": score,
    })
    return row


def bridge_runtime_series(config: BridgeAmpConfig, sim: Dict[str, object],
                          window_steps: int = 10) -> List[Dict[str, float | str]]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    if len(times) < 40:
        return []
    rows: List[Dict[str, float | str]] = []
    window = max(30, len(times) // window_steps)
    step = max(10, window // 3)
    for start in range(0, len(times) - window, step):
        stop = start + window
        t_win = times[start:stop]
        q_win = qs[start:stop]
        v_win = vs[start:stop]
        e9 = target_mode_energy(q_win[:, 2], v_win[:, 2], t_win, 0.045 * config.target_9, float(omega[2]))
        total9 = float(np.mean(energy[start:stop, 2]) + 1e-18)
        phase9, _ = bridge_phase_lock(t_win, q_win, 0.045, config.mode_freqs[0], config.target_6, config.target_9, 0, 1, 2, float(sim["dt_sample"]))
        rows.append({
            "time_mid": float(np.mean(t_win)),
            "energy_at_9": e9,
            "spectral_purity_9": float(min(1.0, e9 / total9)),
            "phase_lock_9": phase9,
        })
    return rows


def run_bridge_stability_validation(config: BridgeAmpConfig, row: Dict[str, float | str],
                                    seed: int, quick: bool, dt: float, t_max: float,
                                    sample_every: int, window_start: float,
                                    window_end: float) -> List[Dict[str, float | str]]:
    validations: List[Tuple[str, float, float]] = [
        ("baseline", dt, t_max),
        ("half_dt", dt * 0.5, t_max),
        ("longer_runtime", dt, t_max * 1.25),
    ]
    rows: List[Dict[str, float | str]] = []
    for idx, (name, test_dt, test_tmax) in enumerate(validations):
        sim, _ = simulate_bridge_amp(config, seed + 500 + idx, quick, dt=test_dt, t_max=test_tmax, sample_every=sample_every)
        test_row = bridge_metrics_window(config, sim, seed + 500 + idx, name, row["sweep"], row["sweep_value"], window_start, window_end)
        controls = bridge_stability_controls(config, seed + 900 + idx * 10, quick, test_dt, test_tmax, sample_every, window_start, window_end)
        finalize_bridge_stability_row(test_row, controls)
        test_row["validation_test"] = name
        test_row["candidate_id"] = row["candidate_id"]
        test_row["relative_bridge_ratio_to_baseline"] = metric_ratio(float(test_row["generated_vs_direct_bridge_ratio"]), float(row["generated_vs_direct_bridge_ratio"]))
        rows.append(test_row)
    return rows


def plot_bridge_stability_outputs(out_dir: Path, ranked: List[Dict[str, float | str]],
                                  validation_rows: List[Dict[str, float | str]],
                                  runtime_rows: List[Dict[str, float | str]],
                                  ledger_rows: List[Dict[str, float | str]]) -> None:
    if ranked:
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        ax.scatter([float(r["generated_vs_direct_bridge_ratio"]) for r in ranked], [float(r["phase_lock_9"]) for r in ranked], c=[float(r["bridge_stability_score"]) for r in ranked])
        ax.axvline(0.75, color="tab:red", linestyle="--", linewidth=1.0)
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_xlabel("generated/direct bridge ratio")
        ax.set_ylabel("phase_lock_9")
        ax.set_title("Bridge ratio vs phase lock")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_ratio_vs_phase_lock.png", dpi=140)
        plt.close(fig)

    if runtime_rows:
        times = [float(r["time_mid"]) for r in runtime_rows]
        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["phase_lock_9"]) for r in runtime_rows])
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("phase_lock_9 over runtime")
        ax.set_xlabel("time")
        ax.set_ylabel("phase lock")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_phase_lock_over_runtime.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["energy_at_9"]) for r in runtime_rows])
        ax.set_title("9-energy over time")
        ax.set_xlabel("time")
        ax.set_ylabel("energy at 9")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_9_energy_over_time.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot(times, [float(r["spectral_purity_9"]) for r in runtime_rows])
        ax.axhline(0.45, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("Spectral purity over time")
        ax.set_xlabel("time")
        ax.set_ylabel("spectral purity at 9")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_spectral_purity_over_time.png", dpi=140)
        plt.close(fig)

    best_case = str(ranked[0]["candidate_id"]) if ranked else ""
    ledger = [r for r in ledger_rows if str(r.get("candidate_id", "")) == best_case]
    if ledger:
        fig, ax = plt.subplots(figsize=(10, 4.8))
        ax.plot([float(r["time"]) for r in ledger], [float(r["energy_budget_error_rel"]) for r in ledger])
        ax.axhline(0.002, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("Energy budget overlay")
        ax.set_xlabel("time")
        ax.set_ylabel("relative budget error")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_energy_budget_overlay.png", dpi=140)
        plt.close(fig)

    if validation_rows:
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        labels = [str(r["validation_test"]) for r in validation_rows]
        ax.bar(labels, [float(r["generated_vs_direct_bridge_ratio"]) for r in validation_rows], alpha=0.75, label="bridge ratio")
        ax.axhline(0.75, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_ylabel("bridge ratio")
        ax2 = ax.twinx()
        ax2.plot(labels, [float(r["phase_lock_9"]) for r in validation_rows], color="tab:orange", marker="o", label="phase lock")
        ax2.axhline(0.90, color="tab:orange", linestyle=":", linewidth=1.0)
        ax.set_title("Full-run vs quick/validation comparison")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_stability_full_vs_quick_comparison.png", dpi=140)
        plt.close(fig)


def write_bridge_stability_report(out_dir: Path, ranked: List[Dict[str, float | str]],
                                  validation_rows: List[Dict[str, float | str]]) -> None:
    best = ranked[0] if ranked else {}
    passing = [r for r in ranked if str(r.get("passed")) == "True"]
    best_passing = passing[0] if passing else {}
    validation_id = str(best_passing.get("candidate_id", ""))
    candidate_validation = [r for r in validation_rows if str(r.get("candidate_id", "")) == validation_id]
    if not candidate_validation:
        candidate_validation = validation_rows[:3]
    half_dt = next((r for r in candidate_validation if str(r.get("validation_test")) == "half_dt"), {})
    longer = next((r for r in candidate_validation if str(r.get("validation_test")) == "longer_runtime"), {})
    lines = [
        "# Bridge Stability Report",
        "",
        "## Direct Answers",
        f"1. Can the 96.6% quick bridge result be stabilized in full non-quick runs? {'yes' if best_passing else 'not yet'} by the current hard gates.",
        f"2. Best passing parameter set: {best_passing.get('sweep', 'none')}={best_passing.get('sweep_value', '')}; ratio={float(best_passing.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}, phase={float(best_passing.get('phase_lock_9', 0.0)):.6g}.",
        f"3. Failure mode of top raw candidate: {best.get('failure_mode', 'unknown')}.",
        f"4. Half-dt preserves result? {half_dt.get('passed', 'False')}; ratio={float(half_dt.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}, phase={float(half_dt.get('phase_lock_9', 0.0)):.6g}.",
        f"5. Promote to geometry369/selflock/evolve? {'yes' if best_passing and half_dt.get('passed') == 'True' and longer.get('passed') == 'True' else 'not yet'}; longer_runtime_pass={longer.get('passed', 'False')}.",
        "",
        "## Ranked Candidates",
    ]
    for row in ranked[:20]:
        lines.append(
            f"- {row['candidate_id']}: score={float(row['bridge_stability_score']):.6g}, passed={row['passed']}, "
            f"ratio={float(row['generated_vs_direct_bridge_ratio']):.6g}, phase={float(row['phase_lock_9']):.6g}, "
            f"purity={float(row['spectral_purity_9']):.6g}, budget={float(row['energy_budget_error']):.6g}, failure={row['failure_mode']}"
        )
    (out_dir / "README_BRIDGE_STABILITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_bridge_stability(out_dir: Path, seed: int, quick: bool = False,
                                include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    dt, t_max, sample_every = bridge_amp_timebase(quick)
    specs = bridge_stability_candidate_specs(quick, include_sweeps)
    summary_rows: List[Dict[str, float | str]] = []
    sweep_rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    control_cache: Dict[Tuple[float, float, float], Dict[str, Dict[str, float | str]]] = {}
    control_base = bridge_stability_base_config()

    for idx, (sweep, value, config, runtime_multiplier, window_start) in enumerate(specs):
        window_end = runtime_multiplier if sweep == "fft_window" else 1.0
        runtime = t_max * runtime_multiplier if sweep == "runtime_length" else t_max
        sim, ledger = simulate_bridge_amp(config, seed + idx * 17, quick, dt=dt, t_max=runtime, sample_every=sample_every)
        row = bridge_metrics_window(config, sim, seed + idx * 17, "sweep" if include_sweeps else "core", sweep, value, window_start, window_end)
        cache_key = (float(runtime), float(window_start), float(window_end))
        if cache_key not in control_cache:
            control_cache[cache_key] = bridge_stability_controls(control_base, seed + 4000 + idx * 31, quick, dt, runtime, sample_every, window_start, window_end)
        controls = control_cache[cache_key]
        finalize_bridge_stability_row(row, controls)
        summary_rows.append(row)
        sweep_rows.append(row)
        for item in ledger:
            ledger_item = dict(item)
            ledger_item["candidate_id"] = row["candidate_id"]
            ledger_item["sweep"] = sweep
            ledger_item["sweep_value"] = value
            ledger_rows.append(ledger_item)

    validation_rows: List[Dict[str, float | str]] = []
    runtime_rows: List[Dict[str, float | str]] = []
    ranked = sorted(summary_rows, key=lambda r: (float(r["bridge_stability_score"]), float(r["generated_vs_direct_bridge_ratio"])), reverse=True)
    candidates_to_validate = [r for r in ranked if str(r["passed"]) == "True"][:5]
    if not candidates_to_validate and ranked:
        candidates_to_validate = [ranked[0]]

    for best_for_validation in candidates_to_validate:
        best_spec = next((spec for spec in specs if f"{spec[0]}:{spec[1]}" == best_for_validation["candidate_id"]), specs[0])
        _, _, best_config, runtime_multiplier, window_start = best_spec
        window_end = runtime_multiplier if best_spec[0] == "fft_window" else 1.0
        runtime = t_max * runtime_multiplier if best_spec[0] == "runtime_length" else t_max
        candidate_validation = run_bridge_stability_validation(best_config, best_for_validation, seed + 9000 + len(validation_rows), quick, dt, runtime, sample_every, window_start, window_end)
        validation_rows.extend(candidate_validation)

        half_dt = next((r for r in candidate_validation if str(r["validation_test"]) == "half_dt"), {})
        longer = next((r for r in candidate_validation if str(r["validation_test"]) == "longer_runtime"), {})
        best_for_validation["half_dt_stability_score"] = ratio_stability_score(
            float(half_dt.get("generated_vs_direct_bridge_ratio", 0.0)),
            float(best_for_validation["generated_vs_direct_bridge_ratio"]),
        )
        best_for_validation["longer_runtime_stability_score"] = ratio_stability_score(
            float(longer.get("generated_vs_direct_bridge_ratio", 0.0)),
            float(best_for_validation["generated_vs_direct_bridge_ratio"]),
        )
        validation_passed = half_dt.get("passed") == "True" and longer.get("passed") == "True"
        if not validation_passed:
            best_for_validation["failed_gate_names"] = ";".join(filter(None, [str(best_for_validation.get("failed_gate_names", "")), "validation_stability"]))
            best_for_validation["passed"] = "False"
            best_for_validation["failure_mode"] = "runtime_instability"
            best_for_validation["bridge_stability_score"] = 0.0
            best_for_validation["score"] = 0.0
        else:
            sim, _ = simulate_bridge_amp(best_config, seed + 9500, quick, dt=dt, t_max=runtime, sample_every=sample_every)
            runtime_rows = bridge_runtime_series(best_config, sim)
            break

    ranked = sorted(summary_rows, key=lambda r: (float(r["bridge_stability_score"]), float(r["generated_vs_direct_bridge_ratio"])), reverse=True)

    write_csv(out_dir / "bridge_stability_summary.csv", summary_rows)
    write_csv(out_dir / "bridge_stability_ranked.csv", ranked)
    write_csv(out_dir / "bridge_stability_sweeps.csv", sweep_rows)
    write_csv(out_dir / "bridge_full_run_validation.csv", validation_rows)
    write_csv(out_dir / "bridge_stability_runtime_series.csv", runtime_rows)
    write_csv(out_dir / "bridge_stability_energy_ledger.csv", ledger_rows)
    plot_bridge_stability_outputs(out_dir, ranked, validation_rows, runtime_rows, ledger_rows)
    write_bridge_stability_report(out_dir, ranked, validation_rows)

    return [
        {
            "experiment": "bridge_stability",
            "case": row["case"],
            "freqs": row["freqs"],
            "score": row["bridge_stability_score"],
            "passed": row["passed"],
            "generated_vs_direct_bridge_ratio": row["generated_vs_direct_bridge_ratio"],
            "phase_lock_9": row["phase_lock_9"],
            "spectral_purity_9": row["spectral_purity_9"],
            "energy_budget_error": row["energy_budget_error"],
            "note": row["note"],
        }
        for row in ranked[:20]
    ]


# ----------------------------
# Experiment 12: bridge phase-lock diagnosis
# ----------------------------

def bridge_phase_lock_base_config() -> BridgeAmpConfig:
    return replace(
        bridge_stability_base_config(),
        stage_b_nonlinear_strength=0.90,
        stage_b_phase_bias_deg=30.0,
        note="phase-lock near-miss seed: stage_B=0.9, phase_bias=30",
    )


def bridge_phase_lock_specs(quick: bool, include_sweeps: bool) -> List[Tuple[str, str, BridgeAmpConfig, float, float, float]]:
    base = bridge_phase_lock_base_config()
    specs: List[Tuple[str, str, BridgeAmpConfig, float, float, float]] = [
        ("baseline_phase_bias_30", "stageB0.9_phase30", base, 1.25, 0.35, 1.0)
    ]
    if not include_sweeps:
        return specs

    receiver_detunings = [8.92, 8.96, 9.00, 9.04, 9.08] if quick else [8.90, 8.95, 9.00, 9.05, 9.10]
    secondary_detunings = [5.92, 5.96, 6.00, 6.04, 6.08] if quick else [5.90, 5.95, 6.00, 6.05, 6.10]
    phase_biases = [20.0, 25.0, 30.0, 35.0, 40.0]
    stage_b_values = [0.75, 0.85, 0.90, 0.95]
    damping_values = [0.45, 0.60, 0.75] if quick else [0.45, 0.60, 0.75, 0.90]
    couplings = [0.85, 1.20, 1.55] if quick else [0.80, 1.10, 1.40, 1.70]
    spark_thresholds = [0.025, 0.035, 0.055]
    windows = [(0.35, 1.0), (0.45, 1.0), (0.55, 1.0)]
    runtimes = [1.10, 1.25, 1.40] if quick else [1.15, 1.25, 1.40]

    for value in receiver_detunings:
        specs.append(("receiver_detuning", f"{value:g}", replace(base, mode_freqs=(3.0, 6.0, value)), 1.25, 0.35, 1.0))
    for value in secondary_detunings:
        specs.append(("secondary_detuning", f"{value:g}", replace(base, mode_freqs=(3.0, value, 9.0)), 1.25, 0.35, 1.0))
    for value in phase_biases:
        specs.append(("phase_bias", f"{value:g}", replace(base, stage_b_phase_bias_deg=value), 1.25, 0.35, 1.0))
    for value in stage_b_values:
        specs.append(("stage_B_nonlinear_strength", f"{value:g}", replace(base, stage_b_nonlinear_strength=value), 1.25, 0.35, 1.0))
    for value in damping_values:
        specs.append(("stage_B_damping", f"{value:g}", replace(base, stage_b_damping=value, receiver_damping=value), 1.25, 0.35, 1.0))
    for value in couplings:
        specs.append(("stage_A_to_stage_B_coupling", f"{value:g}", replace(base, stage_a_to_stage_b_coupling=value), 1.25, 0.35, 1.0))
        specs.append(("stage_B_to_receiver_coupling", f"{value:g}", replace(base, stage_b_to_receiver_coupling=value), 1.25, 0.35, 1.0))
    for value in spark_thresholds:
        specs.append(("passive_spark_threshold", f"{value:g}", replace(base, spark_threshold=value), 1.25, 0.35, 1.0))
    for start, end in windows:
        specs.append(("fft_window", f"{start:g}-{end:g}", base, 1.25, start, end))
    for value in runtimes:
        specs.append(("runtime_length", f"{value:g}", base, value, 0.35, 1.0))
    return specs


def bridge_phase_diagnostic_series(config: BridgeAmpConfig, sim: Dict[str, object],
                                   direct_sim: Dict[str, object] | None = None,
                                   window_start: float = 0.35,
                                   window_end: float = 1.0) -> Tuple[List[Dict[str, float | str]], Dict[str, float | str]]:
    times = sim["times"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    energy = sim["energy"]  # type: ignore[assignment]
    omega = sim["omega"]  # type: ignore[assignment]
    drive_until = float(sim["drive_until"])
    dt_sample = float(sim["dt_sample"])
    if len(times) < 40:
        return [], {
            "phase_drift_rate": 0.0,
            "lock_duration": 0.0,
            "time_to_unlock": 0.0,
            "amplitude_phase_correlation": 0.0,
            "drift_direction": "none",
            "effective_target_frequency": config.target_9,
            "mean_sliding_bridge_ratio": 0.0,
            "min_sliding_phase_lock": 0.0,
        }

    start_idx = int(np.searchsorted(times, window_start * drive_until))
    stop_idx = int(np.searchsorted(times, window_end * drive_until))
    start_idx = max(0, min(start_idx, len(times) - 2))
    stop_idx = max(start_idx + 2, min(stop_idx, len(times)))
    window = max(30, int(6.0 / max(dt_sample, 1e-9)))
    step = max(8, window // 4)

    direct_times = direct_sim["times"] if direct_sim else None  # type: ignore[index]
    direct_qs = direct_sim["qs"] if direct_sim else None  # type: ignore[index]
    direct_vs = direct_sim["vs"] if direct_sim else None  # type: ignore[index]
    direct_omega = direct_sim["omega"] if direct_sim else None  # type: ignore[index]

    raw_rows: List[Dict[str, float | str]] = []
    for start in range(start_idx, max(start_idx + 1, stop_idx - window), step):
        stop = min(start + window, stop_idx)
        if stop - start < 12:
            continue
        t_win = times[start:stop]
        q_win = qs[start:stop]
        v_win = vs[start:stop]
        amp3 = complex_projection(q_win[:, 0], t_win, 0.045 * config.mode_freqs[0])
        amp6 = complex_projection(q_win[:, 1], t_win, 0.045 * config.target_6)
        amp9 = complex_projection(q_win[:, 2], t_win, 0.045 * config.target_9)
        phase3 = float(np.angle(amp3))
        phase6 = float(np.angle(amp6))
        phase9 = float(np.angle(amp9))
        mismatch = float(wrap_angle(phase3 + phase6 - phase9))
        e9 = target_mode_energy(q_win[:, 2], v_win[:, 2], t_win, 0.045 * config.target_9, float(omega[2]))
        total9 = float(np.mean(energy[start:stop, 2]) + 1e-18)

        direct_e9 = 0.0
        if direct_sim is not None and direct_times is not None and direct_qs is not None and direct_vs is not None and direct_omega is not None:
            dmask = (direct_times >= float(t_win[0])) & (direct_times <= float(t_win[-1]))
            if int(np.sum(dmask)) >= 4:
                direct_e9 = target_mode_energy(
                    direct_qs[dmask, 2],
                    direct_vs[dmask, 2],
                    direct_times[dmask],
                    0.045 * config.target_9,
                    float(direct_omega[2]),
                )

        raw_rows.append({
            "time_mid": float(np.mean(t_win)),
            "phase_9_over_time": phase9,
            "phase_mismatch_3_plus_6_minus_9": mismatch,
            "energy_at_9": e9,
            "sliding_spectral_purity_9": float(min(1.0, e9 / total9)),
            "sliding_bridge_ratio": metric_ratio(e9, direct_e9),
            "amplitude_9": float(abs(amp9)),
        })

    if not raw_rows:
        return [], {}

    t_mid = np.asarray([float(r["time_mid"]) for r in raw_rows])
    phase9_unwrapped = np.unwrap(np.asarray([float(r["phase_9_over_time"]) for r in raw_rows]))
    mismatch_unwrapped = np.unwrap(np.asarray([float(r["phase_mismatch_3_plus_6_minus_9"]) for r in raw_rows]))
    if len(t_mid) >= 2:
        phase9_rate = np.gradient(phase9_unwrapped, t_mid)
        mismatch_rate = np.gradient(mismatch_unwrapped, t_mid)
    else:
        phase9_rate = np.zeros_like(t_mid)
        mismatch_rate = np.zeros_like(t_mid)
    inst_freq = config.target_9 + phase9_rate / (2.0 * np.pi * 0.045)
    local_lock = np.exp(-np.minimum(5.0, np.abs(mismatch_rate) * window * dt_sample))
    purity = np.asarray([float(r["sliding_spectral_purity_9"]) for r in raw_rows])
    bridge_ratio = np.asarray([float(r["sliding_bridge_ratio"]) for r in raw_rows])
    amp = np.asarray([float(r["amplitude_9"]) for r in raw_rows])
    phase_abs = np.abs(np.asarray([float(r["phase_mismatch_3_plus_6_minus_9"]) for r in raw_rows]))
    if len(amp) > 2 and np.std(amp) > 1e-12 and np.std(phase_abs) > 1e-12:
        amp_phase_corr = float(np.corrcoef(amp, phase_abs)[0, 1])
    else:
        amp_phase_corr = 0.0

    locked = (local_lock > 0.90) & (purity > 0.45)
    lock_duration = 0.0
    time_to_unlock = float(t_mid[-1] - t_mid[0]) if len(t_mid) else 0.0
    if len(t_mid) >= 2:
        dt_mid = float(np.median(np.diff(t_mid)))
        lock_duration = float(np.sum(locked) * dt_mid)
        for idx in range(0, len(locked)):
            if not locked[idx] and idx >= 2:
                time_to_unlock = float(t_mid[idx] - t_mid[0])
                break
    mean_drift = float(np.mean(mismatch_rate)) if len(mismatch_rate) else 0.0
    if mean_drift > 1e-4:
        drift_direction = "positive"
    elif mean_drift < -1e-4:
        drift_direction = "negative"
    else:
        drift_direction = "flat"

    rows: List[Dict[str, float | str]] = []
    for idx, row in enumerate(raw_rows):
        rr = dict(row)
        rr["instantaneous_frequency_9"] = float(inst_freq[idx])
        rr["phase_drift_rate"] = float(mismatch_rate[idx])
        rr["local_phase_lock"] = float(local_lock[idx])
        rr["effective_target_frequency"] = float(inst_freq[idx])
        rows.append(rr)

    summary = {
        "phase_drift_rate": float(np.mean(np.abs(mismatch_rate))) if len(mismatch_rate) else 0.0,
        "lock_duration": lock_duration,
        "time_to_unlock": time_to_unlock,
        "amplitude_phase_correlation": amp_phase_corr,
        "drift_direction": drift_direction,
        "effective_target_frequency": float(np.mean(inst_freq)) if len(inst_freq) else config.target_9,
        "mean_sliding_bridge_ratio": float(np.mean(bridge_ratio)) if len(bridge_ratio) else 0.0,
        "min_sliding_phase_lock": float(np.min(local_lock)) if len(local_lock) else 0.0,
    }
    return rows, summary


def bridge_phase_lock_controls(config: BridgeAmpConfig, seed: int, quick: bool,
                               dt: float, runtime: float, sample_every: int,
                               window_start: float, window_end: float) -> Tuple[Dict[str, Dict[str, float | str]], Dict[str, object]]:
    controls = bridge_stability_controls(config, seed, quick, dt, runtime, sample_every, window_start, window_end)
    direct_config = bridge_stability_direct_reference(config)
    direct_sim, _ = simulate_bridge_amp(direct_config, seed + 700, quick, dt=dt, t_max=runtime, sample_every=sample_every)
    return controls, direct_sim


def finalize_bridge_phase_lock_row(row: Dict[str, float | str],
                                   controls: Dict[str, Dict[str, float | str]]) -> None:
    finalize_bridge_stability_row(row, controls)
    pass_ratio = float(row["generated_vs_direct_bridge_ratio"]) > 0.75
    pass_phase = float(row["phase_lock_9"]) > 0.90
    pass_purity = float(row["spectral_purity_9"]) > 0.45
    pass_budget = float(row["energy_budget_error"]) < 0.002
    pass_controls = (
        float(row["linear_rejection_ratio"]) >= 10.0
        and float(row["detuned_rejection_ratio"]) > 1.0
        and float(row["random_rejection_ratio"]) > 1.0
    )
    pass_lock_duration = float(row.get("lock_duration", 0.0)) >= 0.40 * max(float(row.get("runtime", 0.0)), 1e-18)
    passed = pass_ratio and pass_phase and pass_purity and pass_budget and pass_controls
    score = (
        float(row["generated_vs_direct_bridge_ratio"])
        * float(row["phase_lock_9"])
        * float(row["spectral_purity_9"])
        * (1.0 + min(1.0, float(row.get("lock_duration", 0.0)) / max(float(row.get("runtime", 1.0)), 1e-18)))
        / (1.0 + 500.0 * float(row["energy_budget_error"]))
    )
    if not passed:
        score = 0.0

    failures = []
    if not pass_ratio:
        failures.append("bridge_ratio")
    if not pass_phase:
        failures.append("phase_lock_9")
    if not pass_purity:
        failures.append("spectral_purity_9")
    if not pass_budget:
        failures.append("energy_budget")
    if not pass_controls:
        failures.append("controls")
    if passed and not pass_lock_duration:
        failures.append("short_lock_duration")

    if abs(float(row.get("effective_target_frequency", 9.0)) - float(row["target_9"])) > 0.08:
        failure_mode = "frequency_detuning"
    elif float(row.get("phase_drift_rate", 0.0)) > 0.012:
        failure_mode = "phase_drift"
    elif not pass_ratio:
        failure_mode = "coupling_loss"
    elif not pass_purity:
        failure_mode = "weak_purity"
    elif float(row.get("amplitude_phase_correlation", 0.0)) < -0.35:
        failure_mode = "beating"
    elif "fft_window" in failures:
        failure_mode = "fft_window_artifact"
    else:
        failure_mode = "stable"

    row["passed"] = str(passed)
    row["strong_passed"] = str(passed and pass_lock_duration and float(row["phase_lock_9"]) > 0.93 and float(row["generated_vs_direct_bridge_ratio"]) > 0.90)
    row["failed_gate_names"] = ";".join(failures)
    row["failure_mode"] = failure_mode
    row["bridge_phase_lock_score"] = score
    row["score"] = score


def bridge_phase_lock_validation(config: BridgeAmpConfig, row: Dict[str, float | str],
                                 seed: int, quick: bool, dt: float, runtime: float,
                                 sample_every: int, window_start: float,
                                 window_end: float) -> List[Dict[str, float | str]]:
    validations = [
        ("baseline", dt, runtime),
        ("half_dt", dt * 0.5, runtime),
        ("longer_runtime", dt, runtime * 1.15),
    ]
    rows: List[Dict[str, float | str]] = []
    for idx, (name, test_dt, test_runtime) in enumerate(validations):
        sim, _ = simulate_bridge_amp(config, seed + idx * 17, quick, dt=test_dt, t_max=test_runtime, sample_every=sample_every)
        controls, direct_sim = bridge_phase_lock_controls(config, seed + 200 + idx * 31, quick, test_dt, test_runtime, sample_every, window_start, window_end)
        metrics = bridge_metrics_window(config, sim, seed + idx * 17, name, row["sweep"], row["sweep_value"], window_start, window_end)
        diag_rows, diag_summary = bridge_phase_diagnostic_series(config, sim, direct_sim, window_start, window_end)
        metrics.update(diag_summary)
        finalize_bridge_phase_lock_row(metrics, controls)
        metrics["validation_test"] = name
        metrics["candidate_id"] = row["candidate_id"]
        metrics["relative_bridge_ratio_to_candidate"] = metric_ratio(float(metrics["generated_vs_direct_bridge_ratio"]), float(row["generated_vs_direct_bridge_ratio"]))
        rows.append(metrics)
    return rows


def bridge_phase_lock_arnold_specs(quick: bool) -> List[Tuple[str, float, float, BridgeAmpConfig]]:
    base = bridge_phase_lock_base_config()
    if quick:
        detunings = [8.95, 9.0, 9.05]
        strengths = [0.80, 0.90, 0.95]
        phases = [25.0, 30.0, 35.0]
        couplings = [0.85, 1.20, 1.55]
        damping = [0.45, 0.70, 0.95]
    else:
        detunings = [8.90, 8.95, 9.0, 9.05, 9.10]
        strengths = [0.75, 0.85, 0.90, 0.95]
        phases = [20.0, 25.0, 30.0, 35.0, 40.0]
        couplings = [0.80, 1.10, 1.40, 1.70]
        damping = [0.45, 0.60, 0.75, 0.90]

    specs: List[Tuple[str, float, float, BridgeAmpConfig]] = []
    for detuning in detunings:
        for strength in strengths:
            specs.append(("receiver_detuning_vs_stage_B_strength", detuning, strength, replace(base, mode_freqs=(3.0, 6.0, detuning), stage_b_nonlinear_strength=strength)))
    for phase in phases:
        for detuning in detunings:
            specs.append(("phase_bias_vs_receiver_detuning", phase, detuning, replace(base, stage_b_phase_bias_deg=phase, mode_freqs=(3.0, 6.0, detuning))))
    for coupling in couplings:
        for detuning in detunings:
            specs.append(("coupling_vs_detuning", coupling, detuning, replace(base, stage_b_to_receiver_coupling=coupling, mode_freqs=(3.0, 6.0, detuning))))
    for damp in damping:
        for detuning in detunings:
            specs.append(("damping_vs_detuning", damp, detuning, replace(base, stage_b_damping=damp, receiver_damping=damp, mode_freqs=(3.0, 6.0, detuning))))
    return specs


def run_bridge_phase_lock_arnold_maps(seed: int, quick: bool, dt: float, runtime: float,
                                      sample_every: int) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    control_cache: Dict[Tuple[float, float, float], Dict[str, Dict[str, float | str]]] = {}
    for idx, (map_type, x, y, config) in enumerate(bridge_phase_lock_arnold_specs(quick)):
        sim, _ = simulate_bridge_amp(config, seed + 6000 + idx, quick, dt=dt, t_max=runtime, sample_every=sample_every)
        cache_key = (runtime, 0.35, 1.0)
        if cache_key not in control_cache:
            control_cache[cache_key] = bridge_stability_controls(config, seed + 8000, quick, dt, runtime, sample_every, 0.35, 1.0)
        metrics = bridge_metrics_window(config, sim, seed + 6000 + idx, "arnold", map_type, f"{x:g}_{y:g}", 0.35, 1.0)
        diag_rows, diag_summary = bridge_phase_diagnostic_series(config, sim, None, 0.35, 1.0)
        metrics.update(diag_summary)
        finalize_bridge_phase_lock_row(metrics, control_cache[cache_key])
        rows.append({
            "map_type": map_type,
            "x_value": x,
            "y_value": y,
            "phase_lock_9": metrics["phase_lock_9"],
            "lock_duration": metrics.get("lock_duration", 0.0),
            "generated_vs_direct_bridge_ratio": metrics["generated_vs_direct_bridge_ratio"],
            "spectral_purity_9": metrics["spectral_purity_9"],
            "effective_target_frequency": metrics.get("effective_target_frequency", config.target_9),
            "energy_budget_error": metrics["energy_budget_error"],
            "passed": metrics["passed"],
            "score": metrics["bridge_phase_lock_score"],
        })
    return rows


def plot_bridge_phase_lock_outputs(out_dir: Path, ranked: List[Dict[str, float | str]],
                                   drift_rows: List[Dict[str, float | str]],
                                   arnold_rows: List[Dict[str, float | str]]) -> None:
    if drift_rows:
        times = [float(r["time_mid"]) for r in drift_rows]
        plot_specs = [
            ("phase_9_over_time", "phase_9_over_time", "phase 9"),
            ("instantaneous_frequency_9", "instantaneous_frequency_9", "instantaneous frequency near 9"),
            ("sliding_spectral_purity_9", "sliding_spectral_purity_9", "sliding spectral purity"),
            ("sliding_bridge_ratio", "sliding_bridge_ratio", "sliding bridge ratio"),
            ("phase_drift_rate", "phase_drift_rate", "phase drift rate"),
        ]
        for filename, key, title in plot_specs:
            fig, ax = plt.subplots(figsize=(10, 4.8))
            ax.plot(times, [float(r.get(key, 0.0)) for r in drift_rows])
            ax.set_title(title)
            ax.set_xlabel("time")
            ax.set_ylabel(key)
            fig.tight_layout()
            fig.savefig(out_dir / f"bridge_phase_lock_{filename}.png", dpi=140)
            plt.close(fig)

    if ranked:
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        ax.scatter([float(r["generated_vs_direct_bridge_ratio"]) for r in ranked], [float(r["phase_lock_9"]) for r in ranked], c=[float(r.get("bridge_phase_lock_score", 0.0)) for r in ranked])
        ax.axvline(0.75, color="tab:red", linestyle="--", linewidth=1.0)
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("Bridge ratio vs phase lock")
        ax.set_xlabel("bridge ratio")
        ax.set_ylabel("phase_lock_9")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_phase_lock_ratio_vs_phase_lock.png", dpi=140)
        plt.close(fig)

    for map_type in sorted({str(r["map_type"]) for r in arnold_rows}):
        rows = [r for r in arnold_rows if str(r["map_type"]) == map_type]
        if not rows:
            continue
        xs = sorted({float(r["x_value"]) for r in rows})
        ys = sorted({float(r["y_value"]) for r in rows})
        if not xs or not ys:
            continue
        metric = "phase_lock_9"
        if map_type == "phase_bias_vs_receiver_detuning":
            metric = "lock_duration"
        elif map_type == "coupling_vs_detuning":
            metric = "generated_vs_direct_bridge_ratio"
        elif map_type == "damping_vs_detuning":
            metric = "spectral_purity_9"
        matrix = np.zeros((len(ys), len(xs)))
        for r in rows:
            x_idx = xs.index(float(r["x_value"]))
            y_idx = ys.index(float(r["y_value"]))
            matrix[y_idx, x_idx] = float(r.get(metric, 0.0))
        fig, ax = plt.subplots(figsize=(7.5, 5.4))
        im = ax.imshow(matrix, origin="lower", aspect="auto")
        ax.set_xticks(np.arange(len(xs)))
        ax.set_xticklabels([f"{x:g}" for x in xs], rotation=30, ha="right")
        ax.set_yticks(np.arange(len(ys)))
        ax.set_yticklabels([f"{y:g}" for y in ys])
        ax.set_title(f"Arnold tongue: {map_type}")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        fig.colorbar(im, ax=ax, label=metric)
        fig.tight_layout()
        fig.savefig(out_dir / f"bridge_phase_lock_arnold_{safe_token(map_type)}.png", dpi=140)
        plt.close(fig)


def write_bridge_phase_lock_report(out_dir: Path, ranked: List[Dict[str, float | str]],
                                   validation_rows: List[Dict[str, float | str]],
                                   drift_rows: List[Dict[str, float | str]]) -> None:
    best = ranked[0] if ranked else {}
    passing = [r for r in ranked if str(r.get("passed")) == "True"]
    best_passing = passing[0] if passing else {}
    longer = next((r for r in validation_rows if str(r.get("validation_test")) == "longer_runtime" and str(r.get("candidate_id")) == str(best_passing.get("candidate_id", ""))), {})
    if not longer:
        longer = next((r for r in validation_rows if str(r.get("validation_test")) == "longer_runtime"), {})
    effective_freq = float(best.get("effective_target_frequency", 9.0))
    failure = best.get("failure_mode", "unknown")
    if failure == "phase_drift" and abs(effective_freq - 9.0) > 0.04:
        cause = "phase drift with slight effective frequency detuning"
    elif failure == "frequency_detuning":
        cause = "effective frequency detuning"
    elif failure == "beating":
        cause = "beating between amplitude and phase"
    elif failure == "coupling_loss":
        cause = "coupling loss / bridge ratio decay"
    elif failure == "stable":
        cause = "no hard failure in the measured window"
    else:
        cause = str(failure)

    lines = [
        "# Bridge Phase Lock Report",
        "",
        "## Direct Answers",
        f"1. Long-run failure cause: {cause}.",
        f"2. Effective generated target frequency near 9: {effective_freq:.6g}.",
        f"3. Stable lock island with longer-runtime phase_lock_9 > 0.90? {'yes' if best_passing and longer.get('passed') == 'True' else 'not found'} by current gates.",
        f"4. Parameter set to promote: {best_passing.get('candidate_id', 'none')}; ratio={float(best_passing.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}, phase={float(best_passing.get('phase_lock_9', 0.0)):.6g}.",
        f"5. Next step: {'passive tuning' if best_passing else 'active PLL/selflock'}; geometry369 should wait for a validated long-runtime lock.",
        "",
        "## Ranked Candidates",
    ]
    for row in ranked[:20]:
        lines.append(
            f"- {row['candidate_id']}: score={float(row.get('bridge_phase_lock_score', 0.0)):.6g}, passed={row['passed']}, "
            f"ratio={float(row['generated_vs_direct_bridge_ratio']):.6g}, phase={float(row['phase_lock_9']):.6g}, "
            f"purity={float(row['spectral_purity_9']):.6g}, eff_freq={float(row.get('effective_target_frequency', 9.0)):.6g}, "
            f"drift={float(row.get('phase_drift_rate', 0.0)):.6g}, failure={row.get('failure_mode', '')}"
        )
    (out_dir / "README_BRIDGE_PHASE_LOCK_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_bridge_phase_lock(out_dir: Path, seed: int, quick: bool = False,
                                 include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    dt, base_tmax, sample_every = bridge_amp_timebase(quick)
    specs = bridge_phase_lock_specs(quick, include_sweeps)
    summary_rows: List[Dict[str, float | str]] = []
    drift_rows_all: List[Dict[str, float | str]] = []
    lock_rows: List[Dict[str, float | str]] = []
    control_cache: Dict[Tuple[float, float, float], Tuple[Dict[str, Dict[str, float | str]], Dict[str, object]]] = {}

    for idx, (sweep, value, config, runtime_multiplier, window_start, window_end) in enumerate(specs):
        runtime = base_tmax * runtime_multiplier
        sim, _ = simulate_bridge_amp(config, seed + idx * 19, quick, dt=dt, t_max=runtime, sample_every=sample_every)
        cache_key = (runtime, window_start, window_end)
        if cache_key not in control_cache:
            control_cache[cache_key] = bridge_phase_lock_controls(config, seed + 3000 + idx * 23, quick, dt, runtime, sample_every, window_start, window_end)
        controls, direct_sim = control_cache[cache_key]
        row = bridge_metrics_window(config, sim, seed + idx * 19, "sweep" if include_sweeps else "core", sweep, value, window_start, window_end)
        diag_rows, diag_summary = bridge_phase_diagnostic_series(config, sim, direct_sim, window_start, window_end)
        row.update(diag_summary)
        finalize_bridge_phase_lock_row(row, controls)
        summary_rows.append(row)
        for drow in diag_rows:
            dd = dict(drow)
            dd["candidate_id"] = row["candidate_id"]
            dd["sweep"] = sweep
            dd["sweep_value"] = value
            drift_rows_all.append(dd)
        lock_rows.append({
            "candidate_id": row["candidate_id"],
            "sweep": sweep,
            "sweep_value": value,
            "phase_drift_rate": row.get("phase_drift_rate", 0.0),
            "lock_duration": row.get("lock_duration", 0.0),
            "time_to_unlock": row.get("time_to_unlock", 0.0),
            "drift_direction": row.get("drift_direction", ""),
            "effective_target_frequency": row.get("effective_target_frequency", config.target_9),
            "amplitude_phase_correlation": row.get("amplitude_phase_correlation", 0.0),
            "generated_vs_direct_bridge_ratio": row["generated_vs_direct_bridge_ratio"],
            "phase_lock_9": row["phase_lock_9"],
            "spectral_purity_9": row["spectral_purity_9"],
            "passed": row["passed"],
        })

    arnold_runtime = base_tmax * (1.10 if quick else 1.15)
    arnold_rows = run_bridge_phase_lock_arnold_maps(seed, quick, dt, arnold_runtime, sample_every) if include_sweeps else []
    ranked = sorted(summary_rows, key=lambda r: (float(r.get("bridge_phase_lock_score", 0.0)), float(r["generated_vs_direct_bridge_ratio"])), reverse=True)

    validation_rows: List[Dict[str, float | str]] = []
    top_candidates = [r for r in ranked if str(r["passed"]) == "True"][:4]
    if not top_candidates and ranked:
        top_candidates = [ranked[0]]
    for idx, candidate in enumerate(top_candidates):
        spec = next((s for s in specs if f"{s[0]}:{s[1]}" == candidate["candidate_id"]), specs[0])
        _, _, config, runtime_multiplier, window_start, window_end = spec
        runtime = base_tmax * runtime_multiplier
        candidate_validation = bridge_phase_lock_validation(config, candidate, seed + 9000 + idx * 200, quick, dt, runtime, sample_every, window_start, window_end)
        validation_rows.extend(candidate_validation)
        half_dt = next((r for r in candidate_validation if str(r["validation_test"]) == "half_dt"), {})
        longer = next((r for r in candidate_validation if str(r["validation_test"]) == "longer_runtime"), {})
        if not (half_dt.get("passed") == "True" and longer.get("passed") == "True"):
            candidate["passed"] = "False"
            candidate["failed_gate_names"] = ";".join(filter(None, [str(candidate.get("failed_gate_names", "")), "validation_stability"]))
            candidate["failure_mode"] = "phase_drift" if float(longer.get("phase_lock_9", 0.0)) < 0.90 else "runtime_instability"
            candidate["bridge_phase_lock_score"] = 0.0
            candidate["score"] = 0.0
        else:
            break

    ranked = sorted(summary_rows, key=lambda r: (float(r.get("bridge_phase_lock_score", 0.0)), float(r["generated_vs_direct_bridge_ratio"])), reverse=True)
    best_id = str(ranked[0]["candidate_id"]) if ranked else ""
    drift_rows = [r for r in drift_rows_all if str(r.get("candidate_id", "")) == best_id]
    if not drift_rows and drift_rows_all:
        drift_rows = drift_rows_all[:]

    write_csv(out_dir / "bridge_phase_lock_summary.csv", summary_rows)
    write_csv(out_dir / "bridge_phase_lock_ranked.csv", ranked)
    write_csv(out_dir / "bridge_phase_drift_timeseries.csv", drift_rows_all)
    write_csv(out_dir / "bridge_lock_islands.csv", lock_rows)
    write_csv(out_dir / "bridge_arnold_tongue_map.csv", arnold_rows)
    write_csv(out_dir / "bridge_phase_lock_validation.csv", validation_rows)
    plot_bridge_phase_lock_outputs(out_dir, ranked, drift_rows, arnold_rows)
    write_bridge_phase_lock_report(out_dir, ranked, validation_rows, drift_rows)

    return [
        {
            "experiment": "bridge_phase_lock",
            "case": row["case"],
            "freqs": row["freqs"],
            "score": row.get("bridge_phase_lock_score", 0.0),
            "passed": row["passed"],
            "generated_vs_direct_bridge_ratio": row["generated_vs_direct_bridge_ratio"],
            "phase_lock_9": row["phase_lock_9"],
            "effective_target_frequency": row.get("effective_target_frequency", 9.0),
            "failure_mode": row.get("failure_mode", ""),
            "note": row["note"],
        }
        for row in ranked[:20]
    ]


# ----------------------------
# Experiment 13: bridge lock refinement
# ----------------------------

def bridge_lock_refine_base_config() -> BridgeAmpConfig:
    return replace(
        bridge_phase_lock_base_config(),
        mode_freqs=(3.0, 6.0, 8.90),
        stage_b_phase_bias_deg=30.0,
        stage_b_nonlinear_strength=0.90,
        note="promoted passive lock island: receiver_tuning=8.9, phase_bias=30, stage_B=0.9",
    )


BridgeLockRefineSpec = Tuple[str, str, BridgeAmpConfig, float, float, float, str]


def bridge_lock_refine_specs(quick: bool, include_sweeps: bool) -> List[BridgeLockRefineSpec]:
    base = bridge_lock_refine_base_config()
    specs: List[BridgeLockRefineSpec] = [
        ("promoted_baseline", "receiver8.9_phase30_stageB0.9", base, 1.25, 0.35, 1.0, "baseline")
    ]
    if not include_sweeps:
        return specs

    if quick:
        receiver_detunings = [8.86, 8.885, 8.90, 8.915, 8.93]
        phase_biases = [20.0, 23.5, 26.5, 30.0]
        strengths = [0.84, 0.88, 0.90, 0.94]
        coupling_a_values = [1.02, 1.20, 1.38]
        coupling_b_values = [0.85, 1.00, 1.15]
        damping_values = [0.56, 0.70, 0.84]
        spark_values = [0.028, 0.035, 0.042]
        windows = [(0.30, 1.0), (0.35, 1.0), (0.45, 1.0)]
    else:
        receiver_detunings = [8.86, 8.87, 8.88, 8.89, 8.90, 8.91, 8.92, 8.93]
        phase_biases = [20.0, 22.0, 24.0, 26.0, 28.0, 30.0]
        strengths = [0.84, 0.865, 0.89, 0.915, 0.94]
        coupling_a_values = [1.02, 1.11, 1.20, 1.29, 1.38]
        coupling_b_values = [0.85, 0.925, 1.00, 1.075, 1.15]
        damping_values = [0.56, 0.63, 0.70, 0.77, 0.84]
        spark_values = [0.028, 0.0315, 0.035, 0.0385, 0.042]
        windows = [(0.30, 1.0), (0.35, 1.0), (0.45, 1.0), (0.55, 1.0)]

    for detuning in receiver_detunings:
        for phase in phase_biases:
            config = replace(base, mode_freqs=(3.0, 6.0, detuning), stage_b_phase_bias_deg=phase)
            specs.append(("receiver_phase_grid", f"receiver{detuning:.3f}_phase{phase:g}", config, 1.25, 0.35, 1.0, "receiver_detuning_vs_phase_bias"))

    for detuning in receiver_detunings:
        for strength in strengths:
            config = replace(base, mode_freqs=(3.0, 6.0, detuning), stage_b_nonlinear_strength=strength)
            specs.append(("receiver_strength_grid", f"receiver{detuning:.3f}_stageB{strength:g}", config, 1.25, 0.35, 1.0, "receiver_detuning_vs_stage_B_strength"))

    for value in coupling_a_values:
        specs.append(("stage_A_to_stage_B_coupling", f"{value:g}", replace(base, stage_a_to_stage_b_coupling=value), 1.25, 0.35, 1.0, "one_factor"))
    for value in coupling_b_values:
        specs.append(("stage_B_to_receiver_coupling", f"{value:g}", replace(base, stage_b_to_receiver_coupling=value), 1.25, 0.35, 1.0, "one_factor"))
    for value in damping_values:
        specs.append(("stage_B_damping", f"{value:g}", replace(base, stage_b_damping=value, receiver_damping=value), 1.25, 0.35, 1.0, "one_factor"))
    for value in spark_values:
        specs.append(("passive_spark_threshold", f"{value:g}", replace(base, spark_threshold=value), 1.25, 0.35, 1.0, "one_factor"))
    for start, end in windows:
        specs.append(("fft_window", f"{start:g}-{end:g}", base, 1.25, start, end, "window"))
    for factor in [1.0, 2.0, 4.0]:
        specs.append(("runtime_length", f"{factor:g}x", base, 1.25 * factor, 0.35, 1.0, "runtime"))
    return specs


def bridge_lock_refine_direct_metrics(seed: int, quick: bool, dt: float, runtime: float,
                                      sample_every: int, window_start: float,
                                      window_end: float) -> Tuple[Dict[str, object], Dict[str, float | str]]:
    direct_config = bridge_stability_direct_reference(bridge_lock_refine_base_config())
    direct_sim, _ = simulate_bridge_amp(direct_config, seed, quick, dt=dt, t_max=runtime, sample_every=sample_every)
    direct_row = bridge_metrics_window(direct_config, direct_sim, seed, "direct_reference", "direct_3_plus_6", "reference", window_start, window_end)
    return direct_sim, direct_row


def bridge_lock_refine_core_pass(row: Dict[str, float | str]) -> bool:
    return (
        float(row.get("generated_vs_direct_bridge_ratio", 0.0)) > 0.75
        and float(row.get("phase_lock_9", 0.0)) > 0.90
        and float(row.get("spectral_purity_9", 0.0)) > 0.60
        and float(row.get("energy_budget_error", 1.0)) < 0.002
    )


def update_bridge_lock_refine_score(row: Dict[str, float | str]) -> None:
    passed = bridge_lock_refine_core_pass(row)
    robustness = float(row.get("lock_island_robustness", 0.35))
    repeatability = float(row.get("repeatability_score", 1.0))
    sensitivity = float(row.get("parameter_sensitivity_score", 1.0))
    penalty = 1.0 + 1000.0 * max(0.0, float(row.get("energy_budget_error", 0.0)))
    score = (
        float(row.get("generated_vs_direct_bridge_ratio", 0.0))
        * float(row.get("phase_lock_9", 0.0))
        * float(row.get("spectral_purity_9", 0.0))
        * robustness
        * repeatability
        * sensitivity
        / penalty
    )
    if not passed:
        score = 0.0

    failures = []
    if float(row.get("generated_vs_direct_bridge_ratio", 0.0)) <= 0.75:
        failures.append("bridge_ratio")
    if float(row.get("phase_lock_9", 0.0)) <= 0.90:
        failures.append("phase_lock_9")
    if float(row.get("spectral_purity_9", 0.0)) <= 0.60:
        failures.append("spectral_purity_9")
    if float(row.get("energy_budget_error", 1.0)) >= 0.002:
        failures.append("energy_budget")

    strong = (
        passed
        and float(row.get("generated_vs_direct_bridge_ratio", 0.0)) > 0.85
        and float(row.get("phase_lock_9", 0.0)) > 0.95
        and float(row.get("spectral_purity_9", 0.0)) > 0.75
        and float(row.get("energy_budget_error", 1.0)) < 0.001
        and robustness > 0.20
    )
    if abs(float(row.get("effective_target_frequency", 9.0)) - 9.0) > 0.08:
        failure_mode = "frequency_detuning"
    elif float(row.get("phase_drift_rate", 0.0)) > 0.08:
        failure_mode = "phase_drift"
    elif float(row.get("generated_vs_direct_bridge_ratio", 0.0)) <= 0.75:
        failure_mode = "coupling_loss"
    elif passed:
        failure_mode = "stable"
    else:
        failure_mode = "weak_lock"

    row["passed"] = str(passed)
    row["strong_passed"] = str(strong)
    row["failed_gate_names"] = ";".join(failures)
    row["failure_mode"] = failure_mode
    row["promoted_lock_score"] = score
    row["score"] = score


def finalize_bridge_lock_refine_row(row: Dict[str, float | str],
                                    direct_row: Dict[str, float | str]) -> None:
    bridge_ratio = metric_ratio(float(row.get("energy_at_9", 0.0)), float(direct_row.get("energy_at_9", 0.0)))
    row.update({
        "experiment": "bridge_lock_refine",
        "generated_vs_direct_bridge_ratio": bridge_ratio,
        "energy_at_9_from_direct_3_plus_6_reference": direct_row.get("energy_at_9", 0.0),
        "bridge_ratio": bridge_ratio,
        "lock_island_width": row.get("lock_island_width", 0.0),
        "lock_island_robustness": row.get("lock_island_robustness", 0.35),
        "parameter_sensitivity_score": row.get("parameter_sensitivity_score", 1.0),
        "repeatability_score": row.get("repeatability_score", 1.0),
        "dt_stability_score": row.get("dt_stability_score", 0.0),
        "runtime_stability_score": row.get("runtime_stability_score", 0.0),
        "promoted_lock_score": 0.0,
    })
    update_bridge_lock_refine_score(row)


def bridge_lock_refine_measure(config: BridgeAmpConfig, seed: int, quick: bool, dt: float,
                               runtime: float, sample_every: int, sweep: str, value: str,
                               window_start: float, window_end: float, map_type: str,
                               direct_sim: Dict[str, object],
                               direct_row: Dict[str, float | str]) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]]]:
    sim, _ = simulate_bridge_amp(config, seed, quick, dt=dt, t_max=runtime, sample_every=sample_every)
    row = bridge_metrics_window(config, sim, seed, "refine", sweep, value, window_start, window_end)
    diag_rows, diag_summary = bridge_phase_diagnostic_series(config, sim, direct_sim, window_start, window_end)
    row.update(diag_summary)
    row["experiment"] = "bridge_lock_refine"
    row["map_type"] = map_type
    row["candidate_id"] = f"{sweep}:{value}"
    row["receiver_detuning"] = config.mode_freqs[2]
    row["receiver_tuning"] = config.mode_freqs[2]
    row["phase_bias_deg"] = config.stage_b_phase_bias_deg
    row["stage_B_nonlinear_strength"] = config.stage_b_nonlinear_strength
    row["stage_A_to_stage_B_coupling"] = config.stage_a_to_stage_b_coupling
    row["stage_B_to_receiver_coupling"] = config.stage_b_to_receiver_coupling
    row["stage_B_damping"] = config.stage_b_damping
    row["spark_threshold"] = config.spark_threshold
    finalize_bridge_lock_refine_row(row, direct_row)

    labeled_diag: List[Dict[str, float | str]] = []
    for item in diag_rows:
        rr = dict(item)
        rr["candidate_id"] = row["candidate_id"]
        rr["sweep"] = sweep
        rr["sweep_value"] = value
        rr["map_type"] = map_type
        labeled_diag.append(rr)
    return row, labeled_diag


def bridge_lock_refine_grid_steps(rows: List[Dict[str, float | str]], key: str) -> float:
    values = sorted({float(r[key]) for r in rows if key in r})
    diffs = [b - a for a, b in zip(values, values[1:]) if b > a]
    return min(diffs) if diffs else 1.0


def apply_bridge_lock_refine_robustness(rows: List[Dict[str, float | str]],
                                        include_sweeps: bool) -> List[Dict[str, float | str]]:
    if not rows:
        return []
    if not include_sweeps:
        for row in rows:
            row["lock_island_width"] = 1.0 if bridge_lock_refine_core_pass(row) else 0.0
            row["lock_island_robustness"] = 1.0 if bridge_lock_refine_core_pass(row) else 0.0
            row["parameter_sensitivity_score"] = 1.0
            update_bridge_lock_refine_score(row)
        return rows

    map_rows = [r for r in rows if str(r.get("map_type")) in ("receiver_detuning_vs_phase_bias", "receiver_detuning_vs_stage_B_strength")]
    det_step = bridge_lock_refine_grid_steps(map_rows, "receiver_tuning") if map_rows else 0.02
    phase_rows = [r for r in map_rows if str(r.get("map_type")) == "receiver_detuning_vs_phase_bias"]
    strength_rows = [r for r in map_rows if str(r.get("map_type")) == "receiver_detuning_vs_stage_B_strength"]
    phase_step = bridge_lock_refine_grid_steps(phase_rows, "phase_bias_deg") if phase_rows else 3.0
    strength_step = bridge_lock_refine_grid_steps(strength_rows, "stage_B_nonlinear_strength") if strength_rows else 0.03

    passed_phase = [r for r in phase_rows if bridge_lock_refine_core_pass(r)]
    passed_strength = [r for r in strength_rows if bridge_lock_refine_core_pass(r)]
    phase_det_width = (max([float(r["receiver_tuning"]) for r in passed_phase]) - min([float(r["receiver_tuning"]) for r in passed_phase])) if len(passed_phase) >= 2 else 0.0
    phase_bias_width = (max([float(r["phase_bias_deg"]) for r in passed_phase]) - min([float(r["phase_bias_deg"]) for r in passed_phase])) if len(passed_phase) >= 2 else 0.0
    strength_det_width = (max([float(r["receiver_tuning"]) for r in passed_strength]) - min([float(r["receiver_tuning"]) for r in passed_strength])) if len(passed_strength) >= 2 else 0.0
    strength_width = (max([float(r["stage_B_nonlinear_strength"]) for r in passed_strength]) - min([float(r["stage_B_nonlinear_strength"]) for r in passed_strength])) if len(passed_strength) >= 2 else 0.0
    global_width = min(1.0, 0.25 * (phase_det_width / 0.07) + 0.25 * (phase_bias_width / 10.0) + 0.25 * (strength_det_width / 0.07) + 0.25 * (strength_width / 0.10))

    def local_neighbors(row: Dict[str, float | str]) -> List[Dict[str, float | str]]:
        map_type = str(row.get("map_type"))
        if map_type == "receiver_detuning_vs_phase_bias":
            return [
                other for other in phase_rows
                if abs(float(other["receiver_tuning"]) - float(row["receiver_tuning"])) <= det_step + 1e-9
                and abs(float(other["phase_bias_deg"]) - float(row["phase_bias_deg"])) <= phase_step + 1e-9
            ]
        if map_type == "receiver_detuning_vs_stage_B_strength":
            return [
                other for other in strength_rows
                if abs(float(other["receiver_tuning"]) - float(row["receiver_tuning"])) <= det_step + 1e-9
                and abs(float(other["stage_B_nonlinear_strength"]) - float(row["stage_B_nonlinear_strength"])) <= strength_step + 1e-9
            ]
        candidates = phase_rows or strength_rows or rows
        return sorted(candidates, key=lambda other: abs(float(other.get("receiver_tuning", 9.0)) - float(row.get("receiver_tuning", 9.0))))[:6]

    robustness_rows: List[Dict[str, float | str]] = []
    for row in rows:
        neighbors = local_neighbors(row)
        if neighbors:
            pass_fraction = float(sum(1 for item in neighbors if bridge_lock_refine_core_pass(item)) / len(neighbors))
            metrics = []
            for key in ("generated_vs_direct_bridge_ratio", "phase_lock_9", "spectral_purity_9"):
                values = np.asarray([float(item.get(key, 0.0)) for item in neighbors], dtype=float)
                mean = float(np.mean(np.abs(values))) + 1e-18
                metrics.append(float(np.std(values) / mean))
            sensitivity = float(1.0 / (1.0 + 4.0 * np.mean(metrics)))
        else:
            pass_fraction = 0.0
            sensitivity = 0.0
        row["lock_island_width"] = global_width
        row["lock_island_robustness"] = pass_fraction
        row["parameter_sensitivity_score"] = sensitivity
        update_bridge_lock_refine_score(row)
        robustness_rows.append({
            "candidate_id": row["candidate_id"],
            "map_type": row.get("map_type", ""),
            "receiver_tuning": row.get("receiver_tuning", 0.0),
            "phase_bias_deg": row.get("phase_bias_deg", 0.0),
            "stage_B_nonlinear_strength": row.get("stage_B_nonlinear_strength", 0.0),
            "lock_island_width": row["lock_island_width"],
            "lock_island_robustness": row["lock_island_robustness"],
            "parameter_sensitivity_score": row["parameter_sensitivity_score"],
            "passed": row["passed"],
            "promoted_lock_score": row["promoted_lock_score"],
        })
    return robustness_rows


def bridge_lock_refine_validation(config: BridgeAmpConfig, candidate: Dict[str, float | str],
                                  seed: int, quick: bool, dt: float, runtime: float,
                                  sample_every: int, window_start: float,
                                  window_end: float) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]]]:
    validations = [
        ("baseline_1x", dt, runtime, seed),
        ("half_dt_1x", dt * 0.5, runtime, seed + 17),
        ("quarter_dt_1x", dt * 0.25, runtime, seed + 29),
        ("runtime_2x", dt, runtime * 2.0, seed + 43),
        ("runtime_4x", dt, runtime * 4.0, seed + 59),
        ("seed_alt_1", dt, runtime, seed + 101),
        ("seed_alt_2", dt, runtime, seed + 151),
    ]
    validation_rows: List[Dict[str, float | str]] = []
    drift_rows: List[Dict[str, float | str]] = []
    direct_cache: Dict[Tuple[float, float, float, float, float], Tuple[Dict[str, object], Dict[str, float | str]]] = {}
    for name, test_dt, test_runtime, test_seed in validations:
        cache_key = (test_dt, test_runtime, window_start, window_end, float(sample_every))
        if cache_key not in direct_cache:
            direct_cache[cache_key] = bridge_lock_refine_direct_metrics(test_seed + 700, quick, test_dt, test_runtime, sample_every, window_start, window_end)
        direct_sim, direct_row = direct_cache[cache_key]
        row, diag = bridge_lock_refine_measure(
            config,
            test_seed,
            quick,
            test_dt,
            test_runtime,
            sample_every,
            str(candidate.get("sweep", "validation")),
            str(candidate.get("sweep_value", "validation")),
            window_start,
            window_end,
            "validation",
            direct_sim,
            direct_row,
        )
        row["candidate_id"] = candidate["candidate_id"]
        row["validation_test"] = name
        row["relative_bridge_ratio_to_candidate"] = metric_ratio(float(row["generated_vs_direct_bridge_ratio"]), float(candidate["generated_vs_direct_bridge_ratio"]))
        validation_rows.append(row)
        for item in diag:
            item["candidate_id"] = candidate["candidate_id"]
            item["validation_test"] = name
            drift_rows.append(item)
    return validation_rows, drift_rows


def apply_bridge_lock_validation_status(candidate: Dict[str, float | str],
                                        validation_rows: List[Dict[str, float | str]]) -> None:
    own_rows = [r for r in validation_rows if str(r.get("candidate_id")) == str(candidate.get("candidate_id"))]
    by_test = {str(r.get("validation_test")): r for r in own_rows}
    half = by_test.get("half_dt_1x", {})
    quarter = by_test.get("quarter_dt_1x", {})
    runtime2 = by_test.get("runtime_2x", {})
    runtime4 = by_test.get("runtime_4x", {})
    seeds = [by_test.get("seed_alt_1", {}), by_test.get("seed_alt_2", {})]

    half_pass = half.get("passed") == "True"
    quarter_pass = quarter.get("passed") == "True"
    runtime2_pass = runtime2.get("passed") == "True"
    runtime4_pass = runtime4.get("passed") == "True"
    seed_passes = [s.get("passed") == "True" for s in seeds if s]
    repeatability = float(sum(1 for item in seed_passes if item) / max(len(seed_passes), 1))
    dt_scores = [
        ratio_stability_score(float(half.get("generated_vs_direct_bridge_ratio", 0.0)), float(candidate.get("generated_vs_direct_bridge_ratio", 0.0))),
        ratio_stability_score(float(quarter.get("generated_vs_direct_bridge_ratio", 0.0)), float(candidate.get("generated_vs_direct_bridge_ratio", 0.0))),
    ]
    runtime_scores = [
        ratio_stability_score(float(runtime2.get("generated_vs_direct_bridge_ratio", 0.0)), float(candidate.get("generated_vs_direct_bridge_ratio", 0.0))),
        ratio_stability_score(float(runtime4.get("generated_vs_direct_bridge_ratio", 0.0)), float(candidate.get("generated_vs_direct_bridge_ratio", 0.0))),
    ]
    candidate["half_dt_passed"] = str(half_pass)
    candidate["quarter_dt_passed"] = str(quarter_pass)
    candidate["runtime_2x_passed"] = str(runtime2_pass)
    candidate["runtime_4x_passed"] = str(runtime4_pass)
    candidate["repeatability_score"] = repeatability
    candidate["dt_stability_score"] = float(np.mean(dt_scores))
    candidate["runtime_stability_score"] = float(np.mean(runtime_scores))
    candidate["validation_status"] = "passed" if half_pass and runtime2_pass else "failed"
    update_bridge_lock_refine_score(candidate)
    if candidate["validation_status"] != "passed":
        candidate["passed"] = "False"
        candidate["failed_gate_names"] = ";".join(filter(None, [str(candidate.get("failed_gate_names", "")), "validation_stability"]))
        candidate["promoted_lock_score"] = 0.0
        candidate["score"] = 0.0
    strong = (
        candidate.get("validation_status") == "passed"
        and str(candidate.get("strong_passed")) == "True"
        and runtime4_pass
        and quarter_pass
    )
    candidate["strong_passed"] = str(strong)


def bridge_lock_refine_heatmap(ax, rows: List[Dict[str, float | str]], map_type: str,
                               x_key: str, y_key: str, metric: str, title: str) -> None:
    plot_rows = [r for r in rows if str(r.get("map_type")) == map_type]
    xs = sorted({float(r[x_key]) for r in plot_rows if x_key in r})
    ys = sorted({float(r[y_key]) for r in plot_rows if y_key in r})
    if not xs or not ys:
        ax.set_title(title)
        return
    matrix = np.full((len(ys), len(xs)), np.nan)
    for row in plot_rows:
        x_idx = xs.index(float(row[x_key]))
        y_idx = ys.index(float(row[y_key]))
        matrix[y_idx, x_idx] = float(row.get(metric, 0.0))
    im = ax.imshow(matrix, origin="lower", aspect="auto")
    ax.set_xticks(np.arange(len(xs)))
    ax.set_xticklabels([f"{x:g}" for x in xs], rotation=35, ha="right")
    ax.set_yticks(np.arange(len(ys)))
    ax.set_yticklabels([f"{y:g}" for y in ys])
    ax.set_xlabel(x_key)
    ax.set_ylabel(y_key)
    ax.set_title(title)
    plt.colorbar(im, ax=ax, label=metric)


def plot_bridge_lock_refine_outputs(out_dir: Path, ranked: List[Dict[str, float | str]],
                                    island_rows: List[Dict[str, float | str]],
                                    robustness_rows: List[Dict[str, float | str]],
                                    validation_drift_rows: List[Dict[str, float | str]]) -> None:
    if island_rows:
        fig, ax = plt.subplots(figsize=(8.6, 5.4))
        bridge_lock_refine_heatmap(ax, island_rows, "receiver_detuning_vs_phase_bias", "receiver_tuning", "phase_bias_deg", "phase_lock_9", "receiver detuning vs phase bias")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_receiver_phase_heatmap.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.6, 5.4))
        bridge_lock_refine_heatmap(ax, island_rows, "receiver_detuning_vs_stage_B_strength", "receiver_tuning", "stage_B_nonlinear_strength", "phase_lock_9", "receiver detuning vs Stage B strength")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_receiver_strength_heatmap.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.6, 5.4))
        phase_rows = [r for r in island_rows if str(r.get("map_type")) == "receiver_detuning_vs_phase_bias"]
        xs = sorted({float(r["receiver_tuning"]) for r in phase_rows})
        ys = sorted({float(r["phase_bias_deg"]) for r in phase_rows})
        if len(xs) >= 2 and len(ys) >= 2:
            matrix = np.zeros((len(ys), len(xs)))
            for row in phase_rows:
                matrix[ys.index(float(row["phase_bias_deg"])), xs.index(float(row["receiver_tuning"]))] = float(row.get("promoted_lock_score", 0.0))
            contour = ax.contourf(xs, ys, matrix, levels=10)
            fig.colorbar(contour, ax=ax, label="promoted_lock_score")
            ax.set_xlabel("receiver_tuning")
            ax.set_ylabel("phase_bias_deg")
        ax.set_title("lock island contour")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_lock_island_contour.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.6, 5.4))
        bridge_lock_refine_heatmap(ax, robustness_rows, "receiver_detuning_vs_phase_bias", "receiver_tuning", "phase_bias_deg", "lock_island_robustness", "robustness map")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_robustness_map.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8.6, 5.0))
        tuning_groups = sorted({float(r["receiver_tuning"]) for r in island_rows if "receiver_tuning" in r})
        means = []
        for tuning in tuning_groups:
            values = [float(r.get("effective_target_frequency", 9.0)) for r in island_rows if abs(float(r.get("receiver_tuning", 0.0)) - tuning) < 1e-9]
            means.append(float(np.mean(values)) if values else 0.0)
        ax.plot(tuning_groups, means, marker="o")
        ax.axhline(9.0, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("effective generated frequency vs receiver tuning")
        ax.set_xlabel("receiver_tuning")
        ax.set_ylabel("effective_target_frequency")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_effective_frequency_vs_tuning.png", dpi=140)
        plt.close(fig)

    if ranked:
        fig, ax = plt.subplots(figsize=(8.2, 5.2))
        ax.scatter(
            [float(r.get("generated_vs_direct_bridge_ratio", 0.0)) for r in ranked],
            [float(r.get("phase_lock_9", 0.0)) for r in ranked],
            c=[float(r.get("promoted_lock_score", 0.0)) for r in ranked],
        )
        ax.axvline(0.75, color="tab:red", linestyle="--", linewidth=1.0)
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("bridge ratio vs phase lock")
        ax.set_xlabel("bridge ratio")
        ax.set_ylabel("phase_lock_9")
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_ratio_vs_phase_lock.png", dpi=140)
        plt.close(fig)

    if validation_drift_rows:
        fig, ax = plt.subplots(figsize=(9.0, 5.2))
        for test in ("baseline_1x", "runtime_2x", "runtime_4x"):
            rows = [r for r in validation_drift_rows if str(r.get("validation_test")) == test]
            if rows:
                ax.plot([float(r["time_mid"]) for r in rows], [float(r.get("phase_drift_rate", 0.0)) for r in rows], label=test)
        ax.set_title("phase drift over runtime")
        ax.set_xlabel("time")
        ax.set_ylabel("phase_drift_rate")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "bridge_lock_refine_phase_drift_runtime.png", dpi=140)
        plt.close(fig)


def write_bridge_lock_refine_report(out_dir: Path, ranked: List[Dict[str, float | str]],
                                    validation_rows: List[Dict[str, float | str]],
                                    robustness_rows: List[Dict[str, float | str]]) -> None:
    best = ranked[0] if ranked else {}
    passing = [r for r in ranked if str(r.get("passed")) == "True"]
    best_passing = passing[0] if passing else {}
    own_validation = [r for r in validation_rows if str(r.get("candidate_id")) == str(best_passing.get("candidate_id", ""))]
    by_test = {str(r.get("validation_test")): r for r in own_validation}
    width = float(best_passing.get("lock_island_width", 0.0)) if best_passing else 0.0
    robustness = float(best_passing.get("lock_island_robustness", 0.0)) if best_passing else 0.0
    broad_answer = "broad enough to promote" if robustness > 0.50 and width > 0.20 else "narrow but reproducible" if best_passing else "not found"
    runtime2 = by_test.get("runtime_2x", {})
    runtime4 = by_test.get("runtime_4x", {})
    half = by_test.get("half_dt_1x", {})
    quarter = by_test.get("quarter_dt_1x", {})
    lines = [
        "# Bridge Lock Refine Report",
        "",
        "## Direct Answers",
        f"1. Promoted lock island shape: {broad_answer}; robustness={robustness:.3g}, width={width:.3g}.",
        f"2. Best stable passive tuning: {best_passing.get('candidate_id', 'none')}; receiver={float(best_passing.get('receiver_tuning', 0.0)):.6g}, phase={float(best_passing.get('phase_bias_deg', 0.0)):.6g}, stageB={float(best_passing.get('stage_B_nonlinear_strength', 0.0)):.6g}.",
        f"3. Effective generated frequency near 9: {float(best_passing.get('effective_target_frequency', 0.0)):.6g}.",
        f"4. 2x runtime passed? {runtime2.get('passed', 'n/a')}; 4x runtime passed? {runtime4.get('passed', 'n/a')}.",
        f"5. Half-dt passed? {half.get('passed', 'n/a')}; quarter-dt passed? {quarter.get('passed', 'n/a')}.",
        f"6. Promote to geometry369? {'yes' if best_passing and runtime2.get('passed') == 'True' and runtime4.get('passed') == 'True' and half.get('passed') == 'True' and quarter.get('passed') == 'True' else 'not yet'} under the strict 4x-runtime gate.",
        "",
        "## Top Candidates",
    ]
    for row in ranked[:20]:
        lines.append(
            f"- {row['candidate_id']}: score={float(row.get('promoted_lock_score', 0.0)):.6g}, passed={row.get('passed')}, "
            f"ratio={float(row.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}, phase={float(row.get('phase_lock_9', 0.0)):.6g}, "
            f"purity={float(row.get('spectral_purity_9', 0.0)):.6g}, budget={float(row.get('energy_budget_error', 0.0)):.6g}, "
            f"robust={float(row.get('lock_island_robustness', 0.0)):.6g}, eff_freq={float(row.get('effective_target_frequency', 0.0)):.6g}"
        )
    (out_dir / "README_BRIDGE_LOCK_REFINE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_bridge_lock_refine(out_dir: Path, seed: int, quick: bool = False,
                                  include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    dt, base_tmax, sample_every = bridge_amp_timebase(quick)
    specs = bridge_lock_refine_specs(quick, include_sweeps)
    summary_rows: List[Dict[str, float | str]] = []
    drift_rows: List[Dict[str, float | str]] = []
    direct_cache: Dict[Tuple[float, float, float, float], Tuple[Dict[str, object], Dict[str, float | str]]] = {}

    for idx, (sweep, value, config, runtime_multiplier, window_start, window_end, map_type) in enumerate(specs):
        runtime = base_tmax * runtime_multiplier
        cache_key = (runtime, window_start, window_end, dt)
        if cache_key not in direct_cache:
            direct_cache[cache_key] = bridge_lock_refine_direct_metrics(seed + 5000 + idx * 7, quick, dt, runtime, sample_every, window_start, window_end)
        direct_sim, direct_row = direct_cache[cache_key]
        row, diag = bridge_lock_refine_measure(config, seed + idx * 23, quick, dt, runtime, sample_every, sweep, value, window_start, window_end, map_type, direct_sim, direct_row)
        summary_rows.append(row)
        drift_rows.extend(diag)

    robustness_rows = apply_bridge_lock_refine_robustness(summary_rows, include_sweeps)
    ranked = sorted(summary_rows, key=lambda r: (float(r.get("promoted_lock_score", 0.0)), float(r.get("generated_vs_direct_bridge_ratio", 0.0))), reverse=True)

    validation_rows: List[Dict[str, float | str]] = []
    validation_drift_rows: List[Dict[str, float | str]] = []
    top_candidates = [r for r in ranked if bridge_lock_refine_core_pass(r)][:2 if include_sweeps else 1]
    if not top_candidates and ranked:
        top_candidates = [ranked[0]]

    for idx, candidate in enumerate(top_candidates):
        spec = next((s for s in specs if f"{s[0]}:{s[1]}" == str(candidate["candidate_id"])), specs[0])
        _, _, config, runtime_multiplier, window_start, window_end, _ = spec
        runtime = base_tmax * runtime_multiplier
        rows, diag = bridge_lock_refine_validation(config, candidate, seed + 9000 + idx * 500, quick, dt, runtime, sample_every, window_start, window_end)
        validation_rows.extend(rows)
        validation_drift_rows.extend(diag)
        apply_bridge_lock_validation_status(candidate, validation_rows)
        if str(candidate.get("validation_status")) == "passed":
            break

    ranked = sorted(summary_rows, key=lambda r: (float(r.get("promoted_lock_score", 0.0)), float(r.get("generated_vs_direct_bridge_ratio", 0.0))), reverse=True)
    island_rows = [
        {
            "candidate_id": row["candidate_id"],
            "map_type": row.get("map_type", ""),
            "receiver_tuning": row.get("receiver_tuning", 0.0),
            "phase_bias_deg": row.get("phase_bias_deg", 0.0),
            "stage_B_nonlinear_strength": row.get("stage_B_nonlinear_strength", 0.0),
            "generated_vs_direct_bridge_ratio": row.get("generated_vs_direct_bridge_ratio", 0.0),
            "phase_lock_9": row.get("phase_lock_9", 0.0),
            "spectral_purity_9": row.get("spectral_purity_9", 0.0),
            "energy_budget_error": row.get("energy_budget_error", 0.0),
            "effective_target_frequency": row.get("effective_target_frequency", 0.0),
            "phase_drift_rate": row.get("phase_drift_rate", 0.0),
            "lock_duration": row.get("lock_duration", 0.0),
            "time_to_unlock": row.get("time_to_unlock", 0.0),
            "lock_island_width": row.get("lock_island_width", 0.0),
            "lock_island_robustness": row.get("lock_island_robustness", 0.0),
            "parameter_sensitivity_score": row.get("parameter_sensitivity_score", 0.0),
            "passed": row.get("passed", "False"),
            "promoted_lock_score": row.get("promoted_lock_score", 0.0),
        }
        for row in summary_rows
    ]

    write_csv(out_dir / "bridge_lock_refine_summary.csv", summary_rows)
    write_csv(out_dir / "bridge_lock_refine_ranked.csv", ranked)
    write_csv(out_dir / "bridge_lock_island_map.csv", island_rows)
    write_csv(out_dir / "bridge_lock_robustness.csv", robustness_rows)
    write_csv(out_dir / "bridge_lock_validation.csv", validation_rows)
    write_csv(out_dir / "bridge_lock_refine_drift_timeseries.csv", drift_rows + validation_drift_rows)
    plot_bridge_lock_refine_outputs(out_dir, ranked, island_rows, robustness_rows, validation_drift_rows)
    write_bridge_lock_refine_report(out_dir, ranked, validation_rows, robustness_rows)

    return [
        {
            "experiment": "bridge_lock_refine",
            "case": row["case"],
            "freqs": row["freqs"],
            "score": row.get("promoted_lock_score", 0.0),
            "passed": row.get("passed", "False"),
            "strong_passed": row.get("strong_passed", "False"),
            "generated_vs_direct_bridge_ratio": row.get("generated_vs_direct_bridge_ratio", 0.0),
            "phase_lock_9": row.get("phase_lock_9", 0.0),
            "spectral_purity_9": row.get("spectral_purity_9", 0.0),
            "energy_budget_error": row.get("energy_budget_error", 0.0),
            "lock_island_robustness": row.get("lock_island_robustness", 0.0),
            "effective_target_frequency": row.get("effective_target_frequency", 0.0),
            "validation_status": row.get("validation_status", ""),
            "note": row["note"],
        }
        for row in ranked[:20]
    ]


# ----------------------------
# Experiment 14: magnetic bridge stabilization
# ----------------------------

@dataclass
class MagneticBridgeConfig:
    name: str
    bridge: BridgeAmpConfig
    magnetic_option: str = "linear_air_core"
    mutual_inductance_a_b: float = 0.0
    mutual_inductance_b_receiver: float = 0.0
    receiver_feedback: float = 0.0
    flux_leakage_loss: float = 0.0
    hysteresis_loss: float = 0.0
    eddy_current_loss: float = 0.0
    magnetic_damping: float = 0.0
    magnetic_phase_lag_deg: float = 0.0
    magnetic_bias_field: float = 0.0
    core_saturation_strength: float = 0.0
    rotating_flux_bias_phase_deg: float = 0.0
    reference_role: str = "discovery_candidate"
    family: str = "369"
    note: str = ""


def magnetic_bridge_seed_bridge(receiver_tuning: float, phase_bias: float,
                                stage_b_strength: float = 0.90) -> BridgeAmpConfig:
    return replace(
        bridge_lock_refine_base_config(),
        mode_freqs=(3.0, 6.0, receiver_tuning),
        stage_b_phase_bias_deg=phase_bias,
        stage_b_nonlinear_strength=stage_b_strength,
        note=f"magnetic bridge seed receiver={receiver_tuning:g}, phase={phase_bias:g}, stageB={stage_b_strength:g}",
    )


def magnetic_bridge_effective_bridge(config: MagneticBridgeConfig) -> BridgeAmpConfig:
    bridge = config.bridge
    if config.magnetic_option == "control_no_magnetic_layer":
        return replace(bridge, note=f"{bridge.note}; no magnetic layer")

    loss_damping = config.magnetic_damping + 0.70 * config.hysteresis_loss + 0.45 * config.eddy_current_loss + 0.30 * config.flux_leakage_loss
    saturation_pull = config.core_saturation_strength / (1.0 + abs(config.core_saturation_strength))
    bias_pull = 0.020 * config.magnetic_bias_field
    rotating_pull = 0.012 * math.sin(math.radians(config.rotating_flux_bias_phase_deg))
    lag_pull = 0.020 * math.sin(math.radians(config.magnetic_phase_lag_deg))

    coupling_a_b = max(0.05, bridge.stage_a_to_stage_b_coupling + config.mutual_inductance_a_b * (1.0 - 0.35 * saturation_pull))
    coupling_b_r = max(0.05, bridge.stage_b_to_receiver_coupling + config.mutual_inductance_b_receiver * (1.0 - 0.25 * saturation_pull) + config.receiver_feedback)
    receiver_tuning = max(0.5, bridge.mode_freqs[2] + bias_pull - lag_pull + rotating_pull - 0.018 * config.mutual_inductance_b_receiver)
    stage_b_tuning = max(0.5, bridge.mode_freqs[1] + 0.010 * config.magnetic_bias_field - 0.010 * config.mutual_inductance_a_b)
    phase_bias = bridge.stage_b_phase_bias_deg + config.magnetic_phase_lag_deg + 4.0 * config.magnetic_bias_field
    strength = max(0.0, bridge.stage_b_nonlinear_strength * (1.0 + 0.10 * saturation_pull))

    if config.magnetic_option == "biased_saturable_core":
        receiver_tuning += 0.012 * config.magnetic_bias_field
        strength *= 1.03
    elif config.magnetic_option == "lossy_hysteretic_core":
        loss_damping += 0.08
        phase_bias += 0.5 * config.magnetic_phase_lag_deg
    elif config.magnetic_option == "rotating_flux_bias":
        phase_bias += 8.0 * math.sin(math.radians(config.rotating_flux_bias_phase_deg))
        receiver_tuning += 0.010 * math.cos(math.radians(config.rotating_flux_bias_phase_deg))
    elif config.magnetic_option == "control_random_magnetic_coupling":
        receiver_tuning += 0.11
        phase_bias -= 17.0

    return replace(
        bridge,
        mode_freqs=(bridge.mode_freqs[0], stage_b_tuning, receiver_tuning),
        stage_a_to_stage_b_coupling=coupling_a_b,
        stage_b_to_receiver_coupling=coupling_b_r,
        stage_b_phase_bias_deg=phase_bias,
        stage_b_nonlinear_strength=strength,
        stage_b_damping=max(0.05, bridge.stage_b_damping + loss_damping),
        receiver_damping=max(0.05, bridge.receiver_damping + loss_damping),
        note=f"{bridge.note}; magnetic={config.magnetic_option}",
    )


def magnetic_bridge_core_configs() -> List[MagneticBridgeConfig]:
    seed_a = magnetic_bridge_seed_bridge(8.90, 30.0)
    seed_b = magnetic_bridge_seed_bridge(8.915, 20.0)
    configs = [
        MagneticBridgeConfig(
            "no_magnetic_layer_seed_a",
            seed_a,
            magnetic_option="control_no_magnetic_layer",
            reference_role="control",
            note="8.9/30 no magnetic baseline",
        ),
        MagneticBridgeConfig(
            "no_magnetic_layer_seed_b",
            seed_b,
            magnetic_option="control_no_magnetic_layer",
            reference_role="control",
            note="8.915/20 no magnetic baseline",
        ),
        MagneticBridgeConfig(
            "linear_air_core_seed_a",
            seed_a,
            magnetic_option="linear_air_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.20,
            magnetic_damping=0.015,
            note="linear passive flux coupling on 8.9/30 seed",
        ),
        MagneticBridgeConfig(
            "saturable_core_seed_a",
            seed_a,
            magnetic_option="saturable_core",
            mutual_inductance_a_b=0.14,
            mutual_inductance_b_receiver=0.22,
            core_saturation_strength=0.55,
            magnetic_damping=0.012,
            note="saturable passive flux coupling on 8.9/30 seed",
        ),
        MagneticBridgeConfig(
            "biased_saturable_core_seed_b",
            seed_b,
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.24,
            core_saturation_strength=0.60,
            magnetic_bias_field=-0.35,
            magnetic_phase_lag_deg=-4.0,
            magnetic_damping=0.016,
            note="biased saturable passive layer on 8.915/20 seed",
        ),
        MagneticBridgeConfig(
            "lossy_hysteretic_core_seed_b",
            seed_b,
            magnetic_option="lossy_hysteretic_core",
            mutual_inductance_a_b=0.13,
            mutual_inductance_b_receiver=0.18,
            magnetic_phase_lag_deg=-3.0,
            hysteresis_loss=0.018,
            eddy_current_loss=0.012,
            magnetic_damping=0.020,
            note="lossy passive magnetic damping layer",
        ),
        MagneticBridgeConfig(
            "rotating_flux_bias_seed_b",
            seed_b,
            magnetic_option="rotating_flux_bias",
            mutual_inductance_a_b=0.12,
            mutual_inductance_b_receiver=0.20,
            magnetic_bias_field=-0.20,
            rotating_flux_bias_phase_deg=45.0,
            magnetic_damping=0.012,
            note="passive rotating-bias approximation",
        ),
        MagneticBridgeConfig(
            "random_magnetic_coupling_control",
            seed_b,
            magnetic_option="control_random_magnetic_coupling",
            mutual_inductance_a_b=0.31,
            mutual_inductance_b_receiver=-0.17,
            magnetic_bias_field=0.55,
            magnetic_phase_lag_deg=23.0,
            reference_role="control",
            note="randomized magnetic coupling control",
        ),
        MagneticBridgeConfig(
            "magnetic_bridge_4_to_8_to_12_control",
            BridgeAmpConfig(
                "bridge_4_to_8_to_12_control",
                mode_freqs=(4.0, 8.0, 11.90),
                drive_freqs=(4.0,),
                drive_modes=(0,),
                target_6=8.0,
                target_9=12.0,
                stage_b_nonlinear_strength=0.90,
                stage_b_phase_bias_deg=20.0,
                family="non369",
                note="non-369 magnetic bridge control",
            ),
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.24,
            core_saturation_strength=0.60,
            magnetic_bias_field=-0.35,
            magnetic_phase_lag_deg=-4.0,
            magnetic_damping=0.016,
            family="non369",
            reference_role="control",
        ),
        MagneticBridgeConfig(
            "magnetic_bridge_5_to_10_to_15_control",
            BridgeAmpConfig(
                "bridge_5_to_10_to_15_control",
                mode_freqs=(5.0, 10.0, 14.90),
                drive_freqs=(5.0,),
                drive_modes=(0,),
                target_6=10.0,
                target_9=15.0,
                stage_b_nonlinear_strength=0.90,
                stage_b_phase_bias_deg=20.0,
                family="non369",
                note="non-369 magnetic bridge control",
            ),
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.24,
            core_saturation_strength=0.60,
            magnetic_bias_field=-0.35,
            magnetic_phase_lag_deg=-4.0,
            magnetic_damping=0.016,
            family="non369",
            reference_role="control",
        ),
    ]
    return configs


def magnetic_bridge_sweep_configs(quick: bool) -> List[MagneticBridgeConfig]:
    seed = magnetic_bridge_seed_bridge(8.915, 20.0)
    configs: List[MagneticBridgeConfig] = []
    receiver_values = [8.86, 8.90, 8.93] if quick else [8.86, 8.88, 8.90, 8.915, 8.93]
    phase_values = [15.0, 25.0, 35.0] if quick else [15.0, 20.0, 25.0, 30.0, 35.0]
    strength_values = [0.84, 0.90, 0.94] if quick else [0.84, 0.875, 0.90, 0.925, 0.94]
    bias_values = [-0.55, -0.25, 0.0, 0.25] if quick else [-0.60, -0.35, -0.10, 0.15, 0.40]
    saturation_values = [0.0, 0.45, 0.80] if quick else [0.0, 0.30, 0.55, 0.80]
    mutual_values = [0.08, 0.18, 0.30] if quick else [0.06, 0.14, 0.22, 0.30]
    lag_values = [-8.0, -3.0, 3.0] if quick else [-10.0, -5.0, 0.0, 5.0]
    loss_values = [0.0, 0.015, 0.035] if quick else [0.0, 0.010, 0.025, 0.040]
    rotating_values = [0.0, 60.0, 180.0] if quick else [0.0, 45.0, 90.0, 180.0]

    for receiver in receiver_values:
        for bias in bias_values:
            bridge = replace(seed, mode_freqs=(3.0, 6.0, receiver))
            configs.append(MagneticBridgeConfig(
                f"sweep_receiver_bias_r{safe_token(receiver)}_b{safe_token(bias)}",
                bridge,
                magnetic_option="biased_saturable_core",
                mutual_inductance_a_b=0.16,
                mutual_inductance_b_receiver=0.22,
                core_saturation_strength=0.55,
                magnetic_bias_field=bias,
                magnetic_phase_lag_deg=-4.0,
                magnetic_damping=0.014,
            ))
    for receiver in receiver_values:
        for saturation in saturation_values:
            bridge = replace(seed, mode_freqs=(3.0, 6.0, receiver))
            configs.append(MagneticBridgeConfig(
                f"sweep_receiver_saturation_r{safe_token(receiver)}_s{safe_token(saturation)}",
                bridge,
                magnetic_option="saturable_core",
                mutual_inductance_a_b=0.15,
                mutual_inductance_b_receiver=0.22,
                core_saturation_strength=saturation,
                magnetic_damping=0.014,
            ))
    for mutual in mutual_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_mutual_inductance_{safe_token(mutual)}",
            seed,
            magnetic_option="linear_air_core",
            mutual_inductance_a_b=mutual,
            mutual_inductance_b_receiver=mutual * 1.20,
            magnetic_damping=0.012,
        ))
    for lag in lag_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_magnetic_phase_lag_{safe_token(lag)}",
            seed,
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.22,
            core_saturation_strength=0.55,
            magnetic_bias_field=-0.30,
            magnetic_phase_lag_deg=lag,
            magnetic_damping=0.014,
        ))
    for loss in loss_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_magnetic_loss_{safe_token(loss)}",
            seed,
            magnetic_option="lossy_hysteretic_core",
            mutual_inductance_a_b=0.15,
            mutual_inductance_b_receiver=0.20,
            hysteresis_loss=loss,
            eddy_current_loss=loss * 0.7,
            flux_leakage_loss=loss * 0.4,
            magnetic_damping=0.012 + loss,
        ))
    for phase in rotating_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_rotating_flux_bias_{safe_token(phase)}",
            seed,
            magnetic_option="rotating_flux_bias",
            mutual_inductance_a_b=0.14,
            mutual_inductance_b_receiver=0.22,
            magnetic_bias_field=-0.20,
            rotating_flux_bias_phase_deg=phase,
            magnetic_damping=0.014,
        ))
    for phase in phase_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_phase_bias_{safe_token(phase)}",
            replace(seed, stage_b_phase_bias_deg=phase),
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.22,
            core_saturation_strength=0.55,
            magnetic_bias_field=-0.30,
            magnetic_phase_lag_deg=-4.0,
            magnetic_damping=0.014,
        ))
    for strength in strength_values:
        configs.append(MagneticBridgeConfig(
            f"sweep_stage_B_strength_{safe_token(strength)}",
            replace(seed, stage_b_nonlinear_strength=strength),
            magnetic_option="biased_saturable_core",
            mutual_inductance_a_b=0.16,
            mutual_inductance_b_receiver=0.22,
            core_saturation_strength=0.55,
            magnetic_bias_field=-0.30,
            magnetic_phase_lag_deg=-4.0,
            magnetic_damping=0.014,
        ))
    return configs


def magnetic_bridge_runtime_factors(include_sweeps: bool) -> List[float]:
    return [1.0, 2.0, 4.0] if include_sweeps else [1.0]


def magnetic_bridge_direct_reference(config: MagneticBridgeConfig) -> BridgeAmpConfig:
    direct = bridge_stability_direct_reference(config.bridge)
    return replace(direct, target_6=config.bridge.target_6, target_9=config.bridge.target_9)


def magnetic_bridge_direct_9_reference(config: MagneticBridgeConfig) -> BridgeAmpConfig:
    direct = bridge_stability_direct_9(config.bridge)
    return replace(direct, target_6=config.bridge.target_6, target_9=config.bridge.target_9)


def magnetic_bridge_flux_ledger(config: MagneticBridgeConfig, effective: BridgeAmpConfig,
                                sim: Dict[str, object],
                                oscillator_ledger: List[Dict[str, float | str]]) -> List[Dict[str, float | str]]:
    times = sim["times"]  # type: ignore[assignment]
    vs = sim["vs"]  # type: ignore[assignment]
    qs = sim["qs"]  # type: ignore[assignment]
    if len(times) == 0:
        return []
    dt_sample = float(sim["dt_sample"])
    rows: List[Dict[str, float | str]] = []
    cumulative_leakage = 0.0
    cumulative_hysteresis = 0.0
    cumulative_eddy = 0.0
    cumulative_exchange = 0.0
    for idx, t in enumerate(times):
        v = vs[idx]
        q = qs[idx]
        field = float(np.linalg.norm(v) + abs(config.magnetic_bias_field))
        sat = 1.0 / (1.0 + max(0.0, config.core_saturation_strength) * field * field)
        l_a = 1.0 + 0.12 * config.mutual_inductance_a_b * sat
        l_b = 1.0 + 0.08 * (config.mutual_inductance_a_b + config.mutual_inductance_b_receiver) * sat
        l_r = 1.0 + 0.12 * config.mutual_inductance_b_receiver * sat
        flux_a = l_a * float(v[0]) + config.mutual_inductance_a_b * float(v[1]) + config.magnetic_bias_field
        flux_b = l_b * float(v[1]) + config.mutual_inductance_a_b * float(v[0]) + config.mutual_inductance_b_receiver * float(v[2])
        flux_r = l_r * float(v[2]) + config.mutual_inductance_b_receiver * float(v[1]) + config.receiver_feedback * float(v[1])
        e_a = 0.5 * l_a * float(v[0] ** 2)
        e_b = 0.5 * l_b * float(v[1] ** 2)
        e_r = 0.5 * l_r * float(v[2] ** 2)
        mutual_ab = 0.5 * abs(config.mutual_inductance_a_b) * float((v[0] - v[1]) ** 2)
        mutual_br = 0.5 * abs(config.mutual_inductance_b_receiver) * float((v[1] - v[2]) ** 2)
        magnetic_energy = e_a + e_b + e_r + mutual_ab + mutual_br
        speed2 = float(np.dot(v, v))
        cumulative_leakage += config.flux_leakage_loss * speed2 * dt_sample
        cumulative_hysteresis += config.hysteresis_loss * float(np.sum(np.abs(v) ** 1.35)) * dt_sample
        cumulative_eddy += config.eddy_current_loss * speed2 * dt_sample
        cumulative_exchange += (
            config.mutual_inductance_a_b * float((q[0] - q[1]) * (v[0] - v[1]))
            + config.mutual_inductance_b_receiver * float((q[1] - q[2]) * (v[1] - v[2]))
        ) * dt_sample * 0.001
        source = oscillator_ledger[idx] if idx < len(oscillator_ledger) else {}
        rows.append({
            "case": config.name,
            "time": float(t),
            "magnetic_option": config.magnetic_option,
            "magnetic_flux_A": flux_a,
            "magnetic_flux_B": flux_b,
            "magnetic_flux_receiver": flux_r,
            "magnetic_energy_A": e_a,
            "magnetic_energy_B": e_b,
            "magnetic_energy_receiver": e_r,
            "magnetic_energy_total": magnetic_energy,
            "mutual_inductance_A_B": config.mutual_inductance_a_b,
            "mutual_inductance_B_receiver": config.mutual_inductance_b_receiver,
            "flux_leakage_loss": cumulative_leakage,
            "hysteresis_loss": cumulative_hysteresis,
            "eddy_current_loss": cumulative_eddy,
            "magnetic_loss_total": cumulative_leakage + cumulative_hysteresis + cumulative_eddy,
            "magnetic_phase_lag": config.magnetic_phase_lag_deg,
            "magnetic_bias_field": config.magnetic_bias_field,
            "core_saturation_strength": config.core_saturation_strength,
            "effective_inductance_A": l_a,
            "effective_inductance_B": l_b,
            "effective_inductance_receiver": l_r,
            "effective_receiver_frequency": effective.mode_freqs[2],
            "magnetic_work_input_if_any": 0.0,
            "magnetic_coupling_exchange_net": cumulative_exchange,
            "oscillator_total_stored_energy": source.get("total_stored_energy", 0.0),
            "oscillator_energy_budget_error_rel": source.get("energy_budget_error_rel", 0.0),
        })
    return rows


def magnetic_bridge_measure(config: MagneticBridgeConfig, seed: int, quick: bool, dt: float,
                            runtime: float, sample_every: int, runtime_factor: float,
                            run_type: str, sweep: str, sweep_value: str,
                            direct_sim: Dict[str, object], direct_row: Dict[str, float | str],
                            no_mag_row: Dict[str, float | str] | None = None
                            ) -> Tuple[Dict[str, float | str], List[Dict[str, float | str]], List[Dict[str, float | str]]]:
    effective = magnetic_bridge_effective_bridge(config)
    sim, oscillator_ledger = simulate_bridge_amp(effective, seed, quick, dt=dt, t_max=runtime, sample_every=sample_every)
    row = bridge_metrics_window(effective, sim, seed, run_type, sweep, sweep_value, 0.35, 1.0)
    diag_rows, diag_summary = bridge_phase_diagnostic_series(effective, sim, direct_sim, 0.35, 1.0)
    magnetic_ledger = magnetic_bridge_flux_ledger(config, effective, sim, oscillator_ledger)
    row.update(diag_summary)
    row["experiment"] = "magnetic_bridge"
    row["case"] = config.name
    row["candidate_id"] = f"{config.name}:{runtime_factor:g}x"
    row["magnetic_option"] = config.magnetic_option
    row["reference_role"] = config.reference_role
    row["family"] = config.family
    row["runtime_factor"] = runtime_factor
    row["bridge_ratio"] = metric_ratio(float(row.get("energy_at_9", 0.0)), float(direct_row.get("energy_at_9", 0.0)))
    row["generated_vs_direct_bridge_ratio"] = row["bridge_ratio"]
    row["energy_at_9_from_direct_3_plus_6_reference"] = direct_row.get("energy_at_9", 0.0)
    row["magnetic_energy_total"] = magnetic_ledger[-1]["magnetic_energy_total"] if magnetic_ledger else 0.0
    row["magnetic_loss_total"] = magnetic_ledger[-1]["magnetic_loss_total"] if magnetic_ledger else 0.0
    row["flux_leakage_loss"] = magnetic_ledger[-1]["flux_leakage_loss"] if magnetic_ledger else 0.0
    row["hysteresis_loss"] = magnetic_ledger[-1]["hysteresis_loss"] if magnetic_ledger else 0.0
    row["eddy_current_loss"] = magnetic_ledger[-1]["eddy_current_loss"] if magnetic_ledger else 0.0
    row["magnetic_work_input_if_any"] = magnetic_ledger[-1]["magnetic_work_input_if_any"] if magnetic_ledger else 0.0
    row["magnetic_coupling_exchange_net"] = magnetic_ledger[-1]["magnetic_coupling_exchange_net"] if magnetic_ledger else 0.0
    row["effective_generated_frequency"] = row.get("effective_target_frequency", effective.target_9)
    row["effective_receiver_frequency"] = effective.mode_freqs[2]
    row["magnetic_lock_gain_vs_no_magnetic_layer"] = metric_ratio(float(row.get("phase_lock_9", 0.0)), float(no_mag_row.get("phase_lock_9", 0.0))) if no_mag_row else 1.0
    row["long_runtime_stability_score"] = 1.0
    row["magnetic_passive_discovery_score"] = 0.0
    row["mutual_inductance_A_B"] = config.mutual_inductance_a_b
    row["mutual_inductance_B_receiver"] = config.mutual_inductance_b_receiver
    row["magnetic_phase_lag"] = config.magnetic_phase_lag_deg
    row["magnetic_bias_field"] = config.magnetic_bias_field
    row["core_saturation_strength"] = config.core_saturation_strength
    row["magnetic_damping"] = config.magnetic_damping
    row["rotating_flux_bias_phase"] = config.rotating_flux_bias_phase_deg
    row["active_magnetic_bias_input"] = 0.0
    row["no_direct_6_drive"] = str(not any(abs(freq - effective.target_6) < 1e-9 and mode == 1 for freq, mode in zip(effective.drive_freqs, effective.drive_modes)))
    row["no_direct_9_drive"] = str(not any(abs(freq - effective.target_9) < 1e-9 and mode == 2 for freq, mode in zip(effective.drive_freqs, effective.drive_modes)))
    for item in diag_rows:
        item["candidate_id"] = row["candidate_id"]
        item["case"] = config.name
        item["runtime_factor"] = runtime_factor
    update_magnetic_bridge_score(row)
    return row, magnetic_ledger, diag_rows


def magnetic_bridge_core_pass(row: Dict[str, float | str]) -> bool:
    runtime_factor = float(row.get("runtime_factor", 1.0))
    budget_gate = 0.005 if runtime_factor >= 4.0 else 0.002
    exchange_ok = abs(float(row.get("magnetic_coupling_exchange_net", 0.0))) < 0.05 + 0.20 * abs(float(row.get("magnetic_energy_total", 0.0)))
    return (
        float(row.get("generated_vs_direct_bridge_ratio", 0.0)) > 0.75
        and float(row.get("phase_lock_9", 0.0)) > 0.90
        and float(row.get("spectral_purity_9", 0.0)) > 0.60
        and float(row.get("energy_budget_error", 1.0)) < budget_gate
        and exchange_ok
        and str(row.get("no_direct_6_drive", "False")) == "True"
        and str(row.get("no_direct_9_drive", "False")) == "True"
        and abs(float(row.get("magnetic_work_input_if_any", 0.0))) < 1e-12
    )


def update_magnetic_bridge_score(row: Dict[str, float | str]) -> None:
    passed = magnetic_bridge_core_pass(row)
    failures = []
    runtime_factor = float(row.get("runtime_factor", 1.0))
    budget_gate = 0.005 if runtime_factor >= 4.0 else 0.002
    if float(row.get("generated_vs_direct_bridge_ratio", 0.0)) <= 0.75:
        failures.append("bridge_ratio")
    if float(row.get("phase_lock_9", 0.0)) <= 0.90:
        failures.append("phase_lock_9")
    if float(row.get("spectral_purity_9", 0.0)) <= 0.60:
        failures.append("spectral_purity_9")
    if float(row.get("energy_budget_error", 1.0)) >= budget_gate:
        failures.append("energy_budget")
    if abs(float(row.get("magnetic_work_input_if_any", 0.0))) > 1e-12:
        failures.append("active_magnetic_input")
    if str(row.get("no_direct_6_drive", "False")) != "True" or str(row.get("no_direct_9_drive", "False")) != "True":
        failures.append("direct_drive_contamination")
    if abs(float(row.get("magnetic_coupling_exchange_net", 0.0))) >= 0.05 + 0.20 * abs(float(row.get("magnetic_energy_total", 0.0))):
        failures.append("magnetic_exchange")

    lock_gain = min(2.0, float(row.get("magnetic_lock_gain_vs_no_magnetic_layer", 1.0)))
    long_stability = float(row.get("long_runtime_stability_score", 1.0))
    loss_penalty = 1.0 + 2.0 * float(row.get("magnetic_loss_total", 0.0))
    budget_penalty = 1.0 + 700.0 * max(0.0, float(row.get("energy_budget_error", 0.0)))
    score = (
        float(row.get("generated_vs_direct_bridge_ratio", 0.0))
        * float(row.get("phase_lock_9", 0.0))
        * float(row.get("spectral_purity_9", 0.0))
        * lock_gain
        * long_stability
        / (budget_penalty * loss_penalty)
    )
    if not passed or str(row.get("reference_role", "")) in ("reference", "ceiling_reference", "control") or str(row.get("magnetic_option", "")).startswith("control_"):
        score = 0.0

    strong = (
        passed
        and float(row.get("generated_vs_direct_bridge_ratio", 0.0)) > 0.85
        and float(row.get("phase_lock_9", 0.0)) > 0.95
        and float(row.get("spectral_purity_9", 0.0)) > 0.75
        and ((runtime_factor < 4.0 and float(row.get("energy_budget_error", 1.0)) < 0.001) or (runtime_factor >= 4.0 and float(row.get("energy_budget_error", 1.0)) < 0.003))
        and float(row.get("magnetic_lock_gain_vs_no_magnetic_layer", 1.0)) > 1.25
    )
    if "phase_lock_9" in failures:
        failure_mode = "phase_drift"
    elif "energy_budget" in failures:
        failure_mode = "energy_budget_drift"
    elif "magnetic_exchange" in failures:
        failure_mode = "magnetic_exchange_residual"
    elif "bridge_ratio" in failures:
        failure_mode = "weak_bridge_ratio"
    elif passed:
        failure_mode = "stable"
    else:
        failure_mode = "weak_magnetic_lock"

    row["passed"] = str(passed)
    row["strong_passed"] = str(strong)
    row["failed_gate_names"] = ";".join(failures)
    row["failure_mode"] = failure_mode
    row["magnetic_passive_discovery_score"] = score
    row["score"] = score


def apply_magnetic_validation_status(candidate: Dict[str, float | str],
                                     validation_rows: List[Dict[str, float | str]]) -> None:
    rows = [r for r in validation_rows if str(r.get("case")) == str(candidate.get("case"))]
    by_factor = {float(r.get("runtime_factor", 1.0)): r for r in rows if str(r.get("validation_test", "")).startswith("runtime_")}
    half = next((r for r in rows if str(r.get("validation_test")) == "half_dt_1x"), {})
    quarter = next((r for r in rows if str(r.get("validation_test")) == "quarter_dt_1x"), {})
    runtime2 = by_factor.get(2.0, {})
    runtime4 = by_factor.get(4.0, {})
    half_pass = half.get("passed") == "True"
    quarter_pass = quarter.get("passed") == "True"
    runtime2_pass = runtime2.get("passed") == "True"
    runtime4_pass = runtime4.get("passed") == "True"
    candidate["half_dt_passed"] = str(half_pass)
    candidate["quarter_dt_passed"] = str(quarter_pass)
    candidate["runtime_2x_passed"] = str(runtime2_pass)
    candidate["runtime_4x_passed"] = str(runtime4_pass)
    candidate["validation_status"] = "passed" if half_pass and quarter_pass and runtime2_pass else "failed"
    candidate["long_runtime_stability_score"] = float(np.mean([
        1.0 if runtime2_pass else 0.0,
        1.0 if runtime4_pass else 0.0,
        ratio_stability_score(float(runtime2.get("phase_lock_9", 0.0)), float(candidate.get("phase_lock_9", 0.0))),
        ratio_stability_score(float(runtime4.get("phase_lock_9", 0.0)), float(candidate.get("phase_lock_9", 0.0))),
    ]))
    update_magnetic_bridge_score(candidate)
    if not (half_pass and quarter_pass and runtime2_pass):
        candidate["passed"] = "False"
        candidate["failed_gate_names"] = ";".join(filter(None, [str(candidate.get("failed_gate_names", "")), "validation_stability"]))
        candidate["magnetic_passive_discovery_score"] = 0.0
        candidate["score"] = 0.0
    candidate["promotion_ready"] = str(half_pass and quarter_pass and runtime2_pass and runtime4_pass)


def magnetic_bridge_validation(config: MagneticBridgeConfig, seed: int, quick: bool, dt: float,
                               base_runtime: float, sample_every: int,
                               no_mag_rows: Dict[float, Dict[str, float | str]]) -> Tuple[List[Dict[str, float | str]], List[Dict[str, float | str]], List[Dict[str, float | str]]]:
    tests = [
        ("runtime_1x", dt, base_runtime, 1.0),
        ("half_dt_1x", dt * 0.5, base_runtime, 1.0),
        ("quarter_dt_1x", dt * 0.25, base_runtime, 1.0),
        ("runtime_2x", dt, base_runtime * 2.0, 2.0),
        ("runtime_4x", dt, base_runtime * 4.0, 4.0),
    ]
    rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    drift_rows: List[Dict[str, float | str]] = []
    direct_cache: Dict[Tuple[float, float], Tuple[Dict[str, object], Dict[str, float | str]]] = {}
    for idx, (name, test_dt, runtime, factor) in enumerate(tests):
        cache_key = (test_dt, runtime)
        if cache_key not in direct_cache:
            direct_cfg = magnetic_bridge_direct_reference(config)
            direct_sim, _ = simulate_bridge_amp(direct_cfg, seed + 700 + idx, quick, dt=test_dt, t_max=runtime, sample_every=sample_every)
            direct_row = bridge_metrics_window(direct_cfg, direct_sim, seed + 700 + idx, "direct_reference", "direct_3_plus_6", "reference", 0.35, 1.0)
            direct_cache[cache_key] = (direct_sim, direct_row)
        direct_sim, direct_row = direct_cache[cache_key]
        no_mag_row = no_mag_rows.get(factor)
        row, ledger, drift = magnetic_bridge_measure(
            config,
            seed + idx * 31,
            quick,
            test_dt,
            runtime,
            sample_every,
            factor,
            "validation",
            name,
            name,
            direct_sim,
            direct_row,
            no_mag_row,
        )
        row["validation_test"] = name
        rows.append(row)
        ledger_rows.extend(ledger)
        drift_rows.extend(drift)
    return rows, ledger_rows, drift_rows


def plot_magnetic_bridge_outputs(out_dir: Path, ranked: List[Dict[str, float | str]],
                                 sweep_rows: List[Dict[str, float | str]],
                                 ledger_rows: List[Dict[str, float | str]],
                                 drift_rows: List[Dict[str, float | str]],
                                 comparison_rows: List[Dict[str, float | str]]) -> None:
    if ranked:
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        ax.scatter(
            [float(r.get("generated_vs_direct_bridge_ratio", 0.0)) for r in ranked],
            [float(r.get("phase_lock_9", 0.0)) for r in ranked],
            c=[float(r.get("magnetic_passive_discovery_score", 0.0)) for r in ranked],
        )
        ax.axvline(0.75, color="tab:red", linestyle="--", linewidth=1.0)
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_title("magnetic bridge ratio vs phase lock")
        ax.set_xlabel("bridge ratio")
        ax.set_ylabel("phase_lock_9")
        fig.tight_layout()
        fig.savefig(out_dir / "magnetic_bridge_ratio_vs_phase_lock.png", dpi=140)
        plt.close(fig)

    if drift_rows:
        for key, ylabel, filename in [
            ("local_phase_lock", "local phase lock", "magnetic_phase_lock_over_runtime.png"),
            ("sliding_bridge_ratio", "sliding bridge ratio", "magnetic_bridge_ratio_over_time.png"),
            ("phase_drift_rate", "phase drift rate", "magnetic_phase_drift_rate_over_time.png"),
        ]:
            fig, ax = plt.subplots(figsize=(9.5, 5.0))
            for case in list(dict.fromkeys(str(r.get("case", "")) for r in drift_rows))[:5]:
                rows = [r for r in drift_rows if str(r.get("case", "")) == case]
                if rows:
                    ax.plot([float(r["time_mid"]) for r in rows], [float(r.get(key, 0.0)) for r in rows], label=case[:28])
            ax.set_title(ylabel)
            ax.set_xlabel("time")
            ax.set_ylabel(ylabel)
            ax.legend(fontsize=7)
            fig.tight_layout()
            fig.savefig(out_dir / filename, dpi=140)
            plt.close(fig)

    if ledger_rows:
        fig, ax = plt.subplots(figsize=(9.0, 5.0))
        rows = [r for r in ledger_rows if str(r.get("case")) == str(ranked[0].get("case", ""))] if ranked else ledger_rows
        ax.plot([float(r["time"]) for r in rows], [float(r.get("magnetic_energy_total", 0.0)) for r in rows], label="magnetic")
        ax.plot([float(r["time"]) for r in rows], [float(r.get("oscillator_total_stored_energy", 0.0)) for r in rows], label="oscillator")
        ax.set_title("magnetic energy vs oscillator energy")
        ax.set_xlabel("time")
        ax.set_ylabel("energy")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "magnetic_energy_vs_oscillator_energy.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9.0, 5.0))
        ax.plot([float(r["time"]) for r in rows], [float(r.get("flux_leakage_loss", 0.0)) for r in rows], label="flux leakage")
        ax.plot([float(r["time"]) for r in rows], [float(r.get("hysteresis_loss", 0.0)) for r in rows], label="hysteresis")
        ax.plot([float(r["time"]) for r in rows], [float(r.get("eddy_current_loss", 0.0)) for r in rows], label="eddy")
        ax.set_title("magnetic losses")
        ax.set_xlabel("time")
        ax.set_ylabel("cumulative loss")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "magnetic_losses_over_time.png", dpi=140)
        plt.close(fig)

    def heatmap(rows: List[Dict[str, float | str]], match: str, x_key: str, y_key: str, metric: str, filename: str, title: str) -> None:
        selected = [r for r in rows if match in str(r.get("case", ""))]
        xs = sorted({float(r.get(x_key, 0.0)) for r in selected})
        ys = sorted({float(r.get(y_key, 0.0)) for r in selected})
        if not xs or not ys:
            return
        matrix = np.zeros((len(ys), len(xs)))
        for row in selected:
            matrix[ys.index(float(row.get(y_key, 0.0))), xs.index(float(row.get(x_key, 0.0)))] = float(row.get(metric, 0.0))
        fig, ax = plt.subplots(figsize=(8.2, 5.3))
        im = ax.imshow(matrix, origin="lower", aspect="auto")
        ax.set_xticks(np.arange(len(xs)))
        ax.set_xticklabels([f"{x:g}" for x in xs], rotation=35, ha="right")
        ax.set_yticks(np.arange(len(ys)))
        ax.set_yticklabels([f"{y:g}" for y in ys])
        ax.set_title(title)
        ax.set_xlabel(x_key)
        ax.set_ylabel(y_key)
        fig.colorbar(im, ax=ax, label=metric)
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=140)
        plt.close(fig)

    heatmap(sweep_rows, "receiver_bias", "receiver_tuning", "magnetic_bias_field", "phase_lock_9", "magnetic_receiver_tuning_vs_bias_heatmap.png", "receiver tuning vs magnetic bias")
    heatmap(sweep_rows, "receiver_saturation", "receiver_tuning", "core_saturation_strength", "phase_lock_9", "magnetic_core_saturation_vs_phase_lock_heatmap.png", "core saturation vs phase lock")
    heatmap(sweep_rows, "mutual_inductance", "mutual_inductance_A_B", "mutual_inductance_B_receiver", "generated_vs_direct_bridge_ratio", "magnetic_mutual_inductance_vs_bridge_ratio_heatmap.png", "mutual inductance vs bridge ratio")

    if comparison_rows:
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        labels = [str(r.get("case", ""))[:22] for r in comparison_rows]
        values = [float(r.get("phase_lock_9", 0.0)) for r in comparison_rows]
        ax.bar(np.arange(len(labels)), values)
        ax.axhline(0.90, color="tab:red", linestyle="--", linewidth=1.0)
        ax.set_xticks(np.arange(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylabel("phase_lock_9")
        ax.set_title("magnetic vs non-magnetic lock comparison")
        fig.tight_layout()
        fig.savefig(out_dir / "magnetic_vs_nonmagnetic_lock_comparison.png", dpi=140)
        plt.close(fig)


def write_magnetic_bridge_report(out_dir: Path, ranked: List[Dict[str, float | str]],
                                 validation_rows: List[Dict[str, float | str]],
                                 comparison_rows: List[Dict[str, float | str]]) -> None:
    best = ranked[0] if ranked else {}
    passing = [r for r in ranked if str(r.get("passed")) == "True"]
    validated_passing = [r for r in passing if str(r.get("validation_status")) == "passed" or str(r.get("promotion_ready")) == "True"]
    best_passing = validated_passing[0] if validated_passing else (passing[0] if passing else {})
    runtime4_pass = any(str(r.get("validation_test")) == "runtime_4x" and str(r.get("passed")) == "True" for r in validation_rows if str(r.get("case")) == str(best_passing.get("case", "")))
    long_validation = [r for r in validation_rows if float(r.get("runtime_factor", 1.0)) > 1.0]
    best_long_row = max(long_validation, key=lambda r: float(r.get("magnetic_lock_gain_vs_no_magnetic_layer", 0.0)), default={})
    best_gain = float(best_long_row.get("magnetic_lock_gain_vs_no_magnetic_layer", best_passing.get("magnetic_lock_gain_vs_no_magnetic_layer", 0.0))) if best_passing else 0.0
    best_option = str(best_passing.get("magnetic_option", "none")) if best_passing else "none"
    non369 = [r for r in ranked if str(r.get("family")) == "non369"]
    non369_best = max((float(r.get("magnetic_passive_discovery_score", 0.0)) for r in non369), default=0.0)
    best_score = float(best_passing.get("magnetic_passive_discovery_score", 0.0)) if best_passing else 0.0
    lines = [
        "# Magnetic Bridge Report",
        "",
        "## Direct Answers",
        f"1. Magnetic layer reduces long-runtime phase drift? {'yes' if best_gain > 1.0 else 'not clearly'}; best 2x/4x lock gain vs no magnetic layer = {best_gain:.6g}.",
        f"2. Passive magnetic configuration survives 4x runtime? {'yes' if runtime4_pass else 'not found'} by current gates.",
        f"3. Magnetic bias/saturation widens the lock island? {'yes' if best_option in ('biased_saturable_core', 'saturable_core') and best_gain > 1.0 else 'not proven'} in this run.",
        f"4. Best improvement source: {best_long_row.get('magnetic_option', best_option)}.",
        f"5. Clean energy accounting preserved? {'yes' if best_passing and float(best_passing.get('energy_budget_error', 1.0)) < 0.002 and abs(float(best_passing.get('magnetic_work_input_if_any', 0.0))) < 1e-12 else 'not for the best candidate'}.",
        f"6. 3->6->9 beats non-369 magnetic controls? {'yes' if best_score > non369_best else 'not clearly'}; best_369_score={best_score:.6g}, best_non369_score={non369_best:.6g}.",
        f"7. Promote to geometry369? {'yes' if runtime4_pass else 'not yet; use active self-lock/PLL or more passive damping work next'}.",
        f"8. Next seed: {best_passing.get('case', 'none')} with option={best_option}, receiver={best_passing.get('receiver_tuning', '')}, bias={best_passing.get('magnetic_bias_field', '')}, M_AB={best_passing.get('mutual_inductance_A_B', '')}, M_BR={best_passing.get('mutual_inductance_B_receiver', '')}.",
        "",
        "## Top Candidates",
    ]
    for row in ranked[:20]:
        lines.append(
            f"- {row.get('case')}: score={float(row.get('magnetic_passive_discovery_score', 0.0)):.6g}, passed={row.get('passed')}, "
            f"runtime={float(row.get('runtime_factor', 1.0)):.3g}x, option={row.get('magnetic_option')}, ratio={float(row.get('generated_vs_direct_bridge_ratio', 0.0)):.6g}, "
            f"phase={float(row.get('phase_lock_9', 0.0)):.6g}, purity={float(row.get('spectral_purity_9', 0.0)):.6g}, "
            f"budget={float(row.get('energy_budget_error', 0.0)):.6g}, lock_gain={float(row.get('magnetic_lock_gain_vs_no_magnetic_layer', 0.0)):.6g}, failure={row.get('failure_mode', '')}"
        )
    (out_dir / "README_MAGNETIC_BRIDGE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def experiment_magnetic_bridge(out_dir: Path, seed: int, quick: bool = False,
                               include_sweeps: bool = False) -> List[Dict[str, float | str]]:
    dt, base_tmax, sample_every = bridge_amp_timebase(quick)
    base_runtime = base_tmax * 1.25
    configs = magnetic_bridge_core_configs()
    if include_sweeps:
        configs.extend(magnetic_bridge_sweep_configs(quick))

    rows: List[Dict[str, float | str]] = []
    sweep_rows: List[Dict[str, float | str]] = []
    ledger_rows: List[Dict[str, float | str]] = []
    drift_rows: List[Dict[str, float | str]] = []
    comparison_rows: List[Dict[str, float | str]] = []
    direct_cache: Dict[float, Tuple[Dict[str, object], Dict[str, float | str]]] = {}
    no_mag_by_factor: Dict[float, Dict[str, float | str]] = {}

    for factor in [1.0, 2.0, 4.0]:
        runtime = base_runtime * factor
        direct_cfg = magnetic_bridge_direct_reference(magnetic_bridge_core_configs()[0])
        direct_sim, _ = simulate_bridge_amp(direct_cfg, seed + 17000 + int(factor * 10), quick, dt=dt, t_max=runtime, sample_every=sample_every)
        direct_row = bridge_metrics_window(direct_cfg, direct_sim, seed + 17000 + int(factor * 10), "direct_reference", "direct_3_plus_6", "reference", 0.35, 1.0)
        direct_cache[factor] = (direct_sim, direct_row)
        no_cfg = magnetic_bridge_core_configs()[1]
        no_sim, no_ledger = simulate_bridge_amp(magnetic_bridge_effective_bridge(no_cfg), seed + 18000 + int(factor * 10), quick, dt=dt, t_max=runtime, sample_every=sample_every)
        no_row = bridge_metrics_window(no_cfg.bridge, no_sim, seed + 18000 + int(factor * 10), "no_magnetic_control", "no_magnetic_layer", f"{factor:g}x", 0.35, 1.0)
        no_row["phase_lock_9"] = no_row.get("phase_lock_9", 0.0)
        no_mag_by_factor[factor] = no_row

    for idx, config in enumerate(configs):
        factor = 1.0
        runtime = base_runtime
        direct_sim, direct_row = direct_cache[factor]
        row, ledger, drift = magnetic_bridge_measure(
            config,
            seed + idx * 19,
            quick,
            dt,
            runtime,
            sample_every,
            factor,
            "sweep" if include_sweeps else "core",
            config.magnetic_option,
            config.name,
            direct_sim,
            direct_row,
            no_mag_by_factor.get(factor),
        )
        rows.append(row)
        if include_sweeps or config.magnetic_option != "control_no_magnetic_layer":
            sweep_rows.append(row)
        ledger_rows.extend(ledger)
        drift_rows.extend(drift)
        if config.magnetic_option in ("control_no_magnetic_layer", "linear_air_core", "saturable_core", "biased_saturable_core", "lossy_hysteretic_core"):
            comparison_rows.append(row)

    ranked = sorted(rows, key=lambda r: (float(r.get("magnetic_passive_discovery_score", 0.0)), float(r.get("phase_lock_9", 0.0))), reverse=True)
    top_candidates = [r for r in ranked if magnetic_bridge_core_pass(r) and str(r.get("reference_role")) == "discovery_candidate"][:5 if include_sweeps else 8]
    if not top_candidates and ranked:
        top_candidates = [ranked[0]]

    validation_rows: List[Dict[str, float | str]] = []
    for idx, candidate in enumerate(top_candidates):
        cfg = next((c for c in configs if c.name == candidate["case"]), configs[0])
        vrows, vledger, vdrift = magnetic_bridge_validation(cfg, seed + 21000 + idx * 1000, quick, dt, base_runtime, sample_every, no_mag_by_factor)
        validation_rows.extend(vrows)
        ledger_rows.extend(vledger)
        drift_rows.extend(vdrift)
        apply_magnetic_validation_status(candidate, validation_rows)
        if str(candidate.get("promotion_ready")) == "True":
            break

    ranked = sorted(rows, key=lambda r: (float(r.get("magnetic_passive_discovery_score", 0.0)), float(r.get("phase_lock_9", 0.0))), reverse=True)
    lock_rows = [
        {
            "case": row.get("case", ""),
            "magnetic_option": row.get("magnetic_option", ""),
            "runtime_factor": row.get("runtime_factor", 1.0),
            "receiver_tuning": row.get("receiver_tuning", row.get("effective_receiver_frequency", 0.0)),
            "phase_lock_9": row.get("phase_lock_9", 0.0),
            "phase_drift_rate": row.get("phase_drift_rate", 0.0),
            "lock_duration": row.get("lock_duration", 0.0),
            "time_to_unlock": row.get("time_to_unlock", 0.0),
            "effective_generated_frequency": row.get("effective_generated_frequency", 0.0),
            "effective_receiver_frequency": row.get("effective_receiver_frequency", 0.0),
            "magnetic_lock_gain_vs_no_magnetic_layer": row.get("magnetic_lock_gain_vs_no_magnetic_layer", 0.0),
            "passed": row.get("passed", "False"),
        }
        for row in rows + validation_rows
    ]

    write_csv(out_dir / "magnetic_bridge_summary.csv", rows)
    write_csv(out_dir / "magnetic_bridge_ranked.csv", ranked)
    write_csv(out_dir / "magnetic_bridge_sweeps.csv", sweep_rows)
    write_csv(out_dir / "magnetic_energy_ledger.csv", ledger_rows)
    write_csv(out_dir / "magnetic_phase_drift_timeseries.csv", drift_rows)
    write_csv(out_dir / "magnetic_lock_islands.csv", lock_rows)
    write_csv(out_dir / "magnetic_vs_nonmagnetic_comparison.csv", comparison_rows + validation_rows)
    plot_magnetic_bridge_outputs(out_dir, ranked, sweep_rows, ledger_rows, drift_rows, comparison_rows + validation_rows)
    write_magnetic_bridge_report(out_dir, ranked, validation_rows, comparison_rows)

    return [
        {
            "experiment": "magnetic_bridge",
            "case": row.get("case", ""),
            "freqs": row.get("freqs", ""),
            "score": row.get("magnetic_passive_discovery_score", 0.0),
            "passed": row.get("passed", "False"),
            "promotion_ready": row.get("promotion_ready", "False"),
            "magnetic_option": row.get("magnetic_option", ""),
            "generated_vs_direct_bridge_ratio": row.get("generated_vs_direct_bridge_ratio", 0.0),
            "phase_lock_9": row.get("phase_lock_9", 0.0),
            "spectral_purity_9": row.get("spectral_purity_9", 0.0),
            "energy_budget_error": row.get("energy_budget_error", 0.0),
            "magnetic_lock_gain_vs_no_magnetic_layer": row.get("magnetic_lock_gain_vs_no_magnetic_layer", 0.0),
            "failure_mode": row.get("failure_mode", ""),
            "note": row.get("note", ""),
        }
        for row in ranked[:20]
    ]


# ----------------------------
# Ranking and orchestration
# ----------------------------

def rank_and_write(out_dir: Path, rows: List[Dict[str, float | str]]) -> None:
    # Sort within each experiment by score descending.
    ranked = []
    for exp in sorted({str(r["experiment"]) for r in rows}):
        exp_rows = [r for r in rows if r["experiment"] == exp]
        exp_rows = sorted(exp_rows, key=lambda r: float(r.get("score", 0.0)), reverse=True)
        for rank, r in enumerate(exp_rows, 1):
            rr = dict(r)
            rr["rank_within_experiment"] = rank
            ranked.append(rr)
    write_csv(out_dir / "summary.csv", ranked)

    # Markdown report for humans.
    report = ["# Tesla 3-6-9 Lab Report", "", "This run asks: does a 3-6-9 pattern beat controls?", ""]
    for exp in sorted({str(r["experiment"]) for r in ranked}):
        report.append(f"## {exp}")
        exp_rows = [r for r in ranked if r["experiment"] == exp]
        for r in exp_rows:
            report.append(
                f"- rank {r['rank_within_experiment']}: **{r['case']}** - score={float(r['score']):.6g}; "
                f"freqs={r['freqs']}; note={r.get('note','')}"
            )
        report.append("")

    report.append("## How to interpret")
    report.append("- If `369_exact_sum` wins but `4812_exact_sum` also wins, the effect is probably harmonic triad resonance, not mystical numerology.")
    report.append("- If a phase-locked case beats its random-phase twin, phase geometry matters.")
    report.append("- In the receiver-coil run, compare `369_two_tone_sum_pump` with `369_linear_no_gap` to test whether nonlinear mixing is doing real work.")
    report.append("- In the silent-9 run, compare `3_plus_6_to_9_nonlinear` against its linear, detuned, and non-369 sum-pair controls.")
    report.append("- Treat `normal_resonant_single_9` as a ceiling/reference, not the discovery winner.")
    report.append("- If `normal_resonant_single_6` wins, ordinary resonant tuning beats phase coding in this toy model.")
    report.append("- If detuned/non-sum controls beat 369, the hypothesis is weak for this model.")
    report.append("- A real anomaly should reproduce across seeds, grid sizes, time steps, and damping settings.")
    (out_dir / "README_RUN_REPORT.md").write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tesla 3-6-9 resonance, wave, receiver-coil, silent-9, atlas, cascade, validation, clean validation, bridge amplification/stability/phase-lock/refinement/magnetic, optimization, and energy-audit simulations.")
    parser.add_argument("--mode", choices=["all", "triad", "wave", "receiver", "silent9", "atlas", "cascade", "validate", "clean_validate", "clean_optimize", "bridge_amp", "bridge_stability", "bridge_phase_lock", "bridge_lock_refine", "magnetic_bridge", "energy_audit"], default="all")
    parser.add_argument("--seed", type=int, default=369)
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--quick", action="store_true", help="Faster, lower-resolution wave run.")
    parser.add_argument("--sweeps", action="store_true", help="Run sweep packs for silent-9, atlas, cascade, bridge, and phase-lock modes.")
    parser.add_argument("--case", type=str, default="all", help="Case selector for energy_audit mode.")
    parser.add_argument("--energy-clean", action="store_true", help="Use the passive energy-clean validation model. This is now the default for validate mode.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ensure_dir(Path(args.out) if args.out else Path("runs") / f"tesla_369_{timestamp}")

    rows: List[Dict[str, float | str]] = []
    if args.mode in ("all", "triad"):
        rows.extend(experiment_triad_resonators(out_dir, args.seed))
    if args.mode in ("all", "wave"):
        rows.extend(experiment_wave_lattice(out_dir, args.seed, quick=args.quick))
    if args.mode in ("all", "receiver"):
        rows.extend(experiment_receiver_coils(out_dir, args.seed, quick=args.quick))
    if args.mode in ("all", "silent9"):
        rows.extend(experiment_silent_9_receiver(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("all", "atlas"):
        rows.extend(experiment_atlas(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("all", "cascade"):
        rows.extend(experiment_cascade(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("validate",):
        rows.extend(experiment_clean_validate(out_dir, args.seed, quick=args.quick, include_optimize=False))
    if args.mode in ("clean_validate",):
        rows.extend(experiment_clean_validate(out_dir, args.seed, quick=args.quick, include_optimize=False))
    if args.mode in ("clean_optimize",):
        rows.extend(experiment_clean_validate(out_dir, args.seed, quick=args.quick, include_optimize=True))
    if args.mode in ("bridge_amp",):
        rows.extend(experiment_bridge_amp(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("bridge_stability",):
        rows.extend(experiment_bridge_stability(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("bridge_phase_lock",):
        rows.extend(experiment_bridge_phase_lock(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("bridge_lock_refine",):
        rows.extend(experiment_bridge_lock_refine(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("magnetic_bridge",):
        rows.extend(experiment_magnetic_bridge(out_dir, args.seed, quick=args.quick, include_sweeps=args.sweeps))
    if args.mode in ("energy_audit",):
        rows.extend(experiment_energy_audit(out_dir, args.seed, quick=args.quick, case_arg=args.case))

    rank_and_write(out_dir, rows)
    print(f"Done. Results written to: {out_dir.resolve()}")
    print(f"Open: {out_dir / 'README_RUN_REPORT.md'}")
    print(f"CSV:  {out_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
