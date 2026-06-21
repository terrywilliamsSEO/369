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

## Bridge Limiter Predictive Servo

Added a limiter/predictive-servo mode:

- Starts from the refined Stage A basin lead: Stage A offset `+0.030`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`.
- Track A tests passive limiter redesign only: existing limiter, soft/tanh/cubic-quintic/coupling saturation, adaptive generated damping, envelope-derivative damping, and energy-bucket limiting.
- Track B tests predictive servo timing only with receiver tuning, Stage B detuning, and magnetic bias actuators.
- Track C combines limiter candidates with predictive servo timing.
- Tracks generated and target envelope CV, max phase jump, near-slip count, phase-slip count, bridge ratio, purity, strict budget, limiter work, servo work, trigger count, lead time, and no-direct-drive flags.
- Quick smoke found high-lock, budget-clean 369 damping rows, but no promotion: best 369 CV was 0.274 and best max jump was 1.744 rad.
- The best high-lock 369 row, passive `adaptive_generated_damping`, reached lock 0.968 at half-dt primary and preserved lock at half/quarter validation, but CV and phase jumps stayed above gate.
- Predictive servo timing measured lead time before jumps but did not reduce max jump below 1.0 rad.
- A 5 -> 10 -> 15 control stayed stronger by normalized budget score, so this run argues for a general harmonic-bridge study before geometry/evolve.

## Harmonic Bridge Family

Added a harmonic family mode:

- Compares 2->4->6, 3->6->9, 4->8->12, 5->10->15, 6->12->18, 7->14->21, and 8->16->24.
- Runs passive baseline, refined Stage A basin equivalent, adaptive generated damping, envelope-derivative damping, energy-bucket limiting, and an optional active PLL comparator proxy.
- Keeps direct 2f/3f drive and target-frequency injection out of passive discovery rows; active PLL rows are marked `active_control` and scored separately.
- Reports lock, bridge ratio, purity, relative/absolute budget error, generated/target envelope CV, max phase jump, near slips, limiter/servo work, normalized family score, and dt validation.
- Quick smoke ran 42 core rows plus baseline/half/quarter-dt validation for top family rows. `--quick --sweeps` expands the grid to 91 rows before validation.
- Strongest passive normalized family was 5 -> 10 -> 15 passive baseline: lock 0.994, purity 0.999, budget 0.000749, generated-envelope CV 0.057, max jump 0.807, score 0.328. It failed promotion because bridge ratio was 1.122, below the 1.5 gate.
- 3 -> 6 -> 9 did not beat 5 -> 10 -> 15. Its best normalized row was passive baseline with lock 0.735, generated-envelope CV 0.582, max jump 3.05 rad, and 21 near slips.
- 4 -> 8 -> 12 came closest to a harmonic candidate: refined Stage A equivalent had lock 0.984, bridge ratio 1.929, purity 0.992, budget 0.00185, generated-envelope CV 0.126, and max jump 1.05 rad, but did not preserve the result across all dt checks.
- No family passed `harmonic_bridge_candidate`, no family passed strict, and no `general_harmonic_bridge_law` label passed.
- Current next fix: family-law mapping before geometry/evolve or 369-specific PLL.

## Harmonic Bridge Dt Rescue

Added a dt-rescue mode for the 4 -> 8 -> 12 near miss:

- Starts from the best 4 -> 8 -> 12 refined Stage A equivalent from `harmonic_bridge_family`.
- Runs every candidate at baseline dt, half dt, and quarter dt.
- Ranks aggregate rows using worst-case all-dt lock, bridge ratio, purity, budget, generated/target envelope CV, max jump, and near-slip metrics.
- Varies Stage A offset, generated damping factor, A->B coupling, limiter strength, target detuning, Stage B detuning, and diagnostic-only phase-analysis windows.
- Includes 3 -> 6 -> 9 and 5 -> 10 -> 15 comparison rows under the same all-dt scoring.
- Quick smoke found a strong 4 -> 8 -> 12 target-detuned row (`target_detuning=-0.08`) that satisfied all strict non-budget metrics at all dt levels: lock about 0.985, bridge ratio about 1.875, purity about 0.992, generated-envelope CV below 0.139, max jump below 0.999 rad, and near slips 0.
- That row did not promote because the budget gate failed at baseline dt and barely missed at half-dt: baseline budget 0.04485, half-dt 0.005006, quarter-dt 0.000628.
- No 4 -> 8 -> 12 row passed `harmonic_bridge_candidate` or strict because all-dt budget cleanliness was not achieved.
- After bridge-ratio gating, 4 -> 8 -> 12 beat 5 -> 10 -> 15. 3 -> 6 -> 9 remained behind 4 -> 8 -> 12, but not behind 5 -> 10 -> 15 after budget/bridge-ratio normalization.
- Current next fix: 4 -> 8 -> 12 budget-ledger refinement, then a tighter target-detuning sweep.

## Harmonic Bridge Budget Ledger

Added a budget-ledger diagnostic for the 4 -> 8 -> 12 target-detuned near miss:

- Starts from the dt-rescue primary row: family 4 -> 8 -> 12, target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`.
- Compares against 3 -> 6 -> 9, 5 -> 10 -> 15, no-drive/no-servo, drive-only, damping-only, nonlinear-only, limiter-only, and full-model 4 -> 8 -> 12 rows.
- Runs baseline dt, half dt, quarter dt, and optional eighth dt in sweep mode.
- Reports stored energy, drive work, positive input work, damping/spark/magnetic loss, limiter/adaptive work, nonlinear-potential delta, residual per time/work, residual scaling, and convergence order.
- Adds left-endpoint, midpoint/trapezoid, RK-loop cumulative, finite-difference, component-wise, and diagnostic magnetic-loss accounting variants.

