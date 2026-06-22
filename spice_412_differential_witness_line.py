#!/usr/bin/env python3
"""Differential witness-line test for the 4->8->12 electrical bridge.

This experiment asks a narrower question than the prior high-Q extraction
tracks: does coherent 150 MHz power grow inside the transmission line before
any readout can manufacture apparent purity?  Every discovery row is paired
against its own matched RSG shadow.  Promotion depends on pre-extraction
object/reference separation, not absolute post-filter purity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

import spice_412_hybrid_purity_lockin as lockin
import spice_412_varactor_nltl_design as design


OUT_DIR = Path("runs") / "spice_412_differential_witness_line"
SOURCE_HZ = design.SOURCE_HZ
GENERATED_HZ = design.GENERATED_HZ
TARGET_HZ = design.TARGET_HZ
EPS = 1.0e-30

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
class WitnessCase(lockin.LockinCase):
    trial_id: str = ""
    paired_trial_name: str = ""
    side: str = "object"
    object_family: str = ""
    reference_transform: str = ""
    witness_role: str = "paired_witness"
    qpm_pattern_mode: str = "native"
    varactor_polarity_mode: str = "native"
    matched_shadow_of: str = ""
    direct_ceiling_denominator_only: bool = False


@dataclass(frozen=True)
class WitnessTrial:
    trial_id: str
    name: str
    object_case: WitnessCase
    reference_case: WitnessCase


@dataclass(frozen=True)
class WitnessExport:
    case: WitnessCase
    netlist_path: Path
    csv_path: Path


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
    return lockin.safe_float(value, default)


def clean_name(value: str) -> str:
    return lockin.clean_name(value)


def spice_num(value: float) -> str:
    return design.spice_num(value)


def to_witness_case(base: lockin.LockinCase, **updates: object) -> WitnessCase:
    data = asdict(base)
    data.update(updates)
    return WitnessCase(**data)


def clone_case(base: WitnessCase, **updates: object) -> WitnessCase:
    data = asdict(base)
    data.update(updates)
    return WitnessCase(**data)


def deterministic_sign(seed: str, idx: int) -> float:
    digest = hashlib.sha256(f"{seed}:{idx}".encode("utf-8")).digest()
    return -1.0 if digest[0] & 1 else 1.0


def bmag_sign(case: WitnessCase, idx: int) -> float:
    if case.qpm_pattern_mode == "none":
        return 1.0
    if case.qpm_pattern_mode == "shuffled":
        return deterministic_sign(case.paired_trial_name or case.case_id, idx)
    if case.qpm_pattern_mode == "chirped":
        local_period = max(2, int(round(3.0 + 7.0 * idx / max(case.cell_count, 1))))
        return -1.0 if (idx // local_period) % 2 else 1.0
    if case.qpm_pattern_mode in {"alternating", "alternating_magnetic_bias"}:
        period = max(2, case.cell_count // 8)
        return -1.0 if (idx // period) % 2 else 1.0
    return 1.0


def apply_bmag_pattern(text: str, case: WitnessCase) -> str:
    if case.qpm_pattern_mode == "native":
        return text

    coeff_re = re.compile(r"(I=\{\()([-+0-9.eE]+)(\)\*kmag)")

    def repl(line: str) -> str:
        match_idx = re.match(r"(Bmag)(\d+)\s", line)
        if not match_idx:
            return line
        idx = int(match_idx.group(2))
        sign = bmag_sign(case, idx)

        def coeff(match: re.Match[str]) -> str:
            try:
                value = abs(float(match.group(2))) * sign
            except ValueError:
                return match.group(0)
            return f"{match.group(1)}{spice_num(value)}{match.group(3)}"

        return coeff_re.sub(coeff, line, count=1)

    return "\n".join(repl(line) for line in text.splitlines()) + "\n"


def apply_varactor_polarity(text: str, case: WitnessCase) -> str:
    if case.varactor_polarity_mode != "alternating":
        return text
    pattern = re.compile(r"^(Dvar(\d+)\s+)(\S+)\s+(\S+)(\s+DVAR.*)$")
    period = max(2, case.cell_count // 8)
    lines: List[str] = []
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            lines.append(line)
            continue
        idx = int(match.group(2))
        flip = (idx // period) % 2 == 1
        if flip:
            lines.append(f"{match.group(1)}{match.group(4)} {match.group(3)}{match.group(5)}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def original_measure_node(netlist: str, fallback: str) -> str:
    for line in netlist.splitlines():
        stripped = line.strip()
        if not stripped.startswith("wrdata "):
            continue
        voltage_tokens: List[str] = []
        parts = stripped.replace(",", " ").split()
        for token in parts:
            token_lower = token.lower()
            if token_lower.startswith("v(") and token.endswith(")"):
                voltage_tokens.append(token[2:-1])
        if voltage_tokens:
            return voltage_tokens[-1]
    return fallback


def tap_nodes(case: WitnessCase) -> List[Tuple[str, int, str]]:
    nodes: List[Tuple[str, int, str]] = []
    for label, frac in TAP_FRACTIONS:
        idx = min(case.cell_count, max(0, int(round(frac * case.cell_count))))
        nodes.append((label, idx, design.n(idx)))
    return nodes


def instrument_netlist(case: WitnessCase, csv_path: Path) -> str:
    text = lockin.netlist_for_case(case, csv_path)
    text = apply_bmag_pattern(text, case)
    text = apply_varactor_polarity(text, case)

    raw_node = design.n(case.cell_count)
    post_node = original_measure_node(text, raw_node)
    node_exprs = " ".join(f"v({node})" for _, _, node in tap_nodes(case))
    replacement = f"wrdata {csv_path.name} time {node_exprs} v({post_node}) i(Vsrc) i(Vbias)"
    lines: List[str] = []
    replaced = False
    for line in text.splitlines():
        if line.strip().startswith("wrdata "):
            lines.append(replacement)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise ValueError(f"could not find wrdata line for {case.case_id}")
    lines.insert(
        1,
        (
            f"* Differential witness probes: trial={case.trial_id}; side={case.side}; "
            f"raw_pre_extraction={raw_node}; diagnostic_post={post_node}; "
            f"source_only={case.source_only_drive}; no direct target injection."
        ),
    )
    return "\n".join(lines) + "\n"


def base_object_case(trial_id: str, family: str, idx: int) -> WitnessCase:
    seed = "h025" if idx % 2 else "h024"
    cells = 64 if family != "object_50_100_150mhz_standard_line" else 80
    z0 = 75.0 if idx % 3 else 100.0
    length_m = 0.50 if family != "object_low_frequency_10_20_30mhz_magnetic_line" else 0.76
    base = lockin.make_case(
        f"{trial_id}_object",
        seed,
        extraction_topology="none",
        cleanup="none",
        notch50=False,
        notch100=False,
        cells=cells,
        z0=z0,
        length_m=length_m,
        output_load=z0 * 2.0,
        drive_v=2.35 if seed == "h025" else 2.45,
        cjo_scale=1.20,
        bias_v=3.8,
        magnetic_strength=0.48,
        magnetic_sat_i=0.10,
        magnetic_loss=0.22,
        varactor_fraction=0.48,
        magnetic_start=0.40,
        magnetic_end=0.94,
        overlap=0.08,
        magnetic_spacing=3,
        magnetic_count=20,
        distributed_spacing=0,
        distributed_strength=0.0,
        family=family,
        role="discovery",
        notes=f"Paired differential witness object family {family}; raw/tap metrics are promotion basis.",
    )
    name = f"{trial_id}_{family}_object"
    witness = to_witness_case(
        base,
        case_id=f"{trial_id}_object",
        name=clean_name(name),
        filename=f"{clean_name(name)}.cir",
        trial_id=trial_id,
        paired_trial_name="",
        side="object",
        object_family=family,
        reference_transform="object",
        qpm_pattern_mode="alternating",
        varactor_polarity_mode="native",
        cleanup_topology="none",
        extraction_topology="none",
        pre_notch_50=False,
        pre_notch_100=False,
        source_rejection=False,
        generated_rejection=False,
        target_bandpass_coupling=0.0,
        post_filter_strength=0.0,
    )

    updates: Dict[str, object] = {}
    if family == "object_braided_qpm_varactor_magnetic":
        updates.update(
            varactor_block_fraction=0.64,
            magnetic_block_start_fraction=0.16,
            magnetic_block_end_fraction=0.98,
            overlap_fraction=0.18,
            alternating_overlap_only=True,
            qpm_pattern_mode="alternating",
            magnetic_dc_bias_proxy=0.25,
            hybrid_relative_phase=0.35,
        )
    elif family == "object_varactor_first_magnetic_second":
        updates.update(
            varactor_block_fraction=0.38,
            magnetic_block_start_fraction=0.46,
            magnetic_block_end_fraction=0.98,
            overlap_fraction=0.04,
            qpm_pattern_mode="alternating",
        )
    elif family == "object_magnetic_first_varactor_second":
        updates.update(
            varactor_block_fraction=0.82,
            magnetic_block_start_fraction=0.04,
            magnetic_block_end_fraction=0.58,
            overlap_fraction=0.02,
            magnetic_strength=0.58,
            qpm_pattern_mode="alternating_magnetic_bias",
        )
    elif family == "object_chirped_qpm_bias":
        updates.update(
            qpm_pattern_mode="chirped",
            magnetic_dc_bias_proxy=0.55,
            target_phase_velocity_scale=0.992,
            generated_phase_velocity_scale=1.006,
            phase_velocity_m_s=5.08e6,
        )
    elif family == "object_alternating_polarity_varactors":
        updates.update(
            varactor_polarity_mode="alternating",
            varactor_block_fraction=0.72,
            magnetic_block_start_fraction=0.34,
            magnetic_block_end_fraction=0.94,
            overlap_fraction=0.12,
            qpm_pattern_mode="alternating",
        )
    elif family == "object_alternating_magnetic_bias":
        updates.update(
            qpm_pattern_mode="alternating_magnetic_bias",
            magnetic_dc_bias_proxy=0.70,
            magnetic_strength=0.62,
            magnetic_section_spacing=2,
            magnetic_section_count=26,
        )
    elif family == "object_dual_lane_directional_coupled":
        updates.update(
            varactor_block_fraction=0.56,
            magnetic_block_start_fraction=0.20,
            magnetic_block_end_fraction=0.90,
            overlap_fraction=0.20,
            hybrid_relative_phase=1.10,
            magnetic_section_spacing=2,
            varactor_section_spacing=1,
            qpm_pattern_mode="alternating",
            notes="Dual-lane directional-coupled proxy using interleaved varactor/magnetic sections.",
        )
    elif family == "object_generated_velocity_trimmed_qpm":
        updates.update(
            generated_phase_velocity_scale=0.985,
            target_phase_velocity_scale=1.002,
            phase_velocity_m_s=5.12e6,
            qpm_pattern_mode="alternating",
        )
    elif family == "object_target_velocity_trimmed_qpm":
        updates.update(
            generated_phase_velocity_scale=1.004,
            target_phase_velocity_scale=0.988,
            phase_velocity_m_s=5.05e6,
            qpm_pattern_mode="alternating",
        )
    elif family == "object_low_frequency_10_20_30mhz_magnetic_line":
        updates.update(
            fixed_cap_only=True,
            cjo_scale=0.0,
            magnetic_strength=0.88,
            magnetic_section_count=30,
            magnetic_section_spacing=2,
            magnetic_saturation_current_a=0.16,
            magnetic_core_loss_proxy=0.30,
            source_amplitude_v=1.90,
            qpm_pattern_mode="alternating_magnetic_bias",
            notes=(
                "Low-frequency magnetic-line surrogate kept on the 50/100/150 MHz projection grid "
                "for this first paired ngspice smoke."
            ),
        )
    elif family == "object_50_100_150mhz_standard_line":
        updates.update(
            cell_count=80,
            total_length_m=0.50,
            z0_ohm=75.0,
            varactor_block_fraction=0.50,
            magnetic_block_start_fraction=0.50,
            overlap_fraction=0.06,
            qpm_pattern_mode="alternating",
        )
    elif family == "no_qpm_baseline":
        updates.update(qpm_pattern_mode="none", varactor_polarity_mode="native")

    if updates:
        witness = clone_case(witness, **updates)
    return witness


def reference_from_object(obj: WitnessCase, transform: str) -> WitnessCase:
    updates: Dict[str, object] = {
        "case_id": obj.case_id.replace("_object", "_reference"),
        "side": "reference",
        "role": "control",
        "reference_transform": transform,
        "matched_shadow_of": obj.case_id,
        "witness_role": "matched_shadow",
        "notes": f"Matched RSG shadow for {obj.object_family}; transform={transform}.",
    }

    if transform == "shuffled_qpm_shadow":
        updates.update(qpm_pattern_mode="shuffled")
    elif transform == "phase_mismatched_shadow":
        updates.update(
            generated_phase_velocity_scale=0.88,
            target_phase_velocity_scale=1.18,
            phase_velocity_m_s=4.15e6,
            phase_velocity_error_50=-0.17,
            phase_velocity_error_100=-0.12,
            phase_velocity_error_150=0.18,
        )
    elif transform == "generated_path_suppressed_shadow":
        updates.update(
            nonlinear_fraction=0.12,
            cjo_scale=0.22,
            varactor_block_fraction=0.10,
            varactor_section_count=max(4, obj.varactor_section_count // 5),
            generated_phase_velocity_scale=0.74,
            magnetic_block_start_fraction=0.64,
            magnetic_strength=max(0.05, obj.magnetic_strength * 0.38),
        )
    elif transform == "target_velocity_detuned_shadow":
        updates.update(
            target_phase_velocity_scale=0.78,
            phase_velocity_m_s=3.85e6,
            phase_velocity_error_150=-0.22,
        )
    elif transform == "linear_no_nonlinearity_shadow":
        updates.update(
            fixed_cap_only=True,
            cjo_scale=0.0,
            nonlinear_fraction=0.0,
            nonlinear_strength_scale=0.0,
            magnetic_strength=0.0,
            magnetic_section_count=0,
            qpm_pattern_mode="none",
            varactor_polarity_mode="native",
        )
    elif transform == "pure_varactor_shadow":
        updates.update(
            magnetic_strength=0.0,
            magnetic_section_count=0,
            magnetic_core_loss_proxy=0.0,
            magnetic_hysteresis_loss=0.0,
            qpm_pattern_mode="none",
        )
    elif transform == "pure_magnetic_shadow":
        updates.update(
            fixed_cap_only=True,
            cjo_scale=0.0,
            nonlinear_fraction=0.0,
            magnetic_strength=max(0.65, obj.magnetic_strength),
            magnetic_section_count=max(16, obj.magnetic_section_count),
            qpm_pattern_mode=obj.qpm_pattern_mode,
            varactor_polarity_mode="native",
        )
    elif transform == "too_short_shadow":
        updates.update(total_length_m=max(0.05, obj.total_length_m * 0.22))
    elif transform == "too_lossy_shadow":
        updates.update(
            series_loss_ohm_scale=obj.series_loss_ohm_scale * 30.0,
            shunt_loss_ohm=min(obj.shunt_loss_ohm, 9_000.0),
            magnetic_core_loss_proxy=max(obj.magnetic_core_loss_proxy, 2.0),
            magnetic_hysteresis_loss=max(obj.magnetic_hysteresis_loss, 1.0),
        )
    else:
        raise ValueError(f"unknown reference transform {transform}")

    name = clean_name(f"{obj.trial_id}_{obj.object_family}__vs__{transform}_reference")
    updates.update(name=name, filename=f"{name}.cir")
    return clone_case(obj, **updates)


def build_trials() -> List[WitnessTrial]:
    plan = [
        ("object_braided_qpm_varactor_magnetic", "shuffled_qpm_shadow"),
        ("object_varactor_first_magnetic_second", "pure_varactor_shadow"),
        ("object_magnetic_first_varactor_second", "pure_magnetic_shadow"),
        ("object_chirped_qpm_bias", "target_velocity_detuned_shadow"),
        ("object_alternating_polarity_varactors", "generated_path_suppressed_shadow"),
        ("object_alternating_magnetic_bias", "phase_mismatched_shadow"),
        ("object_dual_lane_directional_coupled", "linear_no_nonlinearity_shadow"),
        ("object_generated_velocity_trimmed_qpm", "too_lossy_shadow"),
        ("object_target_velocity_trimmed_qpm", "too_short_shadow"),
        ("object_low_frequency_10_20_30mhz_magnetic_line", "phase_mismatched_shadow"),
        ("object_50_100_150mhz_standard_line", "shuffled_qpm_shadow"),
        ("no_qpm_baseline", "linear_no_nonlinearity_shadow"),
        ("object_braided_qpm_varactor_magnetic", "phase_mismatched_shadow"),
        ("object_braided_qpm_varactor_magnetic", "generated_path_suppressed_shadow"),
        ("object_braided_qpm_varactor_magnetic", "target_velocity_detuned_shadow"),
    ]
    trials: List[WitnessTrial] = []
    for idx, (family, transform) in enumerate(plan, start=1):
        trial_id = f"w{idx:03d}"
        obj = base_object_case(trial_id, family, idx)
        name = clean_name(f"{family}__vs__{transform}")
        obj = clone_case(obj, paired_trial_name=name)
        ref = reference_from_object(obj, transform)
        trials.append(WitnessTrial(trial_id=trial_id, name=name, object_case=obj, reference_case=ref))
    return trials


def direct_reference_case() -> WitnessCase:
    base = lockin.make_case(
        "direct_50plus100_reference",
        "h024",
        extraction_topology="none",
        cleanup="none",
        notch50=False,
        notch100=False,
        cells=64,
        z0=75.0,
        length_m=0.50,
        output_load=150.0,
        source_only=False,
        direct_100_v=1.0,
        magnetic_strength=0.0,
        magnetic_count=0,
        family="direct_50plus100_reference",
        role="ceiling_reference",
        notes="Separated direct 50+100 MHz ceiling denominator only; excluded from promotion.",
    )
    return to_witness_case(
        base,
        case_id="direct_50plus100_reference",
        name="direct_50plus100_reference_ceiling",
        filename="direct_50plus100_reference_ceiling.cir",
        trial_id="ceiling",
        paired_trial_name="direct_50plus100_reference_ceiling",
        side="ceiling_reference",
        object_family="direct_50plus100_reference",
        reference_transform="direct_50plus100_reference",
        witness_role="ceiling_reference",
        source_only_drive=False,
        direct_100_drive_present=True,
        direct_generated_amplitude_v=1.0,
        direct_ceiling_denominator_only=True,
        qpm_pattern_mode="none",
    )


def build_all_cases() -> Tuple[List[WitnessTrial], List[WitnessCase]]:
    trials = build_trials()
    cases: List[WitnessCase] = []
    for trial in trials:
        cases.extend([trial.object_case, trial.reference_case])
    cases.append(direct_reference_case())
    return trials, cases


def export_netlists(out_dir: Path) -> Tuple[List[WitnessTrial], List[WitnessExport]]:
    ensure_dir(out_dir)
    trials, cases = build_all_cases()
    exports: List[WitnessExport] = []
    for case in cases:
        netlist_path = out_dir / case.filename
        csv_path = out_dir / f"{Path(case.filename).stem}_tran.csv"
        netlist_path.write_text(instrument_netlist(case, csv_path), encoding="utf-8")
        exports.append(WitnessExport(case=case, netlist_path=netlist_path, csv_path=csv_path))
    return trials, exports


def run_ngspice(export: WitnessExport, ngspice_path: str, timeout_s: int) -> design.RunResult:
    shim = type("ExportShim", (), {"netlist_path": export.netlist_path, "csv_path": export.csv_path})()
    result = design.spice_base.run_ngspice(shim, ngspice_path, timeout_s)
    return design.RunResult(result.execution_status, result.success, result.reason, result.log_path)


def try_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def read_transient(path: Path) -> Dict[str, np.ndarray]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"empty transient CSV {path}")
    first = lines[0].replace(",", " ").split()
    has_header = any(try_float(tok) is None for tok in first)
    data_lines = lines[1:] if has_header else lines
    rows: List[List[float]] = []
    for line in data_lines:
        values = [try_float(tok) for tok in line.replace(",", " ").split()]
        numeric = [float(v) for v in values if v is not None]
        if numeric:
            rows.append(numeric)
    if not rows:
        raise ValueError(f"no numeric rows in {path}")
    width = min(len(row) for row in rows)
    arr = np.asarray([row[:width] for row in rows], dtype=float)
    offset = 1
    if has_header:
        offset = 2 if len(first) > 1 and first[1].lower() == "time" else 1
    elif width >= 14 and np.allclose(arr[:, 0], arr[:, 1]):
        offset = 2
    expected_vectors = len(TAP_FRACTIONS) + 3
    if width < offset + expected_vectors:
        raise ValueError(f"expected time plus {expected_vectors} vectors in {path}, got {width} columns")
    data: Dict[str, np.ndarray] = {"time": arr[:, 0]}
    for idx, (label, _) in enumerate(TAP_FRACTIONS):
        data[label] = arr[:, offset + idx]
    post_idx = offset + len(TAP_FRACTIONS)
    data["v_post"] = arr[:, post_idx]
    data["i_src"] = arr[:, post_idx + 1]
    data["i_bias"] = arr[:, post_idx + 2]
    return data


def uniform_resample(data: Dict[str, np.ndarray], max_points: int = 12000) -> Dict[str, np.ndarray]:
    keys = [label for label, _ in TAP_FRACTIONS] + ["v_post", "i_src", "i_bias"]
    t = np.asarray(data["time"], dtype=float)
    finite = np.isfinite(t)
    for key in keys:
        finite &= np.isfinite(np.asarray(data[key], dtype=float))
    order = np.argsort(t[finite])
    t_sorted = t[finite][order]
    keep = np.concatenate(([True], np.diff(t_sorted) > 0.0))
    t_sorted = t_sorted[keep]
    if len(t_sorted) < 16:
        raise ValueError("not enough unique transient samples")
    n_points = min(max_points, len(t_sorted))
    target_t = np.linspace(float(t_sorted[0]), float(t_sorted[-1]), n_points)
    result: Dict[str, np.ndarray] = {"time": target_t}
    for key in keys:
        values = np.asarray(data[key], dtype=float)[finite][order][keep]
        result[key] = np.interp(target_t, t_sorted, values)
    return result


def complex_projection(signal: np.ndarray, t: np.ndarray, freq_hz: float) -> complex:
    return 2.0 * np.mean(signal * np.exp(-1j * 2.0 * math.pi * freq_hz * t))


def fft_peak(signal: np.ndarray, t: np.ndarray, lo_hz: float, hi_hz: float) -> Tuple[float, float]:
    dt = float(np.median(np.diff(t)))
    centered = signal - np.mean(signal)
    window = np.hanning(len(centered))
    spec = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), dt)
    power = np.abs(spec) ** 2
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    if not np.any(mask):
        return 0.0, 0.0
    idxs = np.nonzero(mask)[0]
    peak_idx = idxs[int(np.argmax(power[mask]))]
    return float(freqs[peak_idx]), float(power[peak_idx])


def band_power(signal: np.ndarray, t: np.ndarray, center_hz: float, half_width_hz: float) -> float:
    dt = float(np.median(np.diff(t)))
    centered = signal - np.mean(signal)
    spec = np.fft.rfft(centered * np.hanning(len(centered)))
    freqs = np.fft.rfftfreq(len(centered), dt)
    power = np.abs(spec) ** 2
    mask = (freqs >= center_hz - half_width_hz) & (freqs <= center_hz + half_width_hz)
    return float(np.sum(power[mask]))


def phase_lock(values: np.ndarray, weights: np.ndarray | None = None) -> float:
    if len(values) == 0:
        return 0.0
    phasors = np.exp(1j * values)
    if weights is None:
        return float(abs(np.mean(phasors)))
    w = np.asarray(weights, dtype=float)
    if np.sum(w) <= EPS:
        return float(abs(np.mean(phasors)))
    return float(abs(np.sum(w * phasors) / np.sum(w)))


def envelope_cv(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    return float(np.std(values) / max(np.mean(values), EPS)) if len(values) else 0.0


def band_metrics(signal: np.ndarray, t: np.ndarray, source_signal: np.ndarray) -> Dict[str, float]:
    source_peak, source_power = fft_peak(signal, t, SOURCE_HZ * 0.85, SOURCE_HZ * 1.15)
    gen_peak, gen_power = fft_peak(signal, t, GENERATED_HZ * 0.85, GENERATED_HZ * 1.15)
    target_peak, target_power = fft_peak(signal, t, TARGET_HZ * 0.85, TARGET_HZ * 1.15)
    target_band = band_power(signal, t, TARGET_HZ, 8.0e6)
    broad_power = band_power(signal, t, 100.0e6, 90.0e6)
    z50 = complex_projection(source_signal, t, SOURCE_HZ)
    z100 = complex_projection(signal, t, GENERATED_HZ)
    z150 = complex_projection(signal, t, TARGET_HZ)
    return {
        "source_fft_peak_hz": source_peak,
        "generated_fft_peak_hz": gen_peak,
        "target_fft_peak_hz": target_peak,
        "source_fft_power": source_power,
        "generated_fft_power": gen_power,
        "target_fft_power": target_power,
        "spectral_purity_150mhz": target_band / max(broad_power, EPS),
        "target_coherent_power": float(abs(z150) ** 2),
        "phase_50_rad": float(np.angle(z50)),
        "phase_100_rad": float(np.angle(z100)),
        "phase_150_rad": float(np.angle(z150)),
        "amp_50": float(abs(z50)),
        "amp_100": float(abs(z100)),
        "amp_150": float(abs(z150)),
    }


def node_metrics(case: WitnessCase, data: Dict[str, np.ndarray]) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    d = uniform_resample(data)
    t = d["time"]
    start = int(0.25 * len(t))
    t2 = t[start:]
    source_signal = d["input"][start:]

    rows: List[Dict[str, object]] = []
    amps_50: List[float] = []
    amps_100: List[float] = []
    amps_150: List[float] = []
    phi_50: List[float] = []
    phi_100: List[float] = []
    phi_150: List[float] = []
    powers_150: List[float] = []

    for label, frac in TAP_FRACTIONS:
        signal = d[label][start:]
        z50 = complex_projection(signal, t2, SOURCE_HZ)
        z100 = complex_projection(signal, t2, GENERATED_HZ)
        z150 = complex_projection(signal, t2, TARGET_HZ)
        p50 = band_power(signal, t2, SOURCE_HZ, 6.0e6)
        p100 = band_power(signal, t2, GENERATED_HZ, 8.0e6)
        p150 = band_power(signal, t2, TARGET_HZ, 8.0e6)
        broad = band_power(signal, t2, 100.0e6, 90.0e6)
        row = {
            "row_type": "spice_412_differential_witness_node_metric",
            "case_id": case.case_id,
            "trial_id": case.trial_id,
            "paired_trial_name": case.paired_trial_name,
            "side": case.side,
            "object_family": case.object_family,
            "reference_transform": case.reference_transform,
            "tap_label": label,
            "tap_fraction": frac,
            "amp_50mhz": float(abs(z50)),
            "amp_100mhz": float(abs(z100)),
            "amp_150mhz": float(abs(z150)),
            "phase_50mhz_rad": float(np.angle(z50)),
            "phase_100mhz_rad": float(np.angle(z100)),
            "phase_150mhz_rad": float(np.angle(z150)),
            "fft_power_50mhz": p50,
            "fft_power_100mhz": p100,
            "fft_power_150mhz": p150,
            "purity_150mhz_local": p150 / max(broad, EPS),
        }
        rows.append(row)
        amps_50.append(float(abs(z50)))
        amps_100.append(float(abs(z100)))
        amps_150.append(float(abs(z150)))
        phi_50.append(float(np.angle(z50)))
        phi_100.append(float(np.angle(z100)))
        phi_150.append(float(np.angle(z150)))
        powers_150.append(p150)

    amp50 = np.asarray(amps_50, dtype=float)
    amp100 = np.asarray(amps_100, dtype=float)
    amp150 = np.asarray(amps_150, dtype=float)
    p150_arr = np.asarray(powers_150, dtype=float)
    ph50 = np.unwrap(np.asarray(phi_50, dtype=float))
    ph100 = np.unwrap(np.asarray(phi_100, dtype=float))
    ph150 = np.unwrap(np.asarray(phi_150, dtype=float))
    positions = np.asarray([frac for _, frac in TAP_FRACTIONS], dtype=float)
    non_input = slice(1, None)
    first_idx = 1 if len(amp150) > 1 else 0
    generated_error = ph100 - 2.0 * ph50
    target_error = ph150 - ph100 - ph50
    target_3f_error = ph150 - 3.0 * ph50
    slope = float(np.polyfit(positions, np.log(amp150 + EPS), 1)[0]) if len(positions) > 1 else 0.0
    generated_slope = float(np.polyfit(positions, np.log(amp100 + EPS), 1)[0]) if len(positions) > 1 else 0.0
    phase_jumps = np.abs(np.diff(np.unwrap(target_error)))
    raw_signal = d["raw_output"][start:]
    post_signal = d["v_post"][start:]
    raw = band_metrics(raw_signal, t2, source_signal)
    post = band_metrics(post_signal, t2, source_signal)
    growth100 = float(amp100[-1] / max(amp100[first_idx], EPS))
    growth150 = float(amp150[-1] / max(amp150[first_idx], EPS))
    lock_2f = phase_lock(generated_error[non_input], amp100[non_input] + EPS)
    lock_target = phase_lock(target_error[non_input], amp150[non_input] + EPS)
    lock_3f = phase_lock(target_3f_error[non_input], amp150[non_input] + EPS)

    pre_target_power = safe_float(raw.get("target_fft_power"))
    post_target_power = safe_float(post.get("target_fft_power"))
    pre_source_power = safe_float(raw.get("source_fft_power"))
    post_source_power = safe_float(post.get("source_fft_power"))
    pre_generated_power = safe_float(raw.get("generated_fft_power"))
    post_generated_power = safe_float(post.get("generated_fft_power"))
    gain150 = post_target_power / max(pre_target_power, EPS)
    gain50 = post_source_power / max(pre_source_power, EPS)
    gain100 = post_generated_power / max(pre_generated_power, EPS)
    selectivity = gain150 / max(0.5 * (gain50 + gain100), EPS)
    extraction_dependency = min(1.0, max(0.0, math.log10(max(gain150, 1.0))) / 1.5 + max(0.0, math.log10(max(selectivity, 1.0))) / 1.5)
    peak_voltage = float(max(np.max(np.abs(d[label])) for label, _ in TAP_FRACTIONS))
    peak_bias_current = float(np.max(np.abs(d["i_bias"])))
    peak_source_current = float(np.max(np.abs(d["i_src"])))
    peak_varactor_current = peak_bias_current / max(case.cell_count + 1, 1)
    reverse_bias_margin = case.bias_v - peak_voltage
    stress_score = float(
        max(
            peak_voltage / max(case.bias_v * 0.85, EPS),
            peak_varactor_current / 0.020,
            (case.bias_v + peak_voltage) / max(case.varactor_bv_v, EPS),
        )
    )
    if stress_score < 0.75 and reverse_bias_margin > 0.25:
        stress_class = "plausible"
    elif stress_score < 1.35 and reverse_bias_margin > -0.5:
        stress_class = "aggressive-but-testable"
    else:
        stress_class = "unrealistic"

    summary = {
        "pre_extraction_150mhz_purity": raw["spectral_purity_150mhz"],
        "target_fft_power_pre": pre_target_power,
        "target_coherent_power_pre": raw["target_coherent_power"],
        "post_extraction_150mhz_purity": post["spectral_purity_150mhz"],
        "target_fft_power_post": post_target_power,
        "internal_100mhz_growth": growth100,
        "internal_150mhz_growth": growth150,
        "distributed_100mhz_growth_slope": generated_slope,
        "distributed_150mhz_growth_slope": slope,
        "distributed_150mhz_coherent_growth": growth150 * lock_3f,
        "distributed_150mhz_phase_lock_to_3f": lock_3f,
        "distributed_100mhz_phase_lock_to_2f": lock_2f,
        "phase_lock_generated_pre": lock_2f,
        "phase_lock_target_pre": lock_target,
        "generated_envelope_cv_pre": envelope_cv(amp100[non_input]),
        "target_envelope_cv_pre": envelope_cv(amp150[non_input]),
        "max_phase_jump_pre": float(np.max(phase_jumps)) if len(phase_jumps) else 0.0,
        "post_pre_extraction_dependency": gain150,
        "extraction_dependency_score": extraction_dependency,
        "filter_selectivity_score": max(0.0, selectivity - 1.0),
        "source_fft_power_pre": pre_source_power,
        "generated_fft_power_pre": pre_generated_power,
        "tap_150mhz_power_json": json.dumps({r["tap_label"]: r["fft_power_150mhz"] for r in rows}, sort_keys=True),
        "tap_100mhz_power_json": json.dumps({r["tap_label"]: r["fft_power_100mhz"] for r in rows}, sort_keys=True),
        "tap_150mhz_amp_json": json.dumps({r["tap_label"]: r["amp_150mhz"] for r in rows}, sort_keys=True),
        "tap_100mhz_amp_json": json.dumps({r["tap_label"]: r["amp_100mhz"] for r in rows}, sort_keys=True),
        "tap_target_phase_error_json": json.dumps(
            {label: float(value) for (label, _), value in zip(TAP_FRACTIONS, target_error)},
            sort_keys=True,
        ),
        "peak_voltage_v": peak_voltage,
        "source_peak_current_a": peak_source_current,
        "bias_peak_current_a": peak_bias_current,
        "varactor_peak_current_a": peak_varactor_current,
        "reverse_bias_margin_v": reverse_bias_margin,
        "component_stress_score": stress_score,
        "component_stress_class": stress_class,
        "behavioral_dependency_score": lockin.behavioral_dependency(case),
    }
    return rows, summary


def contamination_flags(case: WitnessCase) -> List[str]:
    flags: List[str] = []
    if case.direct_100_drive_present or case.direct_generated_amplitude_v > 0.0:
        flags.append("direct_100mhz_drive_present")
    if case.direct_150_drive_present:
        flags.append("direct_150mhz_drive_present")
    if case.target_frequency_injection_present:
        flags.append("target_frequency_injection_present")
    if case.behavioral_helper and case.side not in {"object", "reference"}:
        flags.append("behavioral_helper")
    return flags


def summarize_case(
    export: WitnessExport,
    run_requested: bool,
    ngspice_available: bool,
    ngspice_path: str | None,
    result: design.RunResult,
    metrics: Dict[str, object] | None,
) -> Dict[str, object]:
    case = export.case
    row: Dict[str, object] = {
        "row_type": "spice_412_differential_witness_case",
        "case_id": case.case_id,
        "trial_id": case.trial_id,
        "paired_trial_name": case.paired_trial_name,
        "side": case.side,
        "object_family": case.object_family,
        "reference_transform": case.reference_transform,
        "family": case.family,
        "role": case.role,
        "witness_role": case.witness_role,
        "netlist_file": export.netlist_path.name,
        "csv_file": export.csv_path.name if result.success else "",
        "execution_status": result.execution_status,
        "convergence_failure_reason": "" if result.success else result.reason,
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "ngspice_path": ngspice_path or "",
        "source_only_drive": str(case.source_only_drive),
        "direct_100mhz_drive_present": str(case.direct_100_drive_present),
        "direct_150mhz_drive_present": str(case.direct_150_drive_present),
        "target_frequency_injection_present": str(case.target_frequency_injection_present),
        "hidden_behavioral_target_source_present": "False",
        "direct_drive_contamination_flags": ",".join(contamination_flags(case)),
        "cell_count": case.cell_count,
        "z0_target_ohm": case.z0_ohm,
        "total_length_m": case.total_length_m,
        "source_frequency_hz": SOURCE_HZ,
        "generated_frequency_hz": GENERATED_HZ,
        "target_frequency_hz": TARGET_HZ,
        "source_amplitude_v": case.source_amplitude_v,
        "direct_generated_amplitude_v": case.direct_generated_amplitude_v,
        "bias_v": case.bias_v,
        "nonlinear_fraction": case.nonlinear_fraction,
        "magnetic_strength": case.magnetic_strength,
        "qpm_pattern_mode": case.qpm_pattern_mode,
        "varactor_polarity_mode": case.varactor_polarity_mode,
        "cleanup_topology": case.cleanup_topology,
        "extraction_topology": case.extraction_topology,
        "notes": case.notes,
    }
    if metrics:
        row.update(metrics)
        if case.side == "reference" and case.reference_transform != "direct_50plus100_reference":
            leakage = min(
                1.0,
                safe_float(metrics.get("pre_extraction_150mhz_purity"))
                + max(safe_float(metrics.get("internal_150mhz_growth")) - 1.0, 0.0) / 4.0,
            )
            row["control_leakage_score"] = leakage
        else:
            row["control_leakage_score"] = 0.0
    elif result.execution_status in {"failed_to_converge", "parser_failed"}:
        row["promotion_category"] = "reject_due_to_convergence_or_parser_failure"
    return row


def successful(row: Dict[str, object]) -> bool:
    return row.get("execution_status") == "ran_successfully"


def pair_row(trial: WitnessTrial, case_rows: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    obj = case_rows.get(trial.object_case.case_id, {})
    ref = case_rows.get(trial.reference_case.case_id, {})
    obj_success = successful(obj)
    ref_success = successful(ref)
    obj_power = safe_float(obj.get("target_fft_power_pre"))
    ref_power = safe_float(ref.get("target_fft_power_pre"))
    obj_coherent = safe_float(obj.get("target_coherent_power_pre"))
    ref_coherent = safe_float(ref.get("target_coherent_power_pre"))
    gain = obj_power / max(ref_power, EPS)
    differential_coherent_power = obj_coherent - ref_coherent
    leakage = min(1.0, ref_power / max(obj_power, EPS))
    kill_score = max(0.0, 1.0 - ref_power / max(obj_power, EPS))
    transform = trial.reference_case.reference_transform
    generated_dependency = kill_score if transform == "generated_path_suppressed_shadow" else 0.0
    phase_mismatch_kill = kill_score if transform == "phase_mismatched_shadow" else 0.0
    target_velocity_dependency = kill_score if transform == "target_velocity_detuned_shadow" else 0.0
    direct_flags = ",".join(flag for flag in [obj.get("direct_drive_contamination_flags", ""), ref.get("direct_drive_contamination_flags", "")] if flag)
    stress_ok = str(obj.get("component_stress_class")) in {"plausible", "aggressive-but-testable"}
    source_clean = (
        obj.get("source_only_drive") == "True"
        and obj.get("direct_100mhz_drive_present") == "False"
        and obj.get("direct_150mhz_drive_present") == "False"
        and obj.get("target_frequency_injection_present") == "False"
        and not direct_flags
    )

    full_gate = (
        obj_success
        and ref_success
        and source_clean
        and gain >= 10.0
        and safe_float(obj.get("distributed_150mhz_phase_lock_to_3f")) >= 0.90
        and safe_float(obj.get("phase_lock_target_pre")) >= 0.90
        and safe_float(obj.get("phase_lock_generated_pre")) >= 0.80
        and safe_float(obj.get("distributed_150mhz_coherent_growth")) >= 2.0
        and safe_float(obj.get("distributed_150mhz_growth_slope")) > 0.0
        and safe_float(obj.get("generated_envelope_cv_pre"), 99.0) <= 0.25
        and safe_float(obj.get("target_envelope_cv_pre"), 99.0) <= 0.25
        and safe_float(obj.get("max_phase_jump_pre"), 99.0) <= 0.50
        and safe_float(obj.get("post_pre_extraction_dependency"), 99.0) <= 3.0
        and safe_float(obj.get("extraction_dependency_score"), 99.0) <= 0.25
        and stress_ok
        and safe_float(obj.get("behavioral_dependency_score"), 99.0) <= 0.25
        and leakage < 0.15
    )
    near_gate = (
        obj_success
        and ref_success
        and source_clean
        and gain >= 3.0
        and safe_float(obj.get("distributed_150mhz_phase_lock_to_3f")) >= 0.85
        and safe_float(obj.get("phase_lock_target_pre")) >= 0.85
        and safe_float(obj.get("phase_lock_generated_pre")) >= 0.75
        and safe_float(obj.get("distributed_150mhz_coherent_growth")) >= 1.5
        and safe_float(obj.get("distributed_150mhz_growth_slope")) > 0.0
        and leakage < 0.15
        and safe_float(obj.get("extraction_dependency_score"), 99.0) <= 0.35
        and stress_ok
    )
    if full_gate:
        category = "electromagnetic_differential_witness_candidate"
    elif near_gate:
        category = "electromagnetic_differential_witness_near_miss"
    elif not (obj_success and ref_success):
        category = "reject_due_to_failed_paired_trial"
    elif not source_clean:
        category = "reject_due_to_direct_drive_contamination"
    elif gain < 3.0:
        category = "reject_due_to_weak_object_reference_pre_gain"
    elif leakage >= 0.15:
        category = "reject_due_to_shadow_control_leakage"
    else:
        category = "not_promoted"

    return {
        "row_type": "spice_412_differential_witness_pair",
        "case_id": trial.trial_id,
        "trial_id": trial.trial_id,
        "paired_trial_name": trial.name,
        "object_case_id": trial.object_case.case_id,
        "reference_case_id": trial.reference_case.case_id,
        "object_family": trial.object_case.object_family,
        "reference_transform": transform,
        "object_execution_status": obj.get("execution_status", ""),
        "reference_execution_status": ref.get("execution_status", ""),
        "source_only_drive": str(source_clean),
        "direct_100mhz_drive_present": str("direct_100mhz_drive_present" in direct_flags),
        "direct_150mhz_drive_present": str("direct_150mhz_drive_present" in direct_flags),
        "target_frequency_injection_present": str("target_frequency_injection_present" in direct_flags),
        "hidden_behavioral_target_source_present": "False",
        "direct_drive_contamination_flags": direct_flags,
        "pre_extraction_150mhz_purity_object": obj.get("pre_extraction_150mhz_purity", ""),
        "pre_extraction_150mhz_purity_reference": ref.get("pre_extraction_150mhz_purity", ""),
        "pre_extraction_object_reference_gain_150mhz": gain,
        "target_fft_power_pre_object": obj_power,
        "target_fft_power_pre_reference": ref_power,
        "internal_100mhz_growth_object": obj.get("internal_100mhz_growth", ""),
        "internal_150mhz_growth_object": obj.get("internal_150mhz_growth", ""),
        "distributed_150mhz_growth_slope": obj.get("distributed_150mhz_growth_slope", ""),
        "distributed_150mhz_coherent_growth": obj.get("distributed_150mhz_coherent_growth", ""),
        "distributed_150mhz_phase_lock_to_3f": obj.get("distributed_150mhz_phase_lock_to_3f", ""),
        "distributed_100mhz_phase_lock_to_2f": obj.get("distributed_100mhz_phase_lock_to_2f", ""),
        "phase_lock_generated_pre": obj.get("phase_lock_generated_pre", ""),
        "phase_lock_target_pre": obj.get("phase_lock_target_pre", ""),
        "generated_envelope_cv_pre": obj.get("generated_envelope_cv_pre", ""),
        "target_envelope_cv_pre": obj.get("target_envelope_cv_pre", ""),
        "max_phase_jump_pre": obj.get("max_phase_jump_pre", ""),
        "post_pre_extraction_dependency": obj.get("post_pre_extraction_dependency", ""),
        "extraction_dependency_score": obj.get("extraction_dependency_score", ""),
        "filter_selectivity_score": obj.get("filter_selectivity_score", ""),
        "control_leakage_score": ref.get("control_leakage_score", ""),
        "generated_path_dependency_score": generated_dependency,
        "phase_mismatch_kill_score": phase_mismatch_kill,
        "target_velocity_dependency_score": target_velocity_dependency,
        "differential_150mhz_coherent_power": differential_coherent_power,
        "differential_control_leakage_score": leakage,
        "component_stress_class": obj.get("component_stress_class", ""),
        "behavioral_dependency_score": obj.get("behavioral_dependency_score", ""),
        "promotion_category": category,
    }


def apply_pair_aggregate_scores(pair_rows: List[Dict[str, object]]) -> Dict[str, float]:
    best_obj_power = max((safe_float(row.get("target_fft_power_pre_object")) for row in pair_rows), default=0.0)
    pure_var = max(
        (
            safe_float(row.get("target_fft_power_pre_reference"))
            for row in pair_rows
            if row.get("reference_transform") == "pure_varactor_shadow"
        ),
        default=0.0,
    )
    linear = max(
        (
            safe_float(row.get("target_fft_power_pre_reference"))
            for row in pair_rows
            if row.get("reference_transform") == "linear_no_nonlinearity_shadow"
        ),
        default=0.0,
    )
    generated_kill = max((safe_float(row.get("generated_path_dependency_score")) for row in pair_rows), default=0.0)
    phase_kill = max((safe_float(row.get("phase_mismatch_kill_score")) for row in pair_rows), default=0.0)
    target_kill = max((safe_float(row.get("target_velocity_dependency_score")) for row in pair_rows), default=0.0)
    ratios = {
        "hybrid_vs_pure_varactor_pre_filter_ratio": best_obj_power / max(pure_var, EPS),
        "hybrid_vs_linear_pre_filter_ratio": best_obj_power / max(linear, EPS),
        "generated_path_dependency_score": generated_kill,
        "phase_mismatch_kill_score": phase_kill,
        "target_velocity_dependency_score": target_kill,
    }
    for row in pair_rows:
        row.update(ratios)
    return ratios


def aggregate_summary(
    pair_rows: List[Dict[str, object]],
    case_rows: List[Dict[str, object]],
    run_requested: bool,
    ngspice_available: bool,
) -> Dict[str, object]:
    ratios = apply_pair_aggregate_scores(pair_rows)
    successful_pairs = [row for row in pair_rows if row.get("object_execution_status") == "ran_successfully" and row.get("reference_execution_status") == "ran_successfully"]
    promoted = [row for row in pair_rows if row.get("promotion_category") == "electromagnetic_differential_witness_candidate"]
    near = [row for row in pair_rows if row.get("promotion_category") == "electromagnetic_differential_witness_near_miss"]
    best_gain = max(pair_rows, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), default={})
    best_object = max(pair_rows, key=lambda row: safe_float(row.get("target_fft_power_pre_object")), default={})
    best_shadow = max(pair_rows, key=lambda row: safe_float(row.get("target_fft_power_pre_reference")), default={})
    by_family: Dict[str, List[Dict[str, object]]] = {}
    for row in successful_pairs:
        by_family.setdefault(str(row.get("object_family")), []).append(row)
    hardest_rows: List[Dict[str, object]] = []
    for family_rows in by_family.values():
        hardest_rows.append(min(family_rows, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz"))))
    best_hardest = max(hardest_rows, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), default={})
    max_leak = max((safe_float(row.get("differential_control_leakage_score")) for row in pair_rows), default=0.0)
    max_extraction_dependency = max((safe_float(row.get("extraction_dependency_score")) for row in pair_rows), default=0.0)
    coherent_growth_positive = any(safe_float(row.get("distributed_150mhz_growth_slope")) > 0.0 for row in successful_pairs)
    separated_hybrid_from_pure = ratios["hybrid_vs_pure_varactor_pre_filter_ratio"] >= 2.0
    extraction_artifact_likely = bool(
        not promoted
        or max_leak >= 0.15
        or max_extraction_dependency > 0.35
        or ratios["hybrid_vs_pure_varactor_pre_filter_ratio"] < 2.0
        or ratios["generated_path_dependency_score"] < 0.80
        or ratios["phase_mismatch_kill_score"] < 0.80
    )
    real_signal = bool(
        promoted
        and coherent_growth_positive
        and separated_hybrid_from_pure
        and not extraction_artifact_likely
    )
    if real_signal:
        recommendation = "repeat the paired witness at larger cell count and move toward independent pickup hardware"
    elif near:
        recommendation = "repeat only the near-miss pair with stricter shadows and independent broadband pickup"
    else:
        recommendation = "keep the electrical route blocked; test a different magnetic-line topology or prioritize the acoustic branch"
    statuses = ";".join(sorted(set(str(row.get("execution_status")) for row in case_rows)))
    return {
        "row_type": "aggregate",
        "case_id": "aggregate",
        "name": "spice_412_differential_witness_line_aggregate",
        "run_requested": str(run_requested),
        "ngspice_available": str(ngspice_available),
        "execution_statuses": statuses,
        "rows_total": len(case_rows),
        "paired_trials_total": len(pair_rows),
        "successful_pairs": len(successful_pairs),
        "promoted_count": len(promoted),
        "near_miss_count": len(near),
        "top_candidates": ";".join(str(row.get("paired_trial_name")) for row in promoted[:5]),
        "top_near_misses": ";".join(str(row.get("paired_trial_name")) for row in near[:5]),
        "best_object_case": best_object.get("object_case_id", ""),
        "best_object_family": best_object.get("object_family", ""),
        "best_shadow_reference_case": best_shadow.get("reference_case_id", ""),
        "best_shadow_reference_transform": best_shadow.get("reference_transform", ""),
        "best_pair_by_gain": best_gain.get("paired_trial_name", ""),
        "best_pair_gain": best_gain.get("pre_extraction_object_reference_gain_150mhz", ""),
        "best_hardest_shadow_family": best_hardest.get("object_family", ""),
        "best_hardest_shadow_pair": best_hardest.get("paired_trial_name", ""),
        "best_hardest_shadow_gain": best_hardest.get("pre_extraction_object_reference_gain_150mhz", ""),
        "object_reference_pre_gain": best_gain.get("pre_extraction_object_reference_gain_150mhz", ""),
        "line_itself_produced_coherent_150mhz_before_extraction": str(coherent_growth_positive),
        "differential_readout_separated_hybrid_from_pure_varactor": str(separated_hybrid_from_pure),
        "result_still_likely_filter_artifact": str(extraction_artifact_likely),
        "extraction_artifact_likely": str(extraction_artifact_likely),
        "electrical_bridge_real_signal": str(real_signal),
        "recommended_next_step": recommendation,
        "max_differential_control_leakage_score": max_leak,
        "max_extraction_dependency_score": max_extraction_dependency,
        **ratios,
    }


def timeseries_rows(export: WitnessExport, data: Dict[str, np.ndarray], stride: int = 24) -> List[Dict[str, object]]:
    d = uniform_resample(data, max_points=6000)
    rows: List[Dict[str, object]] = []
    for idx in range(0, len(d["time"]), stride):
        row: Dict[str, object] = {
            "row_type": "spice_412_differential_witness_tap_timeseries",
            "case_id": export.case.case_id,
            "trial_id": export.case.trial_id,
            "paired_trial_name": export.case.paired_trial_name,
            "side": export.case.side,
            "object_family": export.case.object_family,
            "reference_transform": export.case.reference_transform,
            "time_s": float(d["time"][idx]),
            "v_post_diagnostic": float(d["v_post"][idx]),
            "i_src": float(d["i_src"][idx]),
            "i_bias": float(d["i_bias"][idx]),
        }
        for label, _ in TAP_FRACTIONS:
            row[f"v_{label}"] = float(d[label][idx])
        rows.append(row)
    return rows


def write_report(out_dir: Path, pair_rows: List[Dict[str, object]], aggregate: Dict[str, object]) -> None:
    ranked = sorted(pair_rows, key=lambda row: safe_float(row.get("pre_extraction_object_reference_gain_150mhz")), reverse=True)
    shadows = sorted(pair_rows, key=lambda row: safe_float(row.get("target_fft_power_pre_reference")), reverse=True)
    lines = [
        "# SPICE 4->8->12 Differential Witness Line",
        "",
        "Paired OBJECT / REFERENCE nonlinear electrical-magnetic transmission-line test. Promotion is based on coherent 150 MHz growth inside raw/internal line nodes before extraction.",
        "",
        "## Direct Answers",
        "",
        f"- Top candidates: {aggregate.get('top_candidates') or 'none'}.",
        f"- Top matched shadow references: {', '.join(str(row.get('reference_case_id')) for row in shadows[:5])}.",
        f"- Best object case: {aggregate.get('best_object_case')} ({aggregate.get('best_object_family')}).",
        f"- Best shadow reference case: {aggregate.get('best_shadow_reference_case')} ({aggregate.get('best_shadow_reference_transform')}).",
        f"- object_reference_pre_gain: {aggregate.get('object_reference_pre_gain')}.",
        f"- promoted_count: {aggregate.get('promoted_count')}.",
        f"- near_miss_count: {aggregate.get('near_miss_count')}.",
        f"- Did the line itself produce coherent 150 MHz before extraction? {aggregate.get('line_itself_produced_coherent_150mhz_before_extraction')}.",
        f"- Did differential readout separate hybrid from pure-varactor? {aggregate.get('differential_readout_separated_hybrid_from_pure_varactor')}.",
        f"- Is the result still likely a filter artifact? {aggregate.get('result_still_likely_filter_artifact')}.",
        f"- extraction_artifact_likely: {aggregate.get('extraction_artifact_likely')}.",
        f"- electrical_bridge_real_signal: {aggregate.get('electrical_bridge_real_signal')}.",
        f"- recommended_next_step: {aggregate.get('recommended_next_step')}.",
        "",
        "## Aggregate",
        "",
        f"- Paired trials: total={aggregate.get('paired_trials_total')}, successful={aggregate.get('successful_pairs')}, statuses={aggregate.get('execution_statuses')}.",
        f"- Best hardest-shadow family: {aggregate.get('best_hardest_shadow_family')} via {aggregate.get('best_hardest_shadow_pair')} gain={aggregate.get('best_hardest_shadow_gain')}.",
        f"- Hybrid vs pure-varactor pre-filter ratio: {aggregate.get('hybrid_vs_pure_varactor_pre_filter_ratio')}.",
        f"- Hybrid vs linear pre-filter ratio: {aggregate.get('hybrid_vs_linear_pre_filter_ratio')}.",
        f"- Kill scores: generated_path={aggregate.get('generated_path_dependency_score')}, phase_mismatch={aggregate.get('phase_mismatch_kill_score')}, target_velocity={aggregate.get('target_velocity_dependency_score')}.",
        f"- Max differential control leakage: {aggregate.get('max_differential_control_leakage_score')}.",
        "",
        "## Top Paired Trials",
        "",
    ]
    for row in ranked[:12]:
        lines.append(
            "- {name}: category={cat}, gain={gain}, object_purity={op}, reference_purity={rp}, "
            "lock_target={lock}, coherent_growth={growth}, slope={slope}, leakage={leak}, stress={stress}.".format(
                name=row.get("paired_trial_name"),
                cat=row.get("promotion_category"),
                gain=row.get("pre_extraction_object_reference_gain_150mhz"),
                op=row.get("pre_extraction_150mhz_purity_object"),
                rp=row.get("pre_extraction_150mhz_purity_reference"),
                lock=row.get("phase_lock_target_pre"),
                growth=row.get("distributed_150mhz_coherent_growth"),
                slope=row.get("distributed_150mhz_growth_slope"),
                leak=row.get("differential_control_leakage_score"),
                stress=row.get("component_stress_class"),
            )
        )
    lines.extend(
        [
            "",
            "## Controls And Scoring Rules",
            "",
            "- Every paired object row is source-only at 50 MHz: no direct 100 MHz drive, no direct 150 MHz drive, and no target-frequency injection.",
            "- The direct 50+100 MHz row is exported and measured only as a separated ceiling denominator.",
            "- The summary ranks each object family against its hardest surviving matched shadow, not the easiest shadow.",
            "- Post-extraction/readout metrics are diagnostic liabilities only. Candidate gates use raw/internal pre-extraction metrics first.",
        ]
    )
    (out_dir / "README_SPICE_412_DIFFERENTIAL_WITNESS_LINE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Run paired differential witness-line SPICE experiment.")
    parser.add_argument("--out", default=str(OUT_DIR), help="Output directory.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after exporting netlists.")
    parser.add_argument("--ngspice-path", default="", help="Path to ngspice or wsl:ngspice.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per netlist in seconds.")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out))
    trials, exports = export_netlists(out_dir)
    ngspice_path = design.resolve_ngspice_path(args.ngspice_path or None)
    ngspice_available = ngspice_path is not None

    run_results: Dict[str, design.RunResult] = {}
    parsed: Dict[str, Dict[str, np.ndarray]] = {}
    if args.run and not ngspice_available:
        for export in exports:
            run_results[export.case.case_id] = design.RunResult("skipped_no_ngspice", False, "ngspice not found")
    elif args.run and ngspice_path:
        for export in exports:
            result = run_ngspice(export, ngspice_path, args.timeout)
            if result.success:
                try:
                    parsed[export.case.case_id] = read_transient(export.csv_path)
                except Exception as exc:
                    result = design.RunResult("parser_failed", False, f"{type(exc).__name__}: {exc}", result.log_path)
            run_results[export.case.case_id] = result
    else:
        for export in exports:
            run_results[export.case.case_id] = design.RunResult("exported", False, "export only; use --run")

    case_rows: List[Dict[str, object]] = []
    node_rows_all: List[Dict[str, object]] = []
    timeseries: List[Dict[str, object]] = []
    for export in exports:
        result = run_results[export.case.case_id]
        metrics: Dict[str, object] | None = None
        if result.success and export.case.case_id in parsed:
            node_rows, metrics = node_metrics(export.case, parsed[export.case.case_id])
            node_rows_all.extend(node_rows)
            timeseries.extend(timeseries_rows(export, parsed[export.case.case_id]))
        case_rows.append(summarize_case(export, args.run, ngspice_available, ngspice_path, result, metrics))

    case_by_id = {str(row.get("case_id")): row for row in case_rows}
    pair_rows = [pair_row(trial, case_by_id) for trial in trials]
    aggregate = aggregate_summary(pair_rows, case_rows, args.run, ngspice_available)
    all_summary_rows = [aggregate] + pair_rows + case_rows

    write_csv(out_dir / "spice_412_differential_witness_line_summary.csv", all_summary_rows)
    if node_rows_all:
        write_csv(out_dir / "spice_412_differential_witness_line_node_metrics.csv", node_rows_all)
    if timeseries:
        write_csv(out_dir / "spice_412_differential_witness_line_tap_timeseries.csv", timeseries)
    (out_dir / "spice_412_differential_witness_line_summary.json").write_text(
        json.dumps(
            sanitize(
                {
                    "aggregate": aggregate,
                    "pairs": pair_rows,
                    "cases": case_rows,
                    "node_metrics": node_rows_all,
                    "netlists": [
                        {
                            **asdict(export.case),
                            "netlist_path": str(export.netlist_path),
                            "csv_path": str(export.csv_path),
                        }
                        for export in exports
                    ],
                }
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_report(out_dir, pair_rows, aggregate)
    print(
        json.dumps(
            sanitize(
                {
                    "paired_trials_total": aggregate.get("paired_trials_total"),
                    "successful_pairs": aggregate.get("successful_pairs"),
                    "promoted_count": aggregate.get("promoted_count"),
                    "near_miss_count": aggregate.get("near_miss_count"),
                    "electrical_bridge_real_signal": aggregate.get("electrical_bridge_real_signal"),
                    "extraction_artifact_likely": aggregate.get("extraction_artifact_likely"),
                    "recommended_next_step": aggregate.get("recommended_next_step"),
                    "summary": str(out_dir / "spice_412_differential_witness_line_summary.json"),
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
