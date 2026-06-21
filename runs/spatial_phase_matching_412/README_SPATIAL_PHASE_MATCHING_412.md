# Spatial Phase Matching 4->8->12

Distributed 1D coupled-mode test for explicit phase matching and quasi-phase matching.

## Summary

- Discovery rows: 47.
- Controls: 4.
- Promoted spatial bridge candidates: 17.
- Near misses: 6.
- Controls dead: True with max leakage 0.0647121085184914.

## Direct Answers

1. Does explicit phase matching recover coherent 4->8->12 lock? Yes. Best row s043 (co_directional_phase_matched) reached lock=0.9991278141488681 and bridge=4.748881251878379.
2. Does QPM outperform lumped and mismatched controls? True. Best QPM row s005 reached lock=0.744985690703558; it was a near miss, not the best promoted topology.
3. Does phase mismatch predict failure? True. Deliberately mismatched rows were rejected for phase mismatch.
4. Do controls stay dead? True; max_control_leakage=0.0647121085184914.
5. Is the likely physical realization distributed/waveguide-like rather than lumped LC? Yes. Promoted rows are distributed phase-matched, backward-wave, or alternating-sign topologies; the compact lumped-equivalent row is rejected for phase mismatch.
6. Next step: SPICE distributed ladder export, then physical waveguide model.

## Top Rows

- s043 nonlinear_strength_1.55: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9991278141488681, bridge=4.748881251878379, purity=0.997300188575618, growth=20.196272876601334, budget=3.4369509047502676e-12.
- s042 nonlinear_strength_1.20: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9990204449617943, bridge=3.166876883034445, purity=0.997295771985137, growth=29.302077584194112, budget=2.232912189732089e-12.
- s002 codirectional_phase_matched: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9989373691137109, bridge=2.3073148353118826, purity=0.9971974587538963, growth=38.825393455753314, budget=1.7093113459158328e-12.
- s037 group_velocity_mismatch_+0.00: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9989373691137109, bridge=2.3073148353118826, purity=0.9971974587538963, growth=38.825393455753314, budget=1.7093113459158328e-12.
- s049 damping_loss_0.045: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9989373691137109, bridge=2.3073148353118826, purity=0.9971974587538963, growth=38.825393455753314, budget=1.7093113459158328e-12.
- s046 coupling_strength_0.20: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9988270294143726, bridge=2.2975041233982108, purity=0.9966053848547695, growth=38.59930772993998, budget=1.7067170988353715e-12.
- s041 nonlinear_strength_0.80: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9987303376571485, bridge=1.50731869444917, purity=0.9969342077084634, growth=55.028244611685395, budget=1.3154495316340826e-12.
- s045 coupling_strength_0.12: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.998380842581517, bridge=2.3164009768412224, purity=0.9976291351131759, growth=39.025254176224315, budget=1.7128032561255883e-12.
- s007 alternating_coupling_sign: topology=alternating_coupling_sign, category=spatial_phase_bridge_candidate, lock=0.9980799015152018, bridge=2.5362688236397286, purity=0.9984360923382771, growth=26.865946703614465, budget=2.1276841885105203e-12.
- s035 phase_matched_length_32_cells_96: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9978867711569518, bridge=2.352753175691199, purity=0.9979527521410321, growth=39.80827206796015, budget=1.6891941101224498e-12.
- s044 coupling_strength_0.08: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9978529925338772, bridge=2.3240322705158594, purity=0.9979138510074396, growth=39.185397081371015, budget=1.7134727168731392e-12.
- s034 phase_matched_length_18_cells_48: topology=co_directional_phase_matched, category=spatial_phase_bridge_candidate, lock=0.9971339817192442, bridge=2.242003747282244, purity=0.9947108907051027, growth=37.4755292517865, budget=1.7218089855934964e-12.

## Controls

- s008 randomized_grating_control: category=control_dead, lock=0.3443322565388153, bridge=0.13580829649655307, growth=12.143417201106663, leakage=0.0647121085184914.
- s009 linear_no_nonlinearity_control: category=control_dead, lock=0.0, bridge=0.0, growth=0.0, leakage=0.0647121085184914.
- s010 detuned_target_control: category=control_dead, lock=0.026813128902179562, bridge=2.626752281439604e-05, growth=0.333758304826872, leakage=0.0647121085184914.
- s011 shuffled_frequency_control: category=control_dead, lock=0.007838778362510486, bridge=2.1549300470808645e-08, growth=0.14809057102937298, leakage=0.0647121085184914.

## Notes

- Discovery rows drive only the source band at 4.
- Direct 4+8 is a separated ceiling denominator only.
- The model is normalized coupled-mode physics for topology screening, not a hardware proof.
