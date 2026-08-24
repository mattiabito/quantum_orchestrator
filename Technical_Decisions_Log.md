# Quantum Orchestrator — Technical Decisions Log

**A working record of technical decisions, experimental observations and reasoning.**

> **What this file is, and what it is not.**
> This is a raw working document. I kept it for myself while building Quantum
> Orchestrator, to hold on to the *why* behind each technical choice — not just
> what was done, but what I observed that led there, what I got wrong on the way,
> and what each finding would mean for the write-up. It was never written for an
> audience, and it reads like it: it is long, uneven, and it records dead ends and
> retracted conclusions alongside the things that worked.
>
> It is public because the project's argument depends on it. The article claims
> that a benchmark is only as trustworthy as its account of how it was built; that
> claim is cheap unless the account is available. Several entries below document
> conclusions I published and later had to withdraw, and the reasoning that
> replaced them. Those are the entries most worth reading.
>
> It was written in Italian and translated to English so that anyone who wants to
> follow the reasoning can. Nothing was rewritten in the translation: where an
> entry was wrong and was later corrected, both the original statement and the
> correction are still here, as they were. A handful of statements that later
> became factually stale carry a dated correction note — marked as such — rather
> than being quietly edited.
>
> Entries are chronological. The format is consistent: what we observed, why it
> happens, the decision taken, and what it means for the report.

---

## 29 June 2026 — IBM Quantum setup: from a direct token to Cloud IAM

**What we observed:**
The user's `.env` contained `IBM_API_KEY` and `IBM_INSTANCE`, not the classic
`IBM_QUANTUM_TOKEN` that the older IBM documentation calls for.

**Why it happens:**
IBM changed the authentication system: the new "IBM Quantum Platform" plan
(post-2024) uses Cloud IAM instead of a direct token. This requires
`channel="ibm_cloud"` instead of `channel="ibm_quantum"`, and an `instance`
parameter alongside the token.

**Decision taken:**
Rewrote `select_backend` to use
`QiskitRuntimeService(channel="ibm_cloud", token=IBM_API_KEY, instance=IBM_INSTANCE)`.

**Relevance for the report:**
Worth mentioning in the setup/installation section — IBM's online documentation is
often out of step with the current API, a real obstacle for anyone trying to
replicate the work.

---

## 29 June 2026 — VS Code: working directory and file creation

**What we observed:**
Files created from VS Code did not show up in the project folder when the script
was launched from a terminal (`check_backends.py` not found).

**Why it happens:**
VS Code had been opened without the project folder as its root — files were being
saved into the Windows home directory instead of into `quantum-orchestrator`.

**Decision taken:**
Standard procedure: always open VS Code with `code .` from the project folder, or
via File → Open Folder.

**Relevance for the report:**
None — a personal workflow detail, not a technical or scientific one.

---

## 29 June 2026 — Qiskit Runtime: `job.status()` is a string, not an object

**What we observed:**
```
AttributeError: 'str' object has no attribute 'name'
```
in the polling code, which was doing `status.name == "RUNNING"`.

**Why it happens:**
In `qiskit-ibm-runtime 0.47`, `job.status()` returns a plain string directly
(`"QUEUED"`, `"RUNNING"`, `"DONE"`), not an enum with a `.name` attribute as in
earlier versions of the SDK.

**Decision taken:**
Changed every comparison from `status.name == "X"` to `status == "X"`.

**Relevance for the report:**
Worth mentioning as a technical/troubleshooting note — quantum computing libraries
change their APIs quickly, which is a stability problem for anyone developing on
these platforms.

---

## 29 June 2026 — Qiskit Runtime: the measurement register's name is not fixed

**What we observed:**
```
AttributeError: 'DataBin' object has no attribute 'meas'
```
when trying to read `pub_result.data.meas.get_counts()`.

**Why it happens:**
The name of the measurement register in SamplerV2 results depends on how the
circuit was built — it is not always `meas`. The robust solution is to read the
first available register dynamically with `list(pub_result.data)[0]`.

**Decision taken:**
```python
register = list(pub_result.data)[0]
counts   = dict(getattr(pub_result.data, register).get_counts())
```

**Relevance for the report:**
Minor technical note, useful for anyone replicating the code.

---

## 29 June 2026 — KEY FINDING: `pending_jobs` does not predict the real queue time

**What we observed:**
First run on `ibm_kingston` with **a single pending job**: total time **20+
minutes**, later confirmed at **3645.6 seconds (60 minutes 45 seconds)**.
Subsequent runs on `ibm_fez` and `ibm_marrakesh` with comparable pending-job
counts (1–6): total times of **10–23 seconds**.

**Why it happens:**
IBM does not run a simple FIFO queue. Scheduling depends on internal factors not
exposed through the API: priority, the machine's calibration state at that moment,
maintenance, circuit type. The `pending_jobs` field is necessary but not sufficient
to estimate the real wait.

**Decision taken:**
1. Implemented an **adaptive** fallback based on a proportional threshold (not an
   absolute one): `threshold = QUEUE_MULTIPLIER * estimated_exec_s` instead of a
   fixed value.
2. Implemented an **absolute timeout** as a safety net (`ABSOLUTE_TIMEOUT_S = 1800`,
   30 minutes), independent of the estimate.
3. Implemented an **autonomous backend selector** that always picks the backend
   with the fewest pending jobs among those available, instead of a hardcoded name.

**Relevance for the report — HIGH:**
This is one of the strongest empirical results of the project. It demonstrates that:
- the "pending jobs" metric exposed by the public API is not reliable as a single
  predictor;
- autonomous backend selection (trying the best available machine, not a fixed
  name) has a measurable impact on performance: same request, same day, from 60
  minutes to 10 seconds depending on which machine is chosen;
- it empirically confirms the central argument of the thesis: quantum computing is
  an **architecture/orchestration** problem, not only a hardware one.

---

## 29 June 2026 — Key figure: the execution-to-queue ratio

**What we observed:**
On the job described in the previous entry, IBM's own dashboard reported
"Estimated QR usage: 4s", while the job sat in Pending status for nearly an hour.
Final measurement: **execution time = 2s, queue time = 3645.6s**.
Queue-to-execution ratio: **1822:1**.

> **Correction (21 August 2026):** the original text of this entry attributed this
> measurement to `ibm_marrakesh`. That was a slip: the previous entry, the project
> diary and commit `86ab7ae` all record the run as `ibm_kingston` (Bell state,
> fidelity 96.48%, queue 3645s, execution 2s). Corrected here to `ibm_kingston`.
> Note also that "Estimated QR usage" is IBM's estimate of *quantum runtime*, i.e.
> execution — and at 4s against a measured 2s it was accurate. What no exposed
> metric predicted was the wait.

**Why it happens:**
Direct confirmation that the bottleneck in quantum-computing-as-a-service is not
the quantum computation itself (which is already fast — 2 to 4 seconds) but access
to, and scheduling of, the cloud service.

