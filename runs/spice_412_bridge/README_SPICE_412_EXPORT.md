# SPICE 4->8->12 Bridge Export

This track exports the physical 4->8->12 LC bridge into ngspice-compatible netlists. Discovery netlists drive only resonator 1. The direct 4+8 netlist is separated as a ceiling/reference denominator and is not a discovery row.

## Direct Answers
1. Which netlists ran successfully under ngspice? ; execution_statuses=failed_to_converge;ran_successfully.
2. Did any source-only SPICE netlist show target build-up near 12? True; circuits=normalized_412_bridge;normalized_412_bridge_voltage_dependent_capacitance_proxy;audio_412_bridge_diode_pair_proxy;low_rf_412_bridge_diode_pair_proxy;audio_412_bridge_varactor_diode_model_proxy;low_rf_412_bridge_varactor_diode_model_proxy;normalized_412_bridge_varactor_diode_model_proxy;audio_412_bridge_saturable_inductor_proxy;low_rf_412_bridge_saturable_inductor_proxy;normalized_412_bridge_saturable_inductor_proxy.
3. Did any nonlinear model variant roughly reproduce the Python LC behavior? False; circuits=.
4. Did the linear-no-nonlinearity control fail as expected? True.
5. Is the required nonlinear element plausible, aggressive, or unrealistic? behavioral proxy remains aggressive; diode/varactor/saturable variants are first-pass realism checks.
6. Next step: component refinement, parameter sweep, then spatial phase-matching modeling.

