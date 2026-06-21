# SPICE 4->8->12 Varactor NLTL Refinement

Focused refinement around the prior best 48-cell/75-ohm varactor NLTL row.

## Direct Answers

1. Can target purity be raised while preserving lock? cleanup_helped=True; best_purity=0.11284289458518919; best_lock=0.9962832721192616.
2. Any full candidate? candidates=0; near_misses=0.
3. Does increasing cell count help? purity_by_cell_count={"48": 0.010083619536122253, "64": 0.05088563820928789, "80": 0.10720309990905755, "96": 0.11284289458518919}.
4. Does target-band extraction/filtering help? True; best_cleanup=extraction_plus_rejection.
5. Controls stay dead? True; max_leakage=0.1375429237794662.
6. Component stresses plausible? best_stress=unrealistic score=1.3506579533005882.
7. Next step: acoustic parallel simulation plus deeper component/BOM sweep before PCB layout.

## Rows

- r001 refine_48c_75ohm_none: role=discovery, status=ran_successfully, category=not_promoted, cleanup=none, cells=48, z0=75.0, lock=0.9319739781317603, bridge=0.7185654118892597, purity=0.010083619536122253, growth=0.879424922716947, stress=plausible, behavioral=0.08.
- r002 refine_64c_75ohm_none: role=discovery, status=ran_successfully, category=not_promoted, cleanup=none, cells=64, z0=75.0, lock=0.9913685959960474, bridge=1.0346441621049047, purity=0.019271653128144908, growth=1.05981006281449, stress=plausible, behavioral=0.08.
- r003 refine_80c_75ohm_none: role=discovery, status=ran_successfully, category=not_promoted, cleanup=none, cells=80, z0=75.0, lock=0.9914118474111702, bridge=8.462013675197507, purity=0.10720309990905755, growth=1.0079273743037258, stress=plausible, behavioral=0.08.
- r004 refine_96c_75ohm_none: role=discovery, status=ran_successfully, category=not_promoted, cleanup=none, cells=96, z0=75.0, lock=0.9849204796512431, bridge=8.541621736375374, purity=0.08840744420166201, growth=0.933118976522, stress=aggressive-but-testable, behavioral=0.08.
- r005 refine_64c_50ohm_target_extraction: role=discovery, status=ran_successfully, category=not_promoted, cleanup=target_extraction, cells=64, z0=50.0, lock=0.9982116518380103, bridge=4.989679590852062, purity=0.04947983721896085, growth=0.8472626000205352, stress=plausible, behavioral=0.08.
- r006 refine_64c_75ohm_target_extraction: role=discovery, status=ran_successfully, category=not_promoted, cleanup=target_extraction, cells=64, z0=75.0, lock=0.9986550525783496, bridge=5.0074499125401095, purity=0.05088563820928789, growth=0.8258319846888666, stress=plausible, behavioral=0.08.
- r007 refine_64c_100ohm_target_extraction: role=discovery, status=ran_successfully, category=not_promoted, cleanup=target_extraction, cells=64, z0=100.0, lock=0.9964116033364341, bridge=4.747373002216147, purity=0.04988292223620868, growth=0.8081708263267817, stress=plausible, behavioral=0.08.
- r008 refine_80c_50ohm_weak_150_bandpass: role=discovery, status=ran_successfully, category=not_promoted, cleanup=weak_150_bandpass, cells=80, z0=50.0, lock=0.9589244962689608, bridge=4.151747925644173, purity=0.040426393014074455, growth=0.9678519701638261, stress=plausible, behavioral=0.08.
- r009 refine_80c_75ohm_weak_150_bandpass: role=discovery, status=ran_successfully, category=not_promoted, cleanup=weak_150_bandpass, cells=80, z0=75.0, lock=0.9372964633360674, bridge=3.819549819718746, purity=0.037841054274196734, growth=0.8441436835913719, stress=aggressive-but-testable, behavioral=0.08.
- r010 refine_80c_100ohm_weak_150_bandpass: role=discovery, status=ran_successfully, category=not_promoted, cleanup=weak_150_bandpass, cells=80, z0=100.0, lock=0.93275862641185, bridge=3.2226982505162485, purity=0.03294057002081199, growth=0.8313629044105671, stress=aggressive-but-testable, behavioral=0.08.
- r011 refine_96c_50ohm_extraction_plus_rejection: role=discovery, status=ran_successfully, category=not_promoted, cleanup=extraction_plus_rejection, cells=96, z0=50.0, lock=0.9744812876780009, bridge=12.445642875755226, purity=0.08776056706556863, growth=1.324853746977207, stress=aggressive-but-testable, behavioral=0.08.
- r012 refine_96c_75ohm_extraction_plus_rejection: role=discovery, status=ran_successfully, category=not_promoted, cleanup=extraction_plus_rejection, cells=96, z0=75.0, lock=0.991438381945108, bridge=15.612458440290018, purity=0.10144133078840824, growth=1.1862561290468554, stress=aggressive-but-testable, behavioral=0.08.
- r013 refine_96c_100ohm_extraction_plus_rejection: role=discovery, status=ran_successfully, category=not_promoted, cleanup=extraction_plus_rejection, cells=96, z0=100.0, lock=0.9962832721192616, bridge=18.50273150673982, purity=0.11284289458518919, growth=1.0752074581627575, stress=unrealistic, behavioral=0.08.
- r014 refine_80c_75ohm_source_rejection: role=discovery, status=ran_successfully, category=not_promoted, cleanup=source_rejection, cells=80, z0=75.0, lock=0.9801020823868823, bridge=6.960024852288823, purity=0.09465859400015614, growth=1.523605162121515, stress=plausible, behavioral=0.08.
- r015 refine_80c_75ohm_generated_rejection: role=discovery, status=ran_successfully, category=not_promoted, cleanup=generated_rejection, cells=80, z0=75.0, lock=0.9581282813116526, bridge=1.8496120703656524, purity=0.01853557636550749, growth=0.9601333896938623, stress=plausible, behavioral=0.08.
- r016 refine_80c_75ohm_target_shunt_trap: role=discovery, status=ran_successfully, category=not_promoted, cleanup=target_shunt_trap, cells=80, z0=75.0, lock=0.9330018871039282, bridge=4.033618818213655, purity=0.054087173117605386, growth=1.3491037444517362, stress=plausible, behavioral=0.08.
- c001 linear_fixed_capacitor_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.3237383600409814, bridge=0.011260263397327375, purity=1.0070870728779915e-08, growth=1.0118075481530688, stress=aggressive-but-testable, behavioral=0.02.
- c002 weak_varactor_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.28497662064045387, bridge=0.026800473733857806, purity=4.810433411058783e-08, growth=1.0018092101435048, stress=aggressive-but-testable, behavioral=0.08.
- c003 detuned_target_velocity_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.9417509445417177, bridge=7.567173695785014, purity=0.05596027455501724, growth=0.7818923621720588, stress=aggressive-but-testable, behavioral=0.08.
- c004 shuffled_frequency_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.7474014340259597, bridge=1.2080116483631145, purity=0.004498772416131621, growth=1.2750858475589324, stress=plausible, behavioral=0.08.
- c005 too_short_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.5826739296190468, bridge=0.1571910456281063, purity=0.002366421960876708, growth=0.9741060154523352, stress=plausible, behavioral=0.08.
- c006 too_lossy_refine_control: role=control, status=ran_successfully, category=control_dead, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.9835160849106085, bridge=8.91522932174911, purity=0.10509587026784671, growth=1.2055927505282913, stress=aggressive-but-testable, behavioral=0.08.
- direct_50plus100_reference direct_50plus100_reference: role=ceiling_reference, status=ran_successfully, category=ceiling_reference_not_discovery, cleanup=extraction_plus_rejection, cells=80, z0=75.0, lock=0.8081741888994481, bridge=1.0, purity=0.01772122812907386, growth=0.8112216154049705, stress=plausible, behavioral=0.08.

## Circuit Notes

- Discovery rows drive only the 50 MHz source band.
- Passive cleanup networks use resonant extraction or shunt traps; no hidden 100 MHz or 150 MHz source is added.
- Direct 50+100 MHz remains a separated ceiling denominator only.
