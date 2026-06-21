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
- The standalone `spice_412_component_realism.py` script removes behavioral current mixing from discovery and sweeps component-plausible diode, varactor, saturable, hybrid, and trap networks. Six component rows crossed bridge ratio 1.5, but none phase-locked; the closest behavioral-proxy row had lock 0.017518, purity 0.989155, bridge ratio 1.647442, and no promotion. Weak-nonlinearity and detuned controls also leaked target-band response, so controls did not all stay dead.
- The standalone `spice_412_component_phase_lock.py` script sweeps detuning, coupling orientation/sign, coupling strength, Q/load shaping, trap phase shapers, and limiter/loss around the six component bridge crossers. It preserved many high bridge ratios but found no row above phase lock 0.50; weak and detuned controls still leaked under coherent-growth scoring.
- The standalone `spatial_phase_matching_412.py` script models a distributed 1D phase-matched topology for 4 -> 8 -> 12. It promoted 17 source-only spatial bridge candidates with clean controls; the best row had lock 0.999128, bridge ratio 4.748881, purity 0.997300, generated-envelope CV 0.053898, max phase jump 0.000683, and clean energy budget.
- The standalone `spice_412_distributed_ladder.py` script exports the distributed topology as normalized ngspice envelope-ladder netlists. The phase-matched source-only ladder promoted with lock 0.915421, bridge ratio 3.718438, purity 0.970030, generated-envelope CV 0.032846, max phase jump 0.003169, and clean coherent controls.
- The standalone `spice_412_transmission_line_refine.py` script refines that result into explicit normalized LC transmission-line ladders. The phase-matched source-only TL row promoted with lock 0.997206, bridge ratio 8.261740, purity 0.961441, generated-envelope CV 0.070890, max phase jump 0.057316, and behavioral dependency 0.36, lower than the envelope-ladder baseline 0.65.
- The standalone `physical_waveguide_412.py` script maps the promoted TL row into physical media candidates. It ranks a nonlinear varactor-loaded transmission line as the best first electrical bench analog at 50 MHz with required interaction length 0.382 m; acoustic/phononic and nonlinear magnetic lines are also plausible bench-scale, while plain PCB/microstrip is length/nonlinearity limited.
- The standalone `spice_412_varactor_nltl_design.py` script builds concrete 50/100/150 MHz varactor-loaded LC ladder netlists. All 22 ngspice rows ran, controls stayed dead, and behavioral dependency fell to 0.08, but no row promoted because 150 MHz spectral purity stayed low. The best row was 48 cells at 75 ohm with lock 0.896172, bridge ratio 1.287941, purity 0.006802, and plausible stress.
- The standalone `spice_412_varactor_nltl_refine.py` script refines the realistic varactor line with larger cell counts, passive 150 MHz extraction/rejection, load/Q shaping, and stronger capacitance-swing settings. All 23 ngspice rows ran and controls stayed dead. Purity improved to 0.112843, with lock 0.996283 and bridge ratio 18.502732, but no row promoted because target purity remained below gate and the highest-purity row had unrealistic stress.
- The standalone `acoustic_waveguide_412.py` script builds a low-frequency acoustic/phononic analog at 40/80/120 kHz. One source-only phase-matched row promoted: 48 cells, 0.058 m length, lock 0.999352, bridge ratio 4628.598328, 120 kHz purity 0.999611, generated-envelope CV 0.231570, max jump 0.007893, plausible pressure stress, and dead controls.
- The standalone `spice_412_electrical_candidate_race.py` script races realistic electrical families at 50/100/150 MHz. All 26 ngspice rows ran successfully. No electrical candidate or near miss promoted; strongest was hybrid varactor-plus-magnetic with lock 0.964163, bridge ratio 13.199504, purity 0.102689, generated CV 0.086907, max jump 0.676598, aggressive-but-testable stress, and dead controls.

## Current Blocker

No 3 -> 6 -> 9 passive model has passed the strict 4x runtime lock gate.

