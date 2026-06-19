# Project Status

Last updated: 2026-06-19

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

## Current Blocker

No passive model has passed the strict 4x runtime lock gate.

The main 4x failure is phase drift. Some candidates also accumulate unacceptable energy-budget error over long runtime.

## Latest Magnetic Bridge Summary

Mode added:

```bash
python tesla_369_lab.py --mode magnetic_bridge
python tesla_369_lab.py --mode magnetic_bridge --quick
python tesla_369_lab.py --mode magnetic_bridge --sweeps
```

Quick sweep result:

- Best 2x/4x magnetic lock gain vs no-magnetic baseline: about 1.08 in the quick sweep.
- No candidate passed 4x phase lock.
- Saturable-core and lossy/hysteretic variants are the best passive leads.
- Non-369 magnetic bridge controls underperformed the 3->6->9 bridge.

## Recommendation

Do not promote to `geometry369` yet.

Next options:

1. Fine-optimize passive lossy/saturable magnetic damping for 4x runtime only.
2. Move to active self-lock / PLL and explicitly account for active work.
3. Add a geometry mode only after a 4x-stable seed exists.

