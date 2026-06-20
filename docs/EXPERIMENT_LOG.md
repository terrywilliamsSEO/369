# Experiment Log

## Early Baselines

- `triad`: tested nonlinear triads such as 3-6-9 and controls like 3-5-7, detuned 3-6.25-9, and 4-8-12.
- `wave`: tested 2D nonlinear wave localization.
- Initial read: 369-like wave phase patterns looked interesting, but harmonic controls could also be strong.

## Silent 9

Goal:

```text
drive 3 + 6 only -> receiver tuned to 9
```

This removed direct 9 contamination and tested nonlinear sum-frequency conversion.

## Atlas

Mapped many integer pump pairs into targets 6, 9, 12, 15, 18, and 24.

Main lesson:

- 3+6->9 is a useful case, but the broader mechanism is nonlinear sum-frequency conversion.

## Cascade

Tested:

```text
3+3 -> 6
3+generated 6 -> 9
6+generated 9 -> 15
9+generated 15 -> 24
```

Main lesson:

- Early cascade stages can appear.
- Higher stages are weak and should not be promoted without stricter validation.

## Energy Audit And Clean Validation

Added passive nonlinear potential accounting and stricter energy-budget gates.

Main lesson:

- Clean passive accounting matters.
- Some apparent effects weaken when hidden active/nonconservative terms are removed.

## Bridge Amplification

Built staged clean passive bridge:

```text
Stage A: 3 -> generated 6
Stage B: 3 + generated 6 -> 9
Stage C: receiver tuned near 9
```

Main lesson:

- Generated 6 can partially replace direct 6 at 1x runtime.
- Phase lock becomes the limiting factor.

## Bridge Phase Lock

Diagnosed long-runtime drift.

Key result:

- Receiver detuning around 8.9 stabilizes 1x behavior.
- Effective target frequency lands above nominal, around 9.05-9.09.

## Bridge Lock Refine

Fine-mapped the passive lock island.

Key result:

- The island is real at 1x and survives dt refinement.
- It fails strict 2x/4x full-resolution validation.

## Magnetic Bridge

Added passive magnetic-flux coupling diagnostics and controls.

Key result:

- Passive magnetic variants can improve 2x stability.
- No tested passive magnetic candidate survives 4x phase-lock gates.
- Best next passive leads are lossy/hysteretic and saturable magnetic variants.

## Magnetic Autolock

Added open-loop and semi-passive phase-capture mechanisms before moving to full PLL:

- autoresonant receiver/bias/Stage B sweeps,
- passive hybrid magnetic mode tuning,
- ultraweak counted injection locking,
- wrong-direction/random/wrong-frequency controls,
- non-369 staged bridge controls,
- 1x/2x/4x, half-dt, and quarter-dt validation hooks.

Quick sweep smoke result:

- Best 1x row was `sweep_receiver_capture_8p82_to_8p9_s0p9`.
- It reached bridge ratio 0.957, phase_lock_9 0.950, spectral purity 0.643, and budget error 0.000227.
- The best 4x validation rows still failed by phase drift; top 4x phase lock was about 0.747.
- Autolock is useful for finding capture islands, but it has not yet promoted a 4x-stable candidate.
