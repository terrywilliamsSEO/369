# Agent Guide

Read these files first:

1. `README.md` at repo root.
2. `docs/PROJECT_STATUS.md`.
3. `docs/EXPERIMENT_LOG.md`.
4. `tesla_369_lab/README.md`.
5. `tesla_369_lab/tesla_369_lab.py`.

## Operating Rules

- Treat this as a falsifiable physics/toy-model lab, not a numerology proof.
- Keep direct 6 and direct 9 drives out of generated bridge discovery cases.
- Treat direct resonance cases as references or ceilings, never discovery winners.
- Keep passive energy accounting strict.
- Always summarize results in chat; do not tell the user to read markdown as the primary answer.
- Keep generated run folders out of git unless a specific result set is curated and promoted.

## Current Promotion Gate

Do not promote a passive bridge to `geometry369` unless it passes:

- 1x runtime.
- 2x runtime.
- 4x runtime.
- Half-dt and quarter-dt.
- `phase_lock_9 > 0.90`.
- `spectral_purity_9 > 0.60`.
- Energy budget below the mode-specific gate.

The current best 3 -> 6 -> 9 candidates still fail 4x promotion. Stage A `+0.03` tuning can remove target slips, and forensics found budget-clean zero-slip compensation rows. The refined-dt basin check preserved budget cleanliness, but lock/jump/envelope gates still failed. The limiter/predictive-servo smoke improved 369 lock above 0.96 with passive adaptive damping, but generated-envelope CV stayed around 0.28 and max phase jumps stayed around 1.75 rad, so no 369 row promoted. The harmonic-family smoke found 5 -> 10 -> 15 strongest by normalized passive score and 4 -> 8 -> 12 closest to a candidate. Harmonic dt-rescue found a 4 -> 8 -> 12 target-detuned row whose strict non-budget metrics survive dt checks, but the baseline ledger was dirty. Budget-ledger classified that residual as numerical sensitivity, and substep-quadrature then showed the source is trajectory-integration error: substep-4 re-integration closes baseline/half/quarter/eighth dt while preserving lock, bridge, purity, envelope CV, and phase-jump gates. The 4 -> 8 -> 12 detuning-refine smoke now has strict substep-4 rows; the best uses target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.03`, and worst all-dt lock 0.992, bridge ratio 1.589, purity 0.923, budget 0.0000510, generated-envelope CV 0.135, max jump 0.972 rad, near slips 0. `independent_validate_412.py` independently reproduces that candidate outside the main harness with `independent_validation_passed=True` and no material metric differences. `physical_412_lc_bridge.py` expresses the same candidate as a three-resonator nonlinear LC model across audio, low-RF, and normalized scale presets with `all_dt_all_scales_passed=True`, worst lock 0.992108, bridge ratio 1.606971, purity 0.922789, budget 0.0000510, and source-only drive. `spice_412_export.py` exports and runs ngspice-compatible netlists for audio, low-RF, normalized, nonlinear realism variants, linear controls, and direct 4+8 reference cases. WSL ngspice is installed as `/usr/bin/ngspice` (`ngspice-42`); `python spice_412_export.py --run --ngspice-path wsl:ngspice` produced 15 successful rows and 4 `failed_to_converge` rows. The normalized behavioral proxy preserved lock 0.997003 and purity 0.971359, but its bridge ratio was only 0.788167 against the normalized direct 4+8 reference. `spice_412_refine_nonlinearity.py` then ran a focused normalized-scale sweep and found two source-only behavioral proxy rows above bridge ratio 1.5 with linear controls dead; closest was `r042` with lock 0.996193, purity 0.981658, bridge ratio 1.563169, target-band growth 1.276714, generated-envelope CV 0.091533, and max jump 0.289970. `spice_412_component_realism.py` forbids behavioral current mixing in discovery rows and found six source-only component-plausible rows above bridge ratio 1.5, but none phase-locked; closest was `c018` with lock 0.016446, purity 0.986424, bridge ratio 1.573878, and plausible stress. Weak-nonlinearity and detuned controls leaked target-band response, so component controls did not all stay dead. This is not a geometry/evolve promotion or hardware proof. Next work should deepen component sweeps around phase-lock and control cleanliness, then run physical parameter sweeps, add spatial phase-matching modeling, and continue broader family-law replication before any geometry/evolve or 369-specific PLL branch.
