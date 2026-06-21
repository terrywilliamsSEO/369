# 369 Resonance Lab

This repo is the central source of truth for the Tesla-inspired 3/6/9 resonance experiments.

The project does **not** assume that 3/6/9 is magic. It treats 3-6-9 as a falsifiable nonlinear resonance hypothesis: can lower-frequency pumps create unusually stable, phase-locked transfer into higher modes under clean passive energy accounting?

## Current State

The strongest signal so far is a clean passive staged bridge:

```text
3-only drive -> generated 6 -> 3 + generated 6 -> receiver near 9
```

What survived:

- 1x runtime bridge lock exists.
- Half-dt and quarter-dt checks pass for several candidates.
- 2x runtime can pass for some passive magnetic/lossy variants.
- Magnetic autolock quick sweeps produce stronger 1x capture candidates.
- Non-369 controls can show strong generic harmonic behavior, so they remain separated from discovery ranking.

What has not survived yet:

- No passive candidate has passed the strict 4x runtime phase-lock gate.
- The long-runtime failure remains phase drift, sometimes with energy-budget growth.
- Open-loop control-authority tests now measure whether allowed real-world actuators can pull that drift without direct 6/9 drive or target-frequency injection.
- Precomputed drift feedforward ramps stayed energetically tiny but did not hold 4x lock in quick smoke.
- PI phase servo improves the 3 -> 6 -> 9 phase lock modestly, but still does not reach the 4x lock gate.
- Emergent-lock diagnostics find a small pulled local target near 9.02 for the 3 -> 6 -> 9 bridge, but the fitted-frequency phase lock still stays below the 0.90 gate.
- Phase-slip audit shows the 3 -> 6 -> 9 bridge loses 4x lock through discrete phase slips, with generated-6 envelope instability before target lock loss.
- Generated-stage stabilization reduced slips only in a budget-breaking raw Stage A tuning row; the best budget-clean damping row improved lock/purity but did not remove slips.
- Stage A budget audit shows static `+0.03` tuning can remove target slips, but the final tuned configuration itself breaks the budget gate even with no dynamic retuning.
- Stage A budget forensics suggests the Stage A budget issue is driven-model ledger/numerical sensitivity: no-drive errors are tiny in absolute terms, and half/quarter-dt reduce full-model budget below gate.
- Harmonic-family mapping now shows 5 -> 10 -> 15 stronger than 3 -> 6 -> 9 under normalized passive scoring, while 4 -> 8 -> 12 is closest to a family candidate.
- Harmonic dt rescue shows the best 4 -> 8 -> 12 target-detuned row is not a phase instability: strict non-budget metrics survive baseline/half/quarter dt, but baseline-dt budget error still blocks promotion.
- Harmonic budget-ledger forensics shows that 4 -> 8 -> 12 budget residual converges away strongly through eighth dt and no single ledger component matches the residual magnitude; it is currently classified as numerical ledger sensitivity, not promotion.
- Harmonic substep quadrature independently validates the 4 -> 8 -> 12 near-candidate as trajectory-integration sensitive: trajectory-preserving quadrature does not close baseline budget, but substep-4 re-integration closes baseline/half/quarter/eighth dt while preserving lock, bridge ratio, purity, envelope CV, and phase-jump gates.
- Independent validation and the first LC physicalization now preserve the strict 4 -> 8 -> 12 result outside the main harness. The LC track keeps audio, low-RF, and normalized scale presets source-only with no direct 8 drive, no direct 12 drive, and no target-frequency injection.
- The SPICE export track now emits and runs CI-friendly ngspice netlists through WSL ngspice. In the latest run, 15 of 19 netlists ran successfully and 4 stiff behavioral/audio/RF rows failed to converge. The normalized behavioral proxy preserved strong lock and purity, but not the Python bridge-ratio gain.
- The SPICE nonlinearity-refinement track found two source-only behavioral proxy rows that cross bridge ratio >1.5 with clean linear controls. The closest row is still behavioral-only, not component-plausible: lock 0.996193, purity 0.981658, bridge ratio 1.563169, target-band growth 1.276714.
- The SPICE component-realism track forbids behavioral current mixing in discovery rows. Several component-plausible rows crossed bridge ratio >1.5, but all had very low phase lock near 0.02 and two controls leaked target-band response, so no component candidate or near miss promoted.
- The SPICE component phase-lock track kept high component bridge ratios under detuning, coupling orientation, Q/load shaping, trap, and limiter sweeps, but no row exceeded phase lock 0.50. Weak and detuned controls still leaked under coherent-growth scoring.
- The spatial phase-matching track shows that an explicit distributed topology can recover coherent 4 -> 8 -> 12 phase lock in the normalized model: 17 discovery rows promoted, best lock 0.999128, bridge ratio 4.748881, purity 0.997300, and controls stayed dead. This points toward distributed/waveguide-like validation rather than more lumped scalar tuning.
- The distributed-ladder SPICE track exports that topology into normalized ngspice envelope-ladder netlists. The phase-matched source-only ladder ran successfully and promoted with lock 0.915421, bridge ratio 3.718438, purity 0.970030, generated-envelope CV 0.032846, max phase jump 0.003169, and dead linear/detuned/shuffled controls.
- The transmission-line SPICE refinement replaces envelope-state propagation with explicit normalized LC ladder propagation plus tuned shunt band sections. The phase-matched source-only TL row promoted with lock 0.997206, bridge ratio 8.261740, purity 0.961441, generated-envelope CV 0.070890, max phase jump 0.057316, behavioral dependency 0.36 versus the envelope-ladder baseline 0.65, and dead controls.
- The physical waveguide interpretation layer maps the promoted TL result onto candidate media. The best first electrical bench analog is a nonlinear varactor-loaded transmission line near 50 MHz with estimated interaction length 0.382 m; acoustic/phononic rows look easiest for compact length, while plain PCB/microstrip is mostly length/nonlinearity limited.
- The bench-oriented varactor NLTL SPICE design exports concrete 50/100/150 MHz varactor-diode loaded LC ladders. All 22 ngspice rows ran successfully, but no row promoted: the best 48-cell/75-ohm line reached lock 0.896172 and bridge ratio 1.287941 with plausible stress and low behavioral dependency 0.08, but 150 MHz spectral purity stayed only 0.006802.
- The varactor NLTL refinement raises 150 MHz purity but still does not promote. All 23 ngspice rows ran; the highest-purity row used 96 cells, 100 ohm, and passive extraction plus rejection, reaching lock 0.996283, bridge ratio 18.502732, purity 0.112843, and behavioral dependency 0.08, but component stress was unrealistic and purity remained below the 0.80 gate.
- The acoustic waveguide parallel simulation promotes a low-frequency 40/80/120 kHz phase-matched analog. The best source-only row is a 48-cell, 0.058 m guide with lock 0.999352, bridge ratio 4628.598328, purity 0.999611, generated-envelope CV 0.231570, max phase jump 0.007893, plausible pressure stress, and dead controls.
- Do not promote to `geometry369` yet.