**Relevance for the report — HIGH:**
A direct quote for the abstract or introduction: *"for every second of quantum
computation, the user waited up to 30 minutes in queue"*. This is the figure that
turns the qualitative argument of the thesis (Chapter 2: "access to a QPU may
depend on queues and variable availability") into a measured number.

---

## 29 June 2026 — Architectural decision: three configurable execution strategies

**What we observed (the user's reasoning):**
With a fixed fallback threshold, jobs that are "only slightly heavier" than
expected get cut off automatically — a risk of excluding legitimate use cases (for
example a 20-minute job that would be perfectly acceptable in a real application,
but is discarded by an over-aggressive threshold).

**Why it is a real problem:**
A single fallback policy cannot simultaneously satisfy: (a) someone who always
wants a fast answer, (b) someone who wants real QPU results at any cost, (c)
someone who can wait but does not want to block indefinitely.

**Decision taken:**
Implemented three explicit, configurable strategies:
- `responsive` — immediate fallback if the estimated queue exceeds the threshold
  (default, for interactive use and testing);
- `accurate` — always waits for the real QPU, never falls back (for research and
  serious benchmarks);
- `adaptive` — waits up to the absolute timeout, then falls back automatically (for
  batch jobs and overnight runs).

**Relevance for the report — HIGH:**
This is the conceptual turning point of the project: from "benchmark tool" to a
genuine orchestrator. Quotable verbatim: the user observed that *"the goal is for
the service to handle as many cases as possible, so that the user is accommodated
in their usage and not cut off because of their particular needs"* — that sentence
is the guiding principle behind the multi-strategy architecture.

---

## 29 June 2026 — Choosing IonQ over Azure Quantum

**What we observed:**
An attempt to integrate Azure Quantum as a third provider failed: the error
`Azure Quantum workspace not fully specified` shows that Azure Quantum **has no
true standalone local simulator** — it always requires a connection to a
configured Azure Cloud workspace, even just to simulate.

**Why it matters:**
Azure as a "local simulator" would have been functionally identical to IBM Aer
(both ideal simulators, 100% fidelity) — no real added value to the comparison,
only setup complexity (account, workspace, billing) with no scientific benefit.

**Decision taken:**
Replaced Azure with **IonQ** (trapped-ion, via the AWS Braket density matrix
simulator), already reachable through the existing AWS SDK, no extra account
needed.

**Technical rationale for the choice:**
IonQ uses a different physical technology from IBM — trapped ions (ytterbium ions
manipulated with lasers) instead of superconducting qubits. This adds an
architecturally different data point, not just another ideal simulator. The IonQ
noise model was implemented with realistic parameters: single-qubit gate ~0.03%
(vs IBM ~0.1%), CNOT ~0.3% (vs IBM ~1%), readout ~0.5% (vs IBM ~2%).

**Relevance for the report — MEDIUM-HIGH:**
It allows a comparison between two physically different hardware paradigms
(superconducting vs trapped-ion), not just between software providers. An explicit
justification to include in the methodology section: "Azure was excluded because
its local simulator requires cloud workspace configuration with no architectural
difference from IBM Aer; IonQ was chosen instead for its distinct physical qubit
technology."

---

## 29 June 2026 — Observation: the IonQ simulator beats the real IBM QPU on fidelity

**What we observed:**
Across several runs, `ionq_simulator` showed systematically higher fidelity
(98.14%–99.41%) than the real IBM QPU (94.34%–98.93%), even though IonQ is "only"
a simulator with a noise model, not physical hardware.

**Why it happens:**
The IonQ noise model as implemented uses optimistic error parameters based on the
vendor's published specifications, which do not necessarily capture every real
noise source (crosstalk, calibration drift, the full spectrum of SPAM errors)
present on real physical hardware.

**Decision taken:**
No code change — the finding is kept and commented on explicitly.

**Relevance for the report — MEDIUM:**
An important point of methodological honesty: it must be stated clearly that the
"IonQ" comparison in this project is a *simulator with a calibrated noise model*,
not real physical hardware — unlike the IBM figure, which is a real hardware
measurement. A direct fidelity-vs-fidelity comparison between the two is not
equivalent; this must be specified in the report to avoid misleading conclusions
("IonQ is better than IBM" would be a claim the collected data does not support).

> **Update 19 July 2026:** real cause identified — not just optimistic vendor
> parameters, but a bug in the noise model (the two-qubit error channel was
> missing). See the entry below. IonQ data to be re-measured.

---

## 29 June 2026 — Validation: circuit complexity (Bell vs GHZ) as a benchmark proxy

**What we observed (the user's question):**
Doubt about whether the Bell state (2 qubits, the simplest validation circuit used
throughout the project) was a sufficient proxy for more complex circuits, or
whether GHZ (3 qubits) also needed to be validated before making architectural
decisions based on Bell alone.

**First attempt (methodologically flawed):**
Shots efficiency tested with **a single run per shot value** — result: chaotic
Bell/GHZ curves, crossing each other with no interpretable pattern across 10
manual repetitions of the whole experiment.

**Cause of the problem:**
The noise model uses `depolarizing_error`, which is intrinsically stochastic —
every call to `backend.run()` resamples the errors randomly. A single measurement
per point cannot distinguish "real convergence" from "noise in a single
observation".

**Methodological correction:**
Rewrote the script with **10 replicas for each shot value**, measuring mean and
standard deviation instead of a single point value.

**Clean result (data validated 29 June 2026):**
```
Bell fidelity (mean): 95.55% → 95.39% → 95.45% → 95.66% → 95.60% → 95.72%  (128→4096 shots)
GHZ fidelity (mean):  92.73% → 93.05% → 92.50% → 92.60% → 92.92% → 93.11%  (128→4096 shots)

Bell std dev: 1.31% → 1.03% → 0.68% → 0.56% → 0.51% → 0.29%
GHZ std dev:  3.05% → 1.77% → 0.97% → 0.74% → 0.55% → 0.53%

Bell-GHZ gap at 4096 shots: 2.61%
```

**Interpretation:**
1. The Bell-GHZ fidelity gap (~2.6%) is **real, stable and consistent** across the
   whole shot range — not noise, but a structural effect of circuit depth (more
   gates = more accumulated error).
2. The true signature of statistical convergence is the **reduction of the standard
   deviation** as shots increase (both circuits more than halve their std dev from
   128 to 4096 shots), not the stability of the mean value (which was already
   relatively stable even at low shot counts).
3. GHZ starts with a std dev almost three times higher than Bell at 128 shots
   (3.05% vs 1.31%) — a more complex circuit has more variance at low shot counts;
   it still converges, but more slowly.
4. **Practical convergence point identified: 1024–2048 shots** — beyond that
   threshold the std dev drops below 0.6% for both circuits, with marginal gains
   past that point.

> **Correction (21 August 2026):** point 4 is slightly optimistic as written. In
> this dataset GHZ is at 0.74% at 1024 shots, i.e. above 0.6%; only from 2048 shots
> is the threshold met by both circuits. A re-run on 21 August put both at 0.40%
> and 0.47% at 2048 shots, and both above 0.6% at 1024. The claim in the README and
> the article has been corrected to "by 2048 shots". Note also that with only 10
> replicas the standard-deviation estimate itself carries roughly 24% relative
> uncertainty, so a threshold crossing at a single shot count should not be read
> too precisely.

**Decision taken:**
- Bell state confirmed as a valid proxy for the *general* baseline noise behaviour
  (readout error, single-qubit gate error) and for statistical convergence analysis.
- Bell state is NOT sufficient on its own to capture the effect of circuit depth —
  GHZ (or more complex circuits such as VQE H₂) must be kept in the benchmark suite
  to measure complexity-related degradation.
- The default of 1024 shots used in all previous runs of the project is confirmed
  as a valid choice, not an arbitrary one — retroactively justified by the
  convergence data.

**Relevance for the report — HIGH:**
An important methodology section. To include: "1024 shots are sufficient for stable
fidelity estimation on circuits up to 3 qubits; beyond that, additional shots
primarily reduce variance rather than shift the mean fidelity. Circuit depth
introduces a measurable and stable fidelity gap (~2.6% between 2-qubit and 3-qubit
entangled states under the same noise model), independent of shot count." Also
worth mentioning is the methodological lesson itself: the importance of multiple
replicas in distinguishing signal from stochastic noise in a probabilistic noise
model — relevant to anyone replicating similar benchmarks.

---

## 29 June 2026 — Strategic decision: one publication (benchmark + orchestrator) instead of two

**What we observed (the user's question):**
Evaluated the option of publishing two distinct articles — one on the benchmark
(for readers who only want to evaluate and compare backends) and one on the
orchestrator proper (for readers who have a circuit to run) — to serve the
project's two user profiles better.

**Why splitting it turned out to be the wrong instinct:**
The two halves are not two subjects, they are one argument in two moves. The
measurements only matter because something acts on them — a queue-to-execution
ratio is a curiosity until a scheduler sizes its patience against it. And the
orchestrator's design is only justified by the measurements: every choice in it
(proportional threshold instead of a fixed cutoff, three strategies instead of one
policy, autonomous selection instead of a hardcoded backend name) is a direct
consequence of a number in the first half. Published separately, the benchmark
would be a table with no "so what", and the tool would be a design with no
evidence. There is also a practical constraint: one project, split across two
articles, mostly reads as the same work told twice.

**Decision taken:**
A single publication structured in two narrative parts: Part 1 (benchmark — "I
measured what the textbooks only describe") and Part 2 (orchestrator — "then I
built a scheduler that acts on those measurements"), with equal weight given to
both. Ruled out: publishing the benchmark half early on its own, which would have
spent the strongest measurements before the argument they exist to support.

**Relevance for the report:**
Defines the narrative structure of the whole final article, and the rule that
follows from it: every engineering decision described in Part 2 must point back to
a measurement in Part 1. If a design choice cannot be traced to one, it does not
belong in the article.

---

## 29 June 2026 — Two explicit use cases for the project (architectural definition)

**What we observed (the user's reasoning):**
A reflection on how to communicate the project's value to two different kinds of
user: someone who only wants to evaluate and compare backends for research purposes
(uses the built-in circuits), and someone who has their own circuit and wants to
run it as well as possible without managing providers, code and fallback by hand.

**Decision taken:**
The architecture is explicitly designed to support both use cases from the start
(the orchestrator already accepts any Qiskit `QuantumCircuit`, not only Bell/GHZ):
- **Use case 1 (benchmarking):** run the built-in circuits, no setup beyond the API
  keys;
- **Use case 2 (custom circuit):** CLI with a QASM file argument, OpenQASM support
  planned for Phase 3.

**Relevance for the report — HIGH:**
Defines the project's value proposition in the README and the article. Not to be
lost: the observation that without this tool, an engineer who wants to run a
circuit on a real QPU has to handle multi-provider authentication, queue
monitoring, timeouts, format conversion and result collection by hand — the project
compresses all of that into a single command line.

---

## 29 June 2026 — Note on managing Claude sessions and persistent memory

**What we observed (the user's question):**
An explicit concern about how to preserve the reasoning and the nuances that emerge
during development sessions, given that Claude has no memory between separate
conversations — the risk being that the *why* behind technical choices is lost by
the time the final report is written.

**Decision taken:**
Created this document (`Technical_Decisions_Log.md`) as a structured external
memory, separate from the progress diary in the project guide (which captures the
*what*, not the *why*). The file is loaded into the Claude project and updated
every relevant session; every new chat working on the project is instructed to read
it and contribute to it.

**Relevance for the report:**
A process meta-decision rather than a technical one — but essential to the quality
of the final report, which depends on how complete this log is.

---

## Notes on using this file

- Every new working session on Quantum Orchestrator should start by reading this
  file.
- When a non-obvious decision, a surprising experimental observation, or an
  architectural choice with non-trivial motivation comes up, a new entry should be
  added following the format: **What we observed** → **Why it happens** →
  **Decision taken** → **Relevance for the report**.
- Decisions that are later discarded should still be kept in the log (not deleted)
  with an explicit note marking them as superseded — the complete decision path,
  dead ends included, has value for the "Methodology" and "Lessons Learned"
  sections of the final report.

---

## 1 July 2026 — VQE H₂: full energy estimation impossible from the Z basis alone

> **⚠️ ENTRY RETRACTED (23 July 2026).** The conclusion below ("the Z basis
> captures only ~65% of the energy, the XX+YY terms worth ~0.394 Hartree are
> missing") is a **misdiagnosis**, discovered by the supervisor's review. The
> plateau at -0.7432 Hartree was not a measurement limit but the exact minimum
> reachable by an ansatz confined to the wrong symmetry sector, on a Hamiltonian
> with wrong coefficients. With the correct Hamiltonian (O'Malley 2016) and a
> Hartree-Fock ansatz the tool reaches -1.1373 Hartree (chemical accuracy). See the
> 23 July entry for the full correction. The original text is kept below so the
> decision path stays traceable.

**What we observed:**
After numerous attempts with different ansätze and parameters, the ideal simulator
always converges to E ≈ -0.74 Hartree instead of -1.1372 Hartree. The empirical
optimizer (a scan over 100 theta values) confirms that -0.7432 Hartree is the
minimum reachable with Z-basis measurements alone.

**Why it happens:**
The H₂ Hamiltonian contains off-diagonal XX and YY terms that contribute ~0.39
Hartree to the total energy. These require measurements in the X and Y bases
(additional circuits with basis rotations). With a single Z-basis circuit it is
physically impossible to obtain the exact energy — this is not a parameter or
ansatz problem, it is a fundamental limit of single-basis measurement.

**Decision taken:**
Kept the VQE benchmark with two separate, honest metrics:
1. Fidelity = fraction of shots in the dominant states (|00⟩ and |11⟩)
2. Z-basis energy = partial estimate (~65% of total energy) with an explicit
   disclaimer in the code and in the output

**Relevance for the report — HIGH:**
A publishable point of methodological honesty. It shows that the orchestrator
executes VQE circuits correctly (fidelity ~95-99% on every backend), but that full
energy estimation requires multi-basis measurement. Statement for the report: "Full
VQE energy estimation requires Z, X and Y basis measurements. This benchmark
implements Z-basis only, capturing ~65% of the Hamiltonian energy. The XX+YY
contribution (~0.394 Hartree) requires additional circuit executions with basis
rotations."

---

## 1 July 2026 — PySCF cannot be installed on Windows without a C compiler

**What we observed:**
`pip install pyscf` fails on Windows with a CMake error: "nmake not found",
"CMAKE_C_COMPILER not set".

**Why it happens:**
PySCF requires compiling C/Fortran code. On Windows this requires Visual Studio
Build Tools (~3GB), not installed in this environment.

**Decision taken:**
Abandoned the PySCF approach. Used exact Hamiltonian coefficients from the
literature (Kandala et al., Nature 549, 2017) with empirical optimization of theta
on the local simulator.

> **Note (23 July 2026):** those coefficients turned out to be mis-transcribed, and
> the attribution wrong — see the 23 July entry. The correct set gives a ground
> eigenvalue of -1.1373 Ha.

**Relevance for the report — LOW:**
A technical note for the requirements section: PySCF requires Linux/Mac or WSL.

---

## 20 July 2026 — `scipy.optimize` blocked by Windows Application Control, isolated from `vqe_h2`

**What we observed:**
`python orchestrator.py --circuit ghz` failed with
`ImportError: DLL load failed while importing pyduccfft` while importing
`scipy.optimize` inside `vqe_h2.py`, even though GHZ does not use scipy in any way.

**Why it happens:**
`orchestrator.py` imported all three circuit modules (bell, ghz, vqe_h2) at the top
of the file, regardless of `--circuit`. `vqe_h2.py` imported `scipy.optimize` at
module level, and that import triggers loading `scipy.fft._duccfft` (a native
component), blocked by a Windows application-control policy (probably Smart App
Control). The traceback stops exactly on this import — not on `backends.ibm`, which
also uses scipy indirectly through `qiskit_ibm_runtime` — consistent with the fact
that Bell/GHZ on the real QPU had already worked on the same machine.

**Decision taken:**
Moved the `circuits.vqe_h2` import from module level into the `if run_vqe:` block in
`orchestrator.py`, with a `try/except ImportError` that disables only the VQE
benchmark (printing a clear error) instead of crashing the whole program. Bell and
GHZ are now completely independent of the VQE dependency chain.

**Relevance for the report — MEDIUM:**
The third Windows environment-fragility problem for this project (after IBM Cloud
IAM auth on 29 June and PySCF on 1 July) — a recurring pattern worth mentioning in
the Requirements/Installation section: Windows needs more care than Linux/Mac for
this tool's scientific dependencies. The fix here is isolation (one broken circuit
does not block the others), not a resolution of the underlying block — running VQE
still requires unblocking scipy on the Windows side (Smart App Control / Windows
Defender Application Control) or reinstalling scipy with a different FFT backend.

---

## 20 July 2026 — Full GHZ benchmark on 5 backends: real impact of the IonQ noise-model fix

**What we observed:**
First GHZ run (3 qubits, 1024 shots) on all five backends after the 19 July fix to
the IonQ noise model:
ideal_simulator 100.00% | noisy_simulator 93.36% | ibm_qpu_ibm_marrakesh (real QPU)
97.66%, queue 10.6s, exec 2s | aws_local_simulator 100.00% | ionq_simulator 98.34%.

**Why it matters:**
With the CNOT error now applied, IonQ (98.34%) stays slightly above the real IBM
QPU (97.66%) — a gap of 0.68 percentage points, much smaller than what was observed
on Bell before the fix (where IonQ reached 99.41% against a real IBM minimum of
94.34%, a gap of up to ~5 points). The fix worked in the expected direction — it
reduced IonQ's artificial advantage — but did not eliminate it entirely: consistent
with the hypothesis already logged on 29 June that the IonQ noise parameters remain
optimistic relative to real physical hardware.

**Decision taken:**
No further code change. Data kept as the first complete GHZ data point across 5
backends (see `results/ghz_comparison.png` and `results/log.jsonl`).

**Relevance for the report — HIGH:**
The first quantitative data confirming the effectiveness of the 19 July fix on a
circuit other than the one used for debugging (GHZ, not Bell) — good evidence that
the correction generalizes. Useful for a "Methodology"/"Validation" section: it
shows the discovery → fix → validation process with real data, not just a
theoretical claim.

> **Correction 20 July 2026:** the point comparison IonQ 98.34% vs QPU 97.66% above
> was based on a single run per backend — see the correction entry further down
> ("A single run is not enough to compare backends"). The IonQ fix stands; the exact
> numerical comparison does not.

---

## 20 July 2026 — Full VQE H₂ benchmark on 5 backends

**What we observed:**
First VQE H₂ run (2 qubits, 1024 shots, optimal theta found by scan: -0.03173 rad)
on all five backends:
ideal_simulator 100.00% (E=-0.7432) | noisy_simulator 96.09% (E=-0.7267) |
ibm_qpu_ibm_marrakesh (real QPU) 99.12% (E=-0.7262), queue 10.6s |
aws_local_simulator 100.00% (E=-0.7432) | ionq_simulator 98.73% (E=-0.7444).

**Decision taken:**
No code change. Data kept as the first complete VQE data point across 5 backends
(see `results/vqe_comparison.png` and `results/log.jsonl`).

**Relevance for the report — HIGH:**
A reference data point (fidelity ~95-99% on every backend, confirming the
qualitative statement already logged on 1 July). The direct comparison with the GHZ
run should be read together with the methodological correction below.

> **Correction 20 July 2026:** the original conclusion of this entry ("the real QPU
> beats IonQ, the opposite direction from GHZ") has been withdrawn — it was based on
> a single run per backend, and the difference is too small to be distinguished from
> sampling noise. See the correction entry below.

> **Note (23 July 2026):** every energy value in this entry was produced with the
> wrong Hamiltonian and the wrong ansatz — see the 23 July entry. They are kept for
> traceability and are not used in any published table.

---

## 20 July 2026 — Methodological correction: a single run is not enough to compare backends

**What we observed:**
The two previous entries (GHZ and VQE) compared IonQ against the real QPU using a
single run per backend, concluding that the direction of the comparison (which has
higher fidelity) depended on the circuit. The user correctly pointed out that the
differences involved (0.4–0.7 percentage points) are small enough to be plain
sampling noise rather than a real effect — exactly the methodological error already
identified and corrected on 29 June for shots efficiency (a single run per point →
premature conclusions).

**Why it happens:**
The same mechanism as on 29 June: the noise models are stochastic, and a single run
at 1024 shots has non-negligible sampling variance on differences of this size. We
had not applied here the same discipline (multiple replicas) already established for
shots efficiency.

**Decision taken:**
Re-ran GHZ and VQE with 10 replicas at 1024 shots on ideal/noisy/AWS/IonQ (the four
simulated backends, runnable without an IBM account):

| Backend | GHZ mean ± std | VQE mean ± std |
|---|---|---|
| noisy_simulator | 93.47% ± 0.83% | 95.29% ± 0.70% |
| aws_local_simulator | 100.00% ± 0.00% | 100.00% ± 0.00% |
| ionq_simulator | 97.72% ± 0.48% | 98.68% ± 0.41% |

Comparing against the single real-QPU values already measured (GHZ 97.66%, VQE
99.12%): on GHZ the QPU (97.66%) falls inside the IonQ distribution (97.72% ±
0.48%) — no significant difference. On VQE the QPU (99.12%) is about one standard
deviation above the IonQ mean (98.68% ± 0.41%) — a weak, non-conclusive indication
of a real difference (and in any case not replicated on the QPU side). **The
conclusion "the direction of the comparison depends on the circuit" is not
supported by the data — it must be withdrawn.**

**Relevance for the report — HIGH:**
A point of methodological honesty to include explicitly: comparing backends
requires replicas for the systematic benchmark too (not just for shots efficiency),
especially when the differences are small. The real QPU remains limited to a single
sample per run (repeating it costs real quota) — this must be stated as such in the
report, and not used for absolute ranking claims without replicas. A statistically
solid IonQ-vs-QPU comparison would require replicas on the real QPU as well (cost:
real queue time multiplied by the number of replicas).

---

## 20 July 2026 — Real-QPU replicas completed (5× GHZ, 5× VQE): IonQ-vs-QPU now statistically supported

**What we observed:**
The user manually ran 5 GHZ replicas and 5 VQE replicas with `--strategy accurate`
(10 real submissions to the IBM QPU). The selector chose different backends run by
run (minimum pending jobs among `ibm_fez`/`ibm_marrakesh`/`ibm_kingston`).

GHZ — QPU (mixed backends, n=5): 94.63% ± 1.70% (values: 97.27, 94.04, 95.31,
93.26, 93.26 — 4 runs on `ibm_fez`, 1 on `ibm_marrakesh`). IonQ (n=5, same user
venv): 97.89% ± 0.60%. QPU queue: 10.6–116.6s (mean 40.6s).

VQE — QPU (mixed backends, n=5): 97.30% ± 1.79% (values: 95.51, 95.21, 98.83,
98.34, 98.63). Of which **`ibm_fez` only (n=2): 95.36% mean** vs **`ibm_marrakesh`
only (n=3): 98.60% mean**. IonQ (n=5): 98.83% ± 0.12%. QPU queue: 10.6–33.4s (mean
23.5s).

> **⚠️ The VQE half of this entry is superseded (23 July 2026, confirmed 21 August
> 2026).** These five VQE runs predate the Hamiltonian/ansatz fix: they measure a
> different circuit, their dominant count is `00`, and their fidelity was computed
> with the old Bell-style formula. They are **not** used in any published table; the
> VQE hardware figure in the README is the two post-fix `ibm_kingston` runs instead.
> The GHZ half of this entry is unaffected and remains the source of the
> backend-selection finding.

**Why it matters:**
1. On GHZ, with real replicas, the gap between IonQ (97.89 ± 0.60%) and the QPU
   (94.63 ± 1.70%) is now real and statistically supported (~1.9 standard
   deviations of the QPU separate the means) — confirming the direction originally
   observed (and then correctly withdrawn for lack of replicas), this time with
   solid evidence.
2. On VQE the picture is subtler: the QPU's variance (±1.79%) is almost entirely
   explained by **which machine was selected**, not by random noise —
   `ibm_marrakesh` (98.60% mean) clearly beats `ibm_fez` (95.36% mean) on the same
   circuit. This is itself an interesting result and consistent with the central
   argument of the thesis: autonomous backend selection has a measurable impact on
   performance, not only on queue time (already demonstrated on 29 June) but on the
   fidelity obtained.
3. IonQ remains the highest and most stable value (small std, 0.12–0.60%) on both
   circuits — consistent with it being a simulator with a fixed noise model, while
   the QPU reflects real hardware variability (calibration, machine selected,
   crosstalk).

**Decision taken:**
No code change. Data kept as the reference measurement for Bell/GHZ/VQE in the
report. Deleted (at the user's request) the temporary scripts and files used for
the replication (`run_replicas.ps1`, `manual_replicas_ghz.txt`,
`manual_replicas_vqe.txt`) — the project code was not touched by this test.

> **Correction (21 August 2026):** deleting those scripts was a mistake, and it cost
> the project its reproducibility for exactly the numbers it advertises. A later
> review found that none of the replicated reference figures could be regenerated
> from the repo. `src/replicas.py` now exists precisely to close that gap: it is the
> committed, documented script behind every n=100 reference row. Rule adopted: a
> number that gets published must have a script in the repo that regenerates it.

**Relevance for the report — HIGH:**
Supersedes the previous entries (single-run, then withdrawn) with solid data from 5
real replicas. To include in the results section: the IonQ-vs-QPU gap on GHZ is
confirmed real (not noise), while on VQE the primary source of variability is the
choice of IBM backend rather than random noise — direct quantitative support for
the thesis argument about autonomous backend selection. Caveat to keep: n=5 is not
the n=10 gold standard already used for shots efficiency, and all the measurements
were collected in the same session (~1 hour) — the calibration state of the IBM
machines at that moment is not necessarily representative of other moments (see 29
June, `ibm_kingston` queue up to 3645s on other occasions).

---

## 22 July 2026 — Bell re-run post-fix: updated data on all 5 backends

**What we observed:**
`--circuit bell --strategy accurate` re-run after the IonQ fix (19 July) and the
other changes of the session: ideal_simulator 100.00% | noisy_simulator 96.58% |
ibm_qpu_ibm_marrakesh 98.54% (queue 21.7s) | aws_local_simulator 100.00% |
ionq_simulator 98.73%.

**Why it matters:**
A single run (n=1), so no strong conclusion about the IonQ-vs-QPU direction from
this isolated data point — a lesson already applied in this session. The IonQ value
(98.73%) does stay inside the range already measured before the fix (98.14–99.41%):
Bell has a single CNOT (like VQE), so the impact of the two-qubit fix is more
contained than on GHZ (two CNOTs) — consistent with what was already observed.

**Decision taken:**
No code change. `results/bell_comparison.png` and `results/log.jsonl` updated with
current data, replacing the 3 July version (pre-fix).

**Relevance for the report — MEDIUM:**
An updated reference data point for the final measurement table. A statistically
solid IonQ-vs-QPU comparison on Bell as well (as done for GHZ/VQE) would require
multiple replicas — not done here; a single run is sufficient only as a post-fix
reference point.

---

## 22 July 2026 — README and project guide: the custom-QASM example command was wrong

**What we observed:**
The example command for "Use case 2" (running a custom QASM circuit) in the README
and the project guide used `--circuit file.qasm`, but the actual CLI flag is
`--qasm` (`--circuit` only accepts `bell`/`ghz`/`vqe`/`all`). `--circuit vqe_h2` in
the README's "Run built-in benchmarks" section was also wrong (the correct value is
`vqe`).

**Why it happens:**
A documentation typo, probably dating from an earlier version of the CLI, never
updated after the final argparse arguments were implemented.

**Decision taken:**
Corrected both commands in README.md and the project guide.

**Relevance for the report — MEDIUM:**
A concrete reproducibility bug: anyone who had followed the README or the guide to
the letter for the project's headline use case ("run your own circuit") would have
received an argparse error. Always check that the commands in a public README have
actually been executed, not just written by hand.

---

## 20 July 2026 — The `scipy.optimize` import in `vqe_h2.py` was never used

**What we observed:**
While investigating the Windows Application Control block (previous entry),
`from scipy.optimize import minimize_scalar` in `vqe_h2.py` was found never to be
called anywhere in the file — `_get_optimal_theta()` uses a brute-force numpy scan
(`np.linspace` + `np.argmin`), not `minimize_scalar`.

**Why it happens:**
A leftover import, probably from an earlier version of the implementation that used
the scipy optimizer, later replaced by the manual scan without removing the import.

**Decision taken:**
Removed the dead import. Verified (with `scipy.optimize` forcibly blocked in a
sandbox) that the VQE circuit is created with the same optimal theta as before,
without touching `scipy.optimize` in any way — VQE now depends only on numpy.

**Relevance for the report — MEDIUM:**
Resolves the Windows Application Control block of the previous entry at the root
instead of merely isolating it, and simplifies installation for anyone replicating
the project (one heavy, Windows-fragile dependency fewer).

---

## 1 July 2026 — Phase 3 complete: the tool's final feature set

**What we built:**
- 3 built-in circuits: Bell (2 qubits), GHZ (3 qubits), VQE H₂ (2 qubits)
- 5 backends: ideal simulator, noisy simulator, real IBM QPU, AWS LocalSimulator,
  IonQ trapped-ion simulator
- 3 strategies: responsive, accurate, adaptive
- Complete CLI: `--circuit`, `--strategy`, `--shots`, `--qasm`
- QASM support: any standard circuit as input
- Structured JSON output (NDJSON)
- Shots efficiency benchmark with statistical analysis (10 replicas/point)
- Autonomous backend selector with adaptive fallback

**Decision taken:**
Tool declared feature-complete for publication. Phase 4 = article, final README,
visibility, applications.

**Relevance for the report — HIGH:**
This is the finished project. Everything after this is communication.

---

## 19 July 2026 — Correction: the IonQ noise model was missing the two-qubit error channel

**What we observed:**
A code review found that `ionq.py` declared a CNOT two-qubit error of ~0.3% in its
docstring ("vs IBM ~1%"), but the `run()` method applied only single-qubit
depolarizing (0.03%) and readout bit-flip (0.5%) — no error channel on the CNOT at
all.

**Why it happens:**
An omission dating back to the first implementation (29 June): the single-qubit and
readout channels were written but never completed with the two-qubit channel
matching the value already declared in the docstring.

**Decision taken:**
Added `braket_circuit.two_qubit_depolarizing(q0, q1, probability=0.003)` on every
CNOT gate in the original circuit (iterating `circuit.data`), applied after the
single-qubit depolarizing and before the readout bit-flip. Verified in an isolated
sandbox that the channel is correctly inserted into the resulting Braket circuit.

**Relevance for the report — HIGH:**
Corrects the observation of 29 June ("the IonQ simulator beats the real IBM QPU on
fidelity"): that entry hypothesized "optimistic vendor parameters" as the cause,
but the real cause (at least in part) was a missing error channel in the code, not
just a choice of parameters. Every IonQ measurement collected so far (README,
project guide, measurement table) was produced WITHOUT this channel and must be
considered obsolete — to be re-measured before publication.

---

## 19 July 2026 — Generic fidelity for custom QASM circuits (Hellinger fidelity)

**What we observed:**
Fidelity for user-loaded QASM circuits (`--qasm`) always used the Bell formula (the
fraction of counts on `|00⟩`/`|11⟩`), which is meaningless for circuits whose ideal
distribution is not two equiprobable dominant states. The same problem affected the
comparison plot: the "ideal count" line always assumed `shots/2` on 2 states.

**Why it happens:**
`run_job()` applies `compute_fidelity` from `bell.py` by default when no explicit
`fidelity_fn` is passed; the custom-QASM branch in `orchestrator.py` did not pass a
specific one.

**Decision taken:**
Implemented `compute_fidelity_generic()` in `orchestrator.py`: Hellinger fidelity
F = (Σ√(pᵢ·qᵢ))² between the observed distribution and the one measured on the
`ideal_simulator` run of the same circuit, used as a reference instead of assumed.
Scope deliberately limited to custom QASM circuits — Bell/GHZ/VQE keep the existing
formulas (already correct for those three cases) so that the historical data
already collected across 5 backends is not invalidated. `graph.py` updated in
parallel: the reference line now reads the actual per-state counts from `log1`
instead of assuming 2 states at `shots/2`, and the Y axis uses dynamic headroom
based on the maximum observed value — generalizing to any distribution without
touching the fidelity values already measured on the built-in circuits.

**Relevance for the report — MEDIUM-HIGH:**
It makes "Use case 2 — run your own circuit" in the README honest for any QASM, not
just for Bell-like circuits. Worth mentioning in the methodology section: "the tool
reports fidelity for arbitrary circuits by measuring the ideal-simulator
distribution directly rather than assuming its shape, and computing Hellinger
fidelity against it." Verified with synthetic numerical tests (self-match = 1.0,
uniform vs concentrated distribution = 0.5, multi-state QASM case = 0.91) and by
generating a plot on a synthetic circuit with 3 dominant states plus 2 leakage
states, without errors. The existing `results/custom_comparison.png` was generated
with the old Bell formula — it must be regenerated with a new `--qasm` run before
publication.

**Intrinsic limitation — to be stated explicitly in the report:**
Generic fidelity depends on being able to run the circuit on the local
`ideal_simulator` as a reference. For large or deep QASM circuits that reference
becomes expensive to compute in its own right (full-statevector classical
simulation, exponential scaling in the number of qubits) — so the method
generalizes the *definition* of fidelity to any circuit, but does not remove the
fundamental limit of classical simulation as the point of comparison. This is not a
new limitation introduced by this fix: Bell/GHZ/VQE already have the same
constraint today (they too run against `ideal_simulator` as a baseline), but it
must be stated explicitly here because use case 2 in the README promises to accept
"any custom QASM circuit" without qualifying this limit. Useful quote for the
article: "fidelity for arbitrary circuits is bounded by the tractability of
classically simulating the same circuit as a noiseless reference — a limitation
shared with any classical-simulation-based benchmark, not specific to this tool."

---

## 22 July 2026 — Pre-publication hardening: absolute paths, encoding, requirements.txt, repo hygiene

**What we observed:**
An end-to-end verification pass, explicitly requested ("check every corner and
nuance before moving on"), found four latent problems that had never surfaced
because they had never been tested under the right conditions: (1) stdout crashed
with `UnicodeEncodeError` on Windows when output was redirected to a file instead of
printed to an interactive console; (2) launching the script from inside `src/`
instead of from the project root silently recreated a duplicate `src/results/`
folder — the same symptom that had been manually cleaned up on 29-30 June without
understanding the cause at the time; (3) `requirements.txt` was a raw `pip freeze`
dump (~150 packages, including the abandoned Azure Quantum SDK and Jupyter tools
never used) and was encoded in UTF-16LE instead of UTF-8; (4) the project guide was
listed in `.gitignore` but was still tracked by git (committed before being added
to the gitignore), so it would have ended up in the public repo despite the
opposite intent.

**Why it happens:**
(1) Windows uses the system codepage (cp1252) for stdout when it is not attached to
an interactive console, and cannot encode the box-drawing characters of circuit
diagrams. (2) Every `results/...` path in `orchestrator.py`, `graph.py` and
`shots_efficiency.py` was relative to the working directory instead of anchored to
the script's location. (3)/(4) both leftovers of PowerShell commands (`pip freeze >`,
a commit made before the gitignore) never revisited afterwards.

**Decision taken:**
(1) `sys.stdout.reconfigure(encoding="utf-8")` / `sys.stderr.reconfigure(...)` at
the top of `orchestrator.py`. (2) Created `src/paths.py` with an absolute
`RESULTS_DIR` anchored to `__file__`, adopted in all three files. (3) Rewrote
`requirements.txt` with only the 7 packages actually imported (verified by grep),
pinned versions, clean UTF-8. (4) `git rm --cached` on the project guide — the file
stays on disk and in `.gitignore`, but leaves future tracking. Also added
`.gitattributes` (`* text=auto`) to normalize CRLF/LF between Windows and Linux/CI
environments, standard for cross-platform public repos.

> **Note (21 August 2026):** `git rm --cached` removes a file from tracking going
> forward, but **not from the repository's history** — the project guide, and this
> file, remain readable from the commits that contained them. That was not
> understood at the time. It is recorded here because it is the kind of thing worth
> knowing before making a repository public.

**Relevance for the report — HIGH:**
All four are real reproducibility bugs that would have hit anyone trying to clone
and run the public repo from scratch on Windows (the realistic target for a tool
that compares quantum backends) — not just cosmetic details. Worth mentioning in
the methodology/limitations section: always test tools under the conditions a real
user will use them in (redirect to file, different working directory, clean
`pip install`), not only under the conditions they were developed in.

---

## 22 July 2026 — Qiskit→Braket conversion: from silent skipping to generic conversion + fail loud

**What we observed:**
`braket_utils.qiskit_to_braket()` (used by AWS and IonQ) converted only 4 gates (h,
x, cx, ry). Any other gate — even trivial ones like S, T, Z, present in practically
every non-Bell circuit — was silently discarded with a single print line, without
interrupting execution. The circuit executed on AWS/IonQ was therefore different
from the one the user loaded, but the generic fidelity (Hellinger, introduced on 19
July) was still computed and displayed as if the comparison were valid. Reproduced
with a direct test: a circuit with h/s/t/z/cx came out, on the Braket side, with
s/t/z silently absent. The IBM path (ideal/noisy simulator via Aer, real QPU via
transpile) does not have this problem — it does not go through this function.

**Why it happens:**
The function had been written deliberately minimal, sufficient only for
Bell/GHZ/VQE H₂ (the only intended use at the start). When support for arbitrary
QASM was added (19 July), the conversion function was not extended accordingly —
the README promised "pass any OpenQASM file" while the real conversion covered a
much smaller subset, with no error signal to the user.

**Decision taken:**
Redesigned the conversion on three levels, rather than merely extending the list:
1. Explicit named gates (h, x, y, z, s, sdg, t, tdg, rx, ry, rz, cx, cz, swap, ccx)
   — mapping 1:1 onto documented Braket API methods (`circ.si()` for S-dagger,
   `circ.ti()` for T-dagger — different names from Qiskit, verified against the AWS
   developer guide).
2. A generic fallback for any other **single-qubit** gate (u, u1, u2, u3, custom
   gates): conversion through its unitary matrix
   (`instruction.operation.to_matrix()` → `braket_circuit.unitary(...)`), safe
   because a single target qubit has no ordering ambiguity.
3. Any unnamed gate on **multiple qubits** (e.g. iSwap, custom multi-qubit gates)
   raises `UnsupportedGateError` instead of being discarded — qubit ordering in a
   generic multi-qubit fallback is the one place where Qiskit and Braket might not
   agree without verification, so it is better to stop with an explicit error than
   to risk silently wrong data.

`orchestrator.py` catches `UnsupportedGateError` on the AWS/IonQ backends of the
custom-QASM path only and skips that backend with an explicit message (the same
treatment already given to an unavailable backend), without interrupting the rest
of the comparison. A related bug was fixed in parallel: a missing or malformed
`--qasm` file caused a silent fallback to running bell+ghz+vqe on all backends
instead of stopping — it now exits immediately with an explicit error.

**Declared limitation — to be made explicit in the article:**
"Any QASM circuit" is true in practice for any circuit made of standard unitary
gates (which covers the vast majority of real and educational cases), but it is not
universal support: multi-qubit gates outside the explicitly named set (e.g. iSwap,
custom 2+ qubit gates) are not converted — the tool stops with an error instead of
producing incorrect data. Verified with a real Braket SDK (1.110.1, not just a
mock `Circuit` class): a circuit with h/sdg/tdg/u3/cz/swap executed correctly on
`aws_local_simulator` and `ionq_simulator`, `si`/`ti` correctly routed for
sdg/tdg, the generic fallback triggered on `u3` with the expected message, and an
unrecognized multi-qubit gate (iSwap) raised `UnsupportedGateError` as intended
instead of being silently dropped.

**Relevance for the report — HIGH:**
This is the concrete case to cite when explaining how much freedom the "bring your
own circuit" feature really offers: it is not a universal conversion (that would
require a dedicated library such as qiskit-braket-provider, ruled out to avoid an
extra dependency close to the deadline), but an explicit conversion for standard
gates plus a safe generic route for any single-qubit gate — with a clear, declared
boundary (not a silent one) for uncommon multi-qubit gates. Useful quote: "the tool
converts arbitrary single-qubit gates generically via their unitary matrix, and
explicitly refuses — rather than silently mishandles — multi-qubit gates outside a
fixed named set, to avoid an unverified qubit-ordering assumption."

---

## 22 July 2026 — Gate-fix follow-ups: IonQ noise extended to cz/swap, ccx declared unmodelled, misleading fidelity print corrected

**What we observed:**
Two minor consequences of today's gate-conversion work. (1) `ionq.py` applied
two-qubit depolarizing only to `cx` gates: now that `cz` and `swap` are converted
correctly, they were being executed without their two-qubit noise — right circuit,
incomplete noise model for those gates. (2) The `ideal_simulator` reference run in
the custom-QASM path printed to the console a fidelity computed with the Bell
formula (e.g. "0.00%", or other meaningless values on 3-qubit circuits) before the
code overwrote it with 1.0 for saving — the saved data was always correct, but the
on-screen output could look like a failure.

**Why it happens:**
(1) The check `if instruction.operation.name == 'cx'` was not updated when `cz` and
`swap` were added to the conversion. (2) `run_job()` prints `result['fidelity']`
immediately after `adapter.run()`, which for `IBMSimulatorAdapter` always computes
`compute_fidelity` (the Bell formula) by default — the override to 1.0 happened
afterwards, in `orchestrator.py`, i.e. after the print.

**Decision taken:**
(1) Extended the check to `('cx', 'cz', 'swap')`. `ccx` (Toffoli, 3 qubits) remains
explicitly NOT modelled — there is no two-qubit noise channel directly applicable
to 3 qubits, and building an arbitrary approximation (e.g. noise on every pair)
would have been an arbitrary and unjustified choice; better to declare it openly
with an on-screen warning (`[IonQ] Warning: ccx (Toffoli) has no two-qubit noise
model applied`) than to invent a number. (2) `fidelity_fn=lambda counts, shots: 1.0`
passed directly to `run_job()` for the reference run, instead of overwriting the
dictionary afterwards — the printed value and the saved value now always agree.

**Relevance for the report — MEDIUM:**
A concrete example of an honest methodological choice instead of a convenient
approximation: for Toffoli we preferred to declare "not modelled" rather than
invent an unvalidated multi-qubit noise model. Useful for the methodology section
as an example of active transparency about the limits of the noise model.

---

## 22 July 2026 — Known and accepted limitations (consolidated reference for the article's Limitations section)

This is not a new bug or a new decision — it is an index, explicitly requested for
the scientific honesty of the report, of every point where the project knowingly
chose a pragmatic approximation instead of a complete solution. Each point refers
back to the original entry for details; here there is only the summary and the
justification, written to be transferable almost directly into the article's
"Limitations" section.

1. **The noise model is not calibrated on the real backend actually selected.**
   `noisy_simulator` uses fixed "typical" parameters (0.1% single-qubit, 1% CNOT, 2%
   readout for IBM; 0.03/0.3/0.5% for IonQ), not the real calibration parameters of
   `ibm_fez` or `ibm_marrakesh` depending on which is chosen on a given run. It is a
   generic noise model used as a point of comparison, not a replica of the specific
   backend measured in the same comparison. Justification: calibrating the model
   dynamically would require querying IBM's calibration APIs on every run (data not
   always available in real time, and in any case information the "generic" noise
   model does not claim to capture) — out of scope for a tool that compares
   *categories* of backend rather than predicting the exact fidelity of a specific
   machine.

2. **The queue/timeout thresholds are chosen constants, not measured ones.**
   `ESTIMATED_EXEC_S = 10` and `ABSOLUTE_TIMEOUT_S = 1800` (`backends/ibm.py`) are
   reasonable but fixed estimates, not derived from an empirical measurement for
   every circuit/shots/backend combination. The three strategies
   (responsive/accurate/adaptive) are logically correct, but their exact threshold
   point is a design parameter, not a calibrated value.

3. **The circuits tested are small and shallow (2-3 qubits, depth 3-5).** Bell, GHZ
   and a minimal VQE H₂ were chosen deliberately to isolate the backend/noise effect
   from the noise of a complex circuit, but this means the results (e.g. the 1822:1
   queue/execution ratio, the IonQ-vs-QPU gap) have not been verified on larger or
   deeper circuits, where per-gate error accumulation could change the picture. To
   be declared as a limit of generalizability, not just as a design choice.

4. **Custom QASM support is for purely unitary circuits + final measurement, not
   for dynamic circuits.** No support for mid-circuit measurement, reset, or
   classically-conditioned gates (`if`) — absent from "base" OpenQASM 2.0 but
   available in some extensions. The tool assumes a "classical" circuit: all gates,
   then all measurements at the end.

5. **References to limitations already documented in detail elsewhere, for
   completeness of the index:** IonQ is a calibrated simulator, not physical
   hardware (29 June); ~~VQE H₂ measures only the Z basis, ~65% of the total energy
   (20 July)~~ **[SUPERSEDED 23 July: this was a misdiagnosis; the tool now measures
   the full H₂ energy to chemical accuracy with a Z+X measurement, -1.1373 Ha — see
   the 23 July entry]**; generic fidelity for QASM requires `ideal_simulator` to be
   classically tractable, so it does not scale to very large circuits (19 July); the
   Braket conversion covers named gates plus a generic single-qubit fallback, while
   uncommon multi-qubit gates raise an explicit error instead of being approximated
   (22 July); the IonQ noise model does not model `ccx` (22 July, above).

**Relevance for the report — HIGH:**
This is the index to start from when writing the article's Limitations section. The
thread common to every point: whenever the project let an approximation stand, it
did so by declaring it explicitly (on screen, in the code, or here) instead of
hiding it — transparency about limits is itself a methodological result of the
project, not just a footnote.

---

## 23 July 2026 — SUPERVISOR'S REVIEW: VQE H₂ physics bug — wrong Hamiltonian + ansatz in the wrong sector, both corrected

**What we observed:**
The supervisor's code review (commit `8d00f05`) raised that the physical claims of
the VQE benchmark did not match the Hamiltonian actually coded. Independent
verification with `numpy.linalg.eigvalsh` on the `HAMILTONIAN_COEFFS` of
`vqe_h2.py`: eigenvalues `[-1.4556, -0.7432, -0.6361, -0.4073]`. **-1.1372 Hartree
(the exact energy of H₂, declared as the benchmark's ground truth) is not an
eigenvalue of that Hamiltonian.** Moreover the ground state of that Hamiltonian
(E = -1.4556) lives in span{|01⟩,|10⟩}, while the ansatz `Ry(θ)→CX` produced only
states in span{|00⟩,|11⟩}, whose reachable minimum is exactly -0.7432 — the
"plateau" we had observed on 1 July and interpreted as a limit of Z-basis
measurement.

**Why it happens:**
Two independent errors compounding.
1. **Wrong Hamiltonian coefficients.** The values in `HAMILTONIAN_COEFFS`
   (attributed to Kandala et al. 2017) were mis-transcribed or mis-assigned: they
   gave a ground state of -1.4556, not -1.1372. They also contained a symmetric
   XX+YY pair, whereas the correct 2-qubit reduced form (parity mapping + Z₂
   reduction) has **a single off-diagonal term X₀X₁**, not XX+YY.
2. **Ansatz in the wrong symmetry sector.** `Ry(θ)|00⟩→CX` stays in
   span{|00⟩,|11⟩}; the true ground state is in the particle-number-1 sector,
   span{|01⟩,|10⟩}. Starting from |00⟩ without a Hartree-Fock reference state, the
   ansatz could not physically reach the true energy, whatever θ.

Consequence: the conclusion of 1 July ("the Z basis captures ~65% of the energy,
the XX+YY terms worth ~0.394 Hartree are missing") **was a misdiagnosis**. The
-0.7432 was not a partial estimate but the *exact and complete* minimum reachable
by that ansatz on that wrong Hamiltonian — measuring in the X/Y basis would have
recovered no missing energy at all.

**What actually works (verified numerically, not trusted from a transcription):**
The canonical set for H₂/STO-3G at R = 0.735 Å:
`II=-1.05237, Z₀=+0.39793, Z₁=-0.39793, Z₀Z₁=-0.01128, X₀X₁=+0.18093` (a single XX
term). Electronic part: ground state -1.8573 Ha. Folding the nuclear repulsion
(E_nuc = 1/R = +0.7199 Ha) into the identity term, `eigvalsh` gives a ground state
of **-1.13729 Ha** = exact (-1.1372) ✓. The ground state lives in span{|01⟩,|10⟩},
as expected.

> **Correction to the attribution (21 August 2026):** this entry, and the code
> comments that followed from it, credited that coefficient set to O'Malley et al.,
> *Phys. Rev. X* 6, 031007 (2016). That is not right. O'Malley's Eq. (1) is
> `H = g₀𝟙 + g₁Z₀ + g₂Z₁ + g₃Z₀Z₁ + g₄Y₀Y₁ + g₅X₀X₁` — a Bravyi-Kitaev reduction
> that carries **both** Y₀Y₁ and X₀X₁. The single-X₀X₁ set used here is the parity
> mapping + Z₂ two-qubit reduction, the standard values reproduced in the Qiskit
> textbook chapter "Simulating Molecules using VQE". O'Malley remains the canonical
> hardware-VQE reference for this molecule, but is not the source of these
> coefficients. Corrected in `vqe_h2.py`, in the test docstring, in the README and
> in the article. The physics is unaffected — the numbers still diagonalize to
> -1.137288 Ha — but citing a paper for something it does not contain is exactly the
> kind of error this entry is about.

Correct ansatz (single-excitation / Givens, particle-number conserving), using only
`x/cx/ry` gates (convertible on Braket): `X(q0) → CX(0,1) → Ry(θ,1) → CX(1,0)`,
starting from the Hartree-Fock state |01⟩ and rotating within the right sector. It
reaches exactly -1.13729 at θ_opt ≈ 2.9185, with zero leakage. The full measurement
chain was verified too: energy reconstructed from measured counts (real Aer, 10⁵
shots) = -1.1375 Ha (within statistical noise), fidelity 1.0, Z basis alone =
-1.0975 Ha (96.5% of the energy), with the X₀X₁ term (X basis, one extra circuit
with H on both qubits) adding the remaining 3.5%.

**Decision taken:**
1. `vqe_h2.py` rewritten: correct coefficients with explicit nuclear repulsion,
   Hartree-Fock + Givens ansatz, `compute_energy_h2(counts_z, counts_x, ...)`
   estimating the full energy from two bases (Z for the diagonal terms, X for
   X₀X₁), `compute_energy_h2_zdiagonal()` to report the Z-only fraction (96.5%),
   and `compute_fidelity_vqe` updated to the new dominant states |01⟩/|10⟩.
2. `_get_optimal_theta()` now performs an analytical energy scan in pure numpy
   (deterministic, instantaneous) instead of the 100 stochastic 8192-shot Aer jobs
   at import time — this also resolves the review's nit about the dead
   `_energy_analytical` code and about depending on scipy/Aer at circuit-creation
   time.
3. `orchestrator.py`: the VQE block runs two circuits (Z basis and X basis) on each
   backend and combines the energy; output updated with the new narrative.
4. A deliberate choice (agreed with the user) of full Z+X measurement instead of Z
   alone: it doubles the VQE jobs on the real QPU but returns the true physical
   energy, measured rather than assumed — consistent with the project's ethic ("I
   measure what the literature describes").

**Consequence for the data:** all historical VQE data (fidelity and energy, in the
README, the guide and the log) was produced with the old ansatz and metrics and must
be **re-measured** with the corrected code — the same treatment as the IonQ fix of
19 July. Only the deterministic ideal/AWS values (fidelity 100%, E = -1.1373) are
already confirmed.

> **Follow-up (21 August 2026):** the simulator side was re-measured; the real-QPU
> side never was beyond two runs. A review found that the article was still
> publishing the pre-fix five-run figure (97.30% ± 1.79%) as its VQE hardware
> number. It has been replaced by the two post-fix `ibm_kingston` runs, with the
> earlier data explicitly excluded rather than averaged in. Lesson: an entry that
> says "to be re-measured" needs someone to check, later, that the re-measurement
> actually happened — the note alone does not close the loop.

**Verification still open:** the AWS/IonQ path (Braket conversion) was not executed
live in the sandbox (non-persistent environment, the braket install too heavy), but
is covered by construction — the gates `x/cx/ry/h` are all in the list supported by
`braket_utils` and were already validated against the real Braket SDK on 22 July.
To be confirmed on the user's first real run. **[UPDATE: the real run immediately
revealed endianness bug #1 — see the entry below.]**

**Relevance for the report — HIGH (and it changes the claim for the better):**
The old narrative "the tool measures only 65% of H₂'s energy" was wrong *and*
weaker than the true one. With the correct setup the tool **measures the H₂
ground-state energy to chemical accuracy (-1.1373 vs -1.1372 Ha)**: the Z basis
captures 96.5%, and one extra circuit in the X basis recovers the remaining X₀X₁
term. It is a much stronger claim, and now a correct one — to be rewritten this way
in the article before the draft. Cross-cutting methodological lesson (to include in
"Methodology"/"Lessons Learned"): a trivial physical sanity check —
`eigvalsh(H)[0] ≈ E_exact` — would have caught the bug immediately; it is now a test
to add to the suite (see point #7 of the review). A "plausible and stable" result
(-0.7432, reproducible on every backend) is no guarantee of correctness: it was
exact, for the wrong Hamiltonian.

---

## 23 July 2026 — Braket↔Qiskit endianness bug (review #1) exposed by the new VQE, corrected

**What we observed:**
First post-fix VQE re-measurement (`--circuit vqe --strategy accurate`, 1024
shots). The energy on the Braket backends was obviously wrong while the fidelity
looked perfect:

| Backend | Dominant counts | Energy (Z+X) | Fidelity |
|---|---|---|---|
| ideal_simulator (Qiskit) | `01` (1008) | -1.1412 ✓ | 100.00% |
| ibm_qpu_ibm_kingston (Qiskit) | `01` (994) | -1.1155 ✓ | 98.24% |
| aws_local_simulator (Braket) | **`10`** (1011) | **+0.4234** ✗ | 100.00% |
| ionq_simulator (Braket) | **`10`** (996) | **+0.4055** ✗ | 99.02% |

The Braket backends reported `10` where Qiskit reported `01`: inverted bits. The
fidelity stayed at 100%/99% because `compute_fidelity_vqe` sums `01`+`10`
(symmetric → immune to the inversion), but the energy depends on ⟨Z₀⟩ and ⟨Z₁⟩,
which swap sign when the qubits are inverted → energy with a flipped sign (+0.45
instead of -1.10 on the Z-diagonal part). Numerical check: the "buggy" Z-diagonal
part computed by hand from the AWS counts gives exactly +0.4545, identical to what
was measured — an exact reproduction of the bug.

**Why it happens:**
Braket and Qiskit use opposite bit-ordering conventions: Braket puts qubit 0 in the
leftmost bit of the counts string, Qiskit in the rightmost. `aws.py`/`ionq.py` built
the keys by joining the bits in Braket's native order without reversing them. This
is exactly bug #1 of the supervisor's review. It had stayed invisible because every
previous benchmark (Bell `00`/`11`, GHZ `000`/`111`, the old VQE `00`/`11`) has
**palindromic** dominant states — reversing the string maps them onto themselves.
The new, correct VQE ansatz has dominant state `01`, **asymmetric**, which made the
bug immediately visible.

**Decision taken:**
Reversed the bitstring in both Braket adapters:
`"".join(str(b) for b in k)[::-1]`. Safe for historical data: Bell/GHZ are
palindromes, so the reversal is a no-op for them. Verified that after the fix the
AWS counts `{'10':1011,'01':13}` become `{'01':1011,'10':13}` (aligned with
Qiskit) and the Z-diagonal part returns to -1.0968, in line with the ideal
(-1.0921, the difference being only shot noise). Two minor facets of point #1
remain unaddressed, relevant only to the custom-QASM path (not to Bell/GHZ/VQE,
which all measure every qubit): (1a) inactive qubits are dropped by Braket → keys
shorter than the reference, needing padding; (1b) the measurement map
(`measure q[i]->c[j]`) is ignored.

**Relevance for the report — HIGH (a double methodological lesson):**
1. **A symmetric metric can hide an asymmetric bug.** Fidelity (symmetric by
   construction on Bell/GHZ/VQE) masked a bit-ordering error for weeks; it surfaced
   only when a *second* metric sensitive to ordering (the energy) was computed on an
   asymmetric state. A direct argument for the Methodology section: use metrics with
   different sensitivities, not just one.
2. **Fixing one bug revealed another.** The VQE fix (dominant state going from the
   palindromic `00`/`11` to the asymmetric `01`) turned the endianness bug from
   latent into observable — a textbook example of why tests must be run on
   asymmetric inputs (exactly the test the review recommends at point #7). To cite
   as a concrete case in the report.

---

## 23 July 2026 — VQE energy convergence vs shots: statistical noise vs systematic bias

**What we observed:**
A new benchmark `vqe_energy_convergence.py` (VQE energy vs shot count, 10
replicas/point, 128→8192 shots) on ideal/noisy/IonQ. Data:

| Shots | ideal E±std (mHa off) | noisy E±std (mHa off) | IonQ E±std (mHa off) |
|---|---|---|---|
| 128  | -1.1470 ± 19.8 mHa (9.8) | -1.0798 ± 14.0 (57.4) | -1.1223 ± 24.7 (14.9) |
| 1024 | -1.1395 ± 6.6 mHa (2.3)  | -1.0845 ± 9.0 (52.7)  | -1.1251 ± 8.9 (12.1) |
| 4096 | **-1.1372 ± 4.2 mHa (0.0)** | -1.0851 ± 4.5 (52.1) | -1.1235 ± 5.5 (13.7) |
| 8192 | -1.1368 ± 2.2 mHa (0.4)  | -1.0857 ± 3.4 (51.5)  | -1.1221 ± 3.3 (15.1) |

Ideal std (128→8192): `[19.8, 8.6, 9.6, 6.6, 4.0, 4.2, 2.2]` mHa — scaling cleanly
as 1/√shots (4× shots → ~½ std).

> **⚠️ Correction (21 August 2026) — the bolded value above does not replicate.**
> The benchmark was re-run on 9 August and again on 21 August. Neither run
> reproduces "-1.1372 exactly at 4096 shots": they give -1.1378 and -1.1396
> respectively, and the ideal simulator's mean wanders around the exact line rather
> than converging monotonically onto it. The stored
> `results/vqe_energy_convergence.json` has carried the 9 August numbers since then,
> while this entry, the README and the article all still quoted the 23 July one — a
> three-way drift nobody noticed for six weeks.
>
> The underlying statistics explain why: with n=10 replicas and a std of ~4 mHa, the
> standard error on the mean is ~1.3 mHa, i.e. the same size as the ±1.6 mHa
> chemical-accuracy band. This experiment design cannot resolve whether the mean is
> inside that band; hitting -1.1372 on the nose once was a coincidence of a single
> realization, not a result.
>
> The claim has been replaced everywhere by one the data does support, measured at a
> fixed condition with a hundred replicas instead: at 1024 shots the ideal simulator
> gives -1.1366 Ha and AWS -1.1377 Ha — 0.6 and 0.5 mHa from exact, with a standard
> error on the mean of 0.8 mHa, comfortably inside the band. Measured the same way,
> the noisy simulator sits at +50.4 mHa and IonQ at +12.9 mHa, i.e. sixty and
> fifteen times the uncertainty on the measurement of the bias itself. Point 2 below
> — the real finding of this entry — is unaffected and if anything comes out
> stronger.

**Why it matters:**
1. **The ideal case converges to the exact value:** the mean enters the
   chemical-accuracy band (±1.6 mHa) from ~2048 shots, and at 4096 shots is exactly
   -1.1372 (0.0 mHa). Experimental confirmation, not just analytical, that the
   ansatz and Hamiltonian are correct. *(See the correction above: the direction is
   right, the specific numbers are not reproducible.)*
2. **Statistical vs systematic:** the two noisy backends do not converge to the
   exact value — they settle on a plateau (noisy ~-1.085, bias ~51 mHa; IonQ
   ~-1.123, bias ~13 mHa). More shots narrow the error bars (statistical noise
   ∝ 1/√shots) but do not move the plateau (systematic bias of the noise model).
   This is the distinction between statistical error (averageable) and systematic
   error (not averageable), made visible on real data.
3. **IonQ is less biased than IBM noisy on the energy** (13 vs 51 mHa): the same
   direction already observed on fidelity (29 June, 20 July: the IonQ noise model is
   optimistic), now quantified on a second, independent metric — a good
   cross-confirmation.
4. **Honesty about the chemical-accuracy claim:** the single-run std never drops
   below 1.6 mHa in the tested range (2.2 mHa even at 8192). So chemical accuracy is
   reached by the *averaged* estimator over replicas, not by a single low-shot run —
   the ansatz reaches it exactly (a property of the circuit), but demonstrating it on
   hardware or a simulator requires either replicas or ~20k+ shots per run.

**Decision taken:**
No change to the tool's code. Added `vqe_energy_convergence.py` as a separate
benchmark (companion to `shots_efficiency.py`). Data saved to
`results/vqe_energy_convergence.{png,json}`.

**Relevance for the report — HIGH:**
A strong, direct figure for the article, joining two threads of the project: the
replica discipline (from 29 June) and the IonQ bias story. Quotable sentence: *"shot
noise averages out as 1/√N and the ideal estimator reaches chemical accuracy, but
the noise-model bias is systematic — additional shots shrink the error bars without
moving the plateau, cleanly separating statistical from systematic error on a
measured observable."* To be paired with the shots-efficiency figure for fidelity:
one shows the convergence of the variance, the other the variance-vs-bias
distinction on the energy.

---

## 23 July 2026 — Minimal test suite (review #7): it caught endianness facet 1a immediately

**What we observed:**
Added the minimal test suite recommended by the review (`tests/`, stdlib
`unittest`, no new dependencies), three files: `test_fidelity.py` (fidelity
functions on synthetic counts), `test_vqe_physics.py` (VQE physics sanity,
including `eigvalsh(H)[0] ≈ E_exact`), `test_braket_endianness.py` (Qiskit↔Braket
round-trip on an **asymmetric** circuit). 18 tests in total. On the first run, the
endianness test on AWS failed with an unexpected error: the circuit "X on qubit 0"
(qubit 1 inactive) → the Braket backends returned `{'1': 2000}`, a **single
character** key instead of `01`. This was not the main facet of the endianness bug
(already fixed by reversing the bitstring), but **facet 1a of the review**: Braket
samples only the qubits that appear in the circuit, so an inactive qubit is omitted
from the counts string.

> **Note (21 August 2026):** the suite has grown since — it is 24 tests today, the
> extra ones covering the measurement-map rejection described in the next paragraph.

**Why it happens:**
Facet 1a had been declared "open, relevant only to custom QASM" in the previous
endianness entry. The test materialized it with a minimal asymmetric circuit
containing an inactive qubit — exactly the scenario a use-case-2 user might submit.
Bell/GHZ/VQE do not trigger it because all their qubits are active.

**Decision taken:**
1. Fixed 1a in `braket_utils.qiskit_to_braket()`: padding with an identity
   (`braket_circuit.i(q)`) on every qubit in `range(num_qubits)` before converting
   the gates, so that every qubit appears in the Braket circuit and is measured. A
   no-op for circuits with all qubits active (Bell/GHZ/VQE) → historical data
   untouched. After the fix all 3 endianness tests pass.
2. Suite runnable with `python -m unittest discover -s tests`. Tests that require
   the full environment (generic fidelity → `qiskit_ibm_runtime`) skip themselves
   instead of failing.
3. Only facet 1b remains open (the measurement map `measure q[i]->c[j]` being
   ignored, relevant only to custom QASM circuits that measure a subset or remap
   the classical bits) — no built-in circuit triggers it; to be addressed if and
   when use case 2 is consolidated.

> **Closure (23 July 2026, later the same night):** facet 1b was closed too — see
> the "residual nits" entry below. `braket_utils.py` now detects measure
> instructions and raises `UnsupportedGateError` if the map is not the identity,
> with regression tests covering it.

**Relevance for the report — HIGH (meta-point):**
A concrete, citable example of the value of tests: the suite found a real bug (1a)
**on the same day it was written**, on an asymmetric input — exactly the class of
input the review identified as necessary, and which the project's symmetric
circuits could not cover. It reinforces the lesson that emerged the same day (a
symmetric metric hides an asymmetric bug): not only metrics, but *tests* too must be
designed around asymmetric cases. The two key tests (`eigvalsh` and the asymmetric
round-trip) are now a permanent regression net against the two high-severity bugs
fixed today.

---

## 23 July 2026 — IonQ noise now interleaved with the gates (review #3): it scales with depth

**What we observed:**
The review (#3) found, by dumping the Braket instruction list, that in `ionq.py`
every noise channel was appended **at the end** of the circuit: single-qubit
depolarizing once per *qubit* (not per gate), and the two-qubit channel after all
the gates. Two consequences: (a) a depth-100 circuit received the same 1-qubit noise
as a depth-1 one; (b) with the noise placed after all the gates, an error occurring
mid-circuit did not propagate through the subsequent gates.

**Why it happens:**
The first implementation (29 June) applied the noise in a block at the end because
that was sufficient for the small initial circuits. Braket applies noise at the
position where it appears in the instruction stream — so appending it at the end
decouples it from circuit depth.

**Decision taken:**
Rewrote the noise application in `ionq.py` using `Circuit.apply_gate_noise(...)`,
the idiomatic Braket method that inserts the channel **immediately after every gate**
of the given type, in the right position in the stream:
- `Depolarizing(0.0003)` on every 1-qubit gate (H, X, Y, Z, S, Si, T, Ti, Rx, Ry,
  Rz) — now once *per gate*, not per qubit;
- `TwoQubitDepolarizing(0.003)` on every entangling gate (CNot, CZ, Swap) — now
  interleaved between the gates, so the error propagates;
- the readout `bit_flip(0.005)` stays at the end (it is genuinely a measurement
  error).

`has_1q`/`has_2q` guards avoid calling `apply_gate_noise` on gate types that are
absent. `ccx` remains unmodelled (no direct two-qubit equivalent on 3 qubits, as on
22 July). Generic single-qubit gates that become a `Unitary` (u/u1/u2/u3 via the
braket_utils fallback) are not covered by the named list — a minor declared gap, not
triggered by any built-in circuit. Error rates unchanged (0.03% / 0.3% / 0.5%): what
changed is the *position* of the noise, not its magnitude.

**Verification (with the real Braket SDK):**
1. Instruction dump: DEPO(0.0003) after every 1q gate, TwoQubitDepolarizing after
   every CNot between the gates, BitFlip at the end — interleaving confirmed.
2. Scaling with depth: `H + Z^n + H` (ideal |0⟩) gives fidelity
   `0.9996 / 0.9977 / 0.9903 / 0.9591` for n = `0 / 10 / 50 / 200` — the noise grows
   with depth, whereas with the old model it would have been constant.
3. GHZ via the real adapter: dominant 000/111, fidelity 0.9822.

**Consequence for the data — IonQ to be re-measured:**
All historical IonQ measurements (Bell/GHZ/VQE in the README, the guide and the
log) use the old model and must be re-measured — the same treatment as the IonQ fix
of 19 July. For GHZ in particular the new model applies 1q depolarizing only where
there is a single-qubit gate (only H on q0), not on q1/q2, which previously received
spurious 1q noise despite having no single-qubit gate — so IonQ fidelity tends to
rise slightly relative to the pre-fix data. It does not affect IBM (Aer and the QPU
do not go through this function) or AWS (an ideal, noiseless simulator).

**Relevance for the report — MEDIUM-HIGH:**
Closes the last substantive point of the review. Relevant now that the tool
advertises arbitrary QASM circuits (of varying depth): the IonQ noise model is now
physically sensible with respect to depth, not just to the count of entangling
gates. A direct link to the question raised repeatedly in this log (29 June, 20
July: "why does IonQ stay optimistic?") — part of the answer was this too, the noise
not scaling with depth. The IonQ benchmark is to be re-run and the numbers updated
before the article.

---

## 23 July 2026 — Simulator reference replicas fixed at n=100

**What we observed:**
The fidelity/energy comparison table (Bell/GHZ/VQE × backend) uses the replica mean
of the simulated backends (noisy Aer, IonQ) as its reference. Simulators run locally
at zero cost, so the standard for these reference means is **n=100 replicas at 1024
shots**. The real QPU stays at n=5: each replica costs queue time plus IBM quota, so
the sample there is deliberately small.

n=100 data (1024 shots), fidelity:

| Circuit | noisy (n=100) | IonQ (n=100) |
|---|---|---|
| Bell | 95.53% ± 0.67% | 98.86% ± 0.31% |
| GHZ  | 93.00% ± 0.86% | 98.15% ± 0.49% |
| VQE  | 95.11% ± 0.71% | 98.67% ± 0.37% |

VQE energy (Z+X, 1024 shots, n=100): noisy -1.0877 ± 0.011 Ha (bias ~50 mHa); IonQ
-1.1236 ± 0.008 Ha (bias ~14 mHa).

> **Update (21 August 2026):** these numbers were correct but not reproducible — the
> loop that produced them was a throwaway script that had been deleted, so nothing in
> the repository could regenerate them. `src/replicas.py` was written to close that
> gap and every row was re-measured with it. The new values agree with the old ones
> within noise, which is the reassuring part: Bell noisy 95.55% ± 0.60%, Bell IonQ
> 98.84% ± 0.32%, GHZ noisy 93.08% ± 0.77%, GHZ IonQ 98.12% ± 0.42%, VQE noisy
> 95.16% ± 0.62%, VQE IonQ 98.70% ± 0.34%; VQE energy noisy -1.0868 ± 0.0091 Ha
> (bias +50.4 mHa), IonQ -1.1243 ± 0.0076 Ha (bias +12.9 mHa). The published tables
> now carry the reproducible set, and every one of them can be regenerated with
> `python src/replicas.py --all`.

**Why it matters — a statistical note not to forget:**
The means agree with the smaller-sample values (differences < noise). **The "± std"
reported is the dispersion between single runs** (a property of the noise at 1024
shots) and **does not shrink as replicas are added** — what shrinks is the *error on
the mean* (std/√n, i.e. how well the mean is pinned down): from ~0.27% to ~0.086%
going from n=10 to n=100. So n=100 does not buy tighter error bars (those stay about
the same), it buys a **solid reference mean**. Careful not to describe it as
"tighter error bars" in the article.

**Decision taken:**
No change to the tool's code. n=100 data generated with the same code and the same
noise models as the repo (reproducible). Article, README and guide tables updated.
The **convergence studies** (shots efficiency and energy vs shots) stay at **n=10
per point**: they are trend sweeps across many shot values, not single-condition
comparisons, and n=10/point is the standard for that kind of plot.

**Relevance for the report — MEDIUM:**
It makes the simulated half of the tables statistically robust at no quota cost; the
real QPU at n=5 should be presented as a motivated choice (rationed hardware), not
as insufficient statistics — which is how the article's Limitations section already
frames it.

---
