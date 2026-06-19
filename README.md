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
- Non-369 magnetic controls do not beat the 3->6->9 bridge in current scoring.

What has not survived yet:

- No passive candidate has passed the strict 4x runtime phase-lock gate.
- The long-runtime failure remains phase drift, sometimes with energy-budget growth.
- Do not promote to `geometry369` yet.

Best current direction:

- Keep passive magnetic damping/saturation as a useful lead.
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
python tesla_369_lab.py --mode magnetic_bridge --quick
python tesla_369_lab.py --mode magnetic_bridge --quick --sweeps
```

Key bridge modes:

```bash
python tesla_369_lab.py --mode bridge_lock_refine --quick --sweeps
python tesla_369_lab.py --mode bridge_phase_lock --quick --sweeps
python tesla_369_lab.py --mode magnetic_bridge --quick --sweeps
```

## Evidence Standard

A result is not promoted unless it survives:

- Linear, detuned, random, and non-369 controls.
- Clean passive energy accounting.
- Half-dt and quarter-dt checks.
- Longer runtime checks.
- Strong phase lock and spectral purity at the target.
- No direct 6 or direct 9 drive contamination in generated bridge cases.

## Latest Magnetic Bridge Read

Quick sweep result:

- Passive magnetic coupling can improve 2x runtime stability.
- Saturable and lossy/hysteretic variants are the most useful passive leads.
- Best observed 4x lock gains improve relative to no-magnetic baseline, but still fail the hard phase-lock gate.
- Current recommendation: do not promote to geometry yet; either refine passive damping specifically for 4x or move to active self-lock / PLL.