Quick smoke result:

- Primary 4 -> 8 -> 12 non-budget metrics stayed strong across dt: lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max phase jump 0.998 rad, near slips 0.
- Existing ledger residual converged away with dt: budget error 0.04490 at baseline dt, 0.00498 at half-dt, 0.000605 at quarter-dt, and 0.000110 at eighth-dt; convergence order was about 3.11.
- Midpoint/trapezoid accounting did not make baseline dt clean: it remained 0.04401. Quarter-dt was clean at 0.000850 and eighth-dt dropped to 0.0000116.
- No single component matched the residual, and subtracting magnetic loss as a missing term made the ledger worse.
- Current read: classify this as numerical ledger sensitivity, not a promotion and not proven physical non-passive energy creation. Next step is independent corrected/substep quadrature, then a tighter 4 -> 8 -> 12 detuning sweep if validated.

## Harmonic Bridge Substep Quadrature

Added an independent substep audit for the 4 -> 8 -> 12 target-detuned near-candidate:

- Starts from the dt-rescue/budget-ledger primary row: target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`.
- Separates trajectory-preserving auditors from re-integrated smaller-step trajectories.
- Tests existing ledger, RK-stage-consistent accounting, sampled trapezoid/Simpson/Gauss-Legendre, finite-difference/component checks, 2/4/8/16 trajectory-preserving substep quadrature, and substep-4 re-integration.
- Keeps direct 2f/3f drive and target-frequency injection forbidden.

Quick sweeps result:

- The primary 4 -> 8 -> 12 row stayed strong: lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max phase jump 0.998 rad, and near slips 0.
- Same-trajectory quadrature did not close baseline: existing ledger 0.04493, RK-stage-consistent 0.06762, sampled 16-substep quadrature 0.382.
- Substep-4 re-integration closed the budget at all audited dt levels: baseline 0.0000511, half-dt 0.000000747, quarter-dt 0.0000000298, eighth-dt 0.00000000425.
- Substep re-integration preserved the bridge: baseline substep-4 lock 0.9917, bridge ratio 1.531, purity 0.925.
- The run marks `candidate_pending_detuning_refine=True`, `budget_residual_source=trajectory_integration_error`, and `candidate_numerically_fragile=False`.
- Current next fix: tight 4 -> 8 -> 12 target-detuning sweep plus an independent validation script/solver before any final promotion.

## Harmonic Bridge 4->8->12 Detuning Refine

Added a substep-validated detuning refinement mode:

- Starts from the substep-quadrature 4 -> 8 -> 12 candidate: target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`.
- Uses substep-4 re-integration for all primary candidate rows.
- Quick mode runs a lead-centered one-axis smoke; `--quick --sweeps` expands to the requested target-detuning crossed grid over Stage A offset, generated damping, A->B coupling, and limiter strength.
- Validates top rows at baseline, half, and quarter dt; sweep mode also adds eighth dt.
- Keeps 3 -> 6 -> 9, 5 -> 10 -> 15, 4 -> 8 -> 12 no-detuning, and direct-reference ceiling rows in the ranking.
- Discovery rows keep direct 2f drive, direct 3f drive, and target-frequency injection forbidden.

