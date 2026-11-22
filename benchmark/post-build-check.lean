module

import Lean
meta import Lean
import all Formalism.HermitianCurvature.HermitianCurvatureProofs.EtaleIntegralityFacts

example {E F : Type*} [NormedAddCommGroup E] [NormedSpace ℝ E]
    [NormedAddCommGroup F] [NormedSpace ℝ F]
    {ι : Type*} [Fintype ι] [DecidableEq ι] {q : ℕ} {f : E → ι → F} {u : E} {S P : ℝ}
    (h : ∀ i, Formalism.FourierDecayAlt.P.EtaleIntegralityFacts.DB q (fun v => f v i) u S P)
    (hP : 0 ≤ P) :
    Formalism.FourierDecayAlt.P.EtaleIntegralityFacts.DB q f u (Fintype.card ι * S) P :=
  Formalism.FourierDecayAlt.P.EtaleIntegralityFacts.DB.pi h hP

open Lean in
run_cmd do
  let allowed : Array Name := #[`propext, `Classical.choice, `Quot.sound]
  for target in #[`Formalism.FourierDecayAlt.P.EtaleIntegralityFacts.DB.pi] do
    let actual ← collectAxioms target
    for ax in actual do
      unless allowed.contains ax do
        throwError "Unexpected benchmark theorem axiom {ax} in {target}"
    logInfo m!"[BENCH_AXIOMS] {target}: {actual}"
  logInfo "[BENCH_POSTCHECK_COMPLETED]"
