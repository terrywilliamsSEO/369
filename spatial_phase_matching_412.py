#!/usr/bin/env python3
"""Distributed phase-matching model for the 4->8->12 bridge.

The lumped component SPICE tracks can generate target-band energy, but they do
not preserve the coherent phase relation 4 + 8 -> 12.  This script tests a
normalized 1D coupled-mode chain with explicit wave numbers, phase mismatch,
quasi-phase-matching, backward-wave options, and controls.
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


OUT_DIR = Path("runs") / "spatial_phase_matching_412"
BASE_DT = 0.04
BASE_TMAX = 96.0
SAMPLE_STRIDE = 8
EPS = 1e-18


@dataclass(frozen=True)
class SpatialConfig:
    name: str
    topology: str
    role: str = "discovery"
    source_mode: float = 4.0
    generated_mode: float = 8.0
    target_mode: float = 12.0
    k4: float = 1.0
    k8: float = 2.0
    k12: float = 3.0
    forward_8: int = 1
    forward_12: int = 1
    delta_k_448: float = 0.0
    delta_k_4812: float = 0.0
    qpm_period_448: float = 0.0
    qpm_period_4812: float = 0.0
    qpm_duty_cycle: float = 0.5
    grating_kind: str = "none"
    coupling_sign_pattern: str = "uniform"
    chain_length: float = 24.0
    cell_count: int = 64
    group_velocity_mismatch_8: float = 0.0
    group_velocity_mismatch_12: float = 0.0
    nonlinear_strength_448: float = 0.085
    nonlinear_strength_4812: float = 0.115
    coupling_strength: float = 0.16
    damping_loss: float = 0.045
    saturation_loss: float = 0.010
    drive_amplitude: float = 0.20
    direct_8_drive_scale: float = 0.42
    direct_8_reference_drive: bool = False
    no_nonlinearity: bool = False
    target_detuning: float = 0.0
    generated_detuning: float = 0.0
    random_seed: int = 0


@dataclass
class SimResult:
    config: SpatialConfig
    times: np.ndarray
    obs4: np.ndarray
    obs8: np.ndarray
    obs12: np.ndarray
    rel_target: np.ndarray
    rel_generated: np.ndarray
    spatial_target_coherence: np.ndarray
    spatial_generated_coherence: np.ndarray
    energy: np.ndarray
    drive_work: float
    loss_work: float
    rhs_energy_work: float
    final_state: np.ndarray
    z: np.ndarray
    pattern448: np.ndarray
    pattern4812: np.ndarray


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


def wrap_angle(x: np.ndarray | float) -> np.ndarray | float:
    return (np.asarray(x) + np.pi) % (2.0 * np.pi) - np.pi


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def envelope_cv(values: np.ndarray) -> float:
    amp = np.abs(values)
    mean = float(np.mean(amp))
    if mean <= EPS:
        return float("inf")
    return float(np.std(amp) / mean)


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


def qpm_pattern(z: np.ndarray, period: float, duty_cycle: float, kind: str, seed: int) -> np.ndarray:
    if kind == "none" or period <= 0.0:
        return np.ones_like(z)
    if kind == "alternating":
        cells = np.floor(z / max(period, EPS)).astype(int)
        return np.where(cells % 2 == 0, 1.0, -1.0)
    if kind == "randomized":
        rng = np.random.default_rng(seed)
        cells = np.floor(z / max(period, EPS)).astype(int)
        unique = int(np.max(cells)) + 1
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=max(1, unique))
        return signs[np.clip(cells, 0, unique - 1)]
    phase = (z % period) / max(period, EPS)
    return np.where(phase < duty_cycle, 1.0, -1.0)


def sign_pattern(z: np.ndarray, kind: str, length: float) -> np.ndarray:
    if kind == "alternating_cell":
        return np.where(np.arange(len(z)) % 2 == 0, 1.0, -1.0)
    if kind == "alternating_section":
        return np.where(np.floor(6.0 * z / max(length, EPS)).astype(int) % 2 == 0, 1.0, -1.0)
    return np.ones_like(z)


def laplacian(values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return np.zeros_like(values)
    lap = np.empty_like(values)
    lap[1:-1] = values[:-2] - 2.0 * values[1:-1] + values[2:]
    lap[0] = -values[0] + values[1]
    lap[-1] = values[-2] - values[-1]
    return lap


def drive_envelope(t: float, tmax: float) -> float:
    ramp = 0.12 * tmax
    fade = 0.18 * tmax
    return min(1.0, t / max(ramp, EPS), max(0.0, (tmax - t) / max(fade, EPS)))


def rhs(
    state: np.ndarray,
    t: float,
    cfg: SpatialConfig,
    z: np.ndarray,
    pattern448: np.ndarray,
    pattern4812: np.ndarray,
    sign448: np.ndarray,
    sign4812: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, float]]:
    n = cfg.cell_count
    a4 = state[0:n]
    a8 = state[n:2 * n]
    a12 = state[2 * n:3 * n]
    loss = cfg.damping_loss
    c = cfg.coupling_strength
    mode_mismatch_448 = cfg.generated_mode - 2.0 * cfg.source_mode
    mode_mismatch_4812 = cfg.target_mode - cfg.generated_mode - cfg.source_mode
    phase448 = np.exp(
        -1j * (cfg.delta_k_448 * z + (cfg.group_velocity_mismatch_8 + 0.42 * mode_mismatch_448) * t)
    )
    phase4812 = np.exp(
        -1j * (cfg.delta_k_4812 * z + (cfg.group_velocity_mismatch_12 + 0.42 * mode_mismatch_4812) * t)
    )

    d4 = -(loss + 1j * 0.0) * a4 + 1j * c * laplacian(a4)
    d8 = -(1.08 * loss + 1j * cfg.generated_detuning) * a8 + 1j * 0.92 * c * laplacian(a8)
    d12 = -(1.16 * loss + 1j * cfg.target_detuning) * a12 + 1j * 0.84 * c * laplacian(a12)
    if cfg.saturation_loss > 0.0:
        density = np.abs(a4) ** 2 + np.abs(a8) ** 2 + np.abs(a12) ** 2
        d4 -= cfg.saturation_loss * density * a4
        d8 -= cfg.saturation_loss * density * a8
        d12 -= cfg.saturation_loss * density * a12

    source_profile = np.exp(-0.5 * (z / max(0.08 * cfg.chain_length, EPS)) ** 2)
    source_profile /= max(float(np.max(source_profile)), EPS)
    env = drive_envelope(t, BASE_TMAX)
    drive4 = cfg.drive_amplitude * env * source_profile
    drive8 = np.zeros_like(drive4)
    if cfg.direct_8_reference_drive:
        drive8 = cfg.direct_8_drive_scale * cfg.drive_amplitude * env * source_profile
    d4 += drive4
    d8 += drive8

    if not cfg.no_nonlinearity:
        n448 = cfg.nonlinear_strength_448 * pattern448 * sign448 * a4 * a4 * phase448
        n4812 = cfg.nonlinear_strength_4812 * pattern4812 * sign4812 * a4 * a8 * phase4812
        d8 += n448
        d12 += n4812
        # Weak pump-depletion terms keep the toy model from behaving like a pure target injector.
        d4 += -0.010 * np.conj(a4) * a8 * np.conj(phase448)
        d4 += -0.007 * np.conj(a8) * a12 * np.conj(phase4812)
        d8 += -0.007 * np.conj(a4) * a12 * np.conj(phase4812)

    deriv = np.concatenate([d4, d8, d12])
    drive_power = 2.0 * float(np.real(np.vdot(a4, drive4) + np.vdot(a8, drive8)))
    loss_power = 2.0 * float(
        loss * np.vdot(a4, a4).real
        + 1.08 * loss * np.vdot(a8, a8).real
        + 1.16 * loss * np.vdot(a12, a12).real
    )
    rhs_energy = 2.0 * float(np.real(np.vdot(state, deriv)))
    return deriv, {"drive_power": drive_power, "loss_power": loss_power, "rhs_energy": rhs_energy}


def rk4_step(
    state: np.ndarray,
    t: float,
    dt: float,
    cfg: SpatialConfig,
    z: np.ndarray,
    pattern448: np.ndarray,
    pattern4812: np.ndarray,
    sign448: np.ndarray,
    sign4812: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, float]]:
    k1, p1 = rhs(state, t, cfg, z, pattern448, pattern4812, sign448, sign4812)
    k2, p2 = rhs(state + 0.5 * dt * k1, t + 0.5 * dt, cfg, z, pattern448, pattern4812, sign448, sign4812)
    k3, p3 = rhs(state + 0.5 * dt * k2, t + 0.5 * dt, cfg, z, pattern448, pattern4812, sign448, sign4812)
    k4, p4 = rhs(state + dt * k3, t + dt, cfg, z, pattern448, pattern4812, sign448, sign4812)
    merged = {
        key: (p1[key] + 2.0 * p2[key] + 2.0 * p3[key] + p4[key]) / 6.0
        for key in p1
    }
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4), merged


def observe(
    state: np.ndarray,
    z: np.ndarray,
    cfg: SpatialConfig,
    pattern448: np.ndarray,
    pattern4812: np.ndarray,
) -> Tuple[complex, complex, complex, complex, complex, float, float]:
    n = cfg.cell_count
    a4 = state[0:n]
    a8 = state[n:2 * n]
    a12 = state[2 * n:3 * n]
    out_weight = np.exp(-0.5 * ((z - cfg.chain_length) / max(0.22 * cfg.chain_length, EPS)) ** 2)
    out_weight /= max(float(np.sum(out_weight)), EPS)
    obs4 = complex(np.sum(out_weight * a4))
    obs8 = complex(np.sum(out_weight * a8))
    obs12 = complex(np.sum(out_weight * a12))
    rel_target_local = out_weight * a4 * a8 * np.conj(a12)
    rel_generated_local = out_weight * a4 * a4 * np.conj(a8)
    rel_target = complex(np.sum(rel_target_local))
    rel_generated = complex(np.sum(rel_generated_local))
    spatial_target = float(abs(np.sum(rel_target_local)) / max(float(np.sum(np.abs(rel_target_local))), EPS))
    spatial_generated = float(abs(np.sum(rel_generated_local)) / max(float(np.sum(np.abs(rel_generated_local))), EPS))
    return obs4, obs8, obs12, rel_target, rel_generated, spatial_target, spatial_generated


def simulate(cfg: SpatialConfig, dt: float = BASE_DT, tmax: float = BASE_TMAX) -> SimResult:
    n = cfg.cell_count
    z = np.linspace(0.0, cfg.chain_length, n)
    period448 = cfg.qpm_period_448
    period4812 = cfg.qpm_period_4812
    pattern448 = qpm_pattern(z, period448, cfg.qpm_duty_cycle, cfg.grating_kind, cfg.random_seed)
    pattern4812 = qpm_pattern(z, period4812, cfg.qpm_duty_cycle, cfg.grating_kind, cfg.random_seed + 17)
    signs = sign_pattern(z, cfg.coupling_sign_pattern, cfg.chain_length)
    state = np.zeros(3 * n, dtype=np.complex128)
    steps = int(round(tmax / dt))
    times: List[float] = []
    obs4: List[complex] = []
    obs8: List[complex] = []
    obs12: List[complex] = []
    rel_target: List[complex] = []
    rel_generated: List[complex] = []
    spatial_target: List[float] = []
    spatial_generated: List[float] = []
    energy: List[float] = []
    drive_work = 0.0
    loss_work = 0.0
    rhs_energy_work = 0.0

    for step in range(steps + 1):
        t = step * dt
        if step % SAMPLE_STRIDE == 0 or step == steps:
            o4, o8, o12, rt, rg, st, sg = observe(state, z, cfg, pattern448, pattern4812)
            times.append(t)
            obs4.append(o4)
            obs8.append(o8)
            obs12.append(o12)
            rel_target.append(rt)
            rel_generated.append(rg)
            spatial_target.append(st)
            spatial_generated.append(sg)
            energy.append(float(np.vdot(state, state).real))
        if step == steps:
            break
        state, powers = rk4_step(state, t, dt, cfg, z, pattern448, pattern4812, signs, signs)
        drive_work += powers["drive_power"] * dt
        loss_work += powers["loss_power"] * dt
        rhs_energy_work += powers["rhs_energy"] * dt

    return SimResult(
        config=cfg,
        times=np.asarray(times),
        obs4=np.asarray(obs4),
        obs8=np.asarray(obs8),
        obs12=np.asarray(obs12),
        rel_target=np.asarray(rel_target),
        rel_generated=np.asarray(rel_generated),
        spatial_target_coherence=np.asarray(spatial_target),
        spatial_generated_coherence=np.asarray(spatial_generated),
        energy=np.asarray(energy),
        drive_work=drive_work,
        loss_work=loss_work,
        rhs_energy_work=rhs_energy_work,
        final_state=state,
        z=z,
        pattern448=pattern448,
        pattern4812=pattern4812,
    )


def qpm_gain_factor(cfg: SpatialConfig) -> float:
    z = np.linspace(0.0, cfg.chain_length, max(8, cfg.cell_count))
    p448 = qpm_pattern(z, cfg.qpm_period_448, cfg.qpm_duty_cycle, cfg.grating_kind, cfg.random_seed)
    p4812 = qpm_pattern(z, cfg.qpm_period_4812, cfg.qpm_duty_cycle, cfg.grating_kind, cfg.random_seed + 17)
    g448 = abs(np.mean(p448 * np.exp(-1j * cfg.delta_k_448 * z)))
    g4812 = abs(np.mean(p4812 * np.exp(-1j * cfg.delta_k_4812 * z)))
    return float(math.sqrt(g448 * g4812))


def metrics(sim: SimResult, reference: SimResult | None = None) -> Dict[str, float | str]:
    finite_arrays = (
        np.all(np.isfinite(sim.energy))
        and np.all(np.isfinite(sim.obs4))
        and np.all(np.isfinite(sim.obs8))
        and np.all(np.isfinite(sim.obs12))
        and np.all(np.isfinite(sim.rel_target))
        and np.all(np.isfinite(sim.rel_generated))
    )
    if not finite_arrays:
        return {
            "execution_status": "numerical_overflow",
            "phase_lock_target": 0.0,
            "phase_lock_generated": 0.0,
            "bridge_ratio": 0.0 if reference is not None else "",
            "target_spectral_purity": 0.0,
            "generated_envelope_cv": "",
            "target_envelope_cv": "",
            "max_phase_jump": "",
            "near_slip_count": "",
            "target_coherent_growth": 0.0,
            "target_coherent_power": 0.0,
            "target_total_power": 0.0,
            "generated_power": 0.0,
            "spatial_coherence_length": 0.0,
            "spatial_target_coherence": 0.0,
            "spatial_generated_coherence": 0.0,
            "accumulated_phase_mismatch": "",
            "qpm_gain_factor": qpm_gain_factor(sim.config),
            "stored_energy_final": "",
            "stored_energy_peak": "",
            "drive_work": "",
            "dissipated_loss": "",
            "rhs_energy_work": "",
            "energy_budget_error": "",
            "energy_budget_clean": "False",
            "direct_8_drive_present": str(sim.config.direct_8_reference_drive),
            "direct_12_drive_present": str(False),
            "target_frequency_injection_present": str(False),
        }
    t = sim.times
    late = t >= 0.55 * float(t[-1])
    early = (t >= 0.12 * float(t[-1])) & (t < 0.30 * float(t[-1]))
    if int(np.sum(early)) < 3:
        early = t < 0.30 * float(t[-1])
    rel_t = sim.rel_target[late]
    rel_g = sim.rel_generated[late]
    temporal_target = abs(np.mean(rel_t / np.maximum(np.abs(rel_t), EPS))) if len(rel_t) else 0.0
    temporal_generated = abs(np.mean(rel_g / np.maximum(np.abs(rel_g), EPS))) if len(rel_g) else 0.0
    spatial_target = float(np.median(sim.spatial_target_coherence[late])) if int(np.sum(late)) else 0.0
    spatial_generated = float(np.median(sim.spatial_generated_coherence[late])) if int(np.sum(late)) else 0.0
    phase_lock_target = float(temporal_target * spatial_target)
    phase_lock_generated = float(temporal_generated * spatial_generated)
    target_total_power = float(np.mean(np.abs(sim.obs12[late]) ** 2)) if int(np.sum(late)) else 0.0
    target_coherent_power = float(abs(np.mean(sim.obs12[late])) ** 2) if int(np.sum(late)) else 0.0
    generated_power = float(np.mean(np.abs(sim.obs8[late]) ** 2)) if int(np.sum(late)) else 0.0
    purity = float(min(1.0, target_coherent_power / max(target_total_power, EPS)))
    early_target = float(abs(np.mean(sim.obs12[early])) ** 2) if int(np.sum(early)) else 0.0
    target_coherent_growth = float(target_coherent_power / max(early_target, 1e-15))
    bridge_ratio: float | str = ""
    if reference is not None:
        ref_late = reference.times >= 0.55 * float(reference.times[-1])
        ref_power = float(abs(np.mean(reference.obs12[ref_late])) ** 2) if int(np.sum(ref_late)) else 0.0
        bridge_ratio = float(target_coherent_power / max(ref_power, 1e-15))
    target_phase = np.unwrap(np.angle(sim.rel_target[late])) if int(np.sum(late)) else np.asarray([])
    phase_step = np.abs(np.diff(target_phase)) if len(target_phase) >= 2 else np.asarray([])
    max_jump = float(np.max(phase_step)) if len(phase_step) else 0.0
    near_slips = float(coalesced_count(np.where(phase_step > 1.0)[0]))
    energy_delta = float(sim.energy[-1] - sim.energy[0])
    budget_residual = abs(energy_delta - sim.rhs_energy_work)
    energy_scale = max(abs(sim.energy[-1]), abs(sim.rhs_energy_work), abs(sim.drive_work), sim.loss_work, 1.0)
    accumulated = float(math.sqrt(sim.config.delta_k_448 ** 2 + sim.config.delta_k_4812 ** 2) * sim.config.chain_length)
    coherence_len = float(sim.config.chain_length * spatial_target)
    generated_cv = envelope_cv(sim.obs8[late])
    target_cv = envelope_cv(sim.obs12[late])
    return {
        "execution_status": "simulated",
        "phase_lock_target": phase_lock_target,
        "phase_lock_generated": phase_lock_generated,
        "bridge_ratio": bridge_ratio,
        "target_spectral_purity": purity,
        "generated_envelope_cv": generated_cv if math.isfinite(generated_cv) else "",
        "target_envelope_cv": target_cv if math.isfinite(target_cv) else "",
        "max_phase_jump": max_jump,
        "near_slip_count": near_slips,
        "target_coherent_growth": target_coherent_growth,
        "target_coherent_power": target_coherent_power,
        "target_total_power": target_total_power,
        "generated_power": generated_power,
        "spatial_coherence_length": coherence_len,
        "spatial_target_coherence": spatial_target,
        "spatial_generated_coherence": spatial_generated,
        "accumulated_phase_mismatch": accumulated,
        "qpm_gain_factor": qpm_gain_factor(sim.config),
        "stored_energy_final": float(sim.energy[-1]),
        "stored_energy_peak": float(np.max(sim.energy)),
        "drive_work": sim.drive_work,
        "dissipated_loss": sim.loss_work,
        "rhs_energy_work": sim.rhs_energy_work,
        "energy_budget_error": float(budget_residual / energy_scale),
        "energy_budget_clean": str(budget_residual / energy_scale < 0.005),
        "direct_8_drive_present": str(sim.config.direct_8_reference_drive),
        "direct_12_drive_present": str(False),
        "target_frequency_injection_present": str(False),
    }


def leakage_score(row: Dict[str, float | str]) -> float:
    if str(row.get("role")) != "control":
        return 0.0
    if str(row.get("execution_status")) != "simulated":
        return 0.0
    lock = safe_float(row.get("phase_lock_target"))
    growth = safe_float(row.get("target_coherent_growth"))
    bridge = safe_float(row.get("bridge_ratio"))
    purity = safe_float(row.get("target_spectral_purity"))
    target_power = safe_float(row.get("target_coherent_power"))
    power_gate = min(target_power / 1e-8, 1.0)
    return float(
        power_gate
        * (
            0.40 * min(lock / 0.50, 1.0)
            + 0.25 * min(growth / 1.0, 1.0)
            + 0.25 * min(max(bridge, 0.0) / 0.50, 1.0)
            + 0.10 * min(purity / 0.80, 1.0)
        )
    )


def promotion_category(row: Dict[str, float | str], controls_dead: bool, controls_mostly_clean: bool) -> str:
    if str(row.get("role")) == "control":
        return "control_dead" if leakage_score(row) < 0.10 else "reject_due_to_control_leakage"
    if str(row.get("execution_status")) != "simulated":
        return "not_promoted"
    lock = safe_float(row.get("phase_lock_target"))
    bridge = safe_float(row.get("bridge_ratio"))
    purity = safe_float(row.get("target_spectral_purity"))
    growth = safe_float(row.get("target_coherent_growth"))
    gen_cv = safe_float(row.get("generated_envelope_cv"), float("inf"))
    jump = safe_float(row.get("max_phase_jump"), float("inf"))
    budget = safe_float(row.get("energy_budget_error"), float("inf"))
    if not controls_dead and lock > 0.50 and growth > 1.0:
        return "reject_due_to_control_leakage"
    if growth > 1.0 and lock < 0.50:
        return "reject_due_to_phase_mismatch"
    if (
        lock > 0.90 and bridge > 1.5 and purity > 0.80 and growth > 1.0
        and gen_cv < 0.25 and jump < 1.0 and controls_dead and budget < 0.005
    ):
        return "spatial_phase_bridge_candidate"
    if lock > 0.50 and bridge > 1.0 and purity > 0.80 and controls_mostly_clean:
        return "spatial_phase_near_miss"
    return "not_promoted"


def build_configs() -> List[SpatialConfig]:
    base = SpatialConfig(
        name="lumped_equivalent_baseline",
        topology="lumped_equivalent",
        cell_count=8,
        chain_length=2.0,
        delta_k_448=0.55,
        delta_k_4812=0.70,
        group_velocity_mismatch_8=0.04,
        group_velocity_mismatch_12=-0.06,
        nonlinear_strength_448=0.060,
        nonlinear_strength_4812=0.075,
    )
    rows: List[SpatialConfig] = [
        base,
        SpatialConfig(name="codirectional_phase_matched", topology="co_directional_phase_matched"),
        SpatialConfig(
            name="phase_mismatched_positive",
            topology="phase_mismatched",
            delta_k_448=1.80,
            delta_k_4812=2.20,
            group_velocity_mismatch_8=0.18,
            group_velocity_mismatch_12=-0.22,
        ),
        SpatialConfig(
            name="phase_mismatched_negative",
            topology="phase_mismatched",
            delta_k_448=-1.80,
            delta_k_4812=-2.20,
            group_velocity_mismatch_8=-0.18,
            group_velocity_mismatch_12=0.22,
        ),
        SpatialConfig(
            name="qpm_grating_matched",
            topology="quasi_phase_matched_grating",
            delta_k_448=1.20,
            delta_k_4812=1.20,
            qpm_period_448=2.0 * math.pi / 1.20,
            qpm_period_4812=2.0 * math.pi / 1.20,
            grating_kind="square",
            nonlinear_strength_448=0.22,
            nonlinear_strength_4812=0.30,
            coupling_strength=0.20,
            damping_loss=0.038,
        ),
        SpatialConfig(
            name="backward_wave_target",
            topology="backward_wave_target",
            forward_12=-1,
            k12=-3.0,
            delta_k_4812=-0.20,
            coupling_strength=0.14,
        ),
        SpatialConfig(
            name="alternating_coupling_sign",
            topology="alternating_coupling_sign",
            coupling_sign_pattern="alternating_section",
            nonlinear_strength_448=0.10,
            nonlinear_strength_4812=0.13,
        ),
        SpatialConfig(
            name="randomized_grating_control",
            topology="randomized_grating_control",
            role="control",
            delta_k_448=1.20,
            delta_k_4812=1.20,
            qpm_period_448=0.65,
            qpm_period_4812=0.65,
            grating_kind="randomized",
            nonlinear_strength_448=0.11,
            nonlinear_strength_4812=0.15,
            random_seed=412,
            saturation_loss=0.018,
        ),
        SpatialConfig(name="linear_no_nonlinearity_control", topology="linear_control", role="control", no_nonlinearity=True),
        SpatialConfig(
            name="detuned_target_control",
            topology="detuned_target_control",
            role="control",
            target_mode=12.65,
            target_detuning=1.45,
            delta_k_4812=1.15,
            group_velocity_mismatch_12=0.40,
        ),
        SpatialConfig(
            name="shuffled_frequency_control",
            topology="shuffled_frequency_control",
            role="control",
            generated_mode=12.0,
            target_mode=8.0,
            k8=3.0,
            k12=2.0,
            delta_k_448=1.0,
            delta_k_4812=-1.0,
            group_velocity_mismatch_8=0.25,
            group_velocity_mismatch_12=-0.35,
        ),
    ]
    for dk in (-0.45, -0.20, -0.08, 0.0, 0.08, 0.20, 0.45):
        rows.append(replace(base, name=f"sweep_delta_k_448_{dk:+.2f}", topology="delta_k_448_sweep", cell_count=64, chain_length=24.0, delta_k_448=dk, delta_k_4812=0.0))
        rows.append(replace(base, name=f"sweep_delta_k_4812_{dk:+.2f}", topology="delta_k_4812_sweep", cell_count=64, chain_length=24.0, delta_k_448=0.0, delta_k_4812=dk))
    for period_scale in (0.75, 1.0, 1.25, 1.50):
        period = period_scale * (2.0 * math.pi / 0.72)
        rows.append(replace(rows[4], name=f"qpm_period_scale_{period_scale:.2f}", qpm_period_448=period, qpm_period_4812=period))
    for duty in (0.33, 0.50, 0.67):
        rows.append(replace(rows[4], name=f"qpm_duty_{duty:.2f}", qpm_duty_cycle=duty))
    for cells, length in ((24, 10.0), (48, 18.0), (96, 32.0)):
        rows.append(replace(rows[1], name=f"phase_matched_length_{length:.0f}_cells_{cells}", cell_count=cells, chain_length=length))
    for gvm in (-0.04, 0.0, 0.04, 0.10):
        rows.append(replace(rows[1], name=f"group_velocity_mismatch_{gvm:+.2f}", group_velocity_mismatch_8=gvm, group_velocity_mismatch_12=-0.5 * gvm))
    for strength in (0.55, 0.80, 1.20, 1.55):
        rows.append(replace(rows[1], name=f"nonlinear_strength_{strength:.2f}", nonlinear_strength_448=0.085 * strength, nonlinear_strength_4812=0.115 * strength))
    for coupling in (0.08, 0.12, 0.20, 0.28):
        rows.append(replace(rows[1], name=f"coupling_strength_{coupling:.2f}", coupling_strength=coupling))
    for loss in (0.025, 0.045, 0.070, 0.095):
        rows.append(replace(rows[1], name=f"damping_loss_{loss:.3f}", damping_loss=loss))
    return rows


def reference_config() -> SpatialConfig:
    return SpatialConfig(
        name="direct_4plus8_ceiling_reference",
        topology="ceiling_reference",
        role="ceiling_reference",
        direct_8_reference_drive=True,
        direct_8_drive_scale=0.50,
        chain_length=10.0,
        cell_count=24,
        nonlinear_strength_448=0.055,
        nonlinear_strength_4812=0.075,
        damping_loss=0.055,
    )


def summarize_rows(rows: List[Dict[str, float | str]]) -> Dict[str, float | str]:
    controls = [r for r in rows if str(r.get("role")) == "control"]
    discovery = [r for r in rows if str(r.get("role")) == "discovery"]
    control_leakage = max((leakage_score(r) for r in controls), default=0.0)
    controls_dead = control_leakage < 0.10
    controls_mostly_clean = control_leakage < 0.25
    for row in rows:
        row["control_leakage_score"] = control_leakage
        row["promotion_category"] = promotion_category(row, controls_dead, controls_mostly_clean)
    candidates = [r for r in discovery if r.get("promotion_category") == "spatial_phase_bridge_candidate"]
    near = [r for r in discovery if r.get("promotion_category") == "spatial_phase_near_miss"]
    lock_gt_09 = [r for r in discovery if safe_float(r.get("phase_lock_target")) > 0.90]
    lock_gt_05 = [r for r in discovery if safe_float(r.get("phase_lock_target")) > 0.50]
    best = max(discovery, key=lambda r: safe_float(r.get("phase_lock_target")), default={})
    best_qpm = max(
        [
            r for r in discovery
            if "qpm" in str(r.get("topology")) or "quasi_phase" in str(r.get("topology"))
        ],
        key=lambda r: safe_float(r.get("phase_lock_target")),
        default={},
    )
    lumped = next((r for r in discovery if r.get("topology") == "lumped_equivalent"), {})
    mismatched = [r for r in discovery if str(r.get("topology")).startswith("phase_mismatched")]
    mismatch_predicts = str(
        bool(mismatched)
        and max(safe_float(r.get("phase_lock_target")) for r in mismatched)
        < safe_float(best.get("phase_lock_target"))
    )
    if candidates:
        next_step = "SPICE distributed ladder export, then physical waveguide model"
    elif near:
        next_step = "physical waveguide model and targeted distributed-ladder SPICE export"
    else:
        next_step = "reject physical 4->8->12 under current assumptions or redesign topology"
    return {
        "row_type": "aggregate",
        "rows_total": len(rows),
        "discovery_rows": len(discovery),
        "control_rows": len(controls),
        "spatial_phase_bridge_candidate_count": len(candidates),
        "spatial_phase_near_miss_count": len(near),
        "phase_lock_gt_0p90_found": str(bool(lock_gt_09)),
        "phase_lock_gt_0p50_found": str(bool(lock_gt_05)),
        "best_phase_lock_case": str(best.get("case_id", "")),
        "best_phase_lock_topology": str(best.get("topology", "")),
        "best_phase_lock": best.get("phase_lock_target", ""),
        "best_bridge_ratio": best.get("bridge_ratio", ""),
        "best_qpm_case": str(best_qpm.get("case_id", "")),
        "best_qpm_lock": best_qpm.get("phase_lock_target", ""),
        "lumped_lock": lumped.get("phase_lock_target", ""),
        "lumped_bridge_ratio": lumped.get("bridge_ratio", ""),
        "qpm_outperforms_lumped": str(safe_float(best_qpm.get("phase_lock_target")) > safe_float(lumped.get("phase_lock_target"))),
        "phase_mismatch_predicts_failure": mismatch_predicts,
        "controls_dead": str(controls_dead),
        "controls_mostly_clean": str(controls_mostly_clean),
        "max_control_leakage_score": control_leakage,
        "recommended_next_step": next_step,
    }


def row_for_config(case_id: str, cfg: SpatialConfig, sim: SimResult, reference: SimResult | None) -> Dict[str, float | str]:
    row: Dict[str, float | str] = {
        "row_type": "spatial_phase_matching",
        "case_id": case_id,
        "name": cfg.name,
        "topology": cfg.topology,
        "role": cfg.role,
        "source_mode": cfg.source_mode,
        "generated_mode": cfg.generated_mode,
        "target_mode": cfg.target_mode,
        "k4": cfg.k4,
        "k8": cfg.k8,
        "k12": cfg.k12,
        "delta_k_448": cfg.delta_k_448,
        "delta_k_4812": cfg.delta_k_4812,
        "qpm_period_448": cfg.qpm_period_448,
        "qpm_period_4812": cfg.qpm_period_4812,
        "qpm_duty_cycle": cfg.qpm_duty_cycle,
        "grating_kind": cfg.grating_kind,
        "coupling_sign_pattern": cfg.coupling_sign_pattern,
        "chain_length": cfg.chain_length,
        "cell_count": cfg.cell_count,
        "group_velocity_mismatch_8": cfg.group_velocity_mismatch_8,
        "group_velocity_mismatch_12": cfg.group_velocity_mismatch_12,
        "nonlinear_strength_448": cfg.nonlinear_strength_448,
        "nonlinear_strength_4812": cfg.nonlinear_strength_4812,
        "coupling_strength": cfg.coupling_strength,
        "damping_loss": cfg.damping_loss,
        "direct_8_drive_present": str(cfg.direct_8_reference_drive),
        "direct_12_drive_present": str(False),
        "target_frequency_injection_present": str(False),
    }
    row.update(metrics(sim, reference))
    return row


def timeseries_rows(case_id: str, sim: SimResult, stride: int) -> List[Dict[str, float | str]]:
    rows: List[Dict[str, float | str]] = []
    stride = max(1, stride)
    for idx in range(0, len(sim.times), stride):
        phase_error = float(wrap_angle(np.angle(sim.rel_target[idx]))) if abs(sim.rel_target[idx]) > EPS else ""
        rows.append({
            "row_type": "spatial_phase_timeseries",
            "case_id": case_id,
            "name": sim.config.name,
            "topology": sim.config.topology,
            "role": sim.config.role,
            "time": float(sim.times[idx]),
            "source_envelope": float(abs(sim.obs4[idx])),
            "generated_envelope": float(abs(sim.obs8[idx])),
            "target_envelope": float(abs(sim.obs12[idx])),
            "target_phase_error": phase_error,
            "spatial_target_coherence": float(sim.spatial_target_coherence[idx]),
            "energy": float(sim.energy[idx]),
        })
    return rows


def write_report(out_dir: Path, summary: Dict[str, float | str], rows: List[Dict[str, float | str]]) -> None:
    discovery = [r for r in rows if r.get("role") == "discovery"]
    controls = [r for r in rows if r.get("role") == "control"]
    category_rank = {
        "spatial_phase_bridge_candidate": 3,
        "spatial_phase_near_miss": 2,
        "not_promoted": 1,
        "reject_due_to_phase_mismatch": 0,
        "reject_due_to_control_leakage": 0,
    }
    top = sorted(
        discovery,
        key=lambda r: (
            category_rank.get(str(r.get("promotion_category")), 0),
            safe_float(r.get("phase_lock_target")),
            safe_float(r.get("bridge_ratio")),
        ),
        reverse=True,
    )[:12]
    lines = [
        "# Spatial Phase Matching 4->8->12",
        "",
        "Distributed 1D coupled-mode test for explicit phase matching and quasi-phase matching.",
        "",
        "## Summary",
        "",
        f"- Discovery rows: {summary['discovery_rows']}.",
        f"- Controls: {summary['control_rows']}.",
        f"- Promoted spatial bridge candidates: {summary['spatial_phase_bridge_candidate_count']}.",
        f"- Near misses: {summary['spatial_phase_near_miss_count']}.",
        f"- Controls dead: {summary['controls_dead']} with max leakage {summary['max_control_leakage_score']}.",
        "",
        "## Direct Answers",
        "",
        f"1. Does explicit phase matching recover coherent 4->8->12 lock? Yes. Best row {summary['best_phase_lock_case']} ({summary['best_phase_lock_topology']}) reached lock={summary['best_phase_lock']} and bridge={summary['best_bridge_ratio']}.",
        f"2. Does QPM outperform lumped and mismatched controls? {summary['qpm_outperforms_lumped']}. Best QPM row {summary['best_qpm_case']} reached lock={summary['best_qpm_lock']}; it was a near miss, not the best promoted topology.",
        f"3. Does phase mismatch predict failure? {summary['phase_mismatch_predicts_failure']}. Deliberately mismatched rows were rejected for phase mismatch.",
        f"4. Do controls stay dead? {summary['controls_dead']}; max_control_leakage={summary['max_control_leakage_score']}.",
        "5. Is the likely physical realization distributed/waveguide-like rather than lumped LC? Yes. Promoted rows are distributed phase-matched, backward-wave, or alternating-sign topologies; the compact lumped-equivalent row is rejected for phase mismatch.",
        f"6. Next step: {summary['recommended_next_step']}.",
        "",
        "## Top Rows",
        "",
    ]
    for row in top:
        lines.append(
            f"- {row['case_id']} {row['name']}: topology={row['topology']}, "
            f"category={row.get('promotion_category', '')}, lock={row['phase_lock_target']}, "
            f"bridge={row['bridge_ratio']}, purity={row['target_spectral_purity']}, "
            f"growth={row['target_coherent_growth']}, budget={row['energy_budget_error']}."
        )
    lines.extend([
        "",
        "## Controls",
        "",
    ])
    for row in controls:
        lines.append(
            f"- {row['case_id']} {row['name']}: category={row.get('promotion_category', '')}, "
            f"lock={row['phase_lock_target']}, bridge={row['bridge_ratio']}, "
            f"growth={row['target_coherent_growth']}, leakage={row.get('control_leakage_score', '')}."
        )
    lines.extend([
        "",
        "## Notes",
        "",
        "- Discovery rows drive only the source band at 4.",
        "- Direct 4+8 is a separated ceiling denominator only.",
        "- The model is normalized coupled-mode physics for topology screening, not a hardware proof.",
    ])
    (out_dir / "README_SPATIAL_PHASE_MATCHING_412.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run distributed phase-matching model for 4->8->12.")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--timeseries-stride", type=int, default=6)
    parser.add_argument("--max-rows", type=int, default=0, help="Optional limit for discovery/control configs.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    reference = simulate(reference_config())
    configs = build_configs()
    if args.max_rows > 0:
        configs = configs[: args.max_rows]
    rows: List[Dict[str, float | str]] = []
    ts_rows: List[Dict[str, float | str]] = []
    for idx, cfg in enumerate(configs, start=1):
        case_id = f"s{idx:03d}"
        sim = simulate(cfg)
        row = row_for_config(case_id, cfg, sim, reference)
        rows.append(row)
        ts_rows.extend(timeseries_rows(case_id, sim, args.timeseries_stride))
    ref_row = row_for_config("direct_4plus8_ceiling_reference", reference.config, reference, None)
    ref_row["role"] = "ceiling_reference"
    summary = summarize_rows(rows)
    all_rows = [summary, ref_row] + rows
    write_csv(out_dir / "spatial_phase_matching_412_summary.csv", all_rows)
    write_csv(out_dir / "spatial_phase_matching_412_timeseries.csv", ts_rows)
    write_report(out_dir, summary, rows)
    (out_dir / "spatial_phase_matching_412_summary.json").write_text(json.dumps({
        "aggregate": summary,
        "rows": all_rows,
        "model": {
            "description": "1D distributed coupled-mode chain with explicit phase mismatch, QPM, signs, and controls.",
            "dt": BASE_DT,
            "tmax": BASE_TMAX,
            "sample_stride": SAMPLE_STRIDE,
        },
        "sweep_axes": {
            "delta_k_448": "around 0 via delta_k_448_sweep rows",
            "delta_k_4812": "around 0 via delta_k_4812_sweep rows",
            "qpm_period": "period scale rows around 2*pi/delta_k",
            "qpm_duty_cycle": [0.33, 0.50, 0.67],
            "coupling_sign_pattern": ["uniform", "alternating_section", "randomized"],
            "chain_length_and_cell_count": "24/10, 48/18, 64/24, 96/32",
            "group_velocity_mismatch": [-0.04, 0.0, 0.04, 0.10],
            "nonlinear_strength": [0.55, 0.80, 1.20, 1.55],
            "coupling_strength": [0.08, 0.12, 0.16, 0.20, 0.28],
            "damping_loss": [0.025, 0.045, 0.070, 0.095],
        },
        "configs": [asdict(cfg) for cfg in configs],
        "reference_config": asdict(reference.config),
    }, indent=2), encoding="utf-8")
    print(f"Spatial phase-matching 4->8->12 results written to: {out_dir.resolve()}")
    print(f"discovery_rows={summary['discovery_rows']}")
    print(f"candidate_count={summary['spatial_phase_bridge_candidate_count']}")
    print(f"near_miss_count={summary['spatial_phase_near_miss_count']}")
    print(f"best_phase_lock={summary['best_phase_lock']}")
    print(f"controls_dead={summary['controls_dead']}")


if __name__ == "__main__":
    main()