Quick smoke result:

- Best row: 4 -> 8 -> 12 with target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, limiter `0.03`.
- It passed `harmonic_bridge_candidate`, `strict_harmonic_bridge_candidate`, and `family_lead_candidate` across baseline/half/quarter dt under substep-4 accounting.
- Worst all-dt metrics: phase lock 0.992, bridge ratio 1.589, spectral purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max phase jump 0.972 rad, near slips 0.
- Nearby strict rows also appeared at Stage A `+0.045`, target detuning `-0.075`, and target detuning `-0.070`.
- 4 -> 8 -> 12 beat 3 -> 6 -> 9 and 5 -> 10 -> 15 under the same substep accounting after bridge-ratio gating.
- Current next fix: independent validation solver first, then full family-law mapping. Do not promote geometry/evolve from this mode alone.

## Independent 4->8->12 Validation

Added `independent_validate_412.py`:

- Standalone script; it does not import `tesla_369_lab.py` or call any experiment mode.
- Reimplements the explicit three-mode oscillator equations, fixed effective 4 -> 8 -> 12 candidate constants, RK4 substep integration, energy ledger, phase lock, bridge ratio, purity, envelope CV, phase-jump diagnostics, and JSON/CSV/Markdown writers.
- Candidate drive remains source-only 4. No direct 8 drive, no direct 12 drive, and no target-frequency injection are used in the discovery candidate.
- A direct 4+8 row is simulated only as a ceiling denominator for bridge ratio.
- Outputs go to `runs/independent_validate_412/independent_412_summary.json`, `independent_412_summary.csv`, `independent_412_timeseries.csv`, and `README_INDEPENDENT_412_VALIDATION.md`.

Standalone result:

- `independent_validation_passed=True` and `all_dt_passed=True` across baseline, half-dt, and quarter-dt.
- Worst all-dt metrics: lock 0.992, bridge ratio 1.607, purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max phase jump 0.972 rad, near slips 0.
- No material differences from the main harness were flagged. The bridge ratio is slightly higher than the harness report because the standalone denominator is candidate-specific.
- Current next fix: full family-law mapping and broader replication before any geometry/evolve promotion.

## Physical 4->8->12 LC Bridge

Added `physical_412_lc_bridge.py`:

- Translates the independently validated strict 4 -> 8 -> 12 candidate into a normalized but physically interpretable nonlinear LC model.
- Represents three resonators as `L1/C1/R1`, `L2/C2/R2`, and `L3/C3/R3`, computes resonant frequencies with `f = 1 / (2*pi*sqrt(LC))`, and derives Q/R from the validated damping constants.
- Includes `audio-scale`, `low-RF-scale`, and `arbitrary-normalized-scale` presets.
- Reports weak linear coupling coefficients, varactor-like nonlinear capacitance strength, nonlinear mixing, passive soft-limiter loss, joule-scale drive work, stored energy, resistive loss, limiter loss, peak voltages, and peak currents.
- Keeps discovery rows source-only: no direct 8 drive, no direct 12 drive, and no target-frequency injection. Direct 4+8 remains only a ceiling denominator.
- Outputs go to `runs/physical_412_lc_bridge/physical_412_summary.json`, `physical_412_summary.csv`, `physical_412_timeseries.csv`, and `README_PHYSICAL_412_LC_BRIDGE.md`.