Best current direction:

- Convert the acoustic waveguide candidate into a bench/readout design, and continue a deeper varactor BOM/part-family sweep before PCB layout.
- Map the f->2f->3f family law with strict budget normalization.
- Stabilize generated 6 if continuing the 3 -> 6 -> 9 branch.
- Repair or refine the driven nonlinear/damping ledger before promoting any Stage A tuned basin.
- 3 -> 6 -> 9 is not uniquely special yet; keep non-369 controls central before geometry/evolve.

## Repo Map

```text
tesla_369_lab/
  tesla_369_lab.py      Main simulation runner.
  README.md             Detailed mode-by-mode lab guide.
  requirements.txt      Python dependencies.
  example_run/          Small starter/example output set.

docs/
  AGENT_GUIDE.md        How a fresh agent should read and continue the project.
  EXPERIMENT_LOG.md     Condensed history of what has been tested.
  PROJECT_STATUS.md     Latest scientific status and next steps.
  prompts/              User experiment prompts/specs that drove major modes.
```

## Main Commands

Install:

```bash
cd tesla_369_lab
pip install -r requirements.txt
```

Fast smoke test:

```bash
python tesla_369_lab.py --mode all --quick
```

Latest experiment:

```bash
python tesla_369_lab.py --mode magnetic_autolock --quick
python tesla_369_lab.py --mode magnetic_autolock --quick --sweeps
python tesla_369_lab.py --mode bridge_min_nudge --quick
python tesla_369_lab.py --mode bridge_min_nudge --quick --sweeps
python tesla_369_lab.py --mode bridge_lock_threshold --quick
python tesla_369_lab.py --mode bridge_lock_threshold --quick --sweeps
python tesla_369_lab.py --mode bridge_control_authority --quick
python tesla_369_lab.py --mode bridge_control_authority --quick --sweeps
python tesla_369_lab.py --mode bridge_drift_feedforward --quick
python tesla_369_lab.py --mode bridge_drift_feedforward --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_servo --quick
python tesla_369_lab.py --mode bridge_phase_servo --quick --sweeps
python tesla_369_lab.py --mode bridge_emergent_lock --quick
python tesla_369_lab.py --mode bridge_emergent_lock --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick --sweeps
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer --quick
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_budget_audit --quick
python tesla_369_lab.py --mode bridge_stageA_budget_audit --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_budget_forensics --quick
python tesla_369_lab.py --mode bridge_stageA_budget_forensics --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_refined_basin --quick
python tesla_369_lab.py --mode bridge_stageA_refined_basin --quick --sweeps
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --quick
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_family --quick
python tesla_369_lab.py --mode harmonic_bridge_family --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_dt_rescue --quick
python tesla_369_lab.py --mode harmonic_bridge_dt_rescue --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_budget_ledger --quick
python tesla_369_lab.py --mode harmonic_bridge_budget_ledger --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_substep_quadrature --quick
python tesla_369_lab.py --mode harmonic_bridge_substep_quadrature --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_412_detuning_refine --quick
python tesla_369_lab.py --mode harmonic_bridge_412_detuning_refine --quick --sweeps
python independent_validate_412.py
python physical_412_lc_bridge.py
python spice_412_export.py
python spice_412_export.py --run
python spice_412_export.py --run --ngspice-path "C:/path/to/ngspice.exe"
python spice_412_export.py --run --ngspice-path wsl:ngspice
python spice_412_refine_nonlinearity.py --ngspice-path wsl:ngspice
python spice_412_component_realism.py --ngspice-path wsl:ngspice
python spice_412_component_phase_lock.py --ngspice-path wsl:ngspice
python spatial_phase_matching_412.py
python spice_412_distributed_ladder.py --run --ngspice-path wsl:ngspice
python spice_412_transmission_line_refine.py --run --ngspice-path wsl:ngspice
python physical_waveguide_412.py
python spice_412_varactor_nltl_design.py --run --ngspice-path wsl:ngspice
python spice_412_varactor_nltl_refine.py --run --ngspice-path wsl:ngspice
python acoustic_waveguide_412.py
```

Key bridge modes:

```bash
python tesla_369_lab.py --mode bridge_lock_refine --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_lock --quick --sweeps
python tesla_369_lab.py --mode magnetic_bridge --quick --sweeps
python tesla_369_lab.py --mode magnetic_autolock --quick --sweeps
python tesla_369_lab.py --mode bridge_min_nudge --quick --sweeps
python tesla_369_lab.py --mode bridge_lock_threshold --quick --sweeps
python tesla_369_lab.py --mode bridge_control_authority --quick --sweeps
python tesla_369_lab.py --mode bridge_drift_feedforward --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_servo --quick --sweeps
python tesla_369_lab.py --mode bridge_emergent_lock --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_slip_audit --quick --sweeps
python tesla_369_lab.py --mode bridge_generated_stage_stabilizer --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_budget_audit --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_budget_forensics --quick --sweeps
python tesla_369_lab.py --mode bridge_stageA_refined_basin --quick --sweeps
python tesla_369_lab.py --mode bridge_limiter_predictive_servo --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_family --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_dt_rescue --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_budget_ledger --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_substep_quadrature --quick --sweeps
python tesla_369_lab.py --mode harmonic_bridge_412_detuning_refine --quick --sweeps
```

## Evidence Standard

A result is not promoted unless it survives:

- Linear, detuned, random, and non-369 controls.
- Clean passive energy accounting.
- Half-dt and quarter-dt checks.
- Longer runtime checks.
- Strong phase lock and spectral purity at the target.
- No direct 6 or direct 9 drive contamination in generated bridge cases.

## Latest Magnetic Autolock Read

Quick sweep result:

