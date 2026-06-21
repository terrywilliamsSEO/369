# SPICE 4->8->12 Varactor NLTL Design

Bench-oriented varactor-loaded nonlinear transmission-line design at 50/100/150 MHz.

## Direct Answers

1. Can a realistic varactor-loaded NLTL preserve the bridge? candidates=0; near_misses=0; best=varactor_nltl_48cells_75ohm.
2. Best cell count and impedance: 48 cells at 75.0 ohm.
3. Stress plausibility: plausible with stress score 0.37240550809233597.
4. Controls stay dead? True; max leakage=0.09980137709284176.
5. Behavioral dependency: best=0.08; lower_than_0.36=True.
6. Bench-buildable? False with best feasibility 0.6699390733006245.
7. Next step: component selection/BOM plus stronger varactor sweep before PCB layout.

## Rows

- d001 varactor_nltl_12cells_25ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=12, z0=25.0, lock=0.1798174885649563, bridge=0.0009523038917253835, purity=2.4918380694754413e-10, stress=plausible, behavioral=0.08.
- d002 varactor_nltl_12cells_50ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=12, z0=50.0, lock=0.22655687821753517, bridge=0.001582865860157376, purity=7.278981430254647e-10, stress=plausible, behavioral=0.08.
- d003 varactor_nltl_12cells_75ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=12, z0=75.0, lock=0.2280377430259011, bridge=0.0018108763586217162, purity=1.1556609684031424e-09, stress=plausible, behavioral=0.08.
- d004 varactor_nltl_16cells_25ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=16, z0=25.0, lock=0.072820015884054, bridge=0.007789913057896961, purity=9.185011896376998e-08, stress=plausible, behavioral=0.08.
- d005 varactor_nltl_16cells_50ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=16, z0=50.0, lock=0.06727040324259305, bridge=0.010049672447216839, purity=1.5389681559064114e-07, stress=plausible, behavioral=0.08.
- d006 varactor_nltl_16cells_75ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=16, z0=75.0, lock=0.0652859981003619, bridge=0.011050196205652944, purity=1.789882760449274e-07, stress=plausible, behavioral=0.08.
- d007 varactor_nltl_24cells_25ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=24, z0=25.0, lock=0.23957542307382046, bridge=0.004049443711210905, purity=1.1557816509237917e-05, stress=plausible, behavioral=0.08.
- d008 varactor_nltl_24cells_50ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=24, z0=50.0, lock=0.21365786231146758, bridge=0.005202702541318431, purity=1.5518486862565884e-05, stress=plausible, behavioral=0.08.
- d009 varactor_nltl_24cells_75ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=24, z0=75.0, lock=0.20120289992921553, bridge=0.0060497504367481286, purity=1.5809536878396748e-05, stress=plausible, behavioral=0.08.
- d010 varactor_nltl_32cells_25ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=32, z0=25.0, lock=0.1883087586600528, bridge=0.024328646719386903, purity=0.0003759204808092879, stress=plausible, behavioral=0.08.
- d011 varactor_nltl_32cells_50ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=32, z0=50.0, lock=0.19927480281545606, bridge=0.05222282416182916, purity=0.0005947764529017286, stress=plausible, behavioral=0.08.
- d012 varactor_nltl_32cells_75ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=32, z0=75.0, lock=0.19297039611849465, bridge=0.0653273916104036, purity=0.0006963186584858452, stress=plausible, behavioral=0.08.
- d013 varactor_nltl_48cells_25ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=48, z0=25.0, lock=0.8317946636921645, bridge=0.6251243740488418, purity=0.0037614664325752896, stress=plausible, behavioral=0.08.
- d014 varactor_nltl_48cells_50ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=48, z0=50.0, lock=0.8872032216636218, bridge=1.068574378696935, purity=0.005838948797945488, stress=plausible, behavioral=0.08.
- d015 varactor_nltl_48cells_75ohm: role=discovery, status=ran_successfully, category=not_promoted, cells=48, z0=75.0, lock=0.8961718833832657, bridge=1.2879414175695514, purity=0.00680203728635401, stress=plausible, behavioral=0.08.
- c001 linear_fixed_capacitor_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.2888173662724263, bridge=0.0015104819374650387, purity=1.1333516713490192e-06, stress=plausible, behavioral=0.02.
- c002 weak_varactor_nonlinearity_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.2877841760245237, bridge=0.0015308485674477245, purity=1.1942346147475916e-06, stress=aggressive-but-testable, behavioral=0.08.
- c003 detuned_target_phase_velocity_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.47148161285288304, bridge=0.2325216890196442, purity=0.001834906159439446, stress=plausible, behavioral=0.08.
- c004 shuffled_frequency_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.8647730865565293, bridge=1.1160146566924363, purity=0.0075440878169349525, stress=plausible, behavioral=0.08.
- c005 too_short_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.3266033649452086, bridge=0.01064140111094629, purity=2.2025837180425824e-05, stress=plausible, behavioral=0.08.
- c006 too_lossy_line: role=control, status=ran_successfully, category=control_dead, cells=48, z0=50.0, lock=0.8099152635186175, bridge=0.4602309540862693, purity=0.0038062111706196953, stress=plausible, behavioral=0.08.
- direct_50plus100_reference direct_50plus100_reference: role=ceiling_reference, status=ran_successfully, category=ceiling_reference_not_discovery, cells=48, z0=50.0, lock=0.8537489760076943, bridge=1.0, purity=0.00955601883727864, stress=plausible, behavioral=0.08.

## Circuit Notes

- Discovery rows drive only the 50 MHz source band.
- Generated 100 MHz and target 150 MHz content arise from reverse-biased varactor diode capacitance.
- The direct 50+100 MHz reference is separated and is not a discovery row.
- Band-selective shunts are passive phase-velocity controls, not target-frequency sources.