Standalone result:

- `all_dt_all_scales_passed=True` across audio, low-RF, and normalized scale presets.
- Worst all-dt/all-scale metrics: lock 0.992108, bridge ratio 1.606971, purity 0.922789, budget error 0.0000510, generated-envelope CV 0.134693, target-envelope CV 0.035824, max phase jump 0.971944 rad, near slips 0.
- Audio-scale representative values: f=(440, 883.894, 1309.862) Hz, L=(13.08 mH, 6.90 mH, 4.47 mH), C=(10 uF, 4.7 uF, 3.3 uF), R=(0.912, 0.901, 0.480) ohm, Q=(39.7, 42.5, 76.8), all mild.
- Low-RF representative values: f=(1.0 MHz, 2.009 MHz, 2.977 MHz), L=(25.33 uH, 13.36 uH, 8.66 uH), C=(1 nF, 470 pF, 330 pF), R=(4.01, 3.97, 2.11) ohm, Q=(39.7, 42.5, 76.8), all mild.
- Current next fix: SPICE/ngspice validation, then physical parameter refinement and spatial phase-matching modeling.

## SPICE 4->8->12 Export

Added `spice_412_export.py`:

- Exports the physical 4 -> 8 -> 12 LC bridge into ngspice-compatible netlists for audio-scale, low-RF-scale, and normalized-scale.
- Exports a separated `reference_direct_4plus8.cir` ceiling denominator using direct 4+8 drive; it is not a discovery row.
- Adds explicit execution with `--run` and path override with `--ngspice-path`, including `--ngspice-path wsl:ngspice` for WSL installs.
- Reports per-netlist execution status: `exported`, `skipped_no_ngspice`, `ran_successfully`, `failed_to_converge`, or `parser_failed`.
- Discovery netlists drive only resonator 1/source mode and keep direct generated-mode drive, direct target-mode drive, and target-frequency injection absent.
- Circuit model includes three lossy LC resonators, Q-matched inductor-branch resistance, weak mutual inductive coupling, behavioral varactor-like capacitance, behavioral nonlinear mixing, and passive soft-limiter conductance.
- Adds nonlinear model variants: `behavioral_proxy_current`, `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, and `linear_no_nonlinearity_control`.
- If ngspice is installed, the script runs transient simulations, exports ngspice CSV/raw output, parses resonator voltages/currents, and computes target voltage growth, FFT peaks, approximate lock, bridge ratio, purity near 12, generated-envelope CV, and max phase jump.
- Outputs go to `runs/spice_412_bridge/audio_412_bridge.cir`, `low_rf_412_bridge.cir`, `normalized_412_bridge.cir`, `reference_direct_4plus8.cir`, `spice_412_summary.json`, `spice_412_summary.csv`, and `README_SPICE_412_EXPORT.md`.

Standalone result:

- Valid SPICE netlists were generated.
- WSL ngspice was installed through `wsl -u root`; `/usr/bin/ngspice` reports `ngspice-42`.
- `python spice_412_export.py --run --ngspice-path wsl:ngspice` was tested.
- Local execution status mix: `failed_to_converge;ran_successfully`, with 15 successful rows and 4 convergence failures. Failed rows reported ngspice `TRAN: Timestep too small`.
- The normalized `behavioral_proxy_current` discovery row preserved strong target behavior: lock `0.997003`, purity `0.971359`, target growth `2.06766`, max phase jump `0.274669`, but bridge ratio was only `0.788167` against the normalized direct 4+8 reference.
- Several diode/varactor/saturable rows showed target-band content near 12, but their locks were low and none roughly reproduced the full Python LC behavior.
- Linear no-nonlinearity controls failed as expected under target-band criteria: lock stayed near `0.014`, purity near `1.7e-6`, and target-node FFT peaks stayed at the source frequency.
- The nonlinear element remains classified as an aggressive behavioral varactor/mixing proxy: suitable for first ngspice validation, but not yet a physically refined component implementation.
- Current next fix: refine nonlinear components, run parameter sweeps, and add spatial phase-matching modeling.

## SPICE 4->8->12 Nonlinearity Refinement

Added `spice_412_refine_nonlinearity.py`:

- Runs a focused normalized-scale ngspice refinement sweep over nonlinear component implementations.
- Variants: `behavioral_proxy_current`, `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, `hybrid_varactor_plus_saturable_inductor`, and `linear_no_nonlinearity_control`.
- Encodes the requested axes: nonlinear strength scale, limiter/conductance scale, coupling scale, drive amplitude scale, conservative/default/relaxed solver tolerances, and max timestep scale.
- Keeps discovery rows source-only: no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- Uses separated direct 4+8 reference rows only as ceiling denominators for bridge ratio.
- Outputs go to `runs/spice_412_refine_nonlinearity/spice_412_refine_summary.json`, `spice_412_refine_summary.csv`, `spice_412_refine_timeseries.csv`, and `README_SPICE_412_REFINE_NONLINEARITY.md`.

