# Tesla 3-6-9 Lab Report

This run asks: does a 3-6-9 pattern beat controls?

## triad_resonator
- rank 1: **4812_exact_sum** — score=0.64024; freqs=4-8-12; note=non-369 exact sum; tests whether resonance, not numerology, explains it
- rank 2: **369_exact_sum** — score=0.510698; freqs=3-6-9; note=3 + 6 = 9; target myth case
- rank 3: **369_detuned** — score=0.230851; freqs=3-6.25-9; note=same digits idea, broken sum resonance
- rank 4: **357_non_sum** — score=0.028984; freqs=3-5-7; note=odd-number control; 3 + 5 != 7
- rank 5: **random_non_sum** — score=0.000839762; freqs=9.684-5.911-5.372; note=random control

## wave_lattice
- rank 1: **369_radial_phase_locked** — score=0.490625; freqs=3-6-9; note=target: 3 rings, 3 frequencies, 120-degree phase cycle
- rank 2: **369_random_phase** — score=0.461806; freqs=3-6-9; note=same frequencies, broken phase geometry
- rank 3: **357_non_sum** — score=0.291504; freqs=3-5-7; note=nonlinear control; no f3+f5=f7 match
- rank 4: **4812_exact_sum** — score=0.213923; freqs=4-8-12; note=non-369 exact-sum harmonic triad
- rank 5: **single_6** — score=0.0253913; freqs=6-6-6; note=single-frequency control with comparable geometry

## How to interpret
- If `369_exact_sum` wins but `4812_exact_sum` also wins, the effect is probably harmonic triad resonance, not mystical numerology.
- If `369_phase_locked` beats `369_random_phase`, phase geometry matters.
- If detuned/non-sum controls beat 369, the hypothesis is weak for this model.
- A real anomaly should reproduce across seeds, grid sizes, time steps, and damping settings.