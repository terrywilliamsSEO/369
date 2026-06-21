# SPICE 4->8->12 Distributed Ladder

Normalized ngspice envelope-ladder export for the distributed phase-matched 4->8->12 topology.

## Direct Answers

1. Can SPICE reproduce the distributed phase-matched 4->8->12 lock? candidates=1; best=d001 lock=0.915420671203912 bridge=3.7184380579556167.
2. Does the phase-matched ladder beat the lumped-equivalent control? True; phase_lock=0.915420671203912 vs lumped=0.45330745299975866.
3. Does deliberate phase mismatch kill lock? True; mismatched_lock=0.013549706598009194.
4. Does QPM help? True; qpm_lock=0.6209769504873119, qpm_bridge=5.746898032612119.
5. Do linear, detuned, and shuffled controls stay dead? True; max_control_leakage=0.0.
6. Next step: physical waveguide modeling and transmission-line ladder refinement.

## Rows

- d001 phase_matched_codirectional_ladder: status=ran_successfully, category=spice_distributed_phase_candidate, lock=0.915420671203912, bridge=3.7184380579556167, purity=0.9700295013650013, growth=18.0639527160933.
- d002 qpm_ladder: status=ran_successfully, category=not_promoted, lock=0.6209769504873119, bridge=5.746898032612119, purity=0.7182000579848182, growth=129.13656078213947.
- c002 lumped_equivalent_control: status=ran_successfully, category=reject_due_to_phase_mismatch, lock=0.45330745299975866, bridge=837399.0479965085, purity=0.9819992767043265, growth=28844.01979585223.
- c001 mismatched_ladder_control: status=ran_successfully, category=reject_due_to_phase_mismatch, lock=0.013549706598009194, bridge=1.830844287395895, purity=0.925000565055341, growth=530.7299785530755.
- c005 shuffled_frequency_control: status=ran_successfully, category=control_dead, lock=0.010354523028331314, bridge=9.255544832191717e-08, purity=0.00025731420886036257, growth=0.3811060199088669.
- c004 detuned_target_control: status=ran_successfully, category=control_dead, lock=0.0028385035526556743, bridge=0.0003454537339067657, purity=0.0014592942788865374, growth=0.5037243452342581.
- c003 linear_no_nonlinearity_control: status=ran_successfully, category=control_dead, lock=0.0, bridge=0.0, purity=0.0, growth=0.0.

## Notes

- Discovery rows drive only the source band at the first/source section.
- Direct 4+8 is exported only as a separated ceiling denominator.
- The ladder uses normalized envelope state variables, not hardware-realistic LC component values.
