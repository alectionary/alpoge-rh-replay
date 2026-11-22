module

import Lean
meta import Lean
import all Formalism.HermitianCurvature.HermitianCurvatureProofs.CuspidalIrreducibleSubrep

open Matrix

example {n : ℕ} (X : Matrix (Fin n) (Fin n) ℂ)
    (hX : Formalism.FourierDecayAlt.G.IsStrictUpper X) (t : ℂ) :
    (t • (1 : Matrix (Fin n) (Fin n) ℂ) + X) *
        Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.geoS X t =
      t ^ n • (1 : Matrix (Fin n) (Fin n) ℂ) :=
  Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.geom X hX t

example {n : ℕ} (X : Matrix (Fin n) (Fin n) ℂ)
    (B ρ : Fin n → ℂ) (t : ℂ) :
    ∑ j ∈ Finset.range n, (ρ ⬝ᵥ ((-X) ^ j *ᵥ B)) * t ^ (n - 1 - j) =
      ρ ⬝ᵥ (Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.geoS X t *ᵥ B) :=
  Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.sum_eq_geoS X B ρ t

open Lean in
run_cmd do
  let allowed : Array Name := #[`propext, `Classical.choice, `Quot.sound]
  for target in #[`Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.geom,
                  `Formalism.FourierDecayAlt.P.CuspidalIrreducibleSubrep.sum_eq_geoS] do
    let actual ← collectAxioms target
    for ax in actual do
      unless allowed.contains ax do
        throwError "Unexpected benchmark theorem axiom {ax} in {target}"
    logInfo m!"[BENCH_AXIOMS] {target}: {actual}"
  logInfo "[BENCH_POSTCHECK_COMPLETED]"
