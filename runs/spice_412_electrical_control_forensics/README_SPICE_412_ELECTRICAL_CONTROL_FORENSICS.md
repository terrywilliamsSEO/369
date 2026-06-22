# SPICE 4->8->12 Electrical Control Forensics

Strict probe pass to separate true pre-extraction 150 MHz bridge generation from tuned extraction/filter artifacts.

## Direct Answers

1. Is the electrical 150 MHz signal real bridge generation or mostly extraction/filter artifact? real_signal=False; filter_artifact_likely=True.
2. Does hybrid produce more pre-extraction 150 MHz than pure varactor? True; best_hybrid_pre_purity=0.7033799199368376; pure_varactor_pre_purity=0.22916248039696294.
3. Does generated-path suppression kill 150 MHz? True; dependency_score=0.999999825071147.
4. Does phase mismatch kill 150 MHz? True; kill_score=0.8860012804184718.
5. Does extraction create apparent purity from weak broadband response? True; pure_varactor_post_beats_hybrid=False.
6. Should electrical work continue, pivot, or pause? pause this electrical topology behind the acoustic branch while testing a different electrical topology.
7. Is acoustic now the only clean physical proof route? True under this electrical topology.

## Aggregate

- Rows: total=12, successful=12, statuses=ran_successfully.
- Controls: pre_extraction_dead=False, overall_dead=False, max_leakage=0.8172928723255333.
- Best hybrid pre case: f003 purity=0.7033799199368376 target_power=263260.22454435955.
- Best hybrid post case: f001 purity=0.9960952980428012.

## Rows

- f001 best_lockin_hybrid: role=discovery, status=ran_successfully, category=electrical_filter_artifact_likely, pre_purity=0.5740462742923432, post_purity=0.9960952980428012, pre_growth=1.0454598099909358, post_growth=1.0528117952685943, filter_selectivity=55.681793203716424, bridge=1.0608952235737868e-05, control_leak=0.0, stress=aggressive-but-testable.
- f002 previous_hybrid_near_miss: role=discovery, status=ran_successfully, category=electrical_filter_artifact_likely, pre_purity=0.7118770308981421, post_purity=0.950086543775223, pre_growth=1.0409267202336325, post_growth=1.0217863097016304, filter_selectivity=3.97585380636536, bridge=1.8484010916153074e-05, control_leak=0.0, stress=aggressive-but-testable.
- f003 growth_preserving_hybrid_near_miss: role=discovery, status=ran_successfully, category=electrical_filter_artifact_likely, pre_purity=0.7033799199368376, post_purity=0.9538462699314717, pre_growth=1.0249345586502452, post_growth=1.037240802655439, filter_selectivity=3.980151186927684, bridge=2.1355432799539552e-05, control_leak=0.0, stress=aggressive-but-testable.
- f004 tuned_pure_varactor_extraction: role=control, status=ran_successfully, category=reject_due_to_control_leakage, pre_purity=0.22916248039696294, post_purity=0.9483346645333814, pre_growth=1.222894472359788, post_growth=1.1379164155843036, filter_selectivity=54.57234334681356, bridge=2.343690203143429e-06, control_leak=0.8172928723255333, stress=aggressive-but-testable.
- f005 pure_varactor_no_extraction: role=control, status=ran_successfully, category=control_dead, pre_purity=0.04141319255977615, post_purity=0.04141319255977615, pre_growth=1.135300426365374, post_growth=1.135300426365374, filter_selectivity=1.0, bridge=4.5270770663769846e-06, control_leak=0.06765021318268705, stress=aggressive-but-testable.
- f006 pure_magnetic_same_extraction: role=control, status=ran_successfully, category=control_dead, pre_purity=3.5651643266531134e-07, post_purity=0.0005399687078804187, pre_growth=0.9111667120221949, post_growth=0.8920473001438782, filter_selectivity=140.46179602532104, bridge=5.406070186956505e-13, control_leak=0.0, stress=plausible.
- f007 hybrid_no_extraction: role=discovery, status=ran_successfully, category=electrical_filter_artifact_likely, pre_purity=0.011490330370660084, post_purity=0.011490330370660084, pre_growth=1.0691862752502297, post_growth=1.0691862752502297, filter_selectivity=1.0, bridge=5.969601377646111e-07, control_leak=0.0, stress=plausible.
- f008 generated_path_suppressed: role=control, status=ran_successfully, category=control_dead, pre_purity=4.481158315467437e-07, post_purity=0.000625566453494713, pre_growth=0.7464115535827771, post_growth=0.8521293655427965, filter_selectivity=19.745032897813758, bridge=1.2341153292911264e-12, control_leak=0.0, stress=aggressive-but-testable.
- f009 target_velocity_detuned: role=control, status=ran_successfully, category=reject_due_to_control_leakage, pre_purity=0.28388608709177454, post_purity=0.34275145704205695, pre_growth=1.2746706006727275, post_growth=1.3450916721414927, filter_selectivity=1.7847933427575422, bridge=2.176574280456291e-06, control_leak=0.3152972931128033, stress=aggressive-but-testable.
- f010 phase_mismatched_line: role=control, status=ran_successfully, category=control_dead, pre_purity=0.0807719112617625, post_purity=0.2064996083380121, pre_growth=1.0711181249572306, post_growth=1.1439082310850686, filter_selectivity=4.423238218398458, bridge=2.986941775397639e-06, control_leak=0.07845372388054636, stress=aggressive-but-testable.
- f011 linear_fixed_component_extraction: role=control, status=ran_successfully, category=control_dead, pre_purity=1.928604744754719e-07, post_purity=0.00026837763106620015, pre_growth=0.9138153648280993, post_growth=0.7987083534613733, filter_selectivity=49.83619775926774, bridge=1.4989430588692842e-12, control_leak=0.0, stress=aggressive-but-testable.
- direct_50plus100_reference direct_50plus100_ceiling_reference: role=ceiling_reference, status=ran_successfully, category=ceiling_reference_not_discovery, pre_purity=0.5319628369662595, post_purity=0.8426548633045143, pre_growth=0.8112135274075941, post_growth=0.8195923621359171, filter_selectivity=4.12260420150529, bridge=1.907705629201565e-06, control_leak=0.0, stress=plausible.

## Probe Notes

- Every discovery/control row except the separated direct reference drives only the 50 MHz source.
- No discovery/control row uses direct 100 MHz drive, direct 150 MHz drive, target-frequency injection, or hidden target-band behavioral source.
- Each netlist writes v(n0), quarter-line, mid-line, three-quarter-line, raw line output, post-extraction output, source current, and bias current.
- The direct 50+100 MHz row is a ceiling denominator only and is excluded from discovery conclusions.