The main 3 -> 6 -> 9 failure is still generated-stage lock quality and phase slips. The harmonic-family quick smoke did not support 369 uniqueness. The 4 -> 8 -> 12 branch now has strict substep-4 candidate rows, standalone independent validation, a first LC physicalization, first local ngspice execution, a behavioral-only SPICE refinement candidate, a component-realism sweep, a component phase-lock sweep, a distributed phase-matching topology model, a first distributed SPICE ladder export, a less-behavioral transmission-line SPICE refinement, a physical waveguide interpretation layer, a first concrete varactor NLTL SPICE design, a focused varactor NLTL refinement, a promoted acoustic/phononic waveguide analog, and an electrical candidate race across realistic line families. The blocker has narrowed further: lumped component rows can generate target-band energy without coherent phase lock, while the normalized distributed phase-matched model, SPICE envelope ladder, explicit LC transmission-line ladder, and acoustic waveguide analog recover coherent lock with clean controls. Realistic electrical rows can recover lock and bridge gain, but they still do not concentrate enough clean spectral power into the 150 MHz target band. The latest electrical race says target extraction helps, and hybrid varactor-plus-magnetic is stronger than pure varactor, but purity remains below the candidate and near-miss gates.

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
- No row promoted: those bridge-ratio crossers did not phase-lock. The closest behavioral-proxy row was `c008` (`diode_bridge_mixer`) with lock `0.017518`, purity `0.989155`, bridge ratio `1.647442`, target-band growth `1.284235`, and plausible stress.
- No near miss promoted because the near-miss gate requires lock >0.90, purity >0.80, bridge ratio >1.0, and clean controls.
- Linear and shuffled controls stayed dead, but weak-nonlinearity and detuned controls showed target-band leakage under the current criterion. `controls_remained_dead=False`, with maximum leakage score `0.600079`.
- Convergence failures were `c015` (`varactor_pair_mixer`) and `c035` (`hybrid_varactor_plus_saturable_inductor`), both at conservative max-step settings with `TRAN: Timestep too small` around `dvp12a`.
- Current next fix: deeper component sweep and spatial phase-matching modeling before physical parameter refinement.

## Latest SPICE 4->8->12 Component Phase Lock

Script added:

```bash
python spice_412_component_phase_lock.py --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_component_phase_lock/spice_412_component_phase_lock_summary.json`
- `runs/spice_412_component_phase_lock/spice_412_component_phase_lock_summary.csv`
- `runs/spice_412_component_phase_lock/spice_412_component_phase_lock_timeseries.csv`
- `runs/spice_412_component_phase_lock/README_SPICE_412_COMPONENT_PHASE_LOCK.md`

What it tests:

- Focused phase-lock refinement around bridge-ratio crossing component rows `c008`, `c013`, `c018`, `c023`, `c028`, and `c033`.
- Axes include target resonator detuning, generated resonator detuning, coupling sign/orientation, coupling strength, source/generated/target Q shaping, passive resonant traps, and limiter/loss shaping.
- Discovery rows remain source-only with no behavioral current mixing, no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- Controls include linear no-nonlinearity, weak nonlinearity, detuned target, shuffled frequencies, source-only off-resonance, and separated direct 4+8 ceiling references.

Standalone result from `--max-cases 84`:

- 84 discovery rows and 5 controls ran successfully under WSL `ngspice-42`; no convergence failures.
- Many rows retained bridge ratio >1.5, but none reached phase lock >0.50 and none reached phase lock >0.90.
- Best phase-lock row was `p048` (`varactor_pair_mixer`, coupling orientation): lock `0.030889`, generated lock `0.026074`, bridge ratio `0.633056`, purity `0.914026`, coherent growth `1.03079`.
- Best high-bridge row was `p050` (`saturable_inductor_core`, coupling orientation): bridge ratio `124.013`, lock `0.025185`, purity `0.992149`, coherent growth `2.21288`; it was rejected for phase incoherence.
- Weak-nonlinearity and detuned controls still leaked under coherent-growth criteria: weak leakage `0.566821`, detuned leakage `0.563813`. Linear, shuffled, and off-resonance controls stayed dead.
- Coupling orientation produced the highest phase-lock score in this focused pass, but the absolute lock value remained only `0.030889`.
- Current next fix: spatial phase-matching model or rejection of the current component topology before deeper scalar component sweeps.

## Latest Spatial Phase Matching 4->8->12

Script added:

```bash
python spatial_phase_matching_412.py
```

Outputs:

- `runs/spatial_phase_matching_412/spatial_phase_matching_412_summary.json`
- `runs/spatial_phase_matching_412/spatial_phase_matching_412_summary.csv`
- `runs/spatial_phase_matching_412/spatial_phase_matching_412_timeseries.csv`
- `runs/spatial_phase_matching_412/README_SPATIAL_PHASE_MATCHING_412.md`

