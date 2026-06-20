# Tesla 3-6-9 Lab

This project turns the Tesla 3/6/9 myth into testable simulations.

Important framing: the famous "3, 6, 9 key to the universe" quote is not treated as verified history. The scientific version of the idea is that integer-ratio harmonic triads and phase geometry may create unusual energy transfer, nonlinear mixing, or localization. The scripts test that against controls.

## What it runs

1. **Triad resonator simulation**
   - Coupled nonlinear oscillators with frequencies such as 3-6-9.
   - Tests whether the high mode gets pumped when `f1 + f2 = f3`.
   - Controls include 3-6.25-9, 3-5-7, 4-8-12, and random frequencies.

2. **2D nonlinear wave lattice**
   - A finite-difference wave field with a central soft cavity and stiff ring.
   - Drives three concentric rings at 3/6/9 or control frequencies.
   - Measures central energy localization, retention, and sum-frequency content.

3. **Tesla-style receiver coil simulation**
   - Three coupled LC-like oscillators: primary coil, secondary coil, and receiver coil.
   - Adds a secondary varactor-like nonlinearity plus a smooth spark-gap transfer path.
   - Tests a clean two-tone `3 + 6 -> 9` receiver pump, a phase-coded 3/6/9 drive, detuned/non-sum controls, a 4/8/12 harmonic control, and a normal single-frequency resonant transfer control.
   - Measures receiver gain, sustained receiver energy, phase lock, ringdown retention, estimated Q factor, and sum-frequency pickup.

4. **Silent 9 receiver simulation**
   - Receiver is tuned to 9, but the target case drives only 3 and 6.
   - Direct 9 drive appears only in `normal_resonant_single_9`, which is treated as a ceiling/reference rather than the discovery winner.
   - Core controls test nonlinear vs linear conversion, detuning, non-369 sum pairs such as 4+5 and 2+7, and random non-sum input.
   - `--sweeps` adds one-parameter sweeps for nonlinearity, spark threshold, varactor strength, coupling, detuning, phase offset, drive amplitude, damping/Q, and coil-ratio assumptions.

5. **Atlas sum-frequency map**
   - Scans targets 6, 9, 12, 15, 18, and 24.
   - Generates every positive integer pump pair where `f1 + f2 = target`.
   - Compares nonlinear conversion against linear, detuned, random non-sum, and direct-resonance ceiling controls.
   - `--sweeps` explores the best pair per target across phase offset, nonlinear strength, spark threshold, varactor strength, coupling, detuning, and damping/Q.

6. **Cascade ladder simulation**
   - Tests whether a low-frequency seed can bootstrap higher modes through `3+3->6`, `3+6->9`, `6+9->15`, and `9+15->24`.
   - Includes linear, detuned, non-369, random, and direct-resonance ceiling controls.
   - `--sweeps` explores nonlinear strength, spark threshold, varactor strength, coupling, damping/Q, detuning, phase references, and runtime length.

7. **Clean passive validation harness**
   - `validate` now uses the passive energy-clean model by default.
   - Reruns top atlas/cascade candidates and references under half timestep, longer runtime, alternate FFT window, alternate seeds, lower nonlinearity, detuning, linear controls, random controls, input-work audits, and energy-budget checks.
   - Discovery ranking hard-gates relative energy-budget error and excludes direct resonance ceilings from winning.

8. **Energy audit**
   - Reruns cascade and atlas candidates with per-timestep energy ledgers.
   - Compares legacy nonconservative mixing against a passive nonlinear potential and passive spark-loss model.
   - Supports targeted audits with `--case cascade_full_ladder`, `--case atlas_3_plus_3_to_6`, or `--case atlas_4_plus_5_to_9`.

9. **Clean passive optimization**
   - Sweeps energy-clean candidates over nonlinear strength, spark threshold, varactor coefficient, coupling, damping/Q, and receiver detuning.
   - Writes a clean optimized candidate ranking with direct resonance still treated only as a ceiling/reference.

10. **Bridge amplification**
   - Uses only the clean passive model to optimize a staged `3 -> generated 6 -> 9` bridge.
   - Stage A generates 6 from a 3-only drive; Stage B mixes original 3 with generated 6 into a receiver tuned to 9.
   - Compares against direct 3+6, direct 6, direct 9 ceiling, linear/detuned/random controls, and non-369 staged bridges such as 4->8->12 and 5->10->15.
   - `--sweeps` explores stage nonlinear strengths, stage tuning, damping/Q, coupling asymmetry, phase relationship, runtime, and passive spark threshold.

