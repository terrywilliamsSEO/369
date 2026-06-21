# Project Status

Last updated: 2026-06-21

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
- Harmonic-family mapping shows the strongest normalized quick-smoke row is 5 -> 10 -> 15, not 3 -> 6 -> 9; no family passed the harmonic bridge candidate gate yet.
- Harmonic dt rescue shows the 4 -> 8 -> 12 near miss can satisfy all strict non-budget phase/bridge/envelope gates across dt after target detuning, but baseline-dt budget error still blocks promotion.
- Harmonic budget-ledger forensics shows the 4 -> 8 -> 12 budget residual collapses with timestep: baseline 0.04490, half-dt 0.00498, quarter-dt 0.000605, eighth-dt 0.000110, with estimated convergence order about 3.11. No single ledger component matches the residual.
- Harmonic substep quadrature shows the residual is trajectory-integration sensitive: same-trajectory quadrature does not close baseline, but substep-4 re-integration closes baseline/half/quarter/eighth dt and preserves the strong 4 -> 8 -> 12 bridge.
- Harmonic 4 -> 8 -> 12 detuning refinement finds strict substep-4 rows: the best quick row uses target detuning `-0.08` and limiter `0.03`, with all-dt lock 0.992, bridge ratio 1.589, purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max jump 0.972 rad, and near slips 0.
- The standalone `independent_validate_412.py` script independently reproduces the strict 4 -> 8 -> 12 candidate without importing the main harness: baseline/half/quarter dt all pass, worst lock 0.992, bridge ratio 1.607, purity 0.923, budget 0.0000510, generated-envelope CV 0.135, max jump 0.972 rad, near slips 0, and `independent_validation_passed=True`.
- The standalone `physical_412_lc_bridge.py` script expresses that independent 4 -> 8 -> 12 bridge as three coupled nonlinear LC resonators under audio, low-RF, and normalized scale presets. All scale presets pass baseline/half/quarter dt gates with worst lock 0.992108, bridge ratio 1.606971, purity 0.922789, budget 0.0000510, generated-envelope CV 0.134693, max jump 0.971944 rad, and no direct 8/12 drive or target-frequency injection.
- The standalone `spice_412_export.py` script now exports and runs ngspice-compatible audio, low-RF, normalized, nonlinear-variant, linear-control, and direct 4+8 reference netlists for the physical LC bridge. WSL ngspice was installed and the latest local run completed 15 of 19 netlists; 4 stiff behavioral/audio/RF rows failed to converge. The normalized behavioral proxy preserved strong lock and purity but not the Python bridge-ratio gain.
- The standalone `spice_412_refine_nonlinearity.py` script runs a focused normalized-scale ngspice refinement sweep over nonlinear component implementations. It found two source-only behavioral proxy rows above bridge ratio 1.5 with clean linear controls; the closest row had lock 0.996193, purity 0.981658, bridge ratio 1.563169, target-band growth 1.276714, and generated-envelope CV 0.091533. No component-plausible diode/varactor/saturable/hybrid row promoted.
- The standalone `spice_412_component_realism.py` script removes behavioral current mixing from discovery and sweeps component-plausible diode, varactor, saturable, hybrid, and trap networks. Six component rows crossed bridge ratio 1.5, but none phase-locked; the closest row had lock 0.016446, purity 0.986424, bridge ratio 1.573878, and no promotion. Weak-nonlinearity and detuned controls also leaked target-band response, so controls did not all stay dead.

## Current Blocker

No 3 -> 6 -> 9 passive model has passed the strict 4x runtime lock gate.

The main 3 -> 6 -> 9 failure is still generated-stage lock quality and phase slips. The harmonic-family quick smoke did not support 369 uniqueness. The 4 -> 8 -> 12 branch now has strict substep-4 candidate rows, standalone independent validation, a first LC physicalization, first local ngspice execution, a behavioral-only SPICE refinement candidate, and a first component-realism sweep. The blocker for that branch is phase-locking component-plausible nonlinear networks while keeping controls clean, plus parameter sensitivity and broader family-law replication, not the earlier baseline ledger residual.

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

