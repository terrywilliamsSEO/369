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
- PI phase servo improves the 3 -> 6 -> 9 phase lock modestly, but non-369 controls still look stronger on phase lock.
- Emergent-lock diagnostics find a small pulled local 3 -> 6 -> 9 target near 9.02, but not a stable >0.90 emergent phase lock.
- Phase-slip audit points to discrete phase slips driven by generated-6 envelope instability, not a clean stable pulled-frequency lock.
- Generated-stage stabilization confirms the lead: raw tuning can remove slips, but the current slip-free row breaks energy budget.
- Stage A budget audit isolates that failure: static `+0.03` tuning removes slips, but the final tuned configuration still breaks budget even with no servo and no dynamic parameter work.
- Stage A budget forensics suggests that budget failure is dt-sensitive driven-model accounting, not no-drive nonconservation: half-dt and quarter-dt clean the full-model rows.

## Current Blocker

No passive model has passed the strict 4x runtime lock gate.

The main 4x failure is now split between generated-stage lock quality and driven-model budget accounting. The narrow forensics search found budget-clean zero-slip rows, but they still miss lock/jump/envelope gates.

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

## Latest Phase Servo Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_phase_servo
python tesla_369_lab.py --mode bridge_phase_servo --quick
python tesla_369_lab.py --mode bridge_phase_servo --sweeps
```

What it tests:

- Proportional plus small integral feedback using only receiver tuning, Stage B detuning, and magnetic bias servos.
- No direct 6 drive, no direct 9 drive, and no injected 9-frequency reference.
- 3 -> 6 -> 9, 4 -> 8 -> 12, and 5 -> 10 -> 15 under the same servo rules.
- No-servo, wrong-sign, and random-servo controls.
- Half-dt and quarter-dt validation for top rows.

Quick smoke result from `runs/bridge_phase_servo_quick_smoke`:

- Best 3 -> 6 -> 9 row: `receiver_tuning_servo`, Kp 0.003, Ki 0.000045.
- Metrics: phase_lock_target 0.808, bridge ratio 2.722, spectral purity 0.773, budget error 0.00404, servo work fraction 0.000492.
- The servo improved phase lock by about 0.031 over the 369 no-servo baseline, but still missed the 0.90 gate.
- No discovery row passed the 4x gate.
- Non-369 controls reached phase_lock_target 0.994-0.996, but failed full promotion by energy-budget error.

## Latest Emergent Lock Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_emergent_lock
python tesla_369_lab.py --mode bridge_emergent_lock --quick
python tesla_369_lab.py --mode bridge_emergent_lock --sweeps
```

What it tests:

- Whether the 4x nominal phase-lock failure is actually lock to a stable pulled target frequency near the nominal target.
- 3 -> 6 -> 9, 4 -> 8 -> 12, 5 -> 10 -> 15, and 6 -> 12 -> 18 families under no-servo and the physical tuning/bias servo actuators.
- Nominal phase lock, fitted effective target frequency, emergent phase lock at that fitted frequency, detuning drift, dt/seed reproducibility, strict energy budget, and servo work.
- Direct 2f/3f drive and target-frequency injection are explicitly reported as forbidden contamination flags.

Quick smoke result from `runs/bridge_emergent_lock_quick_smoke`:

- Best 3 -> 6 -> 9 row: `stage_B_detuning_servo` on `feedforward_best_magnetic_bias`, Kp 0.0015, Ki 0.000020.
- Metrics: nominal phase lock 0.715, emergent phase lock 0.733, fitted target 9.0226, bridge ratio 3.365, spectral purity 0.929, budget error 0.00106, servo work fraction 0.000198.
- Repeat-seed, half-dt, and quarter-dt checks preserved the fitted detuning near +0.0225, but phase lock stayed below the 0.90 promotion gate.
- No `harmonic_bridge_candidate`, `pulled_frequency_discovery`, or `369_unique_candidate` label passed.
- Non-369 controls reached emergent phase lock around 0.982-0.998, but failed promotion by energy-budget error.
- Current read: the failure is still mostly nominal-target drift or broad harmonic behavior, not a stable pulled-frequency lock.