- Best 1x quick sweep: `sweep_receiver_capture_8p82_to_8p9_s0p9`.
- It reached bridge ratio 0.957, phase lock 0.950, spectral purity 0.643, and budget error 0.000227 with tiny counted sweep work.
- Best 4x validation rows still failed by phase drift, with phase lock around 0.75 or lower despite decent bridge ratio and purity.
- Current recommendation: do not promote to geometry yet; the next serious path is either deeper passive/autolock 4x tuning or explicit active PLL/selflock with active work accounting.

## Latest Control Authority Read

Quick smoke result:

- Best 4x drift reducer was `stage_B_detuning_nudge`, but it reduced drift by only about 5.7%, below the 50% promotion gate.
- `receiver_tuning_nudge` showed a low extrapolated authority margin in one small-signal row, but the measured open-loop drift reduction was only about 1.4%.
- No quick-smoke authority row passed promotion. The result is evidence for measurable actuator pull, not a 4x lock.
- Current recommendation: try frequency-drift feedforward or stronger proportional control before escalating to a real PLL.

## Latest Drift Feedforward Read

Quick smoke result:

- Best 4x feedforward row used `magnetic_bias_ramp` with `hold_after_capture_ramp`.
- It reached phase lock 0.780, bridge ratio 2.717, spectral purity 0.774, and budget error 0.00328.
- Feedforward work was tiny, about 0.0000083 of total input work, but drift reduction was only about 0.14%.
- No discovery row passed the 4x phase-lock gate.
- A non-369 control reached phase lock 0.996 under the same feedforward rules, so the 3 -> 6 -> 9 bridge is not promoted.
- Current recommendation: stronger proportional control next; move to PLL if fixed feedforward remains phase-limited.

## Latest Phase Servo Read

Quick smoke result:

- Best 3 -> 6 -> 9 row used `receiver_tuning_servo` with Kp 0.003 and Ki 0.000045.
- It reached phase lock 0.808, bridge ratio 2.722, spectral purity 0.773, and budget error 0.00404.
- Servo work was small, about 0.000492 of total input work, with correction peak about 0.0090.
- No discovery row passed the 4x phase-lock gate.
- Non-369 controls reached phase lock 0.994-0.996, but failed full promotion by energy budget.
- Current recommendation: do not move to geometry/evolve yet; 3 -> 6 -> 9 is not uniquely special under these servo rules.

## Latest Emergent Lock Read

Quick smoke result from `runs/bridge_emergent_lock_quick_smoke`:

- Best 3 -> 6 -> 9 row used `stage_B_detuning_servo` on the `feedforward_best_magnetic_bias` seed.
- The fitted effective target was 9.0226, about +0.0226 above nominal 9.
- Emergent phase lock improved only slightly over nominal, 0.733 vs 0.715, with bridge ratio 3.365, spectral purity 0.929, budget error 0.00106, and servo work fraction 0.000198.
- No `harmonic_bridge_candidate`, `pulled_frequency_discovery`, or `369_unique_candidate` label passed.
- Non-369 controls had much higher nominal/emergent phase lock, but failed promotion by energy-budget error; after normalized budget/work scoring, the best 369 row scored higher.
- Current recommendation: treat this as nominal-target drift with a small pulled-frequency component, not a stable emergent-frequency lock. Passive tuning or active PLL remains more justified than geometry/evolve.

## Latest Phase Slip Audit Read

Quick smoke result from `runs/bridge_phase_slip_audit_quick_smoke`:

- Best 3 -> 6 -> 9 audit row again used `stage_B_detuning_servo` on the `feedforward_best_magnetic_bias` seed.
- It kept the pulled target near 9.0226, bridge ratio 3.226, spectral purity 0.929, budget error 0.00109, and servo work fraction 0.000197.
- Lock loss was discrete phase slips, not smooth drift: 4 slip events with max phase jump about 3.11 radians.
- Generated-6 was unstable before target lock loss: generated-envelope CV 0.586 and pre-slip instability 0.341.
- The servo acted late in the best 369 row: correction lag before slip was about 2.36.
- Non-369 controls reached high lock, but only with budget-breaking errors around 0.044 for 4->8->12 and 0.20 for 5->10->15.
- Current recommendation: generated-6 stabilization is the next fix; do not move to geometry/evolve yet.

## Latest Generated Stage Stabilizer Read

Quick smoke result from `runs/bridge_generated_stage_stabilizer_quick_smoke`:

- Best strict-budget 369 row was `generated_stage_damping` with moderate Q damping.
- It reached target phase lock 0.825, bridge ratio 3.166, spectral purity 0.952, budget error 0.000921, and stabilizer work fraction 0.000165.
- It did not pass: target slips stayed at 2, max target phase jump was 2.84 rad, generated envelope CV was 0.559, and pre-slip generated instability was 0.308.
- Raw `stage_A_tuning +0.03` removed target slips, but failed budget with error 0.0127, so it is not promotable.
- Non-369 controls again reached high raw lock but failed budget, leaving no budget-clean non-369 winner.
- Current recommendation: continue budget-clean generated-6 passive stabilization; geometry/evolve and full predictive PLL are not justified yet.

## Latest Stage A Budget Audit Read

Quick smoke result from `runs/bridge_stageA_budget_audit_quick_smoke`:

- Static `Stage A tune +0.03` removed target slips, but failed the budget gate: target lock 0.857, slips 0, bridge ratio 3.424, spectral purity 0.956, budget error 0.0118.
- The same static tuning with no servo also failed budget, with error 0.0137 and zero parameter work, so the budget problem is the final tuned configuration itself, not only dynamic retuning.
- Best near miss was `tune_plus_damping_compensation / moderate_q_damping`: target lock 0.915, slips 0, bridge ratio 3.397, spectral purity 0.969, work fraction 0.000106, but budget error 0.00786.
- Best budget-clean 369 row was drive-delayed initialization, but it still had 2 slips and generated-envelope CV 0.522.
- Non-369 controls did not produce a budget-clean winner.
- Current recommendation: run full generated-stage/passive compensation sweeps before geometry/evolve or predictive PLL.

## Latest Stage A Budget Forensics Read

Quick smoke result from `runs/bridge_stageA_budget_forensics_quick_smoke`:

