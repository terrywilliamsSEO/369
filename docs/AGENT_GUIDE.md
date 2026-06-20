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

The current best 3 -> 6 -> 9 candidates still fail 4x promotion. Stage A `+0.03` tuning can remove target slips, and forensics found budget-clean zero-slip compensation rows. The refined-dt basin check preserved budget cleanliness, but lock/jump/envelope gates still fail: best quick 369 lock was 0.864, best generated-envelope CV was 0.528, and best max phase jump was 2.36 rad. Next work should focus on limiter redesign and predictive servo timing before full sweeps or geometry/evolve.