## Latest Phase Slip Audit Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_phase_slip_audit
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick
python tesla_369_lab.py --mode bridge_phase_slip_audit --sweeps
```

What it tests:

- Whether the 3 -> 6 -> 9 lock failure is smooth drift or discrete phase slips.
- 3 -> 6 -> 9, 4 -> 8 -> 12, and 5 -> 10 -> 15 under no-servo, receiver-tuning servo, Stage B detuning servo, and magnetic-bias servo rows.
- Sliding-window generated-2f phase error, target-3f phase error, unwrapped phase, instantaneous drift, fitted target, amplitude envelopes, spectral purity, bridge ratio, correction lag, damping loss, spark loss, and budget error.
- Event metrics: phase-slip count, mean time between slips, max phase jump, drift before slip, amplitude drop before slip, generated-stage instability, correction lag, and budget spikes.

Quick smoke result from `runs/bridge_phase_slip_audit_quick_smoke`:

- Best 3 -> 6 -> 9 row: `stage_B_detuning_servo` on `feedforward_best_magnetic_bias`.
- Metrics: emergent phase lock 0.733, fitted target 9.0226, bridge ratio 3.226, spectral purity 0.929, budget error 0.00109, servo work fraction 0.000197.
- Failure style: discrete phase slips, with 4 detected slips and max phase jump about 3.11 radians.
- Generated 6 destabilized before target lock loss: generated-envelope CV 0.586 and pre-slip instability 0.341.
- Target amplitude breathing was not the main predictor; target amplitude/drift correlation was about -0.443 and pre-slip amplitude drop was about 0.101.
- Servo correction lag was high in the top 369 row, about 2.36, but the root fix is generated-6 stabilization.
- Non-369 controls reached high lock by violating budget: best 4 -> 8 -> 12 budget error was about 0.044 and 5 -> 10 -> 15 was about 0.20.

## Latest Generated Stage Stabilizer Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer --quick
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer --sweeps
```

What it tests:

- Generated-stage damping/Q, Stage A tuning around generated 2f, A->B/B->target coupling asymmetry, passive saturation, lossy/hysteretic magnetic damping, predictive slip guard, and a diagnostic artificial-envelope ceiling.
- 3 -> 6 -> 9 discovery candidate plus 4 -> 8 -> 12 and 5 -> 10 -> 15 controls in every ranking.
- Generated-envelope CV/slope, generated phase error/slips, target phase slips/jumps, pre-slip generated instability, correction lag, target lock, fitted target, bridge ratio, spectral purity, budget, and stabilizer work.
- Half-dt and quarter-dt checks for top 369 rows before any promotion.

Quick smoke result from `runs/bridge_generated_stage_stabilizer_quick_smoke`:

- Best strict-budget 369 row: `generated_stage_damping / moderate_q_damping`.
- Metrics: target phase lock 0.825, target slips 2, max target phase jump 2.84 rad, generated envelope CV 0.559, pre-slip generated instability 0.308, bridge ratio 3.166, spectral purity 0.952, budget error 0.000921, work fraction 0.000165.
- Raw `stage_A_tuning / tune_plus_0p03` removed target slips, but failed budget with error 0.0127; it is evidence, not a promotable result.
- The diagnostic artificial-envelope ceiling reduced generated CV to 0.134 and slips to 0, but it also broke budget/work and collapsed bridge ratio, so it remains a ceiling/control only.
- No row passed promotion. Dt validation did not preserve a slip-free, budget-clean result.
- Current read: generated-envelope instability is likely causal, but the budget-clean stabilizer is not strong enough yet.

