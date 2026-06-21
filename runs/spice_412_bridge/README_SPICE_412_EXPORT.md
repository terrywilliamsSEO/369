# SPICE 4->8->12 Bridge Export

This track exports the physical 4->8->12 LC bridge into ngspice-compatible netlists. Discovery netlists drive only resonator 1. The direct 4+8 netlist is separated as a ceiling/reference denominator and is not a discovery row.

## Direct Answers
1. Which netlists ran successfully under ngspice? none in this run; execution_statuses=skipped_no_ngspice.
2. Did any source-only SPICE netlist show target build-up near 12? not_run; circuits=.
3. Did any nonlinear model variant roughly reproduce the Python LC behavior? not_run; circuits=.
4. Did the linear-no-nonlinearity control fail as expected? not_run.
5. Is the required nonlinear element plausible, aggressive, or unrealistic? behavioral proxy remains aggressive; diode/varactor/saturable variants are first-pass realism checks.
6. Next step: Run ngspice if available, then component refinement, parameter sweep, and spatial phase-matching modeling.

## Exported Netlists
- audio_412_bridge: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=behavioral_proxy_current, netlist=audio_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=behavioral_proxy_current, netlist=low_rf_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=behavioral_proxy_current, netlist=normalized_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- audio_412_bridge_voltage_dependent_capacitance_proxy: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=voltage_dependent_capacitance_proxy, netlist=audio_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge_voltage_dependent_capacitance_proxy: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=voltage_dependent_capacitance_proxy, netlist=low_rf_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge_voltage_dependent_capacitance_proxy: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=voltage_dependent_capacitance_proxy, netlist=normalized_412_bridge_voltage_dependent_capacitance_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- audio_412_bridge_diode_pair_proxy: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=diode_pair_proxy, netlist=audio_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge_diode_pair_proxy: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=diode_pair_proxy, netlist=low_rf_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge_diode_pair_proxy: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=diode_pair_proxy, netlist=normalized_412_bridge_diode_pair_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- audio_412_bridge_varactor_diode_model_proxy: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=varactor_diode_model_proxy, netlist=audio_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge_varactor_diode_model_proxy: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=varactor_diode_model_proxy, netlist=low_rf_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge_varactor_diode_model_proxy: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=varactor_diode_model_proxy, netlist=normalized_412_bridge_varactor_diode_model_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- audio_412_bridge_saturable_inductor_proxy: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=saturable_inductor_proxy, netlist=audio_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge_saturable_inductor_proxy: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=saturable_inductor_proxy, netlist=low_rf_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge_saturable_inductor_proxy: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=saturable_inductor_proxy, netlist=normalized_412_bridge_saturable_inductor_proxy.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- audio_412_bridge_linear_no_nonlinearity_control: status=skipped_no_ngspice, role=discovery, scale=audio-scale, variant=linear_no_nonlinearity_control, netlist=audio_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- low_rf_412_bridge_linear_no_nonlinearity_control: status=skipped_no_ngspice, role=discovery, scale=low-RF-scale, variant=linear_no_nonlinearity_control, netlist=low_rf_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- normalized_412_bridge_linear_no_nonlinearity_control: status=skipped_no_ngspice, role=discovery, scale=arbitrary-normalized-scale, variant=linear_no_nonlinearity_control, netlist=normalized_412_bridge_linear_no_nonlinearity_control.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.
- reference_direct_4plus8: status=skipped_no_ngspice, role=ceiling_reference, scale=low-RF-scale, variant=behavioral_proxy_current, netlist=reference_direct_4plus8.cir.
  Drive flags: direct_8=True, direct_12=False, target_injection=False.
  Execution note: ngspice not found; pass --ngspice-path or add ngspice to PATH.

## Circuit Notes

- Each resonator is a capacitor in parallel with an inductor branch whose series resistance matches the physical Q.
- Weak linear coupling is exported as mutual inductive coupling between adjacent resonators.
- Nonlinear variants include behavioral current mixing, voltage-dependent capacitance, diode pairs, varactor-diode models, saturable-inductor proxies, and a linear no-nonlinearity control.
- The behavioral current variant remains the most aggressive and closest to the Python LC abstraction.
- The diode/varactor/saturable variants are first-pass realism checks, not yet tuned component implementations.