- No-drive/no-servo rows only showed relative tiny-denominator artifacts: worst no-drive relative budget was 1, but worst absolute error was only about 1.2e-9.
- The gate-relevant budget error appears in driven full-model rows: Stage A `+0.03` full model had budget error 0.0137 at baseline dt, but half-dt dropped it to 0.000092 and quarter-dt to 0.0000075.
- The near-promoted damping row behaved similarly: full-model budget error 0.00547 at baseline dt, half-dt 0.000891, quarter-dt 0.000234.
- The narrow compensation search found budget-clean zero-slip rows, but they did not promote because lock stayed around 0.83-0.84, max phase jump stayed above 2.2 rad, and generated-envelope CV stayed around 0.55.
- Best budget-clean zero-slip row: Stage A offset `+0.030`, damping factor `1.05`, A->B coupling `0.90`, limiter `0.04`; budget error 0.000422, lock 0.834, bridge ratio 2.549, purity 0.950.
- Non-369 controls did not produce a budget-clean winner.
- Current recommendation: repair/refine the driven nonlinear+damping ledger before geometry/evolve, full sweeps, or predictive servo timing.

## Latest Stage A Refined Basin Read

Quick smoke result from `runs/bridge_stageA_refined_basin_quick_smoke`:

- The focused quick subset ran the nearby Stage A basin at half-dt, then validated the top 369 rows at baseline dt, half-dt, and quarter-dt.
- The starting lead stayed budget-clean at refined dt: Stage A offset `+0.030`, damping factor `1.05`, A->B coupling `0.90`, limiter `0.04` had budget error 0.00147, absolute budget error 0.0000724, lock 0.836, bridge ratio 2.555, and purity 0.950.
- Best 369 lock in the subset was 0.864, still below the 0.90 gate.
- Generated-envelope CV did not approach the 0.25 gate; best 369 CV was 0.528.
- Max phase jump did not approach the 1.0 rad gate; best 369 jump was 2.36 rad, and top rows still had 22-24 near slips.
- A 5 -> 10 -> 15 control was budget-clean and stronger by normalized score, although its bridge ratio stayed below the 1.5 promotion gate.
- Current recommendation: limiter redesign plus predictive servo timing before full sweeps; geometry/evolve is still not justified.

## Latest Limiter Predictive Servo Read

Quick smoke result from `runs/bridge_limiter_predictive_servo_quick_smoke`:

- Passive/adaptive generated damping and envelope-derivative damping raised 369 lock above 0.96 while staying budget-clean, but they did not pass the generated-envelope or phase-jump gates.
- Best 369 generated-envelope CV was 0.274, still above the 0.25 gate.
- Best 369 max phase jump was 1.744 rad, still above the 1.0 rad gate, with near slips remaining.
- The best budget-clean high-lock 369 row, `adaptive_generated_damping`, preserved high lock at half/quarter dt: half-dt lock 0.968, quarter-dt lock 0.970, but CV stayed about 0.281 and jumps stayed about 1.75-1.77 rad.
- Predictive servo timing fired early enough to measure lead time, but it did not beat passive damping on the actual jump/CV gates.
- A 5 -> 10 -> 15 control stayed much stronger by normalized budget score, so 369 is not unique under these rules.
- Current recommendation: general harmonic-bridge study before geometry/evolve; if continuing 369, focus on an active PLL or more physical limiter redesign.

## Latest Harmonic Bridge Family Read

Quick smoke result from `runs/harmonic_bridge_family_quick_smoke`:

- The new mode compares 2->4->6 through 8->16->24 using passive baseline, refined Stage A basin equivalent, adaptive generated damping, envelope-derivative damping, energy-bucket limiting, and an active PLL comparator proxy scored separately.
- Strongest passive normalized family was 5 -> 10 -> 15 via passive baseline: lock 0.994, purity 0.999, budget 0.000749, generated-envelope CV 0.057, max jump 0.807, score 0.328. It did not promote because bridge ratio was only 1.122, below the 1.5 gate.
- Best 3 -> 6 -> 9 normalized row was passive baseline by score, but it had lock 0.735, generated-envelope CV 0.582, max jump 3.05 rad, and 21 near slips. The high-lock adaptive/envelope damping rows remained useful diagnostics but were penalized by limiter work and still failed jump/CV preservation.
- 4 -> 8 -> 12 came closest to a harmonic candidate: refined Stage A equivalent had lock 0.984, bridge ratio 1.929, purity 0.992, budget 0.00185, generated-envelope CV 0.126, and max jump 1.05, but dt preservation was only 0.667.
- No family passed `harmonic_bridge_candidate`, no family passed strict, and there is not yet evidence for a general harmonic bridge law.
- Current recommendation: family-law mapping before any 369-specific PLL or geometry/evolve step.

## Latest Harmonic Bridge Dt Rescue Read

Quick smoke result from `runs/harmonic_bridge_dt_rescue_quick_smoke`:

- The rescue mode reran each candidate at baseline dt, half dt, and quarter dt, then ranked using worst-case metrics across all three.
- Best 4 -> 8 -> 12 rescue row was target detuning `-0.08`: lock 0.985/0.985/0.985 across dt, bridge ratio about 1.875, purity about 0.992, generated-envelope CV below 0.139, max jump below 0.999 rad, and near slips 0.
- That row did not promote because budget remained dt-sensitive: baseline budget error 0.04485, half-dt 0.005006, quarter-dt 0.000628.
- No 4 -> 8 -> 12 row passed `harmonic_bridge_candidate` or strict because the all-dt budget gate was not met.
- After bridge-ratio gating, 4 -> 8 -> 12 beat 5 -> 10 -> 15; 5 -> 10 -> 15 still failed bridge-ratio and budget normalization in this dt-aware rescue.
- 3 -> 6 -> 9 remained behind 4 -> 8 -> 12, but beat 5 -> 10 -> 15 once 5-family bridge-ratio/budget failures were counted.
- Current recommendation: 4 -> 8 -> 12 budget-ledger refinement, then a tighter target-detuning sweep.

## Latest Harmonic Bridge Budget Ledger Read

Quick smoke result from `runs/harmonic_bridge_budget_ledger_quick_smoke`:

- The primary 4 -> 8 -> 12 row used target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, and limiter `0.04`.
- Non-budget metrics stayed strong across baseline/half/quarter dt: worst lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max jump 0.998 rad, and near slips 0.
- Existing ledger residual converged strongly with timestep: relative budget error 0.04490 at baseline dt, 0.00498 at half-dt, 0.000605 at quarter-dt, and 0.000110 at eighth-dt; estimated convergence order was about 3.11.
- Midpoint/trapezoid sampled accounting did not rescue baseline dt: baseline remained 0.04401, while quarter-dt was clean at 0.000850 and eighth-dt was 0.0000116.
- No single component matched the residual magnitude. Diagnostic magnetic-loss subtraction made the ledger worse, so this is not a simple missing magnetic-loss term.
- The row is marked `candidate_pending_independent_validation=False`, not promoted. Current recommendation: independent corrected/substep quadrature, then a tighter 4 -> 8 -> 12 target-detuning sweep if the independent ledger closes.

