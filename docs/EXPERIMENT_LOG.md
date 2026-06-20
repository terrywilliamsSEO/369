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

## Bridge Minimum Nudge

Added an explicit proportional-only correction-work test:

- Starts from `sweep_receiver_capture_8p82_to_8p9_s0p9` and the passive magnetic `stage_B_nonlinear_strength=0.84` lead.
- Tests only receiver tuning, magnetic bias, and Stage B detuning nudges.
- Keeps direct 6/9 drive and target-frequency injection out of discovery rows.
- Counts signed parameter-work in the energy budget and reports absolute correction-work fraction, RMS, and peak correction.
- Includes no-nudge, wrong-sign, random, and non-369 bridge controls.

## Bridge Lock Threshold

Added a minimum-correction threshold search:

- Starts from the best raw `bridge_min_nudge` actuator rows and `sweep_receiver_capture_8p82_to_8p9_s0p9`.
- Sweeps actuator type, Kp, clamp, smoothing, update interval, receiver tuning, phase bias, and Stage B nonlinear strength.
- Uses only receiver tuning, magnetic bias, and Stage B detuning corrections.
- Keeps direct 6/9 drive and 9-frequency injection out of discovery rows.
- Reports minimum Kp/work for 4x lock, explicit correction work, controls, and half/quarter-dt preservation.

## Bridge Control Authority

Added an open-loop actuator-authority test:

- Starts from the best `bridge_min_nudge` receiver, magnetic, and Stage B rows plus the autolock seed and passive magnetic lead.
- Tests receiver tuning, magnetic bias, and Stage B detuning with negative/positive/medium/large steps, slow ramps, and hold-after-ramp cases.
- Measures generated-frequency pull, phase-drift pull, actuator gain, required correction to cancel drift, correction-work fraction, and authority margin.
- Keeps direct 6/9 drive and target-frequency injection out of discovery rows and includes no-correction, wrong-sign, random, and non-369 controls.
- Quick smoke found measurable pull but no promotion: best Stage B detuning row reduced 4x drift by about 5.7%, below the 50% gate.

## Bridge Drift Feedforward

Added a fixed-ramp feedforward test:

- Runs a no-feedforward 4x baseline for each seed, measures signed phase drift, then applies a precomputed ramp using prior actuator gains.
- Tests only receiver tuning, Stage B detuning, and magnetic bias ramps.
- Uses no PLL, no live feedback, no direct 6/9 drive, and no target-frequency injection.
- Includes linear, piecewise-linear, S-curve, hold-after-capture, and two-stage ramps plus wrong-sign, random, overcorrected, and non-369 controls.
- Quick smoke did not promote: best row was `magnetic_bias_ramp` with phase_lock_9 0.780, feedforward work fraction 0.0000083, and only about 0.14% drift reduction.
- A non-369 control reached phase_lock_9 0.996 under the same feedforward rules, so fixed feedforward does not currently support promotion.

## Bridge Phase Servo

Added a PI phase-servo test:

- Uses proportional plus small integral feedback: `correction = -Kp * phase_error_9 - Ki * integral_phase_error_9`.
- Moves only receiver tuning, Stage B detuning, or magnetic bias; no direct 6/9 drive and no injected 9-frequency reference.
- Compares 3 -> 6 -> 9 against 4 -> 8 -> 12 and 5 -> 10 -> 15 under the same servo rules.
- Includes no-servo, wrong-sign, and random-servo controls plus half/quarter-dt validation for top rows.
- Quick smoke did not promote: best 3 -> 6 -> 9 row used `receiver_tuning_servo`, reached phase_lock_target 0.808, and used servo work fraction 0.000492.
- Non-369 controls reached phase_lock_target 0.994-0.996 but failed energy-budget gates, so no family passed the full 4x promotion gate.

## Bridge Emergent Lock

Added a pulled-frequency diagnostic track:

- Uses the clean staged bridge and existing phase-servo/control-authority infrastructure to ask whether nominal 4x phase failure is actually stable lock to a nearby effective target.
- Compares 3 -> 6 -> 9, 4 -> 8 -> 12, 5 -> 10 -> 15, and 6 -> 12 -> 18 with no-servo, receiver-tuning servo, Stage B detuning servo, and magnetic-bias servo rows.
- Reports nominal phase lock, fitted effective target frequency, emergent phase lock at that fitted frequency, detuning delta/drift/reproducibility, bridge ratio, spectral purity, strict budget error, and servo work fraction.
- Keeps direct 2f/3f drive and target-frequency injection out of generated bridge rows.
- Quick smoke found a reproducible 3 -> 6 -> 9 fitted target near 9.0225, but emergent phase lock only reached about 0.733, below the 0.90 gate.
- No `harmonic_bridge_candidate`, `pulled_frequency_discovery`, or `369_unique_candidate` label passed. The current read is a small pulled component plus continuing phase drift, not a stable emergent-frequency lock.

## Bridge Phase Slip Audit

Added a diagnostic-only phase-slip audit:

- Starts from the best 369 emergent-lock seed, `feedforward_best_magnetic_bias`, with the pulled target near 9.0226.
- Compares 3 -> 6 -> 9, 4 -> 8 -> 12, and 5 -> 10 -> 15 under no-servo, receiver-tuning servo, Stage B detuning servo, and magnetic-bias servo rows.
- Tracks generated-2f phase error, target-3f phase error, unwrapped target phase, instantaneous drift, fitted target, amplitude envelopes, bridge ratio, spectral purity, correction lag, damping loss, spark loss, and budget error.
- Detects slip events and classifies failures as smooth drift, discrete slips, amplitude-phase coupling, generated-stage instability, servo lag, budget artifact, or bridge collapse.
- Quick smoke found the 369 bridge loses lock by discrete phase slips: best row had 4 slips, max phase jump about 3.11 radians, bridge ratio 3.226, purity 0.929, and budget error 0.00109.
- Generated 6 destabilized before target lock loss, and the servo correction lagged the slip timing. Non-369 high-lock controls were budget-breaking.
- Current next fix: generated-6 stabilization before geometry/evolve or stronger target servo.

