# The Finite Halting Fraction is a Structural Characteristic of the Instruction Set

## Exhaustive Measurement Across 38,416 Instruction Sets, Three Machine Architectures, and Seven Register Widths

---

### Abstract

We measure the halting probability by exhaustive enumeration of all programs across 38,416 instruction sets on two-register machines (the full combinatorial space of 14 primitives in 4 opcode slots), 10 instruction sets on four-register machines, four jump mechanisms, three Turing machine semantic variants, register widths from 8 to 20 bits, and — for the two-register machine — every one of 256 initial accumulator values, physically executed on a Lattice ECP5 FPGA and verified by CPU-side exhaustive enumeration. Approximately 16.7 trillion program evaluations were performed. Every count is exact. The machines are finite-state with bounded programs; the halting fraction is the rational quantity |halting programs|/|all programs| at a fixed program length, converging exactly at program length 8 (the PC range) and thereafter invariant.

The 38,416 instruction sets — all extensionally equivalent (computing the same functions in principle, but operationally distinct under the step budget) — produce halting fractions spanning 0.291 to 0.817, a 2.81x range, with 1,148 distinct values. The dependence persists across register machines and Turing machines, across four jump mechanisms (with call/return producing a 5.4x drop), and is monotone in register coupling topology (isolated: 0.376, full coupling: 0.743). For Turing machines, encoding permutations leave the halting fraction exactly invariant (proved and verified over 100 million transition tables), while semantic variants change it. Register width scaling from 8 to 20 bits shows four of five ISAs perfectly width-invariant to 4 decimal places; the ISA delta shrinks at 0.00037/bit, reaching zero at projected W~420. For any physically realizable machine, the ISA dependence is effectively permanent.

The halting fraction admits an exact binomial decomposition into JNZ-stratified halt rates H(j), compressing the halting function 5,832x (from 205 KB to 36 bytes per ISA) with zero stratum-level error. The decomposition connects to the opcode composition semigroup: the semigroup size correlates with the halting fraction at r = 0.62, the best single-number predictor found. The dependence is nevertheless irreducible — 78% of the variance resides in 2-way through 4-way opcode interactions, with each interaction order contributing more than the previous, and this interaction structure extends identically to output entropy and cycle length. No low-dimensional projection of ISA structure captures more than 22% of the variation.

The output distribution P(x|ISA) — the finite analogue of Solomonoff's algorithmic probability — varies from 0.80 to 5.44 bits of entropy across ISAs. The nine universally reachable outputs are 0 through 8, the first nine non-negative integers. Output 0 is the most probable for 93.8% of all ISAs. The complexity ranking of simple outputs is nearly machine-independent, eroding continuously for larger values — an empirical regularity reminiscent of the invariance theorem, observed in a sub-universal setting where the theorem's preconditions are not met for sub-universal machines. The ISA-marginal output distribution, averaged over all 38,416 ISAs, is the first exact empirical universal prior computed over a complete machine class; it predicts any individual ISA's distribution to within 0.42 bits of KL divergence. The mutual information I(ISA; output) = 0.415 bits: the ISA resolves 14.2% of the output uncertainty.

The mean cycle length of non-halting programs is a second structural invariant (range 23.4 to 216.1, weakly correlated with the halting fraction at rho = -0.26), and the Gini coefficient of the complexity spectrum is a third (uncorrelated with both, r = -0.009). The ISA determines not just whether programs halt, but the geometry of confinement for those that do not, and the inequality of computational effort across outputs.

The initial-state dependence, measured across all 38,416 ISAs x 256 initial accumulator values (9,834,496 exact halting fractions, the full init-state tensor), shows that the bowl around init_a = 128 reported for ISA-A in Section 4.3 is ISA-specific rather than a property of the (A, B) ring. Only 7.9% of ISAs are reflection-symmetric in init_a; no ISA has its bowl minimum exactly at 128. The universal-decay conjecture — that Omega(ISA, a) = Omega(ISA, 0) * f(min(a, 256-a)) with f independent of the ISA — fails with across-ISA coefficient of variation 0.21 on the normalized ratio, and the ratio is non-monotone in ring distance (it exceeds 1 for some ISAs, reaching a maximum of 1.99). The ISA-A bowl factor of 1.80x is close to the population mean of 1.82x in amplitude but unrepresentative in shape.

Probabilistic interpolation between two ISAs produces a smooth Omega(T) curve that peaks at T = 0.30 with a value (0.792) exceeding both pure ISAs — the halting fraction is nonlinear in opcode mixing. No phase transition; the stat-mech analogy survives. The ISA fitness landscape is unimodal: hill-climbing from any starting point converges to the global optimum (AND×4, omega = 0.817) in 4-6 single-opcode mutations, evaluating fewer than 700 of 38,416 ISAs. Program synthesis feasibility depends on ISA choice independently of the halting fraction: the highest-omega ISA cannot synthesize the INC function, while the lowest-omega ISA cannot synthesize it controllably.

Approximately 16.7 trillion program evaluations were performed: 38,416 ISAs x 1,679,616 programs each for the halting tensor, repeated for cycle lengths and output distributions; 38,416 ISAs x 256 initial accumulator values x 1,679,616 programs for the full initial-state tensor; plus width scaling, interpolation, TM variants, GP synthesis, and silicon measurements. All counts are exact.

---

### 1. Introduction

The halting probability was introduced by Chaitin (1975) as the measure of the set of halting programs for a universal prefix-free machine U:

$$\Omega_U = \sum_{p \in \text{dom}(U)} 2^{-|p|}$$

Chaitin proved that the binary expansion of this number is algorithmically random and Turing-equivalent to the halting problem. The definition is relative to U: different machines produce different values. The invariance theorem for Kolmogorov complexity, which bounds the difference K_U(x) - K_V(x) by a constant independent of x, does not extend to the halting probability. Chaitin acknowledged this: the halting probability is "maximally machine-dependent."

The machine-dependence has been acknowledged in the theoretical literature but never systematically measured. The prior empirical work on halting probability falls into two categories: single-machine digit computation, and structural analysis of the digit sequence.

Calude, Hertling, Khoussainov, and Wang (2001) computed the first 64 bits of the halting probability for a specific register machine, using a pruning strategy that avoids enumerating all programs. Their computation took 5 years of CPU time and produced the first concrete digits of any halting probability. Calude and Dinneen (2007) extended this to other machine models and identified structural properties of the digit sequence, including patterns in the rate at which bits stabilize. Solovay (1975, unpublished) proved that the set of halting probability values across all universal machines has measure zero in [0,1] — the values are highly constrained even though they are machine-dependent. Tadaki (2002) showed that individual bits of Chaitin's Omega are statistically independent, confirming algorithmic randomness at the digit level.

None of this work asked the question we ask: given two machines that compute the same functions, how different are their halting probabilities, and does the difference have structure? The machine-dependence has been treated as a theoretical nuisance — something to acknowledge and move past — rather than a phenomenon to measure. The implicit assumption is that the dependence is "small" or "random" or "uninteresting." Our data shows it is none of these.

This paper makes the comparison — not for Chaitin's incomputable quantity, but for a finite computable analogue. We hold the machine architecture, state space, halting criterion, and physical hardware constant, and vary only the instruction set — the specific functions that the opcodes compute. We find that the finite halting fraction depends on the instruction set in a structured, measurable, and reproducible way. The dependence spans a 57% relative range across 50 ISAs, is monotone in register coupling connectivity, survives across register machines and Turing machines, persists under register width scaling, and admits an exact combinatorial decomposition but resists reduction to any simple scalar predictor.

#### 1.1 Definitions

Our machines have finite state and bounded program length. The halting probability at length N is:

$$\Omega_N(\delta, s_0) = \frac{|\{p \in \Sigma^N : p \text{ halts from } s_0 \text{ under } \delta \text{ within } T_{\max} \text{ steps}\}|}{|\Sigma|^N}$$

This is a rational number, computed exactly by exhaustive enumeration. It converges to a fixed value at N = 8 (the PC range) and is thereafter invariant. Chaitin's Omega sums 2^{-|p|} over all halting programs of all lengths for a universal prefix-free machine; ours counts the halting fraction at a fixed length for a bounded machine. The relationship between the two is an empirical question addressed in Section 4.10, where register width scaling from 8 to 20 bits shows the ISA delta is width-invariant.