## Latest Harmonic Bridge Substep Quadrature Read

Quick sweeps result from `runs/harmonic_bridge_substep_quadrature_quick_sweeps_smoke`:

- The primary 4 -> 8 -> 12 row remained strong: lock 0.991, bridge ratio 1.531, purity 0.925, generated-envelope CV 0.138, max phase jump 0.998 rad, and near slips 0.
- Same-trajectory/trajectory-preserving auditors did not close the baseline residual: existing ledger 0.04493, RK-stage-consistent 0.06762, and sampled 16-substep quadrature 0.382.
- Re-integrating the same physics with substep-4 closed the budget at every audited dt: baseline 0.0000511, half-dt 0.000000747, quarter-dt 0.0000000298, eighth-dt 0.00000000425.
- Substep re-integration preserved the candidate: baseline substep-4 lock 0.9917, bridge ratio 1.531, and purity 0.925.
- Classification: `budget_residual_source=trajectory_integration_error`, `candidate_pending_detuning_refine=True`, `candidate_numerically_fragile=False`, and no final promotion from this diagnostic mode alone.
- Current recommendation: run a tight 4 -> 8 -> 12 target-detuning sweep plus an independent validation script/solver before promoting any family-law result.

## Latest Harmonic Bridge 4->8->12 Detuning Refine Read

Quick smoke result from `runs/harmonic_bridge_412_detuning_refine_quick_smoke3`:

- The best refined 4 -> 8 -> 12 row used target detuning `-0.08`, Stage A offset `+0.040`, generated damping factor `1.05`, A->B coupling `0.90`, and limiter `0.03`.
- It passed both `harmonic_bridge_candidate` and `strict_harmonic_bridge_candidate` across baseline, half, and quarter dt under substep-4 re-integration.
- Worst all-dt metrics for that row: lock 0.992, bridge ratio 1.589, purity 0.923, budget error 0.0000510, generated-envelope CV 0.135, max phase jump 0.972 rad, and near slips 0.
- Nearby rows at Stage A `+0.045`, target detuning `-0.075`, and target detuning `-0.070` also passed strict gates.
- Under the same substep accounting, 4 -> 8 -> 12 beat 3 -> 6 -> 9 and 5 -> 10 -> 15 after bridge-ratio gating. The 5 -> 10 -> 15 control still had high lock, but its bridge ratio stayed below 1.5.
- This does not promote geometry/evolve. Current recommendation: independent validation solver first, then full family-law mapping.

## Latest Independent 4->8->12 Validation Read

Standalone result from `python independent_validate_412.py`:

- The script does not import `tesla_369_lab.py` or call any experiment mode. It reimplements the explicit three-mode equations, substep-4 RK4 integration, energy ledger, phase diagnostics, and output writers.
- Outputs are written to `runs/independent_validate_412/independent_412_summary.json`, `independent_412_summary.csv`, `independent_412_timeseries.csv`, and `README_INDEPENDENT_412_VALIDATION.md`.
- It reproduced the strict 4 -> 8 -> 12 candidate across baseline, half-dt, and quarter-dt: worst lock 0.992, bridge ratio 1.607, purity 0.923, budget 0.0000510, generated-envelope CV 0.135, max jump 0.972 rad, near slips 0.
- Candidate drive remained source-only 4: no direct 8 drive, no direct 12 drive, and no target-frequency injection. The direct 4+8 row is used only as a ceiling denominator for bridge ratio.
- Material differences from the main harness: none. The candidate is marked `independent_validation_passed=True`.
- Current recommendation: full family-law mapping and broader validation before any geometry/evolve promotion.

## Latest Physical 4->8->12 LC Bridge Read

Standalone result from `python physical_412_lc_bridge.py`:

- The script maps the independent strict 4 -> 8 -> 12 candidate onto three coupled nonlinear LC resonators with `L1/C1/R1`, `L2/C2/R2`, and `L3/C3/R3`, plus Q factors, weak linear coupling, varactor-like quartic capacitance, nonlinear mixing, and passive soft-limiter loss.
- Outputs are written to `runs/physical_412_lc_bridge/physical_412_summary.json`, `physical_412_summary.csv`, `physical_412_timeseries.csv`, and `README_PHYSICAL_412_LC_BRIDGE.md`.
- All audio-scale, low-RF-scale, and arbitrary-normalized-scale rows passed baseline/half/quarter dt gates. Worst metrics: lock 0.992108, bridge ratio 1.606971, purity 0.922789, budget 0.0000510, generated-envelope CV 0.134693, target-envelope CV 0.035824, max jump 0.971944 rad, near slips 0.
- Representative audio-scale parameters: f=(440, 883.894, 1309.862) Hz, L=(13.08 mH, 6.90 mH, 4.47 mH), C=(10 uF, 4.7 uF, 3.3 uF), R=(0.912, 0.901, 0.480) ohm, Q=(39.7, 42.5, 76.8), all mild. Peak voltages were about 8.70 V, 7.45 V, and 10.39 V.
- The LC read remains source-only: no direct 8 drive, no direct 12 drive, and no target-frequency injection. The direct 4+8 row is still only a ceiling denominator.
- Current recommendation: physical nonlinear-component refinement, parameter sweep, and spatial phase-matching modeling.

## Latest SPICE 4->8->12 Export Read

Standalone result from `python spice_412_export.py --run --ngspice-path wsl:ngspice` after installing ngspice in WSL:

- Generated ngspice-compatible netlists for `audio_412_bridge.cir`, `low_rf_412_bridge.cir`, `normalized_412_bridge.cir`, five nonlinear realism variants per scale, the `linear_no_nonlinearity_control`, and the separated ceiling/reference `reference_direct_4plus8.cir`.
- Outputs are written to `runs/spice_412_bridge/spice_412_summary.json`, `spice_412_summary.csv`, `spice_412_timeseries.csv`, and `README_SPICE_412_EXPORT.md`.
- WSL ngspice is installed and available as `/usr/bin/ngspice` (`ngspice-42`). Native Windows `ngspice` is still not on PATH, `winget search ngspice` found no matching package, and Docker is unavailable.
- Execution statuses are `failed_to_converge;ran_successfully`: 15 rows ran successfully and 4 rows failed to converge with ngspice `TRAN: Timestep too small` reports.
- Discovery netlists remain source-only: no direct generated-mode drive, no direct target-mode drive, and no target-frequency injection. The direct 4+8 netlist is marked `ceiling_reference`.
- Circuit variants now include `behavioral_proxy_current`, `voltage_dependent_capacitance_proxy`, `diode_pair_proxy`, `varactor_diode_model_proxy`, `saturable_inductor_proxy`, and `linear_no_nonlinearity_control`.
- The normalized behavioral proxy was the closest SPICE row: lock `0.997003`, purity `0.971359`, target growth `2.06766`, max jump `0.274669`, and normalized reference bridge ratio `0.788167`. It did not preserve the Python LC bridge ratio `1.606971`.
- The linear no-nonlinearity controls ran and failed as expected under target-band criteria: lock stayed near `0.014`, purity near `1.7e-6`, and target FFT peaks stayed at the source frequency rather than near 12.
- Current recommendation: nonlinear component refinement, parameter sweep, then spatial phase-matching modeling.

## Latest SPICE 4->8->12 Nonlinearity Refinement

Standalone result from `python spice_412_refine_nonlinearity.py --ngspice-path wsl:ngspice --max-discovery-cases 56`:

- Added `spice_412_refine_nonlinearity.py` and generated `runs/spice_412_refine_nonlinearity/spice_412_refine_summary.json`, `spice_412_refine_summary.csv`, `spice_412_refine_timeseries.csv`, and `README_SPICE_412_REFINE_NONLINEARITY.md`.
- Focused normalized-scale sweep covered all requested variant families, nonlinear strength scales, limiter/conductance scales, coupling scales, drive amplitude scales, solver tolerance profiles, and max-timestep scales in a bounded 56-row discovery set with matching direct 4+8 references.
- Run result: 36 discovery rows ran successfully and 20 failed to converge with ngspice `TRAN: Timestep too small`.
- Bridge ratio >1.5 was reached by two `behavioral_proxy_current` rows: `r038` and `r042`.
- Closest Python-LC row was `r042`: nonlinear strength scale `2.0`, limiter scale `2.0`, coupling scale `1.25`, drive scale `1.5`, default solver, maxstep scale `1.0`; lock `0.996193`, purity `0.981658`, bridge ratio `1.563169`, generated-envelope CV `0.091533`, max jump `0.289970`, target-band growth `1.276714`.
- Linear no-nonlinearity controls remained dead: maximum linear leakage score `0.0`; target-band growth stayed `0`, purity stayed near `1.7e-6`, and target FFT peaks stayed at the source band.
- No diode/varactor/saturable/hybrid component-plausible row promoted. The successful variants are behavioral-only, so the next step is component-level refinement to replace behavioral mixing, then a physical parameter sweep.

## Latest SPICE 4->8->12 Component Realism

Standalone result from `python spice_412_component_realism.py --ngspice-path wsl:ngspice --max-cases 44`:

- Added `spice_412_component_realism.py` and generated `runs/spice_412_component_realism/spice_412_component_realism_summary.json`, `spice_412_component_realism_summary.csv`, `spice_412_component_realism_timeseries.csv`, and `README_SPICE_412_COMPONENT_REALISM.md`.
- Discovery rows forbid behavioral current mixing, direct 8 drive, direct 12 drive, and target-frequency injection. Direct 4+8 rows are separated ceiling references only.
- Focused normalized-scale sweep covered anti-parallel diode, diode bridge, varactor pair, back-to-back varactor stack, saturable inductor, coupled saturable transformer, hybrid varactor+saturable, and diode+resonant trap component families.
- Run result: 40 discovery rows were evaluated; 38 ran successfully and 2 failed to converge with ngspice `TRAN: Timestep too small`.
- Component-plausible rows crossing bridge ratio >1.5 were `c008`, `c013`, `c018`, `c023`, `c028`, and `c033`; however their target phase lock stayed low, with the closest behavioral-proxy row `c008` at lock `0.017518`, purity `0.989155`, bridge ratio `1.647442`, and target-band growth `1.284235`.
- No `spice_component_bridge_candidate` or `spice_component_near_miss` promoted. Linear and shuffled controls stayed dead, but weak-nonlinearity and detuned controls showed target-band leakage under the current criterion, so `controls_remained_dead=False`.
- Current recommendation: deeper component sweep and spatial phase-matching modeling before physical parameter refinement.

## Latest SPICE 4->8->12 Component Phase Lock

Standalone result from `python spice_412_component_phase_lock.py --ngspice-path wsl:ngspice --max-cases 84`:

- Added `spice_412_component_phase_lock.py` and generated `runs/spice_412_component_phase_lock/spice_412_component_phase_lock_summary.json`, `spice_412_component_phase_lock_summary.csv`, `spice_412_component_phase_lock_timeseries.csv`, and `README_SPICE_412_COMPONENT_PHASE_LOCK.md`.
- Focused on seed rows `c008`, `c013`, `c018`, `c023`, `c028`, and `c033`, sweeping target/generated detuning, coupling sign/orientation, coupling strength, Q/load shaping, passive trap phase shapers, and limiter/loss scale.
- Run result: 84 discovery rows and 5 controls ran successfully under WSL `ngspice-42`; no convergence failures.
- Many rows kept bridge ratio >1.5, but phase lock did not materially recover. Best phase-lock row was `p048` (`varactor_pair_mixer`, coupling orientation) with lock `0.030889`, bridge ratio `0.633056`, purity `0.914026`, and coherent target growth `1.03079`.
- Best high-bridge row was `p050` (`saturable_inductor_core`, coupling orientation) with bridge ratio `124.013`, lock only `0.025185`, purity `0.992149`, and coherent growth `2.21288`, so it was rejected for phase incoherence.
- No row reached phase lock >0.50 or >0.90. No phase candidate or near miss promoted.
- Linear, shuffled, and off-resonance controls stayed dead; weak-nonlinearity and detuned controls still leaked under coherent-growth criteria. Current recommendation: spatial phase-matching model or rejection of the current component topology before deeper sweeps.

## Latest Spatial Phase Matching 4->8->12

Standalone result from `python spatial_phase_matching_412.py`:

- Added `spatial_phase_matching_412.py` and generated `runs/spatial_phase_matching_412/spatial_phase_matching_412_summary.json`, `spatial_phase_matching_412_summary.csv`, `spatial_phase_matching_412_timeseries.csv`, and `README_SPATIAL_PHASE_MATCHING_412.md`.
- The model is a normalized 1D distributed coupled-mode chain with explicit `k4`, `k8`, `k12`, `delta_k_448 = k8 - 2*k4`, `delta_k_4812 = k12 - k8 - k4`, quasi-phase-matching gratings, alternating sign patterns, backward-wave target options, group-velocity mismatch, passive saturation loss, and source-only 4 drive.
- Discovery rows preserve no direct 8 drive, no direct 12 drive, and no target-frequency injection. The separated direct 4+8 row remains a ceiling denominator only.
- Full run result: 47 discovery rows and 4 controls; 17 `spatial_phase_bridge_candidate` rows and 6 near misses promoted. Controls stayed dead with max leakage score `0.064712`.
- Best row was `s043 nonlinear_strength_1.55`: topology `co_directional_phase_matched`, lock `0.999128`, bridge ratio `4.748881`, purity `0.997300`, target coherent growth `20.196273`, generated-envelope CV `0.053898`, max phase jump `0.000683`, and energy budget error `3.44e-12`.
- QPM did not fully promote, but it outperformed compact lumped and deliberately mismatched rows: best QPM lock `0.744986`, bridge ratio `9.413271`; mismatched rows fell to lock `0.026108` and `0.060735`.
- The compact lumped-equivalent row produced large target energy but low phase lock `0.436675`, so it was rejected for phase mismatch. This supports the hypothesis that coherent 4 -> 8 -> 12 transfer needs distributed phase matching rather than the previous lumped LC topology.
- Current next fix: export a distributed-ladder SPICE model, then refine a physical waveguide/phase-matching realization.

## Latest SPICE 4->8->12 Distributed Ladder

Standalone result from `python spice_412_distributed_ladder.py --run --ngspice-path wsl:ngspice`:

- Added `spice_412_distributed_ladder.py` and generated normalized ngspice envelope-ladder netlists for phase-matched, QPM, mismatched, compact lumped, linear, detuned, shuffled, and direct 4+8 ceiling-reference cases.
- Outputs are written to `runs/spice_412_distributed_ladder/spice_412_distributed_ladder_summary.json`, `spice_412_distributed_ladder_summary.csv`, `spice_412_distributed_ladder_timeseries.csv`, and `README_SPICE_412_DISTRIBUTED_LADDER.md`.
- All 8 netlists ran successfully under WSL `ngspice-42`.
- The phase-matched ladder promoted as `spice_distributed_phase_candidate`: lock `0.915421`, bridge ratio `3.718438`, purity `0.970030`, target coherent growth `18.063953`, generated-envelope CV `0.032846`, target-envelope CV `0.027283`, max phase jump `0.003169`, and near slips `0`.
- The phase-matched ladder beat the compact lumped control on coherent lock. The lumped control had huge target amplitude but low lock `0.453307`, so it was rejected for phase mismatch.
- Deliberate phase mismatch killed lock: mismatched lock `0.013550`.
- QPM helped relative to mismatch with lock `0.620977` and bridge ratio `5.746898`, but it did not promote because purity was `0.718200`.
- Linear, detuned, and shuffled controls stayed dead with max coherent leakage score `0.0`.
- Current next fix: physical waveguide modeling plus transmission-line ladder refinement.

## Latest SPICE 4->8->12 Transmission-Line Refinement

Standalone result from `python spice_412_transmission_line_refine.py --run --ngspice-path wsl:ngspice`:

- Added `spice_412_transmission_line_refine.py` and generated normalized ngspice LC transmission-line ladder netlists for phase-matched, QPM, mismatched, compact lumped, linear, detuned, shuffled, and direct 4+8 ceiling-reference cases.
- Outputs are written to `runs/spice_412_transmission_line_refine/spice_412_tl_summary.json`, `spice_412_tl_summary.csv`, `spice_412_tl_timeseries.csv`, and `README_SPICE_412_TRANSMISSION_LINE_REFINE.md`.
- All 8 netlists ran successfully under WSL `ngspice-42`.
- The phase-matched TL ladder promoted as `spice_tl_phase_candidate`: lock `0.997206`, bridge ratio `8.261740`, purity `0.961441`, target coherent growth `3.955957`, generated-envelope CV `0.070890`, max phase jump `0.057316`, and behavioral dependency `0.36`.
- Behavioral dependency is lower than the previous envelope-ladder baseline `0.65` because propagation and band storage now use explicit LC ladder sections; behavioral sources remain for distributed nonlinear mixing and saturation proxies.
- QPM helped relative to dead controls with lock `0.961919`, purity `0.880158`, and target coherent growth `1.583010`, but it did not promote because bridge ratio stayed `0.006003` against the direct 4+8 reference.
- Deliberate mismatch did not lower the raw phase metric on tiny residual target response, but it suppressed material bridge ratio to `0.002707`, so it stayed control-dead.
- Linear, detuned, shuffled, lumped, and mismatched controls stayed dead with max coherent leakage score `0.0`.
- Current next fix: physical waveguide modeling, then PCB/transmission-line approximation.

## Latest Physical Waveguide 4->8->12 Interpretation

Standalone result from `python physical_waveguide_412.py`:

- Added `physical_waveguide_412.py` and generated `runs/physical_waveguide_412/physical_waveguide_412_summary.json`, `physical_waveguide_412_summary.csv`, and `README_PHYSICAL_WAVEGUIDE_412.md`.
- The script maps the promoted TL row onto PCB/microstrip or coaxial ladders, acoustic/phononic chains, nonlinear magnetic transmission lines, varactor-loaded transmission lines, mechanical/metamaterial lattices, and optical/nonlinear waveguides as a conceptual comparison.
- The best first electrical bench analog is `nonlinear_varactor_loaded_transmission_line`: plausible bench-scale, source frequency `50 MHz`, required interaction length `0.381972 m`, estimated bridge ratio `8.261740`, and target coherent growth `4.046130`.
- Acoustic/phononic mapping is also plausible bench-scale and much shorter, with source frequency `40 kHz` and length `0.076394 m`, but the harder part is calibrated nonlinear drive/readout without transducer feedthrough.
- Nonlinear magnetic transmission line mapping is plausible bench-scale at `10 MHz` with length `0.763944 m`, but core loss, bias history, and saturation stress are the risks.
- Plain PCB/microstrip or coax is classified as aggressive but testable: length `6.875494 m`; the blocker is length/nonlinearity more than raw loss.
- Controls stayed dead: phase-mismatched, too-lossy, too-short, weak-nonlinearity, and linear/no-nonlinearity mappings had max leakage score `0.040093`.
- Current next fix: PCB/transmission-line SPICE design for a varactor-loaded nonlinear transmission line, with acoustic simulation as a parallel low-frequency analog.