## Exported Netlists
- audio_412_bridge: status=failed_to_converge, role=discovery, scale=audio-scale, variant=behavioral_proxy_current, netlist=audio_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 0.00053352, timestep = 2.71702e-16: trouble with node "n1"; log=audio_412_bridge.log.
- low_rf_412_bridge: status=failed_to_converge, role=discovery, scale=low-RF-scale, variant=behavioral_proxy_current, netlist=low_rf_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 3.19473e-08, timestep = 1.06062e-19: trouble with node "n1"; log=low_rf_412_bridge.log.
- normalized_412_bridge: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=behavioral_proxy_current, netlist=normalized_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=2.06766, lock=0.997003, bridge=0.788167, purity=0.971359, gen_cv=0.0509967, max_jump=0.274669.
- audio_412_bridge_voltage_dependent_capacitance_proxy: status=failed_to_converge, role=discovery, scale=audio-scale, variant=voltage_dependent_capacitance_proxy, netlist=audio_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 0.000229285, timestep = 2.28135e-16: cause unrecorded.; log=audio_412_bridge_voltage_dependent_capacitance_proxy.log.
- low_rf_412_bridge_voltage_dependent_capacitance_proxy: status=failed_to_converge, role=discovery, scale=low-RF-scale, variant=voltage_dependent_capacitance_proxy, netlist=low_rf_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 1.65e-08, timestep = 0: trouble with node "n3"; log=low_rf_412_bridge_voltage_dependent_capacitance_proxy.log.
- normalized_412_bridge_voltage_dependent_capacitance_proxy: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=voltage_dependent_capacitance_proxy, netlist=normalized_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.6593, lock=0.0303379, bridge=9.34203e-07, purity=0.587838, gen_cv=0.477194, max_jump=3.01559.
- audio_412_bridge_diode_pair_proxy: status=ran_successfully, role=discovery, scale=audio-scale, variant=diode_pair_proxy, netlist=audio_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=0.59813, lock=0.0514178, bridge=nan, purity=0.977497, gen_cv=0.697893, max_jump=2.70246.
- low_rf_412_bridge_diode_pair_proxy: status=ran_successfully, role=discovery, scale=low-RF-scale, variant=diode_pair_proxy, netlist=low_rf_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=2.52347, lock=0.038204, bridge=nan, purity=0.714221, gen_cv=0.480426, max_jump=2.76132.
- normalized_412_bridge_diode_pair_proxy: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=diode_pair_proxy, netlist=normalized_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.4512, lock=0.0373672, bridge=1.90682e-07, purity=0.291544, gen_cv=0.480468, max_jump=3.01851.
- audio_412_bridge_varactor_diode_model_proxy: status=ran_successfully, role=discovery, scale=audio-scale, variant=varactor_diode_model_proxy, netlist=audio_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.43749, lock=0.0427067, bridge=nan, purity=0.995281, gen_cv=0.68948, max_jump=2.68004.
- low_rf_412_bridge_varactor_diode_model_proxy: status=ran_successfully, role=discovery, scale=low-RF-scale, variant=varactor_diode_model_proxy, netlist=low_rf_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=0.211362, lock=0.061527, bridge=nan, purity=0.657039, gen_cv=0.488256, max_jump=3.10847.
- normalized_412_bridge_varactor_diode_model_proxy: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=varactor_diode_model_proxy, netlist=normalized_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=0.306872, lock=0.0397857, bridge=1.01088e-06, purity=0.844358, gen_cv=0.490161, max_jump=2.818.
- audio_412_bridge_saturable_inductor_proxy: status=ran_successfully, role=discovery, scale=audio-scale, variant=saturable_inductor_proxy, netlist=audio_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.68491, lock=0.0268445, bridge=nan, purity=0.982124, gen_cv=0.616417, max_jump=3.09741.
- low_rf_412_bridge_saturable_inductor_proxy: status=ran_successfully, role=discovery, scale=low-RF-scale, variant=saturable_inductor_proxy, netlist=low_rf_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.53436, lock=0.130529, bridge=nan, purity=0.994965, gen_cv=0.529351, max_jump=3.13427.
- normalized_412_bridge_saturable_inductor_proxy: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=saturable_inductor_proxy, netlist=normalized_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.65869, lock=0.0319572, bridge=9.52998e-07, purity=0.597967, gen_cv=0.489623, max_jump=2.83599.
- audio_412_bridge_linear_no_nonlinearity_control: status=ran_successfully, role=discovery, scale=audio-scale, variant=linear_no_nonlinearity_control, netlist=audio_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=3.91804, lock=0.0147665, bridge=nan, purity=1.67561e-06, gen_cv=0.489259, max_jump=1.7422.
- low_rf_412_bridge_linear_no_nonlinearity_control: status=ran_successfully, role=discovery, scale=low-RF-scale, variant=linear_no_nonlinearity_control, netlist=low_rf_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=3.91849, lock=0.0141437, bridge=nan, purity=1.66029e-06, gen_cv=0.489295, max_jump=1.73949.
- normalized_412_bridge_linear_no_nonlinearity_control: status=ran_successfully, role=discovery, scale=arbitrary-normalized-scale, variant=linear_no_nonlinearity_control, netlist=normalized_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=3.91805, lock=0.0146868, bridge=7.19928e-15, purity=1.68388e-06, gen_cv=0.48931, max_jump=1.74166.
- reference_direct_4plus8: status=ran_successfully, role=ceiling_reference, scale=arbitrary-normalized-scale, variant=behavioral_proxy_current, netlist=reference_direct_4plus8.cir.
  Drive flags: direct_8=True, direct_12=False, target_injection=False.
  SPICE metrics: target_growth=1.57498, lock=0.996552, bridge=1, purity=0.883886, gen_cv=0.0585142, max_jump=0.245885.

## Circuit Notes

- Each resonator is a capacitor in parallel with an inductor branch whose series resistance matches the physical Q.
- Weak linear coupling is exported as mutual inductive coupling between adjacent resonators.
- Nonlinear variants include behavioral current mixing, voltage-dependent capacitance, diode pairs, varactor-diode models, saturable-inductor proxies, and a linear no-nonlinearity control.
- The behavioral current variant remains the most aggressive and closest to the Python LC abstraction.
- The diode/varactor/saturable variants are first-pass realism checks, not yet tuned component implementations.