11. **Bridge stability**
   - Starts from the optimized bridge amplification candidate with `stage_B_nonlinear_strength=0.9`.
   - Searches for full-run configurations that keep bridge ratio high while improving `phase_lock_9`.
   - Validates top candidates with half timestep and longer-runtime checks before promotion.
   - `--sweeps` explores Stage B strength/damping/Q, receiver detuning, coupling asymmetry, phase bias, spark threshold, FFT window, and runtime length.

12. **Bridge phase-lock diagnostics**
   - Starts from the near-pass bridge candidate with `stage_B_nonlinear_strength=0.9` and `phase_bias=30`.
   - Adds sliding-window phase, instantaneous-frequency, drift-rate, lock-duration, spectral-purity, and bridge-ratio diagnostics.
   - `--sweeps` maps receiver detuning, Stage B detuning/nonlinearity, phase bias, damping/Q, coupling, spark threshold, FFT windows, runtime, and Arnold tongue lock islands.

13. **Bridge lock refinement**
   - Starts from the promoted passive lock island at `receiver_detuning=8.9`, `phase_bias=30`, and `stage_B_nonlinear_strength=0.9`.
   - Fine-maps receiver tuning, phase bias, Stage B strength, coupling, damping, spark threshold, FFT windows, and 1x/2x/4x runtime behavior.
   - Validates top candidates with half-dt, quarter-dt, repeatability seeds, and longer-runtime checks.

14. **Magnetic bridge stabilization**
   - Adds a passive magnetic-flux coupling layer to the clean staged `3 -> generated 6 -> 9` bridge.
   - Tracks derived flux, effective inductance, magnetic energy, leakage, hysteresis, eddy loss, magnetic work, and coupling exchange.
   - Tests whether air-core, saturable, biased, lossy, rotating-bias, random, and non-369 magnetic controls reduce long-runtime phase drift.

15. **Magnetic autolock**
   - Tests passive and semi-passive phase-capture mechanisms before moving to full active PLL.
   - Adds open-loop receiver/magnetic-bias/Stage-B sweeps, passive hybrid magnetic branch tuning, and ultraweak counted injection locking.
   - Keeps direct 6 and direct 9 out of generated bridge cases, forces direct references to discovery score 0, and penalizes active work.
   - Validates top candidates with 1x/2x/4x runtime plus half-dt and quarter-dt checks.

16. **Bridge minimum nudge**
   - Starts from `sweep_receiver_capture_8p82_to_8p9_s0p9` and the passive magnetic `stage_B_nonlinear_strength=0.84` lead.
   - Tests only receiver tuning, magnetic bias, and Stage B detuning nudges using proportional-only phase feedback.
   - Keeps direct 6/9 drive and target-frequency injection out of discovery tests.
   - Reports passive energy accounting plus explicit correction-work, wrong-sign/random/no-nudge controls, non-369 controls, and half/quarter-dt validation.

17. **Bridge lock threshold**
   - Starts from the best raw `bridge_min_nudge` rows plus the best magnetic/autolock seed.
   - Sweeps actuator type, Kp, clamp, smoothing, update interval, receiver tuning, phase bias, and Stage B nonlinear strength.
   - Uses only receiver tuning, magnetic bias, and Stage B detuning nudges; no direct 6/9 drive and no 9-frequency injection.
   - Reports the minimum Kp/work needed for 4x lock, explicit correction work, controls, and half/quarter-dt preservation checks.

18. **Bridge control authority**
   - Measures open-loop actuator authority for long-runtime 4x phase drift in the clean staged bridge.
   - Tests only receiver tuning, magnetic bias, and Stage B detuning actuators with stepped, ramped, wrong-sign, random, and no-correction controls.
   - Computes drift-rate pull, effective generated frequency pull, required correction to cancel drift, estimated correction work, and authority margin.
   - Keeps direct 6/9 drive and target-frequency injection out of discovery tests while preserving clean energy accounting.

19. **Bridge drift feedforward**
   - Measures no-feedforward 4x drift, then applies precomputed tuning ramps without PLL or live feedback.
   - Uses only receiver tuning, Stage B detuning, and magnetic bias ramps.
   - Tests linear, piecewise-linear, slow S-curve, hold-after-capture, and two-stage ramps with wrong-sign, random, overcorrected, and non-369 controls.
   - Reports feedforward work fraction, ramp size/smoothness, before/after drift, generated-frequency pull, lock duration, and dt preservation.

