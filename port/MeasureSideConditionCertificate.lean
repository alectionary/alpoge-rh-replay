import Mathlib

/-!
Generic map/product side-condition certificate proposal. The definitions and
seven theorem proofs below are extracted unchanged from the generic section
of GuardedProductCertificate SHA256 8eb205e139a091957c09ab0fa7bf05e3a7f9703d4d9d36b84c9a59c054080d18,
which compiled in run 45017435496. This standalone file still requires its own
actual compilation and axiom check. It imports no project or BB module.
A passing certificate does not approve any source declaration or audit finding.
-/

noncomputable section

open MeasureTheory

namespace MeasureSideConditionCertificate

variable {α β : Type*} [MeasurableSpace α] [MeasurableSpace β]

def pinnedMap (f : α → β) (μ : Measure α) : Measure β :=
  @dite (Measure β) (AEMeasurable f μ)
    (Classical.propDecidable (AEMeasurable f μ))
    (fun hf => Measure.mapₗ (hf.mk f) μ) (fun _ => 0)

def pinnedNestedProduct (μ : Measure α) (ν : Measure β) : Measure (α × β) :=
  Measure.join (pinnedMap (fun x : α => pinnedMap (Prod.mk x) ν) μ)

def guardedProduct (μ : Measure α) (ν : Measure β) : Measure (α × β) :=
  let κ : α → Measure (α × β) := fun x => ν.map (Prod.mk x)
  @ite (Measure (α × β)) (AEMeasurable κ μ)
    (Classical.propDecidable (AEMeasurable κ μ)) (μ.bind κ) 0

theorem pinnedMap_eq_map_of_aemeasurable {f : α → β} {μ : Measure α}
    (hf : AEMeasurable f μ) : pinnedMap f μ = μ.map f := by
  simp only [pinnedMap, dite_eq_left hf]
  exact Measure.mapₗ_mk_apply_of_aemeasurable hf

theorem pinnedMap_eq_zero_of_not_aemeasurable {f : α → β} {μ : Measure α}
    (hf : ¬ AEMeasurable f μ) : pinnedMap f μ = 0 := by
  simp only [pinnedMap, dite_eq_right hf]

/-- This fixed insertion is measurable for every measure, without s-finiteness. -/
theorem pinnedMap_prodMk (ν : Measure β) (x : α) :
    pinnedMap (Prod.mk x) ν = ν.map (Prod.mk x) :=
  pinnedMap_eq_map_of_aemeasurable measurable_prodMk_left.aemeasurable

/-- All measures: the outer map's old zero fallback must remain explicit. -/
theorem guardedProduct_eq_pinnedNestedProduct (μ : Measure α) (ν : Measure β) :
    guardedProduct μ ν = pinnedNestedProduct μ ν := by
  classical
  have hκ : (fun x : α => pinnedMap (Prod.mk x) ν) =
      (fun x : α => ν.map (Prod.mk x)) := by
    funext x
    exact pinnedMap_prodMk ν x
  unfold guardedProduct pinnedNestedProduct
  dsimp only
  rw [hκ]
  by_cases h : AEMeasurable (fun x : α => ν.map (Prod.mk x)) μ
  · simpa only [ite_eq_left h, Measure.bind] using
      congrArg Measure.join (pinnedMap_eq_map_of_aemeasurable h).symm
  · simp only [ite_eq_right h, pinnedMap_eq_zero_of_not_aemeasurable h,
      Measure.join_zero]

/-- The separate s-finite specialization recovers the target's product. -/
theorem guardedProduct_eq_currentProd (μ : Measure α) (ν : Measure β) [SFinite ν] :
    guardedProduct μ ν = μ.prod ν := by
  have hκ : Measurable (fun x : α => ν.map (Prod.mk x)) :=
    Measurable.map_prodMk_left
  have hκAE : AEMeasurable (fun x : α => ν.map (Prod.mk x)) μ := hκ.aemeasurable
  simpa only [guardedProduct, ite_eq_left hκAE] using
    (Measure.prod_eq_of_sfinite μ ν).symm

/-- Generic own-hypothesis certificate for product uses with an s-finite second factor. -/
theorem pinnedNestedProduct_eq_currentProd_of_sfinite
    (μ : Measure α) (ν : Measure β) [SFinite ν] :
    pinnedNestedProduct μ ν = μ.prod ν := by
  exact (guardedProduct_eq_pinnedNestedProduct μ ν).symm.trans
    (guardedProduct_eq_currentProd μ ν)

theorem guardedIntegral_eq_pinnedNestedIntegral
    (μ : Measure α) (ν : Measure β) (f : α × β → ℂ) :
    (∫ p, f p ∂(guardedProduct μ ν)) =
      ∫ p, f p ∂(pinnedNestedProduct μ ν) := by
  rw [guardedProduct_eq_pinnedNestedProduct]

end MeasureSideConditionCertificate