## Bridge Generated Stage Stabilizer

Added a generated-2f-first stabilizer mode:

- Starts from the best phase-slip audit seed: 3 -> 6 -> 9, `feedforward_best_magnetic_bias`, `stage_B_detuning_servo`, pulled target near 9.0226.
- Tests generated-stage damping/Q, Stage A tuning around 2f, A->B/B->target coupling asymmetry, passive saturable limiting, lossy/hysteretic magnetic damping, predictive slip guard, and an artificial-envelope ceiling reference.
- Keeps direct 2f/3f drive and target-frequency injection out of discovery rows, includes 4 -> 8 -> 12 and 5 -> 10 -> 15 controls in every ranking, and counts stabilizer work explicitly.
- Quick smoke did not promote. The best strict-budget row was generated-stage damping: target lock 0.825, slips 2, generated-envelope CV 0.559, bridge ratio 3.166, purity 0.952, budget error 0.000921.
- Raw Stage A tuning eliminated target slips, but failed the energy budget with error 0.0127, so it is only evidence that generated-stage control is causal.
- Current next fix: keep searching budget-clean generated-stage damping/tuning before moving to geometry/evolve or full predictive PLL.

## Bridge Stage A Budget Audit

Added a Stage A budget-isolation diagnostic:

- Starts from the best generated-stage stabilizer seed and treats raw `stage_A_tuning / tune_plus_0p03` as a reference/control, not a discovery row.
- Tests static Stage A tuning from t=0, Stage A offsets from +0.005 to +0.05, the same static tuning with no servo, drive-delayed initialization, pre-drive adiabatic ramps, work-counted in-drive ramps, damping/Q compensation, A->B coupling reduction, passive soft limiting, and a passive auxiliary 2f absorber branch proxy.
- Keeps direct 2f/3f drive and target-frequency injection out of discovery rows, keeps 4 -> 8 -> 12 and 5 -> 10 -> 15 controls in every ranking, and reports parameter-work plus budget error before/during/after drive.
- Quick smoke did not promote. Static `+0.03` removed target slips, but failed budget with error 0.0118.
- Static `+0.03` with no servo also failed budget, with error 0.0137 and zero parameter work, so the budget failure is in the final tuned configuration itself, not just dynamic retuning work.
- Best near miss was damping/Q compensation: target lock 0.915, slips 0, bridge ratio 3.397, purity 0.969, work fraction 0.000106, but budget error 0.00786.
- Current next fix: run full generated-stage/passive compensation sweeps around the slip-free Stage A basin before geometry/evolve or predictive PLL.

## Bridge Stage A Budget Forensics

Added a forensics-and-narrow-search mode:

- Part A isolates Stage A `+0.03` and tune+damping rows under no-drive/no-servo subsystem accounting: no damping, damping only, nonlinear only, spark only, magnetic only, drive-only, drive+damping, drive+nonlinear, and full model.
- Part B searches a narrow compensation grid around Stage A offset, generated-stage damping/Q, A->B coupling reduction, Stage B detuning, and weak passive limiter strength.
- Reports relative and absolute budget error, budget growth, stored energy delta, drive work, damping/spark/magnetic loss, nonlinear potential delta, target lock/slips, generated-envelope CV, bridge ratio, purity, and direct-drive contamination flags.
- Quick smoke found no-drive/no-servo relative budget errors are tiny-denominator artifacts: worst no-drive relative error reached 1, but worst absolute error was only about 1.2e-9.
- Gate-relevant budget error appears in driven full-model rows and is strongly dt-sensitive: Stage A `+0.03` full model went from 0.0137 at baseline dt to 0.000092 at half-dt and 0.0000075 at quarter-dt.
- A budget-clean zero-slip 369 row was found, but it did not promote: lock 0.834, max jump 2.30 rad, generated-envelope CV 0.553, budget 0.000422.
- Current next fix: repair/refine driven nonlinear+damping ledger accounting, then rerun compensation search at refined dt before full sweeps, predictive servo timing, or geometry/evolve.

## Bridge Stage A Refined Basin

Added a focused refined-dt basin-map mode:

- Starts from the Stage A `+0.03`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04` lead from budget forensics.
- Runs primary rows at half-dt by default and validates top 369 rows at baseline dt, half-dt, and quarter-dt.
- Quick mode uses a lead-centered subset; `--quick --sweeps` expands to the full requested 3,600-row narrow grid across 3 -> 6 -> 9, 4 -> 8 -> 12, and 5 -> 10 -> 15.
- Reports phase lock, bridge ratio, spectral purity, relative/absolute budget error, budget convergence, generated/target envelope CV, max phase jump, near slips over 1 rad, and direct-drive flags.
- Quick smoke preserved budget cleanliness in the Stage A `+0.03` lead: budget error 0.00147 and absolute budget error 0.0000724 at half-dt.
- No 369 row promoted: best lock was 0.864, best generated-envelope CV was 0.528, best max phase jump was 2.36 rad, and top rows still had 22-24 near slips.
- A 5 -> 10 -> 15 control became budget-clean and stronger by normalized score, though it failed promotion by bridge ratio.
- Current next fix: limiter redesign plus predictive servo timing before full sweeps or geometry/evolve.
