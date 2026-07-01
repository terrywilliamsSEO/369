#!/usr/bin/env python3
"""Modal-triad screen for sacred-geometry-inspired acoustic graph topologies.

Sacred geometry names are used here only as candidate graph-topology labels.
This script does not claim sacred geometry is proven, does not claim crop
circles are messages, and does not claim hardware readiness. Promotion requires
strict matched-control defeat and nonlinear raw 120 kHz purity/growth.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

import acoustic_412_crop_geometry_array as crop


OUT_DIR = Path("runs") / "acoustic_412_sacred_modal_triads"
SOURCE_HZ = crop.SOURCE_HZ
GENERATED_HZ = crop.GENERATED_HZ
TARGET_HZ = crop.TARGET_HZ
BASE_VELOCITY_M_S = crop.BASE_VELOCITY_M_S
STAGE1_OVERLAP_448_THRESHOLD = 0.018
STAGE1_OVERLAP_4812_THRESHOLD = 0.012
STAGE2_TOP_DISCOVERY_COUNT = 4
EPS = 1.0e-18

CONTROL_KINDS: Tuple[str, ...] = (
    "randomized_positions",
    "radial_distribution_angle_shuffle",
    "edge_weight_shuffle",
    "ring_only_equivalent",
    "missing_key_nodes",
    "shortened_cropped_graph",
    "phase_shuffled_source_signs",
    "degree_preserving_random_graph",
    "linear_no_nonlinearity",
)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: Sequence[str] | None = None) -> None:
    if not rows and fieldnames is None:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = [str(key) for key in fieldnames] if fieldnames is not None else []
    if not keys:
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


def deterministic_seed(label: str) -> int:
    return crop.deterministic_seed("sacred_modal_" + label)


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
) -> crop.GeometryConfig:
    return crop.make_config(
        case_id=case_id,
        family=family,
        positions=positions,
        edges=edges,
        source_nodes=source_nodes,
        source_signs=source_signs,
        role=role,
        parent_case_id=parent_case_id,
        control_kind=control_kind,
        name=name or family,
        notes=notes,
        **updates,
    )


def add_edge(edges: set[Tuple[int, int, float]], positions: Sequence[Tuple[float, float]], i: int, j: int, scale: float = 0.014) -> None:
    crop.add_edge(edges, positions, i, j, scale)


def regular_polygon(radius: float, count: int, phase: float = 0.0) -> List[Tuple[float, float]]:
    return crop.polar_points(radius, count, phase)


def source_near_center(positions: Sequence[Tuple[float, float]], count: int = 3) -> Tuple[int, ...]:
    return crop.source_nodes_for_positions(positions, count)


def sri_yantra_nested_triangles(case_id: str = "m001") -> crop.GeometryConfig:
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    triangle_specs = [
        (0.011, math.pi / 2.0),
        (0.015, -math.pi / 2.0),
        (0.020, math.pi / 2.0 + math.pi / 9.0),
        (0.024, -math.pi / 2.0 + math.pi / 8.0),
        (0.030, math.pi / 2.0 - math.pi / 12.0),
        (0.036, -math.pi / 2.0 - math.pi / 14.0),
    ]
    triangles: List[List[int]] = []
    for radius, phase in triangle_specs:
        tri: List[int] = []
        for p in regular_polygon(radius, 3, phase):
            tri.append(len(points))
            points.append(p)
        triangles.append(tri)
    points = list(crop.unique_points(points))
    edges: set[Tuple[int, int, float]] = set()
    for tri in triangles:
        if max(tri) >= len(points):
            continue
        for idx, node in enumerate(tri):
            add_edge(edges, points, node, tri[(idx + 1) % 3])
            add_edge(edges, points, 0, node)
    for edge in crop.k_nearest_edges(points, k=3, scale=0.013):
        edges.add(edge)
    return make_config(case_id, "sri_yantra_nested_triangles", points, tuple(sorted(edges)), source_near_center(points, 4), nonlinear_4812=0.230)


def metatrons_cube(case_id: str = "m002") -> crop.GeometryConfig:
    points = [(0.0, 0.0)] + regular_polygon(0.014, 6, 0.0) + regular_polygon(0.028, 6, math.pi / 6.0)
    edges: set[Tuple[int, int, float]] = set()
    inner = list(range(1, 7))
    outer = list(range(7, 13))
    for ring in (inner, outer):
        for idx, node in enumerate(ring):
            add_edge(edges, points, node, ring[(idx + 1) % len(ring)])
            add_edge(edges, points, 0, node)
    for idx in range(6):
        add_edge(edges, points, inner[idx], outer[idx])
        add_edge(edges, points, inner[idx], outer[(idx - 1) % 6])
        add_edge(edges, points, inner[idx], inner[(idx + 3) % 6])
    return make_config(case_id, "metatrons_cube", points, tuple(sorted(edges)), (0, 1, 3, 5), nonlinear_448=0.135)


def vesica_piscis_seed_of_life(case_id: str = "m003") -> crop.GeometryConfig:
    radius = 0.012
    centers = [(0.0, 0.0)] + regular_polygon(radius, 6, 0.0)
    points: List[Tuple[float, float]] = []
    for cx, cy in centers:
        points.append((cx, cy))
        for idx in range(12):
            theta = 2.0 * math.pi * idx / 12.0
            points.append((cx + radius * math.cos(theta), cy + radius * math.sin(theta)))
    points = list(crop.unique_points(points))
    edges = crop.k_nearest_edges(points, k=4, scale=0.0125)
    return make_config(case_id, "vesica_piscis_seed_of_life", points, edges, source_near_center(points, 7), nonlinear_448=0.138, nonlinear_4812=0.228)


def fibonacci_phyllotaxis(case_id: str = "m004") -> crop.GeometryConfig:
    count = 64
    golden = math.pi * (3.0 - math.sqrt(5.0))
    points = []
    for idx in range(count):
        r = 0.0045 * math.sqrt(idx + 1)
        theta = idx * golden
        points.append((r * math.cos(theta), r * math.sin(theta)))
    edges = crop.k_nearest_edges(points, k=4, scale=0.012)
    return make_config(case_id, "fibonacci_phyllotaxis", points, edges, source_near_center(points, 5), target_path_scale=1.08)


def golden_angle_spiral(case_id: str = "m005") -> crop.GeometryConfig:
    count = 54
    golden = math.pi * (3.0 - math.sqrt(5.0))
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    for idx in range(1, count):
        r = 0.0037 + 0.00068 * idx
        theta = idx * golden
        points.append((r * math.cos(theta), r * math.sin(theta)))
    edges: set[Tuple[int, int, float]] = set(crop.k_nearest_edges(points, k=3, scale=0.012))
    for idx in range(count - 1):
        add_edge(edges, points, idx, idx + 1, scale=0.012)
    return make_config(case_id, "golden_angle_spiral", points, tuple(sorted(edges)), source_near_center(points, 4), phase_velocity_12_ratio=0.990)


def penrose_quasicrystal_patch(case_id: str = "m006") -> crop.GeometryConfig:
    points: List[Tuple[float, float]] = [(0.0, 0.0)]
    for family in range(5):
        angle = 2.0 * math.pi * family / 5.0
        normal = angle + math.pi / 2.0
        for step in range(-3, 4):
            offset = 0.0065 * step
            for t in (-0.018, -0.009, 0.0, 0.009, 0.018):
                x = t * math.cos(angle) + offset * math.cos(normal)
                y = t * math.sin(angle) + offset * math.sin(normal)
                if math.hypot(x, y) <= 0.037:
                    points.append((x, y))
    points = list(crop.unique_points(points, digits=5))
    edges = crop.k_nearest_edges(points, k=4, scale=0.0115)
    return make_config(case_id, "penrose_quasicrystal_patch", points, edges, source_near_center(points, 5), nonlinear_4812=0.222)


def dodecagonal_12fold_quasicrystal(case_id: str = "m007") -> crop.GeometryConfig:
    points = [(0.0, 0.0)]
    rings: List[List[int]] = []
    for radius, count, phase in ((0.010, 12, 0.0), (0.019, 24, math.pi / 24.0), (0.030, 24, math.pi / 12.0), (0.038, 12, math.pi / 24.0)):
        start = len(points)
        points.extend(regular_polygon(radius, count, phase))
        rings.append(list(range(start, start + count)))
    edges = set(crop.ring_edges(points, rings, center=0, scale=0.013))
    for edge in crop.k_nearest_edges(points, k=3, scale=0.013):
        edges.add(edge)
    return make_config(case_id, "dodecagonal_12fold_quasicrystal", points, tuple(sorted(edges)), (0, 1, 4, 7, 10), nonlinear_448=0.132)


def hexagram_dual_triangle_lattice(case_id: str = "m008") -> crop.GeometryConfig:
    points = [(0.0, 0.0)] + regular_polygon(0.014, 6, math.pi / 6.0) + regular_polygon(0.028, 6, 0.0) + regular_polygon(0.036, 12, math.pi / 12.0)
    edges: set[Tuple[int, int, float]] = set(crop.k_nearest_edges(points, k=4, scale=0.013))
    for tri in ((1, 3, 5), (2, 4, 6), (7, 9, 11), (8, 10, 12)):
        for idx, node in enumerate(tri):
            add_edge(edges, points, node, tri[(idx + 1) % len(tri)])
    return make_config(case_id, "hexagram_dual_triangle_lattice", points, tuple(sorted(edges)), (0, 1, 3, 5), nonlinear_4812=0.226)


def tree_of_life_graph(case_id: str = "m009") -> crop.GeometryConfig:
    points = [
        (0.0, 0.037),
        (-0.014, 0.024),
        (0.014, 0.024),
        (0.0, 0.013),
        (-0.017, 0.002),
        (0.017, 0.002),
        (0.0, -0.010),
        (-0.013, -0.023),
        (0.013, -0.023),
        (0.0, -0.036),
        (0.0, 0.0),
        (0.0, 0.026),
    ]
    path_edges = [
        (0, 1), (0, 2), (0, 11), (1, 3), (2, 3), (1, 4), (2, 5), (3, 4),
        (3, 5), (3, 10), (4, 6), (5, 6), (4, 7), (5, 8), (6, 7), (6, 8),
        (6, 9), (7, 9), (8, 9), (10, 11), (10, 6),
    ]
    edges: set[Tuple[int, int, float]] = set()
    for i, j in path_edges:
        add_edge(edges, points, i, j, scale=0.014)
    return make_config(case_id, "tree_of_life_graph", points, tuple(sorted(edges)), (9, 7, 8), target_path_scale=1.12)


def chladni_template_synthetic(case_id: str = "m010") -> crop.GeometryConfig:
    points: List[Tuple[float, float]] = []
    for ix in range(-5, 6):
        for iy in range(-5, 6):
            x = 0.0065 * ix
            y = 0.0065 * iy
            r = math.hypot(x, y)
            if r > 0.040:
                continue
            value = math.sin(3.0 * math.pi * (x / 0.080 + 0.5)) * math.sin(2.0 * math.pi * (y / 0.080 + 0.5))
            if abs(value) < 0.38 or (ix == 0 and iy == 0):
                points.append((x, y))
    points = list(crop.unique_points(points))
    edges = crop.k_nearest_edges(points, k=4, scale=0.011)
    return make_config(case_id, "chladni_template_synthetic", points, edges, source_near_center(points, 5), damping_loss=0.034, nonlinear_4812=0.232)


def discovery_geometries() -> List[crop.GeometryConfig]:
    return [
        sri_yantra_nested_triangles("m001"),
        metatrons_cube("m002"),
        vesica_piscis_seed_of_life("m003"),
        fibonacci_phyllotaxis("m004"),
        golden_angle_spiral("m005"),
        penrose_quasicrystal_patch("m006"),
        dodecagonal_12fold_quasicrystal("m007"),
        hexagram_dual_triangle_lattice("m008"),
        tree_of_life_graph("m009"),
        chladni_template_synthetic("m010"),
    ]


def relabel_control(
    cfg: crop.GeometryConfig,
    control_kind: str,
    positions: Sequence[Tuple[float, float]],
    edges: Sequence[Tuple[int, int, float]],
    source_nodes: Sequence[int],
    source_signs: Sequence[float] | None = None,
    **updates: object,
) -> crop.GeometryConfig:
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
        notes=f"Matched modal-triad control for {cfg.case_id}: {control_kind}",
        **updates,
    )


def edge_weight_shuffle_control(cfg: crop.GeometryConfig) -> crop.GeometryConfig:
    rng = np.random.default_rng(deterministic_seed(cfg.case_id + "_edge_weight_shuffle"))
    weights = [edge[2] for edge in cfg.edges]
    rng.shuffle(weights)
    edges = tuple((i, j, float(weight)) for (i, j, _old), weight in zip(cfg.edges, weights))
    return relabel_control(cfg, "edge_weight_shuffle", cfg.positions, edges, cfg.source_nodes, cfg.source_signs)


def degree_preserving_random_graph_control(cfg: crop.GeometryConfig) -> crop.GeometryConfig:
    rng = np.random.default_rng(deterministic_seed(cfg.case_id + "_degree_preserving"))
    n = len(cfg.positions)
    degree = [0] * n
    weights = []
    for i, j, weight in cfg.edges:
        degree[i] += 1
        degree[j] += 1
        weights.append(float(weight))
    stubs: List[int] = []
    for idx, deg in enumerate(degree):
        stubs.extend([idx] * deg)
    rng.shuffle(stubs)
    edges_raw: set[Tuple[int, int]] = set()
    attempts = 0
    while len(stubs) >= 2 and attempts < 20_000:
        attempts += 1
        a = stubs.pop()
        b = stubs.pop()
        if a == b:
            stubs.extend([a, b])
            rng.shuffle(stubs)
            continue
        i, j = (a, b) if a < b else (b, a)
        if (i, j) in edges_raw:
            continue
        edges_raw.add((i, j))
    if len(edges_raw) < max(1, len(cfg.edges) // 3):
        edges_raw = {(i, j) for i, j, _w in crop.k_nearest_edges(cfg.positions, k=3, scale=0.013)}
    if not weights:
        weights = [1.0]
    edges: List[Tuple[int, int, float]] = []
    for idx, (i, j) in enumerate(sorted(edges_raw)):
        edges.append((i, j, weights[idx % len(weights)]))
    return relabel_control(cfg, "degree_preserving_random_graph", cfg.positions, tuple(edges), cfg.source_nodes, cfg.source_signs)


def linear_no_nonlinearity_control(cfg: crop.GeometryConfig) -> crop.GeometryConfig:
    return relabel_control(
        cfg,
        "linear_no_nonlinearity",
        cfg.positions,
        cfg.edges,
        cfg.source_nodes,
        cfg.source_signs,
        no_nonlinearity=True,
        nonlinear_448=0.0,
        nonlinear_4812=0.0,
        generated_path_scale=0.0,
        target_path_scale=0.0,
    )


def matched_controls(cfg: crop.GeometryConfig) -> List[crop.GeometryConfig]:
    random_pos = crop.randomized_positions_control(cfg)
    radial_shuffle = crop.radial_angle_shuffle_control(cfg)
    ring_only = crop.ring_only_control(cfg)
    missing = crop.missing_satellite_control(cfg)
    shortened = crop.shortened_cropped_control(cfg)
    source_shuffle = crop.phase_shuffled_source_control(cfg)
    control_updates = [
        (random_pos, "randomized_positions"),
        (radial_shuffle, "radial_distribution_angle_shuffle"),
        (ring_only, "ring_only_equivalent"),
        (missing, "missing_key_nodes"),
        (shortened, "shortened_cropped_graph"),
        (source_shuffle, "phase_shuffled_source_signs"),
    ]
    controls: List[crop.GeometryConfig] = []
    for raw, kind in control_updates:
        controls.append(replace(raw, case_id=f"{cfg.case_id}_{kind}", parent_case_id=cfg.case_id, control_kind=kind, name=kind, notes=f"Matched modal-triad control for {cfg.case_id}: {kind}"))
    controls.extend(
        [
            edge_weight_shuffle_control(cfg),
            degree_preserving_random_graph_control(cfg),
            linear_no_nonlinearity_control(cfg),
        ]
    )
    return controls


def build_configs() -> List[crop.GeometryConfig]:
    rows: List[crop.GeometryConfig] = []
    for cfg in discovery_geometries():
        rows.append(cfg)
        rows.extend(matched_controls(cfg))
    return rows


def stiffness_laplacian(cfg: crop.GeometryConfig) -> np.ndarray:
    n = len(cfg.positions)
    mat = np.zeros((n, n), dtype=float)
    for i, j, weight in cfg.edges:
        dist = max(crop.pair_distance(cfg.positions[i], cfg.positions[j]), 1.0e-5)
        stiffness = max(float(weight), 1.0e-6) / (dist * dist)
        mat[i, j] -= stiffness
        mat[j, i] -= stiffness
        mat[i, i] += stiffness
        mat[j, j] += stiffness
    if not np.any(mat):
        for i, j, weight in crop.k_nearest_edges(cfg.positions, k=2, scale=0.013):
            dist = max(crop.pair_distance(cfg.positions[i], cfg.positions[j]), 1.0e-5)
            stiffness = max(float(weight), 1.0e-6) / (dist * dist)
            mat[i, j] -= stiffness
            mat[j, i] -= stiffness
            mat[i, i] += stiffness
            mat[j, j] += stiffness
    return mat


def modal_frequencies_and_vectors(cfg: crop.GeometryConfig) -> Tuple[np.ndarray, np.ndarray]:
    lap = stiffness_laplacian(cfg)
    eigvals, eigvecs = np.linalg.eigh(lap)
    eigvals = np.maximum(eigvals, 0.0)
    frequencies = (cfg.phase_velocity_4_m_s / (2.0 * math.pi)) * np.sqrt(eigvals)
    order = np.argsort(frequencies)
    return frequencies[order], eigvecs[:, order]


def nonlinear_weights(cfg: crop.GeometryConfig) -> np.ndarray:
    distances = crop.graph_distances(cfg)
    motif = crop.motif_field(cfg, distances)
    if cfg.no_nonlinearity:
        return np.zeros_like(motif)
    return np.asarray(motif, dtype=float)


def source_vector(cfg: crop.GeometryConfig) -> np.ndarray:
    profile = crop.source_profile(cfg)
    return np.real(profile)


def output_mask(cfg: crop.GeometryConfig) -> np.ndarray:
    distances = crop.graph_distances(cfg)
    out = crop.output_indices(distances)
    mask = np.zeros(len(cfg.positions), dtype=float)
    mask[out] = 1.0
    return mask


def modal_overlap(phi_a: np.ndarray, phi_b: np.ndarray, phi_c: np.ndarray, weights: np.ndarray) -> float:
    numerator = float(abs(np.sum(phi_a * phi_b * phi_c * weights)))
    denom = math.sqrt(float(np.sum((phi_a * phi_b) ** 2 * np.maximum(weights, 0.0))) * float(np.sum(phi_c ** 2 * np.maximum(weights, 0.0))) + EPS)
    return numerator / max(denom, EPS)


def mode_separation_score(frequencies: np.ndarray, idxs: Tuple[int, int, int]) -> float:
    scores: List[float] = []
    for idx in idxs:
        f = frequencies[idx]
        nearest = min(
            (abs(f - frequencies[j]) for j in range(1, len(frequencies)) if j != idx),
            default=f,
        )
        scores.append(clamp(nearest / max(0.18 * f, EPS)))
    return float(min(scores)) if scores else 0.0


def symmetry_selectivity_score(couplings: np.ndarray, idx: int) -> float:
    selected = abs(float(couplings[idx]))
    if len(couplings) <= 2:
        return clamp(selected)
    sorted_other = sorted((abs(float(v)) for j, v in enumerate(couplings) if j != idx), reverse=True)
    neighbor = sorted_other[0] if sorted_other else 0.0
    return clamp(selected / max(selected + neighbor, EPS))


def triad_score(row: Dict[str, object]) -> float:
    ratio = clamp(1.0 - safe_float(row.get("triad_ratio_error")) / 0.05)
    o448 = clamp(safe_float(row.get("overlap_448_abs")) / STAGE1_OVERLAP_448_THRESHOLD)
    o4812 = clamp(safe_float(row.get("overlap_4812_abs")) / STAGE1_OVERLAP_4812_THRESHOLD)
    source = clamp(safe_float(row.get("source_mode_coupling")) / 0.25)
    target = clamp(safe_float(row.get("target_mode_localization")) / 0.25)
    sep = clamp(safe_float(row.get("mode_separation_score")))
    return float(ratio * math.sqrt(o448 * o4812) * math.sqrt(source * target) * (0.40 + 0.60 * sep))


def find_best_triad(cfg: crop.GeometryConfig) -> Dict[str, object]:
    frequencies, vectors = modal_frequencies_and_vectors(cfg)
    weights = nonlinear_weights(cfg)
    src = source_vector(cfg)
    src_norm = src / max(float(np.linalg.norm(src)), EPS)
    out = output_mask(cfg)
    start = 1 if len(frequencies) > 1 else 0
    max_modes = min(len(frequencies), 36)
    best: Dict[str, object] = {}
    best_score = -1.0
    couplings = np.asarray([abs(float(np.dot(vectors[:, idx], src_norm))) for idx in range(len(frequencies))])
    for i in range(start, max_modes):
        f_a = frequencies[i]
        if f_a <= EPS:
            continue
        for j in range(i + 1, max_modes):
            f_b = frequencies[j]
            rb = f_b / max(f_a, EPS)
            if abs(rb - 2.0) > 0.45:
                continue
            for k in range(j + 1, max_modes):
                f_c = frequencies[k]
                rc = f_c / max(f_a, EPS)
                if abs(rc - 3.0) > 0.65:
                    continue
                ratio_error = max(abs(rb - 2.0) / 2.0, abs(rc - 3.0) / 3.0)
                phi_a = vectors[:, i]
                phi_b = vectors[:, j]
                phi_c = vectors[:, k]
                overlap448 = modal_overlap(phi_a, phi_a, phi_b, weights)
                overlap4812 = modal_overlap(phi_a, phi_b, phi_c, weights)
                source_coupling = abs(float(np.dot(phi_a, src_norm)))
                target_local = float(np.sum((phi_c ** 2) * out) / max(np.sum(phi_c ** 2), EPS))
                sep = mode_separation_score(frequencies, (i, j, k))
                sym = symmetry_selectivity_score(couplings, i)
                score = (
                    clamp(1.0 - ratio_error / 0.09)
                    * math.sqrt(clamp(overlap448 / STAGE1_OVERLAP_448_THRESHOLD) * clamp(overlap4812 / STAGE1_OVERLAP_4812_THRESHOLD))
                    * math.sqrt(clamp(source_coupling / 0.25) * clamp(target_local / 0.25))
                    * (0.35 + 0.45 * sep + 0.20 * sym)
                )
                if score > best_score:
                    scale = SOURCE_HZ / max(f_a, EPS)
                    best_score = score
                    best = {
                        "modal_index_40": int(i),
                        "modal_index_80": int(j),
                        "modal_index_120": int(k),
                        "unscaled_modal_frequency_40": float(f_a),
                        "unscaled_modal_frequency_80": float(f_b),
                        "unscaled_modal_frequency_120": float(f_c),
                        "scaled_modal_frequency_40": float(f_a * scale),
                        "scaled_modal_frequency_80": float(f_b * scale),
                        "scaled_modal_frequency_120": float(f_c * scale),
                        "modal_frequency_error_40": abs(f_a * scale - SOURCE_HZ) / SOURCE_HZ,
                        "modal_frequency_error_80": abs(f_b * scale - GENERATED_HZ) / GENERATED_HZ,
                        "modal_frequency_error_120": abs(f_c * scale - TARGET_HZ) / TARGET_HZ,
                        "triad_ratio_error": float(ratio_error),
                        "overlap_448_abs": float(overlap448),
                        "overlap_4812_abs": float(overlap4812),
                        "source_mode_coupling": float(source_coupling),
                        "target_mode_localization": float(target_local),
                        "mode_separation_score": float(sep),
                        "symmetry_selectivity_score": float(sym),
                    }
    if not best:
        idxs = tuple(range(start, min(start + 3, len(frequencies))))
        while len(idxs) < 3:
            idxs = idxs + (idxs[-1] if idxs else 0,)
        i, j, k = idxs[:3]
        f_a, f_b, f_c = frequencies[i], frequencies[j], frequencies[k]
        scale = SOURCE_HZ / max(f_a, EPS)
        phi_a = vectors[:, i]
        phi_b = vectors[:, j]
        phi_c = vectors[:, k]
        best = {
            "modal_index_40": int(i),
            "modal_index_80": int(j),
            "modal_index_120": int(k),
            "unscaled_modal_frequency_40": float(f_a),
            "unscaled_modal_frequency_80": float(f_b),
            "unscaled_modal_frequency_120": float(f_c),
            "scaled_modal_frequency_40": float(f_a * scale),
            "scaled_modal_frequency_80": float(f_b * scale),
            "scaled_modal_frequency_120": float(f_c * scale),
            "modal_frequency_error_40": 0.0,
            "modal_frequency_error_80": abs(f_b * scale - GENERATED_HZ) / GENERATED_HZ,
            "modal_frequency_error_120": abs(f_c * scale - TARGET_HZ) / TARGET_HZ,
            "triad_ratio_error": 1.0,
            "overlap_448_abs": modal_overlap(phi_a, phi_a, phi_b, weights),
            "overlap_4812_abs": modal_overlap(phi_a, phi_b, phi_c, weights),
            "source_mode_coupling": abs(float(np.dot(phi_a, src_norm))),
            "target_mode_localization": float(np.sum((phi_c ** 2) * out) / max(np.sum(phi_c ** 2), EPS)),
            "mode_separation_score": mode_separation_score(frequencies, (i, j, k)),
            "symmetry_selectivity_score": symmetry_selectivity_score(couplings, i),
        }
    return best


def modal_row(cfg: crop.GeometryConfig) -> Dict[str, object]:
    row = find_best_triad(cfg)
    row.update(
        {
            "row_type": "modal_triad_row",
            "case_id": cfg.case_id,
            "parent_case_id": cfg.parent_case_id,
            "name": cfg.name,
            "family": cfg.family,
            "role": cfg.role,
            "control_kind": cfg.control_kind,
            "node_count": len(cfg.positions),
            "edge_count": len(cfg.edges),
            "source_node_count": len(cfg.source_nodes),
            "source_only_drive": "True",
            "direct_80khz_drive_present": "False",
            "direct_120khz_drive_present": "False",
            "target_frequency_injection_present": "False",
            "stage1_overlap_448_threshold": STAGE1_OVERLAP_448_THRESHOLD,
            "stage1_overlap_4812_threshold": STAGE1_OVERLAP_4812_THRESHOLD,
            "notes": cfg.notes,
        }
    )
    row["modal_triad_score"] = triad_score(row)
    return row


def modal_stage1_gate(row: Dict[str, object]) -> Tuple[bool, str]:
    failures: List[str] = []
    checks = [
        ("triad_ratio_error", 0.05, "<="),
        ("overlap_448_abs", STAGE1_OVERLAP_448_THRESHOLD, ">="),
        ("overlap_4812_abs", STAGE1_OVERLAP_4812_THRESHOLD, ">="),
        ("source_mode_coupling", 0.25, ">="),
        ("target_mode_localization", 0.25, ">="),
        ("geometry_dependency_score", 0.80, ">="),
        ("control_leakage", 0.15, "<"),
    ]
    for key, threshold, op in checks:
        value = safe_float(row.get(key), 99.0 if op in {"<", "<="} else -1.0)
        if op == "<=" and value > threshold:
            failures.append(f"{key}_above_{threshold:g}")
        elif op == "<" and value >= threshold:
            failures.append(f"{key}_not_below_{threshold:g}")
        elif op == ">=" and value < threshold:
            failures.append(f"{key}_below_{threshold:g}")
    return not failures, "pass" if not failures else ";".join(failures)


def apply_stage1_scores(rows: List[Dict[str, object]]) -> None:
    by_parent: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        parent = str(row.get("case_id") if row.get("role") == "discovery" else row.get("parent_case_id"))
        by_parent.setdefault(parent, []).append(row)
    for parent, bundle in by_parent.items():
        discovery = next((row for row in bundle if row.get("role") == "discovery" and row.get("case_id") == parent), None)
        if discovery is None:
            continue
        controls = [row for row in bundle if row.get("role") == "control"]
        cand_score = safe_float(discovery.get("modal_triad_score"))
        max_control = max((safe_float(row.get("modal_triad_score")) for row in controls), default=0.0)
        discovery["max_control_triad_score"] = max_control
        discovery["control_leakage"] = clamp(max_control / max(cand_score, EPS))
        discovery["geometry_dependency_score"] = clamp(1.0 - max_control / max(cand_score, EPS))
        passed, reason = modal_stage1_gate(discovery)
        discovery["stage1_passed"] = str(passed)
        discovery["stage1_pass_fail_reason"] = reason
        discovery["stage1_label"] = "modal_triad_stage1_candidate" if passed else "modal_triad_stage1_fail"
        for control in controls:
            leakage = clamp(safe_float(control.get("modal_triad_score")) / max(cand_score, EPS))
            control["max_control_triad_score"] = ""
            control["control_leakage"] = leakage
            control["geometry_dependency_score"] = ""
            control["stage1_passed"] = str(leakage < 0.15)
            control["stage1_pass_fail_reason"] = "control_dead" if leakage < 0.15 else "control_leakage"
            control["stage1_label"] = "control_dead" if leakage < 0.15 else "control_leakage"


def select_stage2_configs(stage1_rows: List[Dict[str, object]], configs: Sequence[crop.GeometryConfig]) -> List[crop.GeometryConfig]:
    by_id = {cfg.case_id: cfg for cfg in configs}
    discoveries = [row for row in stage1_rows if row.get("role") == "discovery"]
    ranked = sorted(
        discoveries,
        key=lambda row: (
            row.get("stage1_label") == "modal_triad_stage1_candidate",
            safe_float(row.get("modal_triad_score")),
            -safe_float(row.get("control_leakage")),
        ),
        reverse=True,
    )
    selected_ids = [str(row.get("case_id")) for row in ranked[:STAGE2_TOP_DISCOVERY_COUNT]]
    selected: List[crop.GeometryConfig] = []
    for case_id in selected_ids:
        if case_id not in by_id:
            continue
        selected.append(by_id[case_id])
        selected.extend(cfg for cfg in configs if cfg.parent_case_id == case_id)
    return selected


def simulate_stage2_config(cfg: crop.GeometryConfig) -> Tuple[str, Dict[str, object]]:
    return cfg.case_id, crop.base_metrics(crop.simulate(cfg))


def stage2_gate(row: Dict[str, object]) -> Tuple[bool, str]:
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
        ("modal_triad_dependency_score", 0.80, ">="),
    ]
    for key, threshold, op in checks:
        value = safe_float(row.get(key), -1.0 if op == ">=" else 99.0)
        if op == ">=" and value < threshold:
            failures.append(f"{key}_below_{threshold:g}")
        elif op == "<" and value >= threshold:
            failures.append(f"{key}_not_below_{threshold:g}")
    return not failures, "pass" if not failures else ";".join(failures)


def apply_stage2_scores(stage2_rows: List[Dict[str, object]], stage1_by_id: Dict[str, Dict[str, object]]) -> None:
    by_parent: Dict[str, List[Dict[str, object]]] = {}
    for row in stage2_rows:
        parent = str(row.get("case_id") if row.get("role") == "discovery" else row.get("parent_case_id"))
        by_parent.setdefault(parent, []).append(row)
    for parent, bundle in by_parent.items():
        discovery = next((row for row in bundle if row.get("role") == "discovery" and row.get("case_id") == parent), None)
        if discovery is None:
            continue
        controls = [row for row in bundle if row.get("role") == "control"]
        cand_power = crop.row_power(discovery)
        max_control_power = max((crop.row_power(row) for row in controls), default=0.0)
        stage1_row = stage1_by_id.get(parent, {})
        modal_dep = safe_float(stage1_row.get("geometry_dependency_score"))
        discovery["object_reference_gain_120khz"] = cand_power / max(max_control_power, EPS)
        discovery["max_control_leakage"] = clamp(max_control_power / max(cand_power, EPS))
        discovery["modal_triad_dependency_score"] = modal_dep
        discovery["stage1_modal_triad_score"] = stage1_row.get("modal_triad_score", "")
        discovery["stage1_triad_ratio_error"] = stage1_row.get("triad_ratio_error", "")
        passed, reason = stage2_gate(discovery)
        discovery["stage2_passed"] = str(passed)
        discovery["stage2_pass_fail_reason"] = reason
        discovery["promotion_category"] = "acoustic_sacred_modal_triad_candidate" if passed else "stage2_row_fail"
        for control in controls:
            leakage = clamp(crop.row_power(control) / max(cand_power, EPS))
            control["object_reference_gain_120khz"] = crop.row_power(control) / max(cand_power, EPS)
            control["max_control_leakage"] = leakage
            control["modal_triad_dependency_score"] = ""
            control["stage1_modal_triad_score"] = stage1_by_id.get(str(control.get("case_id")), {}).get("modal_triad_score", "")
            control["stage1_triad_ratio_error"] = stage1_by_id.get(str(control.get("case_id")), {}).get("triad_ratio_error", "")
            control["stage2_passed"] = str(leakage < 0.15)
            control["stage2_pass_fail_reason"] = "control_dead" if leakage < 0.15 else "control_leakage"
            control["promotion_category"] = "control_dead" if leakage < 0.15 else "control_leakage"


def stage1_failure_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") != "discovery" or row.get("stage1_label") == "modal_triad_stage1_candidate":
            continue
        out.append(
            {
                "row_type": "stage1_failure",
                "case_id": row.get("case_id"),
                "family": row.get("family"),
                "stage": "stage1_modal",
                "pass_fail_reason": row.get("stage1_pass_fail_reason"),
                "triad_ratio_error": row.get("triad_ratio_error"),
                "overlap_448_abs": row.get("overlap_448_abs"),
                "overlap_4812_abs": row.get("overlap_4812_abs"),
                "source_mode_coupling": row.get("source_mode_coupling"),
                "target_mode_localization": row.get("target_mode_localization"),
                "geometry_dependency_score": row.get("geometry_dependency_score"),
                "control_leakage": row.get("control_leakage"),
            }
        )
    return out


def stage2_failure_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        if row.get("role") != "discovery" or row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate":
            continue
        out.append(
            {
                "row_type": "stage2_failure",
                "case_id": row.get("case_id"),
                "family": row.get("family"),
                "stage": "stage2_nonlinear",
                "pass_fail_reason": row.get("stage2_pass_fail_reason"),
                "phase_lock_80khz": row.get("phase_lock_80khz"),
                "phase_lock_120khz": row.get("phase_lock_120khz"),
                "raw_pre_readout_120khz_purity": row.get("raw_pre_readout_120khz_purity"),
                "distributed_120khz_coherent_growth": row.get("distributed_120khz_coherent_growth"),
                "object_reference_gain_120khz": row.get("object_reference_gain_120khz"),
                "max_control_leakage": row.get("max_control_leakage"),
                "modal_triad_dependency_score": row.get("modal_triad_dependency_score"),
            }
        )
    return out


def aggregate(stage1_rows: List[Dict[str, object]], stage2_rows: List[Dict[str, object]]) -> Dict[str, object]:
    stage1_discovery = [row for row in stage1_rows if row.get("role") == "discovery"]
    stage1_controls = [row for row in stage1_rows if row.get("role") == "control"]
    stage2_discovery = [row for row in stage2_rows if row.get("role") == "discovery"]
    stage2_controls = [row for row in stage2_rows if row.get("role") == "control"]
    stage1_candidates = [row for row in stage1_discovery if row.get("stage1_label") == "modal_triad_stage1_candidate"]
    promoted = [row for row in stage2_discovery if row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate"]
    best_modal = max(
        stage1_discovery,
        key=lambda row: (
            safe_float(row.get("modal_triad_score")),
            -safe_float(row.get("control_leakage")),
            safe_float(row.get("overlap_448_abs")),
            safe_float(row.get("overlap_4812_abs")),
        ),
        default={},
    )
    best_stage2 = max(
        stage2_discovery,
        key=lambda row: (
            row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate",
            safe_float(row.get("object_reference_gain_120khz")),
            safe_float(row.get("raw_pre_readout_120khz_purity")),
            safe_float(row.get("phase_lock_120khz")),
        ),
        default={},
    )
    stage1_leaks = [row for row in stage1_controls if row.get("stage1_label") == "control_leakage"]
    stage2_leaks = [row for row in stage2_controls if row.get("promotion_category") == "control_leakage"]
    strongest_modal_leak = max(stage1_leaks, key=lambda row: safe_float(row.get("control_leakage")), default={})
    strongest_stage2_leak = max(stage2_leaks, key=lambda row: safe_float(row.get("max_control_leakage")), default={})
    counts: Dict[str, int] = {}
    for row in stage1_discovery:
        if row.get("stage1_label") == "modal_triad_stage1_candidate":
            continue
        reason = str(row.get("stage1_pass_fail_reason", "unknown")).split(";")[0]
        counts[f"stage1:{reason}"] = counts.get(f"stage1:{reason}", 0) + 1
    for row in stage2_discovery:
        if row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate":
            continue
        reason = str(row.get("stage2_pass_fail_reason", "unknown")).split(";")[0]
        counts[f"stage2:{reason}"] = counts.get(f"stage2:{reason}", 0) + 1
    label = "acoustic_sacred_modal_triad_candidate" if promoted else ("modal_triad_stage1_only" if stage1_candidates else "not_promoted")
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "acoustic_412_sacred_modal_triads",
        "aggregate_label": label,
        "decision": "no_hardware_build_readiness" if not promoted else "requires_independent_robustness_before_build",
        "stage1_discovery_rows": len(stage1_discovery),
        "stage1_control_rows": len(stage1_controls),
        "stage1_candidate_count": len(stage1_candidates),
        "stage1_control_leak_count": len(stage1_leaks),
        "stage2_discovery_rows": len(stage2_discovery),
        "stage2_control_rows": len(stage2_controls),
        "stage2_promoted_count": len(promoted),
        "stage2_control_leak_count": len(stage2_leaks),
        "best_modal_case_id": best_modal.get("case_id", ""),
        "best_modal_family": best_modal.get("family", ""),
        "best_modal_triad_score": best_modal.get("modal_triad_score", ""),
        "best_modal_triad_ratio_error": best_modal.get("triad_ratio_error", ""),
        "best_modal_overlap_448_abs": best_modal.get("overlap_448_abs", ""),
        "best_modal_overlap_4812_abs": best_modal.get("overlap_4812_abs", ""),
        "best_modal_source_mode_coupling": best_modal.get("source_mode_coupling", ""),
        "best_modal_target_mode_localization": best_modal.get("target_mode_localization", ""),
        "best_modal_geometry_dependency_score": best_modal.get("geometry_dependency_score", ""),
        "best_modal_control_leakage": best_modal.get("control_leakage", ""),
        "best_stage2_case_id": best_stage2.get("case_id", ""),
        "best_stage2_family": best_stage2.get("family", ""),
        "best_stage2_label": best_stage2.get("promotion_category", ""),
        "best_stage2_phase_lock_120khz": best_stage2.get("phase_lock_120khz", ""),
        "best_stage2_raw_pre_readout_120khz_purity": best_stage2.get("raw_pre_readout_120khz_purity", ""),
        "best_stage2_coherent_growth": best_stage2.get("distributed_120khz_coherent_growth", ""),
        "best_stage2_object_reference_gain_120khz": best_stage2.get("object_reference_gain_120khz", ""),
        "best_stage2_max_control_leakage": best_stage2.get("max_control_leakage", ""),
        "strongest_modal_leaking_control": strongest_modal_leak.get("case_id", ""),
        "strongest_modal_leaking_control_kind": strongest_modal_leak.get("control_kind", ""),
        "strongest_modal_leaking_control_score": strongest_modal_leak.get("control_leakage", ""),
        "strongest_stage2_leaking_control": strongest_stage2_leak.get("case_id", ""),
        "strongest_stage2_leaking_control_kind": strongest_stage2_leak.get("control_kind", ""),
        "strongest_stage2_leaking_control_score": strongest_stage2_leak.get("max_control_leakage", ""),
        "dominant_failure_mode": max(counts, key=counts.get) if counts else "none",
        "failure_mode_counts_json": json.dumps(counts, sort_keys=True),
        "recommended_next_step": "do not build; redesign modal geometry or return to compact-guide retiming" if not promoted else "independent robustness validation before any build claim",
    }


def selected_diagram_configs(
    agg: Dict[str, object],
    configs: Sequence[crop.GeometryConfig],
    stage1_rows: List[Dict[str, object]],
    stage2_rows: List[Dict[str, object]],
) -> Dict[str, crop.GeometryConfig]:
    by_id = {cfg.case_id: cfg for cfg in configs}
    selected: Dict[str, crop.GeometryConfig] = {}
    for label, key in (
        ("best_modal_triad_geometry", "best_modal_case_id"),
        ("strongest_leaking_control", "strongest_modal_leaking_control"),
        ("best_stage2_row", "best_stage2_case_id"),
    ):
        case_id = str(agg.get(key, ""))
        if case_id in by_id:
            selected[label] = by_id[case_id]
    stage2_failed = [row for row in stage2_rows if row.get("role") == "discovery" and row.get("promotion_category") != "acoustic_sacred_modal_triad_candidate"]
    best_failed = max(
        stage2_failed,
        key=lambda row: (
            safe_float(row.get("object_reference_gain_120khz")),
            safe_float(row.get("phase_lock_120khz")),
            safe_float(row.get("raw_pre_readout_120khz_purity")),
        ),
        default={},
    )
    if best_failed.get("case_id") in by_id:
        selected["best_failed_near_miss"] = by_id[str(best_failed.get("case_id"))]
    promoted = [row for row in stage2_rows if row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate"]
    if promoted and str(promoted[0].get("case_id")) in by_id:
        selected["promoted_row"] = by_id[str(promoted[0].get("case_id"))]
    return selected


def write_diagrams(out_dir: Path, selected: Dict[str, crop.GeometryConfig]) -> Dict[str, str]:
    paths: Dict[str, str] = {}
    for label, cfg in selected.items():
        path = out_dir / f"{label}_{cfg.case_id}.svg"
        crop.geometry_svg(cfg, path, label.replace("_", " ").title())
        paths[label] = str(path)
    return paths


def write_readme(out_dir: Path, agg: Dict[str, object], diagram_paths: Dict[str, str]) -> None:
    lines = [
        "# Acoustic 4->8->12 Sacred Modal Triads",
        "",
        "Sacred-geometry names are used only as candidate acoustic graph topologies. This run does not prove sacred geometry, does not claim crop circles are messages, and does not imply hardware build readiness.",
        "",
        "## Direct Answers",
        "",
        f"- Did any geometry pass Stage 1 modal triads? {agg.get('stage1_candidate_count')}.",
        f"- Did any geometry pass Stage 2 nonlinear raw purity/growth? {agg.get('stage2_promoted_count')}.",
        f"- Aggregate label: {agg.get('aggregate_label')}.",
        f"- Decision: {agg.get('decision')}.",
        f"- Best modal family: {agg.get('best_modal_family')} ({agg.get('best_modal_case_id')}).",
        f"- Best modal triad score: {agg.get('best_modal_triad_score')}.",
        f"- Best modal geometry dependency: {agg.get('best_modal_geometry_dependency_score')}.",
        f"- Best Stage 2 family: {agg.get('best_stage2_family')} ({agg.get('best_stage2_case_id')}).",
        f"- Best Stage 2 120 kHz purity: {agg.get('best_stage2_raw_pre_readout_120khz_purity')}.",
        f"- Best Stage 2 coherent growth: {agg.get('best_stage2_coherent_growth')}.",
        f"- Strongest modal leaking control: {agg.get('strongest_modal_leaking_control')} {agg.get('strongest_modal_leaking_control_kind')} score={agg.get('strongest_modal_leaking_control_score')}.",
        f"- Strongest Stage 2 leaking control: {agg.get('strongest_stage2_leaking_control')} {agg.get('strongest_stage2_leaking_control_kind')} score={agg.get('strongest_stage2_leaking_control_score')}.",
        f"- Recommended next step: {agg.get('recommended_next_step')}.",
        "",
        "## Scope",
        "",
        "- Stage 1 computes graph Laplacian acoustic modes and searches 1:2:3 modal triads.",
        "- Stage 1 scores nonlinear modal overlap for A+A->B and A+B->C, source coupling, target localization, mode separation, and matched-control leakage.",
        "- Stage 2 time-simulates only the top modal-triad geometry bundles using source-only 40 kHz drive.",
        "- Stage 2 forbids direct 80 kHz drive, direct 120 kHz drive, and target-frequency injection.",
        "- Promotion requires real raw 120 kHz purity and coherent growth, not phase lock alone.",
        "",
        "## Outputs",
        "",
        "- `summary.json`",
        "- `summary.csv`",
        "- `modal_triads.csv`",
        "- `promoted_modal_geometries.csv`",
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
            "## Conservative Rule",
            "",
            "Do not treat a Stage 1 modal triad as promotion. A geometry only promotes if Stage 2 also beats strict matched controls and produces raw 120 kHz purity/growth.",
        ]
    )
    (out_dir / "README_ACOUSTIC_412_SACRED_MODAL_TRIADS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(out_dir: Path, workers: int | None = None) -> Dict[str, object]:
    ensure_dir(out_dir)
    configs = build_configs()
    stage1_rows = [modal_row(cfg) for cfg in configs]
    apply_stage1_scores(stage1_rows)
    stage1_by_id = {str(row.get("case_id")): row for row in stage1_rows}
    stage2_configs = select_stage2_configs(stage1_rows, configs)
    worker_count = workers if workers is not None else min(8, max(1, (os.cpu_count() or 2) - 1))
    stage2_by_id: Dict[str, Dict[str, object]] = {}
    if worker_count <= 1:
        for cfg in stage2_configs:
            case_id, row = simulate_stage2_config(cfg)
            stage2_by_id[case_id] = row
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(simulate_stage2_config, cfg) for cfg in stage2_configs]
            for future in as_completed(futures):
                case_id, row = future.result()
                stage2_by_id[case_id] = row
    stage2_rows = [stage2_by_id[cfg.case_id] for cfg in stage2_configs]
    apply_stage2_scores(stage2_rows, stage1_by_id)
    agg = aggregate(stage1_rows, stage2_rows)
    diagrams = write_diagrams(out_dir, selected_diagram_configs(agg, configs, stage1_rows, stage2_rows))
    all_rows = [agg] + stage1_rows + stage2_rows
    promoted_rows = [row for row in stage2_rows if row.get("promotion_category") == "acoustic_sacred_modal_triad_candidate"]

    write_csv(out_dir / "summary.csv", all_rows)
    write_csv(out_dir / "modal_triads.csv", stage1_rows)
    write_csv(
        out_dir / "promoted_modal_geometries.csv",
        promoted_rows,
        fieldnames=[
            "case_id",
            "family",
            "promotion_category",
            "phase_lock_80khz",
            "phase_lock_120khz",
            "raw_pre_readout_120khz_purity",
            "distributed_120khz_coherent_growth",
            "object_reference_gain_120khz",
            "max_control_leakage",
            "modal_triad_dependency_score",
            "stage2_pass_fail_reason",
        ],
    )
    write_csv(out_dir / "matched_controls.csv", [row for row in stage1_rows + stage2_rows if row.get("role") == "control"])
    write_csv(out_dir / "failure_modes.csv", stage1_failure_rows(stage1_rows) + stage2_failure_rows(stage2_rows))
    (out_dir / "summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": agg,
                    "rows": all_rows,
                    "stage2_case_ids": [cfg.case_id for cfg in stage2_configs],
                    "diagram_paths": diagrams,
                    "configs": [asdict(cfg) for cfg in configs],
                    "control_kinds": list(CONTROL_KINDS),
                    "thresholds": {
                        "stage1_overlap_448": STAGE1_OVERLAP_448_THRESHOLD,
                        "stage1_overlap_4812": STAGE1_OVERLAP_4812_THRESHOLD,
                        "stage2_top_discovery_count": STAGE2_TOP_DISCOVERY_COUNT,
                    },
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_readme(out_dir, agg, diagrams)
    return {"aggregate": agg, "stage1_rows": stage1_rows, "stage2_rows": stage2_rows, "diagram_paths": diagrams}


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen sacred-geometry-inspired acoustic graphs for 40/80/120 kHz modal triads.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel Stage 2 workers; defaults to up to 8.")
    parser.add_argument("--run", action="store_true", help="Run the modal-triad screen and bounded nonlinear follow-up.")
    args = parser.parse_args()
    if not args.run:
        print("Use --run to execute the sacred modal-triad screen.")
        return
    result = run(Path(args.out), workers=args.workers)
    agg = result["aggregate"]
    print(
        json.dumps(
            sanitize(
                {
                    "aggregate_label": agg.get("aggregate_label"),
                    "decision": agg.get("decision"),
                    "stage1_candidate_count": agg.get("stage1_candidate_count"),
                    "stage2_promoted_count": agg.get("stage2_promoted_count"),
                    "best_modal_case_id": agg.get("best_modal_case_id"),
                    "best_modal_family": agg.get("best_modal_family"),
                    "best_modal_triad_score": agg.get("best_modal_triad_score"),
                    "best_stage2_case_id": agg.get("best_stage2_case_id"),
                    "best_stage2_raw_pre_readout_120khz_purity": agg.get("best_stage2_raw_pre_readout_120khz_purity"),
                    "summary": str(Path(args.out) / "summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
