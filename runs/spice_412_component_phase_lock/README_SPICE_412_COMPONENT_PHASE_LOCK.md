# SPICE 4->8->12 Component Phase Lock

Focused phase-lock refinement around component-realism bridge-ratio crossing rows.

## Direct Answers

1. Can any component-plausible row keep bridge ratio >1.5 while raising phase lock? True; best bridge-lock case=p050, lock=0.025184777593100782, bridge=124.01271107930988.
2. Did any row reach phase lock >0.50? False; cases=.
3. Did any row reach phase lock >0.90? False; cases=.
4. Did weak-nonlinearity and detuned controls stop leaking under coherent-growth criteria? weak=0.5668212777186143, detuned=0.5638134620404281, all_controls_dead=False.
5. Which mechanism helps most? coupling_orientation; scores={"coupling_orientation": 0.030888914706286432, "coupling_strength": 0.01808012927728438, "generated_detuning": 0.018865342457972754, "q_load_shaping": 0.023976972527445597, "seed_baseline": 0.02499998484233815, "target_detuning": 0.017729119356998845}.
6. Next step: spatial phase-matching model or reject current component topology before deeper sweeps.

## Top Phase-Lock Rows

- p048 seed=c013 varactor_pair_mixer focus=coupling_orientation: status=ran_successfully, lock=0.030888914706286432, generated_lock=0.026073663674949565, bridge=0.6330558478412127, purity=0.9140262305192789, coherent_growth=1.0307900029150532, category=not_promoted.
- p052 seed=c033 hybrid_varactor_plus_saturable_inductor focus=coupling_orientation: status=ran_successfully, lock=0.030666383984905534, generated_lock=0.025826746258240614, bridge=0.6393792065755929, purity=0.9140311774421512, coherent_growth=1.0312703592461938, category=not_promoted.
- p058 seed=c033 hybrid_varactor_plus_saturable_inductor focus=coupling_orientation: status=ran_successfully, lock=0.029548485708762968, generated_lock=0.025967149748745047, bridge=0.727919870539868, purity=0.8431120146224557, coherent_growth=1.0314479198114754, category=not_promoted.
- p054 seed=c013 varactor_pair_mixer focus=coupling_orientation: status=ran_successfully, lock=0.029502661934568505, generated_lock=0.025939010359061612, bridge=0.7213342901795374, purity=0.8431789881098878, coherent_growth=1.031625402153615, category=not_promoted.
- p050 seed=c023 saturable_inductor_core focus=coupling_orientation: status=ran_successfully, lock=0.025184777593100782, generated_lock=0.020627604759664887, bridge=124.01271107930988, purity=0.9921487129086592, coherent_growth=2.212875898678697, category=reject_due_to_phase_incoherence.
- p051 seed=c028 coupled_saturable_transformer focus=coupling_orientation: status=ran_successfully, lock=0.025184777593100782, generated_lock=0.020627604759664887, bridge=124.01271107930988, purity=0.9921487129086592, coherent_growth=2.212875898678697, category=reject_due_to_phase_incoherence.
- p002 seed=c013 varactor_pair_mixer focus=seed_baseline: status=ran_successfully, lock=0.02499998484233815, generated_lock=0.02062698145428097, bridge=0.6023958221556196, purity=0.9085099676330487, coherent_growth=1.0236463301419703, category=not_promoted.
- p036 seed=c013 varactor_pair_mixer focus=coupling_orientation: status=ran_successfully, lock=0.02499998484233815, generated_lock=0.02062698145428097, bridge=0.6023958221556196, purity=0.9085099676330487, coherent_growth=1.0236463301419703, category=not_promoted.
- p006 seed=c033 hybrid_varactor_plus_saturable_inductor focus=seed_baseline: status=ran_successfully, lock=0.02484483095315086, generated_lock=0.020476720452404538, bridge=0.608136935025716, purity=0.9084722590647029, coherent_growth=1.0237783960276485, category=not_promoted.
- p040 seed=c033 hybrid_varactor_plus_saturable_inductor focus=coupling_orientation: status=ran_successfully, lock=0.02484483095315086, generated_lock=0.020476720452404538, bridge=0.608136935025716, purity=0.9084722590647029, coherent_growth=1.0237783960276485, category=not_promoted.
- p079 seed=c008 diode_bridge_mixer focus=q_load_shaping: status=ran_successfully, lock=0.023976972527445597, generated_lock=0.023453427105787895, bridge=85.32645539622663, purity=0.9929934612780069, coherent_growth=1.6053072500611132, category=reject_due_to_phase_incoherence.
- p042 seed=c013 varactor_pair_mixer focus=coupling_orientation: status=ran_successfully, lock=0.023800194332363075, generated_lock=0.02060548391784363, bridge=0.6844504041186125, purity=0.8342040739676787, coherent_growth=1.0220457747593832, category=not_promoted.

## Convergence Failures

- None.

## Notes

- Discovery rows remain source-only and component-plausible; behavioral current mixing is not used.
- Direct 4+8 references are separated ceiling denominators grouped by seed row.
- Control leakage is scored on coherent target-band build-up, not raw target-band amplitude alone.