20. **Bridge phase servo**
   - Tests proportional plus small integral feedback through physical tuning/bias actuators only.
   - Uses receiver tuning, Stage B detuning, and magnetic bias servos; no direct 6/9 drive and no injected 9-frequency reference.
   - Compares 3->6->9 against 4->8->12 and 5->10->15, plus no-servo, wrong-sign, and random-servo controls.
   - Reports target-family phase lock, target spectral purity, servo work, correction RMS/peak, phase drift, lock duration, and half/quarter-dt preservation.

21. **Bridge emergent lock**
   - Diagnoses whether long-runtime nominal phase failure is actually stable lock to a pulled local target frequency.
   - Uses the clean staged bridge, direct-reference cache, phase diagnostics, and the phase-servo/control-authority actuator infrastructure.
   - Compares 3->6->9 against 4->8->12, 5->10->15, and 6->12->18 under no-servo, receiver-tuning, Stage B detuning, and magnetic-bias servo cases.
   - Keeps direct 2f/3f drive and target-frequency injection out of discovery rows while reporting nominal lock, fitted effective target, emergent lock, detuning drift, work, budget, and dt/seed reproducibility.

22. **Bridge phase-slip audit**
   - Diagnoses why the high-ratio, high-purity pulled-target bridge still fails phase lock.
   - Compares 3->6->9 against 4->8->12 and 5->10->15 under no-servo plus receiver-tuning, Stage B detuning, and magnetic-bias servos.
   - Tracks sliding-window generated-2f phase error, target-3f phase error, unwrapped target phase, instantaneous drift, fitted target, amplitude envelopes, bridge ratio, spectral purity, correction lag, damping loss, spark loss, and energy-budget error.
   - Detects phase-slip events and classifies failure as smooth drift, discrete slips, amplitude-phase coupling, generated-stage instability, servo lag, budget artifact, or bridge collapse.

## Install

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

Fast smoke test:

```bash
python tesla_369_lab.py --mode all --quick
```

Full default run:

```bash
python tesla_369_lab.py --mode all
```

Individual experiments:

```bash
python tesla_369_lab.py --mode triad
python tesla_369_lab.py --mode wave
python tesla_369_lab.py --mode receiver
python tesla_369_lab.py --mode silent9
python tesla_369_lab.py --mode silent9 --sweeps
python tesla_369_lab.py --mode atlas --quick
python tesla_369_lab.py --mode atlas --quick --sweeps
python tesla_369_lab.py --mode cascade --quick
python tesla_369_lab.py --mode cascade --quick --sweeps
python tesla_369_lab.py --mode validate
python tesla_369_lab.py --mode validate --energy-clean
python tesla_369_lab.py --mode clean_validate --quick
python tesla_369_lab.py --mode clean_optimize --quick
python tesla_369_lab.py --mode bridge_amp --quick
python tesla_369_lab.py --mode bridge_amp --quick --sweeps
python tesla_369_lab.py --mode bridge_stability --quick
python tesla_369_lab.py --mode bridge_stability --sweeps
python tesla_369_lab.py --mode bridge_phase_lock
python tesla_369_lab.py --mode bridge_phase_lock --quick
python tesla_369_lab.py --mode bridge_phase_lock --sweeps
python tesla_369_lab.py --mode bridge_phase_lock --quick --sweeps
python tesla_369_lab.py --mode bridge_lock_refine
python tesla_369_lab.py --mode bridge_lock_refine --quick
python tesla_369_lab.py --mode bridge_lock_refine --sweeps
python tesla_369_lab.py --mode bridge_lock_refine --quick --sweeps
python tesla_369_lab.py --mode magnetic_bridge
python tesla_369_lab.py --mode magnetic_bridge --quick
python tesla_369_lab.py --mode magnetic_bridge --sweeps
python tesla_369_lab.py --mode magnetic_bridge --quick --sweeps
python tesla_369_lab.py --mode magnetic_autolock
python tesla_369_lab.py --mode magnetic_autolock --quick
python tesla_369_lab.py --mode magnetic_autolock --sweeps
python tesla_369_lab.py --mode magnetic_autolock --quick --sweeps
python tesla_369_lab.py --mode bridge_min_nudge
python tesla_369_lab.py --mode bridge_min_nudge --quick
python tesla_369_lab.py --mode bridge_min_nudge --sweeps
python tesla_369_lab.py --mode bridge_min_nudge --quick --sweeps
python tesla_369_lab.py --mode bridge_lock_threshold
python tesla_369_lab.py --mode bridge_lock_threshold --quick
python tesla_369_lab.py --mode bridge_lock_threshold --sweeps
python tesla_369_lab.py --mode bridge_lock_threshold --quick --sweeps
python tesla_369_lab.py --mode bridge_control_authority
python tesla_369_lab.py --mode bridge_control_authority --quick
python tesla_369_lab.py --mode bridge_control_authority --sweeps
python tesla_369_lab.py --mode bridge_control_authority --quick --sweeps
python tesla_369_lab.py --mode bridge_drift_feedforward
python tesla_369_lab.py --mode bridge_drift_feedforward --quick
python tesla_369_lab.py --mode bridge_drift_feedforward --sweeps
python tesla_369_lab.py --mode bridge_drift_feedforward --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_servo
python tesla_369_lab.py --mode bridge_phase_servo --quick
python tesla_369_lab.py --mode bridge_phase_servo --sweeps
python tesla_369_lab.py --mode bridge_phase_servo --quick --sweeps
python tesla_369_lab.py --mode bridge_emergent_lock
python tesla_369_lab.py --mode bridge_emergent_lock --quick
python tesla_369_lab.py --mode bridge_emergent_lock --sweeps
python tesla_369_lab.py --mode bridge_emergent_lock --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_slip_audit
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick
python tesla_369_lab.py --mode bridge_phase_slip_audit --sweeps
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick --sweeps
python tesla_369_lab.py --mode energy_audit --quick
python tesla_369_lab.py --mode energy_audit --case cascade_full_ladder
```