What it tests:

- A normalized 1D distributed coupled-mode chain with explicit wave numbers, phase mismatch, quasi-phase-matching gratings, alternating coupling signs, backward-wave target options, group-velocity mismatch, nonlinear 4+4 and 4+8 mixing, and passive saturation loss.
- Discovery rows are source-only at mode 4: no direct generated-mode drive, no direct target-mode drive, and no target-frequency injection.
- Direct 4+8 is a separated ceiling denominator only.
- Controls include randomized grating, linear/no-nonlinearity, detuned target, and shuffled frequency rows.

Standalone result:

- Full run result: 47 discovery rows and 4 controls; 17 rows promoted as `spatial_phase_bridge_candidate`, and 6 more were near misses.
- Best promoted row was `s043 nonlinear_strength_1.55`: topology `co_directional_phase_matched`, lock `0.999128`, bridge ratio `4.748881`, purity `0.997300`, target coherent growth `20.196273`, generated-envelope CV `0.053898`, max phase jump `0.000683`, and energy budget error `3.44e-12`.
- Explicit phase mismatch predicted failure: the mismatched rows fell to lock `0.026108` and `0.060735` with bridge ratios below `0.001`.
- QPM outperformed the compact lumped and mismatched rows but did not fully promote: best QPM lock `0.744986`, bridge ratio `9.413271`, purity `0.970969`.
- Linear, randomized grating, detuned target, and shuffled frequency controls stayed dead under the coherent-growth leakage score; max leakage score was `0.064712`.
- Current interpretation: a plausible next physical path is distributed or waveguide-like phase matching rather than the current lumped LC component topology. This is topology-screening evidence, not hardware proof.
- Current next fix: SPICE distributed ladder export, then physical waveguide/phase-matching refinement.

## Latest SPICE 4->8->12 Distributed Ladder

Script added:

```bash
python spice_412_distributed_ladder.py --run --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_distributed_ladder/phase_matched_codirectional_ladder.cir`
- `runs/spice_412_distributed_ladder/qpm_ladder.cir`
- `runs/spice_412_distributed_ladder/mismatched_ladder_control.cir`
- `runs/spice_412_distributed_ladder/lumped_equivalent_control.cir`
- `runs/spice_412_distributed_ladder/linear_no_nonlinearity_control.cir`
- `runs/spice_412_distributed_ladder/detuned_target_control.cir`
- `runs/spice_412_distributed_ladder/shuffled_frequency_control.cir`
- `runs/spice_412_distributed_ladder/direct_4plus8_ceiling_reference.cir`
- `runs/spice_412_distributed_ladder/spice_412_distributed_ladder_summary.json`
- `runs/spice_412_distributed_ladder/spice_412_distributed_ladder_summary.csv`
- `runs/spice_412_distributed_ladder/spice_412_distributed_ladder_timeseries.csv`
- `runs/spice_412_distributed_ladder/README_SPICE_412_DISTRIBUTED_LADDER.md`

What it tests:

- A normalized ngspice envelope ladder corresponding to the distributed phase-matched 4 -> 8 -> 12 topology.
- Each cell stores source/generated/target real and quadrature envelopes on unit capacitors; behavioral current sources implement propagation, phase mismatch, QPM signs, nonlinear 4+4 and 4+8 mixing, per-cell loss, and passive saturation loss.
- Discovery rows keep source-only drive at the first/source section with no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- Direct 4+8 remains a separated ceiling denominator only.

Standalone result:

- All eight netlists ran successfully under WSL `ngspice-42`.
- One SPICE distributed candidate promoted: `d001 phase_matched_codirectional_ladder`.
- Promoted row metrics: lock `0.915421`, bridge ratio `3.718438`, purity `0.970030`, target coherent growth `18.063953`, generated-envelope CV `0.032846`, target-envelope CV `0.027283`, max phase jump `0.003169`, near slips `0`.
- The phase-matched ladder beat the compact lumped control on coherent lock. The lumped row had large target amplitude but low lock `0.453307`, so it was rejected for phase mismatch.
- Deliberate phase mismatch killed lock: mismatched lock `0.013550`.
- QPM helped relative to mismatch with lock `0.620977` and bridge ratio `5.746898`, but it did not promote because purity was `0.718200`.
- Linear, detuned, and shuffled controls stayed dead; max coherent leakage score was `0.0`.
- Current interpretation: SPICE can reproduce the distributed phase-matched lock in a normalized envelope ladder. This is still not a hardware-realistic circuit.
- Current next fix: physical waveguide modeling and transmission-line ladder refinement.

