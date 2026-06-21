# SPICE 4->8->12 Electrical Candidate Race

Bounded electrical family race at 50/100/150 MHz.

## Direct Answers

1. Strongest electrical family overall: hybrid_varactor_plus_magnetic_line via e007 (e007_hybrid_varactor_plus_magnetic_line_96c_75ohm_extraction_plus_rejection).
2. Any realistic electrical row promoted? candidates=0.
3. Any near miss promoted? near_misses=0.
4. Best 150 MHz purity under plausible/aggressive stress: family=hybrid_varactor_plus_magnetic_line, case=e007, purity=0.10268922614475048.
5. Best bridge ratio under clean controls: family=hybrid_varactor_plus_magnetic_line, case=e007, bridge=13.199503751025986.
6. Do target extraction and rejection traps solve purity? helped=True; extraction_best=0.10268922614475048; raw_best=0.03253752932413984.
7. Do controls stay dead? True; max_leakage=0.0.
8. Next step: nonlinear magnetic/hybrid refinement plus acoustic demo branch.
9. Electrical route recommendation: replace pure varactor as primary with hybrid_varactor_plus_magnetic_line for the next electrical refinement.

## Rows

- e001 varactor_loaded_nltl: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=80, z0=75.0, length=0.38, lock=0.996556337893682, bridge=1.887830633069256, purity=0.03253752932413984, growth=1.0244053536069027, gen_cv=0.012892932026156373, stress=plausible, behavioral=0.08.
- e002 varactor_loaded_nltl: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=128, z0=100.0, length=0.5, lock=0.97833400416033, bridge=1.6685982102492698, purity=0.023581223369171997, growth=1.0392241481978497, gen_cv=0.011619583502057391, stress=plausible, behavioral=0.08.
- e003 step_recovery_diode_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=64, z0=50.0, length=0.38, lock=0.3009617020947018, bridge=0.00161619175314993, purity=6.499664473333159e-08, growth=1.1627469854855375, gen_cv=0.31013799352269206, stress=plausible, behavioral=0.18.
- e004 step_recovery_diode_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=75.0, length=0.5, lock=0.2616682500485698, bridge=0.002522243901857924, purity=1.6326484962176193e-06, growth=0.5526518523516799, gen_cv=0.9945499307901045, stress=plausible, behavioral=0.18.
- e005 nonlinear_magnetic_transmission_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=80, z0=75.0, length=0.75, lock=0.31524662468204967, bridge=0.009020744491405882, purity=1.53397445627411e-06, growth=1.0168769820795949, gen_cv=0.8840071072570392, stress=plausible, behavioral=0.18.
- e006 nonlinear_magnetic_transmission_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=128, z0=100.0, length=0.75, lock=0.2605441691346198, bridge=0.015172698233159818, purity=4.49488810705006e-08, growth=1.682269766425688, gen_cv=1.196699648424292, stress=aggressive-but-testable, behavioral=0.18.
- e007 hybrid_varactor_plus_magnetic_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=75.0, length=0.5, lock=0.9641628123750706, bridge=13.199503751025986, purity=0.10268922614475048, growth=1.0708488912248573, gen_cv=0.08690699148297315, stress=aggressive-but-testable, behavioral=0.19999999999999998.
- e008 hybrid_varactor_plus_magnetic_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=128, z0=100.0, length=0.75, lock=0.9361012231035211, bridge=7.119269139884089, purity=0.07126645749471384, growth=1.0525399442629795, gen_cv=0.24279701187970537, stress=aggressive-but-testable, behavioral=0.19999999999999998.
- e009 varactor_line_with_high_q_target_extraction: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=100.0, length=0.38, lock=0.9659895046285626, bridge=6.2033912368630375, purity=0.04278966226414591, growth=1.036128901808062, gen_cv=0.052861381172667546, stress=aggressive-but-testable, behavioral=0.08.
- e010 varactor_line_with_high_q_target_extraction: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=128, z0=100.0, length=0.5, lock=0.886234274871038, bridge=1.646771477482917, purity=0.01108856907464939, growth=0.8069907302864027, gen_cv=0.030563230128635707, stress=plausible, behavioral=0.08.
- e011 varactor_line_with_distributed_bandpass_sections: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=80, z0=75.0, length=0.38, lock=0.917047181505894, bridge=2.5333297857684314, purity=0.045069912441955906, growth=0.865331371169805, gen_cv=0.03837650855322267, stress=plausible, behavioral=0.12.
- e012 varactor_line_with_distributed_bandpass_sections: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=100.0, length=0.5, lock=0.9168201781542135, bridge=2.4551212087216876, purity=0.019610864846072266, growth=0.6302861966396612, gen_cv=0.0793975688553491, stress=plausible, behavioral=0.12.
- e013 magnetic_line_with_target_extraction: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=75.0, length=0.75, lock=0.21263906060851911, bridge=0.01149656894386009, purity=3.8524726744849386e-07, growth=1.564625141946621, gen_cv=1.0525646906529582, stress=aggressive-but-testable, behavioral=0.18.
- e014 dual_path_phase_matched_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=96, z0=75.0, length=0.5, lock=0.9194835628876876, bridge=1.9850859721024012, purity=0.009510111848111936, growth=0.3745109964474877, gen_cv=0.1328998207565746, stress=plausible, behavioral=0.19999999999999998.
- e015 dual_path_phase_matched_line: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=128, z0=100.0, length=0.75, lock=0.9115242761682906, bridge=4.845786598141786, purity=0.04587569718002384, growth=0.9030031102353792, gen_cv=0.20470429722596306, stress=aggressive-but-testable, behavioral=0.19999999999999998.
- e016 varactor_loaded_nltl: role=discovery, status=ran_successfully, category=reject_due_to_low_purity, cells=48, z0=50.0, length=0.25, lock=0.8226667268331181, bridge=0.4474011849038523, purity=0.006625591737948952, growth=1.0094529079189987, gen_cv=0.0019249621861319747, stress=plausible, behavioral=0.08.
- c001 linear_fixed_component_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.3397116781939722, bridge=0.0027094129152743433, purity=6.8362250459833836e-09, growth=1.1215559340380128, gen_cv=1.0750986021026168, stress=plausible, behavioral=0.02.
- c002 weak_nonlinearity_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.28691913486579346, bridge=0.0012631784902321335, purity=1.078423497273738e-09, growth=1.2141467252844347, gen_cv=0.3269308689247449, stress=aggressive-but-testable, behavioral=0.08.
- c003 detuned_target_velocity_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.9687371998384543, bridge=1.1388624918803183, purity=0.003993645529144059, growth=0.28349999714945673, gen_cv=0.5377318374143008, stress=plausible, behavioral=0.08.
- c004 shuffled_frequency_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.982471704049412, bridge=9.100802763875228, purity=0.0880305318415409, growth=1.1973402637462822, gen_cv=0.016597687519731705, stress=plausible, behavioral=0.08.
- c005 too_short_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.05, lock=0.18646921477097217, bridge=0.00400703059351736, purity=1.6994662106459276e-05, growth=0.9051959699286343, gen_cv=0.01062146490164675, stress=plausible, behavioral=0.08.
- c006 too_lossy_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.9431443469906967, bridge=2.1922437853498353, purity=0.046187900599502694, growth=1.0720222835212159, gen_cv=0.00713837188942476, stress=plausible, behavioral=0.08.
- c007 phase_mismatched_line: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.9555936736819154, bridge=15.596725841904219, purity=0.17925614324038328, growth=1.6222855991731508, gen_cv=0.07317921141038425, stress=aggressive-but-testable, behavioral=0.08.
- c008 target_extraction_only_no_nonlinearity: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.3397116781939722, bridge=0.0027094129152743433, purity=6.8362250459833836e-09, growth=1.1215559340380128, gen_cv=1.0750986021026168, stress=plausible, behavioral=0.02.
- c009 nonlinearity_only_no_target_extraction: role=control, status=ran_successfully, category=control_dead, cells=80, z0=75.0, length=0.38, lock=0.995319905168539, bridge=3.9827499700837388, purity=0.055935820016620064, growth=1.0078586181873468, gen_cv=0.006419576358213168, stress=plausible, behavioral=0.08.
- direct_50plus100_reference direct_50plus100_reference: role=ceiling_reference, status=ran_successfully, category=ceiling_reference_not_discovery, cells=80, z0=75.0, length=0.38, lock=0.9304904993961246, bridge=1.0, purity=0.02426593533138152, growth=0.6517014400228004, gen_cv=0.24198991927494248, stress=plausible, behavioral=0.08.

## Circuit Notes

- Discovery rows drive only the 50 MHz source band.
- No discovery row uses direct 100 MHz drive, direct 150 MHz drive, target-frequency injection, or a hidden behavioral target source.
- Direct 50+100 MHz is separated as a ceiling denominator only.
- Step-recovery and magnetic rows use first-pass nonlinear current/inductance proxies and report higher behavioral dependency than the pure varactor rows.
- This is a bounded race, not a full combinatorial sweep across every axis.
