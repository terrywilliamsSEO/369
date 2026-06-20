# Project Status

Last updated: 2026-06-20

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
- Open-loop control-authority tests now quantify whether receiver tuning, magnetic bias, or Stage B detuning can pull 4x phase drift under clean accounting.
- Precomputed drift feedforward ramps do not currently hold 4x phase lock, even with tiny counted work.

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

## Latest Control Authority Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_control_authority
python tesla_369_lab.py --mode bridge_control_authority --quick
python tesla_369_lab.py --mode bridge_control_authority --sweeps
```

What it tests:

- Open-loop negative/positive/medium/large steps, slow ramps, and hold-after-ramp cases for receiver tuning, magnetic bias, and Stage B detuning.
- No direct 6 drive, no direct 9 drive, and no target-frequency injection in discovery rows.
- Effective generated-frequency pull, phase-drift pull, required correction to cancel drift, estimated correction work, and authority margin.
- No-correction, wrong-sign, random, and non-369 staged bridge controls.

Quick smoke result from `runs/bridge_control_authority_quick_smoke`:

- Best raw 4x drift reducer: `stage_B_detuning_nudge` large step, about 5.7% drift reduction.
- Best small-signal authority margin: `receiver_tuning_nudge` negative small step, but measured drift reduction was only about 1.4%.
- No discovery row passed the 50% drift-reduction promotion gate.
- Current read: the actuators show measurable pull, but the tested open-loop nudges are not enough to prove 4x lock.

## Latest Drift Feedforward Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_drift_feedforward
python tesla_369_lab.py --mode bridge_drift_feedforward --quick
python tesla_369_lab.py --mode bridge_drift_feedforward --sweeps
```

What it tests:

- A no-feedforward baseline, then a precomputed ramp from the measured signed phase drift and previous actuator authority.
- Receiver tuning, Stage B detuning, and magnetic bias ramps only.
- Linear, piecewise-linear, S-curve, hold-after-capture, and two-stage ramps.
- No PLL, no live feedback, no direct 6 drive, no direct 9 drive, and no target-frequency injection.
- Wrong-sign, random, overcorrected, and non-369 staged bridge controls.

Quick smoke result from `runs/bridge_drift_feedforward_quick_smoke`:

- Best row: `magnetic_bias_ramp` with `hold_after_capture_ramp`.
- Metrics: phase_lock_9 0.780, bridge ratio 2.717, spectral purity 0.774, budget error 0.00328, feedforward work fraction 0.0000083.
- Drift reduction was only about 0.14%, so the ramp did not cancel the long-runtime phase drift.
- No discovery row passed the 4x phase-lock gate.
- A non-369 control reached phase_lock_9 0.996 under the same feedforward rules.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Run `bridge_drift_feedforward --sweeps` only if we need a broader fixed-ramp confirmation across timing, ramp size, and runtime.
2. Move to stronger proportional control using the measured actuator gains.
3. Move to active self-lock / PLL and explicitly account for active work if proportional control still cannot hold 4x.
4. Add a geometry mode only after a 4x-stable seed exists.