## Latest SPICE 4->8->12 Transmission-Line Refinement

Script added:

```bash
python spice_412_transmission_line_refine.py --run --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_transmission_line_refine/tl_phase_matched_ladder.cir`
- `runs/spice_412_transmission_line_refine/tl_qpm_ladder.cir`
- `runs/spice_412_transmission_line_refine/tl_mismatched_ladder_control.cir`
- `runs/spice_412_transmission_line_refine/tl_lumped_equivalent_control.cir`
- `runs/spice_412_transmission_line_refine/tl_linear_no_nonlinearity_control.cir`
- `runs/spice_412_transmission_line_refine/tl_detuned_target_control.cir`
- `runs/spice_412_transmission_line_refine/tl_shuffled_frequency_control.cir`
- `runs/spice_412_transmission_line_refine/tl_direct_4plus8_reference.cir`
- `runs/spice_412_transmission_line_refine/spice_412_tl_summary.json`
- `runs/spice_412_transmission_line_refine/spice_412_tl_summary.csv`
- `runs/spice_412_transmission_line_refine/spice_412_tl_timeseries.csv`
- `runs/spice_412_transmission_line_refine/README_SPICE_412_TRANSMISSION_LINE_REFINE.md`

What it tests:

- A normalized ngspice LC transmission-line ladder for the 4, 8, and 12 bands, with per-cell series inductors, shunt capacitors, tuned shunt band sections, loss/loading, capacitive inter-band coupling, and distributed nonlinear mixing.
- Discovery rows remain source-only: no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- Direct 4+8 remains a separated ceiling denominator only.
- Behavioral sources are still used for the nonlinear 4+4 -> 8 and 4+8 -> 12 mixing and saturation proxy, but every row reports `behavioral_dependency_score`.

Standalone result:

- All eight netlists ran successfully under WSL `ngspice-42`.
- One SPICE TL candidate promoted: `t001 tl_phase_matched_ladder`.
- Promoted row metrics: lock `0.997206`, bridge ratio `8.261740`, purity `0.961441`, target coherent growth `3.955957`, generated-envelope CV `0.070890`, target-envelope CV `0.144193`, max phase jump `0.057316`, near slips `0`.
- The promoted row lowered behavioral dependency to `0.36`, below the previous envelope-ladder baseline `0.65`, while preserving the bridge.
- QPM helped relative to dead controls with lock `0.961919`, purity `0.880158`, and target coherent growth `1.583010`, but it did not promote because bridge ratio stayed `0.006003`.
- Deliberate phase mismatch did not kill the raw phase metric on tiny residual response, but it suppressed material bridge ratio to `0.002707`; it remained a dead control.
- Linear, detuned, shuffled, lumped, and mismatched controls stayed dead with max coherent leakage score `0.0`.
- Current next fix: physical waveguide modeling first, then PCB/transmission-line or acoustic waveguide approximations.

## Latest Physical Waveguide 4->8->12 Interpretation

Script added:

```bash
python physical_waveguide_412.py
```

Outputs:

- `runs/physical_waveguide_412/physical_waveguide_412_summary.json`
- `runs/physical_waveguide_412/physical_waveguide_412_summary.csv`
- `runs/physical_waveguide_412/README_PHYSICAL_WAVEGUIDE_412.md`

What it tests:

- A physical interpretation layer for the promoted `spice_412_transmission_line_refine.py` TL row.
- Candidate media: PCB/microstrip or coaxial transmission-line ladder, acoustic/phononic waveguide, nonlinear magnetic transmission line, nonlinear varactor-loaded transmission line, mechanical/metamaterial lattice, and optical/nonlinear waveguide as conceptual comparison only.
- For each row it estimates frequency scale, 4/8/12 wavelengths, phase and group velocity mismatch, required interaction length, coherence length, QPM period, loss per unit length, nonlinear gain per unit length, target coherent growth, stress, feasibility class, and primary blocker.
- Controls include phase-mismatched, too-lossy, too-short, weak-nonlinearity, and linear/no-nonlinearity physical mappings.

