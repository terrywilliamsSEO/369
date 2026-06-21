# SPICE 4->8->12 Component Realism

Component-only refinement track. Behavioral current mixing is forbidden for discovery rows.

## Direct Answers

1. Did any component-plausible SPICE row cross bridge ratio >1.5? True; cases=c008;c013;c018;c023;c028;c033.
2. Did any component-plausible row become a near miss with bridge ratio >1.0? 0.
3. Did linear, weak-nonlinearity, detuned, and shuffled controls stay dead? False; max_control_leakage=0.600079139285388.
4. Which component family was closest to the behavioral proxy? case=c008, variant=diode_bridge_mixer.
5. Were successful or near-miss rows physically plausible, aggressive, or unrealistic? none_promoted; closest_stress=plausible.
6. Next step: deeper component sweep and spatial phase-matching model before physical parameter refinement.

## Top Component Rows

- c008 diode_bridge_mixer: status=ran_successfully, lock=0.01751786020609064, purity=0.9891548487196253, bridge=1.647441888979745, growth=1.2842347606010147, stress=plausible, category=reject_due_to_control_leakage.
- c018 back_to_back_varactor_stack: status=ran_successfully, lock=0.016446472307288146, purity=0.9864243781864668, bridge=1.5738780857154664, growth=0.9844631592794437, stress=plausible, category=reject_due_to_control_leakage.
- c003 anti_parallel_diode_mixer: status=ran_successfully, lock=0.01607174631826026, purity=0.9844911885590285, bridge=1.4042045652545048, growth=0.9153768446886396, stress=plausible, category=reject_due_to_control_leakage.
- c033 hybrid_varactor_plus_saturable_inductor: status=ran_successfully, lock=0.0248827448707826, purity=0.9076540010820803, bridge=2.2476511709646925, growth=0.7966699302432376, stress=plausible, category=reject_due_to_control_leakage.
- c013 varactor_pair_mixer: status=ran_successfully, lock=0.024879716647353015, purity=0.9076794753116296, bridge=2.248285539112825, growth=0.7966731773523938, stress=plausible, category=reject_due_to_control_leakage.
- c002 anti_parallel_diode_mixer: status=ran_successfully, lock=0.018594896837897786, purity=0.9907981049125206, bridge=0.03027798917466447, growth=1.5839003067384931, stress=plausible, category=reject_due_to_control_leakage.
- c012 varactor_pair_mixer: status=ran_successfully, lock=0.01627924051194128, purity=0.985727487918857, bridge=0.020363156427812303, growth=0.9564528983012299, stress=plausible, category=reject_due_to_control_leakage.
- c032 hybrid_varactor_plus_saturable_inductor: status=ran_successfully, lock=0.016185926594372856, purity=0.9857194183019315, bridge=0.020350440480877616, growth=0.956250089571517, stress=plausible, category=reject_due_to_control_leakage.
- c017 back_to_back_varactor_stack: status=ran_successfully, lock=0.01860897676618244, purity=0.9909598196276774, bridge=0.03135284404191694, growth=1.5989854765659919, stress=plausible, category=reject_due_to_control_leakage.
- c007 diode_bridge_mixer: status=ran_successfully, lock=0.018909755154904062, purity=0.9915763739521234, bridge=0.03737918256640442, growth=1.7139298675490946, stress=plausible, category=reject_due_to_control_leakage.

## Direct 4+8 Ceiling References

- ref_direct_4plus8_c0p75_d1p5_l0p5_z20_vc0p5_conservative_m0p5: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.
- ref_direct_4plus8_c1_d1_l1_z100_vc1_default_m1: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.
- ref_direct_4plus8_c1p25_d1p5_l2_z100_vc1_default_m1: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.
- ref_direct_4plus8_c1p25_d1p5_l2_z100_vc4_default_m1: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.
- ref_direct_4plus8_c1p5_d2_l1_z100_vc0p02_default_m1: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.
- ref_direct_4plus8_c1p5_d2_l1_z500_vc2_relaxed_m2: status=ran_successfully, direct_8_drive=True, direct_12_drive=False, target_frequency_injection=False.

## Convergence Failures

- c015 varactor_pair_mixer: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 0.000868919, timestep = 3.82067e-13: trouble with dvarp-instance dvp12a; log=c015_vpair_c0p75_d1p5_l0p5_z20_conservative_m0p5.log
- c035 hybrid_varactor_plus_saturable_inductor: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 0.000868919, timestep = 3.82067e-13: trouble with dvarp-instance dvp12a; log=c035_hybrid_c0p75_d1p5_l0p5_z20_conservative_m0p5.log

## Notes

- Discovery rows use component-plausible diode, varactor, saturable, hybrid, or trap networks only.
- Behavioral current mixing is present only as historical calibration metadata.
- Direct 4+8 references are separated ceiling denominators and are not discovery rows.
