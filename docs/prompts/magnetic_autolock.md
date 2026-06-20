# Magnetic Autolock Prompt

Add a new mode to `tesla_369_lab.py` called `magnetic_autolock`.

Commands:

```bash
python tesla_369_lab.py --mode magnetic_autolock
python tesla_369_lab.py --mode magnetic_autolock --quick
python tesla_369_lab.py --mode magnetic_autolock --sweeps
```

Goal:

Before adding full active PLL feedback, test passive and semi-passive magnetic phase-capture mechanisms that may stabilize the clean staged `3 -> generated 6 -> 9` bridge through 4x runtime.

Current state:

- Clean staged `3 -> generated 6 -> 9` bridge exists.
- Passive nonmagnetic lock island passes 1x and timestep refinement but fails 2x/4x phase lock.
- Passive magnetic coupling improves some 2x cases but does not survive strict 4x phase-lock gates.
- Best magnetic lead: `sweep_stage_B_strength_0p84`, 2x passed, bridge ratio 0.799, phase_lock_9 0.966, spectral purity 0.836, budget error 0.000413, 4x phase_lock_9 0.677.
- Saturable and lossy/hysteretic magnetic variants are the best passive leads.
- Effective generated target frequency is around 9.05-9.08.
- The main failure is long-runtime phase drift, not energy leak.

Test three mechanisms:

1. Magnetic autoresonant capture
   - Slow open-loop sweeps of receiver tuning, magnetic bias, or Stage B effective inductance.
   - No feedback.
   - Count sweep work and require lock to hold after the sweep stops.

2. Hybrid magnetic mode tuning
   - Model Stage B and receiver as magnetically coupled modes with split hybrid branches.
   - Tune mutual inductance, magnetic phase lag, core saturation, and receiver tuning so one branch lands near 9.05-9.08.
   - Track magnetic energy, coupling exchange, losses, and budget error.

3. Ultraweak injection locking
   - Inject a tiny phase reference near 9.02-9.10.
   - No feedback loop.
   - Count injection work and penalize any solution where the active work fraction is large.

Hard gates:

- 1x and 2x runtime pass.
- 4x runtime pass for promotion.
- bridge_ratio > 0.75.
- phase_lock_9 > 0.90.
- spectral_purity_9 > 0.60.
- energy_budget_error < 0.002 at 1x/2x.
- energy_budget_error < 0.005 at 4x.
- half-dt and quarter-dt preserve the result.
- active_work_fraction < 0.05.
- injection_work_fraction < 0.02 for strong injection.
- random, detuned, wrong-direction, wrong-frequency, and non-369 controls reported separately.
- direct resonance references score 0.

Outputs:

- `magnetic_autolock_summary.csv`
- `magnetic_autolock_ranked.csv`
- `magnetic_autolock_sweeps.csv`
- `magnetic_autolock_energy_ledger.csv`
- `magnetic_autolock_phase_timeseries.csv`
- `magnetic_autolock_capture_report.csv`
- `magnetic_autolock_controls.csv`
- `README_MAGNETIC_AUTOLOCK_REPORT.md`

Report questions:

1. Can magnetic autoresonant capture hold the bridge through 4x runtime without feedback?
2. Does the lock survive after the sweep stops?
3. Can hybrid magnetic mode tuning land a stable branch near the generated 9.05-9.08 mode?
4. Does ultraweak injection locking work with less than 1-2% injection work?
5. Which mechanism gives the best 4x stability with the least active work?
6. Does any result beat the passive magnetic baseline?
7. Do non-369 bridge controls beat the 3 -> 6 -> 9 bridge under the same mechanism?
8. Should the next step be full `bridge_pll`, `geometry369`, or `evolve`?
