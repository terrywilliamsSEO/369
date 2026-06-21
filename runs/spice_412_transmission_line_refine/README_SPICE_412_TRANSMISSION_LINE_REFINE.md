# SPICE 4->8->12 Transmission-Line Refinement

Normalized LC transmission-line refinement of the distributed phase-matched bridge.

## Direct Answers

1. Can a less-behavioral transmission-line ladder preserve the lock? candidates=1; best=t001 lock=0.997206257893873 bridge=8.261740025175394.
2. Does lowering behavioral dependency weaken or preserve the bridge? behavioral_dependency_lower_than_envelope=True; phase_matched_dependency=0.36.
3. Does phase mismatch still kill lock? raw_lock=False; material_bridge_suppressed=True; mismatched_lock=0.9895421305710689, mismatched_bridge=0.002706840219315203.
4. Does QPM help? True; qpm_lock=0.9619187789443745, qpm_bridge=0.006002507753474411.
5. Do controls remain dead? True; max_control_leakage=0.0.
6. Next step: physical waveguide modeling, then PCB/transmission-line approximation.

## Rows

- t001 tl_phase_matched_ladder: status=ran_successfully, category=spice_tl_phase_candidate, lock=0.997206257893873, bridge=8.261740025175394, purity=0.961441074707597, behavioral_dependency=0.36.
- t002 tl_qpm_ladder: status=ran_successfully, category=not_promoted, lock=0.9619187789443745, bridge=0.006002507753474411, purity=0.8801584442205528, behavioral_dependency=0.38.
- c001 tl_mismatched_ladder_control: status=ran_successfully, category=control_dead, lock=0.9895421305710689, bridge=0.002706840219315203, purity=0.9906970953328595, behavioral_dependency=0.38.
- c002 tl_lumped_equivalent_control: status=ran_successfully, category=control_dead, lock=0.9999999999202711, bridge=0.0022860774940478, purity=0.9996407805374732, behavioral_dependency=0.38.
- c003 tl_linear_no_nonlinearity_control: status=ran_successfully, category=control_dead, lock=0.8671168846198917, bridge=1.5213910956415734e-16, purity=2.0341306593249395e-05, behavioral_dependency=0.08.
- c004 tl_detuned_target_control: status=ran_successfully, category=control_dead, lock=0.9997257263378, bridge=0.00023676822573669926, purity=0.9323354278245022, behavioral_dependency=0.38.
- c005 tl_shuffled_frequency_control: status=ran_successfully, category=control_dead, lock=0.9885522739545989, bridge=5.335490631367906e-09, purity=0.002744815871326166, behavioral_dependency=0.38.
- direct_4plus8_reference tl_direct_4plus8_reference: status=ran_successfully, category=ceiling_reference_not_discovery, lock=0.9989413192542563, bridge=, purity=0.9913873688353746, behavioral_dependency=0.36.

## Notes

- LC ladder propagation and loading are explicit SPICE components.
- Behavioral sources remain for distributed nonlinear mixing and saturation proxies.
- Direct 4+8 is a separated ceiling reference only.