Standalone result:

- Best first electrical bench analog: `nonlinear_varactor_loaded_transmission_line`.
- Varactor row: plausible bench-scale, source frequency `50 MHz`, required interaction length `0.381972 m`, cell pitch `0.011937 m`, target coherent growth estimate `4.046130`, bridge ratio estimate `8.261740`.
- Acoustic/phononic row: plausible bench-scale, source frequency `40 kHz`, required length `0.076394 m`, bridge ratio estimate `5.251393`; easiest for compact length and slow phase velocity, but harder for clean nonlinear drive/readout.
- Nonlinear magnetic row: plausible bench-scale, source frequency `10 MHz`, required length `0.763944 m`, bridge ratio estimate `6.137960`; risks are core loss, bias history, and saturation stress.
- Plain PCB/microstrip or coax row: aggressive but testable, source frequency `100 MHz`, required length `6.875494 m`; blocker is length/nonlinearity more than raw loss.
- Mechanical/metamaterial row is aggressive but testable; optical/nonlinear waveguide remains conceptual only.
- Controls stayed dead with max leakage score `0.040093`.
- Current next fix: PCB/transmission-line SPICE design for a varactor-loaded nonlinear transmission line, with acoustic simulation as a parallel low-frequency analog.

## Latest SPICE 4->8->12 Varactor NLTL Design

Script added:

```bash
python spice_412_varactor_nltl_design.py --run --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_varactor_nltl_design/spice_412_varactor_nltl_summary.json`
- `runs/spice_412_varactor_nltl_design/spice_412_varactor_nltl_summary.csv`
- `runs/spice_412_varactor_nltl_design/spice_412_varactor_nltl_timeseries.csv`
- `runs/spice_412_varactor_nltl_design/README_SPICE_412_VARACTOR_NLTL_DESIGN.md`

What it tests:

- A concrete low-RF varactor-loaded nonlinear transmission line at 50/100/150 MHz.
- Cell-count sweep: 12, 16, 24, 32, and 48 cells.
- Impedance sweep: 25, 50, and 75 ohm target lines.
- Reverse-biased varactor diode model with `Cjo`, `Vj`, `M`, `Rs`, `Bv`, and `Ibv`.
- Phase velocity and impedance are set through per-cell L/C; nonlinear generation comes from voltage-dependent junction capacitance.
- Discovery rows remain source-only: no direct 100 MHz drive, no direct 150 MHz drive, and no target-frequency injection.
- Controls include fixed-capacitor linear, weak-varactor, detuned phase velocity, shuffled frequency, too-short, too-lossy, and separated direct 50+100 MHz reference rows.

Standalone result:

- All 22 netlists ran successfully under WSL `ngspice-42`.
- No row promoted as `spice_varactor_nltl_candidate`, and no `near_miss` promoted because target-band purity stayed far below the `0.80` gate.
- Best row by feasibility was `d015 varactor_nltl_48cells_75ohm`.
- Best metrics: lock `0.896172`, bridge ratio `1.287941`, spectral purity near 150 MHz `0.006802`, target coherent growth `1.019062`, generated-envelope CV `0.013623`, max phase jump `2.422032`, plausible component stress.
- Best per-cell values: 48 cells, 75 ohm, cell length about `0.007958 m`, per-cell L about `119.366 nH`, total per-cell C about `21.221 pF`, and varactor `Cjo` about `43.791 pF`.
- Behavioral dependency fell to `0.08`, below the previous normalized TL baseline `0.36`.
- Controls stayed dead with max leakage score `0.099801`.
- Current interpretation: this is a bench-plausible component design, but the first-pass varactor capacitance swing and phase-velocity shaping do not concentrate enough coherent energy into the 150 MHz target band.
- Current next fix: component selection/BOM plus stronger varactor sweep before PCB layout; acoustic waveguide simulation remains a useful parallel low-frequency analog.

## Latest SPICE 4->8->12 Varactor NLTL Refinement

Script added:

```bash
python spice_412_varactor_nltl_refine.py --run --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_varactor_nltl_refine/spice_412_varactor_nltl_refine_summary.json`
- `runs/spice_412_varactor_nltl_refine/spice_412_varactor_nltl_refine_summary.csv`
- `runs/spice_412_varactor_nltl_refine/spice_412_varactor_nltl_refine_timeseries.csv`
- `runs/spice_412_varactor_nltl_refine/README_SPICE_412_VARACTOR_NLTL_REFINE.md`