## Latest Stage A Refined Basin Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_stageA_refined_basin
python tesla_369_lab.py --mode bridge_stageA_refined_basin --quick
python tesla_369_lab.py --mode bridge_stageA_refined_basin --sweeps
python tesla_369_lab.py --mode bridge_stageA_refined_basin --quick --sweeps
```

What it tests:

- A focused refined-dt map around the budget-clean Stage A basin from forensics.
- Half-dt primary rows by default, with baseline-dt, half-dt, and quarter-dt validation for the top 369 rows.
- Stage A offset, generated-stage damping factor, A->B coupling, passive limiter strength, and Stage B detuning across 3 -> 6 -> 9, 4 -> 8 -> 12, and 5 -> 10 -> 15.
- Target lock, bridge ratio, spectral purity, relative/absolute budget error, budget convergence, generated/target envelope CV, max phase jump, near slips over 1 rad, and direct-drive contamination flags.

Quick smoke result from `runs/bridge_stageA_refined_basin_quick_smoke`:

- The Stage A `+0.03` lead remained budget-clean at half-dt: budget error 0.00147, absolute budget error 0.0000724, lock 0.836, bridge ratio 2.555, purity 0.950.
- No 369 row crossed the lock gate. Best 369 lock was 0.864.
- No 369 row crossed the generated-envelope gate. Best generated-envelope CV was 0.528, far above 0.25.
- No 369 row crossed the phase-jump gate. Best max phase jump was 2.36 rad, and top rows still had 22-24 near slips.
- A 5 -> 10 -> 15 control was budget-clean and stronger by normalized score, though it failed promotion by bridge ratio.
- No 369 row became promotion-ready after dt validation.
- Current next fix: limiter redesign plus predictive servo timing before full sweeps. Geometry/evolve remains premature.

## Latest Limiter Predictive Servo Summary

Mode added:

```bash
python tesla_369_lab.py --mode bridge_limiter_predictive_servo
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --quick
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --sweeps
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --quick --sweeps
```

What it tests:

- Track A: passive limiter redesign only, including existing, soft/tanh/cubic-quintic/coupling saturation, adaptive generated damping, envelope-derivative damping, and energy-bucket limiting.
- Track B: predictive servo timing only using generated-envelope derivative, generated/target phase acceleration, energy-ratio derivative, and predicted near-slip score.
- Track C: combined limiter plus predictive servo rows.
- It keeps direct 2f drive, direct 3f drive, and target-frequency injection out of discovery rows while tracking limiter loss/work, servo work, predictive trigger count, and lead time before phase jumps.

Quick smoke result from `runs/bridge_limiter_predictive_servo_quick_smoke`:

- No 369 row promoted. The best 369 generated-envelope CV was 0.274, still above the 0.25 gate.
- Best 369 max phase jump was 1.744 rad, still above the 1.0 rad gate.
- Passive `adaptive_generated_damping` crossed lock >0.90 while budget-clean: primary lock 0.968, budget 0.00438, bridge ratio 2.152, purity 0.991.
- That high-lock row preserved lock under dt validation: half-dt lock 0.968 and quarter-dt lock 0.970, but CV stayed about 0.281 and max jump stayed about 1.75-1.77 rad.
- Predictive servo timing recorded trigger lead times, but it did not reduce max jump below gate.
- A 5 -> 10 -> 15 control remained much stronger by normalized budget score, so 369 did not beat the controls.
- Current next fix: general harmonic-bridge study before geometry/evolve; if continuing the 369 branch, try a true active PLL or a more physical limiter redesign.

## Latest Harmonic Bridge Family Summary

Mode added:

```bash
python tesla_369_lab.py --mode harmonic_bridge_family --quick
python tesla_369_lab.py --mode harmonic_bridge_family --quick --sweeps
```

What it tests:

- Whether staged f->2f->3f bridging is general rather than 369-specific.
- Families 2->4->6 through 8->16->24.
- Passive baseline, refined Stage A basin equivalent, adaptive generated damping, envelope-derivative damping, and energy-bucket limiter rows.
- A `true_PLL_comparator` proxy marked `active_control` and scored separately from passive discovery.
- Relative and absolute budget error, limiter/servo work, generated/target envelope CV, phase jumps, near slips, normalized family score, and dt preservation at baseline/half/quarter dt for top rows.

Quick smoke result from `runs/harmonic_bridge_family_quick_smoke`:

- Strongest passive normalized family: 5 -> 10 -> 15 passive baseline. Metrics: lock 0.994, bridge ratio 1.122, purity 0.999, budget error 0.000749, generated-envelope CV 0.057, max jump 0.807, normalized score 0.328.
- 5 -> 10 -> 15 did not promote because bridge ratio stayed below the 1.5 gate.
- Best 3 -> 6 -> 9 normalized row was passive baseline, but it failed badly on lock/jump/envelope: lock 0.735, generated-envelope CV 0.582, max jump 3.05 rad, and 21 near slips.
- The prior high-lock 369 adaptive damping row reappeared as a diagnostic: lock 0.968, bridge ratio 2.152, purity 0.991, budget 0.00437, but generated-envelope CV 0.281, max jump 1.744 rad, 22 near slips, and no dt preservation.
- 4 -> 8 -> 12 was closest to a harmonic candidate: refined Stage A equivalent reached lock 0.984, bridge ratio 1.929, purity 0.992, budget 0.00185, generated-envelope CV 0.126, max jump 1.05 rad, but dt preservation was only 0.667.
- No family passed `harmonic_bridge_candidate`; no family passed `strict_harmonic_bridge_candidate`; no `369_unique_candidate` or `general_harmonic_bridge_law` label passed.
- Current read: this does not justify 369-specific promotion. The next step should be family-law mapping before geometry/evolve or a 369-specific PLL.

## Latest Harmonic Bridge Dt Rescue Summary

Mode added:

```bash
python tesla_369_lab.py --mode harmonic_bridge_dt_rescue --quick
python tesla_369_lab.py --mode harmonic_bridge_dt_rescue --quick --sweeps
```

What it tests:

- Whether the 4 -> 8 -> 12 near miss from `harmonic_bridge_family` fails because of true phase instability or timestep-sensitive tuning/accounting.
- Baseline dt, half dt, and quarter dt for every candidate.
- Stage A offset, generated damping factor, A->B coupling, limiter strength, target detuning, Stage B detuning, and diagnostic-only phase-analysis windows.
- Comparison rows for 3 -> 6 -> 9 and 5 -> 10 -> 15 under the same all-dt aggregate scoring.
- Worst-case all-dt lock, bridge ratio, purity, budget, envelope CV, max jump, near slips, and dt metric spreads.

Quick smoke result from `runs/harmonic_bridge_dt_rescue_quick_smoke`:

- Best 4 -> 8 -> 12 physical rescue row used target detuning `-0.08`.
- Its strict non-budget metrics survived all dt levels: lock stayed about 0.985, bridge ratio about 1.875, purity about 0.992, generated-envelope CV below 0.139, max jump below 0.999 rad, and near slips stayed 0.
- It still failed promotion because budget was dt-sensitive: baseline budget error 0.04485, half-dt 0.005006, quarter-dt 0.000628.
- No 4 -> 8 -> 12 row passed `harmonic_bridge_candidate` or strict because no row met the all-dt budget gate.
- After bridge-ratio gating, 4 -> 8 -> 12 beat 5 -> 10 -> 15. 3 -> 6 -> 9 remained behind 4 -> 8 -> 12, but not behind 5 -> 10 -> 15 once 5-family budget/bridge-ratio failures were counted.
- Current read: the 4 -> 8 -> 12 failure is not a true phase instability in the best row. It is a budget-ledger/dt sensitivity problem followed by a target-detuning refinement problem.

## Latest Harmonic Bridge Budget Ledger Summary

Mode added:

```bash
python tesla_369_lab.py --mode harmonic_bridge_budget_ledger --quick
python tesla_369_lab.py --mode harmonic_bridge_budget_ledger --quick --sweeps
```

What it tests:

- The 4 -> 8 -> 12 target-detuned row from dt-rescue, plus 3 -> 6 -> 9, 5 -> 10 -> 15, no-drive/no-servo, drive-only, damping-only, nonlinear-only, limiter-only, and full-model 4 -> 8 -> 12 diagnostic rows.
- Baseline dt, half dt, quarter dt, and optional eighth dt in sweep mode.
- Existing left-endpoint ledger, sampled midpoint/trapezoid accounting, RK-loop cumulative accounting, finite-difference energy delta, component-wise energy delta, and diagnostic magnetic-loss subtraction.
- Stored-energy delta, drive work, positive input work, damping/spark/magnetic loss, limiter/adaptive work, nonlinear-potential delta, total residual, relative/absolute budget error, residual scaling, and convergence order.

Quick smoke result from `runs/harmonic_bridge_budget_ledger_quick_smoke`:

- Primary 4 -> 8 -> 12 non-budget metrics stayed stable across dt: worst lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max jump 0.998 rad, and near slips 0.
- Existing ledger error converged down strongly: baseline 0.04490, half-dt 0.00498, quarter-dt 0.000605, eighth-dt 0.000110; estimated convergence order was about 3.11.
- Midpoint/trapezoid accounting did not make baseline dt budget-clean: baseline stayed 0.04401, though quarter-dt stayed clean at 0.000850 and eighth-dt was 0.0000116.
- No single component matched the residual; diagnostic magnetic-loss subtraction made the residual much worse, so the failure is not a simple missing magnetic-loss term.
- The row remains `candidate_pending_independent_validation=False`. Current next step: independent corrected/substep quadrature before any promotion, then a tighter 4 -> 8 -> 12 target-detuning sweep if the ledger closes.

## Latest Harmonic Bridge Substep Quadrature Summary

Mode added:

```bash
python tesla_369_lab.py --mode harmonic_bridge_substep_quadrature --quick
python tesla_369_lab.py --mode harmonic_bridge_substep_quadrature --quick --sweeps
```

What it tests:

- The primary 4 -> 8 -> 12 target-detuned near-candidate with Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`, and target detuning `-0.08`.
- Existing ledger, RK-stage-consistent work/loss, sampled trapezoid/Simpson/Gauss-Legendre, finite-difference/component checks, 2/4/8/16 trajectory-preserving substep quadrature, and substep-4 re-integration.
- Comparison rows for 3 -> 6 -> 9, 5 -> 10 -> 15, no-drive/no-servo, drive-only, damping-only, limiter-only, and full-model 4 -> 8 -> 12.
- Direct 2f/3f drive and target-frequency injection remain forbidden.