Quick receiver runs write CSV/report output only so they stay fast. Full receiver runs also write energy and spectrum PNG diagnostics. Silent-9 writes its core cases by default; add `--sweeps` to write `silent_9_receiver_sweeps.csv`. Atlas writes the core map by default; add `--sweeps` to write phase-lock and parameter-sweep atlas outputs.

## Read the output

After running, open:

```text
runs/tesla_369_<timestamp>/README_RUN_REPORT.md
runs/tesla_369_<timestamp>/summary.csv
```

Experiment-specific CSV files are also written:

```text
triad_resonator_summary.csv
wave_lattice_summary.csv
receiver_coil_summary.csv
silent_9_receiver_summary.csv
silent_9_receiver_sweeps.csv
atlas_summary.csv
atlas_ranked_discoveries.csv
per_target_pair_heatmap.csv
phase_lock_islands.csv
cascade_summary.csv
cascade_ranked_discoveries.csv
cascade_stage_energy_over_time.csv
cascade_frequency_ladder.csv
validation_summary.csv
validation_pass_fail.csv
clean_validation_summary.csv
clean_validation_pass_fail.csv
clean_candidate_comparison.csv
generated_vs_direct_bridge.csv
clean_optimized_candidates.csv
bridge_amp_summary.csv
bridge_amp_ranked.csv
bridge_amp_sweeps.csv
bridge_stage_energy_timeseries.csv
bridge_stability_summary.csv
bridge_stability_ranked.csv
bridge_stability_sweeps.csv
bridge_full_run_validation.csv
bridge_phase_lock_summary.csv
bridge_phase_lock_ranked.csv
bridge_phase_drift_timeseries.csv
bridge_lock_islands.csv
bridge_arnold_tongue_map.csv
bridge_lock_refine_summary.csv
bridge_lock_refine_ranked.csv
bridge_lock_island_map.csv
bridge_lock_robustness.csv
bridge_lock_validation.csv
magnetic_bridge_summary.csv
magnetic_bridge_ranked.csv
magnetic_bridge_sweeps.csv
magnetic_energy_ledger.csv
magnetic_phase_drift_timeseries.csv
magnetic_lock_islands.csv
magnetic_vs_nonmagnetic_comparison.csv
magnetic_autolock_summary.csv
magnetic_autolock_ranked.csv
magnetic_autolock_sweeps.csv
magnetic_autolock_energy_ledger.csv
magnetic_autolock_phase_timeseries.csv
magnetic_autolock_capture_report.csv
magnetic_autolock_controls.csv
bridge_min_nudge_summary.csv
bridge_min_nudge_ranked.csv
bridge_min_nudge_timeseries.csv
bridge_lock_threshold_summary.csv
bridge_lock_threshold_ranked.csv
bridge_lock_threshold_sweeps.csv
bridge_lock_threshold_timeseries.csv
bridge_control_authority_summary.csv
bridge_control_authority_ranked.csv
bridge_control_authority_sweeps.csv
bridge_control_authority_timeseries.csv
bridge_drift_feedforward_summary.csv
bridge_drift_feedforward_ranked.csv
bridge_drift_feedforward_sweeps.csv
bridge_drift_feedforward_timeseries.csv
bridge_phase_servo_summary.csv
bridge_phase_servo_ranked.csv
bridge_phase_servo_sweeps.csv
bridge_phase_servo_timeseries.csv
bridge_emergent_lock_summary.csv
bridge_emergent_lock_ranked.csv
bridge_emergent_lock_timeseries.csv
bridge_phase_slip_audit_summary.csv
bridge_phase_slip_audit_ranked.csv
bridge_phase_slip_audit_timeseries.csv
energy_audit_summary.csv
energy_ledger_timeseries.csv
component_budget_breakdown.csv
energy_audit_pass_fail.csv
```