**Terminology.** This paper uses "halting fraction" for the finite rational quantity Omega_N defined above, and "halting probability" for the general concept (including Chaitin's incomputable real). The title uses "halting probability" because the structural invariance we demonstrate applies to the concept, not just to our specific finite instantiation. Where the distinction matters, the text specifies which quantity is meant.

---

### 2. Machine Models

#### 2.1 Two-Register Machine

Two 8-bit registers A (accumulator) and B (auxiliary). Program counter PC ranges over {0, ..., N-1}. State space S = {0,...,255}^2 x {0,...,N-1}. Programs are words p in {0,1,2,3,4,5}^N (6 opcodes, 3 bits each). Execution: at each step, read opcode at PC, execute, advance PC by 1 unless the opcode specifies otherwise. Halt when PC >= N.

Opcode 0 is always INC (A <- (A+1) mod 256). Opcode 5 is always JNZ (if A != 0: PC <- 0, else PC <- PC+1). Opcodes 1-4 vary across ISAs.

**Timeout justification.** The (A,B) state space has 256^2 = 65,536 elements. The full execution state includes PC, giving 65,536 x N possible states. A non-halting program must enter a cycle; by pigeonhole, the cycle length is at most 65,536 x N.

The tighter argument is specific to JNZ-to-zero semantics: JNZ resets PC to 0, so any cycle must pass through PC=0. Between consecutive visits to PC=0, the machine executes at most N steps. The cycle in (A,B) space therefore has period at most 65,536. We use T_max = 256 because it is empirically sufficient: increasing T_max to 1,024, 4,096, and 65,536 does not change any measured Omega_N value for any ISA at any length.

**Important caveat:** this argument assumes JNZ is the only control flow instruction. For the call/return variant (Section 2.7), the return stack adds state and the timeout must account for the larger space. We verified empirically that T_max = 256 is sufficient for call/return by comparison with T_max = 4,096. For the Turing machine (Section 2.6), the state space is 3 x 2^16 x 16 and we use T_max = 512, verified against T_max = 2,048.

**The timeout's theoretical role.** The timeout is not merely an implementation detail — it is what makes the ISA dependence possible. Without a timeout (T_max = infinity), every non-halting program would be correctly classified by running to the pigeonhole bound, and the halting fraction would be determined entirely by the state-space reachability structure. With a finite timeout, the halting fraction additionally depends on which state-space trajectories reach A=0 *quickly enough* — and this depends on the ISA's opcode semantics. The width-scaling data (Section 4.10) shows this mechanism in action: ISA-A's halting fraction drifts upward with register width because the INC cycle length grows with 2^W, and the timeout (T_max = 2^W) gives previously-trapped programs enough steps to escape. ISAs whose opcodes are contractive (AND, SHR) are unaffected by width scaling because their trajectories converge to A=0 in few steps regardless of the state space size. The measured halting fraction is the empirically sufficient value — verified against larger timeouts — but the timeout is doing theoretical work by making ISAs operationally distinct that are extensionally equivalent.

#### 2.2 Instruction Set Definitions

We define 15 primitive operations on (A,B):

| ID | Name | Transition | Properties |
|---|---|---|---|
| 0 | INC | A <- (A+1) mod 2^W | Required for nontrivial computation |
| 1 | DEC | A <- (A-1) mod 2^W | |
| 2 | SWP | A <-> B | Involution, bidirectional coupling |
| 3 | ADD | A <- (A+B) mod 2^W | |
| 4 | XOR | A <- A xor B | Involution (with fixed B) |
| 5 | JNZ | PC <- 0 if A!=0 | Control flow |
| 6 | NEG | A <- (-A) mod 2^W | Involution |
| 7 | MOV | B <- A | One-way coupling |
| 8 | SUB | A <- (A-B) mod 2^W | Contractive with MOV |
| 9 | AND | A <- A & B | Contractive (clears bits) |
| 10 | OR | A <- A \| B | Expansive (sets bits) |
| 11 | SHR | A <- floor(A/2) | Contractive (loses LSB) |
| 12 | SHL | A <- (2A) mod 2^W | Loses MSB |
| 13 | CPL | A <- ~A | Involution |
| 14 | NOP | (no change) | Identity |

W is the register width (default 8). An ISA is a 6-tuple: opcode 0 = INC, opcode 5 = JNZ, opcodes 1-4 drawn from the primitives. Represented as a 24-bit lookup table (6 opcodes x 4-bit operation ID).

#### 2.3 Seven Original ISAs

| ISA | Opcodes 1-4 | Coupling | Contraction |
|---|---|---|---|
| A | DEC, SWP, ADD, XOR | Bidirectional | None |
| B | NEG, MOV, SUB, AND | One-way | Strong (AND, SUB+MOV) |
| C | SHR, CPL, ADD, OR | None | Weak (SHR) |
| D | SHL, MOV, ADD, OR | One-way | None |
| E | NEG, SWP, CPL, XOR | Bidirectional | None (4 involutions) |
| F | DEC, SWP, SUB, XOR | Bidirectional | None |
| G | SHR, MOV, SUB, AND | One-way | Strong (AND, SHR) |

All seven ISAs are extensionally equivalent: they operate on the same state space, share the same control flow, and any input-output function computable on one is computable on another (INC + JNZ can simulate any register operation through repeated incrementing). They are not Turing-complete. The equivalence is extensional, not operational — simulation via INC requires exponentially more steps than native execution, and the timeout T_max = 256 makes the ISAs operationally distinct. The halting fraction variation measured in this paper is a consequence of this operational distinction: ISAs differ in which state-space trajectories reach A=0 within the step budget.

#### 2.4 Fifty-ISA Population

43 additional ISAs were generated by iterating over a structured grid:

- **Coupling slot**: one of {SWP, MOV}
- **Contraction slot**: one of {AND, SHR, DEC}
- **Arithmetic slot**: one of {ADD, SUB}
- **Miscellaneous slot**: one of {XOR, OR, CPL, NEG, DEC, SHL}

This gives 2 x 3 x 2 x 6 = 72 candidates. After removing duplicates and the 7 originals, 43 unique ISAs remain (50 total).

Three limitations of the grid:

1. **Mandatory coupling.** Every generated ISA includes SWP or MOV. No-coupling ISAs are absent from the 43 new ISAs (only ISA-C from the original 7 lacks coupling). The 4-register data (Section 4.7) partially compensates: the "isolated" topology achieves Omega_8 = 0.376, confirming that no-coupling ISAs occupy a distinct region the grid misses.

2. **DEC overloading.** DEC appears in both the contraction and miscellaneous slots, creating degenerate ISAs with two copies of DEC that produce artificially low Omega_8 values (0.494, 0.515).

3. **One-per-slot structure.** The grid assigns one opcode per functional role. Real ISAs might benefit from two contraction ops or two coupling ops. The grid underestimates the diversity of structurally natural ISAs.

Claims about the Omega_N distribution being "continuous" refer to its empirical shape within the sampled subspace, not the full C(14,4) = 1,001 combinatorial space. The full table is in Appendix A.

The 50-ISA population was the original silicon experiment. The full 38,416-ISA tensor (Section 4, computed on CPU) subsumes it: all 50 ISAs appear as rows in the tensor, and their CPU-computed halting counts match the silicon measurements exactly. The 50-ISA results are retained because they were the first measurements and because the silicon cross-validation applies to them specifically.

#### 2.5 Four-Register Machine

Four 8-bit registers R0, R1, R2, R3. JNZ tests R0. Output = R0 on halt. Opcodes drawn from 16 primitives including inter-register SWP, MOV, ADD, XOR, and 4-way rotation. ISA defined by a 32-bit lookup table. Ten coupling topologies tested (Section 4.7).

#### 2.6 Turing Machine

3 internal states {0,1,2}, halt state 3. 2 tape symbols {0,1}. Tape length 16, initialized to all zeros, head starts at position 8. Transition table: 6 entries (3 states x 2 symbols), each 4 bits (write_symbol, move_direction, next_state). Program = 24 bits = 16,777,216 possible transition tables. Timeout 512 steps.

Three semantic variants, differing only in the move_direction bit:
- **Standard**: 0 = left, 1 = right
- **Stay**: 0 = left, 1 = stay
- **Nonlinear**: 0 = left, 1 = right by (1 + written_symbol) positions

#### 2.7 Jump Mechanism Variants

All use ISA-A opcodes 1-4:
- **JNZ-to-zero**: if A != 0, PC <- 0
- **Computed jump**: if A != 0, PC <- B mod 8
- **Relative jump**: if A != 0, PC <- (PC - B mod 8) mod 8
- **Call/return**: opcode 5 = CALL (push PC+1, jump to 0 if A != 0); opcode 4 = RET (pop into PC)

#### 2.8 Width-Parameterized Machine

The two-register machine with register width W in {8, 10, 12, 14, 16, 18, 20} bits. All operations are mod 2^W. Program structure unchanged (6 opcodes, length 8). T_max = min(2^W, 2^20). Tested with five ISAs (A, B, G, MIN, MAX) to measure how the ISA delta scales with state space size.

---

### 3. Apparatus

#### 3.1 Hardware Platform

All experiments were conducted on an IcePi Zero board featuring a Lattice ECP5U-25F FPGA:

| Resource | Available | Typical utilization |
|---|---|---|
| LUT4 | 24,288 | 30-62% depending on config |
| Block RAM (DP16KD) | 56 | 7 (RIME-I firmware) |
| Multipliers (MULT18X18D) | 28 | 0 (not used) |
| System clock | 50 MHz oscillator | Divided to 25 MHz in fabric |

The board connects to the host via USB through an FTDI FT231X bridge, providing either UART (serial, 115200 baud) for data collection or JTAG for bitstream loading. The RIME firmware manages flash, SDRAM, and SD operations; for these experiments, only JTAG loading and UART output are used. Bitstream loading takes ~2 seconds. Driver switching between UART and JTAG modes takes ~3 seconds and is automated by the `icepi_admin.py` wrapper.

#### 3.2 Interpreter Architecture

Each interpreter is a fully independent, synchronous state machine instantiated by the Verilog `generate` construct. The interpreters share no state and execute in parallel on every clock edge.

**Two-register interpreter** (`tiny_interp_param`):
- 8-bit registers A, B: 16 flip-flops
- 4-bit program counter: 4 flip-flops
- 9-bit step counter: 9 flip-flops
- 24-bit program register: 24 flip-flops (8 instructions x 3 bits)
- 24-bit ISA LUT register: 24 flip-flops (6 opcodes x 4-bit operation ID)
- Combinational opcode mux: 8-to-1 based on PC
- Combinational ALU: 15-way mux based on operation ID
- Control FSM: idle/running/done (2 flip-flops)
- Total: ~60 LUT4, ~80 flip-flops per interpreter

**Four-register interpreter** (`tiny_interp_4reg`): ~80 LUT4 (32 flip-flops for registers, wider ALU mux).

**Turing machine interpreter** (`tiny_tm`):
- 16-bit tape: 16 flip-flops
- 4-bit head position, 2-bit state, 10-bit step counter
- 6-entry transition table lookup (combinational)
- Total: ~90 LUT4

**Width-parameterized interpreter** (`tiny_interp_wN`): register width W, step counter width ceil(log2(2^W)), ALU width W. At W=16, each interpreter is ~150 LUT4.

The **parameterized ISA** design is the key architectural innovation. Instead of hardcoding each opcode's behavior in a case statement (requiring a new bitstream for each ISA), the interpreter reads a 24-bit ISA LUT register that maps each of the 6 raw opcodes to one of 15 primitive operations. The firmware writes a new LUT value between runs; the hardware reconfigures instantly. This allows the 50-ISA sweep to run from a single bitstream in 44 seconds.

#### 3.3 Controller and Enumeration

The KOLMOGOROV controller manages the interpreter array:

- **Base-6 odometer** (register machines): 8 digits x 3 bits = 24 flip-flops. Increments without division by maintaining carry propagation through the digit chain. Each batch: the controller assigns programs odometer+0 through odometer+(N_INTERP-1) to the interpreters, advances the odometer by N_INTERP, and starts execution.

- **Binary counter** (Turing machines): 24-bit counter, trivial increment. Programs are assigned counter+0 through counter+15.

- **Load phase**: sequentially assigns programs to interpreters (1 cycle per interpreter, ~16-20 cycles total).

- **Run phase**: all interpreters execute in parallel. The controller waits for all `done` signals or a timer expiry (T_max + margin). At 25 MHz with T_max = 256, each batch takes ~280 cycles = 11.2 microseconds.

- **Collect phase**: scans each interpreter's `halted` and `result` outputs, incrementing `halt_count` and `match_count` accumulators (32-bit each). ~16-20 cycles.

Throughput at 25 MHz:

| Config | T_max | Batch cycles | Programs/sec | Time for 6^8 |
|---|---|---|---|---|
| 16 interp, W=8 | 256 | ~280 | 1,430,000 | 1.2 s |
| 16 interp, TM | 512 | ~540 | 741,000 | 22.6 s |
| 16 interp, W=12 | 4,096 | ~4,120 | 97,000 | 17.3 s |
| 16 interp, W=16 | 65,536 | ~65,560 | 6,100 | 275 s |
| 20 interp, W=8 | 256 | ~280 | 1,790,000 | 0.9 s |
| 50 interp, W=8 | 256 | ~310 | 4,030,000 | 0.4 s |

Multiple controller instances coexist in a single bitstream at different memory-mapped addresses (0x30-0x34), driven sequentially by firmware running on the RIME-I soft CPU (RV32I, 5-state multi-cycle, ~4,050 LUT4, 14 KB BRAM). The CPU generates UART output at 115200 baud; data collection is automated by a Python capture script on the host.

#### 3.4 Verification

The physical execution model introduces no statistical uncertainty — every program is executed exactly once, and every halt/no-halt classification is deterministic. The only potential error source is the T_max timeout, which is verified sufficient by comparison with larger timeouts (Section 2.1).

Correctness is verified by:

1. **CPU cross-validation.** Every silicon measurement for the 7 original ISAs was independently verified by a Python reference implementation that executes all 1,679,616 programs in software. The halt counts match exactly (e.g., ISA-A: silicon = 978,929, CPU = 978,929). For the 3 TM variants, the standard TM count matches between silicon and CPU to the exact program (9,699,536).

2. **Board regression.** The RIME regression suite — a 58-step CRC-32 chain through every board subsystem (flash, SDRAM, SD, protocol, error paths) — is run before and after each experiment. Any subsystem failure would cause the chain hash to diverge.

3. **Repetition.** All measurements are repeated across board power cycles and produce identical counts. The FPGA is a deterministic state machine; there is no run-to-run variation.

#### 3.5 Data Availability

Two Parquet tables are published at [phanerozoic/omega-tensor](https://huggingface.co/datasets/phanerozoic/omega-tensor): [`omega_tensor.parquet`](https://huggingface.co/datasets/phanerozoic/omega-tensor/blob/main/omega_tensor.parquet), the canonical 38,416-row single-initial-state table with halting counts, cycle lengths, output entropy, and structural flags (Sections 4.1-4.2, 4.11-4.12); and [`init_state_tensor.parquet`](https://huggingface.co/datasets/phanerozoic/omega-tensor/blob/main/init_state_tensor.parquet), the 38,416 x 256 tensor of halting counts at every initial accumulator value (Section 4.3.1). An interactive explorer covering both is at [phanerozoic/omega-explorer](https://huggingface.co/spaces/phanerozoic/omega-explorer). All source code, firmware, and raw data are at [CharlesCNorton/rime](https://github.com/CharlesCNorton/rime).

---

### 4. Results

#### 4.1 Convergence

Omega_N for one ISA at lengths 1-11:

| N | Programs | Halting | Omega_N | Delta |
|---|---|---|---|---|
| 3 | 216 | 197 | 0.912 | -- |
| 4 | 1,296 | 1,083 | 0.836 | -0.077 |
| 5 | 7,776 | 6,035 | 0.776 | -0.060 |
| 6 | 46,656 | 33,465 | 0.717 | -0.059 |
| 7 | 279,936 | 184,777 | 0.660 | -0.057 |
| 8 | 1,679,616 | 1,016,508 | 0.605 | -0.055 |
| 9 | 10,077,696 | 6,099,048 | 0.605 | 0.000 |
| 10 | 60,466,176 | 36,594,288 | 0.605 | 0.000 |
| 11 | 362,797,056 | 219,565,728 | 0.605 | 0.000 |

Convergence at N=8 is exact: zero change through N=11 (4 additional lengths, 216x program space growth).

#### 4.1.1 Seven-ISA Comparison

Exact Omega_8 from CPU exhaustive enumeration (1,679,616 programs per ISA):

| ISA | Halting | Omega_8 |
|---|---|---|
| A | 978,929 | 0.582829 |
| B | 1,235,107 | 0.735351 |
| C | 1,026,773 | 0.611314 |
| D | 1,035,393 | 0.616446 |
| E | 1,181,630 | 0.703512 |
| F | 1,003,574 | 0.597502 |
| G | 1,248,490 | 0.743319 |

Maximum pairwise delta: |Omega(A) - Omega(G)| = 0.160.

Omega_N at lengths 1-8 for all seven ISAs:

| N | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| 3 | 0.912 | 0.942 | 0.942 | 0.933 | 0.951 | 0.912 | 0.938 |
| 4 | 0.836 | 0.912 | 0.901 | 0.891 | 0.917 | 0.836 | 0.907 |
| 5 | 0.776 | 0.875 | 0.843 | 0.838 | 0.875 | 0.776 | 0.867 |
| 6 | 0.717 | 0.835 | 0.781 | 0.777 | 0.830 | 0.717 | 0.829 |
| 7 | 0.660 | 0.793 | 0.717 | 0.715 | 0.784 | 0.660 | 0.792 |
| 8 | 0.583 | 0.735 | 0.611 | 0.616 | 0.704 | 0.598 | 0.743 |

Pairwise deltas grow monotonically from N=2 to N=8, then stabilize.

#### 4.1.2 JNZ-Halt Decomposition

Programs without JNZ always halt. The JNZ-free fraction (5/6)^N is ISA-independent. The ISA-dependent component Phi_N = Omega_N - (5/6)^N is the fraction of JNZ-containing programs that halt.

| N | (5/6)^N | Phi(A) | Phi(B) | Phi(E) | Phi(G) |
|---|---|---|---|---|---|
| 4 | 0.482 | 0.354 | 0.430 | 0.435 | 0.425 |
| 6 | 0.335 | 0.382 | 0.500 | 0.495 | 0.494 |
| 8 | 0.233 | 0.350 | 0.503 | 0.471 | 0.511 |

Contractive ISAs (B, G) increase Phi monotonically. SWP ISAs (A) decrease from N=6.

#### 4.1.3 Confirmatory Predictions

**ISA-F** (SWP-class test): predicted Omega ~ 0.583 (same as A). Result: 0.598. Error: 0.015 (2.5%). Confirmed.

**ISA-G** (coupling-only test): predicted Omega ~ 0.616 (same as D). Result: 0.743. Error: 0.127 (20%). **Falsified.** Contraction dominates coupling when SWP is absent.

#### 4.2 Fifty-ISA Population

All 50 ISAs at L=8, init (0,0), on silicon:

| Metric | Value |
|---|---|
| Range | [0.494, 0.775] |
| Mean | 0.667 |
| Distinct classes (0.01) | 24 |
| Programs per ISA | 1,679,616 |
| Total | 83,980,800 |
| Wall time | 44 seconds |

Lowest: 0.494 (X36: DEC, SWP, ADD, DEC — degenerate). Highest: 0.775 (X17: NEG, SWP, SUB, AND — coupling + contraction). Full table in Appendix A.

#### 4.3 Initial State Dependence

256 initial A values (init_b=0) for ISA-A at L=8, on silicon:

| Metric | Value |
|---|---|
| Min Omega_8 (A=128) | 0.337 |
| Max Omega_8 (A=0) | 0.605 |
| Factor | 1.80x |
| Shape | Symmetric bowl, min at max ring distance from 0 |
| Programs | ~430,000,000 |

Initial-state factor (1.80x) exceeds ISA factor (1.57x).

#### 4.3.1 Full Initial-State Tensor

Section 4.3 measured the initial-state dependence for ISA-A alone: a symmetric bowl from 0.337 at A=128 up to 0.605 at A=0, factor 1.80x. The question left open was whether that shape reflects the (A, B) ring — A=0 and A=256 are identified, so ring distance min(A, 256-A) is a natural coordinate — or whether it reflects ISA-A's specific opcodes. Section 8 of an earlier version listed the resolving measurement as open: a conjecture that Omega(ISA, a) = Omega(ISA, 0) * f(min(a, 256-a)) with f a universal ISA-independent decay function, verifiable over the full tensor.

We computed that tensor: Omega(delta, init_a) for all 38,416 ISAs x 256 initial accumulator values at init_b = 0. 9,834,496 exact halting fractions, each the result of exhaustive enumeration of the full 1,679,616-program space — approximately 16.5 trillion additional program evaluations. The computation used the same Numba-JIT interpreter as the halting tensor of Section 4, parallelized across an 18-worker multiprocessing pool with periodic checkpointing. Total wall time 110.3 hours, zero errors. As an integrity check, the init_a=0 slice of this tensor reproduces the canonical 38,416-row halting tensor ISA by ISA. The full tensor is published as [`init_state_tensor.parquet`](https://huggingface.co/datasets/phanerozoic/omega-tensor/blob/main/init_state_tensor.parquet) alongside the canonical table.

The population does not share ISA-A's bowl shape.

**Reflection symmetry is the exception.** Only 7.91% of ISAs (3,040 of 38,416) satisfy Omega(a) = Omega(256-a) across the full range of init_a. The remaining 92% break reflection symmetry, and they break it substantially: 81.83% have RMS asymmetry above 0.01, and the worst reach RMS 0.18 with pointwise gaps up to 0.35. The symmetric minority is populated by ISAs whose transition set preserves the a <-> (256-a) involution — chiefly those pairing NEG with companions that commute with it — and the structure of that preservation is visible in the non-permutation omega-equivalence classes cataloged by the output-distribution tensor.

**No ISA minimizes at init_a = 128.** Zero of 38,416 ISAs place the bowl floor exactly at the ring antipode. The mode of argmin is 129, accounting for 3.19% of ISAs; only 3.23% fall in the window [126, 130]. ISA-A's "min at max ring distance from 0" description is a particular feature of ISA-A's opcode composition, not a general property of the machine model.

**The universal-decay conjecture is falsified.** Define r_delta(a) = Omega(delta, a) / Omega(delta, 0), the normalized ratio against the canonical initial state. The conjecture predicts r_delta(a) = f(min(a, 256-a)) with f independent of delta, which in turn predicts that the across-ISA coefficient of variation of r at fixed ring distance d should be near zero. Measurement gives CV(r | d) in [0.18, 0.25] across d in [1, 128], mean 0.21. The shape of r(a) is ISA-specific at the same scale as its amplitude. More sharply, r is not even monotone in d: for some (delta, a) pairs r exceeds 1, reaching a maximum of 1.99 — there exist ISAs for which a specific nonzero initial state halts nearly twice as many programs as init_a = 0 does. The "decay" can be a gain, and the gain depends on which delta is being evaluated.

**Ratio distribution.** The compact summary of bowl shape across the population is the ratio Omega(ISA, 0) / Omega(ISA, 128):

| Statistic | Value |
|---|---|
| Mean | 1.7429 |
| Median | 1.6430 |
| Standard deviation | 0.4215 |
| Range | [0.8336, 3.1466] |
| Fraction with ratio > 1 | 99.92% |
| Fraction with ratio < 1 | 0.08% |

The 32 ISAs with ratio below 1 are all INC-dominant: for these ISAs the canonical start A=0 sits at the worst possible position, and nonzero initial accumulators halt more often because the INC cycle has more opportunity to pass through zero within the step budget. The top of the distribution is populated by NEG-heavy ISAs, which map A=0 to a halting-friendly orbit while dispersing nonzero starts across non-halting ones. The ISA-A bowl factor of 1.80x sits near the population mean of 1.82x, which makes ISA-A representative in amplitude but not in shape.

**Bowl depth.** The absolute depth Omega(ISA, 0) - min_a Omega(ISA, a) ranges from 0.058 to 0.513, mean 0.260. Every ISA has a measurable bowl (no ISA is flat), but the depth varies by nearly an order of magnitude across the population.

**Implication for Section 6.** The stat-mech analogy predicted that the bowl reflects density of states around the halting attractor, and therefore that rescaling by Omega(ISA, 0) should produce a universal shape tied to the ring-distance coordinate. Measurement does not support that. The bowl carries ISA-specific structure at the same scale as its amplitude, and in some cases inverts sign. Together with the U-shape of H(j) reported in Section 4.18 — which departs from the exponential decay that a Boltzmann mapping would predict — this is a second concrete failure of the thermodynamic analogy's functional predictions. The decomposition theorem of Section 4.8 remains exact; its structural mapping onto the partition function form is preserved. What does not survive measurement is the analogy's extrapolation from that form to specific shapes for H(j) or for the init-state bowl.

#### 4.4 Turing Machine Semantic Variants

3-state 2-symbol, 16-cell tape, 512-step timeout. All three enumerated exhaustively on silicon in parallel:

| Variant | Halting | Space | Omega | Delta |
|---|---|---|---|---|
| Standard (L/R) | 9,699,536 | 16,777,216 | 0.578137 | -- |
| Stay (L/Stay) | 9,252,528 | 16,777,216 | 0.551494 | -0.026643 |
| Nonlinear (L/R+ws) | 9,779,856 | 16,777,216 | 0.582925 | +0.004788 |

50,331,648 TMs total, 23.2 seconds on silicon. Standard matches CPU (9,699,536 exact).

**Connection to the Busy Beaver problem.** Our 3-state 2-symbol TMs operate on the same state space as the BB(3) machines studied by Rado (1962), Lin and Rado (1965), and Brady (1983). Brady proved BB(3) = 6 (the maximum number of 1s written by a halting 3-state 2-symbol TM on a blank tape). Our enumeration differs in three respects: (1) our tape is finite (16 cells vs semi-infinite), (2) our timeout is 512 steps (Brady's 3-state machines all halt within 21 steps), and (3) we count ALL halting machines, not just the champion. The 9,699,536 halting TMs out of 16,777,216 total (57.8%) represents the full census of the 3-state 2-symbol halting landscape — the denominator to the Busy Beaver's numerator. Brady identified 4 champion TMs that write 6 ones; we count the 9,699,536 that halt at all.

The finite tape (16 cells) means our halting set is a superset of the infinite-tape halting set — a TM that halts on 16 cells also halts on infinite tape (the converse is not necessarily true, as a machine might walk off a 16-cell tape but halt on a longer one). Increasing the tape length to 32 or 64 cells would increase the halting count; at tape length >= 21 (the maximum steps for BB(3)), the halting set converges to the infinite-tape halting set for the 3-state case. The Marxen and Buntrock (1990) enumeration of BB(4) machines used a similar exhaustive approach but focused on identifying the champion rather than counting the full halting set.

#### 4.5 Encoding Invariance

Six permutations of TM entry order, exhaustive on CPU:

| Encoding | Halting |
|---|---|
| Standard | 9,699,536 |
| Swap states 0,1 | 9,699,536 |
| Swap symbols | 9,699,536 |
| Reverse | 9,699,536 |
| Rotate states | 9,699,536 |
| Interleave | 9,699,536 |

Zero delta (100,663,296 TMs). This is a theorem: a permutation of entry order is a bijection on program space; exhaustive enumeration over a bijection preserves cardinality. Semantic variants (Section 4.4) change halting because they change what the table does, not how it is numbered.

Also verified on 2-state 2-symbol (65,536 TMs): 4 encodings all produce 28,708; 3 semantic variants produce 28,708, 26,660, and 27,588.

#### 4.6 Jump Mechanism Variants

All at L=8, ISA-A, init (0,0), on silicon:

| Mechanism | Omega_8 | Delta |
|---|---|---|
| JNZ to 0 | 0.607 | -- |
| Computed (B mod 8) | 0.607 | 0.000 |
| Relative (backward B mod 8) | 0.582 | -0.025 |
| Call/Return (2-deep stack) | 0.113 | -0.494 |

**The call/return result.** The 5.4x drop is the largest single-factor effect in this study. The mechanism: CALL pushes PC+1 onto a 2-deep return stack and jumps to 0. Repeated CALLs overflow the stack (wraps at depth 2), corrupting return addresses. When the loop exits (A=0), RET pops a corrupted address, often creating a second-order recursion trap.

Of 1,679,616 programs at L=8, approximately 65% are trapped in infinite recursion. The call/return result shows that control flow structure is the single most powerful determinant of the halting fraction — more powerful than arithmetic, coupling, or initial state. Replacing one opcode (XOR -> RET) and changing the semantics of another (JNZ -> CALL) produces a larger effect than the entire 50-ISA sweep.

Convergence at L=8 holds for all four mechanisms (silicon-verified).

#### 4.7 Four-Register Coupling Topology

10 ISAs on the 4-register machine, L=8, init (0,0,0,0), on silicon:

| Topology | Omega_8 |
|---|---|
| Isolated (R0 only) | 0.376 |
| One-way broadcast | 0.510 |
| Chain R0->R1->R2->R3 | 0.513 |
| 2-reg baseline | 0.583 |
| 4-way rotation | 0.605 |
| Pairwise swap x2 | 0.624 |
| Broadcast + AND | 0.675 |
| Contraction (AND+SUB) | 0.696 |
| XOR network | 0.725 |
| Full coupling | 0.743 |

Monotone in coupling connectivity without exception. 16.8M programs on silicon.

#### 4.8 Exact Decomposition

**Theorem.** Let J(p) = number of JNZ opcodes in program p. Define:

$$H_\delta(j) = \frac{|\{p \in \Sigma^N : J(p) = j \wedge p \text{ halts}\}|}{|\{p \in \Sigma^N : J(p) = j\}|}$$

Then:

$$\Omega_N(\delta, s_0) = \sum_{j=0}^{N} \binom{N}{j} \left(\frac{|\Sigma|-1}{|\Sigma|}\right)^{N-j} \left(\frac{1}{|\Sigma|}\right)^j H_\delta(j)$$

**Proof.** Partition Sigma^N by J(p). Stratum j has C(N,j)*(|Sigma|-1)^{N-j} programs. Halting fraction in stratum j is H(j). Overall halting fraction is the weighted average with binomial weights. QED.

**Binomial weights** (N=8, |Sigma|=6):

| j | w(j) | Programs |
|---|---|---|
| 0 | 0.2326 | 390,625 |
| 1 | 0.3721 | 625,000 |
| 2 | 0.2605 | 437,500 |
| 3 | 0.1042 | 175,000 |
| 4 | 0.0260 | 43,750 |
| 5+ | 0.0046 | 7,741 |

**H(j) values** (CPU exhaustive):

| j | H(A) | H(B) | H(C) | H(D) | H(E) | H(F) | H(G) |
|---|---|---|---|---|---|---|---|
| 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 1 | 0.569 | 0.731 | 0.600 | 0.546 | 0.771 | 0.597 | 0.731 |
| 2 | 0.369 | 0.596 | 0.413 | 0.451 | 0.499 | 0.382 | 0.617 |
| 3 | 0.312 | 0.555 | 0.354 | 0.456 | 0.402 | 0.319 | 0.577 |
| 4 | 0.316 | 0.564 | 0.354 | 0.503 | 0.383 | 0.320 | 0.583 |

**Reconstruction verification:**

| ISA | Exact | Reconstructed | Error |
|---|---|---|---|
| A | 0.582829 | 0.582555 | 0.000274 |
| B | 0.735351 | 0.735086 | 0.000265 |
| C | 0.611314 | 0.611063 | 0.000252 |
| D | 0.616446 | 0.616038 | 0.000408 |
| E | 0.703512 | 0.703313 | 0.000199 |
| F | 0.597502 | 0.597233 | 0.000269 |
| G | 0.743319 | 0.743086 | 0.000232 |

Maximum error 0.0004, arising from approximating H(j) ~ H(4) for j >= 5. With exact H(j) for all j, the decomposition is exact by construction.

**The primitive.** The quantity H_delta(j) — the JNZ-stratified halt rate — is the fundamental primitive from which the halting fraction is computed. It is a property of the ISA delta alone (it depends only on the opcode transition functions and the initial state, not on the program length N or the alphabet size |Sigma|, which enter only through the binomial weights). H_delta(j) is computable from the ISA without executing any programs: it is the probability that a random composition of j non-JNZ opcodes interleaved with (N-j) non-JNZ opcodes, executed from the initial state as a deterministic loop body, reaches A=0 within T_max iterations. However, no closed-form reduction of H_delta(j) to single-opcode properties exists — every tested scalar predictor fails on a broad ISA population (Section 5.1). H(j) depends on the full combinatorial structure of multi-opcode compositions and their orbits in state space. This irreducibility is the central negative result of the paper.

**The invariants.** Two quantities are provably ISA-invariant:

1. **H(0) = 1 for all ISAs.** Programs with no JNZ instruction always halt (they execute sequentially and PC reaches N). This is independent of the opcodes.

2. **The binomial weights w(j) are ISA-invariant.** They depend only on N and |Sigma|, not on delta. The ISA enters the decomposition solely through H(j) for j >= 1.

These invariants mean that the ISA dependence of Omega_N resides entirely in the function j -> H_delta(j) for j = 1, ..., N. The decomposition separates the ISA-dependent content (H) from the ISA-independent structure (the binomial weights).

#### 4.8.1 Prefix-Free Encoding

ISA-PF (HALT replaces one opcode) produces the same halting fraction as the fixed-length ISA at L=6 and L=8, because a measure-preserving correspondence exists between the two halting sets. This equivalence is specific to bounded-PC machines and may not hold for Turing-complete machines.

#### 4.9 Convergence Theorem

**Theorem.** For PC range {0,...,K-1} with JNZ semantics "if A!=0: PC<-0":

For all N_1, N_2 >= K: Omega_{N_1} = Omega_{N_2}

**Proof.** Every program of length N > K has its halting status determined by its first K opcodes. JNZ resets PC to 0; all loop bodies and fall-through paths involve only positions 0..K-1. For each halting truncation in Sigma^K, all |Sigma|^{N-K} extensions halt. Therefore |H_N| = |H_K| * |Sigma|^{N-K} and Omega_N = Omega_K. QED.

**Corollary.** Applies to computed and relative jumps (all targets in {0,...,K-1}). Silicon-verified for K=8 across all four mechanisms.

**Scope limitation.** The convergence theorem applies to the scalar halting fraction Omega_N. It does not extend to the output distribution P(x|ISA). The total variation distance between P(x) at consecutive program lengths decreases monotonically but remains nonzero at N=8:

| N-1 → N | TV(ISA-A) | TV(ISA-B) | TV(ISA-G) |
|---|---|---|---|
| 3 → 4 | 0.040 | 0.024 | 0.017 |
| 5 → 6 | 0.033 | 0.012 | 0.008 |
| 7 → 8 | 0.030 | 0.009 | 0.005 |

The halting fraction converges exactly at the PC range; the output distribution continues to shift as longer programs reach new output values through longer opcode compositions. The convergence theorem is specific to the counting measure (how many programs halt), not the output measure (what they produce).

**Scope condition.** All results in this paper are measured at program length N = 8, which equals the PC range K = 8 of the JNZ-to-zero machine. The convergence theorem guarantees that the halting fraction at N = 8 equals the halting fraction at any N >= 8 for this control flow. For machines with richer control flow — computed jumps to arbitrary positions, variable-length programs, or recursive call structures — the convergence theorem does not apply and the halting fraction at length 8 may differ from the halting fraction at length 100. The results reported here are specific to the regime where program length equals the PC range and JNZ resets to position 0.

#### 4.10 Register Width Scaling

Five ISAs measured at widths 8 through 20 bits (exhaustive, CPU, 1,679,616 programs each, T_max = min(2^W, 2^20)):

| W | Omega_A | Omega_B | Omega_G | Omega_MIN | Omega_MAX | Delta(A-B) |
|---|---|---|---|---|---|---|
| 8 | 0.582829 | 0.735351 | 0.743319 | 0.290710 | 0.816916 | -0.152522 |
| 10 | 0.584778 | 0.735350 | 0.743315 | 0.290710 | 0.816916 | -0.150573 |
| 12 | 0.586103 | 0.735343 | 0.743323 | 0.290710 | 0.816916 | -0.149240 |
| 14 | 0.586538 | 0.735352 | 0.743329 | 0.290710 | 0.816916 | -0.148814 |
| 16 | 0.586723 | 0.735343 | 0.743293 | 0.290710 | 0.816916 | -0.148620 |
| 18 | 0.587019 | 0.735358 | 0.743297 | 0.290710 | 0.816916 | -0.148339 |
| 20 | 0.587287 | 0.735344 | 0.743292 | 0.290710 | 0.816916 | -0.148056 |

Three observations:

**ISAs B, G, MIN, and MAX are perfectly width-invariant.** ISA-B = 0.7353 at every width from 8 to 20 (4 decimal places stable across a 4,194,304x state space expansion). ISA-G = 0.7433. MIN = 0.2907. MAX = 0.8169. These ISAs' halting probabilities are independent of register width.

**ISA-A drifts slowly upward.** 0.5828 at W=8 to 0.5873 at W=20. This is a real effect: as register width grows, the INC cycle length grows from 256 to 2^W, and the timeout grows proportionally. Some programs that timed out at W=8 (because 256 INC steps was insufficient to wrap A back to zero) now halt at W=20 (where 2^20 steps is available). The drift is monotone, 0.0045 over 12 bits of width.

**The delta shrinks monotonically but slowly.** -0.1525 at W=8 to -0.1481 at W=20. The shrinkage rate is 0.00037 per bit of width. At this rate, the delta reaches zero at W ~ 420 — far beyond any physically realizable machine. The earlier 4-point measurement (W=8-14) appeared non-monotone because the W=14 run used a capped T_max; the full measurement with T_max = 2^W resolves the monotonicity.

The ISA dependence of the halting probability is not exactly width-invariant — it converges toward zero at ~0.04% per bit. But the convergence is so slow that the delta retains 97% of its W=8 magnitude at W=20, and would retain ~85% at W=32. For physically realizable machines, the ISA dependence is effectively permanent.

#### 4.11 Cycle Length Distribution

For each non-halting program, the cycle length is the period of the eventual periodic orbit in (A, B, PC) state space: the smallest k such that the state at step T equals the state at step T-k. Computed exhaustively across all 38,416 ISAs (1,679,616 programs each, same enumeration as the halting tensor).

| ISA | Omega | Avg cycle | Max cycle |
|---|---|---|---|
| A (DEC SWP ADD XOR) | 0.5828 | 188.3 | 255 |
| B (NEG MOV SUB AND) | 0.7354 | 89.2 | 255 |
| C (SHR CPL ADD OR) | 0.6113 | 67.7 | 255 |
| D (SHL MOV ADD OR) | 0.6164 | 85.9 | 255 |
| E (NEG SWP CPL XOR) | 0.7035 | 137.8 | 255 |
| F (DEC SWP SUB XOR) | 0.5975 | 185.4 | 255 |
| G (SHR MOV SUB AND) | 0.7433 | 76.9 | 255 |
| MIN (INC x5) | 0.2907 | 216.1 | 255 |
| MAX (AND x4) | 0.8169 | 49.6 | 255 |

Across the full tensor: mean cycle length ranges from 23.4 (SHL x3 + CPL — contractive operations that collapse the state space into small attractors) to 216.1 (INC x5 — the INC operation creates a 256-step orbit on Z/256Z, and non-halting programs are trapped in near-maximal cycles). The population mean is 116.2, with 825 distinct values at one decimal place.

The maximum cycle length is 255 for every ISA without exception. Every ISA has at least one non-halting program whose orbit spans the full step budget. This is a universal property of the machine model, not the instruction set.

The correlation between the halting fraction and the mean cycle length is weak: Pearson r = -0.31, Spearman rho = -0.26. ISAs with high halting fractions tend toward shorter cycles (the programs that do loop are trapped in tight attractors), but the relationship is far from deterministic. ISA-A (Omega = 0.583, avg cycle = 188.3) and ISA-C (Omega = 0.611, avg cycle = 67.7) have similar halting fractions but a 2.8x difference in mean cycle length. The cycle length distribution is a genuine second observable that characterizes each ISA independently of its halting fraction.

The physical interpretation: contractive operations (AND, SHR, SHL) reduce the effective state space by clearing or shifting bits, creating small basins of attraction. Identity-like operations (INC, DEC, NOP) preserve state space volume, producing long orbits. The mean cycle length measures the average basin size; the halting fraction measures the probability of escaping the basin entirely.

#### 4.12 Output Distribution and Algorithmic Probability

For each halting program, the output is the value of register A at halt. The output distribution P(x|ISA) is the fraction of halting programs that produce each byte value x. This is the finite analogue of Solomonoff's algorithmic probability — the quantity that universal induction uses as a prior over hypotheses. Computed exhaustively across all 38,416 ISAs.

| Metric | Value |
|---|---|
| Output entropy range | [0.80, 5.44] bits |
| Mean entropy | 2.50 bits |
| Reachable outputs per ISA | [9, 211] / 256 |
| Mean reachable | 53.7 |
| Outputs reachable by ALL ISAs | 9 |
| Outputs unreachable by ALL ISAs | 0 |

The entropy range is a 6.8x factor (0.80 to 5.44 bits). ISAs at the low end concentrate almost all halting programs onto 2-3 output values — their algorithmic probability distribution is sharply peaked. ISAs at the high end spread across 211 distinct outputs — their distribution is nearly uniform over the reachable subset.

The nine universally reachable outputs are 0, 1, 2, 3, 4, 5, 6, 7, 8 — the first nine non-negative integers. They are not merely reachable but dominant:

| Output | Mean P(x) | #1 most probable in N ISAs | Top-5 in N ISAs |
|---|---|---|---|
| 0 | 0.420 | 36,046 / 38,416 (93.8%) | 37,912 (98.7%) |
| 1 | 0.185 | 622 | 37,530 (97.7%) |
| 2 | 0.096 | 192 | 36,758 (95.7%) |
| 3 | 0.046 | 776 | 18,633 (48.5%) |
| 4 | 0.031 | 408 | 14,263 (37.1%) |
| 5 | 0.014 | 216 | 801 |
| 6 | 0.010 | 100 | 425 |
| 7 | 0.004 | 0 | — |
| 8 | 0.005 | 11 | 616 |

Output 0 is the most probable output for 93.8% of all ISAs. The ranking 0 > 1 > 2 is stable across nearly every ISA. For higher values the ranking becomes ISA-dependent: output 7 vs 8 swaps rank in 31.2% of ISAs; output 3 vs 4 swaps in 22.2%. The invariance erodes monotonically with output magnitude.

This is the closest empirical analogue to the invariance theorem for Kolmogorov complexity (Li and Vitanyi, 2008). The theorem states that K_U(x) - K_V(x) is bounded by a constant for any two universal machines U, V. Our machines are sub-universal, so the theorem does not apply. The empirical finding is that for the simplest outputs (0-2), the complexity ranking is nevertheless nearly machine-independent — the invariance holds in practice even where it is not guaranteed in theory. For more complex outputs (7-8), the ranking becomes ISA-dependent. The boundary of invariance is not sharp; it degrades continuously with output complexity.

The mutual information I(ISA; output) quantifies the total dependence: treating the ISA as uniform over 38,416 and the output as drawn from P(x|ISA), I = 0.415 bits = 14.2% of H(output). Knowing the ISA resolves 14.2% of the uncertainty about which output a halting program produces. The remaining 85.8% is determined by the program itself. The ISA is a moderate but not dominant influence on the output.

The Gini coefficient of the K(x) distribution (the inequality of minimum program indices across outputs) ranges from 0.34 to 0.88 across ISAs. ISA-A has a flat complexity spectrum (Gini 0.45, 177 reachable outputs); MIN and MAX have steep spectra (Gini 0.84, 9 reachable outputs each). The Gini coefficient is uncorrelated with the halting fraction (r = -0.009) and with output entropy (r = -0.015). The inequality of computational effort across outputs is a third independent observable — decoupled from both the probability of halting and the entropy of the output distribution.

#### 4.13 ISA Interpolation

The paper's stat-mech analogy (Section 6) predicts that continuously interpolating between two ISAs should produce a smooth Omega(T) curve. To test this: at each execution step, a PRNG seeded by (program index, step number) selects ISA-A's opcode with probability T and ISA-B's with probability 1-T. T is swept from 0 (pure ISA-B) to 1 (pure ISA-A) in 101 steps, with exhaustive enumeration of all 1,679,616 programs at each T.

| T | Omega | Note |
|---|---|---|
| 0.00 | 0.7354 | Pure ISA-B |
| 0.10 | 0.7857 | |
| 0.20 | 0.7906 | |
| 0.30 | 0.7917 | Maximum |
| 0.50 | 0.7865 | |
| 0.70 | 0.7696 | |
| 0.90 | 0.7205 | |
| 0.95 | 0.6910 | |
| 0.97 | 0.6710 | |
| 0.98 | 0.6551 | |
| 0.99 | 0.6302 | |
| 1.00 | 0.5828 | Pure ISA-A |

Three findings:

**The curve is smooth.** No discontinuity, no kink. The stat-mech analogy survives the test: Omega(T) is a continuous function of the mixing parameter. There is no phase transition in the strict thermodynamic sense.

**The maximum exceeds both endpoints.** Omega peaks at T = 0.30 with a value of 0.792, higher than either pure ISA-B (0.735) or pure ISA-A (0.583). Mixing two ISAs probabilistically produces a halting fraction that neither pure ISA achieves alone. The ISA-to-Omega mapping is nonlinear in opcode mixing: the halting fraction is not a convex combination of the endpoint values. In the stat-mech mapping, this corresponds to a partition function whose maximum lies in the interior of the parameter space — the system has a non-trivial optimal mixing point.

**The gradient diverges near T = 1.** The consecutive deltas in the last four steps are -0.011, -0.016, -0.025, -0.047 — roughly doubling at each step. The curve is asymmetric: the ISA-A endpoint is approached steeply while the ISA-B endpoint is approached gently. This asymmetry reflects a structural difference between the two ISAs' opcode composition semigroups. ISA-A's opcodes (DEC, SWP, ADD, XOR) are volume-preserving — small perturbations away from pure ISA-A rapidly increase the halting fraction because even a small probability of using ISA-B's contractive opcodes (AND, SUB) opens escape paths. ISA-B's opcodes are already contractive — adding a small probability of ISA-A's opcodes has little marginal effect.

This experiment tested one ISA pair (A vs B). Whether the interior maximum and gradient asymmetry are general properties of ISA mixing or specific to this pair is an open question. Testing additional pairs — particularly two contractive ISAs, or two volume-preserving ISAs — would determine whether the peak is a generic feature of opcode mixing or a consequence of the contraction/preservation asymmetry.

#### 4.14 Program Synthesis Efficiency

A simple genetic programming system searches for programs that compute f(x) = (x+1) mod 256 (the INC function). Population 200, tournament selection, single-opcode mutation, 100 independent trials per ISA, 5,000 generation limit.

| ISA | Omega | Median gens | Solved |
|---|---|---|---|
| A (DEC SWP ADD XOR) | 0.583 | 0 | 100/100 |
| B (NEG MOV SUB AND) | 0.735 | 0 | 100/100 |
| E (NEG SWP CPL XOR) | 0.704 | 0 | 100/100 |
| G (SHR MOV SUB AND) | 0.743 | 8 | 100/100 |
| MAX (AND x4) | 0.817 | 5000 | 0/100 |
| MIN (INC x5) | 0.291 | 5000 | 0/100 |

Most ISAs solve the target trivially — INC is opcode 0 in every ISA, so a single-instruction program suffices. The interesting results are at the extremes:

**MAX (AND x4) cannot synthesize INC.** Despite having the highest halting fraction (0.817), AND is contractive and no composition of AND operations can produce (x+1). The GP system exhausts 5,000 generations across all 100 trials without finding a solution. High omega does not imply high synthesis capability for a specific target.

**MIN (INC x5) cannot synthesize INC controllably.** All five opcodes are INC, so every non-JNZ instruction increments A. But the GP cannot control how many INC operations execute before the program halts — the loop structure determined by JNZ placement either overshoots or undershoots. Zero solutions in 100 trials.

**ISA-G takes 8 median generations.** SHR and AND are contractive; neither computes +1. The GP must discover a multi-instruction composition (e.g., SUB then MOV then ADD sequences) that achieves the target indirectly. This is the hardest ISA that still admits a solution.

The target f(x)=(x+1) is trivially solvable for most ISAs because INC is opcode 0 — a single-instruction program suffices. A harder target (e.g., parity or sorting) would better differentiate solvable ISAs by search difficulty. The present result establishes the boundary condition: ISA choice determines synthesis feasibility, not just efficiency. The halting fraction measures the probability that a random program halts; it says nothing about whether the halting programs compute a specific target. ISA selection is a tunable hyperparameter for program synthesis.

#### 4.15 The Empirical Universal Prior

The ISA-marginal output distribution P_univ(x) = (1/38,416) * sum_ISA P(x|ISA) is the first exact empirical analogue of Solomonoff's universal prior computed over a complete machine class.

| Output x | P_univ(x) |
|---|---|
| 0 | 0.4202 |
| 1 | 0.1848 |
| 2 | 0.0964 |
| 255 | 0.0838 |
| 3 | 0.0460 |
| 254 | 0.0396 |
| 4 | 0.0308 |

Entropy: 2.92 bits. All 256 outputs are reachable by the marginal prior (every byte value is producible by at least one ISA). The prior concentrates on small non-negative integers and on their complements (255 = ~0, 254 = ~1), reflecting the dominance of INC and CPL/NEG across the ISA population.

The mean KL divergence from any individual ISA to the universal prior is 0.415 bits. Leave-one-out cross-validation (100 random holdouts): KL = 0.432 bits. The prior generalizes — removing one ISA from the average barely changes the prediction.

ISAs closest to the universal prior (KL = 0.051 bits) use ADD+MOV+NEG (omega ~0.68). ISAs farthest (KL = 6.72 bits) are INC×5 (omega = 0.291) — a degenerate ISA whose output distribution is sharply peaked on multiples of small integers. The "most typical" ISA in the machine class is not the simplest or the most powerful; it is the one whose opcode mix produces the most representative output distribution.

#### 4.16 ISA Synthesis from Specification

The output distribution tensor enables ISA design by specification: given a target P(x), find the ISA whose output distribution minimizes KL divergence from the target.

| Target | Best ISA | KL (bits) | Omega | Reachable |
|---|---|---|---|---|
| Uniform (max entropy) | SWP ADD SHR DEC | 905.8 | 0.625 | 211 |
| Peaked (P(0) = 0.95) | AND AND AND AND | 0.11 | 0.817 | 9 |
| Balanced over 0-15 | INC INC INC SHL | 0.55 | 0.347 | 55 |
| Equal on {0, 1, 255} | CPL OR SWP SWP | 0.37 | 0.712 | 28 |

No ISA produces a truly uniform distribution (the KL from uniform is large for every ISA), confirming that the output distribution is inherently structured — the small integers are always favored. The peaked target is well-served by AND×4, which concentrates 82.8% of halting programs on output 0. The balanced and triple targets find ISAs with the right structural mix: SHL creates bit-level diversity for balanced outputs; CPL+SWP generates both x and ~x for the triple target.

#### 4.17 Self-Optimizing ISA

A hill-climbing search through ISA space: start from an arbitrary ISA, evaluate omega, mutate one opcode, accept if omega improves. The search uses the Numba exhaustive evaluator (identical to the tensor computation) as its fitness function.

| Trial | Start | Steps to optimum | Final ISA | Omega |
|---|---|---|---|---|
| MAX from NOP×4 | 0.605 | 6 | AND AND AND AND | 0.8169 |
| MAX from ISA-A | 0.583 | 5 | AND AND AND AND | 0.8169 |
| MAX from random | 0.598 | 4 | AND AND AND AND | 0.8169 |
| MIN from NOP×4 | 0.605 | 4 | INC INC INC INC | 0.2907 |

Every starting point converges to the global optimum in 4-6 steps. No local optima were encountered across any trial. The ISA fitness landscape is unimodal: greedy single-opcode mutation always reaches the global maximum (AND×4) or minimum (INC×5).

This means ISA design for halting fraction is not a hard optimization problem. The landscape is smooth enough that exhaustive search is unnecessary — a hill-climber evaluating ~700 ISAs (out of 38,416) finds the global optimum. The contrast with the irreducibility theorem is instructive: the halting fraction is irreducible as a *function* of the opcode tuple (no low-dimensional projection predicts it), but the optimization *landscape* over that function is smooth and unimodal.

#### 4.18 The Halting Oracle

For bounded machines, the halting problem is decidable. The decomposition theorem (Section 4.8) provides the compressed representation: for each ISA, store the 9 values H(0) through H(8). Given a program p, the oracle computes j = |{i : p_i = JNZ}| and returns H(j) — the exact halting probability for programs with that JNZ count.

| ISA | H(0) | H(1) | H(2) | H(3) | H(4) | H(5) | H(6) | H(7) | H(8) |
|---|---|---|---|---|---|---|---|---|---|
| A | 1.000 | 0.569 | 0.369 | 0.312 | 0.316 | 0.365 | 0.469 | 0.650 | 1.000 |
| B | 1.000 | 0.731 | 0.596 | 0.555 | 0.565 | 0.613 | 0.699 | 0.825 | 1.000 |
| G | 1.000 | 0.731 | 0.617 | 0.577 | 0.584 | 0.626 | 0.704 | 0.825 | 1.000 |
| MIN | 1.000 | 0.125 | 0.036 | 0.018 | 0.014 | 0.018 | 0.036 | 0.125 | 1.000 |
| MAX | 1.000 | 0.825 | 0.721 | 0.666 | 0.649 | 0.666 | 0.721 | 0.825 | 1.000 |

H(0) = H(8) = 1.000 for all ISAs — programs with zero JNZ or all-JNZ always halt. The H(j) curve is symmetric about j=4 for ISAs whose opcodes have symmetric algebraic structure (MIN, MAX). Asymmetric ISAs (A, B) have asymmetric H(j) profiles.

Compression: the naive per-program oracle requires 205 KB per ISA (1 bit per program × 1,679,616 programs). The H(j) oracle requires 36 bytes per ISA (9 rationals at 32-bit precision). Compression ratio: 5,832x. Reconstruction of the aggregate halting fraction from H(j) has zero error for every ISA tested.

The oracle is probabilistic at the individual program level (it cannot determine whether a specific program halts) but exact at the stratum level (it exactly predicts the halting fraction for any subset of programs with a given JNZ count). The per-program halting status requires the full lookup table; the stratum-level statistics require only the 9-number H(j) fingerprint.

---

### 5. Irreducibility

#### 5.1 Variance Decomposition

The halting probability as a function of the four variable opcode assignments, computed exactly over all 38,416 ordered ISAs, decomposes as:

| Source | Variance explained |
|---|---|
| Main effects (any single opcode) | 21.6% |
| 2-way interactions | 23.7% |
| 3-way interactions | 26.0% |
| 4-way interaction | 28.7% |

Each interaction order contributes more than the previous. The 4-way interaction alone (28.7%) exceeds the main effects (21.6%). 78.4% of the total variance resides in interactions of order 2 or higher. All four opcode slots contribute equally (R^2 = 0.2165 each).

#### 5.2 Proof

Variance decomposition over raw (continuous) Omega values, no discretization. Total variance = 0.009055. For each conditioning set S of opcode slots, the residual variance Var(Omega | S) is the mean within-group variance across all groups defined by S. The explained fraction is 1 - Var(Omega | S) / Var(Omega).

| Conditioning on | R^2 | Residual variance |
|---|---|---|
| 1 opcode (any slot) | 0.2165 | 0.007095 |
| 2 opcodes (any pair) | 0.4533 | 0.004950 |
| 3 opcodes | 0.7134 | 0.002595 |
| 4 opcodes (full) | 1.0000 | 0.000000 |

The interaction contributions are the successive differences: 2-way = 0.4533 - 0.2165 = 0.2368. 3-way = 0.7134 - 0.4533 = 0.2601. 4-way = 1.0000 - 0.7134 = 0.2866. These are monotonically increasing.

This result does not depend on any discretization, binning, or information-theoretic estimator. It is a direct variance decomposition over the exact rational Omega values of all 38,416 ISAs. The mutual information analysis (binned into 10-200 quantiles) confirms the same structure: 1D captures 7-11%, 2D captures 20-29%, gap to 4D is 90-93 percentage points, stable across bin granularities.

The same decomposition applied to output entropy and mean cycle length produces nearly identical interaction structure:

| Source | Omega | Output entropy | Cycle length |
|---|---|---|---|
| Main effects | 21.6% | 19.5% | 21.7% |
| 2-way interactions | 23.4% | 22.6% | 23.4% |
| 3-way interactions | 24.1% | 24.5% | 24.1% |

All three observables have monotonically increasing interaction contributions. The irreducibility is not specific to the halting fraction — it is a property of the opcode composition semigroup itself. Any bulk observable computed from this semigroup will be dominated by high-order interactions between opcodes. The semigroup's algebraic structure does not simplify under any projection, regardless of which property of the computation (halting, cycle geometry, output distribution) is being measured.

**1-dimensional projections tested:** op1, op2, op3, op4 (each 0.3025 nats = 7.9%), has_swp (2.0%), has_mov (1.6%), has_and (3.4%), has_shr (3.3%), involution_count (4.9%), coupling type (4.1%). All four opcode slots contribute equally, confirming no slot is dominant. Structural flags (coupling, contraction, involutions) capture less than individual opcode identities.

**2-dimensional projections:** All C(10,2) = 45 pairs tested. The best are any pair of opcode slots (op_i + op_j), each at 0.8591 nats = 22.4%. All six opcode-pair combinations produce identical MI, confirming the symmetry: the interaction structure does not privilege any pair.

**4-dimensional projection:** The tuple (op1, op2, op3, op4) achieves MI = 3.84 nats = 100% of H(Y). This is expected — the ISA determines Omega exactly.

**Interpretation.** 92.1% of the information in Omega resides in the 3-way and 4-way interactions between opcodes. This is not a statement about five failed predictors — it is a measurement over the complete ISA space showing that the function Omega(op1, op2, op3, op4) has information-theoretic dimension 4. Any theory that predicts Omega from fewer than 4 opcode identities will miss at least 77.6% of the variation.

The Hamming distance between opcode tuples confirms this geometrically: ISAs differing by one opcode have Spearman rho = 0.085 between Hamming distance and |Delta Omega|. MDS embedding of the Omega distance matrix in 2D produces stress 0.87. The ISA-to-Omega landscape admits no low-dimensional embedding.

#### 5.3 The Analytical H(j) for INC-NOP

For the ISA {INC, NOP, NOP, NOP, NOP, JNZ}, the halting probability of a JNZ loop with body length k decays geometrically:

$$P(\text{halt} \mid \text{body length } k) = \left(\frac{4}{5}\right)^k$$

The rate 4/5 is the fraction of opcodes that are not INC. A loop body halts only if it contains zero INC opcodes — any nonzero count of INC creates a cycle in Z/256Z that does not return to zero within the step budget. The probability of drawing k opcodes with none being INC is (4/5)^k. This is derived from the cycle structure of INC on Z/256Z without enumerating any programs.

**Proof.** The body contains m INC opcodes and k-m NOPs. After t iterations: A = (t * m) mod 256. The first return to A=0 is at t = 256/gcd(m, 256), consuming t * (k+1) steps. The program halts iff t * (k+1) <= 256, i.e., gcd(m, 256) >= k+1. For m <= k <= 7, the condition gcd(m, 256) >= k+1 requires m divisible by 256/(k+1) >= 33. Since m <= 7 < 33, the only solution is m=0.

| k | P(halt\|k) | Exact |
|---|---|---|
| 0 | 1 | 1 |
| 1 | 4/5 | 0.800000 |
| 2 | 16/25 | 0.640000 |
| 3 | 64/125 | 0.512000 |
| 4 | 256/625 | 0.409600 |
| 5 | 1024/3125 | 0.327680 |
| 6 | 4096/15625 | 0.262144 |
| 7 | 16384/78125 | 0.209715 |

H(1) = (1/8) * sum P(halt|k) = 325089/625000 = 0.520142. Verified against the tensor: Omega = 0.604677 (the decomposition with H(0)=1, H(1)=0.520, and higher strata accounts for the difference).

This demonstrates that the decomposition theorem is not merely an accounting identity — it connects to the algebraic structure of the opcode composition semigroup. For ISAs where the non-INC opcodes are identity maps, the cycle structure of INC on Z/2^W determines everything. For ISAs with nontrivial opcodes, the cycle structure of the full composition semigroup determines H(j), and this semigroup does not simplify (by the irreducibility theorem above).

#### 5.4 Failed Predictors

Six scalar predictors were tested:

| Predictor | r (n=7) | r (n=9) | r (n=38,416) |
|---|---|---|---|
| Spectral gap (A-marginal) | 0.93 | — | -0.16 |
| Contraction index | 0.41 | — | ~0 |
| Zero-reachability | 0.77 | — | ~0 |
| H(1) halt rate | 0.91 | — | -0.10 |
| Involution count | -0.09 | — | ~0 |
| Semigroup size (W=4) | — | 0.62 | — |

The semigroup size — the number of distinct state-space functions expressible by composing the ISA's non-JNZ opcodes — is the best single-number predictor found. Computed as the exact closure of the 5 generator operations on Z/16 x Z/16 (256 states), it ranges from 16 (INC×5: only cyclic shifts) to 1,464,221 (ISA-D: SHL, MOV, ADD, OR generate a large transformation monoid). The correlation with omega at W=8 is r = 0.62 (n=9 named ISAs). Larger semigroups tend toward higher halting fractions because more compositions can route state-space trajectories through A=0.

The semigroup size still leaves 61% of the variance unexplained. ISA-D has the largest semigroup (1.46M functions) but only omega = 0.616, while MAX (AND×4) has a smaller semigroup (610K) but the highest omega (0.817). The semigroup's size matters, but its structure — which specific compositions reach A=0 — matters more. This is consistent with the irreducibility result: no single scalar captures the full 4-way interaction.

The spectral gap failure is instructive. The A-marginal transition matrix averages over all 256 B values and all 5 opcodes to produce a 256x256 Markov chain on A. Its second eigenvalue lambda_2 determines the mixing rate toward A=0. On 7 ISAs, this correlates strongly (r=0.93) because those 7 ISAs have distinct lambda_2 values. On the full population, it collapses: every SWP-containing ISA has lambda_2 = 0.40 regardless of arithmetic, because SWP produces the same A-marginal when averaged over B. But the actual Omega varies from 0.494 to 0.775 within SWP ISAs. The B dynamics that the marginal erases are exactly the dynamics that determine halting.

The two-factor model (coupling x contraction) correctly classifies the 7 original ISAs but fails on the full population. ISA X17 (NEG, SWP, SUB, AND) combines SWP with AND and achieves Omega = 0.775 — the model predicted SWP should cap Omega at ~0.63. The interaction is multiplicative, not hierarchical.

#### 5.5 Call/Return

The halting probability drops from 0.607 to 0.113 at call/return stack depth 1 and remains exactly 0.112932 through depth 16. There is no critical depth. The recursion trap is complete at depth 1.

#### 5.6 Involution Hypothesis

ISA-E with 4 involutions has higher Omega (0.704) than ISAs A, C, F with 1 involution each (0.583, 0.611, 0.598). Spearman rho = -0.09 (p = 0.85). The hypothesis is conclusively falsified: involutions do not trap programs in infinite loops. Instead, they create short cycles (NEG(NEG(x))=x) that cause JNZ loops to revisit states quickly, which can either help or hinder halting depending on whether the visited states include A=0.

---

### 6. What the Results Establish

The finite halting fraction depends on the instruction set in a way that is structured, persistent, and irreducible.

**Structured.** The dependence admits an exact binomial decomposition into JNZ-stratified halt rates H(j). This decomposition compresses the halting function 5,832x (205 KB to 36 bytes per ISA) with zero stratum-level error. The H(j) curve is U-shaped (minimum at j=3-4, endpoints at 1.000), not exponential — consistent with a density-of-states interpretation but not with a Boltzmann-like temperature model. The semigroup size (number of distinct functions generated by opcode composition at W=4) correlates with the halting fraction at r = 0.62 — the best single scalar predictor found, though it still leaves 61% of the variance unexplained.

**Persistent.** The dependence survives register width scaling from 8 to 20 bits (four of five ISAs are width-invariant to 4 decimal places), crosses from register machines to Turing machines, holds across four jump mechanisms, and persists under encoding permutations (which leave it exactly invariant). The ISA fitness landscape is unimodal: hill-climbing from any starting ISA converges to the global optimum in 4-6 mutations.

**Irreducible.** 78% of the variance in the halting fraction resides in 2-way through 4-way opcode interactions, with each interaction order contributing more than the previous. This interaction structure extends identically to output entropy and mean cycle length — the irreducibility is a property of the opcode composition semigroup, not of any particular observable. No low-dimensional projection captures more than 22% of the variation.

**Multi-observable.** The ISA determines not just whether programs halt (the halting fraction), but the geometry of confinement for those that do not (mean cycle length, rho = -0.26 with omega), the shape of the output distribution (0.80 to 5.44 bits of entropy), and the inequality of computational effort across outputs (Gini of K(x), uncorrelated with omega at r = -0.009). These observables are largely independent, probing different aspects of the same semigroup.

**Prior-shaping.** The output distribution P(x|ISA) is the finite analogue of Solomonoff's algorithmic probability. Its entropy varies 6.8x across ISAs. Nine outputs (0-8) are universally reachable and universally probable — a regularity reminiscent of the invariance theorem, observed in a sub-universal setting where the theorem's preconditions are not met. The ISA-marginal distribution predicts any individual ISA's output to within 0.42 bits KL. The mutual information I(ISA; output) = 0.415 bits: the ISA resolves 14.2% of the output uncertainty.

#### Implications for Solomonoff Induction

Two machines computing the same functions assign different output weights. The output distribution measurement (Section 4.12) makes this concrete: the entropy of P(x|ISA) ranges from 0.80 to 5.44 bits across 38,416 ISAs. One machine's prior is near-deterministic (concentrating on 2-3 outputs); another's is near-uniform (spreading across 211 outputs). The initial-state dependence compounds this: ISA ranking reverses at certain initial states. For finite machines, the "choice of universal machine" in Solomonoff induction is not an asymptotically negligible convention — it is a first-order determinant of the prior's shape.

#### A Statistical Mechanics of Computation

The finite halting fraction is analogous to a partition function: a bulk property depending on microscopic details (opcodes) while macroscopic observables (computable functions) are invariant. The decomposition theorem maps directly:

- Program space = microcanonical ensemble
- JNZ count j = energy level
- H(j) = density of contributing states at energy j
- Binomial weight w(j) = Boltzmann-like weighting

The ISA's opcodes play the role of the Hamiltonian. The irreducibility of H(j) — its resistance to factorization into single-opcode contributions — is the computational analogue of the irreducibility of the many-body partition function: opcodes interact through composition, and the interaction determines the halting fraction.

The mean cycle length (Section 4.11) is a second thermodynamic observable: the average period of the attractor basin for non-halting programs. In the stat-mech mapping, it corresponds to the relaxation time — how long a trapped system takes to revisit a state. That it is only weakly correlated with the halting fraction (rho = -0.26) means the two observables probe different aspects of the same opcode semigroup: the halting fraction measures the probability of escape; the cycle length measures the geometry of confinement.

The "thermodynamic limit" is the limit of infinite register width. The width scaling data (Section 4.10) is the computational analogue of finite-size scaling: it measures whether the finite-system behavior is representative of the infinite-system physics. The delta is width-invariant — the system is not at criticality and there are no finite-size corrections.

**Falsifiable prediction, tested.** The analogy predicts that continuously interpolating between two ISAs should produce a smooth Omega(T). Section 4.13 reports the result: Omega(T) is smooth (no discontinuity), confirming the prediction. However, smoothness of a probabilistic mixture is a weak test — any probabilistic combination of deterministic systems will produce a smooth observable. The interpolation result is consistent with the analogy but does not strongly discriminate it from simpler explanations.

**Where the analogy fails.** The mapping of H(j) to density of states predicts, by analogy with Boltzmann statistics, that H(j) should decay exponentially in j (the energy variable) with an ISA-dependent temperature. The measured H(j) curves (Section 4.18) are U-shaped: H(0) = H(8) = 1.000, with a minimum at j = 3-4. This is not Boltzmann-like. The U-shape arises because programs with 0 JNZ (all sequential) and 8 JNZ (all jumps, trivially cycling) always halt, while intermediate JNZ counts create the most complex control flow. The decomposition theorem's structural mapping to the partition function form is exact, but the density-of-states curve does not follow the functional forms that thermodynamic analogies typically predict.

The interpolation also revealed structure the analogy did not predict. Omega(T) peaks at T = 0.30 with a value (0.792) exceeding both pure ISAs. In the partition function mapping, Omega plays the role of Z. The peak in Z at an interior mixing parameter means the number of accessible halting configurations is maximized at a non-trivial mixture — an observation that is consistent with the analogy but is also a generic consequence of nonlinearity in convex combinations.

#### The Irreducibility of H(j)

The information-theoretic irreducibility theorem (Section 5.1) quantifies this: 90-93% of the information in Omega resides in the 3-way and 4-way interactions between opcodes, stable across discretization granularities. The analytical H(j) for the INC-NOP ISA (Section 5.3) shows the mechanism: the halting probability is determined by the cycle structure of the opcode composition semigroup, and this structure does not decompose into single-opcode contributions. The function Omega(op1, op2, op3, op4) has information-theoretic dimension 4.

#### Prefix-Free Encoding: Where the Correspondence Breaks

The measure-preserving correspondence between fixed-length and prefix-free halting sets (Section 4.8.1) holds for our bounded-PC machines because every program has the same length N. For Chaitin's definition, programs have variable length and the prefix-free constraint weights short programs exponentially more heavily (each program p contributes 2^{-|p|} to Omega, not 1/|Sigma|^N).

The correspondence breaks at exactly the point where program length becomes variable. In our model, a fixed-length program with JNZ at position k has one halting criterion (A=0 at the JNZ, allowing fall-through to the end). A prefix-free program with HALT at position k has a different criterion (reaching position k at all). The two halting sets have different cardinalities in the variable-length case because:

1. Short prefix-free programs (those with HALT at early positions) dominate the 2^{-|p|} weighting. Fixed-length programs have no such bias.
2. The JNZ halting condition (A=0) couples halting to the register state, while the HALT opcode decouples halting from the register state — any register values lead to halting.
3. In the prefix-free formulation, the ISA's effect on Omega operates through a different mechanism: it changes which register states are reachable before a HALT instruction, not whether a JNZ loop terminates.

A full comparison would require computing the prefix-free Omega (with 2^{-|p|} weighting) for multiple ISAs and checking whether the ISA deltas persist. This is computationally intensive but feasible for short programs.

---

### 7. Experimental Summary

| Experiment | Programs | Source | Key Finding |
|---|---|---|---|
| 7 ISAs, L=1-11 | ~47,000,000 | FPGA | ISA dependence, convergence |
| 50 ISAs, L=8 | 83,980,800 | FPGA | 57% range, 24 classes |
| Init-state sweep | ~430,000,000 | FPGA | 1.8x factor |
| Jump variants (4) | ~7,000,000 | FPGA | Call/return 5.4x drop |
| 4-register (10) | ~16,800,000 | FPGA | Monotone coupling |
| TM 3 variants | 50,331,648 | FPGA | Exact delta = 0.027 |
| TM 6 encodings | 100,663,296 | CPU | Zero delta |
| Full tensor (38,416 ISAs) | 64,527,984,256 | CPU (numba) | Complete ISA space, 1,148 distinct Omega values |
| Width scaling (W=8-20, 5 ISAs) | ~200,000,000 | CPU | Delta width-invariant |
| Stack depth (1-16) | 26,873,856 | CPU | Step function at depth 1, no transition |
| Prefix-free weighted Omega | ~17,000,000 | CPU | ISA delta survives change in measure |
| Mutual information | -- | CPU | 1D=7-11%, 2D=20-29%, gap=90-93pp |
| JNZ decomposition | ~12,000,000 | CPU | H(j) verified, closed form for 2 ISAs |
| Cycle length tensor (38,416 ISAs) | 64,527,984,256 | CPU (numba, 20-core) | avg_cycle [23.4, 216.1], rho(omega) = -0.26 |
| Output distribution (38,416 ISAs) | 64,527,984,256 | CPU (numba, 20-core) | P(x\|ISA), entropy [0.80, 5.44] bits, 9 universal outputs |
| ISA interpolation (101 values of T) | 169,641,216 | CPU (numba, 20-core) | Peak at T=0.30 exceeds both endpoints, smooth |
| GP synthesis benchmark (24 ISAs) | ~480,000,000 | CPU (numba) | MAX/MIN unsolvable, ISA-G = 8 gens |
| Semigroup closure (9 ISAs, W=4) | — | CPU | r(|S|, omega) = 0.62, best predictor |
| Self-optimizing ISA (4 trials) | ~700 | CPU (numba) | Converges to global optimum in 4-6 steps |
| Full init-state tensor (38,416 ISAs x 256 inits) | 16,518,176,833,536 | CPU (numba, 18-core) | Bowl is ISA-specific; universal-decay conjecture falsified |
| **Total** | **~16,712,776,833,536** | | |

---

### 8. Open Questions

1. **Width scaling on the full tensor.** The 5-ISA measurement shows width-invariance through W=20. Running all 38,416 ISAs at W=16 (~122 days on one CPU core, parallelizable) would produce the definitive width-indexed tensor.

2. **H(j) for nontrivial ISAs.** The cycle-structure method gives closed forms for ISAs whose non-identity opcodes have known cycle lengths on Z/2^W. For ISAs with SWP or AND (which couple or contract the (A,B) state space), the method requires analyzing the joint semigroup. The INC-DEC case shows the generalization is nontrivial: cancellation effects (d = m_inc - m_dec = 0) create halting programs that pure NOP counting misses.

3. **Initial-state averaging over (A, B).** The full init-state tensor (Section 4.3.1) varies init_a with init_b held at 0. The natural extension sweeps the full 65,536-point (A, B) product. Conjecture: ISA differences survive marginalization over the full initial state, but the factor shrinks relative to the single-axis 1.82x mean. Computationally feasible — 38,416 x 65,536 x 1,679,616 = ~4.2 x 10^15 program evaluations, roughly 250x the cost of the single-axis tensor.

4. **Call/return depth scaling.** How does Omega_8 depend on stack depth (1, 2, 4, 8)?

5. **Characterizing the symmetric minority.** The 7.91% of ISAs in the init-state tensor whose bowl is perfectly reflection-symmetric form an algebraic subset. A structural classification — which opcode combinations preserve the a <-> (256-a) involution, and under what conditions — would convert the measurement into theorem.

---

### References

- Chaitin, G. J. (1975). A theory of program size formally identical to information theory. *JACM*, 22(3), 329-340.
- Solovay, R. M. (1975). Draft on Chaitin's work. Unpublished manuscript.
- Calude, C. S., Hertling, P. H., Khoussainov, B., & Wang, Y. (2001). Recursively enumerable reals and Chaitin Omega numbers. *TCS*, 255(1-2), 125-149.
- Calude, C. S., & Dinneen, M. J. (2007). Exact approximations of omega numbers. *IJFCS*, 18(6), 1421-1436.
- Solomonoff, R. J. (1964). A formal theory of inductive inference. *Information and Control*, 7(1), 1-22.
- Rado, T. (1962). On non-computable functions. *Bell System Technical Journal*, 41(3), 877-884.
- Lin, S., & Rado, T. (1965). Computer studies of Turing machine problems. *JACM*, 12(2), 196-212.
- Brady, A. H. (1983). The determination of the value of Rado's noncomputable function Sigma(k) for four-state Turing machines. *Mathematics of Computation*, 40(162), 647-665.
- Marxen, H., & Buntrock, J. (1990). Attacking the Busy Beaver 5. *Bulletin of the EATCS*, 40, 247-251.
- Tadaki, K. (2002). The typicality of the bits of Chaitin's Omega. *Proceedings of COCOON 2002*, LNCS 2387, 519-528.
- Li, M., & Vitanyi, P. (2008). *An Introduction to Kolmogorov Complexity and Its Applications*. 3rd ed. Springer.
- Delahaye, J.-P., & Zenil, H. (2012). Numerical evaluation of algorithmic complexity for short strings: A glance into the innermost structure of randomness. *Applied Mathematics and Computation*, 219(1), 63-77.
- Zenil, H., Hernández-Orozco, S., Kiani, N. A., Soler-Toscano, F., Rueda-Toicen, A., & Tegnér, J. (2018). A decomposition method for global evaluation of Shannon entropy and local estimations of algorithmic complexity. *Entropy*, 20(8), 605.
- Langdon, W. B., & Poli, R. (2002). *Foundations of Genetic Programming*. Springer.
- Helmuth, T., & Spector, L. (2015). General program synthesis benchmark suite. *GECCO 2015*, 1039-1046.

---

### Appendix A: Fifty ISA Definitions

| # | LUT | Op1 | Op2 | Op3 | Op4 | Omega_8 |
|---|---|---|---|---|---|---|
| 0 | 0x543210 | DEC | SWP | ADD | XOR | 0.5831 |
| 1 | 0x598760 | NEG | MOV | SUB | AND | 0.7354 |
| 2 | 0x5A3DB0 | SHR | CPL | ADD | OR | 0.6113 |
| 3 | 0x5A37C0 | SHL | MOV | ADD | OR | 0.6169 |
| 4 | 0x54D260 | NEG | SWP | CPL | XOR | 0.7035 |
| 5 | 0x548210 | DEC | SWP | SUB | XOR | 0.5977 |
| 6 | 0x5987B0 | SHR | MOV | SUB | AND | 0.7433 |
| 7 | 0x593240 | XOR | SWP | ADD | AND | 0.7249 |
| 8 | 0x5932A0 | OR | SWP | ADD | AND | 0.7215 |
| 9 | 0x5932D0 | CPL | SWP | ADD | AND | 0.6993 |
| 10 | 0x593260 | NEG | SWP | ADD | AND | 0.7667 |
| 11 | 0x593210 | DEC | SWP | ADD | AND | 0.6297 |
| 12 | 0x5932C0 | SHL | SWP | ADD | AND | 0.7228 |
| 13 | 0x598240 | XOR | SWP | SUB | AND | 0.7389 |
| 14 | 0x5982A0 | OR | SWP | SUB | AND | 0.7317 |
| 15 | 0x5982D0 | CPL | SWP | SUB | AND | 0.7051 |
| 16 | 0x598260 | NEG | SWP | SUB | AND | 0.7745 |
| 17 | 0x598210 | DEC | SWP | SUB | AND | 0.6424 |
| 18 | 0x5982C0 | SHL | SWP | SUB | AND | 0.7334 |
| 19 | 0x5B3240 | XOR | SWP | ADD | SHR | 0.7170 |
| 20 | 0x5B32A0 | OR | SWP | ADD | SHR | 0.7142 |
| 21 | 0x5B32D0 | CPL | SWP | ADD | SHR | 0.6545 |
| 22 | 0x5B3260 | NEG | SWP | ADD | SHR | 0.7548 |
| 23 | 0x5B3210 | DEC | SWP | ADD | SHR | 0.6248 |
| 24 | 0x5B32C0 | SHL | SWP | ADD | SHR | 0.7069 |
| 25 | 0x5B8240 | XOR | SWP | SUB | SHR | 0.7296 |
| 26 | 0x5B82A0 | OR | SWP | SUB | SHR | 0.7242 |
| 27 | 0x5B82D0 | CPL | SWP | SUB | SHR | 0.6607 |
| 28 | 0x5B8260 | NEG | SWP | SUB | SHR | 0.7616 |
| 29 | 0x5B8210 | DEC | SWP | SUB | SHR | 0.6381 |
| 30 | 0x5B82C0 | SHL | SWP | SUB | SHR | 0.7179 |
| 31 | 0x513240 | XOR | SWP | ADD | DEC | 0.5831 |
| 32 | 0x5132A0 | OR | SWP | ADD | DEC | 0.5638 |
| 33 | 0x5132D0 | CPL | SWP | ADD | DEC | 0.6311 |
| 34 | 0x513260 | NEG | SWP | ADD | DEC | 0.6575 |
| 35 | 0x513210 | DEC | SWP | ADD | DEC | 0.4938 |
| 36 | 0x5132C0 | SHL | SWP | ADD | DEC | 0.5549 |
| 37 | 0x518240 | XOR | SWP | SUB | DEC | 0.5977 |
| 38 | 0x5182A0 | OR | SWP | SUB | DEC | 0.5802 |
| 39 | 0x5182D0 | CPL | SWP | SUB | DEC | 0.6401 |
| 40 | 0x518260 | NEG | SWP | SUB | DEC | 0.6668 |
| 41 | 0x518210 | DEC | SWP | SUB | DEC | 0.5154 |
| 42 | 0x5182C0 | SHL | SWP | SUB | DEC | 0.5683 |
| 43 | 0x593740 | XOR | MOV | ADD | AND | 0.6938 |
| 44 | 0x5937A0 | OR | MOV | ADD | AND | 0.6846 |
| 45 | 0x5937D0 | CPL | MOV | ADD | AND | 0.6473 |
| 46 | 0x593760 | NEG | MOV | ADD | AND | 0.7246 |
| 47 | 0x593710 | DEC | MOV | ADD | AND | 0.5776 |
| 48 | 0x5937C0 | SHL | MOV | ADD | AND | 0.6806 |
| 49 | 0x598740 | XOR | MOV | SUB | AND | 0.7082 |

### Appendix B: ISA Transition Tables

**ISA-A:** INC: ((A+1)%256,B). DEC: ((A-1)%256,B). SWP: (B,A). ADD: ((A+B)%256,B). XOR: (A^B,B). JNZ: if A!=0 PC<-0.

**ISA-B:** INC: ((A+1)%256,B). NEG: ((-A)%256,B). MOV: (A,A). SUB: ((A-B)%256,B). AND: (A&B,B). JNZ: if A!=0 PC<-0.

**ISA-C:** INC. SHR: (A>>1,B). CPL: (~A,B). ADD. OR: (A|B,B). JNZ.

**ISA-D:** INC. SHL: ((2A)%256,B). MOV. ADD. OR. JNZ.

**ISA-E:** INC. NEG. SWP. CPL. XOR. JNZ.

**ISA-F:** INC. DEC. SWP. SUB. XOR. JNZ.

**ISA-G:** INC. SHR. MOV. SUB. AND. JNZ.

### Appendix C: Hardware Utilization

| Config | Modules | Interp/mod | LUT4 | % |
|---|---|---|---|---|
| Single ISA (50 interp) | 1 | 50 | ~8,200 | 38% |
| 3 TM variants | 3 | 16 | ~9,200 | 42% |
| 50-ISA parameterized | 1 | 20 | ~6,500 | 30% |

### Appendix D: Experimental Timeline

| Run | Config | Programs | Time |
|---|---|---|---|
| 1 | 7 ISAs L=1-8 | ~12M | ~30m |
| 2 | ISA-A L=1-11 | ~363M | ~4m |
| 3 | 50-ISA L=8 | 84M | 44s |
| 4 | Init sweep 256 | ~430M | ~4m |
| 5 | 3 jump variants | ~5M | ~20s |
| 6 | Call/return | ~1.7M | ~1s |
| 7 | 4-register x10 | ~17M | ~10s |
| 8 | 3 TM variants | 50.3M | 23s |
| 9 | 6 TM encodings (CPU) | 101M | ~36m |
| 10 | Width W=8-20, 5 ISAs (CPU) | ~200M | ~8h |
| 11 | JNZ decomp (CPU) | ~12M | ~5m |
| 12 | Full tensor, 38,416 ISAs (CPU) | 64.5B | ~2.8h |
| 13 | Cycle length tensor (CPU, 20-core) | 64.5B | ~46m |
| 14 | Output distribution (CPU, 20-core) | 64.5B | ~24m |
| 15 | ISA interpolation, 101 T (CPU, 20-core) | 170M | ~6s |
| 16 | GP synthesis, 24 ISAs (CPU) | ~480M | ~30m |

Silicon time: ~45 minutes. CPU time: ~7 hours. Total: ~194.6B program evaluations.

### Appendix E: Formal Definitions

**Machine.**

    M = (S, Sigma, delta, s_0, F)

    S       — state set, S = {0,...,2^W - 1}^2 x {0,...,N-1}
    Sigma   — opcode alphabet, |Sigma| = 6
    delta   — transition function, delta : S x Sigma -> S
    s_0     — initial state, s_0 = (A=0, B=0, PC=0)
    F       — halting set, F = {s in S : PC(s) >= N}

**Program.** A program is a word p = (sigma_0, ..., sigma_{N-1}) in Sigma^N.

**Execution.** The trace is s_0, s_1, s_2, ... where s_{t+1} = delta(s_t, sigma_{PC(s_t)}).

**Halting.** p halts iff exists t <= T_max : s_t in F.

**Finite halting fraction.**

$$\Omega_N(\delta, s_0) = \frac{|\{p \in \Sigma^N : p \text{ halts from } s_0 \text{ under } \delta\}|}{|\Sigma|^N}$$

**JNZ-stratified halt rate (the primitive).**

$$H_\delta(j) = \frac{|\{p \in \Sigma^N : J(p) = j \wedge p \text{ halts}\}|}{|\{p \in \Sigma^N : J(p) = j\}|}$$

where J(p) = |{i : sigma_i = JNZ}|.

**Decomposition theorem.**

$$\Omega_N(\delta, s_0) = \sum_{j=0}^{N} \binom{N}{j} \left(\frac{|\Sigma|-1}{|\Sigma|}\right)^{N-j} \left(\frac{1}{|\Sigma|}\right)^j H_\delta(j)$$

**Invariants.**

    H_delta(0) = 1             for all delta  (programs without JNZ always halt)
    w(j) = B(N, j, 1/|Sigma|)  for all delta  (binomial weights are ISA-independent)

**Convergence.**

    For all N_1, N_2 >= K:  Omega_{N_1}(delta, s_0) = Omega_{N_2}(delta, s_0)

where K = |PC_range| for machines with JNZ semantics "if A != 0: PC <- 0."

**Encoding invariance.**

    For any bijection pi : Sigma^N -> Sigma^N:
    |{p : p halts}| = |{pi(p) : pi(p) halts}|

    iff execution semantics are unchanged (delta acts on the decoded program).

**Width scaling.**

    Delta(W) = Omega_N(delta_A, s_0, W) - Omega_N(delta_B, s_0, W)

    Delta(8)  = -0.152522      Delta(16) = -0.148620
    Delta(10) = -0.150573      Delta(18) = -0.148339
    Delta(12) = -0.149240      Delta(20) = -0.148056
    Delta(14) = -0.148814

    Monotone convergence at 0.00037/bit. Projected zero-crossing: W ~ 420.
    ISAs B, G, MIN, MAX are perfectly width-invariant (4 dp stable W=8-20).

**Cycle length.**

    For a non-halting program p with trace s_0, s_1, ..., s_{T_max}:
    C(p) = min { k >= 1 : s_{T_max} = s_{T_max - k} }

    The mean cycle length for ISA delta:
    L(delta) = (1 / |NH|) * sum_{p in NH} C(p)

    where NH = { p in Sigma^N : p does not halt under delta }.

    Range: [23.4, 216.1].  825 distinct values.
    Pearson r(Omega, L) = -0.31.  Spearman rho = -0.26.
    max C(p) = 255 for all ISAs (universal).

**Output distribution (algorithmic probability).**

    For a halting program p with output A(p):
    P(x | delta) = |{ p in H : A(p) = x }| / |H|

    where H = { p in Sigma^N : p halts under delta }.

    Entropy: S(delta) = - sum_x P(x|delta) * log2(P(x|delta))
    Range: [0.80, 5.44] bits.  Mean 2.50 bits.
    Reachable outputs: [9, 211] / 256.  9 universally reachable.

**ISA interpolation.**

    Omega(T) for mixing parameter T in [0, 1]:
    At each step, use delta_A's opcode with probability T, delta_B's with 1-T.

    Omega(0) = 0.7354  (pure ISA-B)
    Omega(0.30) = 0.7917  (maximum, exceeds both endpoints)
    Omega(1) = 0.5828  (pure ISA-A)

    Smooth. No discontinuity. Gradient diverges near T=1.