Standalone result:

- Run command tested: `python spice_412_refine_nonlinearity.py --ngspice-path wsl:ngspice --max-discovery-cases 56`.
- 56 discovery rows were run; 36 ran successfully and 20 failed to converge with ngspice `TRAN: Timestep too small`.
- Bridge ratio >1.5 was reached by two source-only `behavioral_proxy_current` rows, `r038` and `r042`.
- Closest Python-LC behavior was `r042`: lock `0.996193`, purity `0.981658`, bridge ratio `1.563169`, target-band growth `1.276714`, generated-envelope CV `0.091533`, and max phase jump `0.289970`.
- Linear no-nonlinearity controls remained dead: maximum leakage score `0.0`, target-band growth `0`, purity near `1.7e-6`, and target FFT at the source frequency.
- No diode/varactor/saturable/hybrid component-plausible row promoted; successful rows are behavioral-only.
- Current next fix: component-level refinement to replace behavioral current mixing, then a physical parameter sweep.

## SPICE 4->8->12 Component Realism

Added `spice_412_component_realism.py`:

- Replaces behavioral current mixing in discovery rows with component-plausible nonlinear networks: anti-parallel diode, diode bridge, varactor pair, back-to-back varactor stack, saturable inductor, coupled saturable transformer, hybrid varactor+saturable, and diode+resonant trap.
- Keeps discovery rows source-only: no direct 8 drive, no direct 12 drive, and no target-frequency injection. Direct 4+8 rows remain separated ceiling references only.
- Adds controls for linear/no-nonlinearity, weak nonlinearity, detuned target, and shuffled generated/target frequencies.
- Outputs go to `runs/spice_412_component_realism/spice_412_component_realism_summary.json`, `spice_412_component_realism_summary.csv`, `spice_412_component_realism_timeseries.csv`, and `README_SPICE_412_COMPONENT_REALISM.md`.

Standalone result:

- Run command tested: `python spice_412_component_realism.py --ngspice-path wsl:ngspice --max-cases 44`.
- 40 discovery rows were evaluated; 38 ran successfully and 2 failed to converge with ngspice `TRAN: Timestep too small`.
- Six source-only component rows crossed bridge ratio >1.5: `c008`, `c013`, `c018`, `c023`, `c028`, and `c033`.
- None promoted because phase lock stayed very low. Closest component row was `c018` (`back_to_back_varactor_stack`): lock `0.016446`, purity `0.986424`, bridge ratio `1.573878`, target-band growth `0.984463`, and plausible stress.
- Linear and shuffled controls stayed dead, but weak-nonlinearity and detuned controls leaked target-band response under the current criterion; `controls_remained_dead=False`.
- Current next fix: deeper component sweep and spatial phase-matching modeling before physical parameter refinement.
