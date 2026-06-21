# SPICE 4->8->12 Bridge Export

This track exports the physical 4->8->12 LC bridge into ngspice-compatible netlists. The discovery netlists drive only resonator 1. The direct 4+8 netlist is separated as a ceiling/reference denominator and is not a discovery row.

## Direct Answers
1. Were valid SPICE netlists generated? True.
2. Does ngspice run locally? False; completed=False.
3. Does the SPICE transient preserve target build-up without direct 8/12 drive? not_run.
4. Does SPICE roughly match Python lock, purity, and bridge-ratio behavior? not_run for local execution; see summary metrics when ngspice runs.
5. Is the nonlinear element physically plausible, aggressive, or unrealistic? aggressive behavioral varactor/mixing proxy; needs component-level refinement.
6. Next step: Install/run ngspice if missing; then refine nonlinear components, sweep parameters, and add spatial phase-matching modeling.

## Exported Netlists
- audio_412_bridge: role=discovery, scale=audio-scale, f=(440, 883.894, 1309.86) Hz, ngspice_run=False, netlist=audio_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not installed on PATH.
- low_rf_412_bridge: role=discovery, scale=low-RF-scale, f=(1e+06, 2.00885e+06, 2.97696e+06) Hz, ngspice_run=False, netlist=low_rf_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not installed on PATH.
- normalized_412_bridge: role=discovery, scale=arbitrary-normalized-scale, f=(0.18, 0.361593, 0.535853) Hz, ngspice_run=False, netlist=normalized_412_bridge.cir.
  Drive flags: direct_8=False, direct_12=False, target_injection=False.
  Execution note: ngspice not installed on PATH.
- reference_direct_4plus8: role=ceiling_reference, scale=low-RF-scale, f=(1e+06, 2.00885e+06, 2.97696e+06) Hz, ngspice_run=False, netlist=reference_direct_4plus8.cir.
  Drive flags: direct_8=True, direct_12=False, target_injection=False.
  Execution note: ngspice not installed on PATH.

## Circuit Notes

- Each resonator is a capacitor in parallel with an inductor branch whose series resistance matches the physical Q.
- Weak linear coupling is exported as mutual inductive coupling between adjacent resonators.
- Varactor-like behavior is exported with behavioral current sources using `ddt(V(node))`.
- Nonlinear mixing is exported as behavioral current injection scaled from the normalized Python LC model.
- The soft limiter is a passive voltage-drop-dependent conductance between resonators.
- These behavioral nonlinear elements are deliberately marked aggressive: they preserve the bridge mechanism for SPICE testing but are not yet a bill of materials.