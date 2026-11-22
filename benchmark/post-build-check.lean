module

import Lean
meta import Lean
import all Formalism.HermitianCurvature.HermitianCurvatureProofs.EtaleIntegralityFacts

example : Formalism.FourierDecayAlt.G.AmpBoundFar :=
  Formalism.FourierDecayAlt.P.amplitude_bound_far

open Lean in
run_cmd do
  let allowed : Array Name := #[`propext, `Classical.choice, `Quot.sound]
  for target in #[`Formalism.FourierDecayAlt.P.amplitude_bound_far] do
    let actual ← collectAxioms target
    for ax in actual do
      unless allowed.contains ax do
        throwError "Unexpected benchmark theorem axiom {ax} in {target}"
    logInfo m!"[BENCH_AXIOMS] {target}: {actual}"
  logInfo "[BENCH_POSTCHECK_COMPLETED]"