Quick sweeps result from `runs/harmonic_bridge_substep_quadrature_quick_sweeps_smoke`:

- The primary 4 -> 8 -> 12 row stayed non-budget stable: lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max phase jump 0.998 rad, near slips 0.
- Trajectory-preserving auditors did not close baseline budget: existing ledger 0.04493, RK-stage-consistent 0.06762, and sampled 16-substep quadrature 0.382.
- Re-integrated substep-4 closed budget at every audited dt: baseline 0.0000511, half-dt 0.000000747, quarter-dt 0.0000000298, eighth-dt 0.00000000425.
- The re-integrated trajectory preserved the bridge: baseline substep-4 lock 0.9917, bridge ratio 1.531, purity 0.925.
- Classification: `budget_residual_source=trajectory_integration_error`, `candidate_pending_detuning_refine=True`, `candidate_numerically_fragile=False`.
- This does not final-promote the row. Current next step: tight 4 -> 8 -> 12 target-detuning sweep plus an independent validation script/solver.

## Latest Harmonic Bridge 4->8->12 Detuning Refine Summary

Mode added:

```bash
python tesla_369_lab.py --mode harmonic_bridge_412_detuning_refine --quick
python tesla_369_lab.py --mode harmonic_bridge_412_detuning_refine --quick --sweeps
```

