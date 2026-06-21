# SPICE 4->8->12 Nonlinearity Refinement

Focused ngspice parameter sweep for nonlinear component implementations of the physical 4->8->12 LC bridge.
Discovery rows drive only resonator 1. Direct 4+8 rows are separated ceiling/reference denominators.

## Direct Answers

1. Did any SPICE nonlinear variant cross bridge ratio >1.5? True; cases=r038;r042.
2. Did the linear no-nonlinearity control remain dead? True.
3. Which nonlinear model is closest to Python LC behavior? case=r042, variant=behavioral_proxy_current, distance=1.067996114467785.
4. Are successful variants behavioral-only or component-plausible? behavioral-only.
5. Which rows failed convergence and why? r008;r009;r010;r011;r013;r014;r039;r040;r041;r044;r045;r046;r047;r048;r049;r050;r051;r052;r053;r054. See summary CSV failure reasons.
6. Next step: component-level refinement to replace behavioral mixing, then parameter sweep.

## Sweep Axes

- nonlinear strength scale: 0.25, 0.5, 1.0, 2.0, 4.0, 8.0
- limiter/conductance scale: 0.25, 0.5, 1.0, 2.0, 4.0
- coupling scale: 0.5, 0.75, 1.0, 1.25, 1.5
- drive amplitude scale: 0.5, 1.0, 1.5, 2.0
- solver tolerances: conservative, default, relaxed
- max timestep scale: 0.5, 1.0, 2.0

## Top Rows By Python-LC Distance

- r042 behavioral_proxy_current: status=ran_successfully, lock=0.9961927017977427, purity=0.9816579363872546, bridge=1.5631690074282802, target_band_growth=1.2767135824822675, category=spice_behavioral_bridge_candidate.
- r001 behavioral_proxy_current: status=ran_successfully, lock=0.9970400732873074, purity=0.9716873341117486, bridge=0.8063931446859259, target_band_growth=2.0578140070073077, category=not_promoted.
- r036 behavioral_proxy_current: status=ran_successfully, lock=0.9907183438090142, purity=0.9901091072766461, bridge=0.3856280111999405, target_band_growth=6.947276068863883, category=not_promoted.
- r037 behavioral_proxy_current: status=ran_successfully, lock=0.9969474035783781, purity=0.988987390400094, bridge=0.5267290332558507, target_band_growth=2.4725992372307, category=not_promoted.
- r038 behavioral_proxy_current: status=ran_successfully, lock=0.9952072248111854, purity=0.8135073266551713, bridge=4.231482578451208, target_band_growth=6.123897393245585, category=spice_behavioral_bridge_candidate.
- r043 behavioral_proxy_current: status=ran_successfully, lock=0.7356623615392921, purity=0.9757029632104598, bridge=0.5486443648011831, target_band_growth=1.2969380022152877, category=not_promoted.
- r004 varactor_diode_model_proxy: status=ran_successfully, lock=0.039785738486740066, purity=0.8443577385211225, bridge=1.044119756041783e-06, target_band_growth=0.3068715192175163, category=not_promoted.
- r006 hybrid_varactor_plus_saturable_inductor: status=ran_successfully, lock=0.04027803261411437, purity=0.8421059010839933, bridge=1.0293119646917504e-06, target_band_growth=0.30476107991345636, category=not_promoted.
- r055 hybrid_varactor_plus_saturable_inductor: status=ran_successfully, lock=0.03298425374683542, purity=0.8054726345844475, bridge=0.0003031136647816038, target_band_growth=2.147907563741264, category=not_promoted.
- r056 hybrid_varactor_plus_saturable_inductor: status=ran_successfully, lock=0.027287401338046215, purity=0.631475737798508, bridge=4.150138414067623e-06, target_band_growth=0.9900044604887152, category=not_promoted.

## Convergence Failures

- r008 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 21.4592, timestep = 6.8369e-13: trouble with node "n3"; log=r008_beh_ns2_lim1_k1p25_drv1p5_default_m1.log
- r009 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 10.2646, timestep = 2.68569e-14: trouble with node "n3"; log=r009_beh_ns4_lim1_k1p25_drv1p5_default_m1.log
- r010 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 4.69732, timestep = 1.43778e-12: trouble with node "n1"; log=r010_beh_ns8_lim0p5_k1p25_drv2_relaxed_m2.log
- r011 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 16.6604, timestep = 0: trouble with node "n3"; log=r011_beh_ns2_lim0p5_k1p5_drv1p5_default_m1.log
- r013 voltage_dependent_capacitance_proxy: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 26.5815, timestep = 6.09345e-13: trouble with node "n2"; log=r013_vcap_ns4_lim1_k1p25_drv1p5_default_m1.log
- r014 voltage_dependent_capacitance_proxy: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 9.7801, timestep = 1.51486e-12: trouble with node "n2"; log=r014_vcap_ns8_lim0p5_k1p25_drv2_relaxed_m2.log
- r039 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 6.11778, timestep = 0: trouble with node "n3"; log=r039_beh_ns8_lim1_k1p25_drv1p5_default_m1.log
- r040 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 17.0455, timestep = 5.17073e-13: trouble with node "n3"; log=r040_beh_ns2_lim0p25_k1p25_drv1p5_default_m1.log
- r041 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 17.0058, timestep = 0: trouble with node "n3"; log=r041_beh_ns2_lim0p5_k1p25_drv1p5_default_m1.log
- r044 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 20.1267, timestep = 4.49434e-13: trouble with node "n3"; log=r044_beh_ns2_lim1_k0p5_drv1p5_default_m1.log
- r045 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 21.8576, timestep = 5.03779e-13: trouble with node "n3"; log=r045_beh_ns2_lim1_k0p75_drv1p5_default_m1.log
- r046 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 19.8949, timestep = 0: trouble with node "n3"; log=r046_beh_ns2_lim1_k1_drv1p5_default_m1.log
- r047 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 25.2729, timestep = 0: trouble with node "n3"; log=r047_beh_ns2_lim1_k1p5_drv1p5_default_m1.log
- r048 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 56.078, timestep = 0: trouble with node "n3"; log=r048_beh_ns2_lim1_k1p25_drv0p5_default_m1.log
- r049 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 27.1064, timestep = 0: trouble with node "n3"; log=r049_beh_ns2_lim1_k1p25_drv1_default_m1.log
- r050 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 18.8897, timestep = 0: trouble with node "n3"; log=r050_beh_ns2_lim1_k1p25_drv2_default_m1.log
- r051 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 19.7006, timestep = 0: trouble with node "n3"; log=r051_beh_ns2_lim1_k1p25_drv1p5_conservative_m1.log
- r052 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 21.631, timestep = 2.17658e-14: trouble with node "n3"; log=r052_beh_ns2_lim1_k1p25_drv1p5_relaxed_m1.log
- r053 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 22.0489, timestep = 3.46602e-13: trouble with node "n3"; log=r053_beh_ns2_lim1_k1p25_drv1p5_relaxed_m0p5.log
- r054 behavioral_proxy_current: returncode=0 but ngspice reported: doAnalyses: TRAN:  Timestep too small; time = 22.0452, timestep = 1.49763e-12: trouble with node "n3"; log=r054_beh_ns2_lim1_k1p25_drv1p5_relaxed_m2.log

## Notes

- Bridge ratios are measured against matching separated direct 4+8 references for each swept parameter bundle.
- Target-band growth is counted only when the target FFT peak is near the nominal 12 band.
- Linear control leakage is rejected if the linear rows show target-band build-up or high bridge ratio.
