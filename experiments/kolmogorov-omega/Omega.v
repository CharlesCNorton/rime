(* Omega.v — Finite halting fraction: definitions and theorem statements.

   STATUS: UNTESTED. This file has not been compiled with Rocq/Coq.
   It is a specification of the definitions, lemmas, and theorems
   from the paper, written in Gallina for future formal verification.
   The proofs are stubbed with Admitted.

   Target: Rocq 9.0 (rocq compile Omega.v)
   Dependencies: none beyond the standard library.
*)

Require Import Arith.
Require Import List.
Require Import Lia.
Require Import Nat.
Import ListNotations.

(* ================================================================ *)
(* Machine model                                                     *)
(* ================================================================ *)

(* Register width. All arithmetic is mod 2^W. *)
Definition W := 8.
Definition modulus := 2 ^ W.

(* State: accumulator A, auxiliary B, program counter PC. *)
Record state := mkState {
  reg_a : nat;
  reg_b : nat;
  pc : nat;
}.

Definition init_state : state := mkState 0 0 0.

(* An opcode is a number 0..5. *)
Definition opcode := nat.

(* A program is a list of opcodes of length N. *)
Definition program := list opcode.

(* The number of opcodes in the alphabet. *)
Definition sigma_size := 6.

(* Program length. *)
Definition prog_len := 8.

(* Maximum execution steps before timeout. *)
Definition t_max := 256.

(* The JNZ opcode number. *)
Definition jnz_opcode := 5.

(* ================================================================ *)
(* Operation primitives                                              *)
(* ================================================================ *)

(* An operation transforms (A, B) -> (A', B'). *)
Definition operation := nat -> nat -> (nat * nat).

Definition op_inc (a b : nat) : nat * nat := ((a + 1) mod modulus, b).
Definition op_dec (a b : nat) : nat * nat := ((a + modulus - 1) mod modulus, b).
Definition op_swp (a b : nat) : nat * nat := (b, a).
Definition op_add (a b : nat) : nat * nat := ((a + b) mod modulus, b).
Definition op_xor (a b : nat) : nat * nat := (Nat.lxor a b, b).
Definition op_nop (a b : nat) : nat * nat := (a, b).

(* An ISA maps opcode numbers 0..4 to operations.
   Opcode 5 is always JNZ (handled separately in execution). *)
Definition isa := nat -> operation.

(* ISA-A: INC DEC SWP ADD XOR *)
Definition isa_a (opc : nat) : operation :=
  match opc with
  | 0 => op_inc
  | 1 => op_dec
  | 2 => op_swp
  | 3 => op_add
  | 4 => op_xor
  | _ => op_nop
  end.

(* ================================================================ *)
(* Execution semantics                                               *)
(* ================================================================ *)

(* Fetch the opcode at position pc from a program.
   Returns jnz_opcode + 1 if pc is out of bounds (signals halt). *)
Definition fetch (p : program) (idx : nat) : nat :=
  match nth_error p idx with
  | Some opc => opc
  | None => sigma_size + 1  (* out of bounds = halt *)
  end.