What it tests:

- The substep-validated 4 -> 8 -> 12 target-detuned basin around target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, and limiter `0.04`.
- Substep-4 re-integration for every primary candidate row.
- Baseline/half/quarter-dt validation for top rows, with eighth dt added in sweep mode.
- Comparison rows for the best current 3 -> 6 -> 9 and 5 -> 10 -> 15 rows under the same substep-4 accounting, plus 4 -> 8 -> 12 no-detuning and a direct-reference ceiling.
- Direct 2f/3f drive and target-frequency injection remain forbidden in discovery rows.

Quick smoke result from `runs/harmonic_bridge_412_detuning_refine_quick_smoke3`:

- Best row: target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.03`.
- It passed `harmonic_bridge_candidate`, `strict_harmonic_bridge_candidate`, and `family_lead_candidate` across baseline, half, and quarter dt.
- Worst all-dt metrics: lock 0.992, bridge ratio 1.589, purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max phase jump 0.972 rad, and near slips 0.
- Nearby strict passes were also found at Stage A `+0.045`, target detuning `-0.075`, and target detuning `-0.070`.
- 4 -> 8 -> 12 beat the 3 -> 6 -> 9 and 5 -> 10 -> 15 comparison rows under the same substep accounting and bridge-ratio gating. The 5 -> 10 -> 15 control kept high lock but failed the bridge-ratio gate.
- Current next fix: independent validation solver, then full family-law mapping. Do not promote geometry/evolve from this mode alone.

## Latest Independent 4->8->12 Validation Summary

Script added:

```bash
python independent_validate_412.py
```

Outputs:

- `runs/independent_validate_412/independent_412_summary.json`
- `runs/independent_validate_412/independent_412_summary.csv`
- `runs/independent_validate_412/independent_412_timeseries.csv`
- `runs/independent_validate_412/README_INDEPENDENT_412_VALIDATION.md`

What it tests:

- The strict 4 -> 8 -> 12 candidate outside the main experiment orchestration.
- Explicit effective constants for target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.03`.
- Substep-4 RK4 integration and energy accounting for baseline, half-dt, and quarter-dt.
- Candidate source-only drive policy: no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- A direct 4+8 ceiling denominator is simulated only to compute bridge ratio, never as a discovery row.