What it tests:

- A focused refinement around the prior best `d015` 48-cell/75-ohm varactor NLTL row.
- Cell-count sweep: 48, 64, 80, and 96 cells.
- Impedance variants: 50, 75, and 100 ohm.
- Varactor refinement over capacitance swing, `Cjo`, `Rs`, `Vj`, `M`, bias voltage, and drive amplitude.
- Phase-velocity and target-band cleanup variants: raw line, 150 MHz target extraction, weak 150 MHz bandpass, source rejection trap, generated rejection trap, target shunt trap, and extraction plus rejection.
- Controls remain source-only checks with linear fixed capacitance, weak varactor, detuned velocity, shuffled frequency, too-short, too-lossy, and separated direct 50+100 MHz reference rows.

Standalone result:

- All 23 netlists ran successfully under WSL `ngspice-42`.
- No `spice_varactor_nltl_candidate` and no `near_miss` promoted.
- Target-band cleanup did raise purity: best purity improved from the previous `0.006802` to `0.112843`.
- Best purity row: `r013 refine_96c_100ohm_extraction_plus_rejection`, with lock `0.996283`, bridge ratio `18.502732`, purity `0.112843`, target growth `1.075207`, generated-envelope CV `0.073475`, max phase jump `0.252252`, behavioral dependency `0.08`, but `unrealistic` component stress.
- Best plausible-stress purity row: `r003 refine_80c_75ohm_none`, with lock `0.991412`, bridge ratio `8.462014`, purity `0.107203`, target growth `1.007927`, and plausible stress.
- Increasing cell count helped through 80 cells and saturated near 96 cells: best purity by cell count was 48=`0.010084`, 64=`0.050886`, 80=`0.107203`, 96=`0.112843`.
- Passive extraction/rejection helped purity, but not enough for the 0.30 near-miss or 0.80 candidate purity gates.
- Controls stayed dead with max leakage score `0.137543`.
- Current interpretation: low-behavioral varactor NLTL rows can recover lock and bridge gain, but clean 150 MHz target-band purity remains the physical blocker.
- Current next fix: acoustic parallel simulation plus deeper component/BOM sweep before PCB layout.

## Latest Acoustic Waveguide 4->8->12

Script added:

```bash
python acoustic_waveguide_412.py
```

Outputs:

- `runs/acoustic_waveguide_412/acoustic_waveguide_412_summary.json`
- `runs/acoustic_waveguide_412/acoustic_waveguide_412_summary.csv`
- `runs/acoustic_waveguide_412/acoustic_waveguide_412_timeseries.csv`
- `runs/acoustic_waveguide_412/README_ACOUSTIC_WAVEGUIDE_412.md`

What it tests:

- A low-frequency 1D acoustic/phononic waveguide analog for source-only 40 kHz -> generated 80 kHz -> target 120 kHz transfer.
- Explicit wave numbers `k4`, `k8`, `k12`, mismatch terms `delta_k_448 = k8 - 2*k4` and `delta_k_4812 = k12 - k8 - k4`, coherence length, QPM period, forward transport, group-velocity ratios, damping/loss, boundary absorption, and local nonlinear stiffness proxies.
- Discovery rows remain source-only: no direct 80 kHz drive, no direct 120 kHz drive, and no target-frequency injection.
- Controls include linear/no-nonlinearity, weak nonlinearity, detuned target velocity, phase mismatch, shuffled frequency, too-short guide, too-lossy guide, and a separated direct 40+80 kHz ceiling reference.

Standalone result:

- Sixteen rows were evaluated: eight discovery rows, seven controls, and one direct 40+80 ceiling reference.
- One acoustic phase bridge candidate promoted: `a005 phase_matched_short_48cell`.
- Promoted metrics: lock `0.999352`, bridge ratio `4628.598328`, 120 kHz spectral purity `0.999611`, target coherent growth `26.944527`, generated-envelope CV `0.231570`, target-envelope CV `0.322958`, max phase jump `0.007893`, and near slips `0`.
- The promoted row is bench-scale in the normalized acoustic mapping: 48 cells, length `0.058 m`, peak pressure about `328.77 Pa`, plausible pressure stress, and transducer feedthrough risk `0.024243`.
- Phase mismatch predicted failure under material metrics: the mismatched control had bridge ratio `0.000026`, purity `0.009303`, and stayed control-dead.
- Linear, weak, detuned, mismatched, shuffled, too-short, and too-lossy controls stayed dead with max leakage score `0.0`.
- QPM did not beat the best co-directional phase-matched row in this first acoustic pass. The best QPM row kept high raw lock but only bridge ratio `0.013277`.
- Current interpretation: the acoustic/phononic analog recovers clean 120 kHz purity where the realistic varactor NLTL did not. This is still a normalized drive/readout model, so the next fix is acoustic bench design focused on nonlinear transducer coupling, feedthrough suppression, and readout calibration.

## Latest SPICE 4->8->12 Electrical Candidate Race

Script added:

```bash
python spice_412_electrical_candidate_race.py --run --ngspice-path wsl:ngspice
```

Outputs:

- `runs/spice_412_electrical_candidate_race/spice_412_electrical_candidate_race_summary.json`
- `runs/spice_412_electrical_candidate_race/spice_412_electrical_candidate_race_summary.csv`
- `runs/spice_412_electrical_candidate_race/spice_412_electrical_candidate_race_timeseries.csv`
- `runs/spice_412_electrical_candidate_race/README_SPICE_412_ELECTRICAL_CANDIDATE_RACE.md`

What it tests:

- A bounded electrical implementation race at 50/100/150 MHz.
- Candidate families: varactor-loaded NLTL, step-recovery diode line, nonlinear magnetic transmission line, hybrid varactor-plus-magnetic line, high-Q target extraction, distributed bandpass sections, magnetic target extraction, and dual-path phase-matched line.
- Discovery rows remain source-only: no direct 100 MHz drive, no direct 150 MHz drive, no target-frequency injection, and no hidden behavioral target source.
- Controls include linear fixed-component, weak-nonlinearity, detuned target velocity, shuffled frequency, too-short, too-lossy, phase-mismatched, target-extraction-only/no-nonlinearity, nonlinearity-only/no-extraction, and a separated direct 50+100 MHz ceiling reference.

Standalone result:

- All 26 rows ran successfully under WSL `ngspice-42`: 16 discovery rows, 9 controls, and one ceiling reference.
- No `spice_electrical_412_candidate` promoted, and no `spice_electrical_412_near_miss` promoted. All discovery rows failed on low 150 MHz purity.
- Strongest overall, best plausible/aggressive-stress purity, and best clean-control bridge ratio were all `e007 hybrid_varactor_plus_magnetic_line`.
- Best row metrics: lock `0.964163`, bridge ratio `13.199504`, 150 MHz purity `0.102689`, target coherent growth `1.070849`, generated-envelope CV `0.086907`, target-envelope CV `0.184348`, max phase jump `0.676598`, near slips `0`, aggressive-but-testable stress, behavioral dependency `0.20`.
- Target extraction/rejection helped purity but did not solve it: extraction best `0.102689` versus raw-line best `0.032538`, still far below the `0.80` candidate gate.
- Pure varactor rows remained low-purity: best raw varactor purity was `0.032538`; high-Q extraction varactor rows topped out at `0.042790`.
- Step-recovery and pure magnetic proxies did not compete in this first pass; their best purity values remained near zero.
- Controls stayed dead with max leakage score `0.0`.
- Current interpretation: pure varactor NLTL should not remain the only electrical route. The next electrical refinement should focus on hybrid varactor-plus-magnetic topology and more physical nonlinear magnetic/step-recovery component models, while the acoustic demo branch remains the stronger purity path.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Convert the promoted acoustic/phononic waveguide analog into a bench-oriented nonlinear drive/readout design.
2. Refine hybrid varactor-plus-magnetic and nonlinear magnetic electrical line models before committing to PCB layout.
3. Run the expanded `harmonic_bridge_412_detuning_refine --quick --sweeps` grid when runtime is acceptable.
4. Treat the entire f->2f->3f family as first-class until 369 beats it under normalized budget scoring.
5. If staying on 369, use either a true PLL or a more physical limiter redesign; predictive timing alone did not clear jump/CV gates.
6. Add a geometry/evolve mode only after a 4x-stable 3 -> 6 -> 9 seed beats non-369 controls under the same accounting.
