# Acoustic Waveguide 4->8->12

Low-frequency acoustic/phononic analog of the distributed phase-matched bridge.

## Direct Answers

1. Can the acoustic analog recover clean 120 kHz purity? candidates=1; best_purity=0.999610626442031; best=phase_matched_short_48cell.
2. Does phase matching predict success and mismatch failure? success=True; mismatch_failure=True.
3. Do controls stay dead? True; max_leakage=0.0.
4. Required guide length bench-scale? True; best_length_m=0.058.
5. Nonlinear drive/readout plausible? pressure=328.76744698434413 Pa, class=plausible, feedthrough_risk=0.02424264032061959.
6. Next step: acoustic bench design focused on nonlinear drive/readout and feedthrough suppression.

## Rows

- a001 phase_matched_64cell_baseline: role=discovery, topology=phase_matched, category=not_promoted, lock=0.9990554845040679, bridge=0.5261723644547974, purity=0.9943694848398767, growth=1.2786033862672974, length=0.07639437268410976, pressure=plausible.
- a002 phase_matched_80cell_low_loss: role=discovery, topology=phase_matched, category=not_promoted, lock=0.9999426132555992, bridge=2.3303518513195585e-06, purity=0.41813064811946093, growth=0.029793698328401806, length=0.07639437268410976, pressure=plausible.
- a003 phase_matched_96cell_high_nonlinearity: role=discovery, topology=phase_matched, category=not_promoted, lock=0.0, bridge=0.0, purity=0.00022037737491087714, growth=0.0022503947817970452, length=0.07639437268410976, pressure=plausible.
- a004 phase_matched_longer_96cell: role=discovery, topology=phase_matched, category=not_promoted, lock=0.0, bridge=0.0, purity=0.0002596845789037251, growth=0.002108134765871401, length=0.105, pressure=plausible.
- a005 phase_matched_short_48cell: role=discovery, topology=phase_matched, category=acoustic_phase_bridge_candidate, lock=0.9993517564087016, bridge=4628.598328042856, purity=0.999610626442031, growth=26.9445267041662, length=0.058, pressure=plausible.
- a006 qpm_mild_mismatch_square: role=discovery, topology=qpm, category=not_promoted, lock=0.9979751070959949, bridge=0.013277076091968211, purity=0.8318761284997074, growth=0.8174696935655594, length=0.07639437268410976, pressure=plausible.
- a007 qpm_high_nonlinearity_80cell: role=discovery, topology=qpm, category=not_promoted, lock=0.9994189627967349, bridge=1.8496823040795757e-08, purity=0.017268454873829508, growth=0.06645524653304156, length=0.07639437268410976, pressure=plausible.
- a008 mild_dispersion_phase_trim: role=discovery, topology=phase_matched_trim, category=near_miss, lock=0.9992136137457979, bridge=2.2034350939522427, purity=0.9947186292502518, growth=1.1389804102260683, length=0.07639437268410976, pressure=plausible.
- c001 linear_no_nonlinearity_control: role=control, topology=control, category=control_dead, lock=0.0, bridge=0.0, purity=5.783451452928947e-17, growth=0.0, length=0.07639437268410976, pressure=plausible.
- c002 weak_nonlinearity_control: role=control, topology=control, category=control_dead, lock=0.9995528201974149, bridge=6.1026925264751056e-05, purity=0.021461392369395742, growth=0.4611320786144851, length=0.07639437268410976, pressure=plausible.
- c003 detuned_target_velocity_control: role=control, topology=control, category=control_dead, lock=0.9161796598845218, bridge=4.018897272705708e-08, purity=7.202149121081278e-06, growth=0.8630573244864341, length=0.07639437268410976, pressure=plausible.
- c004 phase_mismatched_control: role=control, topology=control, category=control_dead, lock=0.9994166690953092, bridge=2.5973045076211464e-05, purity=0.009303389095858294, growth=0.708232873701404, length=0.07639437268410976, pressure=plausible.
- c005 shuffled_frequency_control: role=control, topology=control, category=control_dead, lock=0.9997955621424395, bridge=4.809035761423456e-11, purity=1.7195277742773814e-08, growth=0.7447434426031041, length=0.07639437268410976, pressure=plausible.
- c006 too_short_guide_control: role=control, topology=control, category=control_dead, lock=0.9995644823709471, bridge=0.0010454799191525308, purity=0.27116443275044, growth=0.46068062836705165, length=0.013750987083139756, pressure=plausible.
- c007 too_lossy_guide_control: role=control, topology=control, category=control_dead, lock=0.0, bridge=0.0, purity=0.174821731686385, growth=8.965605395008346, length=0.07639437268410976, pressure=plausible.
- direct_40plus80_reference direct_40plus80_reference: role=ceiling_reference, topology=control, category=ceiling_reference_not_discovery, lock=0.9993330087585308, bridge=1.0, purity=0.8100529736630634, growth=1.776802419091411, length=0.07639437268410976, pressure=plausible.

## Notes

- Discovery rows drive only 40 kHz.
- No direct 80 kHz drive, no direct 120 kHz drive, and no target-frequency injection are used in discovery rows.
- The direct 40+80 row is a separated ceiling denominator only.
- Lock, bridge ratio, and envelope CV are scored on a settled pre-fade window so ramp-up and fade-out do not masquerade as envelope instability.
- Target purity is measured as 120 kHz band power divided by broad 20-160 kHz readout power.
- Pressure and feedthrough estimates are screening metrics, not hardware validation.