(* One execution step. Returns None if halted, Some s' otherwise. *)
Definition step (delta : isa) (p : program) (s : state) : option state :=
  if pc s >=? length p then
    None  (* PC past end: halt *)
  else
    let opc := fetch p (pc s) in
    if opc =? jnz_opcode then
      (* JNZ: if A != 0 then PC <- 0 else PC++ *)
      if reg_a s =? 0 then
        Some (mkState (reg_a s) (reg_b s) (pc s + 1))
      else
        Some (mkState (reg_a s) (reg_b s) 0)
    else
      (* Non-JNZ: apply operation, advance PC *)
      let op := delta opc in
      let '(a', b') := op (reg_a s) (reg_b s) in
      Some (mkState a' b' (pc s + 1))
  end.

(* Execute for up to t steps. Returns true if halted. *)
Fixpoint execute (delta : isa) (p : program) (s : state) (t : nat) : bool :=
  match t with
  | 0 => false  (* timeout: did not halt *)
  | S t' =>
    match step delta p s with
    | None => true  (* halted *)
    | Some s' => execute delta p s' t'
    end
  end.

Definition halts (delta : isa) (p : program) : bool :=
  execute delta p init_state t_max.

(* ================================================================ *)
(* JNZ count                                                         *)
(* ================================================================ *)

(* Count the number of JNZ opcodes in a program. *)
Definition jnz_count (p : program) : nat :=
  length (filter (fun opc => opc =? jnz_opcode) p).

(* ================================================================ *)
(* Theorem statements                                                *)
(* ================================================================ *)

(* Enumerate all programs of length N over alphabet {0,...,sigma_size-1}. *)
(* This is computationally expensive but well-defined. *)
(* We state theorems in terms of counting functions. *)

(* Count programs of length N with exactly j JNZ opcodes. *)
Definition stratum_size (n j : nat) : nat :=
  Nat.choose n j * (sigma_size - 1) ^ (n - j).

(* THEOREM 1: The strata partition the program space. *)
Theorem partition_exhaustive :
  forall n : nat,
    fold_left Nat.add
      (map (fun j => stratum_size n j) (seq 0 (n + 1)))
      0
    = sigma_size ^ n.
Proof.
  (* This is the binomial theorem: sum C(n,j) * (S-1)^(n-j) * 1^j = S^n *)
  Admitted.

(* THEOREM 2 (H(0) = 1): Programs with no JNZ always halt. *)
Theorem h0_is_one :
  forall (delta : isa) (p : program),
    length p = prog_len ->
    jnz_count p = 0 ->
    halts delta p = true.
Proof.
  (* No JNZ means no instruction modifies PC except sequential advance.
     PC visits 0, 1, ..., N-1, then N >= N triggers halt. *)
  Admitted.

(* THEOREM 3 (Convergence): For N >= K, halting depends only on prefix. *)
Theorem convergence :
  forall (delta : isa) (p : program) (suffix : list opcode),
    length p = prog_len ->
    halts delta p = halts delta (p ++ suffix).
Proof.
  (* Instructions at positions >= prog_len are never reached because
     JNZ resets PC to 0 and sequential advance reaches at most prog_len.
     Therefore appending a suffix does not change execution. *)
  Admitted.

(* THEOREM 4 (Encoding invariance): Bijections preserve halt count. *)
(* This is immediate from the definition but worth stating. *)
Theorem encoding_invariance :
  forall (programs : list program) (pi : program -> program),
    (forall p1 p2, pi p1 = pi p2 -> p1 = p2) ->  (* injective *)
    (forall q, exists p, pi p = q) ->               (* surjective *)
    length (filter (fun p => halts isa_a p) programs) =
    length (filter (fun p => halts isa_a (pi p)) programs).
Proof.
  (* Bijection on a finite set preserves the cardinality of any subset. *)
  Admitted.

(* INVARIANT: Binomial weights are ISA-independent. *)
(* The weight w(j) = C(N,j) * ((S-1)/S)^(N-j) * (1/S)^j depends only
   on N and S, not on delta. This is definitional — delta does not
   appear in the weight formula. No proof needed beyond the definition. *)

(* ================================================================ *)
(* The decomposition equation (stated, not proved)                   *)
(* ================================================================ *)

(* The finite halting fraction Omega_N(delta) equals the weighted sum
   of JNZ-stratified halt rates:

     Omega_N = sum_{j=0}^{N} w(j) * H_delta(j)

   where w(j) = C(N,j) * ((S-1)/S)^(N-j) * (1/S)^j
   and   H_delta(j) = |{p : J(p)=j and p halts}| / |{p : J(p)=j}|.

   This follows from partitioning the program space by jnz_count
   and taking the weighted average. The proof is the same as
   partition_exhaustive composed with the definition of conditional
   probability on finite sets. *)

(* ================================================================ *)
(* Width invariance (empirical conjecture, not a theorem)            *)
(* ================================================================ *)

(* CONJECTURE: For ISAs delta_A and delta_B, the quantity
     Delta(W) = Omega_N(delta_A, W) - Omega_N(delta_B, W)
   is independent of the register width W.

   Measured: Delta(8) = -0.1525, Delta(10) = -0.1506,
             Delta(12) = -0.1492, Delta(14) = -0.1520.
   CV = 0.97%.

   This is NOT a theorem. A proof would require showing that the
   distribution of opcode composition orbits over Z/2^W is
   width-independent in the statistical sense relevant to halting.
   This is an open problem. *)