## Latest SPICE 4->8->12 Varactor NLTL Design

Standalone result from `python spice_412_varactor_nltl_design.py --run --ngspice-path wsl:ngspice`:

- Added `spice_412_varactor_nltl_design.py` and generated concrete low-RF varactor-loaded LC ladder netlists for 50/100/150 MHz operation.
- Outputs are written to `runs/spice_412_varactor_nltl_design/spice_412_varactor_nltl_summary.json`, `spice_412_varactor_nltl_summary.csv`, `spice_412_varactor_nltl_timeseries.csv`, and `README_SPICE_412_VARACTOR_NLTL_DESIGN.md`.
- Sweep coverage: 12, 16, 24, 32, and 48 cells crossed with 25, 50, and 75 ohm target impedances, plus linear, weak-varactor, detuned, shuffled, too-short, too-lossy, and direct 50+100 MHz reference controls.
- All 22 netlists ran successfully under WSL `ngspice-42`.
- No `spice_varactor_nltl_candidate` or `near_miss` promoted. The best row was `d015 varactor_nltl_48cells_75ohm`: lock `0.896172`, bridge ratio `1.287941`, purity `0.006802`, target coherent growth `1.019062`, generated-envelope CV `0.013623`, max phase jump `2.422032`, and plausible stress.
- Behavioral dependency dropped to `0.08`, well below the previous TL baseline `0.36`, because generation comes from the varactor diode capacitance model rather than explicit behavioral current mixing.
- Controls stayed dead with max leakage score `0.099801`.
- Current read: the bench NLTL is component-plausible and stable, but the first capacitance-swing/phase-velocity design spreads too much energy outside the 150 MHz target band. Next fix is component selection/BOM plus stronger varactor and phase-velocity sweeps before PCB layout.

## Latest SPICE 4->8->12 Varactor NLTL Refinement

Standalone result from `python spice_412_varactor_nltl_refine.py --run --ngspice-path wsl:ngspice`:

- Added `spice_412_varactor_nltl_refine.py` and generated focused refinement netlists around the previous best 48-cell/75-ohm varactor NLTL row.
- Outputs are written to `runs/spice_412_varactor_nltl_refine/spice_412_varactor_nltl_refine_summary.json`, `spice_412_varactor_nltl_refine_summary.csv`, `spice_412_varactor_nltl_refine_timeseries.csv`, and `README_SPICE_412_VARACTOR_NLTL_REFINE.md`.
- Sweep coverage: 48, 64, 80, and 96 cells; 50, 75, and 100 ohm variants; stronger capacitance swing/bias/drive settings; phase-velocity trims; passive 150 MHz extraction, source/generated rejection, target shunt trap, and load/Q shaping.
- All 23 netlists ran successfully under WSL `ngspice-42`.
- No `spice_varactor_nltl_candidate` or `near_miss` promoted. Target purity improved but remained below the `0.30` near-miss and `0.80` candidate gates.
- Best purity row was `r013 refine_96c_100ohm_extraction_plus_rejection`: lock `0.996283`, bridge ratio `18.502732`, purity `0.112843`, target growth `1.075207`, generated-envelope CV `0.073475`, max phase jump `0.252252`, behavioral dependency `0.08`, but stress was `unrealistic`.
- Best plausible-stress purity row was `r003 refine_80c_75ohm_none`: lock `0.991412`, bridge ratio `8.462014`, purity `0.107203`, target growth `1.007927`, and plausible stress.
- Increasing cell count helped purity up to the 80/96-cell region: best purity by cell count was 48=`0.010084`, 64=`0.050886`, 80=`0.107203`, 96=`0.112843`.
- Passive target extraction/rejection helped purity, but not enough to reach a clean 150 MHz band. Controls stayed dead with max leakage score `0.137543`.
- Current read: varactor NLTL phase lock and bridge gain are recoverable with low behavioral dependency, but clean target-band purity remains the blocker. Next fix is acoustic parallel simulation plus deeper component/BOM sweep before PCB layout.

## Latest Acoustic Waveguide 4->8->12

Standalone result from `python acoustic_waveguide_412.py`:

- Added `acoustic_waveguide_412.py` and generated a low-frequency acoustic/phononic 1D waveguide analog at 40/80/120 kHz.
- Outputs are written to `runs/acoustic_waveguide_412/acoustic_waveguide_412_summary.json`, `acoustic_waveguide_412_summary.csv`, `acoustic_waveguide_412_timeseries.csv`, and `README_ACOUSTIC_WAVEGUIDE_412.md`.
- The model includes explicit `k4`, `k8`, `k12`, `delta_k_448`, `delta_k_4812`, forward waveguide transport, phase-matching gain, QPM signs, nonlinear local stiffness proxies for 40+40 -> 80 and 40+80 -> 120, damping/loss, boundary absorption, pressure/readout estimates, and source-only drive.
- One source-only discovery row promoted: `a005 phase_matched_short_48cell`.
- Promoted metrics: lock `0.999352`, bridge ratio `4628.598328`, 120 kHz purity `0.999611`, target coherent growth `26.944527`, generated-envelope CV `0.231570`, target-envelope CV `0.322958`, max phase jump `0.007893`, and near slips `0`.
- Estimated physical scale is bench-sized: 40 kHz source, 0.058 m guide length for the promoted row, peak pressure about `329 Pa`, plausible stress, and transducer feedthrough risk about `0.024`.
- Linear/no-nonlinearity, weak-nonlinearity, detuned-target, phase-mismatched, shuffled-frequency, too-short, and too-lossy controls stayed dead with max leakage score `0.0`.
- Current read: the acoustic analog recovers clean 120 kHz purity in a normalized phase-matched waveguide model. The next fix is acoustic bench/readout design, with deeper varactor BOM sweeps remaining a parallel electrical path.
