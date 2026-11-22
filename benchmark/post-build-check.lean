import Lean
import all Formalism.HermitianCurvature.HermitianCurvatureProofs.PhaseFunctionDerivatives

example (ω : ℂ) (hω : ‖ω‖ = 1) (i : ℕ) : ‖ω ^ i - 1‖ ≤ i * ‖ω - 1‖ :=
  Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_pow_sub_one ω hω i

example (s : ℕ) (hs : 0 < s) (z z' : ℂ) (hz : z ≠ 0)
    (h : z' ^ s = z ^ s) (hne : z' ≠ z) : ‖z‖ ≤ s * ‖z' - z‖ :=
  Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_root_sep s hs z z' hz h hne

open Lean in
run_cmd do
  let allowed : Array Name := #[`propext, `Classical.choice, `Quot.sound]
  for target in #[`Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_pow_sub_one,
                  `Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_root_sep] do
    let actual ← collectAxioms target
    for ax in actual do
      unless allowed.contains ax do
        throwError "Unexpected benchmark theorem axiom {ax} in {target}"
    logInfo m!"[BENCH_AXIOMS] {target}: {actual}"
  logInfo "[BENCH_POSTCHECK_COMPLETED]"
