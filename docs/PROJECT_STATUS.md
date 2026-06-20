# Project Status

Last updated: 2026-06-19

## Scientific Status

The project has moved from broad 3/6/9 tests into a specific mechanism:

```text
3-only drive -> generated 6 -> 3 + generated 6 -> 9 receiver
```

This is a clean passive nonlinear bridge test. It asks whether generated 6 can replace a direct 6 pump and hold a receiver near 9 in phase over time.

## Best Findings

- The generated bridge exists at 1x runtime.
- A receiver tuned slightly below nominal 9 can stabilize the 1x lock.
- Effective generated frequency near the receiver tends to sit around 9.05-9.09.
- Half-dt and quarter-dt validations pass for several candidates.
- Passive magnetic damping/saturation can improve 2x behavior.
- Open-loop magnetic autolock sweeps and hybrid tuning improve 1x capture in quick sweeps.

## Current Blocker

No passive model has passed the strict 4x runtime lock gate.

The main 4x failure is phase drift. Some candidates also accumulate unacceptable energy-budget error over long runtime.

## Latest Magnetic Autolock Summary

Mode added:

```bash
python tesla_369_lab.py --mode magnetic_autolock
python tesla_369_lab.py --mode magnetic_autolock --quick
python tesla_369_lab.py --mode magnetic_autolock --sweeps
```

What it tests:

- Open-loop receiver, magnetic bias, and Stage B inductance sweeps.
- Passive hybrid magnetic branch tuning near the effective generated 9.05-9.08 mode.
- Ultraweak counted injection near the generated mode as a semi-active comparator.
- Wrong-direction, random, wrong-frequency, random-phase, direct-reference, and non-369 controls.

Quick sweep result from `runs/magnetic_autolock_quick_sweeps_smoke`:

- Best 1x row: `sweep_receiver_capture_8p82_to_8p9_s0p9`.
- Metrics: bridge ratio 0.957, phase_lock_9 0.950, spectral purity 0.643, budget error 0.000227, active work fraction 0.00020.
- Best 4x validation rows still failed phase lock: the top 4x phase lock was about 0.747, below the 0.90 gate.
- Non-369 controls remain important because they can show strong generic harmonic behavior; they are reported separately and cannot win discovery ranking.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Run `bridge_min_nudge --sweeps` to test whether a tiny explicitly accounted proportional tuning correction can hold 4x lock.
2. Run deeper `magnetic_autolock --sweeps` focused on 4x phase drift.
3. Move to active self-lock / PLL and explicitly account for active work.
4. Add a geometry mode only after a 4x-stable seed exists.
