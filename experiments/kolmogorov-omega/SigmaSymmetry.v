(** * SigmaSymmetry.v

    A Rocq 9.0 formalization of the sigma-symmetry theorem for the
    two-register bounded register machine studied in RESULTS.md.

    For every ISA whose four variable opcodes are drawn from one of two
    closed sets, and whose INC and DEC opcode counts balance, the
    halting predicate is preserved by the state involution sigma that
    negates both registers mod 256. The set of length-8 programs that
    halt from initial state (a, 0) is in bijection with the set of
    length-8 programs that halt from (-a, 0); consequently the halting
    count -- and therefore the halting fraction Omega = count / 6^8 --
    is invariant under a ↦ -a.

    Both cases are proved in this file:

    - Case A (Part II):
      C_A = { INC, DEC, SWP, ADD, NEG, MOV, SUB, SHL, NOP }.
      sigma commutes with each of these primitives unconditionally.

    - Case B (Part III):
      C_B = { INC, DEC, ADD, XOR, NEG, SUB, AND, OR, SHL, NOP }.
      SWP and MOV are excluded (they are the only primitives that
      write to register B); SHR and CPL are also excluded (they
      break sigma-equivariance even on b = 0). With b held at 0,
      the bitwise primitives XOR, AND, OR reduce to sigma-symmetric
      operations on register A, and an invariant-subspace argument
      pushes the result through execution.

    The set-cardinality corollary [halting_count_sigma_symmetric]
    (Part IV) lifts the program-level bijection to an equality of
    halting counts via an exhaustive enumeration of length-8 programs;
    [halting_fraction_sigma_symmetric] (Part V) divides by 6^8 to
    state the result at the Omega level used in the paper.

    Build: rocq compile SigmaSymmetry.v
*)

From Stdlib Require Import ZArith QArith List Lia Bool Permutation.
Import ListNotations.
Open Scope Z_scope.

(* ------------------------------------------------------------------ *)
(* Machine model.                                                      *)
(* ------------------------------------------------------------------ *)

Definition Modulus : Z := 256.
Definition NLen   : nat := 8%nat.
Definition Tmax   : nat := 256%nat.

Lemma Modulus_pos : 0 < Modulus.
Proof. unfold Modulus; lia. Qed.

Lemma Modulus_nonzero : Modulus <> 0.
Proof. unfold Modulus; lia. Qed.

Record State : Type := mkState { regA : Z; regB : Z; pc : nat }.

Inductive primitive : Type :=
| PInc | PDec | PSwp | PAdd | PNeg | PMov | PSub | PShl | PNop
| PXor | PAnd | POr | PShr | PCpl.

(** [apply_prim p s] applies primitive [p] to [s] and advances the PC. *)
Definition apply_prim (p : primitive) (s : State) : State :=
  match p with
  | PInc => mkState ((regA s + 1) mod Modulus) (regB s)             (S (pc s))
  | PDec => mkState ((regA s - 1) mod Modulus) (regB s)             (S (pc s))
  | PSwp => mkState (regB s)                    (regA s)            (S (pc s))
  | PAdd => mkState ((regA s + regB s) mod Modulus) (regB s)        (S (pc s))
  | PNeg => mkState ((- regA s) mod Modulus)  (regB s)              (S (pc s))
  | PMov => mkState (regA s)                    (regA s)            (S (pc s))
  | PSub => mkState ((regA s - regB s) mod Modulus) (regB s)        (S (pc s))
  | PShl => mkState ((2 * regA s) mod Modulus) (regB s)             (S (pc s))
  | PNop => mkState (regA s)                    (regB s)            (S (pc s))
  | PXor => mkState (Z.lxor (regA s) (regB s) mod Modulus) (regB s) (S (pc s))
  | PAnd => mkState (Z.land (regA s) (regB s) mod Modulus) (regB s) (S (pc s))
  | POr  => mkState (Z.lor  (regA s) (regB s) mod Modulus) (regB s) (S (pc s))
  | PShr => mkState (Z.shiftr (regA s) 1 mod Modulus) (regB s)      (S (pc s))
  | PCpl => mkState ((Modulus - 1 - regA s) mod Modulus) (regB s)   (S (pc s))
  end.

Record ISA : Type := mkISA { op1 : primitive; op2 : primitive;
                             op3 : primitive; op4 : primitive }.

(** Opcodes 0 (INC) and 5 (JNZ) are fixed; opcodes 1..4 are the ISA's. *)
Definition step_opcode (isa : ISA) (o : nat) (s : State) : State :=
  match o with
  | 0%nat => apply_prim PInc s
  | 1%nat => apply_prim (op1 isa) s
  | 2%nat => apply_prim (op2 isa) s
  | 3%nat => apply_prim (op3 isa) s
  | 4%nat => apply_prim (op4 isa) s
  | 5%nat =>
      if Z.eqb (regA s) 0 then
        mkState (regA s) (regB s) (S (pc s))
      else
        mkState (regA s) (regB s) 0%nat
  | _ => s
  end.

Definition Program := list nat.
Definition fetch (p : Program) (i : nat) : nat := nth i p 0%nat.

Definition step (isa : ISA) (p : Program) (s : State) : option State :=
  if Nat.leb NLen (pc s) then None
  else Some (step_opcode isa (fetch p (pc s)) s).

Fixpoint execute (isa : ISA) (p : Program) (s : State) (n : nat) : bool :=
  match n with
  | O    => false
  | S n' =>
      match step isa p s with
      | None    => true
      | Some s' => execute isa p s' n'
      end
  end.

Definition halts (isa : ISA) (p : Program) (s : State) : bool :=
  execute isa p s Tmax.

(** The initial state for initial accumulator [a] is [(a mod 256, 0, 0)]. *)
Definition init_state (a : Z) : State := mkState (a mod Modulus) 0 0%nat.

(* ------------------------------------------------------------------ *)
(* Arithmetic lemmas for mod 256.                                      *)
(* ------------------------------------------------------------------ *)

Lemma neg_neg_mod : forall x : Z,
  ((- ((- x) mod Modulus)) mod Modulus) = x mod Modulus.
Proof.
  intro x.
  pose proof (Z_div_mod_eq_full (- x) Modulus) as Heq.
  set (q := (- x) / Modulus) in Heq.
  set (r := (- x) mod Modulus) in *.
  assert (- r = x + q * Modulus) as Hr by lia.
  rewrite Hr.
  apply Z_mod_plus_full.
Qed.

(* ------------------------------------------------------------------ *)
(* Involution sigma.                                                   *)
(* ------------------------------------------------------------------ *)

Definition neg_byte (x : Z) : Z := (- x) mod Modulus.

Definition sigma (s : State) : State :=
  mkState (neg_byte (regA s)) (neg_byte (regB s)) (pc s).

Lemma neg_byte_range : forall x, 0 <= neg_byte x < Modulus.
Proof. intro. apply Z.mod_pos_bound. apply Modulus_pos. Qed.

Lemma neg_byte_invol_modded : forall x : Z,
  neg_byte (neg_byte x) = x mod Modulus.
Proof.
  intros. unfold neg_byte. apply neg_neg_mod.
Qed.

Lemma neg_byte_zero : neg_byte 0 = 0.
Proof.
  unfold neg_byte. simpl. apply Zmod_0_l.
Qed.

Lemma neg_byte_eq_zero_iff : forall x,
  0 <= x < Modulus -> (neg_byte x = 0 <-> x = 0).
Proof.
  intros x [H0 H1]. unfold neg_byte. split.
  - intro Hmod.
    destruct (Z.eq_dec x 0) as [->|Hne]; [reflexivity|].
    exfalso.
    assert (0 < x < Modulus) as Hx by lia.
    assert ((- x) mod Modulus = Modulus - x) as Heq.
    { replace (- x) with (Modulus - x + (-1) * Modulus) by ring.
      rewrite Z_mod_plus_full. apply Zmod_small. unfold Modulus in *; lia. }
    rewrite Heq in Hmod. unfold Modulus in *; lia.
  - intro. subst. apply Zmod_0_l.
Qed.

(* ------------------------------------------------------------------ *)
(* Per-primitive sigma-equivariance.                                   *)
(* ------------------------------------------------------------------ *)

(** [sigma_conj p] is the sigma-conjugate primitive of [p]: INC <-> DEC,
    all others fixed. *)
Definition sigma_conj (p : primitive) : primitive :=
  match p with
  | PInc => PDec
  | PDec => PInc
  | q    => q
  end.

Lemma sigma_conj_invol : forall p, sigma_conj (sigma_conj p) = p.
Proof. destruct p; reflexivity. Qed.

(** Key arithmetic lemma: opposite distributes through mod. *)
Lemma opp_mod_distr : forall x,
  (- (x mod Modulus)) mod Modulus = (- x) mod Modulus.
Proof.
  intro x.
  pose proof (Z_div_mod_eq_full x Modulus) as Heq.
  set (q := x / Modulus) in Heq.
  set (r := x mod Modulus) in *.
  assert (- x = - r + (- q) * Modulus) as Hnx by lia.
  rewrite Hnx. symmetry. apply Z_mod_plus_full.
Qed.

(** Add-by-constant commutes with mod reduction on the left operand. *)
Lemma mod_add_const : forall y k,
  (y mod Modulus + k) mod Modulus = (y + k) mod Modulus.
Proof.
  intros y k.
  pose proof (Z_div_mod_eq_full y Modulus) as Heq.
  set (q := y / Modulus) in Heq.
  set (r := y mod Modulus) in *.
  assert (y + k = (r + k) + q * Modulus) as Hyk by lia.
  rewrite Hyk. symmetry. apply Z_mod_plus_full.
Qed.

Lemma mod_sub_const : forall y k,
  (y mod Modulus - k) mod Modulus = (y - k) mod Modulus.
Proof.
  intros y k.
  pose proof (Z_div_mod_eq_full y Modulus) as Heq.
  set (q := y / Modulus) in Heq.
  set (r := y mod Modulus) in *.
  assert (y - k = (r - k) + q * Modulus) as Hyk by lia.
  rewrite Hyk. symmetry. apply Z_mod_plus_full.
Qed.

Lemma mod_opp_add : forall x y,
  (- ((x + y) mod Modulus)) mod Modulus
  = ((- x) mod Modulus + (- y) mod Modulus) mod Modulus.
Proof.
  intros x y. rewrite opp_mod_distr.
  replace (- (x + y)) with ((- x) + (- y)) by ring.
  rewrite Zplus_mod. reflexivity.
Qed.

Lemma mod_opp_sub : forall x y,
  (- ((x - y) mod Modulus)) mod Modulus
  = ((- x) mod Modulus - (- y) mod Modulus) mod Modulus.
Proof.
  intros x y. rewrite opp_mod_distr.
  replace (- (x - y)) with ((- x) - (- y)) by ring.
  rewrite Zminus_mod. reflexivity.
Qed.

Lemma mod_opp_mul2 : forall x,
  (- ((2 * x) mod Modulus)) mod Modulus
  = (2 * ((- x) mod Modulus)) mod Modulus.
Proof.
  intros x. rewrite opp_mod_distr.
  replace (- (2 * x)) with (2 * (- x)) by ring.
  symmetry. apply Z.mul_mod_idemp_r. apply Modulus_nonzero.
Qed.

Lemma mod_opp_succ : forall x,
  (- ((x + 1) mod Modulus)) mod Modulus = ((- x) mod Modulus - 1) mod Modulus.
Proof.
  intros x. rewrite opp_mod_distr. rewrite mod_sub_const.
  f_equal. ring.
Qed.

Lemma mod_opp_pred : forall x,
  (- ((x - 1) mod Modulus)) mod Modulus = ((- x) mod Modulus + 1) mod Modulus.
Proof.
  intros x. rewrite opp_mod_distr. rewrite mod_add_const.
  f_equal. ring.
Qed.

Lemma mod_opp_self : forall x,
  (- ((- x) mod Modulus)) mod Modulus = x mod Modulus.
Proof. intros. apply neg_neg_mod. Qed.

(** Membership in C_A: the nine primitives admitted by Case A. *)
Definition is_CA_prim (p : primitive) : bool :=
  match p with
  | PInc | PDec | PSwp | PAdd | PNeg | PMov | PSub | PShl | PNop => true
  | _ => false
  end.

(** Membership in C_B: primitives admitted by Case B (no SWP, no MOV). *)
Definition is_CB_prim (p : primitive) : bool :=
  match p with
  | PInc | PDec | PAdd | PNeg | PSub | PShl | PNop
  | PXor | PAnd | POr => true
  | _ => false
  end.

(** The central per-primitive theorem: for every primitive [p] in the closed
    set C_A, [sigma (apply_prim p s)] equals [apply_prim (sigma_conj p) (sigma s)]. *)
Theorem sigma_equivariance : forall (p : primitive) (s : State),
  is_CA_prim p = true ->
  sigma (apply_prim p s) = apply_prim (sigma_conj p) (sigma s).
Proof.
  intros p [a b pcv] Hca.
  destruct p; simpl in Hca; try discriminate Hca;
    simpl; unfold sigma, neg_byte; simpl; try reflexivity.
  - (* PInc → PDec *) f_equal. apply mod_opp_succ.
  - (* PDec → PInc *) f_equal. apply mod_opp_pred.
  - (* PAdd *)        f_equal. apply mod_opp_add.
  - (* PSub *)        f_equal. apply mod_opp_sub.
  - (* PShl *)        f_equal. apply mod_opp_mul2.
Qed.

(* ------------------------------------------------------------------ *)
(* Opcode-level involution F.                                          *)
(* ------------------------------------------------------------------ *)

(** An ISA is "sigma-closed" when each of its four variable primitives
    lies in the closed set C_A. All members of C_A are sigma-conjugated
    into C_A by [sigma_conj] (this is a consequence of how C_A was
    defined: it is the image of sigma_conj restricted to C_A). *)

Definition in_CA (p : primitive) : bool := is_CA_prim p.

Definition isa_in_CA (isa : ISA) : bool :=
  (in_CA (op1 isa)) && (in_CA (op2 isa))
  && (in_CA (op3 isa)) && (in_CA (op4 isa)).

(** An opcode-level involution [F : nat -> nat] on {0..5} — used to
    pair each INC-mapped opcode slot with a DEC-mapped one, and to
    fix slots whose primitive is sigma-self-conjugate. *)

Definition OpcodeInvol := nat -> nat.

Definition bounded_state (s : State) : Prop :=
  0 <= regA s < Modulus /\ 0 <= regB s < Modulus.

Definition valid_F (isa : ISA) (F : OpcodeInvol) : Prop :=
  (forall o, (o < 6)%nat -> (F o < 6)%nat) /\
  (forall o, (o < 6)%nat -> F (F o) = o) /\
  (* F fixes JNZ (opcode 5) *)
  (F 5%nat = 5%nat) /\
  (* Key: F conjugates the step function under sigma. The boundedness
     hypothesis is needed for JNZ, whose branching tests [regA s = 0]:
     [sigma] maps 0 ↦ 0 only when the accumulator is in its canonical range. *)
  (forall o s, (o < 6)%nat -> bounded_state s ->
    step_opcode isa (F o) (sigma s) = sigma (step_opcode isa o s)).

(* ------------------------------------------------------------------ *)
(* JNZ commutes with sigma.                                             *)
(* ------------------------------------------------------------------ *)

Lemma neg_byte_eqb_zero : forall x,
  0 <= x < Modulus -> Z.eqb (neg_byte x) 0 = Z.eqb x 0.
Proof.
  intros x Hrange.
  destruct (Z.eq_dec x 0) as [Hx|Hx].
  - subst. rewrite neg_byte_zero. reflexivity.
  - assert (neg_byte x <> 0) as Hnb.
    { intro Hc. apply (proj1 (neg_byte_eq_zero_iff x Hrange)) in Hc. contradiction. }
    apply Z.eqb_neq in Hx. apply Z.eqb_neq in Hnb.
    rewrite Hx, Hnb. reflexivity.
Qed.

(* ------------------------------------------------------------------ *)
(* Program-level lifting.                                              *)
(* ------------------------------------------------------------------ *)

(** F lifted to programs: replace each opcode o with F o. *)
Definition F_prog (F : OpcodeInvol) (p : Program) : Program := map F p.

Lemma F_prog_invol : forall F p,
  (forall o, In o p -> (o < 6)%nat) ->
  (forall o, (o < 6)%nat -> F (F o) = o) ->
  F_prog F (F_prog F p) = p.
Proof.
  intros F p Hp HinvF.
  unfold F_prog. rewrite map_map.
  induction p as [|o rest IH]; simpl; [reflexivity|].
  assert (In o (o :: rest)) as Ho by (left; reflexivity).
  rewrite HinvF by (apply Hp; exact Ho).
  f_equal. apply IH. intros. apply Hp. right; assumption.
Qed.

(* ------------------------------------------------------------------ *)
(* Execution equivariance: the main load-bearing lemma.                *)
(* ------------------------------------------------------------------ *)

(** Every opcode appearing in valid programs is < 6. *)
Definition valid_prog (p : Program) : Prop :=
  forall o, In o p -> (o < 6)%nat.

Lemma apply_prim_bounded : forall p s,
  bounded_state s -> bounded_state (apply_prim p s).
Proof.
  intros p [a b pcv] [HA HB].
  destruct p; unfold bounded_state; simpl;
    (split; [try exact HA; try exact HB; apply Z.mod_pos_bound; apply Modulus_pos
           | try exact HA; try exact HB; apply Z.mod_pos_bound; apply Modulus_pos]).
Qed.

Lemma step_opcode_bounded : forall isa o s,
  bounded_state s -> bounded_state (step_opcode isa o s).
Proof.
  intros isa o s H.
  destruct o as [|[|[|[|[|[|?]]]]]]; unfold step_opcode.
  - apply apply_prim_bounded; exact H.
  - apply apply_prim_bounded; exact H.
  - apply apply_prim_bounded; exact H.
  - apply apply_prim_bounded; exact H.
  - apply apply_prim_bounded; exact H.
  - (* JNZ *) destruct H as [HA HB]. unfold bounded_state.
    destruct (Z.eqb (regA s) 0); simpl; split; assumption.
  - exact H.
Qed.

Lemma step_bounded : forall isa p s s',
  bounded_state s -> step isa p s = Some s' -> bounded_state s'.
Proof.
  intros isa p s s' Hb Hstep. unfold step in Hstep.
  destruct (Nat.leb NLen (pc s)); [discriminate|].
  inversion Hstep. subst. apply step_opcode_bounded. exact Hb.
Qed.

Lemma pc_preserved_by_sigma : forall s, pc (sigma s) = pc s.
Proof. intro s. reflexivity. Qed.

Lemma fetch_F_prog : forall F p i,
  (i < length p)%nat ->
  fetch (F_prog F p) i = F (fetch p i).
Proof.
  intros F p i Hlt. unfold F_prog, fetch.
  rewrite (nth_indep _ 0%nat (F 0%nat)) by (rewrite length_map; exact Hlt).
  apply map_nth.
Qed.

(** Strengthened well-formedness: programs have length exactly NLen. *)
Definition wf_prog (p : Program) : Prop :=
  length p = NLen /\ forall o, In o p -> (o < 6)%nat.

Lemma wf_F_prog : forall F p,
  wf_prog p ->
  (forall o, (o < 6)%nat -> (F o < 6)%nat) ->
  wf_prog (F_prog F p).
Proof.
  intros F p [Hlen Hin] Hrange.
  split.
  - unfold F_prog. rewrite length_map. exact Hlen.
  - intros o Ho. unfold F_prog in Ho. rewrite in_map_iff in Ho.
    destruct Ho as [o' [<- Hin']]. apply Hrange. apply Hin. exact Hin'.
