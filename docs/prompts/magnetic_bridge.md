# Magnetic Bridge Prompt

Add a new mode to `tesla_369_lab.py` called `magnetic_bridge`.

Commands:

```bash
python tesla_369_lab.py --mode magnetic_bridge
python tesla_369_lab.py --mode magnetic_bridge --quick
python tesla_369_lab.py --mode magnetic_bridge --sweeps
```

Goal:

Add a magnetic-flux coupling layer to the clean passive staged `3 -> generated 6 -> 9` bridge. The purpose is not to increase raw energy. The purpose is to stabilize long-runtime phase lock and reduce 2x/4x drift while preserving clean energy accounting.

Core requirement:

- Use clean passive model only.
- No hidden active gain.
- No direct 6 drive in generated bridge cases.
- No direct 9 drive except reference/ceiling cases.
- Track magnetic energy, magnetic losses, magnetic work, and magnetic coupling exchange.

Report questions:

1. Does the magnetic layer reduce long-runtime phase drift?
2. Does any passive magnetic configuration survive 4x runtime?
3. Does magnetic bias or saturation widen the lock island?
4. Is the best improvement from flux coupling, saturation, bias, or loss/damping?
5. Does the magnetic layer preserve clean energy accounting?
6. Does the 3 -> 6 -> 9 bridge outperform non-369 magnetic bridge controls?
7. Should the result be promoted to geometry369, or should we move to active self-lock / PLL?
8. What exact candidate parameters should be used as the next seed?

