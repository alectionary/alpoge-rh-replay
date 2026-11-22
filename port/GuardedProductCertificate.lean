import Mathlib
import Formalism.DoubleCosetMeasures.Statement

/-!
Private, uncompiled certificate candidate for M144284.
Archive: 8ec38f92ac54b5c91bc07f4f6f88ea61691b7975.
Pinned Mathlib: 0df444a360eaa60ab8c11dca51a86af692955474.
Target Mathlib: fc4f59e577feb1a4956671bc04ac18aaaf8cd842.

pinnedMap below copies the literal pinned map branch: the a.e.-measurable
representative is pushed forward with mapₗ; the other branch is zero.
pinnedNestedProduct then expands the pinned prod and bind definitions, including
BOTH old map calls. The current join and mapₗ measurable branch retain their
pinned constructions. The source comparisons are recorded in the accompanying
primary-source and API evidence.

No declaration in the contribution source is changed by this private file.
This file is a candidate proof, not an assertion that Lean has checked it.
The actual-BB theorems below require the reviewed repaired Statement source
SHA256 f232870a0bb149de3d9bfa9dace5626e1ce10374e903e501a499475692800f21,
not the unrepaired accepted source. Their definitional link must be checked
after that exact source patch has been applied.
-/

noncomputable section

open MeasureTheory

namespace M144284SemanticRepairCertificate

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

section BB

open Formalism.DoubleCosetMeasures

variable {K : Type} [CommRing K] [TopologicalSpace K] [IsTopologicalRing K]

/--
The exact proposed BB body, using @ite and Classical.propDecidable explicitly.
It adds no ambient namespace opening, instance, hypothesis, import or option to BB.
It must coincide definitionally with imported BB on the reviewed repaired source.
-/
def repairedBBTerm (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) : ℂ :=
  let κ : lowW K s t → Measure (lowW K s t × upUniG K s.sum) :=
    fun x => μ₂.map (Prod.mk x)
  ∫ p, phi R s t ψ C e lam p ∂(
    @ite (Measure (lowW K s t × upUniG K s.sum)) (AEMeasurable κ μ₁)
      (Classical.propDecidable (AEMeasurable κ μ₁)) (μ₁.bind κ) 0)

theorem repairedBBTerm_eq_pinnedExpansion
    (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) :
    repairedBBTerm R s t ψ C e lam μ₁ μ₂ =
      ∫ p, phi R s t ψ C e lam p ∂(pinnedNestedProduct μ₁ μ₂) := by
  change (∫ p, phi R s t ψ C e lam p ∂(guardedProduct μ₁ μ₂)) = _
  rw [guardedProduct_eq_pinnedNestedProduct]

/-- This specialization compares with the current Mathlib product, independently of BB's source. -/
theorem repairedBBTerm_eq_currentProdIntegral_of_sfinite
    (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) [SFinite μ₂] :
    repairedBBTerm R s t ψ C e lam μ₁ μ₂ =
      ∫ p, phi R s t ψ C e lam p ∂(μ₁.prod μ₂) := by
  change (∫ p, phi R s t ψ C e lam p ∂(guardedProduct μ₁ μ₂)) =
    ∫ p, phi R s t ψ C e lam p ∂(μ₁.prod μ₂)
  rw [guardedProduct_eq_currentProd]

/-- Definitional link to the actual imported BB; valid only on the reviewed repaired source. -/
theorem actualBB_eq_repairedBBTerm
    (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) :
    BB R s t ψ C e lam μ₁ μ₂ = repairedBBTerm R s t ψ C e lam μ₁ μ₂ := by
  rfl

/-- Actual repaired BB preserves the literal pinned nested expansion for all measures. -/
theorem actualBB_eq_pinnedExpansion
    (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) :
    BB R s t ψ C e lam μ₁ μ₂ =
      ∫ p, phi R s t ψ C e lam p ∂(pinnedNestedProduct μ₁ μ₂) := by
  exact (actualBB_eq_repairedBBTerm R s t ψ C e lam μ₁ μ₂).trans
    (repairedBBTerm_eq_pinnedExpansion R s t ψ C e lam μ₁ μ₂)

/-- This separate specialization also checks the new source compatibility helper's exact API. -/
theorem actualBB_eq_currentProdIntegral_of_sfinite
    (R : Subring K) (s : List ℕ) (t : ℕ → Kˣ) (ψ : AddChar K ℂ)
    (C : Type) [AddCommGroup C] [Module R C] (e : C) (lam : C →ₗ[R] KR R)
    (μ₁ : Measure (lowW K s t)) (μ₂ : Measure (upUniG K s.sum)) [SFinite μ₂] :
    BB R s t ψ C e lam μ₁ μ₂ =
      ∫ p, phi R s t ψ C e lam p ∂(μ₁.prod μ₂) := by
  exact BB_eq_prod_of_sfinite R s t ψ C e lam μ₁ μ₂

end BB

end M144284SemanticRepairCertificate
