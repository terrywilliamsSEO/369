# Physical 4->8->12 LC Bridge

This run translates the independently validated abstract 4->8->12 bridge into a three-resonator nonlinear LC interpretation. The simulated state remains normalized, while each preset supplies absolute resonant frequencies, capacitances, inductances, resistances, voltage/current scales, and joule-scale energy accounting.

## Direct Answers
1. Can the independent 4->8->12 bridge be expressed as a nonlinear LC resonator system? yes, as a normalized three-LC model with conservative nonlinear capacitance/mixing terms and passive saturation loss; physical_lc_bridge_expressed=True.
2. Required L, C, R, Q, coupling, and nonlinear parameters are listed below for each scale preset; the summary CSV/JSON carry the exact numeric fields.
3. Plausibility: Q values are mild; linear coupling fractions are about 0.00427045 and 0.00420169; nonlinear mixing is the aggressive part. Realism labels: physically plausible but needs circuit validation.
4. Does the physical LC version preserve lock >0.90? yes; worst lock=0.992108.
5. Does bridge ratio remain >1.5? yes; worst bridge ratio=1.60697.
6. Does purity remain >0.80? yes; worst purity=0.922789.
7. Does budget remain <0.005? yes; worst budget=5.10442e-05.
8. Are direct 8 drive, direct 12 drive, and target-frequency injection still absent? direct_8_absent=True, direct_12_absent=True, target_injection_absent=True.
9. Recommended next step: SPICE/ngspice validation first, then physical parameter refinement and spatial phase-matching modeling.

## Baseline Presets
- audio-scale: f=(440, 883.894, 1309.86) Hz, L=(0.01308, 0.006898, 0.004474) H, C=(1e-05, 4.7e-06, 3.3e-06) F, R=(0.9115, 0.9011, 0.4795) ohm, Q=(39.68, 42.52, 76.78) [mild, mild, mild], realism=0.933 (physically plausible but needs circuit validation).
  Metrics: lock=0.992495, bridge=1.60697, purity=0.922789, budget=5.10442e-05, gen_cv=0.13245, target_cv=0.0356446, max_jump=0.971944, near_slips=0.
  Energy/peaks: stored_peak=0.000615154 J, drive_work=0.00396334 J, resistive_loss=0.00369308 J, soft_limiter_loss=0.000247726 J, peak_V=(8.69592, 7.45427, 10.3929) V, peak_I=(0.241506, 0.192326, 0.280081) A.
- low-RF-scale: f=(1e+06, 2.00885e+06, 2.97696e+06) Hz, L=(2.533e-05, 1.336e-05, 8.661e-06) H, C=(1e-09, 4.7e-10, 3.3e-10) F, R=(4.011, 3.965, 2.11) ohm, Q=(39.68, 42.52, 76.78) [mild, mild, mild], realism=0.933 (physically plausible but needs circuit validation).
  Metrics: lock=0.992495, bridge=1.60697, purity=0.922789, budget=5.10442e-05, gen_cv=0.13245, target_cv=0.0356446, max_jump=0.971944, near_slips=0.
  Energy/peaks: stored_peak=6.15154e-10 J, drive_work=3.96334e-09 J, resistive_loss=3.69308e-09 J, soft_limiter_loss=2.47726e-10 J, peak_V=(0.869592, 0.745427, 1.03929) V, peak_I=(0.00548877, 0.00437104, 0.00636549) A.
- arbitrary-normalized-scale: f=(0.18, 0.361593, 0.535853) Hz, L=(0.7818, 0.1937, 0.08822) H, C=(1, 1, 1) F, R=(0.02228, 0.01035, 0.003868) ohm, Q=(39.68, 42.52, 76.78) [mild, mild, mild], realism=0.875 (physically plausible but needs circuit validation).
  Metrics: lock=0.992495, bridge=1.60697, purity=0.922789, budget=5.10442e-05, gen_cv=0.13245, target_cv=0.0356446, max_jump=0.971944, near_slips=0.
  Energy/peaks: stored_peak=0.615154 J, drive_work=3.96334 J, resistive_loss=3.69308 J, soft_limiter_loss=0.247726 J, peak_V=(0.869592, 0.511039, 0.597025) V, peak_I=(0.987979, 1.14765, 1.99456) A.

## Model Notes

- Each resonator is represented by `L_i`, `C_i`, and `R_i` with `f_i = 1 / (2*pi*sqrt(L_i*C_i))` and `Q_i = omega_i*L_i/R_i`.
- The source drive is a voltage/current-equivalent force applied only to resonator 1. The generated and target resonators receive no direct drive.
- The linear coupling coefficients are weak normalized LC coupling terms. The nonlinear varactor and mixing coefficients are the intentionally aggressive bridge mechanism.
- The soft limiter is passive saturation/loss; there is no active limiter work term in this first physicalization.
- `direct_source_plus_generated_reference_ceiling` is used only as the bridge-ratio denominator and is never a discovery row.

## Candidate Constants
```json
{
  "name": "physicalized_independent_412_candidate",
  "mode_freqs": [
    4.0,
    8.0354,
    11.907835129474883
  ],
  "drive_freqs": [
    4.0
  ],
  "drive_modes": [
    0
  ],
  "drive_phases": [
    0.0
  ],
  "target_6": 8.0,
  "target_9": 12.0,
  "stage_a_nonlinear_strength": 0.5,
  "stage_b_nonlinear_strength": 0.8959006451612903,
  "stage_a_to_stage_b_coupling": 1.2201290322580647,
  "stage_b_to_receiver_coupling": 1.200483870967742,
  "stage_a_damping": 0.7,
  "stage_b_damping": 0.9800000000000001,
  "receiver_damping": 0.8140000000000001,
  "drive_amp": 0.07,
  "varactor_coefficient": 0.19,
  "spark_strength": 0.079568,
  "spark_threshold": 0.035,
  "stage_b_phase_bias_deg": 24.8,
  "reference_role": "discovery_candidate",
  "note": "Physicalization of the independent strict 4->8->12 candidate: target detuning -0.08, Stage A offset +0.040, generated damping factor 1.05, A->B coupling 0.90, limiter 0.03. Discovery drive is source-only; no direct 8 drive, no direct 12 drive, no target-frequency injection."
}
```