The key question is not "did 369 look cool?" The key questions are:

- Does 369 beat non-369 controls?
- Does it reproduce across seeds?
- Does it survive detuning, grid-size changes, and time-step changes?
- Does 4-8-12 behave similarly? If yes, the effect is probably general nonlinear resonance, not special numerology.
- Does ordinary single-frequency resonant tuning beat phase-coded transfer in the receiver-coil model?
- In the silent-9 test, does 3+6 produce more receiver energy at 9 than its linear and detuned twins under equal input work?
- In the atlas, does 3+6->9 remain special when compared against every other integer sum pair and multiple targets?
- In cascade mode, does generated 6 actually feed later stages without direct 6 or 9 injection?
- In clean validate mode, do the best candidates survive artifact-killer controls under passive energy accounting?
- In bridge amp mode, can generated 6 replace direct 6 well enough to feed 9 under clean passive accounting?
- In bridge stability mode, does that bridge stay phase-locked under full runtime, half-dt, and longer-runtime checks?
- In bridge phase-lock mode, is the long-runtime failure phase drift, detuning, beating, coupling loss, damping, or an FFT/window artifact?
- In bridge lock refine mode, is the passive lock island broad enough to promote to geometry369?
- In magnetic bridge mode, can passive flux coupling stabilize 2x/4x runtime without hidden energy injection?
- In magnetic autolock mode, can open-loop capture, passive hybrid tuning, or tiny counted injection survive 4x without becoming hidden feedback?
- In bridge minimum nudge mode, can an explicitly accounted tiny tuning correction stabilize 4x lock without overpowering the passive bridge?
- In bridge lock threshold mode, what is the minimum explicitly accounted correction needed for 4x lock, if any?
- In bridge emergent lock mode, is nominal 4x phase failure actually a stable pulled-frequency lock, and does 3->6->9 still beat non-369 controls after normalization?
- In bridge phase-slip audit mode, does target lock fail by smooth drift, discrete slips, generated-6 instability, servo lag, amplitude breathing, or budget artifacts?
- In energy-audit mode, does the effect survive after enforcing passive energy accounting?

## How to interpret receiver results

- If `normal_resonant_single_6` wins, plain resonant tuning is stronger than phase coding in this toy model.
- If `369_two_tone_sum_pump` beats `369_linear_no_gap`, the nonlinear spark/varactor path is doing real work.
- If `369_phase_coded` beats `369_random_phase`, phase geometry may matter.
- If `369_detuned_mid`, `357_non_sum`, or random controls beat the exact 369 cases, the 369 hypothesis is weak for this model.

## How to interpret silent-9 results

- `3_plus_6_to_9_nonlinear` vs `3_plus_6_to_9_linear` tests whether the nonlinear element is doing useful conversion.
- `3_plus_6_to_9_nonlinear` vs `3_plus_6p25_to_9_nonlinear` tests whether exact sum-frequency locking matters.
- `3_plus_6_to_9_nonlinear` vs `4_plus_5_to_9_nonlinear` and `2_plus_7_to_9_nonlinear` tests whether 3+6 is special or whether any exact pair summing to 9 works.
- `normal_resonant_single_9` is the direct-drive ceiling, not the discovery result.

## Best next mutations

- Sweep phase offsets around 0, 120, and 240 degrees.
- Sweep central defect radius and stiffness in the wave lattice.
- Sweep coil coupling, damping, receiver distance, drive amplitude, and spark threshold.
- Replace the receiver toy model with an explicit mutual-inductance LC system.
- Add seed sweeps and confidence intervals for every score.
- Add FFT-based anomaly detection across every wave-grid cell.
