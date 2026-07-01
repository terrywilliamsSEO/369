#!/usr/bin/env python3
"""Crop-geometry-inspired 40/80/120 kHz acoustic graph screen.

This is a geometry-inspiration experiment, not a claim about crop circles or
messages. It treats several 2D glyph-like layouts as acoustic node graphs and
asks whether source-only 40 kHz drive can produce raw coherent 80/120 kHz
buildup while defeating strict matched geometry controls.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np


OUT_DIR = Path("runs") / "acoustic_412_crop_geometry_array"
SOURCE_HZ = 40_000.0
GENERATED_HZ = 80_000.0
TARGET_HZ = 120_000.0
BASE_VELOCITY_M_S = 800.0
BASE_RADIUS_M = 0.041
BASE_DT = 0.055
BASE_TMAX = 72.0
SAMPLE_STRIDE = 7
EPS = 1.0e-18

CONTROL_KINDS: Tuple[str, ...] = (
    "randomized_positions",
    "radial_distribution_angle_shuffle",
    "ring_only_equivalent",
    "phase_shuffled_source_signs",
    "missing_satellite_nodes",
    "shortened_cropped_geometry",
    "linear_no_nonlinearity",
    "generated_path_suppressed_80",
    "phase_mismatched_120",
    "sensor_artifact_control",
)


@dataclass(frozen=True)
class GeometryConfig:
    case_id: str
    name: str
    family: str
    role: str
    positions: Tuple[Tuple[float, float], ...]
    edges: Tuple[Tuple[int, int, float], ...]
    source_nodes: Tuple[int, ...]
    source_signs: Tuple[float, ...]
    parent_case_id: str = ""
    control_kind: str = ""
    phase_velocity_4_m_s: float = BASE_VELOCITY_M_S
    phase_velocity_8_ratio: float = 0.992
    phase_velocity_12_ratio: float = 0.984
    coupling_strength: float = 0.66
    damping_loss: float = 0.038
    boundary_absorption: float = 0.018
    nonlinear_448: float = 0.125
    nonlinear_4812: float = 0.210
    generated_path_scale: float = 1.0
    target_path_scale: float = 1.0
    drive_amplitude: float = 0.305
    no_nonlinearity: bool = False
    target_detuning: float = 0.0
    generated_detuning: float = 0.0
    sensor_artifact_drive: bool = False
    readout_feedthrough: float = 0.018
    notes: str = ""


@dataclass
class GeometryResult:
    config: GeometryConfig
    times: np.ndarray
    tap_a4: np.ndarray
    tap_a8: np.ndarray
    tap_a12: np.ndarray
    node_a4: np.ndarray
    node_a8: np.ndarray
    node_a12: np.ndarray
    tap_indices: List[int]
    output_indices: List[int]
    graph_distances_m: np.ndarray
    drive_work: float
    loss_work: float


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: Sequence[str] | None = None) -> None:
    if not rows and fieldnames is None:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    if fieldnames is not None:
        keys = [str(key) for key in fieldnames]
    else:
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
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def sanitize(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(key): sanitize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [sanitize(value) for value in obj]
    if isinstance(obj, tuple):
        return [sanitize(value) for value in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def wrap_pi(value: np.ndarray | float) -> np.ndarray | float:
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


def deterministic_seed(label: str) -> int:
    return 7919 + sum((idx + 1) * ord(ch) for idx, ch in enumerate(label)) % 1_000_000


def pair_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unique_points(points: Iterable[Tuple[float, float]], digits: int = 7) -> Tuple[Tuple[float, float], ...]:
    seen = set()
    out: List[Tuple[float, float]] = []
    for x, y in points:
        key = (round(x, digits), round(y, digits))
        if key in seen:
            continue
        seen.add(key)
        out.append((float(x), float(y)))
    return tuple(out)


def sorted_edge(i: int, j: int, weight: float = 1.0) -> Tuple[int, int, float]:
    if i == j:
        raise ValueError("self edge")
    return (i, j, weight) if i < j else (j, i, weight)


def edge_length_weight(positions: Sequence[Tuple[float, float]], i: int, j: int, scale: float) -> Tuple[int, int, float]:
    dist = pair_distance(positions[i], positions[j])
    return sorted_edge(i, j, math.exp(-dist / max(scale, EPS)))


def add_edge(edges: set[Tuple[int, int, float]], positions: Sequence[Tuple[float, float]], i: int, j: int, scale: float) -> None:
    if i == j:
        return
    edges.add(edge_length_weight(positions, i, j, scale))


def k_nearest_edges(positions: Sequence[Tuple[float, float]], k: int = 3, scale: float = 0.014) -> Tuple[Tuple[int, int, float], ...]:
    edges: set[Tuple[int, int, float]] = set()
    n = len(positions)
    for i in range(n):
        distances = sorted((pair_distance(positions[i], positions[j]), j) for j in range(n) if j != i)
        for _dist, j in distances[:k]:
            add_edge(edges, positions, i, j, scale)
    return tuple(sorted(edges))


def polar_points(radius: float, count: int, phase: float = 0.0) -> List[Tuple[float, float]]:
    return [
        (radius * math.cos(phase + 2.0 * math.pi * idx / count), radius * math.sin(phase + 2.0 * math.pi * idx / count))
        for idx in range(count)
    ]


def ring_edges(
    positions: Sequence[Tuple[float, float]],
    rings: Sequence[Sequence[int]],
    center: int | None = None,
    scale: float = 0.014,
) -> Tuple[Tuple[int, int, float], ...]:
    edges: set[Tuple[int, int, float]] = set()
    for ring in rings:
        if len(ring) < 2:
            continue
        for idx, i in enumerate(ring):
            add_edge(edges, positions, i, ring[(idx + 1) % len(ring)], scale)
            if center is not None:
                add_edge(edges, positions, center, i, scale)
    for a, b in zip(rings, rings[1:]):
        for idx, i in enumerate(a):
            j = b[int(round(idx * len(b) / max(len(a), 1))) % len(b)]
            add_edge(edges, positions, i, j, scale)
    return tuple(sorted(edges))


def make_config(
    case_id: str,
    family: str,
    positions: Sequence[Tuple[float, float]],
    edges: Sequence[Tuple[int, int, float]],
    source_nodes: Sequence[int],
    source_signs: Sequence[float] | None = None,
    role: str = "discovery",
    parent_case_id: str = "",
    control_kind: str = "",
    name: str | None = None,
    notes: str = "",
    **updates: object,
) -> GeometryConfig:
    source_nodes_tuple = tuple(int(idx) for idx in source_nodes if 0 <= int(idx) < len(positions))
    if not source_nodes_tuple:
        source_nodes_tuple = (0,)
    signs = tuple(float(v) for v in (source_signs if source_signs is not None else [1.0] * len(source_nodes_tuple)))
    if len(signs) != len(source_nodes_tuple):
        signs = tuple([1.0] * len(source_nodes_tuple))
    cfg = GeometryConfig(
        case_id=case_id,
        name=name or family,
        family=family,
        role=role,
        positions=tuple((float(x), float(y)) for x, y in positions),
        edges=tuple(edges),
        source_nodes=source_nodes_tuple,
        source_signs=signs,
        parent_case_id=parent_case_id,
        control_kind=control_kind,
        notes=notes,
    )
    if updates:
        cfg = replace(cfg, **updates)
    return cfg


def concentric_rings(case_id: str = "g001") -> GeometryConfig:
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    rings: List[List[int]] = []
    for radius, count, phase in ((0.010, 8, 0.0), (0.020, 16, math.pi / 16.0), (0.031, 24, 0.0)):
        start = len(points)
        points.extend(polar_points(radius, count, phase))
        rings.append(list(range(start, start + count)))
    edges = ring_edges(points, rings, center=0, scale=0.013)
    sources = (0, rings[0][0], rings[0][2], rings[0][4], rings[0][6])
    return make_config(case_id, "concentric_rings", points, edges, sources, name="concentric_rings")


def concentric_rings_with_satellite_nodes(case_id: str = "g002") -> GeometryConfig:
    base = concentric_rings(case_id)
    points = list(base.positions)
    outer = list(range(len(points), len(points) + 12))
    points.extend(polar_points(0.039, 12, math.pi / 12.0))
    edges = set(base.edges)
    for idx, node in enumerate(outer):
        nearest = min(range(len(base.positions)), key=lambda j: pair_distance(points[node], points[j]))
        add_edge(edges, points, node, nearest, 0.013)
        add_edge(edges, points, node, outer[(idx + 1) % len(outer)], 0.013)
    sources = (0, 1, 3, 5, 7)
    return make_config(
        case_id,
        "concentric_rings_with_satellite_nodes",
        points,
        tuple(sorted(edges)),
        sources,
        name="concentric_rings_with_satellite_nodes",
        nonlinear_4812=0.225,
        target_path_scale=1.10,
    )


def flower_of_life_overlap_lattice(case_id: str = "g003") -> GeometryConfig:
    radius = 0.012
    centers = [(0.0, 0.0)] + polar_points(radius, 6, 0.0)
    points: List[Tuple[float, float]] = []
    for cx, cy in centers:
        points.append((cx, cy))
        points.extend(polar_points(radius, 6, math.pi / 6.0 + math.atan2(cy, cx) if cx or cy else math.pi / 6.0))
        for idx in range(6):
            angle = 2.0 * math.pi * idx / 6.0
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    points = list(unique_points(points))
    edges = k_nearest_edges(points, k=4, scale=0.012)
    sources = tuple(sorted(range(len(points)), key=lambda i: pair_distance(points[i], (0.0, 0.0)))[:7])
    return make_config(
        case_id,
        "flower_of_life_overlap_lattice",
        points,
        edges,
        sources,
        name="flower_of_life_overlap_lattice",
        nonlinear_448=0.135,
        nonlinear_4812=0.230,
    )


def radial_spoke_wheel(case_id: str = "g004") -> GeometryConfig:
    spokes = 12
    radial_steps = (0.008, 0.016, 0.025, 0.034)
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    rings: List[List[int]] = []
    for ridx, radius in enumerate(radial_steps):
        ring: List[int] = []
        for idx in range(spokes):
            angle = 2.0 * math.pi * idx / spokes + (math.pi / spokes if ridx % 2 else 0.0)
            ring.append(len(points))
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
        rings.append(ring)
    edges = set(ring_edges(points, rings, center=0, scale=0.013))
    for idx in range(spokes):
        last = 0
        for ring in rings:
            node = ring[idx]
            add_edge(edges, points, last, node, 0.013)
            last = node
    sources = (0,) + tuple(rings[0][idx] for idx in (0, 3, 6, 9))
    return make_config(case_id, "radial_spoke_wheel", points, tuple(sorted(edges)), sources, name="radial_spoke_wheel")


def spiral_petal_pattern(case_id: str = "g005") -> GeometryConfig:
    arms = 6
    steps = 7
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    arm_nodes: List[List[int]] = []
    for arm in range(arms):
        nodes: List[int] = []
        base = 2.0 * math.pi * arm / arms
        for step in range(1, steps + 1):
            r = 0.0055 * step
            theta = base + 0.34 * step
            nodes.append(len(points))
            points.append((r * math.cos(theta), r * math.sin(theta)))
        arm_nodes.append(nodes)
    edges: set[Tuple[int, int, float]] = set()
    for nodes in arm_nodes:
        add_edge(edges, points, 0, nodes[0], 0.013)
        for a, b in zip(nodes, nodes[1:]):
            add_edge(edges, points, a, b, 0.013)
    for step in range(steps):
        ring = [nodes[step] for nodes in arm_nodes]
        for idx, node in enumerate(ring):
            add_edge(edges, points, node, ring[(idx + 1) % len(ring)], 0.013)
    sources = (0,) + tuple(nodes[0] for nodes in arm_nodes[::2])
    return make_config(
        case_id,
        "spiral_petal_pattern",
        points,
        tuple(sorted(edges)),
        sources,
        name="spiral_petal_pattern",
        phase_velocity_12_ratio=0.990,
        target_path_scale=1.12,
    )


def broken_ring_glyph_pattern(case_id: str = "g006") -> GeometryConfig:
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    rings: List[List[int]] = []
    for radius, count, phase, skip_mod in ((0.012, 12, 0.0, 5), (0.024, 24, math.pi / 24.0, 7), (0.036, 36, 0.0, 6)):
        ring: List[int] = []
        for idx in range(count):
            if idx % skip_mod == 0:
                continue
            angle = phase + 2.0 * math.pi * idx / count
            ring.append(len(points))
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
        rings.append(ring)
    edges = set(ring_edges(points, rings, center=0, scale=0.013))
    for ring in rings:
        for idx in range(0, len(ring), max(2, len(ring) // 6)):
            add_edge(edges, points, 0, ring[idx], 0.013)
    sources = (0,) + tuple(rings[0][idx] for idx in range(0, min(len(rings[0]), 6), 2))
    return make_config(
        case_id,
        "broken_ring_glyph_pattern",
        points,
        tuple(sorted(edges)),
        sources,
        name="broken_ring_glyph_pattern",
        damping_loss=0.034,
    )


def straight_guide_baseline(case_id: str = "g007") -> GeometryConfig:
    count = 42
    length = 0.041
    points = [(-length / 2.0 + length * idx / (count - 1), 0.0) for idx in range(count)]
    edges: set[Tuple[int, int, float]] = set()
    for idx in range(count - 1):
        add_edge(edges, points, idx, idx + 1, 0.010)
    for idx in range(count - 2):
        add_edge(edges, points, idx, idx + 2, 0.010)
    sources = (0, 1, 2)
    return make_config(
        case_id,
        "straight_guide_baseline",
        points,
        tuple(sorted(edges)),
        sources,
        name="straight_guide_baseline",
        damping_loss=0.040,
        target_path_scale=1.02,
    )


def simple_ring_baseline(case_id: str = "g008") -> GeometryConfig:
    points: List[Tuple[float, float]] = [(0.0, 0.0)] + polar_points(0.026, 36, 0.0)
    ring = list(range(1, len(points)))
    edges = ring_edges(points, [ring], center=0, scale=0.013)
    sources = (0, 1, 10, 19, 28)
    return make_config(case_id, "simple_ring_baseline", points, edges, sources, name="simple_ring_baseline")


def discovery_geometries() -> List[GeometryConfig]:
    return [
        concentric_rings("g001"),
        concentric_rings_with_satellite_nodes("g002"),
        flower_of_life_overlap_lattice("g003"),
        radial_spoke_wheel("g004"),
        spiral_petal_pattern("g005"),
        broken_ring_glyph_pattern("g006"),
        straight_guide_baseline("g007"),
        simple_ring_baseline("g008"),
    ]


def relabel_control(cfg: GeometryConfig, control_kind: str, positions: Sequence[Tuple[float, float]], edges: Sequence[Tuple[int, int, float]], source_nodes: Sequence[int], source_signs: Sequence[float] | None = None, **updates: object) -> GeometryConfig:
    return make_config(
        case_id=f"{cfg.case_id}_{control_kind}",
        family=cfg.family,
        positions=positions,
        edges=edges,
        source_nodes=source_nodes,
        source_signs=source_signs,
        role="control",
        parent_case_id=cfg.case_id,
        control_kind=control_kind,
        name=control_kind,
        notes=f"Matched control for {cfg.case_id}: {control_kind}",
        **updates,
    )


def centroid(positions: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    return (float(sum(xs) / max(len(xs), 1)), float(sum(ys) / max(len(ys), 1)))


def source_nodes_for_positions(positions: Sequence[Tuple[float, float]], source_count: int) -> Tuple[int, ...]:
    c = centroid(positions)
    return tuple(sorted(range(len(positions)), key=lambda idx: pair_distance(positions[idx], c))[:max(1, source_count)])


def randomized_positions_control(cfg: GeometryConfig) -> GeometryConfig:
    rng = np.random.default_rng(deterministic_seed(cfg.case_id + "_random"))
    radii = [pair_distance(p, centroid(cfg.positions)) for p in cfg.positions]
    max_r = max(radii) if radii else BASE_RADIUS_M
    positions = []
    for _ in cfg.positions:
        r = max_r * math.sqrt(float(rng.random()))
        theta = float(rng.random()) * 2.0 * math.pi
        positions.append((r * math.cos(theta), r * math.sin(theta)))
    edges = k_nearest_edges(positions, k=3, scale=0.013)
    sources = source_nodes_for_positions(positions, len(cfg.source_nodes))
    return relabel_control(cfg, "randomized_positions", positions, edges, sources)


def radial_angle_shuffle_control(cfg: GeometryConfig) -> GeometryConfig:
    rng = np.random.default_rng(deterministic_seed(cfg.case_id + "_angle_shuffle"))
    c = centroid(cfg.positions)
    radii = [pair_distance(p, c) for p in cfg.positions]
    angles = [math.atan2(p[1] - c[1], p[0] - c[0]) for p in cfg.positions]
    rng.shuffle(angles)
    positions = [(r * math.cos(theta), r * math.sin(theta)) for r, theta in zip(radii, angles)]
    edges = k_nearest_edges(positions, k=3, scale=0.013)
    sources = source_nodes_for_positions(positions, len(cfg.source_nodes))
    return relabel_control(cfg, "radial_distribution_angle_shuffle", positions, edges, sources)


def ring_only_control(cfg: GeometryConfig) -> GeometryConfig:
    n = len(cfg.positions)
    c = centroid(cfg.positions)
    radii = sorted(pair_distance(p, c) for p in cfg.positions)
    ring_counts = [max(6, n // 5), max(8, n // 4), max(10, n - max(6, n // 5) - max(8, n // 4) - 1)]
    ring_counts = [count for count in ring_counts if count > 0]
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    rings: List[List[int]] = []
    cursor = 0
    for ridx, count in enumerate(ring_counts):
        if len(points) >= n:
            break
        count = min(count, n - len(points))
        sample = radii[min(len(radii) - 1, cursor + max(count // 2, 0))]
        radius = max(sample, 0.004 + 0.009 * (ridx + 1))
        start = len(points)
        points.extend(polar_points(radius, count, math.pi / max(count, 1) if ridx % 2 else 0.0))
        rings.append(list(range(start, start + count)))
        cursor += count
    while len(points) < n:
        points.append((0.038 * math.cos(len(points)), 0.038 * math.sin(len(points))))
    edges = ring_edges(points, rings, center=0, scale=0.013)
    sources = source_nodes_for_positions(points, len(cfg.source_nodes))
    return relabel_control(cfg, "ring_only_equivalent", points, edges, sources)


def phase_shuffled_source_control(cfg: GeometryConfig) -> GeometryConfig:
    rng = np.random.default_rng(deterministic_seed(cfg.case_id + "_source_signs"))
    signs = tuple(float(rng.choice(np.asarray([-1.0, 1.0]))) for _ in cfg.source_nodes)
    if all(sign > 0.0 for sign in signs):
        signs = tuple(-1.0 if idx == 0 else 1.0 for idx, _ in enumerate(signs))
    return relabel_control(cfg, "phase_shuffled_source_signs", cfg.positions, cfg.edges, cfg.source_nodes, signs)


def missing_satellite_control(cfg: GeometryConfig) -> GeometryConfig:
    c = centroid(cfg.positions)
    radii = np.asarray([pair_distance(p, c) for p in cfg.positions], dtype=float)
    if len(radii) <= 10:
        keep = list(range(len(cfg.positions)))
    else:
        threshold = float(np.quantile(radii, 0.82))
        keep = [idx for idx, radius in enumerate(radii) if radius < threshold or idx in cfg.source_nodes]
        if len(keep) > len(cfg.positions) - 2:
            keep = list(np.argsort(radii)[: max(6, int(0.72 * len(cfg.positions)))])
    mapping = {old: new for new, old in enumerate(keep)}
    positions = [cfg.positions[idx] for idx in keep]
    edges = [
        (mapping[i], mapping[j], w)
        for i, j, w in cfg.edges
        if i in mapping and j in mapping and mapping[i] != mapping[j]
    ]
    if not edges:
        edges = list(k_nearest_edges(positions, k=3, scale=0.013))
    sources = tuple(mapping[idx] for idx in cfg.source_nodes if idx in mapping)
    if not sources:
        sources = source_nodes_for_positions(positions, len(cfg.source_nodes))
    return relabel_control(cfg, "missing_satellite_nodes", positions, tuple(edges), sources)


def shortened_cropped_control(cfg: GeometryConfig) -> GeometryConfig:
    c = centroid(cfg.positions)
    radii = np.asarray([pair_distance(p, c) for p in cfg.positions], dtype=float)
    keep_count = max(6, int(round(0.66 * len(cfg.positions))))
    keep = list(np.argsort(radii)[:keep_count])
    keep.extend(idx for idx in cfg.source_nodes if idx not in keep)
    keep = sorted(set(keep))
    mapping = {old: new for new, old in enumerate(keep)}
    positions = [cfg.positions[idx] for idx in keep]
    edges = [
        (mapping[i], mapping[j], w)
        for i, j, w in cfg.edges
        if i in mapping and j in mapping and mapping[i] != mapping[j]
    ]
    if not edges:
        edges = list(k_nearest_edges(positions, k=3, scale=0.013))
    sources = tuple(mapping[idx] for idx in cfg.source_nodes if idx in mapping)
    if not sources:
        sources = source_nodes_for_positions(positions, len(cfg.source_nodes))
    return relabel_control(cfg, "shortened_cropped_geometry", positions, tuple(edges), sources)


def matched_controls(cfg: GeometryConfig) -> List[GeometryConfig]:
    return [
        randomized_positions_control(cfg),
        radial_angle_shuffle_control(cfg),
        ring_only_control(cfg),
        phase_shuffled_source_control(cfg),
        missing_satellite_control(cfg),
        shortened_cropped_control(cfg),
        relabel_control(cfg, "linear_no_nonlinearity", cfg.positions, cfg.edges, cfg.source_nodes, cfg.source_signs, no_nonlinearity=True, nonlinear_448=0.0, nonlinear_4812=0.0, generated_path_scale=0.0, target_path_scale=0.0),
        relabel_control(cfg, "generated_path_suppressed_80", cfg.positions, cfg.edges, cfg.source_nodes, cfg.source_signs, nonlinear_448=0.010, generated_path_scale=0.035),
        relabel_control(cfg, "phase_mismatched_120", cfg.positions, cfg.edges, cfg.source_nodes, cfg.source_signs, phase_velocity_12_ratio=0.865, target_detuning=0.55),
        relabel_control(cfg, "sensor_artifact_control", cfg.positions, cfg.edges, cfg.source_nodes, cfg.source_signs, no_nonlinearity=True, nonlinear_448=0.0, nonlinear_4812=0.0, generated_path_scale=0.0, target_path_scale=0.0, sensor_artifact_drive=True, readout_feedthrough=0.040),
    ]


def build_configs() -> List[GeometryConfig]:
    rows: List[GeometryConfig] = []
    for cfg in discovery_geometries():
        rows.append(cfg)
        rows.extend(matched_controls(cfg))
    return rows


def adjacency_matrices(cfg: GeometryConfig) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(cfg.positions)
    weights = np.zeros((n, n), dtype=float)
    distances = np.zeros((n, n), dtype=float)
    for i, j, weight in cfg.edges:
        dist = pair_distance(cfg.positions[i], cfg.positions[j])
        w = max(float(weight), 1.0e-6)
        weights[i, j] += w
        weights[j, i] += w
        distances[i, j] = dist
        distances[j, i] = dist
    if not np.any(weights):
        for i, j, weight in k_nearest_edges(cfg.positions, k=2, scale=0.013):
            dist = pair_distance(cfg.positions[i], cfg.positions[j])
            weights[i, j] += weight
            weights[j, i] += weight
            distances[i, j] = dist
            distances[j, i] = dist
    degree = np.sum(weights, axis=1)
    norm = weights / np.maximum(degree[:, None], EPS)
    k4, k8, k12 = wave_numbers(cfg)
    p4 = norm * np.exp(-1j * k4 * distances)
    p8 = norm * np.exp(-1j * k8 * distances)
    p12 = norm * np.exp(-1j * k12 * distances)
    return norm, p4, p8, p12, distances


def graph_distances(cfg: GeometryConfig) -> np.ndarray:
    n = len(cfg.positions)
    adj: List[List[Tuple[int, float]]] = [[] for _ in range(n)]
    for i, j, _w in cfg.edges:
        dist = pair_distance(cfg.positions[i], cfg.positions[j])
        adj[i].append((j, dist))
        adj[j].append((i, dist))
    distances = np.full(n, np.inf, dtype=float)
    heap: List[Tuple[float, int]] = []
    for src in cfg.source_nodes:
        distances[src] = 0.0
        heapq.heappush(heap, (0.0, src))
    while heap:
        d, node = heapq.heappop(heap)
        if d > distances[node]:
            continue
        for nxt, weight in adj[node]:
            cand = d + weight
            if cand < distances[nxt]:
                distances[nxt] = cand
                heapq.heappush(heap, (cand, nxt))
    fallback = np.asarray([pair_distance(cfg.positions[idx], centroid(cfg.positions)) for idx in range(n)], dtype=float)
    distances = np.where(np.isfinite(distances), distances, fallback)
    return distances


def wave_numbers(cfg: GeometryConfig) -> Tuple[float, float, float]:
    v4 = cfg.phase_velocity_4_m_s
    v8 = cfg.phase_velocity_4_m_s * cfg.phase_velocity_8_ratio
    v12 = cfg.phase_velocity_4_m_s * cfg.phase_velocity_12_ratio
    return (
        2.0 * math.pi * SOURCE_HZ / v4,
        2.0 * math.pi * GENERATED_HZ / v8,
        2.0 * math.pi * TARGET_HZ / v12,
    )


def acoustic_numbers(cfg: GeometryConfig) -> Dict[str, float]:
    k4, k8, k12 = wave_numbers(cfg)
    d448 = k8 - 2.0 * k4
    d4812 = k12 - k8 - k4
    limiting = max(abs(d448), abs(d4812))
    return {
        "source_frequency_hz": SOURCE_HZ,
        "generated_frequency_hz": GENERATED_HZ,
        "target_frequency_hz": TARGET_HZ,
        "phase_velocity_4_m_s": cfg.phase_velocity_4_m_s,
        "phase_velocity_8_m_s": cfg.phase_velocity_4_m_s * cfg.phase_velocity_8_ratio,
        "phase_velocity_12_m_s": cfg.phase_velocity_4_m_s * cfg.phase_velocity_12_ratio,
        "k40_rad_m": k4,
        "k80_rad_m": k8,
        "k120_rad_m": k12,
        "delta_k_40_40_to_80_rad_m": d448,
        "delta_k_40_80_to_120_rad_m": d4812,
        "limiting_delta_k_rad_m": limiting,
        "coherence_length_m": math.pi / limiting if limiting > EPS else math.inf,
    }


def drive_envelope(t: float, tmax: float = BASE_TMAX) -> float:
    ramp = 0.14 * tmax
    fade = 0.20 * tmax
    return min(1.0, t / max(ramp, EPS), max(0.0, (tmax - t) / max(fade, EPS)))


def source_profile(cfg: GeometryConfig) -> np.ndarray:
    n = len(cfg.positions)
    profile = np.zeros(n, dtype=complex)
    for idx, sign in zip(cfg.source_nodes, cfg.source_signs):
        if 0 <= idx < n:
            profile[idx] += complex(sign)
    if np.max(np.abs(profile)) <= EPS:
        profile[0] = 1.0
    return profile / max(float(np.max(np.abs(profile))), EPS)


def tap_indices(cfg: GeometryConfig, distances: np.ndarray) -> List[int]:
    order = np.argsort(distances)
    if len(order) <= 9:
        return [int(idx) for idx in order]
    taps: List[int] = []
    for frac in np.linspace(0.0, 1.0, 9):
        target = float(np.quantile(distances, frac))
        idx = int(np.argmin(np.abs(distances - target)))
        if idx not in taps:
            taps.append(idx)
    while len(taps) < 9:
        for idx in order:
            raw = int(idx)
            if raw not in taps:
                taps.append(raw)
            if len(taps) >= 9:
                break
    return taps[:9]


def output_indices(distances: np.ndarray) -> List[int]:
    if len(distances) <= 4:
        return [int(np.argmax(distances))]
    threshold = float(np.quantile(distances, 0.84))
    out = [idx for idx, dist in enumerate(distances) if dist >= threshold]
    return out or [int(np.argmax(distances))]


def motif_field(cfg: GeometryConfig, distances: np.ndarray) -> np.ndarray:
    c = centroid(cfg.positions)
    radii = np.asarray([pair_distance(p, c) for p in cfg.positions], dtype=float)
    max_r = max(float(np.max(radii)), EPS)
    angles = np.asarray([math.atan2(p[1] - c[1], p[0] - c[0]) for p in cfg.positions], dtype=float)
    radial = radii / max_r
    glyph = (
        0.34
        + 0.24 * np.cos(6.0 * angles)
        + 0.18 * np.cos(12.0 * angles + 1.7 * radial)
        + 0.24 * np.power(np.clip(radial, 0.0, 1.0), 1.25)
    )
    if cfg.family in {"flower_of_life_overlap_lattice", "spiral_petal_pattern", "broken_ring_glyph_pattern"} and cfg.role == "discovery":
        glyph += 0.12 * np.cos(3.0 * angles - 2.0 * radial)
    return np.clip(glyph, 0.05, 1.45)


def rhs(
    state: np.ndarray,
    t: float,
    cfg: GeometryConfig,
    p4: np.ndarray,
    p8: np.ndarray,
    p12: np.ndarray,
    distances: np.ndarray,
    motif: np.ndarray,
    drive: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, float]]:
    n = len(cfg.positions)
    a4 = state[0:n]
    a8 = state[n:2 * n]
    a12 = state[2 * n:3 * n]
    dist_norm = distances / max(float(np.max(distances)), EPS)
    boundary = cfg.boundary_absorption * np.power(np.clip(dist_norm, 0.0, 1.0), 2.0)
    loss4 = cfg.damping_loss + 0.60 * boundary
    loss8 = 1.08 * cfg.damping_loss + 0.80 * boundary
    loss12 = 0.92 * cfg.damping_loss + 0.18 * boundary
    cpl = cfg.coupling_strength
    d4 = -loss4 * a4 + cpl * (p4 @ a4 - a4)
    d8 = -(loss8 + 1j * cfg.generated_detuning) * a8 + 0.94 * cpl * (p8 @ a8 - a8)
    d12 = -(loss12 + 1j * cfg.target_detuning) * a12 + 0.88 * cpl * (p12 @ a12 - a12)
    env = drive_envelope(t)
    d4 += cfg.drive_amplitude * env * drive

    density = np.abs(a4) ** 2 + np.abs(a8) ** 2 + np.abs(a12) ** 2
    d4 -= 0.006 * density * a4
    d8 -= 0.007 * density * a8
    d12 -= 0.006 * density * a12

    if not cfg.no_nonlinearity:
        nums = acoustic_numbers(cfg)
        phase448 = np.exp(-1j * nums["delta_k_40_40_to_80_rad_m"] * distances)
        phase4812 = np.exp(-1j * nums["delta_k_40_80_to_120_rad_m"] * distances)
        local448 = cfg.nonlinear_448 * cfg.generated_path_scale * motif * (0.30 + 0.95 * np.clip(dist_norm, 0.0, 1.0))
        local4812 = cfg.nonlinear_4812 * cfg.target_path_scale * motif * np.power(np.clip(dist_norm, 0.0, 1.0), 1.18)
        n448 = local448 * a4 * a4 * phase448
        n4812 = local4812 * a4 * a8 * phase4812
        d8 += n448
        d12 += n4812
        d4 -= 0.010 * np.conj(a4) * a8 * np.conj(phase448) * motif
        d4 -= 0.006 * np.conj(a8) * a12 * np.conj(phase4812) * motif
        d8 -= 0.004 * np.conj(a4) * a12 * np.conj(phase4812) * motif

    if cfg.sensor_artifact_drive:
        out = output_indices(distances)
        artifact = np.zeros(n, dtype=complex)
        artifact[out] = cfg.readout_feedthrough * cfg.drive_amplitude * env
        d12 += artifact

    powers = {
        "drive_power": float(np.sum(np.abs(cfg.drive_amplitude * env * drive) ** 2)),
        "loss_power": float(np.sum(loss4 * np.abs(a4) ** 2 + loss8 * np.abs(a8) ** 2 + loss12 * np.abs(a12) ** 2)),
    }
    return np.concatenate([d4, d8, d12]), powers


def rk4_step(
    state: np.ndarray,
    t: float,
    dt: float,
    cfg: GeometryConfig,
    p4: np.ndarray,
    p8: np.ndarray,
    p12: np.ndarray,
    distances: np.ndarray,
    motif: np.ndarray,
    drive: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, float]]:
    k1, p1 = rhs(state, t, cfg, p4, p8, p12, distances, motif, drive)
    k2, _ = rhs(state + 0.5 * dt * k1, t + 0.5 * dt, cfg, p4, p8, p12, distances, motif, drive)
    k3, _ = rhs(state + 0.5 * dt * k2, t + 0.5 * dt, cfg, p4, p8, p12, distances, motif, drive)
    k4, _ = rhs(state + dt * k3, t + dt, cfg, p4, p8, p12, distances, motif, drive)
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4), p1


def simulate(cfg: GeometryConfig) -> GeometryResult:
    _norm, p4, p8, p12, _edge_distances = adjacency_matrices(cfg)
    distances = graph_distances(cfg)
    taps = tap_indices(cfg, distances)
    outputs = output_indices(distances)
    motif = motif_field(cfg, distances)
    drive = source_profile(cfg)
    n = len(cfg.positions)
    state = np.zeros(3 * n, dtype=complex)
    times: List[float] = []
    a4_rows: List[np.ndarray] = []
    a8_rows: List[np.ndarray] = []
    a12_rows: List[np.ndarray] = []
    drive_work = 0.0
    loss_work = 0.0
    steps = int(round(BASE_TMAX / BASE_DT))
    for step in range(steps + 1):
        t = step * BASE_DT
        if step % SAMPLE_STRIDE == 0:
            a4 = state[0:n]
            a8 = state[n:2 * n]
            a12 = state[2 * n:3 * n]
            times.append(t)
            a4_rows.append(a4[taps].copy())
            a8_rows.append(a8[taps].copy())
            a12_rows.append(a12[taps].copy())
        if step == steps:
            break
        state, powers = rk4_step(state, t, BASE_DT, cfg, p4, p8, p12, distances, motif, drive)
        drive_work += powers["drive_power"] * BASE_DT
        loss_work += powers["loss_power"] * BASE_DT
    return GeometryResult(
        config=cfg,
        times=np.asarray(times),
        tap_a4=np.asarray(a4_rows),
        tap_a8=np.asarray(a8_rows),
        tap_a12=np.asarray(a12_rows),
        node_a4=state[0:n].copy(),
        node_a8=state[n:2 * n].copy(),
        node_a12=state[2 * n:3 * n].copy(),
        tap_indices=taps,
        output_indices=outputs,
        graph_distances_m=distances,
        drive_work=drive_work,
        loss_work=loss_work,
    )


def late_mask(result: GeometryResult) -> np.ndarray:
    mask = (result.times >= 0.52 * BASE_TMAX) & (result.times <= 0.76 * BASE_TMAX)
    if int(np.sum(mask)) < 8:
        mask = result.times >= 0.50 * result.times[-1]
    return mask


def settled_tap_phasors(result: GeometryResult) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = late_mask(result)
    return (
        np.mean(result.tap_a4[mask, :], axis=0),
        np.mean(result.tap_a8[mask, :], axis=0),
        np.mean(result.tap_a12[mask, :], axis=0),
    )


def row_power(row: Dict[str, object]) -> float:
    return safe_float(row.get("target_coherent_power_120khz"))


def base_metrics(result: GeometryResult) -> Dict[str, object]:
    cfg = result.config
    ph4, ph8, ph12 = settled_tap_phasors(result)
    amp4 = np.abs(ph4)
    amp8 = np.abs(ph8)
    amp12 = np.abs(ph12)
    non_source = slice(1, None)
    err80 = np.asarray(wrap_pi(np.angle(ph8) - 2.0 * np.angle(ph4)), dtype=float)
    err120 = np.asarray(wrap_pi(np.angle(ph12) - np.angle(ph8) - np.angle(ph4)), dtype=float)
    lock80 = phase_lock(err80[non_source], amp8[non_source] * np.maximum(amp4[non_source] ** 2, EPS))
    lock120 = phase_lock(err120[non_source], amp12[non_source] * np.maximum(amp8[non_source] * amp4[non_source], EPS))
    out = result.output_indices
    raw4 = np.mean(result.node_a4[out])
    raw8 = np.mean(result.node_a8[out])
    raw12 = np.mean(result.node_a12[out])
    raw_p40 = float(abs(raw4) ** 2)
    raw_p80 = float(abs(raw8) ** 2)
    raw_p120 = float(abs(raw12) ** 2)
    purity = raw_p120 / max(raw_p40 + raw_p80 + raw_p120, EPS)
    first120 = max(float(amp12[1] if len(amp12) > 1 else amp12[0]), 0.05 * float(np.max(amp12)), EPS)
    coherent_growth = float(amp12[-1] / first120) * lock120
    target_power = float(abs(np.sum(result.node_a12[out]) / max(len(out), 1)) ** 2) * lock120
    tap_fracs = result.graph_distances_m[result.tap_indices] / max(float(np.max(result.graph_distances_m)), EPS)
    slope = 0.0
    if len(tap_fracs[1:]) > 2 and float(np.max(amp12)) > EPS:
        floor = max(0.02 * float(np.max(amp12)), EPS)
        slope = float(np.polyfit(tap_fracs[1:], np.log(amp12[1:] + floor), 1)[0])
    mask = late_mask(result)
    target_cv = envelope_cv(result.tap_a12[mask, -1])
    phase_series = np.unwrap(
        np.angle(result.tap_a12[mask, -1])
        - np.angle(result.tap_a8[mask, -1])
        - np.angle(result.tap_a4[mask, -1])
    )
    jumps = np.abs(np.diff(phase_series)) if len(phase_series) > 1 else np.asarray([0.0])
    max_jump = float(np.max(jumps)) if len(jumps) else 0.0
    source_only = True
    nums = acoustic_numbers(cfg)
    return {
        **nums,
        "row_type": "geometry_row",
        "case_id": cfg.case_id,
        "parent_case_id": cfg.parent_case_id,
        "name": cfg.name,
        "family": cfg.family,
        "role": cfg.role,
        "control_kind": cfg.control_kind,
        "node_count": len(cfg.positions),
        "edge_count": len(cfg.edges),
        "source_node_count": len(cfg.source_nodes),
        "source_only_drive": str(source_only),
        "direct_80khz_drive_present": "False",
        "direct_120khz_drive_present": "False",
        "target_frequency_injection_present": "False",
        "phase_lock_80khz": lock80,
        "phase_lock_120khz": lock120,
        "raw_pre_readout_120khz_purity": purity,
        "distributed_120khz_coherent_growth": coherent_growth,
        "distributed_120khz_growth_slope": slope,
        "target_coherent_power_120khz": target_power,
        "raw_output_40khz_power": raw_p40,
        "raw_output_80khz_power": raw_p80,
        "raw_output_120khz_power": raw_p120,
        "target_envelope_cv": target_cv,
        "max_phase_jump": max_jump,
        "graph_radius_m": float(np.max([pair_distance(p, centroid(cfg.positions)) for p in cfg.positions]) if cfg.positions else 0.0),
        "max_graph_distance_m": float(np.max(result.graph_distances_m)),
        "drive_work_proxy": result.drive_work,
        "loss_work_proxy": result.loss_work,
        "notes": cfg.notes,
    }


def row_gate(row: Dict[str, object]) -> Tuple[bool, str]:
    failures: List[str] = []
    bool_checks = [
        ("source_only_drive", "True"),
        ("direct_80khz_drive_present", "False"),
        ("direct_120khz_drive_present", "False"),
        ("target_frequency_injection_present", "False"),
    ]
    for key, expected in bool_checks:
        if str(row.get(key)) != expected:
            failures.append(f"{key}_not_{expected}")
    checks = [
        ("phase_lock_80khz", 0.80, ">="),
        ("phase_lock_120khz", 0.90, ">="),
        ("raw_pre_readout_120khz_purity", 0.60, ">="),
        ("distributed_120khz_coherent_growth", 2.0, ">="),
        ("object_reference_gain_120khz", 10.0, ">="),
        ("max_control_leakage", 0.15, "<"),
        ("geometry_dependency_score", 0.80, ">="),
        ("shortened_pattern_leakage", 0.15, "<"),
        ("randomized_pattern_leakage", 0.15, "<"),
    ]
    for key, threshold, op in checks:
        value = safe_float(row.get(key), -1.0 if op == ">=" else 99.0)
        if op == ">=" and value < threshold:
            failures.append(f"{key}_below_{threshold:g}")
        if op == "<" and value >= threshold:
            failures.append(f"{key}_not_below_{threshold:g}")
    return not failures, "pass" if not failures else ";".join(failures)


def near_miss_gate(row: Dict[str, object]) -> bool:
    return (
        str(row.get("source_only_drive")) == "True"
        and safe_float(row.get("phase_lock_80khz")) >= 0.75
        and safe_float(row.get("phase_lock_120khz")) >= 0.86
        and safe_float(row.get("raw_pre_readout_120khz_purity")) >= 0.45
        and safe_float(row.get("distributed_120khz_coherent_growth")) >= 1.5
        and safe_float(row.get("object_reference_gain_120khz")) >= 3.0
    )


def apply_scores(rows: List[Dict[str, object]]) -> None:
    by_parent: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        if row.get("role") == "discovery":
            by_parent.setdefault(str(row.get("case_id")), []).append(row)
        else:
            by_parent.setdefault(str(row.get("parent_case_id")), []).append(row)
    for parent, bundle in by_parent.items():
        discovery = next((row for row in bundle if row.get("role") == "discovery" and row.get("case_id") == parent), None)
        if discovery is None:
            continue
        controls = [row for row in bundle if row.get("role") == "control"]
        cand_power = row_power(discovery)
        max_control_power = max((row_power(row) for row in controls), default=0.0)
        randomized_power = max(
            (row_power(row) for row in controls if row.get("control_kind") in {"randomized_positions", "radial_distribution_angle_shuffle"}),
            default=0.0,
        )
        shortened_power = max(
            (row_power(row) for row in controls if row.get("control_kind") in {"shortened_cropped_geometry", "missing_satellite_nodes"}),
            default=0.0,
        )
        geometry_control_power = max(
            (
                row_power(row)
                for row in controls
                if row.get("control_kind")
                in {
                    "randomized_positions",
                    "radial_distribution_angle_shuffle",
                    "ring_only_equivalent",
                    "phase_shuffled_source_signs",
                    "missing_satellite_nodes",
                    "shortened_cropped_geometry",
                }
            ),
            default=0.0,
        )
        denominator = max(max_control_power, EPS)
        discovery["object_reference_gain_120khz"] = cand_power / denominator
        discovery["max_control_leakage"] = clamp(max_control_power / max(cand_power, EPS))
        discovery["randomized_pattern_leakage"] = clamp(randomized_power / max(cand_power, EPS))
        discovery["shortened_pattern_leakage"] = clamp(shortened_power / max(cand_power, EPS))
        discovery["geometry_dependency_score"] = clamp(1.0 - geometry_control_power / max(cand_power, EPS))
        passed, reason = row_gate(discovery)
        discovery["promotion_category"] = "acoustic_crop_geometry_candidate" if passed else (
            "acoustic_crop_geometry_near_miss" if near_miss_gate(discovery) else "row_fail"
        )
        discovery["row_passed"] = str(passed)
        discovery["pass_fail_reason"] = reason
        for control in controls:
            leakage = clamp(row_power(control) / max(cand_power, EPS))
            control["object_reference_gain_120khz"] = row_power(control) / max(cand_power, EPS)
            control["max_control_leakage"] = leakage
            control["randomized_pattern_leakage"] = ""
            control["shortened_pattern_leakage"] = ""
            control["geometry_dependency_score"] = ""
            control["row_passed"] = str(leakage < 0.15)
            control["pass_fail_reason"] = "control_dead" if leakage < 0.15 else "control_leakage"
            control["promotion_category"] = "control_dead" if leakage < 0.15 else "control_leakage"


def failure_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") != "discovery" or str(row.get("row_passed")) == "True":
            continue
        out.append(
            {
                "row_type": "failure_mode",
                "case_id": row.get("case_id"),
                "family": row.get("family"),
                "promotion_category": row.get("promotion_category"),
                "pass_fail_reason": row.get("pass_fail_reason"),
                "phase_lock_80khz": row.get("phase_lock_80khz"),
                "phase_lock_120khz": row.get("phase_lock_120khz"),
                "raw_pre_readout_120khz_purity": row.get("raw_pre_readout_120khz_purity"),
                "distributed_120khz_coherent_growth": row.get("distributed_120khz_coherent_growth"),
                "object_reference_gain_120khz": row.get("object_reference_gain_120khz"),
                "max_control_leakage": row.get("max_control_leakage"),
                "geometry_dependency_score": row.get("geometry_dependency_score"),
            }
        )
    return out


def aggregate(rows: List[Dict[str, object]]) -> Dict[str, object]:
    discoveries = [row for row in rows if row.get("role") == "discovery"]
    controls = [row for row in rows if row.get("role") == "control"]
    promoted = [row for row in discoveries if row.get("promotion_category") == "acoustic_crop_geometry_candidate"]
    near = [row for row in discoveries if row.get("promotion_category") == "acoustic_crop_geometry_near_miss"]
    best = max(
        discoveries,
        key=lambda row: (
            1 if row.get("promotion_category") == "acoustic_crop_geometry_candidate" else 0,
            safe_float(row.get("object_reference_gain_120khz")),
            safe_float(row.get("phase_lock_120khz")),
            safe_float(row.get("raw_pre_readout_120khz_purity")),
            safe_float(row.get("target_coherent_power_120khz")),
        ),
        default={},
    )
    leaking_controls = [row for row in controls if row.get("promotion_category") == "control_leakage"]
    strongest_leak = max(leaking_controls, key=lambda row: safe_float(row.get("max_control_leakage")), default={})
    counts: Dict[str, int] = {}
    for row in discoveries:
        if row.get("promotion_category") == "acoustic_crop_geometry_candidate":
            continue
        reason = str(row.get("pass_fail_reason", "unknown")).split(";")[0]
        counts[reason] = counts.get(reason, 0) + 1
    label = "acoustic_crop_geometry_candidate" if promoted else ("acoustic_crop_geometry_near_miss" if near else "not_promoted")
    decision = "geometry_promoted_for_further_simulation" if promoted else "no_hardware_build_readiness"
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "acoustic_412_crop_geometry_array",
        "aggregate_label": label,
        "decision": decision,
        "discovery_rows": len(discoveries),
        "control_rows": len(controls),
        "promoted_count": len(promoted),
        "near_miss_count": len(near),
        "all_controls_dead": str(all(row.get("promotion_category") == "control_dead" for row in controls)),
        "leaking_control_count": len(leaking_controls),
        "strongest_leaking_control": strongest_leak.get("case_id", ""),
        "strongest_leaking_control_family": strongest_leak.get("family", ""),
        "strongest_leaking_control_kind": strongest_leak.get("control_kind", ""),
        "strongest_leaking_control_score": strongest_leak.get("max_control_leakage", ""),
        "best_case_id": best.get("case_id", ""),
        "best_family": best.get("family", ""),
        "best_label": best.get("promotion_category", ""),
        "best_phase_lock_80khz": best.get("phase_lock_80khz", ""),
        "best_phase_lock_120khz": best.get("phase_lock_120khz", ""),
        "best_raw_pre_readout_120khz_purity": best.get("raw_pre_readout_120khz_purity", ""),
        "best_distributed_120khz_coherent_growth": best.get("distributed_120khz_coherent_growth", ""),
        "best_object_reference_gain_120khz": best.get("object_reference_gain_120khz", ""),
        "best_max_control_leakage": best.get("max_control_leakage", ""),
        "dominant_failure_mode": max(counts, key=counts.get) if counts else "none",
        "failure_mode_counts_json": json.dumps(counts, sort_keys=True),
        "recommended_next_step": (
            "independent robustness validation of promoted geometry"
            if promoted
            else "do not build; inspect failed geometry controls or redesign the 2D pattern"
        ),
    }


def dependency_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") != "discovery":
            continue
        out.append(
            {
                "case_id": row.get("case_id"),
                "family": row.get("family"),
                "promotion_category": row.get("promotion_category"),
                "geometry_dependency_score": row.get("geometry_dependency_score"),
                "shortened_pattern_leakage": row.get("shortened_pattern_leakage"),
                "randomized_pattern_leakage": row.get("randomized_pattern_leakage"),
                "max_control_leakage": row.get("max_control_leakage"),
                "object_reference_gain_120khz": row.get("object_reference_gain_120khz"),
                "target_coherent_power_120khz": row.get("target_coherent_power_120khz"),
                "pass_fail_reason": row.get("pass_fail_reason"),
            }
        )
    return out


def geometry_svg(cfg: GeometryConfig, path: Path, title: str) -> None:
    width = 720
    height = 720
    margin = 54
    xs = [p[0] for p in cfg.positions] or [0.0]
    ys = [p[1] for p in cfg.positions] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0e-6)

    def project(p: Tuple[float, float]) -> Tuple[float, float]:
        x = margin + (p[0] - min_x + 0.5 * (span - (max_x - min_x))) / span * (width - 2 * margin)
        y = margin + (p[1] - min_y + 0.5 * (span - (max_y - min_y))) / span * (height - 2 * margin)
        return x, height - y

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0f1117"/>',
        f'<text x="28" y="36" fill="#f5f7fb" font-family="Arial, sans-serif" font-size="20">{title}</text>',
        f'<text x="28" y="62" fill="#aab2c5" font-family="Arial, sans-serif" font-size="13">{cfg.family} | {cfg.case_id} | {cfg.role} {cfg.control_kind}</text>',
    ]
    for i, j, weight in cfg.edges:
        x1, y1 = project(cfg.positions[i])
        x2, y2 = project(cfg.positions[j])
        opacity = 0.24 + 0.46 * clamp(weight)
        lines.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#6d7890" stroke-width="1.3" opacity="{opacity:.3f}"/>')
    source_set = set(cfg.source_nodes)
    for idx, point in enumerate(cfg.positions):
        x, y = project(point)
        fill = "#ffcf5a" if idx in source_set else "#74d7b7"
        radius = 5.4 if idx in source_set else 3.8
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}" stroke="#11151f" stroke-width="1.0"/>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def select_diagram_rows(rows: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    discoveries = [row for row in rows if row.get("role") == "discovery"]
    controls = [row for row in rows if row.get("role") == "control"]
    promoted = [row for row in discoveries if row.get("promotion_category") == "acoustic_crop_geometry_candidate"]
    near = [row for row in discoveries if row.get("promotion_category") == "acoustic_crop_geometry_near_miss"]
    failed = [row for row in discoveries if row not in promoted]
    out: Dict[str, Dict[str, object]] = {}
    out["nominal_pattern"] = max(discoveries, key=lambda row: safe_float(row.get("target_coherent_power_120khz")), default={})
    out["strongest_leaking_control"] = max(
        [row for row in controls if row.get("promotion_category") == "control_leakage"] or controls,
        key=lambda row: safe_float(row.get("max_control_leakage")),
        default={},
    )
    out["best_failed_near_miss"] = max(
        near or failed,
        key=lambda row: (
            safe_float(row.get("object_reference_gain_120khz")),
            safe_float(row.get("phase_lock_120khz")),
            safe_float(row.get("raw_pre_readout_120khz_purity")),
        ),
        default={},
    )
    out["best_promoted_row"] = max(promoted, key=lambda row: safe_float(row.get("object_reference_gain_120khz")), default={})
    return out


def config_by_id(configs: Sequence[GeometryConfig]) -> Dict[str, GeometryConfig]:
    return {cfg.case_id: cfg for cfg in configs}


def write_diagrams(out_dir: Path, rows: List[Dict[str, object]], configs: Sequence[GeometryConfig]) -> Dict[str, str]:
    by_id = config_by_id(configs)
    selected = select_diagram_rows(rows)
    paths: Dict[str, str] = {}
    for label, row in selected.items():
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id not in by_id:
            continue
        path = out_dir / f"{label}_{case_id}.svg"
        geometry_svg(by_id[case_id], path, label.replace("_", " ").title())
        paths[label] = str(path)
    return paths


def write_readme(out_dir: Path, agg: Dict[str, object], rows: List[Dict[str, object]], diagram_paths: Dict[str, str]) -> None:
    promoted = [row for row in rows if row.get("promotion_category") == "acoustic_crop_geometry_candidate"]
    near = [row for row in rows if row.get("promotion_category") == "acoustic_crop_geometry_near_miss"]
    leak = [row for row in rows if row.get("promotion_category") == "control_leakage"]
    lines = [
        "# Acoustic 4->8->12 Crop Geometry Array",
        "",
        "Crop-circle-inspired geometry is used only as spatial-layout inspiration. This run does not claim crop circles are proven messages and does not imply hardware build readiness.",
        "",
        "## Direct Answers",
        "",
        f"- Did any 2D geometry promote? {agg.get('promoted_count')} promoted; aggregate_label={agg.get('aggregate_label')}.",
        f"- Best family: {agg.get('best_family')} ({agg.get('best_case_id')}) with label {agg.get('best_label')}.",
        f"- Best 120 kHz lock: {agg.get('best_phase_lock_120khz')}.",
        f"- Best raw pre-readout 120 kHz purity: {agg.get('best_raw_pre_readout_120khz_purity')}.",
        f"- Best object/reference gain: {agg.get('best_object_reference_gain_120khz')}.",
        f"- Best max control leakage: {agg.get('best_max_control_leakage')}.",
        f"- All controls dead? {agg.get('all_controls_dead')}; leaking_control_count={agg.get('leaking_control_count')}.",
        f"- Strongest leaking control: {agg.get('strongest_leaking_control')} {agg.get('strongest_leaking_control_kind')} score={agg.get('strongest_leaking_control_score')}.",
        f"- Recommended next step: {agg.get('recommended_next_step')}.",
        "",
        "## Scope",
        "",
        "- Source-only 40 kHz drive in discovery rows.",
        "- No direct 80 kHz drive, no direct 120 kHz drive, and no target-frequency injection.",
        "- Raw graph tap phasors are promotion evidence; diagrams are diagnostic only.",
        "- Matched controls include randomized positions, angular shuffle, ring-only equivalent, source phase shuffle, missing satellites, shortened/cropped geometry, linear no-nonlinearity, generated-path suppression, phase mismatch, and sensor artifact control.",
        "",
        "## Output Files",
        "",
        "- `summary.json`",
        "- `summary.csv`",
        "- `promoted_geometries.csv`",
        "- `geometry_dependency.csv`",
        "- `matched_controls.csv`",
        "- `failure_modes.csv`",
    ]
    if diagram_paths:
        lines.extend(["", "## Diagrams", ""])
        for label, path in diagram_paths.items():
            lines.append(f"- {label}: `{path}`")
    lines.extend(
        [
            "",
            "## Promotion Result",
            "",
            f"- Promoted rows: {', '.join(str(row.get('case_id')) for row in promoted) or 'none'}.",
            f"- Near misses: {', '.join(str(row.get('case_id')) for row in near) or 'none'}.",
            f"- Leaking controls: {', '.join(str(row.get('case_id')) for row in leak[:12]) or 'none'}.",
            f"- Dominant failure mode: {agg.get('dominant_failure_mode')} counts={agg.get('failure_mode_counts_json')}.",
            "",
            "## Conservative Rule",
            "",
            "Do not use this run as hardware proof. A promoted geometry would require independent robustness validation before any build claim.",
        ]
    )
    (out_dir / "README_ACOUSTIC_412_CROP_GEOMETRY_ARRAY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def simulate_config(cfg: GeometryConfig) -> Tuple[str, Dict[str, object]]:
    return cfg.case_id, base_metrics(simulate(cfg))


def run(out_dir: Path, workers: int | None = None) -> Dict[str, object]:
    ensure_dir(out_dir)
    configs = build_configs()
    worker_count = workers if workers is not None else min(8, max(1, (os.cpu_count() or 2) - 1))
    rows_by_id: Dict[str, Dict[str, object]] = {}
    if worker_count <= 1:
        for cfg in configs:
            case_id, row = simulate_config(cfg)
            rows_by_id[case_id] = row
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(simulate_config, cfg) for cfg in configs]
            for future in as_completed(futures):
                case_id, row = future.result()
                rows_by_id[case_id] = row
    rows = [rows_by_id[cfg.case_id] for cfg in configs]
    apply_scores(rows)
    agg = aggregate(rows)
    all_rows = [agg] + rows
    diagram_paths = write_diagrams(out_dir, rows, configs)

    write_csv(out_dir / "summary.csv", all_rows)
    promoted_rows = [row for row in rows if row.get("promotion_category") == "acoustic_crop_geometry_candidate"]
    promoted_fields = [
        "case_id",
        "family",
        "promotion_category",
        "phase_lock_80khz",
        "phase_lock_120khz",
        "raw_pre_readout_120khz_purity",
        "distributed_120khz_coherent_growth",
        "target_coherent_power_120khz",
        "object_reference_gain_120khz",
        "max_control_leakage",
        "geometry_dependency_score",
        "shortened_pattern_leakage",
        "randomized_pattern_leakage",
        "pass_fail_reason",
    ]
    write_csv(out_dir / "promoted_geometries.csv", promoted_rows, fieldnames=promoted_fields)
    write_csv(out_dir / "geometry_dependency.csv", dependency_rows(rows))
    write_csv(out_dir / "matched_controls.csv", [row for row in rows if row.get("role") == "control"])
    write_csv(out_dir / "failure_modes.csv", failure_rows(rows))
    (out_dir / "summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": agg,
                    "rows": all_rows,
                    "diagram_paths": diagram_paths,
                    "configs": [asdict(cfg) for cfg in configs],
                    "control_kinds": list(CONTROL_KINDS),
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_readme(out_dir, agg, rows, diagram_paths)
    return {"aggregate": agg, "rows": rows, "diagram_paths": diagram_paths}


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop-geometry-inspired 40/80/120 kHz acoustic graph screen.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers; defaults to up to 8.")
    parser.add_argument("--run", action="store_true", help="Run the bounded crop-geometry array.")
    args = parser.parse_args()
    if not args.run:
        print("Use --run to execute the crop-geometry acoustic array screen.")
        return
    result = run(Path(args.out), workers=args.workers)
    agg = result["aggregate"]
    print(
        json.dumps(
            sanitize(
                {
                    "aggregate_label": agg.get("aggregate_label"),
                    "decision": agg.get("decision"),
                    "promoted_count": agg.get("promoted_count"),
                    "near_miss_count": agg.get("near_miss_count"),
                    "best_case_id": agg.get("best_case_id"),
                    "best_family": agg.get("best_family"),
                    "best_label": agg.get("best_label"),
                    "best_object_reference_gain_120khz": agg.get("best_object_reference_gain_120khz"),
                    "best_max_control_leakage": agg.get("best_max_control_leakage"),
                    "leaking_control_count": agg.get("leaking_control_count"),
                    "summary": str(Path(args.out) / "summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