Standalone result:

- `independent_validation_passed=True` and `all_dt_passed=True`.
- Worst all-dt metrics: lock 0.992, bridge ratio 1.607, purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max phase jump 0.972 rad, near slips 0.
- Budget residual converged with dt: baseline 0.0000510, half-dt 0.000000749, quarter-dt 0.0000000295.
- No material differences from the main harness were detected. The bridge ratio is slightly higher because the standalone reference denominator is candidate-specific.
- Current next fix: full family-law mapping and broader independent replication before any geometry/evolve promotion.

## Latest Physical 4->8->12 LC Bridge Summary

Script added:

```bash
python physical_412_lc_bridge.py
```

Outputs:

- `runs/physical_412_lc_bridge/physical_412_summary.json`
- `runs/physical_412_lc_bridge/physical_412_summary.csv`
- `runs/physical_412_lc_bridge/physical_412_timeseries.csv`
- `runs/physical_412_lc_bridge/README_PHYSICAL_412_LC_BRIDGE.md`

What it tests:

- A normalized but physically interpretable three-LC version of the independently validated strict 4 -> 8 -> 12 bridge.
- Scale presets: `audio-scale`, `low-RF-scale`, and `arbitrary-normalized-scale`.
- Resonator values computed from `f = 1 / (2*pi*sqrt(LC))`, with `R` derived from the validated damping/Q values.
- Weak linear coupling, varactor-like quartic capacitance, nonlinear mixing, and passive soft-limiter loss.
- Source-only drive on resonator 1. No direct generated-mode drive, no direct target-mode drive, and no target-frequency injection.
- Direct 4+8 is still used only as a bridge-ratio ceiling denominator.

Standalone result:

- `all_dt_all_scales_passed=True`.
- Worst all-dt/all-scale metrics: lock 0.992108, bridge ratio 1.606971, purity 0.922789, budget 0.0000510, generated-envelope CV 0.134693, target-envelope CV 0.035824, max phase jump 0.971944 rad, near slips 0.
- Audio-scale representative values: f=(440, 883.894, 1309.862) Hz, L=(13.08 mH, 6.90 mH, 4.47 mH), C=(10 uF, 4.7 uF, 3.3 uF), R=(0.912, 0.901, 0.480) ohm, Q=(39.7, 42.5, 76.8), all mild.
- Low-RF representative values: f=(1.0 MHz, 2.009 MHz, 2.977 MHz), L=(25.33 uH, 13.36 uH, 8.66 uH), C=(1 nF, 470 pF, 330 pF), R=(4.01, 3.97, 2.11) ohm, Q=(39.7, 42.5, 76.8), all mild.
- Linear coupling fractions are weak at about 0.00427 and 0.00420. The aggressive assumption is the nonlinear mixing strength, not the LC/Q values.
- Current next fix: physical nonlinear-component refinement, parameter sweep, and spatial phase-matching modeling.

## Latest SPICE 4->8->12 Export Summary

Script added:

```bash
python spice_412_export.py
```

Outputs:

