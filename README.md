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
- Do not promote to `geometry369` yet.

Best current direction:

- Keep passive magnetic damping/saturation and open-loop autolock as useful leads.
- If 4x passive lock remains elusive, move to active self-lock / PLL as the next serious mechanism.

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
```

Key bridge modes:

```bash
python tesla_369_lab.py --mode bridge_lock_refine --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_lock --quick --sweeps
python tesla_369_lab.py --mode magnetic_bridge --quick --sweeps
python tesla_369_lab.py --mode magnetic_autolock --quick --sweeps
python tesla_369_lab.py --mode bridge_min_nudge --quick --sweeps
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