## Latest Stage A Budget Audit Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_stageA_budget_audit
python tesla_369_lab.py --mode bridge_stageA_budget_audit --quick
python tesla_369_lab.py --mode bridge_stageA_budget_audit --sweeps
```

What it tests:

- Whether the raw slip-free `stage_A_tuning / tune_plus_0p03` basin can be made static, passive, and budget-clean.
- Static Stage A tuning, Stage A tuning sweep, no-servo static tuning, drive-delayed initialization, pre-drive adiabatic ramp, work-counted in-drive ramp, damping/Q compensation, A->B coupling reduction, passive soft limiter, and a physicalized passive 2f absorber branch.
- 3 -> 6 -> 9 discovery rows plus 4 -> 8 -> 12 and 5 -> 10 -> 15 controls in every ranking.
- Explicit parameter-work accounting, budget error before/during/after drive, no-direct-drive flags, half-dt and quarter-dt validation for top 369 rows.

Quick smoke result from `runs/bridge_stageA_budget_audit_quick_smoke`:

- Static `Stage A tune +0.03` removed slips but failed budget: target lock 0.857, slips 0, max target jump 2.38 rad, generated-envelope CV 0.515, bridge ratio 3.424, purity 0.956, budget error 0.0118.
- Static `+0.03` with no servo also failed budget, with error 0.0137 and zero parameter work. This points to the final tuned configuration, not dynamic retuning alone.
- Best compensation near-miss was `tune_plus_damping_compensation / moderate_q_damping`: lock 0.915, slips 0, bridge ratio 3.397, purity 0.969, work fraction 0.000106, but budget error 0.00786.
- Best budget-clean 369 row was drive-delayed initialization: budget error 0.00293 and work 0.000129, but it still had 2 slips and generated-envelope CV 0.522.
- No row passed promotion, and non-369 controls did not produce a budget-clean winner.
- Current read: the slip-free basin is real but budget-sensitive. The next move should be full generated-stage/passive compensation sweeps.

## Latest Stage A Budget Forensics Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_stageA_budget_forensics
python tesla_369_lab.py --mode bridge_stageA_budget_forensics --quick
python tesla_369_lab.py --mode bridge_stageA_budget_forensics --sweeps
```

What it tests:

- Part A isolates the Stage A `+0.03` and tune+damping rows across no-drive/no-servo subsystem accounting cases.
- Part B runs a narrow compensation search around Stage A offset, generated-stage damping/Q, A->B coupling, Stage B detuning, and weak passive limiter strength.
- It reports relative and absolute budget error, budget growth, stored-energy delta, drive work, damping/spark/magnetic loss, nonlinear-potential delta, phase/slip/envelope metrics, and no-direct-drive flags.

Quick smoke result from `runs/bridge_stageA_budget_forensics_quick_smoke`:

- No-drive/no-servo relative budget errors were tiny-denominator artifacts: worst relative error reached 1, but worst absolute error was only about 1.2e-9.
- Driven full-model rows create the gate-relevant error. Stage A `+0.03` full model had budget error 0.0137 at baseline dt, then 0.000092 at half-dt and 0.0000075 at quarter-dt.
- Tune+damping full model had budget error 0.00547 at baseline dt, then 0.000891 at half-dt and 0.000234 at quarter-dt.
- A budget-clean zero-slip row was found: Stage A offset `+0.030`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`; budget 0.000422, work 0.000109, bridge ratio 2.549, purity 0.950.
- That row did not promote because target lock was only 0.834, max phase jump was 2.30 rad, and generated-envelope CV was 0.553.
- No 369 row became promotion-ready, and non-369 controls produced no budget-clean winner.
- Current read: repair/refine the driven nonlinear+damping ledger, then rerun the compensation search at refined dt before full sweeps or predictive servo timing.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Repair or refine driven nonlinear+damping energy accounting, because the budget failure is strongly dt-sensitive.
2. Rerun the Stage A compensation search at refined dt, then revisit servo timing only if lock/jump/envelope gates remain the blocker.
3. Treat non-369 controls as first-class competitors because they still beat 3 -> 6 -> 9 on raw phase lock, while failing budget.
4. Add a geometry/evolve mode only after a 4x-stable 3 -> 6 -> 9 seed beats non-369 controls under the same accounting.