- `runs/spice_412_bridge/audio_412_bridge.cir`
- `runs/spice_412_bridge/low_rf_412_bridge.cir`
- `runs/spice_412_bridge/normalized_412_bridge.cir`
- `runs/spice_412_bridge/reference_direct_4plus8.cir`
- variant netlists for `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, and `linear_no_nonlinearity_control`
- `runs/spice_412_bridge/spice_412_summary.json`
- `runs/spice_412_bridge/spice_412_summary.csv`
- `runs/spice_412_bridge/README_SPICE_412_EXPORT.md`

What it tests:

- Exports the physical 4 -> 8 -> 12 LC bridge into ngspice-compatible netlists.
- Execution is explicit: use `python spice_412_export.py --run`; pass native Windows ngspice with `--ngspice-path "C:/path/to/ngspice.exe"` or WSL ngspice with `--ngspice-path wsl:ngspice`.
- Per-netlist execution statuses are now `exported`, `skipped_no_ngspice`, `ran_successfully`, `failed_to_converge`, and `parser_failed`.
- Discovery netlists drive only resonator 1 and keep direct resonator 2 drive, direct resonator 3 drive, and target-frequency injection absent.
- The direct 4+8 netlist is separated as `reference_direct_4plus8.cir` with role `ceiling_reference`.
- Circuit elements include three lossy LC tanks, Q-matched inductor-branch resistance, weak mutual inductive coupling, behavioral varactor-like capacitance, behavioral nonlinear mixing, and passive soft-limiter conductance.
- Nonlinear realism variants include `behavioral_proxy_current`, `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, and `linear_no_nonlinearity_control`.
- If ngspice is installed, the script runs transient simulations, writes ngspice CSV/raw outputs, parses voltages/currents, and computes target voltage growth, source/generated/target FFT peaks, approximate lock, bridge ratio, purity near 12, generated-envelope CV, and max jump.

Standalone result:

- `valid_spice_netlists_generated=True`.
- WSL install command completed through `wsl -u root`: ngspice is available as `/usr/bin/ngspice`, version `ngspice-42`.
- Run command tested: `python spice_412_export.py --run --ngspice-path wsl:ngspice`.
- `ngspice_available=True`; status mix is `failed_to_converge;ran_successfully`, with 15 rows successful and 4 rows correctly classified as convergence failures.
- Convergence failures were the audio and low-RF `behavioral_proxy_current` rows plus the audio and low-RF `voltage_dependent_capacitance_proxy` rows. Failures reported ngspice `TRAN: Timestep too small`.
- `discovery_rows_source_only=True`; the audio, low-RF, and normalized discovery netlists have no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- The normalized `behavioral_proxy_current` discovery row is the closest SPICE reproduction: lock `0.997003`, purity `0.971359`, target growth `2.06766`, max phase jump `0.274669`, but normalized bridge ratio only `0.788167` versus Python LC `1.606971`.
- Target-band build-up was observed in several nonlinear rows, but none roughly reproduced all Python LC behavior once bridge ratio was included.
- Linear no-nonlinearity controls failed as expected under target-band criteria: phase lock stayed near `0.014`, purity near `1.7e-6`, and target-node FFT peaks stayed at the source frequency.
- Nonlinear element assessment: aggressive behavioral varactor/mixing proxy; useful for first circuit validation but not yet a component-level implementation.
- Current next fix: refine nonlinear components, run parameter sweeps, and add spatial phase-matching modeling.

## Latest SPICE 4->8->12 Nonlinearity Refinement

Script added:

```bash
python spice_412_refine_nonlinearity.py --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_refine_nonlinearity/spice_412_refine_summary.json`
- `runs/spice_412_refine_nonlinearity/spice_412_refine_summary.csv`
- `runs/spice_412_refine_nonlinearity/spice_412_refine_timeseries.csv`
- `runs/spice_412_refine_nonlinearity/README_SPICE_412_REFINE_NONLINEARITY.md`

What it tests:

- Focused normalized-scale ngspice sweep over `behavioral_proxy_current`, `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, `hybrid_varactor_plus_saturable_inductor`, and `linear_no_nonlinearity_control`.
- Encodes the requested axes: nonlinear strength scale `0.25, 0.5, 1, 2, 4, 8`; limiter/conductance scale `0.25, 0.5, 1, 2, 4`; coupling scale `0.5, 0.75, 1.0, 1.25, 1.5`; drive amplitude scale `0.5, 1.0, 1.5, 2.0`; conservative/default/relaxed solver profiles; and max timestep scale `0.5, 1.0, 2.0`.
- Discovery rows remain source-only with no direct 8 drive, no direct 12 drive, and no target-frequency injection. Matching direct 4+8 reference rows are separated as ceiling denominators only.

Standalone result from `--max-discovery-cases 56`:

- 56 discovery rows were run; 36 ran successfully and 20 failed to converge with ngspice `TRAN: Timestep too small`.
- Bridge ratio >1.5 was reached by `r038` and `r042`, both `behavioral_proxy_current`.
- Closest Python-LC row was `r042`: nonlinear strength scale `2.0`, limiter scale `2.0`, coupling scale `1.25`, drive scale `1.5`, default solver, maxstep scale `1.0`; lock `0.996193`, purity `0.981658`, bridge ratio `1.563169`, target-band growth `1.276714`, generated-envelope CV `0.091533`, max jump `0.289970`.
- Linear no-nonlinearity controls remained dead: maximum leakage score `0.0`; target-band growth stayed `0`, purity near `1.7e-6`, and target FFT peaks stayed at source frequency.
- No component-plausible diode/varactor/saturable/hybrid row promoted. Successful promotion is behavioral-only.
- Current next fix: component-level refinement to replace behavioral mixing, then a physical parameter sweep.

## Latest SPICE 4->8->12 Component Realism

Script added:

```bash
python spice_412_component_realism.py --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_component_realism/spice_412_component_realism_summary.json`
- `runs/spice_412_component_realism/spice_412_component_realism_summary.csv`
- `runs/spice_412_component_realism/spice_412_component_realism_timeseries.csv`
- `runs/spice_412_component_realism/README_SPICE_412_COMPONENT_REALISM.md`

What it tests:

- Component-plausible nonlinear replacements for the behavioral proxy winner.
- Discovery variants: `anti_parallel_diode_mixer`, `diode_bridge_mixer`, `varactor_pair_mixer`, `back_to_back_varactor_stack`, `saturable_inductor_core`, `coupled_saturable_transformer`, `hybrid_varactor_plus_saturable_inductor`, and `diode_plus_resonant_trap_network`.
- Controls: `linear_no_nonlinearity_control`, `weak_nonlinearity_control`, `detuned_target_control`, `shuffled_frequency_control`, and separated direct 4+8 ceiling references.
- Discovery rows remain source-only with no direct 8 drive, no direct 12 drive, and no target-frequency injection. Behavioral current mixing is forbidden for discovery rows.

Standalone result from `--max-cases 44`:

- 40 discovery rows were evaluated; 38 ran successfully and 2 failed to converge with ngspice `TRAN: Timestep too small`.
- Bridge ratio >1.5 was crossed by `c008`, `c013`, `c018`, `c023`, `c028`, and `c033`, all component-plausible source-only rows.
- No row promoted: those bridge-ratio crossers did not phase-lock. The closest component row was `c018` (`back_to_back_varactor_stack`) with lock `0.016446`, purity `0.986424`, bridge ratio `1.573878`, target-band growth `0.984463`, and plausible stress.
- No near miss promoted because the near-miss gate requires lock >0.90, purity >0.80, bridge ratio >1.0, and clean controls.
- Linear and shuffled controls stayed dead, but weak-nonlinearity and detuned controls showed target-band leakage under the current criterion. `controls_remained_dead=False`, with maximum leakage score `0.600079`.
- Convergence failures were `c015` (`varactor_pair_mixer`) and `c035` (`hybrid_varactor_plus_saturable_inductor`), both at conservative max-step settings with `TRAN: Timestep too small` around `dvp12a`.
- Current next fix: deeper component sweep and spatial phase-matching modeling before physical parameter refinement.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Deepen component-plausible nonlinear sweeps, especially around phase-locking and clean weak/detuned controls.
2. Run the expanded `harmonic_bridge_412_detuning_refine --quick --sweeps` grid when runtime is acceptable.
3. Refine physical component ranges, nonlinear capacitance/mixing implementation, coupling implementation, and spatial phase matching.
4. Treat the entire f->2f->3f family as first-class until 369 beats it under normalized budget scoring.
5. If staying on 369, use either a true PLL or a more physical limiter redesign; predictive timing alone did not clear jump/CV gates.
6. Add a geometry/evolve mode only after a 4x-stable 3 -> 6 -> 9 seed beats non-369 controls under the same accounting.