Qed.

(** Full execution equivariance by induction on the step budget. *)
Lemma execute_equivariance :
  forall (n : nat) (isa : ISA) (F : OpcodeInvol) (p : Program) (s : State),
    valid_F isa F ->
    wf_prog p ->
    bounded_state s ->
    execute isa p s n = execute isa (F_prog F p) (sigma s) n.
Proof.
  induction n as [|n IH]; intros isa F p s HvF Hwf Hb; [reflexivity|].
  simpl.
  destruct (step isa p s) as [s'|] eqn:Hstep.
  - (* Some s' *)
    assert (step isa (F_prog F p) (sigma s) = Some (sigma s')) as Hstep'.
    { unfold step in *.
      rewrite pc_preserved_by_sigma.
      destruct (Nat.leb NLen (pc s)) eqn:Hdone; [discriminate|].
      destruct Hwf as [Hlen Hin].
      apply Nat.leb_gt in Hdone.
      assert ((pc s < length p)%nat) as Hpclt.
      { rewrite Hlen. unfold NLen in Hdone. unfold NLen. exact Hdone. }
      rewrite (fetch_F_prog F p (pc s) Hpclt).
      assert ((fetch p (pc s) < 6)%nat) as Hfo.
      { apply Hin. unfold fetch. apply nth_In. exact Hpclt. }
      destruct HvF as [_ [_ [_ Hconj]]].
      specialize (Hconj (fetch p (pc s)) s Hfo Hb).
      rewrite Hconj.
      inversion Hstep. reflexivity. }
    rewrite Hstep'.
    apply IH; [exact HvF | exact Hwf |].
    unfold step in Hstep.
    destruct (Nat.leb NLen (pc s)) eqn:Hdone; [discriminate|].
    inversion Hstep. subst. apply step_opcode_bounded. exact Hb.
  - (* None *)
    assert (step isa (F_prog F p) (sigma s) = None) as Hstep'.
    { unfold step in *.
      rewrite pc_preserved_by_sigma.
      destruct (Nat.leb NLen (pc s)); [reflexivity|discriminate]. }
    rewrite Hstep'. reflexivity.
Qed.

Theorem halts_equivariance :
  forall (isa : ISA) (F : OpcodeInvol) (p : Program) (a : Z),
    valid_F isa F ->
    wf_prog p ->
    0 <= a < Modulus ->
    halts isa p (init_state a) = halts isa (F_prog F p) (init_state (neg_byte a)).
Proof.
  intros isa F p a HvF Hwf Ha.
  unfold halts.
  assert (a mod Modulus = a) as Hamod by (apply Zmod_small; exact Ha).
  assert ((neg_byte a) mod Modulus = neg_byte a) as Hnbmod.
  { apply Zmod_small. apply neg_byte_range. }
  assert (init_state (neg_byte a) = sigma (init_state a)) as Hinit_eq.
  { unfold init_state, sigma. simpl.
    rewrite Hnbmod, Hamod, neg_byte_zero. reflexivity. }
  rewrite Hinit_eq.
  apply execute_equivariance; [exact HvF | exact Hwf |].
  unfold init_state, bounded_state. simpl.
  split; [apply Z.mod_pos_bound; apply Modulus_pos | unfold Modulus; lia].
Qed.

(* ------------------------------------------------------------------ *)
(* Existence of a valid F for balanced Case-A ISAs.                    *)
(* ------------------------------------------------------------------ *)

(** Decidable equality on primitives. *)
Definition primitive_eqb (p q : primitive) : bool :=
  match p, q with
  | PInc, PInc | PDec, PDec | PSwp, PSwp | PAdd, PAdd
  | PNeg, PNeg | PMov, PMov | PSub, PSub | PShl, PShl | PNop, PNop
  | PXor, PXor | PAnd, PAnd | POr, POr | PShr, PShr | PCpl, PCpl => true
  | _, _ => false
  end.

Lemma primitive_eqb_eq : forall p q, primitive_eqb p q = true <-> p = q.
Proof.
  intros p q. split.
  - destruct p, q; simpl; intro H; try discriminate; reflexivity.
  - intro H; subst; destruct q; reflexivity.
Qed.

Lemma primitive_eqb_refl : forall p, primitive_eqb p p = true.
Proof. destruct p; reflexivity. Qed.

Lemma primitive_eqb_neq : forall p q, primitive_eqb p q = false <-> p <> q.
Proof.
  intros p q. split.
  - intros H Heq. subst. rewrite primitive_eqb_refl in H. discriminate.
  - intros Hneq. destruct (primitive_eqb p q) eqn:E; [|reflexivity].
    apply primitive_eqb_eq in E. contradiction.
Qed.


(** A Case-A ISA: all four variable opcodes in C_A and INC/DEC balanced. *)
Definition count_inc_slots (isa : ISA) : nat :=
  (if primitive_eqb (op1 isa) PInc then 1 else 0)
  + (if primitive_eqb (op2 isa) PInc then 1 else 0)
  + (if primitive_eqb (op3 isa) PInc then 1 else 0)
  + (if primitive_eqb (op4 isa) PInc then 1 else 0).

Definition count_dec_slots (isa : ISA) : nat :=
  (if primitive_eqb (op1 isa) PDec then 1 else 0)
  + (if primitive_eqb (op2 isa) PDec then 1 else 0)
  + (if primitive_eqb (op3 isa) PDec then 1 else 0)
  + (if primitive_eqb (op4 isa) PDec then 1 else 0).

Definition case_A_isa (isa : ISA) : Prop :=
  is_CA_prim (op1 isa) = true /\
  is_CA_prim (op2 isa) = true /\
  is_CA_prim (op3 isa) = true /\
  is_CA_prim (op4 isa) = true /\
  (1 + count_inc_slots isa)%nat = count_dec_slots isa.

(** The primitive at slot [o] for o in {0,1,2,3,4}. Slot 0 is always INC. *)
Definition primitive_at_slot (isa : ISA) (o : nat) : primitive :=
  match o with
  | 0%nat => PInc
  | 1%nat => op1 isa
  | 2%nat => op2 isa
  | 3%nat => op3 isa
  | 4%nat => op4 isa
  | _     => PNop
  end.

Lemma case_A_primitive_at_slot : forall isa o,
  case_A_isa isa -> (o <= 4)%nat -> is_CA_prim (primitive_at_slot isa o) = true.
Proof.
  intros isa o [H1 [H2 [H3 [H4 _]]]] Ho.
  destruct o as [|[|[|[|[|?]]]]]; simpl; try reflexivity; try assumption; lia.
Qed.

(** A transposition of opcodes [i] and [j]: swaps them, fixes all others. *)
Definition swap2 (i j o : nat) : nat :=
  if Nat.eqb o i then j else if Nat.eqb o j then i else o.

Lemma swap2_invol : forall i j o,
  i <> j -> swap2 i j (swap2 i j o) = o.
Proof.
  intros i j o Hneq. unfold swap2.
  destruct (Nat.eqb o i) eqn:Hoi.
  - apply Nat.eqb_eq in Hoi. subst.
    destruct (Nat.eqb j i) eqn:Hji.
    + apply Nat.eqb_eq in Hji. congruence.
    + rewrite Nat.eqb_refl. reflexivity.
  - destruct (Nat.eqb o j) eqn:Hoj.
    + apply Nat.eqb_eq in Hoj. subst. rewrite Nat.eqb_refl. reflexivity.
    + rewrite Hoi, Hoj. reflexivity.
Qed.

Lemma swap2_self : forall i j o, o <> i -> o <> j -> swap2 i j o = o.
Proof.
  intros i j o H1 H2. unfold swap2.
  apply Nat.eqb_neq in H1. apply Nat.eqb_neq in H2.
  rewrite H1, H2. reflexivity.
Qed.

Lemma swap2_i : forall i j, swap2 i j i = j.
Proof. intros. unfold swap2. rewrite Nat.eqb_refl. reflexivity. Qed.

Lemma swap2_j : forall i j, i <> j -> swap2 i j j = i.
Proof.
  intros i j Hneq. unfold swap2.
  destruct (Nat.eqb j i) eqn:Hji.
  - apply Nat.eqb_eq in Hji. congruence.
  - rewrite Nat.eqb_refl. reflexivity.
Qed.

(** Two disjoint transpositions commute. *)
Lemma swap2_swap2_commute : forall i1 j1 i2 j2 o,
  i1 <> i2 -> i1 <> j2 -> j1 <> i2 -> j1 <> j2 ->
  swap2 i1 j1 (swap2 i2 j2 o) = swap2 i2 j2 (swap2 i1 j1 o).
Proof.
  intros i1 j1 i2 j2 o H1 H2 H3 H4. unfold swap2.
  destruct (Nat.eqb o i2) eqn:E1;
    destruct (Nat.eqb o j2) eqn:E2;
    destruct (Nat.eqb o i1) eqn:E3;
    destruct (Nat.eqb o j1) eqn:E4;
    repeat match goal with
           | H : Nat.eqb _ _ = true |- _ => apply Nat.eqb_eq in H; subst
           | H : Nat.eqb _ _ = false |- _ => apply Nat.eqb_neq in H
           end;
    repeat match goal with
           | |- context[Nat.eqb ?x ?y] => destruct (Nat.eqb x y) eqn:?
           end;
    repeat match goal with
           | H : Nat.eqb _ _ = true |- _ => apply Nat.eqb_eq in H; subst
           | H : Nat.eqb _ _ = false |- _ => apply Nat.eqb_neq in H
           end;
    try congruence; try reflexivity.
Qed.

(** [fold_swaps] composes [swap2] applications over a list of pairs,
    folding right-to-left. This generalizes both the single-swap
    zero-extra-INC case and the two-swap one-extra-INC case of
    [construct_F] into a single [list (nat * nat) -> nat -> nat]
    operation. *)
Fixpoint fold_swaps (pairs : list (nat * nat)) (o : nat) : nat :=
  match pairs with
  | [] => o
  | (i, j) :: rest => swap2 i j (fold_swaps rest o)
  end.

(** All first and second components of a pair list, flattened. *)
Fixpoint pair_elts (pairs : list (nat * nat)) : list nat :=
  match pairs with
  | [] => []
  | (i, j) :: rest => i :: j :: pair_elts rest
  end.

(** Disjointness: every pair's components are distinct from every other's. *)
Definition pairs_distinct (pairs : list (nat * nat)) : Prop :=
  NoDup (pair_elts pairs).

Lemma pair_elts_in_fst : forall pairs i j,
  In (i, j) pairs -> In i (pair_elts pairs).
Proof.
  induction pairs as [|[i' j'] rest IH]; intros i j Hin; simpl in Hin.
  - contradiction.
  - destruct Hin as [Heq|Hin].
    + inversion Heq; subst. simpl. left; reflexivity.
    + simpl. right; right. apply (IH i j). exact Hin.
Qed.

Lemma pair_elts_in_snd : forall pairs i j,
  In (i, j) pairs -> In j (pair_elts pairs).
Proof.
  induction pairs as [|[i' j'] rest IH]; intros i j Hin; simpl in Hin.
  - contradiction.
  - destruct Hin as [Heq|Hin].
    + inversion Heq; subst. simpl. right; left; reflexivity.
    + simpl. right; right. apply (IH i j). exact Hin.
Qed.

(** If [o] doesn't appear in any pair, [fold_swaps] fixes [o]. *)
Lemma fold_swaps_fixes_outside : forall pairs o,
  ~ In o (pair_elts pairs) -> fold_swaps pairs o = o.
Proof.
  induction pairs as [|[i j] rest IH]; intros o Hni; simpl in *; [reflexivity|].
  rewrite IH by (intro H; apply Hni; right; right; exact H).
  apply swap2_self.
  - intro H; apply Hni; left; congruence.
  - intro H; apply Hni; right; left; congruence.
Qed.

(** When [i] and [j] don't appear in a pair list, [swap2 i j] commutes
    with [fold_swaps] over that list. *)
Lemma swap2_fold_swaps_commute : forall i j pairs o,
  ~ In i (pair_elts pairs) ->
  ~ In j (pair_elts pairs) ->
  swap2 i j (fold_swaps pairs o) = fold_swaps pairs (swap2 i j o).
Proof.
  intros i j pairs. induction pairs as [|[k l] rest IH]; intros o Hni Hnj;
    simpl in *; [reflexivity|].
  assert (Hnk_i : i <> k) by (intro H; apply Hni; left; congruence).
  assert (Hnk_j : j <> k) by (intro H; apply Hnj; left; congruence).
  assert (Hnl_i : i <> l) by (intro H; apply Hni; right; left; congruence).
  assert (Hnl_j : j <> l) by (intro H; apply Hnj; right; left; congruence).
  rewrite swap2_swap2_commute; try assumption.
  rewrite IH; try reflexivity;
    intro H; [apply Hni | apply Hnj]; right; right; exact H.
Qed.

(** A product of disjoint transpositions is an involution. *)
Lemma fold_swaps_invol : forall pairs o,
  pairs_distinct pairs ->
  fold_swaps pairs (fold_swaps pairs o) = o.
Proof.
  induction pairs as [|[i j] rest IH]; intros o Hdistinct; simpl; [reflexivity|].
  unfold pairs_distinct in Hdistinct. simpl in Hdistinct.
  inversion Hdistinct as [|? ? Hni_rest Hdist']. subst.
  inversion Hdist' as [|? ? Hnj_rest Hdist'']. subst.
  assert (Hni : ~ In i (pair_elts rest)).
  { intro H. apply Hni_rest. right. exact H. }
  assert (Hij : i <> j).
  { intro Heq. apply Hni_rest. left. congruence. }
  rewrite swap2_fold_swaps_commute by assumption.
  rewrite swap2_invol by exact Hij.
  apply IH. exact Hdist''.
Qed.

(** Range preservation: if all pair components are bounded, so is the result. *)
Lemma fold_swaps_range : forall pairs o bound,
  (forall p, In p pairs -> (fst p < bound)%nat /\ (snd p < bound)%nat) ->
  (o < bound)%nat ->
  (fold_swaps pairs o < bound)%nat.
Proof.
  induction pairs as [|[i j] rest IH]; intros o bound Hp Ho; simpl; [exact Ho|].
  assert (Hhd : (i < bound)%nat /\ (j < bound)%nat).
  { apply (Hp (i, j)). left. reflexivity. }
  assert (Hrest : (fold_swaps rest o < bound)%nat).
  { apply IH; [|exact Ho]. intros p Hin. apply Hp. right. exact Hin. }
  unfold swap2.
  destruct (Nat.eqb (fold_swaps rest o) i); [apply Hhd|].
  destruct (Nat.eqb (fold_swaps rest o) j); [apply Hhd|]. exact Hrest.
Qed.

(** A two-pair specialization: swap_compose is fold_swaps applied to a
    two-element list. Kept as a thin convenience wrapper. *)
Definition swap_compose (i1 j1 i2 j2 o : nat) : nat :=
  swap2 i2 j2 (swap2 i1 j1 o).

Lemma swap_compose_is_fold_swaps : forall i1 j1 i2 j2 o,
  swap_compose i1 j1 i2 j2 o = fold_swaps [(i2, j2); (i1, j1)] o.
Proof. intros. reflexivity. Qed.

Lemma swap_compose_invol :
  forall i1 j1 i2 j2,
    i1 <> j1 -> i2 <> j2 ->
    i1 <> i2 -> i1 <> j2 -> j1 <> i2 -> j1 <> j2 ->
    forall o, swap_compose i1 j1 i2 j2 (swap_compose i1 j1 i2 j2 o) = o.
Proof.
  intros i1 j1 i2 j2 Hij1 Hij2 Hi12 Hij12a Hij12b Hjj12 o.
  rewrite !swap_compose_is_fold_swaps.
  apply fold_swaps_invol.
  unfold pairs_distinct. simpl.
  repeat apply NoDup_cons; simpl; try intuition lia.
  apply NoDup_nil.
Qed.

(** For a Case-A ISA, [find_dec_slot] returns the smallest slot in 1..4
    that maps to DEC. If no such slot exists the function returns 0. *)
Definition find_dec_slot (isa : ISA) : nat :=
  if primitive_eqb (op1 isa) PDec then 1%nat
  else if primitive_eqb (op2 isa) PDec then 2%nat
  else if primitive_eqb (op3 isa) PDec then 3%nat
  else if primitive_eqb (op4 isa) PDec then 4%nat
  else 0%nat.

Definition find_other_dec_slot (isa : ISA) (skip : nat) : nat :=
  if andb (negb (Nat.eqb skip 1%nat)) (primitive_eqb (op1 isa) PDec) then 1%nat
  else if andb (negb (Nat.eqb skip 2%nat)) (primitive_eqb (op2 isa) PDec) then 2%nat
  else if andb (negb (Nat.eqb skip 3%nat)) (primitive_eqb (op3 isa) PDec) then 3%nat
  else if andb (negb (Nat.eqb skip 4%nat)) (primitive_eqb (op4 isa) PDec) then 4%nat
  else 0%nat.

Definition find_inc_slot (isa : ISA) : nat :=
  if primitive_eqb (op1 isa) PInc then 1%nat
  else if primitive_eqb (op2 isa) PInc then 2%nat
  else if primitive_eqb (op3 isa) PInc then 3%nat
  else if primitive_eqb (op4 isa) PInc then 4%nat
  else 0%nat.

(** The list of variable slot positions (1..4) whose primitive is PInc. *)
Definition inc_slot_positions (isa : ISA) : list nat :=
  (if primitive_eqb (op1 isa) PInc then [1%nat] else []) ++
  (if primitive_eqb (op2 isa) PInc then [2%nat] else []) ++
  (if primitive_eqb (op3 isa) PInc then [3%nat] else []) ++
  (if primitive_eqb (op4 isa) PInc then [4%nat] else []).

(** The list of variable slot positions (1..4) whose primitive is PDec. *)
Definition dec_slot_positions (isa : ISA) : list nat :=
  (if primitive_eqb (op1 isa) PDec then [1%nat] else []) ++
  (if primitive_eqb (op2 isa) PDec then [2%nat] else []) ++
  (if primitive_eqb (op3 isa) PDec then [3%nat] else []) ++
  (if primitive_eqb (op4 isa) PDec then [4%nat] else []).

(** The matching used to build [construct_F]: pair slot 0 (always INC) and
    every variable INC-mapped slot with one DEC-mapped slot, in order. *)
Definition case_A_pairs (isa : ISA) : list (nat * nat) :=
  combine (0%nat :: inc_slot_positions isa) (dec_slot_positions isa).

(** Unified F construction: a single [fold_swaps] over the INC/DEC matching.
    Zero-extra-INC ISAs yield a one-pair fold (a single transposition);
    one-extra-INC ISAs yield a two-pair fold; balance rules out more. *)
Definition construct_F (isa : ISA) : OpcodeInvol :=
  fold_swaps (case_A_pairs isa).

(** Shape lemmas for [inc_slot_positions] and [dec_slot_positions] given
    the counts, plus the compatibility lemmas relating [construct_F] to
    its earlier two-branch formulation, are introduced after the length
    lemmas below (search for "construct_F_zero_inc_form"). *)

(* ---- Properties of inc_slot_positions and dec_slot_positions ---- *)

Lemma inc_slot_positions_length : forall isa,
  length (inc_slot_positions isa) = count_inc_slots isa.
Proof.
  intro. unfold inc_slot_positions, count_inc_slots.
  destruct (primitive_eqb (op1 isa) PInc);
  destruct (primitive_eqb (op2 isa) PInc);
  destruct (primitive_eqb (op3 isa) PInc);
  destruct (primitive_eqb (op4 isa) PInc); simpl; rewrite ? length_app; simpl; lia.
Qed.

Lemma dec_slot_positions_length : forall isa,
  length (dec_slot_positions isa) = count_dec_slots isa.
Proof.
  intro. unfold dec_slot_positions, count_dec_slots.
  destruct (primitive_eqb (op1 isa) PDec);
  destruct (primitive_eqb (op2 isa) PDec);
  destruct (primitive_eqb (op3 isa) PDec);
  destruct (primitive_eqb (op4 isa) PDec); simpl; rewrite ? length_app; simpl; lia.
Qed.

(** Shape lemmas: reduce [inc_slot_positions] and [dec_slot_positions] to
    their concrete forms when the counts are known. *)

Lemma inc_slot_positions_empty : forall isa,
  count_inc_slots isa = 0%nat -> inc_slot_positions isa = [].
Proof.
  intros isa H.
  pose proof (inc_slot_positions_length isa) as Hlen.
  rewrite H in Hlen.
  destruct (inc_slot_positions isa); [reflexivity|discriminate].
Qed.

Lemma inc_slot_positions_singleton : forall isa,
  count_inc_slots isa = 1%nat ->
  inc_slot_positions isa = [find_inc_slot isa].
Proof.
  intros isa H.
  unfold inc_slot_positions, find_inc_slot, count_inc_slots in *.
  destruct (primitive_eqb (op1 isa) PInc) eqn:E1;
  destruct (primitive_eqb (op2 isa) PInc) eqn:E2;
  destruct (primitive_eqb (op3 isa) PInc) eqn:E3;
  destruct (primitive_eqb (op4 isa) PInc) eqn:E4;
  simpl in H; try lia; reflexivity.
Qed.

Lemma dec_slot_positions_singleton : forall isa,
  count_dec_slots isa = 1%nat ->
  dec_slot_positions isa = [find_dec_slot isa].
Proof.
  intros isa H.
  unfold dec_slot_positions, find_dec_slot, count_dec_slots in *.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4;
  simpl in H; try lia; reflexivity.
Qed.

Lemma dec_slot_positions_pair : forall isa,
  count_dec_slots isa = 2%nat ->
  dec_slot_positions isa =
    [find_dec_slot isa; find_other_dec_slot isa (find_dec_slot isa)].
Proof.
  intros isa H.
  unfold dec_slot_positions, find_dec_slot, find_other_dec_slot,
         count_dec_slots in *.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4;
  simpl in H; try lia; simpl; reflexivity.
Qed.

(** Compatibility: [construct_F] in the zero-extra-INC case reduces to
    a single transposition. *)
Lemma construct_F_zero_inc_form : forall isa o,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  construct_F isa o = swap2 0%nat (find_dec_slot isa) o.
Proof.
  intros isa o Hinc0 Hdec1.
  unfold construct_F, case_A_pairs.
  rewrite (inc_slot_positions_empty isa Hinc0).
  rewrite (dec_slot_positions_singleton isa Hdec1).
  simpl. reflexivity.
Qed.

(** Compatibility: [construct_F] in the one-extra-INC case reduces to the
    composition of two disjoint transpositions. *)
Lemma construct_F_one_inc_form : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  construct_F isa o = swap2 0%nat (find_dec_slot isa)
    (swap2 (find_inc_slot isa)
           (find_other_dec_slot isa (find_dec_slot isa)) o).
Proof.
  intros isa o Hinc1 Hdec2.
  unfold construct_F, case_A_pairs.
  rewrite (inc_slot_positions_singleton isa Hinc1).
  rewrite (dec_slot_positions_pair isa Hdec2).
  simpl. reflexivity.
Qed.

Lemma construct_F_one_inc_as_swap_compose : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  construct_F isa o =
    swap_compose (find_inc_slot isa)
                 (find_other_dec_slot isa (find_dec_slot isa))
                 0%nat (find_dec_slot isa) o.
Proof.
  intros. rewrite construct_F_one_inc_form by assumption.
  unfold swap_compose. reflexivity.
Qed.

Lemma inc_slot_positions_in_range : forall isa x,
  In x (inc_slot_positions isa) -> (1 <= x <= 4)%nat.
Proof.
  intros isa x Hin. unfold inc_slot_positions in Hin.
  repeat rewrite in_app_iff in Hin.
  destruct Hin as [H1|[H2|[H3|H4]]].
  - destruct (primitive_eqb (op1 isa) PInc); simpl in H1;
      [destruct H1 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op2 isa) PInc); simpl in H2;
      [destruct H2 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op3 isa) PInc); simpl in H3;
      [destruct H3 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op4 isa) PInc); simpl in H4;
      [destruct H4 as [<-|[]]; lia | contradiction].
Qed.

Lemma dec_slot_positions_in_range : forall isa x,
  In x (dec_slot_positions isa) -> (1 <= x <= 4)%nat.
Proof.
  intros isa x Hin. unfold dec_slot_positions in Hin.
  repeat rewrite in_app_iff in Hin.
  destruct Hin as [H1|[H2|[H3|H4]]].
  - destruct (primitive_eqb (op1 isa) PDec); simpl in H1;
      [destruct H1 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op2 isa) PDec); simpl in H2;
      [destruct H2 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op3 isa) PDec); simpl in H3;
      [destruct H3 as [<-|[]]; lia | contradiction].
  - destruct (primitive_eqb (op4 isa) PDec); simpl in H4;
      [destruct H4 as [<-|[]]; lia | contradiction].
Qed.

Lemma inc_slot_positions_primitive : forall isa x,
  In x (inc_slot_positions isa) -> primitive_at_slot isa x = PInc.
Proof.
  intros isa x Hin. unfold inc_slot_positions in Hin.
  repeat rewrite in_app_iff in Hin.
  destruct Hin as [H|[H|[H|H]]];
    [destruct (primitive_eqb (op1 isa) PInc) eqn:E
    |destruct (primitive_eqb (op2 isa) PInc) eqn:E
    |destruct (primitive_eqb (op3 isa) PInc) eqn:E
    |destruct (primitive_eqb (op4 isa) PInc) eqn:E]; simpl in H;
    try contradiction;
    destruct H as [<-|[]]; simpl; apply primitive_eqb_eq; exact E.
Qed.

Lemma dec_slot_positions_primitive : forall isa x,
  In x (dec_slot_positions isa) -> primitive_at_slot isa x = PDec.
Proof.
  intros isa x Hin. unfold dec_slot_positions in Hin.
  repeat rewrite in_app_iff in Hin.
  destruct Hin as [H|[H|[H|H]]];
    [destruct (primitive_eqb (op1 isa) PDec) eqn:E
    |destruct (primitive_eqb (op2 isa) PDec) eqn:E
    |destruct (primitive_eqb (op3 isa) PDec) eqn:E
    |destruct (primitive_eqb (op4 isa) PDec) eqn:E]; simpl in H;
    try contradiction;
    destruct H as [<-|[]]; simpl; apply primitive_eqb_eq; exact E.
Qed.

Lemma inc_slot_positions_NoDup : forall isa, NoDup (inc_slot_positions isa).
Proof.
  intro isa. unfold inc_slot_positions.
  destruct (primitive_eqb (op1 isa) PInc) eqn:E1;
  destruct (primitive_eqb (op2 isa) PInc) eqn:E2;
  destruct (primitive_eqb (op3 isa) PInc) eqn:E3;
  destruct (primitive_eqb (op4 isa) PInc) eqn:E4; simpl;
  repeat (apply NoDup_cons; [simpl; intros H;
    repeat (destruct H as [H|H]; [discriminate|]); contradiction|]);
  apply NoDup_nil.
Qed.

Lemma dec_slot_positions_NoDup : forall isa, NoDup (dec_slot_positions isa).
Proof.
  intro isa. unfold dec_slot_positions.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4; simpl;
  repeat (apply NoDup_cons; [simpl; intros H;
    repeat (destruct H as [H|H]; [discriminate|]); contradiction|]);
  apply NoDup_nil.
Qed.

Lemma inc_dec_slot_positions_disjoint : forall isa x,
  In x (inc_slot_positions isa) -> In x (dec_slot_positions isa) -> False.
Proof.
  intros isa x Hinc Hdec.
  pose proof (inc_slot_positions_primitive isa x Hinc) as Hpi.
  pose proof (dec_slot_positions_primitive isa x Hdec) as Hpd.
  rewrite Hpi in Hpd. discriminate.
Qed.

(** The next set of lemmas establishes structural facts about Case-A ISAs
    so that we can prove [construct_F] satisfies [valid_F]. *)

Lemma count_inc_slots_bound : forall isa, (count_inc_slots isa <= 4)%nat.
Proof.
  intro. unfold count_inc_slots.
  destruct (primitive_eqb (op1 isa) PInc);
  destruct (primitive_eqb (op2 isa) PInc);
  destruct (primitive_eqb (op3 isa) PInc);
  destruct (primitive_eqb (op4 isa) PInc); simpl; lia.
Qed.

Lemma count_dec_slots_bound : forall isa, (count_dec_slots isa <= 4)%nat.
Proof.
  intro. unfold count_dec_slots.
  destruct (primitive_eqb (op1 isa) PDec);
  destruct (primitive_eqb (op2 isa) PDec);
  destruct (primitive_eqb (op3 isa) PDec);
  destruct (primitive_eqb (op4 isa) PDec); simpl; lia.
Qed.

(** A single primitive is either INC, DEC, or neither — never both. *)
Lemma slot_inc_dec_exclusive : forall p,
  (if primitive_eqb p PInc then 1 else 0)
  + (if primitive_eqb p PDec then 1 else 0) <= 1.
Proof. destruct p; simpl; lia. Qed.

(** Four slots each contribute at most 1 to (INC + DEC) counts. *)
Lemma count_inc_dec_sum : forall isa,
  (count_inc_slots isa + count_dec_slots isa <= 4)%nat.
Proof.
  intro isa.
  pose proof (slot_inc_dec_exclusive (op1 isa)) as H1.
  pose proof (slot_inc_dec_exclusive (op2 isa)) as H2.
  pose proof (slot_inc_dec_exclusive (op3 isa)) as H3.
  pose proof (slot_inc_dec_exclusive (op4 isa)) as H4.
  unfold count_inc_slots, count_dec_slots.
  destruct (primitive_eqb (op1 isa) PInc);
  destruct (primitive_eqb (op1 isa) PDec);
  destruct (primitive_eqb (op2 isa) PInc);
  destruct (primitive_eqb (op2 isa) PDec);
  destruct (primitive_eqb (op3 isa) PInc);
  destruct (primitive_eqb (op3 isa) PDec);
  destruct (primitive_eqb (op4 isa) PInc);
  destruct (primitive_eqb (op4 isa) PDec);
  simpl in H1, H2, H3, H4 |- *; lia.
Qed.

(** Balance forces count_inc_slots ∈ {0, 1}. *)
Lemma case_A_inc_count : forall isa,
  case_A_isa isa -> (count_inc_slots isa <= 1)%nat.
Proof.
  intros isa [_ [_ [_ [_ Hbal]]]].
  pose proof (count_inc_dec_sum isa). lia.
Qed.

(** When count_inc_slots = 0, count_dec_slots = 1. *)
Lemma case_A_zero_inc : forall isa,
  case_A_isa isa -> count_inc_slots isa = 0%nat -> count_dec_slots isa = 1%nat.
Proof. intros isa [_ [_ [_ [_ Hbal]]]] Hinc. lia. Qed.

Lemma case_A_one_inc : forall isa,
  case_A_isa isa -> count_inc_slots isa = 1%nat -> count_dec_slots isa = 2%nat.
Proof. intros isa [_ [_ [_ [_ Hbal]]]] Hinc. lia. Qed.

(** If count_dec_slots ≥ 1 then find_dec_slot returns a slot in {1,2,3,4}. *)
Lemma find_dec_slot_valid : forall isa,
  (count_dec_slots isa >= 1)%nat ->
  (1 <= find_dec_slot isa <= 4)%nat /\
  primitive_at_slot isa (find_dec_slot isa) = PDec.
Proof.
  intros isa Hcnt. unfold find_dec_slot, count_dec_slots in *.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4;
  try (apply primitive_eqb_eq in E1);
  try (apply primitive_eqb_eq in E2);
  try (apply primitive_eqb_eq in E3);
  try (apply primitive_eqb_eq in E4);
  simpl; split; try lia; unfold primitive_at_slot; try rewrite E1;
  try rewrite E2; try rewrite E3; try rewrite E4; try reflexivity.
Qed.

Lemma find_inc_slot_valid : forall isa,
  (count_inc_slots isa >= 1)%nat ->
  (1 <= find_inc_slot isa <= 4)%nat /\
  primitive_at_slot isa (find_inc_slot isa) = PInc.
Proof.
  intros isa Hcnt. unfold find_inc_slot, count_inc_slots in *.
  destruct (primitive_eqb (op1 isa) PInc) eqn:E1;
  destruct (primitive_eqb (op2 isa) PInc) eqn:E2;
  destruct (primitive_eqb (op3 isa) PInc) eqn:E3;
  destruct (primitive_eqb (op4 isa) PInc) eqn:E4;
  try (apply primitive_eqb_eq in E1);
  try (apply primitive_eqb_eq in E2);
  try (apply primitive_eqb_eq in E3);
  try (apply primitive_eqb_eq in E4);
  simpl; split; try lia; unfold primitive_at_slot; try rewrite E1;
  try rewrite E2; try rewrite E3; try rewrite E4; try reflexivity.
Qed.

(** No slot in 1..4 maps to PInc when count is zero. *)
Lemma no_inc_in_slots_when_zero : forall isa,
  count_inc_slots isa = 0%nat ->
  forall o, (1 <= o <= 4)%nat -> primitive_at_slot isa o <> PInc.
Proof.
  intros isa Hinc0 o Ho.
  unfold count_inc_slots in Hinc0.
  destruct (primitive_eqb (op1 isa) PInc) eqn:E1;
  destruct (primitive_eqb (op2 isa) PInc) eqn:E2;
  destruct (primitive_eqb (op3 isa) PInc) eqn:E3;
  destruct (primitive_eqb (op4 isa) PInc) eqn:E4; simpl in Hinc0; try lia.
  apply primitive_eqb_neq in E1, E2, E3, E4.
  destruct o as [|[|[|[|[|?]]]]]; simpl; try lia; assumption.
Qed.

(** For the zero-INC case, the unique DEC slot is the only PDec. *)
Lemma unique_dec_slot : forall isa,
  count_dec_slots isa = 1%nat ->
  forall o, (1 <= o <= 4)%nat -> o <> find_dec_slot isa ->
    primitive_at_slot isa o <> PDec.
Proof.
  intros isa Hdec1 o Ho Hne.
  unfold count_dec_slots in Hdec1. unfold find_dec_slot in Hne.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4; simpl in Hdec1; try lia;
    apply primitive_eqb_neq in E1 || apply primitive_eqb_eq in E1;
    apply primitive_eqb_neq in E2 || apply primitive_eqb_eq in E2;
    apply primitive_eqb_neq in E3 || apply primitive_eqb_eq in E3;
    apply primitive_eqb_neq in E4 || apply primitive_eqb_eq in E4;
    destruct o as [|[|[|[|[|?]]]]]; simpl; try lia; try assumption;
    try (exfalso; apply Hne; reflexivity).
Qed.

(** Reduce [step_opcode] at variable slots to an application of the
    primitive at that slot. Slot 5 is excluded since it is the JNZ
    opcode (handled separately). *)
Lemma step_opcode_as_apply_prim : forall isa o s,
  (o < 5)%nat ->
  step_opcode isa o s = apply_prim (primitive_at_slot isa o) s.
Proof.
  intros isa o s Ho. destruct o as [|[|[|[|[|?]]]]]; simpl; try lia; reflexivity.
Qed.

(** JNZ commutes with sigma on bounded states, for any ISA (JNZ is
    opcode 5 and its step does not depend on the ISA's variable fields). *)
Lemma jnz_sigma_commute : forall isa s,
  bounded_state s ->
  step_opcode isa 5%nat (sigma s) = sigma (step_opcode isa 5%nat s).
Proof.
  intros isa s Hb. destruct s as [a b pcv]. destruct Hb as [HA HB]. simpl in *.
  unfold sigma; simpl.
  rewrite neg_byte_eqb_zero by exact HA.
  destruct (Z.eqb a 0) eqn:Haz.
  - apply Z.eqb_eq in Haz; subst a. simpl.
    rewrite neg_byte_zero. reflexivity.
  - reflexivity.
Qed.

(** Factored step-equivariance under F: if the primitive at slot F(o)
    is the sigma-conjugate of the primitive at slot o, then the step
    at slot F(o) on sigma(s) equals sigma applied to the step at slot o
    on s. This is the generic reduction from valid_F's step condition
    to [primitive_at_slot] correspondence. *)
Lemma step_equivariance_via_conj : forall isa F o s,
  (o < 5)%nat ->
  (F o < 5)%nat ->
  is_CA_prim (primitive_at_slot isa o) = true ->
  primitive_at_slot isa (F o) = sigma_conj (primitive_at_slot isa o) ->
  step_opcode isa (F o) (sigma s) = sigma (step_opcode isa o s).
Proof.
  intros isa F o s Ho HFo Hca Hconj.
  rewrite step_opcode_as_apply_prim by assumption.
  rewrite step_opcode_as_apply_prim by assumption.
  rewrite Hconj. symmetry. apply sigma_equivariance. assumption.
Qed.

(** sigma_conj is the identity on primitives that are neither INC nor DEC. *)
Lemma sigma_conj_non_inc_dec : forall p,
  p <> PInc -> p <> PDec -> sigma_conj p = p.
Proof.
  destruct p; intros Hnin Hnd; simpl; try reflexivity;
    [exfalso; apply Hnin; reflexivity | exfalso; apply Hnd; reflexivity].
Qed.

(** For the zero-extra-INC Case-A construction, the F constructed as
    [swap2 0 d] maps each primitive to its sigma-conjugate. *)
(** The conjugation property depends only on the INC/DEC-balance
    bookkeeping — not on whether the ISA is Case A or Case B.
    sigma_conj is the identity on any primitive other than PInc and
    PDec (including the Case-B-specific PXor, PAnd, POr), so the
    same proof serves both cases.

    Generic formulation, keyed on the two counts; the Case-A and
    Case-B instantiations follow as corollaries via their balance
    lemmas. *)
Lemma F_zero_inc_conjugation_gen : forall isa o,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  (o <= 4)%nat ->
  primitive_at_slot isa (construct_F isa o)
    = sigma_conj (primitive_at_slot isa o).
Proof.
  intros isa o Hinc0 Hdec1 Ho.
  assert (Hdecv : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdecv) as [Hdrange Hdeq].
  set (d := find_dec_slot isa) in *.
  rewrite construct_F_zero_inc_form by assumption. fold d.
  destruct (Nat.eq_dec o 0%nat) as [->|Ho0].
  - (* o = 0: swap2 0 d 0 = d; primitive at 0 is PInc, at d is PDec *)
    rewrite swap2_i. rewrite Hdeq. reflexivity.
  - destruct (Nat.eq_dec o d) as [->|Hod].
    + (* o = d: swap2 0 d d = 0; primitive at d is PDec, sigma_conj = PInc *)
      rewrite swap2_j by lia. simpl. rewrite Hdeq. reflexivity.
    + (* o in {1..4} \ {d} *)
      rewrite swap2_self by lia.
      assert (Hmid : (1 <= o <= 4)%nat) by lia.
      assert (Hnotinc : primitive_at_slot isa o <> PInc)
        by (apply no_inc_in_slots_when_zero; assumption).
      assert (Hnotdec : primitive_at_slot isa o <> PDec)
        by (apply unique_dec_slot; try assumption; lia).
      symmetry. apply sigma_conj_non_inc_dec; assumption.
Qed.

Lemma F_zero_inc_conjugation : forall isa o,
  case_A_isa isa ->
  count_inc_slots isa = 0%nat ->
  (o <= 4)%nat ->
  primitive_at_slot isa (construct_F isa o)
    = sigma_conj (primitive_at_slot isa o).
Proof.
  intros isa o HcA Hinc0 Ho.
  apply F_zero_inc_conjugation_gen; [assumption | | assumption].
  apply case_A_zero_inc; assumption.
Qed.

(** Construct_F in the zero-inc case lies in {0..5}. *)
Lemma construct_F_zero_inc_range : forall isa o,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  (o < 6)%nat -> (construct_F isa o < 6)%nat.
Proof.
  intros isa o Hinc0 Hdec1 Ho.
  assert (Hdecv : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdecv) as [Hdrange _].
  set (d := find_dec_slot isa) in *.
  rewrite construct_F_zero_inc_form by assumption. fold d.
  unfold swap2. destruct (Nat.eqb o 0); [lia|].
  destruct (Nat.eqb o d); [lia|]. exact Ho.
Qed.

(** Stronger range: construct_F maps {0..4} into {0..4} (since d ∈ {1..4}). *)
Lemma construct_F_zero_inc_range_tight : forall isa o,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  (o <= 4)%nat -> (construct_F isa o <= 4)%nat.
Proof.
  intros isa o Hinc0 Hdec1 Ho.
  assert (Hdecv : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdecv) as [Hdrange _].
  set (d := find_dec_slot isa) in *.
  rewrite construct_F_zero_inc_form by assumption. fold d.
  unfold swap2. destruct (Nat.eqb o 0); [lia|].
  destruct (Nat.eqb o d); [lia|]. exact Ho.
Qed.

(** Construct_F's zero-inc branch is an involution on {0..5}. *)
Lemma construct_F_zero_inc_invol : forall isa o,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  (o < 6)%nat -> construct_F isa (construct_F isa o) = o.
Proof.
  intros isa o Hinc0 Hdec1 Ho.
  assert (Hdecv : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdecv) as [Hdrange _].
  set (d := find_dec_slot isa) in *.
  rewrite !construct_F_zero_inc_form by assumption. fold d.
  apply swap2_invol. lia.
Qed.

(** Construct_F's zero-inc branch fixes JNZ (opcode 5). *)
Lemma construct_F_zero_inc_fixes_5 : forall isa,
  count_inc_slots isa = 0%nat ->
  count_dec_slots isa = 1%nat ->
  construct_F isa 5%nat = 5%nat.
Proof.
  intros isa Hinc0 Hdec1.
  assert (Hdecv : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdecv) as [Hdrange _].
  set (d := find_dec_slot isa) in *.
  rewrite construct_F_zero_inc_form by assumption. fold d.
  apply swap2_self; lia.
Qed.

(** For the one-INC case: find_other_dec_slot returns the OTHER DEC slot,
    which is distinct from [find_dec_slot] and within {1..4}. *)
Lemma find_other_dec_slot_valid_two : forall isa,
  count_dec_slots isa = 2%nat ->
  (1 <= find_other_dec_slot isa (find_dec_slot isa) <= 4)%nat /\
  primitive_at_slot isa (find_other_dec_slot isa (find_dec_slot isa)) = PDec /\
  find_other_dec_slot isa (find_dec_slot isa) <> find_dec_slot isa.
Proof.
  intros isa Hdec2.
  unfold count_dec_slots in Hdec2.
  unfold find_dec_slot, find_other_dec_slot.
  destruct (primitive_eqb (op1 isa) PDec) eqn:E1;
  destruct (primitive_eqb (op2 isa) PDec) eqn:E2;
  destruct (primitive_eqb (op3 isa) PDec) eqn:E3;
  destruct (primitive_eqb (op4 isa) PDec) eqn:E4;
  simpl in Hdec2; try lia;
    try (apply primitive_eqb_eq in E1);
    try (apply primitive_eqb_eq in E2);
    try (apply primitive_eqb_eq in E3);
    try (apply primitive_eqb_eq in E4);
    simpl; repeat split; try lia; unfold primitive_at_slot; try assumption.
Qed.

(** For the one-INC case: the INC slot exists and is in {1..4}. *)
Lemma find_inc_slot_valid_one : forall isa,
  count_inc_slots isa = 1%nat ->
  (1 <= find_inc_slot isa <= 4)%nat /\
  primitive_at_slot isa (find_inc_slot isa) = PInc.
Proof.
  intro isa. intro H. apply find_inc_slot_valid. lia.
Qed.

(** In the one-INC case, the INC slot differs from all DEC slots. *)
Lemma inc_ne_dec : forall isa s1 s2,
  (1 <= s1 <= 4)%nat -> (1 <= s2 <= 4)%nat ->
  primitive_at_slot isa s1 = PInc ->
  primitive_at_slot isa s2 = PDec ->
  s1 <> s2.
Proof.
  intros isa s1 s2 Hs1 Hs2 Hp1 Hp2 Heq. subst s1.
  rewrite Hp1 in Hp2. discriminate.
Qed.

(** Two specific-position lemmas counting INC contributions. *)
Lemma count_inc_slots_ge2_pair : forall isa o1 o2,
  (1 <= o1 <= 4)%nat -> (1 <= o2 <= 4)%nat -> o1 <> o2 ->
  primitive_at_slot isa o1 = PInc ->
  primitive_at_slot isa o2 = PInc ->
  (count_inc_slots isa >= 2)%nat.
Proof.
  intros isa o1 o2 Ho1 Ho2 Hne Hp1 Hp2. unfold count_inc_slots.
  destruct o1 as [|[|[|[|[|?]]]]]; try lia;
  destruct o2 as [|[|[|[|[|?]]]]]; try lia; simpl in Hp1, Hp2;
    try (exfalso; apply Hne; reflexivity);
    rewrite Hp1, Hp2; rewrite ! primitive_eqb_refl;
    repeat (destruct (primitive_eqb _ PInc); simpl); lia.
Qed.

Lemma count_dec_slots_ge3_triple : forall isa o1 o2 o3,
  (1 <= o1 <= 4)%nat -> (1 <= o2 <= 4)%nat -> (1 <= o3 <= 4)%nat ->
  o1 <> o2 -> o1 <> o3 -> o2 <> o3 ->
  primitive_at_slot isa o1 = PDec ->
  primitive_at_slot isa o2 = PDec ->
  primitive_at_slot isa o3 = PDec ->
  (count_dec_slots isa >= 3)%nat.
Proof.
  intros isa o1 o2 o3 Ho1 Ho2 Ho3 H12 H13 H23 Hp1 Hp2 Hp3.
  unfold count_dec_slots.
  destruct o1 as [|[|[|[|[|?]]]]]; try lia;
  destruct o2 as [|[|[|[|[|?]]]]]; try lia;
  destruct o3 as [|[|[|[|[|?]]]]]; try lia;
  simpl in Hp1, Hp2, Hp3;
    try (exfalso; apply H12; reflexivity);
    try (exfalso; apply H13; reflexivity);
    try (exfalso; apply H23; reflexivity);
    rewrite Hp1, Hp2, Hp3; rewrite ! primitive_eqb_refl;
    repeat (destruct (primitive_eqb _ PDec); simpl); lia.
Qed.

(** When [count_inc_slots isa = 1], at most one slot in {1..4} maps to PInc,
    and it is [find_inc_slot isa]. *)
Lemma not_inc_outside_found : forall isa o,
  count_inc_slots isa = 1%nat ->
  (1 <= o <= 4)%nat ->
  o <> find_inc_slot isa ->
  primitive_at_slot isa o <> PInc.
Proof.
  intros isa o Hinc1 Ho Hne Hop.
  assert (Hfv := find_inc_slot_valid_one isa Hinc1).
  destruct Hfv as [Hir Hip].
  pose proof (count_inc_slots_ge2_pair isa o (find_inc_slot isa) Ho Hir Hne Hop Hip).
  lia.
Qed.

(** When [count_dec_slots isa = 2], the only slots in {1..4} that map to PDec
    are [find_dec_slot isa] and [find_other_dec_slot isa (find_dec_slot isa)]. *)
Lemma not_dec_outside_both : forall isa o,
  count_dec_slots isa = 2%nat ->
  (1 <= o <= 4)%nat ->
  o <> find_dec_slot isa ->
  o <> find_other_dec_slot isa (find_dec_slot isa) ->
  primitive_at_slot isa o <> PDec.
Proof.
  intros isa o Hdec2 Ho Hne1 Hne2 Hop.
  pose proof (find_other_dec_slot_valid_two isa Hdec2) as [Hod2r [Hod2p Hod2ne]].
  assert (Hdge : (count_dec_slots isa >= 1)%nat) by lia.
  pose proof (find_dec_slot_valid isa Hdge) as [Hd1r Hd1p].
  pose proof (count_dec_slots_ge3_triple isa o (find_dec_slot isa)
                 (find_other_dec_slot isa (find_dec_slot isa))
                 Ho Hd1r Hod2r Hne1 Hne2 (not_eq_sym Hod2ne) Hop Hd1p Hod2p).
  lia.
Qed.

(** Main zero-inc [valid_F] proof. *)
Lemma construct_F_valid_zero_inc : forall isa,
  case_A_isa isa ->
  count_inc_slots isa = 0%nat ->
  valid_F isa (construct_F isa).
Proof.
  intros isa HcA Hinc0.
  assert (Hdec1 : count_dec_slots isa = 1%nat) by (apply case_A_zero_inc; assumption).
  split; [|split; [|split]].
  - intros o Ho. apply construct_F_zero_inc_range; assumption.
  - intros o Ho. apply construct_F_zero_inc_invol; assumption.
  - apply construct_F_zero_inc_fixes_5; assumption.
  - (* step equivariance *)
    intros o s Ho Hb.
    destruct (Nat.eq_dec o 5%nat) as [->|Ho5].
    + (* JNZ case *)
      rewrite construct_F_zero_inc_fixes_5 by assumption.
      apply jnz_sigma_commute; assumption.
    + (* o < 5 *)
      apply step_equivariance_via_conj.
      * lia.
      * assert (construct_F isa o <= 4)%nat.
        { apply construct_F_zero_inc_range_tight; [assumption | assumption | lia]. }
        lia.
      * apply case_A_primitive_at_slot; [assumption | lia].
      * apply F_zero_inc_conjugation; [assumption | assumption | lia].
Qed.

(* ------------------------------------------------------------------ *)
(* One-INC sub-case of Case A.                                         *)
(* ------------------------------------------------------------------ *)

(** Bundled package of facts about the one-inc construction's slot choices. *)
Lemma one_inc_slots_ok : forall isa,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  let d1 := find_dec_slot isa in
  let i1 := find_inc_slot isa in
  let d2 := find_other_dec_slot isa d1 in
  (1 <= d1 <= 4)%nat /\ primitive_at_slot isa d1 = PDec /\
  (1 <= i1 <= 4)%nat /\ primitive_at_slot isa i1 = PInc /\
  (1 <= d2 <= 4)%nat /\ primitive_at_slot isa d2 = PDec /\
  d1 <> d2 /\ i1 <> d1 /\ i1 <> d2.
Proof.
  intros isa Hinc1 Hdec2.
  assert (Hdec_ge : (count_dec_slots isa >= 1)%nat) by lia.
  destruct (find_dec_slot_valid isa Hdec_ge) as [Hd1r Hd1p].
  destruct (find_inc_slot_valid_one isa Hinc1) as [Hi1r Hi1p].
  destruct (find_other_dec_slot_valid_two isa Hdec2) as [Hd2r [Hd2p Hd2ne]].
  assert (Hid1 : find_inc_slot isa <> find_dec_slot isa)
    by (apply (inc_ne_dec isa (find_inc_slot isa) (find_dec_slot isa)); assumption).
  assert (Hid2 : find_inc_slot isa <> find_other_dec_slot isa (find_dec_slot isa))
    by (apply (inc_ne_dec isa (find_inc_slot isa)
                          (find_other_dec_slot isa (find_dec_slot isa)));
        assumption).
  assert (Hd1d2 : find_dec_slot isa <> find_other_dec_slot isa (find_dec_slot isa))
    by (intro Heq; apply Hd2ne; symmetry; exact Heq).
  split. exact Hd1r.
  split. exact Hd1p.
  split. exact Hi1r.
  split. exact Hi1p.
  split. exact Hd2r.
  split. exact Hd2p.
  split. exact Hd1d2.
  split. exact Hid1.
  exact Hid2.
Qed.

(** Construct_F at one-inc maps {0..4} to {0..4}. *)
Lemma construct_F_one_inc_range_tight : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  (o <= 4)%nat -> (construct_F isa o <= 4)%nat.
Proof.
  intros isa o Hinc1 Hdec2 Ho.
  pose proof (one_inc_slots_ok isa Hinc1 Hdec2) as P.
  destruct P as [Hd1r [_ [Hi1r [_ [Hd2r _]]]]].
  rewrite construct_F_one_inc_form by assumption. unfold swap2.
  repeat (match goal with |- context[Nat.eqb ?x ?y] => destruct (Nat.eqb x y) end); lia.
Qed.

Lemma construct_F_one_inc_range : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  (o < 6)%nat -> (construct_F isa o < 6)%nat.
Proof.
  intros isa o Hinc1 Hdec2 Ho.
  destruct (Nat.eq_dec o 5%nat) as [->|Ho5].
  - pose proof (one_inc_slots_ok isa Hinc1 Hdec2) as P.
    destruct P as [Hd1r [_ [Hi1r [_ [Hd2r _]]]]].
    rewrite construct_F_one_inc_form by assumption. unfold swap2.
    repeat (match goal with
            | |- context[Nat.eqb ?x ?y] => destruct (Nat.eqb x y) eqn:?
            end);
      repeat match goal with
             | H : Nat.eqb _ _ = true |- _ => apply Nat.eqb_eq in H
             end; lia.
  - assert (construct_F isa o <= 4)%nat
      by (apply construct_F_one_inc_range_tight; [assumption | assumption | lia]).
    lia.
Qed.

Lemma construct_F_one_inc_fixes_5 : forall isa,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  construct_F isa 5%nat = 5%nat.
Proof.
  intros isa Hinc1 Hdec2.
  pose proof (one_inc_slots_ok isa Hinc1 Hdec2) as P.
  destruct P as [Hd1r [_ [Hi1r [_ [Hd2r _]]]]].
  rewrite construct_F_one_inc_form by assumption.
  rewrite (swap2_self (find_inc_slot isa)
             (find_other_dec_slot isa (find_dec_slot isa)) 5) by lia.
  apply swap2_self; lia.
Qed.


Lemma construct_F_one_inc_invol : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  (o < 6)%nat -> construct_F isa (construct_F isa o) = o.
Proof.
  intros isa o Hinc1 Hdec2 Ho.
  pose proof (one_inc_slots_ok isa Hinc1 Hdec2) as P.
  destruct P as [Hd1r [_ [Hi1r [_ [Hd2r [_ [Hd1d2 [Hi1d1 Hi1d2]]]]]]]].
  rewrite !construct_F_one_inc_as_swap_compose by assumption.
  apply swap_compose_invol; lia.
Qed.

(** Primitive-level conjugation for one-inc.

    With [construct_F = swap_compose 0 d1 i1 d2], unfolding to nested
    [swap2] applications, each of the five cases reduces via [swap2_i],
    [swap2_j], and [swap2_self] under the slot-distinctness hypotheses. *)
Lemma F_one_inc_conjugation : forall isa o,
  count_inc_slots isa = 1%nat ->
  count_dec_slots isa = 2%nat ->
  (o <= 4)%nat ->
  primitive_at_slot isa (construct_F isa o)
    = sigma_conj (primitive_at_slot isa o).
Proof.
  intros isa o Hinc1 Hdec2 Ho.
  pose proof (one_inc_slots_ok isa Hinc1 Hdec2) as P.
  destruct P as [Hd1r [Hd1p [Hi1r [Hi1p [Hd2r [Hd2p [Hd1d2 [Hi1d1 Hi1d2]]]]]]]].
  rewrite construct_F_one_inc_form by assumption.
  destruct (Nat.eq_dec o 0%nat) as [->|Ho0].
  - (* o = 0: inner swap2 i1 d2 0 = 0, then swap2 0 d1 0 = d1 *)
    rewrite (swap2_self (find_inc_slot isa)
               (find_other_dec_slot isa (find_dec_slot isa)) 0%nat) by lia.
    rewrite swap2_i. simpl. rewrite Hd1p. reflexivity.
  - destruct (Nat.eq_dec o (find_dec_slot isa)) as [->|Hod1].
    + (* o = d1: inner swap2 i1 d2 d1 = d1, then swap2 0 d1 d1 = 0 *)
      rewrite (swap2_self (find_inc_slot isa)
                 (find_other_dec_slot isa (find_dec_slot isa))
                 (find_dec_slot isa)) by lia.
      rewrite swap2_j by lia. simpl. rewrite Hd1p. reflexivity.
    + destruct (Nat.eq_dec o (find_inc_slot isa)) as [->|Hoi1].
      * (* o = i1: inner swap2 i1 d2 i1 = d2, then swap2 0 d1 d2 = d2 *)
        rewrite swap2_i.
        rewrite (swap2_self 0 (find_dec_slot isa)
                   (find_other_dec_slot isa (find_dec_slot isa))) by lia.
        rewrite Hi1p, Hd2p. reflexivity.
      * destruct (Nat.eq_dec o (find_other_dec_slot isa (find_dec_slot isa)))
          as [->|Hod2].
        -- (* o = d2: inner swap2 i1 d2 d2 = i1, then swap2 0 d1 i1 = i1 *)
           rewrite swap2_j by lia.
           rewrite (swap2_self 0 (find_dec_slot isa) (find_inc_slot isa)) by lia.
           rewrite Hi1p, Hd2p. reflexivity.
        -- (* o in {1..4} \ {d1, i1, d2}: both swap2s are identity on o *)
           rewrite (swap2_self (find_inc_slot isa)
                      (find_other_dec_slot isa (find_dec_slot isa)) o) by lia.
           rewrite (swap2_self 0 (find_dec_slot isa) o) by lia.
           assert (Hmid : (1 <= o <= 4)%nat) by lia.
           assert (Hnotinc : primitive_at_slot isa o <> PInc)
             by (apply not_inc_outside_found; assumption).
           assert (Hnotdec : primitive_at_slot isa o <> PDec)
             by (apply not_dec_outside_both; assumption).
           symmetry. apply sigma_conj_non_inc_dec; assumption.
Qed.

(** Main one-inc [valid_F] proof. *)
Lemma construct_F_valid_one_inc : forall isa,
  case_A_isa isa ->
  count_inc_slots isa = 1%nat ->
  valid_F isa (construct_F isa).
Proof.
  intros isa HcA Hinc1.
  assert (Hdec2 : count_dec_slots isa = 2%nat) by (apply case_A_one_inc; assumption).
  split; [|split; [|split]].
  - intros o Ho. apply construct_F_one_inc_range; assumption.
  - intros o Ho. apply construct_F_one_inc_invol; assumption.
  - apply construct_F_one_inc_fixes_5; assumption.
  - intros o s Ho Hb.
    destruct (Nat.eq_dec o 5%nat) as [->|Ho5].
    + rewrite construct_F_one_inc_fixes_5 by assumption.
      apply jnz_sigma_commute; assumption.
    + apply step_equivariance_via_conj.
      * lia.
      * assert (construct_F isa o <= 4)%nat
          by (apply construct_F_one_inc_range_tight; [assumption | assumption | lia]).
        lia.
      * apply case_A_primitive_at_slot; [assumption | lia].
      * apply F_one_inc_conjugation; [assumption | assumption | lia].
Qed.

(** Unified [valid_F] for any Case-A ISA: dispatches on [count_inc_slots]. *)
Lemma construct_F_valid : forall isa,
  case_A_isa isa ->
  valid_F isa (construct_F isa).
Proof.
  intros isa HcA.
  pose proof (case_A_inc_count isa HcA) as Hbound.
  destruct (count_inc_slots isa) as [|[|?]] eqn:Hic.
  - apply construct_F_valid_zero_inc; assumption.
  - apply construct_F_valid_one_inc; assumption.
  - lia.
Qed.

(** Existence of a valid F for any Case-A ISA. *)
Theorem F_exists_case_A : forall isa,
  case_A_isa isa -> exists F, valid_F isa F.
Proof.
  intros isa HcA. exists (construct_F isa). apply construct_F_valid. assumption.
Qed.

(* ------------------------------------------------------------------ *)
(* Main theorem.                                                        *)
(* ------------------------------------------------------------------ *)

(* ================================================================== *)
(* Part III: Case B (invariant-subspace argument for B = 0).            *)
(* ================================================================== *)

(** In Case B we allow ISAs whose variable opcodes lie in a closed set
    C_B = { INC, DEC, ADD, XOR, NEG, SUB, AND, OR, SHL, NOP } that
    adds the bitwise primitives XOR, AND, OR to the Case-A core.
    Starting from init_b = 0, B stays 0 throughout execution, and
    XOR/AND/OR reduce to sigma-symmetric operations on A.

    Excluded from C_B:

    - SWP and MOV: the only primitives that write to register B, so
      their presence would let B become nonzero and break the B = 0
      invariant. Whether this subspace exists at all depends on them
      being absent.

    - SHR and CPL: even under b = 0, these fail to commute with sigma
      on A alone (SHR is not a group homomorphism with respect to
      negation; CPL negates and shifts by 1 in opposite directions).
      No ISA containing either can be sigma-symmetric under any
      initial state; the empirical tensor confirms this. *)

Definition case_B_isa (isa : ISA) : Prop :=
  is_CB_prim (op1 isa) = true /\
  is_CB_prim (op2 isa) = true /\
  is_CB_prim (op3 isa) = true /\
  is_CB_prim (op4 isa) = true /\
  (1 + count_inc_slots isa)%nat = count_dec_slots isa.

Lemma case_B_primitive_at_slot : forall isa o,
  case_B_isa isa -> (o <= 4)%nat -> is_CB_prim (primitive_at_slot isa o) = true.
Proof.
  intros isa o [H1 [H2 [H3 [H4 _]]]] Ho.
  destruct o as [|[|[|[|[|?]]]]]; simpl; try reflexivity; try assumption; lia.
Qed.

(** apply_prim preserves regB = 0 when the primitive is in C_B (no SWP/MOV). *)
Lemma apply_prim_preserves_B_zero : forall p s,
  is_CB_prim p = true -> regB s = 0 -> regB (apply_prim p s) = 0.
Proof.
  intros p s Hcb HB.
  destruct p; simpl in Hcb; try discriminate Hcb; simpl; exact HB.
Qed.

Lemma step_opcode_preserves_B_zero : forall isa o s,
  (o < 6)%nat ->
  (o = 0%nat \/ o = 5%nat \/
   (is_CB_prim (op1 isa) = true /\
    is_CB_prim (op2 isa) = true /\
    is_CB_prim (op3 isa) = true /\
    is_CB_prim (op4 isa) = true)) ->
  regB s = 0 -> regB (step_opcode isa o s) = 0.
Proof.
  intros isa o s Ho Hdisj HB.
  destruct o as [|[|[|[|[|[|?]]]]]]; try lia; simpl.
  - (* o = 0, PInc *) exact HB.
  - destruct Hdisj as [H|[H|[H1 _]]]; try discriminate H.
    apply apply_prim_preserves_B_zero; assumption.
  - destruct Hdisj as [H|[H|[_ [H2 _]]]]; try discriminate H.
    apply apply_prim_preserves_B_zero; assumption.
  - destruct Hdisj as [H|[H|[_ [_ [H3 _]]]]]; try discriminate H.
    apply apply_prim_preserves_B_zero; assumption.
  - destruct Hdisj as [H|[H|[_ [_ [_ H4]]]]]; try discriminate H.
    apply apply_prim_preserves_B_zero; assumption.
  - (* o = 5, JNZ: regB unchanged in both branches *)
    destruct (Z.eqb (regA s) 0); exact HB.
Qed.

(** 8-bit bitwise bounds: if both operands are in [0, 256), so are
    the bitwise XOR, AND, OR, SHR, and the complement. *)

Lemma Z_lxor_0_r : forall a, Z.lxor a 0 = a.
Proof. intro a. apply Z.lxor_0_r. Qed.

Lemma Z_land_0_r : forall a, Z.land a 0 = 0.
Proof. intro a. apply Z.land_0_r. Qed.

Lemma Z_lor_0_r : forall a, Z.lor a 0 = a.
Proof. intro a. apply Z.lor_0_r. Qed.

(** The central Case-B equivariance: for primitives in C_B, on states
    with regB = 0, sigma commutes with apply_prim. *)
Lemma sigma_equivariance_CB_B0 : forall p s,
  is_CB_prim p = true ->
  bounded_state s ->
  regB s = 0 ->
  sigma (apply_prim p s) = apply_prim (sigma_conj p) (sigma s).
Proof.
  intros p [a b pcv] Hcb [HA HB0] HBz. simpl in *. subst b.
  destruct p; simpl in Hcb; try discriminate Hcb;
    simpl; unfold sigma, neg_byte; simpl;
    try reflexivity.
  - (* PInc → PDec *) f_equal. apply mod_opp_succ.
  - (* PDec → PInc *) f_equal. apply mod_opp_pred.
  - (* PAdd: a + 0 = a on both sides *)
    f_equal. rewrite Z.add_0_r, Z.add_0_r.
    rewrite Zmod_mod. apply opp_mod_distr.
  - (* PSub: a - 0 = a *)
    f_equal. rewrite Z.sub_0_r, Z.sub_0_r.
    rewrite Zmod_mod. apply opp_mod_distr.
  - (* PShl *) f_equal. apply mod_opp_mul2.
  - (* PXor: (a xor 0) mod M = a mod M on both sides *)
    f_equal. rewrite Z_lxor_0_r, Z_lxor_0_r.
    rewrite Zmod_mod. apply opp_mod_distr.
  - (* PAnd: (a and 0) mod M = 0 on both sides; sigma of 0 = 0 *)
    f_equal. rewrite Z_land_0_r, Z_land_0_r.
    rewrite Zmod_0_l. rewrite Zmod_0_l. apply neg_byte_zero.
  - (* POr: (a or 0) mod M = a mod M *)
    f_equal. rewrite Z_lor_0_r, Z_lor_0_r.
    rewrite Zmod_mod. apply opp_mod_distr.
Qed.

(** Factored step-equivariance under F for Case B. *)
Lemma step_equivariance_CB_via_conj : forall isa F o s,
  (o < 5)%nat ->
  (F o < 5)%nat ->
  is_CB_prim (primitive_at_slot isa o) = true ->
  bounded_state s -> regB s = 0 ->
  primitive_at_slot isa (F o) = sigma_conj (primitive_at_slot isa o) ->
  step_opcode isa (F o) (sigma s) = sigma (step_opcode isa o s).
Proof.
  intros isa F o s Ho HFo Hcb Hb HBz Hconj.
  rewrite step_opcode_as_apply_prim by assumption.
  rewrite step_opcode_as_apply_prim by assumption.
  rewrite Hconj. symmetry.
  apply sigma_equivariance_CB_B0; assumption.
Qed.

(** When [case_B_isa] holds, construct_F applied per the zero-inc or
    one-inc branch gives a valid [F], provided we maintain the B=0
    invariant. Since the state-level condition of [valid_F] requires
    bounded states without B=0, we define a restricted validity for
    Case B. *)

Definition valid_F_CB (isa : ISA) (F : OpcodeInvol) : Prop :=
  (forall o, (o < 6)%nat -> (F o < 6)%nat) /\
  (forall o, (o < 6)%nat -> F (F o) = o) /\
  (F 5%nat = 5%nat) /\
  (forall o s, (o < 6)%nat -> bounded_state s -> regB s = 0 ->
    step_opcode isa (F o) (sigma s) = sigma (step_opcode isa o s)).

(** [F_zero_inc_conjugation] and [F_one_inc_conjugation] depend on
    case_A_isa to establish that slots not occupied by INC or DEC carry
    primitives with sigma_conj = identity. The analogous Case-B
    assumption must also rule out PShr and PCpl (which can't give
    sigma-symmetric halting even under B=0). The closed set C_B
    achieves exactly that. *)

(** For case_B_isa + zero-inc: F = swap2 0 d. Conjugation property. *)
Lemma F_zero_inc_conjugation_CB : forall isa o,
  case_B_isa isa ->
  count_inc_slots isa = 0%nat ->
  (o <= 4)%nat ->
  primitive_at_slot isa (construct_F isa o)
    = sigma_conj (primitive_at_slot isa o).
Proof.
  intros isa o [_ [_ [_ [_ Hbal]]]] Hinc0 Ho.
  apply F_zero_inc_conjugation_gen; [assumption | | assumption]. lia.
Qed.

(** For case_B_isa + one-inc: the general [F_one_inc_conjugation] works
    directly, since its proof already depends only on the INC/DEC
    counts (not on whether the ISA is in C_A or C_B). *)
Lemma F_one_inc_conjugation_CB : forall isa o,
  case_B_isa isa ->
  count_inc_slots isa = 1%nat ->
  (o <= 4)%nat ->
  primitive_at_slot isa (construct_F isa o)
    = sigma_conj (primitive_at_slot isa o).
Proof.
  intros isa o [_ [_ [_ [_ Hbal]]]] Hinc1 Ho.
  apply F_one_inc_conjugation; [assumption | lia | assumption].
Qed.

(** Case-B [valid_F_CB] for zero-inc construction. *)
Lemma construct_F_valid_CB_zero_inc : forall isa,
  case_B_isa isa ->
  count_inc_slots isa = 0%nat ->
  valid_F_CB isa (construct_F isa).
Proof.
  intros isa HcB Hinc0.
  assert (Hdec1 : count_dec_slots isa = 1%nat)
    by (destruct HcB as [_ [_ [_ [_ H]]]]; lia).
  split; [|split; [|split]].
  - intros o Ho. apply construct_F_zero_inc_range; assumption.
  - intros o Ho. apply construct_F_zero_inc_invol; assumption.
  - apply construct_F_zero_inc_fixes_5; assumption.
  - intros o s Ho Hb HBz.
    destruct (Nat.eq_dec o 5%nat) as [->|Ho5].
    + rewrite construct_F_zero_inc_fixes_5 by assumption.
      apply jnz_sigma_commute; assumption.
    + apply step_equivariance_CB_via_conj; try assumption.
      * lia.
      * assert (construct_F isa o <= 4)%nat
          by (apply construct_F_zero_inc_range_tight; [assumption | assumption | lia]).
        lia.
      * apply case_B_primitive_at_slot; [assumption | lia].
      * apply F_zero_inc_conjugation_CB; [assumption | assumption | lia].
Qed.

(** Case-B [valid_F_CB] for one-inc construction. *)
Lemma construct_F_valid_CB_one_inc : forall isa,
  case_B_isa isa ->
  count_inc_slots isa = 1%nat ->
  valid_F_CB isa (construct_F isa).
Proof.
  intros isa HcB Hinc1.
  assert (Hdec2 : count_dec_slots isa = 2%nat)
    by (destruct HcB as [_ [_ [_ [_ H]]]]; lia).
  split; [|split; [|split]].
  - intros o Ho. apply construct_F_one_inc_range; assumption.
  - intros o Ho. apply construct_F_one_inc_invol; assumption.
  - apply construct_F_one_inc_fixes_5; assumption.
  - intros o s Ho Hb HBz.
    destruct (Nat.eq_dec o 5%nat) as [->|Ho5].
    + rewrite construct_F_one_inc_fixes_5 by assumption.
      apply jnz_sigma_commute; assumption.
    + apply step_equivariance_CB_via_conj; try assumption.
      * lia.
      * assert (construct_F isa o <= 4)%nat
          by (apply construct_F_one_inc_range_tight; [assumption | assumption | lia]).
        lia.
      * apply case_B_primitive_at_slot; [assumption | lia].
      * apply F_one_inc_conjugation_CB; [assumption | assumption | lia].
Qed.

(** Balance in case_B_isa also forces count_inc_slots ∈ {0, 1}. *)
Lemma case_B_inc_count : forall isa,
  case_B_isa isa -> (count_inc_slots isa <= 1)%nat.
Proof.
  intros isa [_ [_ [_ [_ Hbal]]]].
  pose proof (count_inc_dec_sum isa). lia.
Qed.

Lemma construct_F_valid_CB : forall isa,
  case_B_isa isa -> valid_F_CB isa (construct_F isa).
Proof.
  intros isa HcB.
  pose proof (case_B_inc_count isa HcB) as Hbound.
  destruct (count_inc_slots isa) as [|[|?]] eqn:Hic.
  - apply construct_F_valid_CB_zero_inc; assumption.
  - apply construct_F_valid_CB_one_inc; assumption.
  - lia.
Qed.

Theorem F_exists_case_B : forall isa,
  case_B_isa isa -> exists F, valid_F_CB isa F.
Proof.
  intros isa HcB. exists (construct_F isa). apply construct_F_valid_CB. assumption.
Qed.

(** The Case-B analogue of [execute_equivariance], maintaining the B=0
    invariant through the execution. *)
Lemma execute_equivariance_CB :
  forall (n : nat) (isa : ISA) (F : OpcodeInvol) (p : Program) (s : State),
    valid_F_CB isa F ->
    case_B_isa isa ->
    wf_prog p ->
    bounded_state s ->
    regB s = 0 ->
    execute isa p s n = execute isa (F_prog F p) (sigma s) n.
Proof.
  induction n as [|n IH]; intros isa F p s HvF HcB Hwf Hb HBz; [reflexivity|].
  simpl.
  destruct (step isa p s) as [s'|] eqn:Hstep.
  - assert (step isa (F_prog F p) (sigma s) = Some (sigma s')) as Hstep'.
    { unfold step in *.
      rewrite pc_preserved_by_sigma.
      destruct (Nat.leb NLen (pc s)) eqn:Hdone; [discriminate|].
      destruct Hwf as [Hlen Hin].
      apply Nat.leb_gt in Hdone.
      assert ((pc s < length p)%nat) as Hpclt.
      { rewrite Hlen. unfold NLen in Hdone. unfold NLen. exact Hdone. }
      rewrite (fetch_F_prog F p (pc s) Hpclt).
      assert ((fetch p (pc s) < 6)%nat) as Hfo.
      { apply Hin. unfold fetch. apply nth_In. exact Hpclt. }
      destruct HvF as [_ [_ [_ Hconj]]].
      specialize (Hconj (fetch p (pc s)) s Hfo Hb HBz).
      rewrite Hconj. inversion Hstep. reflexivity. }
    rewrite Hstep'.
    apply IH; [exact HvF | exact HcB | exact Hwf | |].
    + unfold step in Hstep.
      destruct (Nat.leb NLen (pc s)) eqn:Hdone; [discriminate|].
      inversion Hstep. subst. apply step_opcode_bounded. exact Hb.
    + unfold step in Hstep.
      destruct (Nat.leb NLen (pc s)) eqn:Hdone; [discriminate|].
      inversion Hstep. subst.
      destruct Hwf as [Hlen Hin].
      apply Nat.leb_gt in Hdone.
      assert ((pc s < length p)%nat) as Hpclt
        by (rewrite Hlen; unfold NLen in *; exact Hdone).
      assert ((fetch p (pc s) < 6)%nat) as Hfo.
      { apply Hin. unfold fetch. apply nth_In. exact Hpclt. }
      apply step_opcode_preserves_B_zero; try assumption.
      destruct HcB as [H1 [H2 [H3 [H4 _]]]].
      right. right. repeat split; assumption.
  - assert (step isa (F_prog F p) (sigma s) = None) as Hstep'.
    { unfold step in *.
      rewrite pc_preserved_by_sigma.
      destruct (Nat.leb NLen (pc s)); [reflexivity|discriminate]. }
    rewrite Hstep'. reflexivity.
Qed.

(** Main theorem (Case A): if an ISA admits a valid sigma-conjugating
    opcode involution F (equivalently, is sigma-closed and INC/DEC
    balanced), then for every initial accumulator value a, the set of
    length-8 halting programs from init_state(a) is in bijection with
    the set from init_state(-a), and therefore the halting counts and
    the halting fraction Omega are equal. *)

Theorem sigma_symmetric_halting :
  forall (isa : ISA) (F : OpcodeInvol) (p : Program) (a : Z),
    valid_F isa F ->
    wf_prog p ->
    0 <= a < Modulus ->
    halts isa p (init_state a) = halts isa (F_prog F p) (init_state (neg_byte a)).
Proof. exact halts_equivariance. Qed.

(** Main theorem (Case B): for any Case-B ISA starting at init_b = 0,
    the halting predicate is sigma-symmetric in init_a via the constructed F. *)
Theorem sigma_symmetric_halting_CB :
  forall (isa : ISA) (F : OpcodeInvol) (p : Program) (a : Z),
    case_B_isa isa ->
    valid_F_CB isa F ->
    wf_prog p ->
    0 <= a < Modulus ->
    halts isa p (init_state a) = halts isa (F_prog F p) (init_state (neg_byte a)).
Proof.
  intros isa F p a HcB HvF Hwf Ha.
  unfold halts.
  assert (Hamod : a mod Modulus = a) by (apply Zmod_small; exact Ha).
  assert (Hnbmod : (neg_byte a) mod Modulus = neg_byte a).
  { apply Zmod_small. apply neg_byte_range. }
  assert (Hinit_eq : init_state (neg_byte a) = sigma (init_state a)).
  { unfold init_state, sigma. simpl.
    rewrite Hnbmod, Hamod, neg_byte_zero. reflexivity. }
  rewrite Hinit_eq.
  apply execute_equivariance_CB; [exact HvF | exact HcB | exact Hwf | |].
  - unfold init_state, bounded_state. simpl.
    split; [apply Z.mod_pos_bound; apply Modulus_pos | unfold Modulus; lia].
  - unfold init_state. simpl. reflexivity.
Qed.

(** Unified user-facing corollary: any Case-A or Case-B ISA admits a
    pairing of programs witnessing sigma-symmetry of the halting
    predicate from (a, 0, 0). *)
Theorem sigma_symmetric_halting_case_A_or_B :
  forall (isa : ISA) (p : Program) (a : Z),
    (case_A_isa isa \/ case_B_isa isa) ->
    wf_prog p ->
    0 <= a < Modulus ->
    exists q : Program,
      halts isa p (init_state a) = halts isa q (init_state (neg_byte a)).
Proof.
  intros isa p a [HcA|HcB] Hwf Ha.
  - exists (F_prog (construct_F isa) p).
    apply sigma_symmetric_halting; try assumption.
    apply construct_F_valid; assumption.
  - exists (F_prog (construct_F isa) p).
    apply sigma_symmetric_halting_CB; try assumption.
    apply construct_F_valid_CB; assumption.
Qed.

(* ================================================================== *)
(* Part IV: Halting-count equality via program-level bijection.         *)
(* ================================================================== *)

(** The set of length-[n] programs over the opcode alphabet {0..5}. *)
Fixpoint enum_progs (n : nat) : list Program :=
  match n with
  | O => [[]]
  | S n' =>
      flat_map (fun o => map (cons o) (enum_progs n'))
               [0%nat; 1%nat; 2%nat; 3%nat; 4%nat; 5%nat]
  end.

Lemma enum_progs_length_prog : forall n p,
  In p (enum_progs n) -> length p = n.
Proof.
  induction n as [|n IH]; intros p Hin.
  - destruct Hin as [<-|[]]. reflexivity.
  - change (enum_progs (S n)) with
      (flat_map (fun o => map (cons o) (enum_progs n))
                [0%nat; 1%nat; 2%nat; 3%nat; 4%nat; 5%nat]) in Hin.
    apply in_flat_map in Hin.
    destruct Hin as [o [_ Hin']].
    apply in_map_iff in Hin'.
    destruct Hin' as [tail [<- Htail]]. simpl. f_equal. apply IH. exact Htail.
Qed.

Lemma enum_progs_in_range : forall n p o,
  In p (enum_progs n) -> In o p -> (o < 6)%nat.
Proof.
  induction n as [|n IH]; intros p o Hp Ho.
  - destruct Hp as [<-|[]]. inversion Ho.
  - change (enum_progs (S n)) with
      (flat_map (fun x => map (cons x) (enum_progs n))
                [0%nat; 1%nat; 2%nat; 3%nat; 4%nat; 5%nat]) in Hp.
    apply in_flat_map in Hp.
    destruct Hp as [x [Hinx Hp]].
    apply in_map_iff in Hp.
    destruct Hp as [tail [<- Htail]].
    destruct Ho as [->|Ho].
    + simpl in Hinx. lia.
    + apply (IH _ _ Htail Ho).
Qed.

Lemma enum_progs_wf : forall p,
  In p (enum_progs NLen) -> wf_prog p.
Proof.
  intros p Hin. split.
  - apply enum_progs_length_prog. exact Hin.
  - intros o Ho. eapply enum_progs_in_range; eassumption.
Qed.

Lemma enum_progs_cons : forall n o p,
  (o < 6)%nat ->
  In p (enum_progs n) ->
  In (o :: p) (enum_progs (S n)).
Proof.
  intros n o p Ho Hp.
  change (enum_progs (S n)) with
    (flat_map (fun x => map (cons x) (enum_progs n))
              [0%nat; 1%nat; 2%nat; 3%nat; 4%nat; 5%nat]).
  apply in_flat_map. exists o. split.
  - destruct o as [|[|[|[|[|[|?]]]]]]; simpl; try lia;
      (left; reflexivity) ||
      (right; left; reflexivity) ||
      (right; right; left; reflexivity) ||
      (right; right; right; left; reflexivity) ||
      (right; right; right; right; left; reflexivity) ||
      (right; right; right; right; right; left; reflexivity).
  - apply in_map_iff. exists p. split; [reflexivity | exact Hp].
Qed.

Lemma enum_progs_complete : forall n p,
  length p = n -> (forall o, In o p -> (o < 6)%nat) -> In p (enum_progs n).
Proof.
  induction n as [|n IH]; intros p Hlen Hop.
  - destruct p; simpl in Hlen; [|discriminate]. simpl. left. reflexivity.
  - destruct p as [|o p']; simpl in Hlen; [discriminate|].
    assert (Hlen' : length p' = n) by lia.
    apply enum_progs_cons.
    + apply Hop. left. reflexivity.
    + apply IH; [exact Hlen'|]. intros o0 Ho0. apply Hop. right. exact Ho0.
Qed.

(** NoDup-preservation under injective-on-list mapping (local injectivity). *)
Lemma NoDup_map_inj_on : forall (A B : Type) (f : A -> B) (l : list A),
  NoDup l ->
  (forall x y, In x l -> In y l -> f x = f y -> x = y) ->
  NoDup (map f l).
Proof.
  intros A B f l Hnd. induction Hnd as [|x l' Hxnotin Hnd IH]; intros Hinj; simpl.
  - apply NoDup_nil.
  - apply NoDup_cons.
    + intro Hfx. rewrite in_map_iff in Hfx.
      destruct Hfx as [y [Hfy Hy]].
      assert (x = y).
      { apply Hinj; [left; reflexivity | right; exact Hy | symmetry; exact Hfy]. }
      subst y. contradiction.
    + apply IH. intros a b Ha Hb Heq.
      apply Hinj; [right; exact Ha | right; exact Hb | exact Heq].
Qed.

(** A function that maps a NoDup list into itself and is an involution on it
    induces a permutation of the list. *)
Lemma nodup_invol_Permutation :
  forall {A : Type} (f : A -> A) (l : list A),
    NoDup l ->
    (forall x, In x l -> In (f x) l) ->
    (forall x, In x l -> f (f x) = x) ->
    Permutation (map f l) l.
Proof.
  intros A f l Hnd Hcl Hinv.
  apply NoDup_Permutation.
  - apply NoDup_map_inj_on; [exact Hnd|].
    intros x y Hx Hy Heq.
    (* Use: f (f x) = x, f (f y) = y, and f x = f y *)
    rewrite <- (Hinv x Hx). rewrite <- (Hinv y Hy). f_equal. exact Heq.
  - exact Hnd.
  - intros x. split.
    + intros Hx. rewrite in_map_iff in Hx. destruct Hx as [y [<- Hy]].
      apply Hcl. exact Hy.
    + intros Hx. rewrite in_map_iff. exists (f x). split.
      * apply Hinv. exact Hx.
      * apply Hcl. exact Hx.
Qed.

(** For [NoDup (enum_progs n)], we use [NoDup_map_inj_on] combined with the
    fact that [cons o] is injective. *)

Lemma NoDup_flat_map_cons :
  forall (l : list nat) (ll : list Program),
    NoDup l -> NoDup ll ->
    NoDup (flat_map (fun o => map (cons o) ll) l).
Proof.
  induction l as [|o l' IH]; intros ll Hl Hll; simpl; [apply NoDup_nil|].
  inversion Hl as [|? ? Honotin Hl']; subst.
  apply NoDup_app.
  - apply NoDup_map_inj_on; [exact Hll|].
    intros t1 t2 _ _ Heq. injection Heq as Heq'. exact Heq'.
  - apply IH; assumption.
  - intros p Hin1 Hin2.
    rewrite in_map_iff in Hin1. destruct Hin1 as [t1 [<- _]].
    rewrite in_flat_map in Hin2. destruct Hin2 as [o' [Ho' Hmap]].
    rewrite in_map_iff in Hmap. destruct Hmap as [t2 [Heq _]].
    injection Heq as Heqo _. subst o'. contradiction.
Qed.

Lemma enum_progs_nodup : forall n, NoDup (enum_progs n).
Proof.
  induction n as [|n IH].
  - simpl. apply NoDup_cons; [intro H; inversion H | apply NoDup_nil].
  - change (enum_progs (S n)) with
      (flat_map (fun o => map (cons o) (enum_progs n))
                [0%nat; 1%nat; 2%nat; 3%nat; 4%nat; 5%nat]).
    apply NoDup_flat_map_cons; [|exact IH].
    repeat (apply NoDup_cons; [simpl; intros H;
      repeat destruct H as [|H]; try discriminate; try contradiction |]).
    apply NoDup_nil.
Qed.

Lemma F_prog_in_enum : forall F n p,
  (forall o, (o < 6)%nat -> (F o < 6)%nat) ->
  In p (enum_progs n) -> In (F_prog F p) (enum_progs n).
Proof.
  intros F n p HFrange Hp.
  apply enum_progs_complete.
  - unfold F_prog. rewrite length_map. apply enum_progs_length_prog. exact Hp.
  - intros o Ho. unfold F_prog in Ho. rewrite in_map_iff in Ho.
    destruct Ho as [o' [<- Ho']].
    apply HFrange. eapply enum_progs_in_range; eassumption.
Qed.

Lemma F_prog_invol_enum : forall F p,
  (forall o, (o < 6)%nat -> F (F o) = o) ->
  (forall o, In o p -> (o < 6)%nat) ->
  F_prog F (F_prog F p) = p.
Proof.
  intros F p Hinv Hp.
  unfold F_prog. rewrite map_map.
  induction p as [|o rest IH]; simpl; [reflexivity|].
  f_equal.
  - apply Hinv. apply Hp. left; reflexivity.
  - apply IH. intros o' Ho'. apply Hp. right; exact Ho'.
Qed.

Lemma Permutation_filter_loc :
  forall {A : Type} (P : A -> bool) (l l' : list A),
    Permutation l l' -> Permutation (filter P l) (filter P l').
Proof.
  intros A P l l' Hperm.
  induction Hperm; simpl.
  - apply perm_nil.
  - destruct (P x); [apply perm_skip | ]; exact IHHperm.
  - destruct (P x) eqn:Ex; destruct (P y) eqn:Ey; simpl;
      try apply perm_swap; try apply Permutation_refl.
  - apply (perm_trans IHHperm1 IHHperm2).
Qed.

Lemma filter_map_length :
  forall {A B : Type} (f : A -> B) (P : B -> bool) (l : list A),
    length (filter P (map f l)) = length (filter (fun x => P (f x)) l).
Proof.
  induction l as [|x l' IH]; simpl; [reflexivity|].
  destruct (P (f x)); simpl; [f_equal|]; exact IH.
Qed.

(** The halting count: number of length-NLen programs that halt from [s]. *)
Definition halting_count (isa : ISA) (s : State) : nat :=
  length (filter (fun p => halts isa p s) (enum_progs NLen)).

(** Counting theorem: halting counts from (a, 0) and (-a, 0) are equal. *)
Theorem halting_count_sigma_symmetric :
  forall (isa : ISA) (a : Z),
    (case_A_isa isa \/ case_B_isa isa) ->
    0 <= a < Modulus ->
    halting_count isa (init_state a)
    = halting_count isa (init_state (neg_byte a)).
Proof.
  intros isa a HAB Ha.
  unfold halting_count.
  set (F := construct_F isa).
  assert (HFrange : forall o, (o < 6)%nat -> (F o < 6)%nat).
  { destruct HAB as [HcA|HcB].
    - exact (proj1 (construct_F_valid isa HcA)).
    - exact (proj1 (construct_F_valid_CB isa HcB)). }
  assert (HFinv : forall o, (o < 6)%nat -> F (F o) = o).
  { destruct HAB as [HcA|HcB].
    - exact (proj1 (proj2 (construct_F_valid isa HcA))).
    - exact (proj1 (proj2 (construct_F_valid_CB isa HcB))). }
  assert (Hpairing : forall p, In p (enum_progs NLen) ->
    halts isa p (init_state a) = halts isa (F_prog F p) (init_state (neg_byte a))).
  { intros p Hp. destruct HAB as [HcA|HcB].
    - apply sigma_symmetric_halting.
      + apply construct_F_valid. exact HcA.
      + apply enum_progs_wf. exact Hp.
      + exact Ha.
    - apply sigma_symmetric_halting_CB; try assumption.
      + apply construct_F_valid_CB. exact HcB.
      + apply enum_progs_wf. exact Hp. }
  assert (Hperm : Permutation (map (F_prog F) (enum_progs NLen)) (enum_progs NLen)).
  { apply nodup_invol_Permutation.
    - apply enum_progs_nodup.
    - intros p Hp. apply F_prog_in_enum; assumption.
    - intros p Hp. apply F_prog_invol_enum.
      + exact HFinv.
      + intros o Ho. eapply enum_progs_in_range; eassumption. }
  (* |filter P l| = |filter P (map F l)| (bijection), and
     |filter P (map F l)| = |filter (P ∘ F) l| (filter-of-map). *)
  assert (step1 :
    length (filter (fun p => halts isa p (init_state a)) (enum_progs NLen))
    = length (filter (fun p => halts isa p (init_state a))
                     (map (F_prog F) (enum_progs NLen)))).
  { apply Permutation_length. apply Permutation_sym.
    apply Permutation_filter_loc. exact Hperm. }
  rewrite step1. rewrite filter_map_length.
  f_equal. apply filter_ext_in.
  intros p Hp.
  assert (Hfp : In (F_prog F p) (enum_progs NLen))
    by (apply F_prog_in_enum; [exact HFrange | exact Hp]).
  rewrite (Hpairing (F_prog F p) Hfp).
  f_equal.
  apply F_prog_invol_enum; [exact HFinv|].
  intros o Ho. apply (enum_progs_in_range NLen p o Hp Ho).
Qed.

(* ================================================================== *)
(* Part V: Halting-fraction (Omega) equality at the rational level.     *)
(* ================================================================== *)

(** The halting fraction [Omega] is the count of halting programs
    divided by the total program space size (6^NLen). *)
Definition Omega (isa : ISA) (s : State) : Q :=
  Z.of_nat (halting_count isa s) # Pos.of_nat (6 ^ NLen).

(** Halting fraction invariance: Omega(isa, a) = Omega(isa, -a) for
    any Case-A or Case-B ISA. The denominator is fixed at 6^8, so
    equality of the halting fractions is equivalent to equality of
    the halting counts proven by [halting_count_sigma_symmetric]. *)
Theorem halting_fraction_sigma_symmetric :
  forall (isa : ISA) (a : Z),
    (case_A_isa isa \/ case_B_isa isa) ->
    0 <= a < Modulus ->
    Omega isa (init_state a) == Omega isa (init_state (neg_byte a)).
Proof.
  intros isa a HAB Ha. unfold Omega.
  rewrite (halting_count_sigma_symmetric isa a HAB Ha).
  reflexivity.
Qed.
