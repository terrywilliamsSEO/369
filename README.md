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
- Do not promote to `geometry369` yet.

Best current direction:

- Use `bridge_drift_feedforward --sweeps` only to confirm the fixed-ramp result across timing/ramp-size variants.
- The stronger next path is proportional control; move to a real PLL if fixed feedforward remains phase-limited.

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
