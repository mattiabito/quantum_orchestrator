# Quantum Orchestrator

An open source CLI tool that accepts any quantum circuit built from standard gates, autonomously selects the best available backend across IBM Quantum, AWS Braket and IonQ, executes the job with automatic fallback, and returns fidelity measurements and comparison graphs.

## Motivation

Most quantum computing literature describes backend selection, noise impact, and hybrid fallback strategies conceptually. This project implements and **measures** them, producing real comparative data across providers.

Built as an extension of my BSc thesis in Computer Engineering (University of Perugia, 2025–2026): *"Perspectives of Quantum Computing in the Architecture of Information Systems and in the Balancing between Cloud and Local Services"*.

> Quantum computing today is not a physics problem. It is a systems architecture problem.

---

## Features

- **Autonomous backend selection** — picks the best available QPU based on queue time, no manual configuration needed
- **Three execution strategies** — `responsive` (fast fallback), `accurate` (always QPU), `adaptive` (wait with timeout)
- **Multi-provider** — IBM Quantum (superconducting), AWS Braket, IonQ (trapped-ion)
- **Real QPU measurements** — fidelity, queue time, and execution time measured on real IBM hardware
- **Custom circuit support** — pass any OpenQASM file built from standard unitary gates as input
- **Automatic fallback** — if QPU queue exceeds threshold, falls back to calibrated noisy simulator automatically

---

## Supported backends

| Backend | Type | Provider |
|---|---|---|
| `ideal_simulator` | Local Aer, no noise | IBM / Qiskit |
| `noisy_simulator` | Local Aer, IBM noise model | IBM / Qiskit |
| `ibm_qpu_*` | Real superconducting QPU | IBM Quantum |
| `aws_local_simulator` | Local simulator | AWS Braket |
| `ionq_simulator` | Trapped-ion noise model | IonQ via AWS Braket |

---

## Quick start

```bash
git clone https://github.com/mattiabito/quantum_orchestrator
cd quantum_orchestrator
pip install -r requirements.txt
cp .env.example .env  # add your IBM API key
python src/orchestrator.py
```

### Run your own circuit
```bash
python src/orchestrator.py --qasm examples/bell.qasm --strategy accurate --shots 2048
```
`examples/bell.qasm` ships with the repo so the command above runs as-is; swap in
any OpenQASM file built from standard unitary gates.

### Run built-in benchmarks
```bash
python src/orchestrator.py --circuit bell --strategy responsive
python src/orchestrator.py --circuit ghz --strategy responsive
python src/orchestrator.py --circuit vqe --strategy accurate
```

### Reference replicas (the numbers in the Results tables)
Runs one condition — fixed circuit, backend and shot count — many times, and reports
mean and standard deviation. This is the script behind every `n=100` figure below.
```bash
python src/replicas.py --all                                    # every circuit × every local backend
python src/replicas.py --circuit vqe --backend ionq --n 100      # one condition
```

### Shots efficiency benchmark
Runs Bell and GHZ at increasing shot counts (10 replicas each) on the noisy simulator, to see how fidelity converges as shots increase.
```bash
python src/shots_efficiency.py
```

### VQE energy convergence benchmark
Measures the VQE H₂ energy vs shot count (10 replicas each) on the local simulators, showing convergence to the exact energy against the chemical-accuracy band, and the systematic noise-model bias.
```bash
python src/vqe_energy_convergence.py
```

### Tests
A minimal test suite (no extra dependencies, uses the standard-library `unittest`) locks in the fidelity metrics, the VQE physics (`eigvalsh(H)[0] ≈ exact ground energy`), and the Qiskit↔Braket bit-order round-trip on an asymmetric circuit.
```bash
python -m unittest discover -s tests
```

---

## Results

All simulator rows below come from `python src/replicas.py --all` (n=100 replicas
at 1024 shots) and can be regenerated with that one command. The `±` is the spread
between individual runs — a property of the noise model at that shot count — not
the uncertainty on the mean, which is under 0.08% at n=100.

### Bell state (2 qubits)

| Backend | Fidelity | Queue | Exec |
|---|---|---|---|
| ideal_simulator | 100.00% | 0s | 0.03s |
| noisy_simulator | 95.55% ± 0.60% (n=100) | 0s | 0.01s |
| ibm_qpu_ibm_marrakesh | 97.95–98.93% | 11–42s | 2s |
| ibm_qpu_ibm_fez | 94.53–95.41% | 10–11s | 2s |
| ibm_qpu_ibm_kingston | 96.48% (n=1) | 3645s | 2s |
| aws_local_simulator | 100.00% | 0s | 0.03s |
| ionq_simulator | 98.84% ± 0.32% (n=100) | 0s | 0.5s |

The three IBM rows are the same circuit on the same afternoon, routed by the
scheduler to whichever machine had the shortest queue — see the backend-selection
finding below.

### GHZ state (3 qubits, 5 replicas on real QPU)

| Backend | Fidelity | Queue | Exec |
|---|---|---|---|
| ideal_simulator | 100.00% | 0s | 0.03s |
| noisy_simulator | 93.08% ± 0.77% (n=100) | 0s | 0.01s |
| ibm_qpu (fez/marrakesh) | 94.63% ± 1.70% (n=5) | 10.6–116.6s | 2s |
| aws_local_simulator | 100.00% | 0s | 0.04s |
| ionq_simulator | 98.12% ± 0.42% (n=100) | 0s | 0.8s |

### VQE H₂ (2 qubits — full ground-state energy, Z + X basis)

Energy from n=100 replicas at 1024 shots for the local simulators. The real-QPU
row is the two hardware runs taken *after* the Hamiltonian/ansatz fix; earlier VQE
hardware data used the wrong ansatz and is excluded, not averaged in. Bias =
offset from the exact energy.

| Backend | Fidelity | Energy (Hartree) | Queue | Exec |
|---|---|---|---|---|
| ideal_simulator | 100.00% | -1.1366 ± 0.0077 (bias +0.6 mHa) | 0s | 0.01s |
| noisy_simulator | 95.16% ± 0.62% (n=100) | -1.0868 ± 0.0091 (bias +50.4 mHa) | 0s | 0.01s |
| ibm_qpu_ibm_kingston | 98.24%, 98.34% (n=2) | -1.1155, -1.1197 (n=2) | 11.1s, 11.3s | 2s |
| aws_local_simulator | 100.00% | -1.1377 ± 0.0083 (bias -0.5 mHa) | 0s | 0.04s |
| ionq_simulator | 98.70% ± 0.34% (n=100) | -1.1243 ± 0.0076 (bias +12.9 mHa) | 0s | 0.4s |

The noiseless backends (ideal, AWS) land within chemical accuracy of the exact H₂
ground state (-1.1372 Hartree, full CI in STO-3G): 0.6 and 0.5 mHa away, with a
standard error on the mean of 0.8 mHa — inside the ±1.6 mHa band. The noisy and
IonQ backends sit at a *systematic* offset (their noise-model bias) fifteen to
sixty times larger than that standard error: more shots shrink the spread but do
not move the offset, cleanly separating statistical shot noise (∝ 1/√shots) from
systematic noise-model bias. IonQ's bias (~13 mHa) is smaller than IBM's
noisy-model bias (~50 mHa), consistent with IonQ's more optimistic noise model.
See `results/vqe_energy_convergence.png`.

Note that a *single* run never reaches chemical accuracy at any shot count tested:
the per-run spread stays above 1.6 mHa even at 8192 shots. The ansatz reaches the
exact energy exactly; demonstrating that it does takes replicas.

**Key finding — queue vs execution:** real QPU execution is stable at 2 seconds — 15 of the 18 logged hardware runs report exactly 2.0s, the other three a sub-second usage figure. Queue time on the same machine ranges from 10 seconds to 61 minutes. Queue/execution ratio: up to 1822:1. This is the empirical demonstration of what the QCaaS literature describes only qualitatively.

**Key finding — backend selection affects fidelity, not just queue time:** on GHZ, five real-QPU runs from one session split 4-to-1 across machines — `ibm_fez` (n=4): 94.04%, 95.31%, 93.26%, 93.26% (mean 93.97%); `ibm_marrakesh` (n=1): 97.27%. The single `ibm_marrakesh` run isn't a distribution, but it sits clearly above the whole `ibm_fez` cluster, consistent with the same machine's higher fidelity on Bell (97.95–98.93% across its own separate replicas, see above). Autonomous backend selection measurably affects result quality, not only wait time — pinning the gap down to a precise number would need more `ibm_marrakesh` replicas than this session produced.

**Caveat — IonQ is a calibrated noise-model simulator, not physical hardware.** The `ionq_simulator` numbers above come from a Braket density-matrix simulator with vendor-published error rates, not a measurement on physical trapped-ion hardware. It is not directly equivalent to the IBM QPU rows, which are real hardware measurements. Replicated data (n=5-10) shows IonQ consistently at or above real IBM QPU fidelity on GHZ, but this reflects the noise model's calibration, not a physical hardware comparison — treat it as a reference point, not a "IonQ beats IBM" claim.

> **Note:** the IonQ noise model was updated so that gate noise is interleaved with the circuit (scaling with depth) rather than applied at the end. The IonQ numbers in the tables above have been re-measured (n=100) under this corrected model; IBM and AWS numbers are unaffected. GHZ fidelity rose slightly (≈97.8% → 98.1%) because the old model over-applied single-qubit noise to qubits that carry no single-qubit gate.

**VQE H₂ — full ground-state energy to chemical accuracy.** The benchmark uses the 2-qubit reduced H₂ Hamiltonian (parity mapping + Z2 reduction at R = 0.735 Å — the standard coefficient set reproduced in the Qiskit textbook; O'Malley et al., *Phys. Rev. X* 6, 031007, 2016 is the canonical hardware-VQE reference for this molecule but uses a different, Bravyi-Kitaev reduction) and a particle-conserving single-excitation ansatz that starts from the Hartree-Fock reference state. Energy is measured in two bases: the Z basis gives the diagonal terms (~96.5% of the energy, ~-1.0973 Hartree) and one X-basis circuit gives the single off-diagonal X₀X₁ term (the remaining ~3.5%). Summing both recovers -1.1373 Hartree on the ideal simulator, matching the exact ground state (-1.1372 Hartree) to chemical accuracy. The fidelity metric measures leakage out of the dominant |01⟩/|10⟩ states and reflects circuit-execution quality on each backend.

---

## Installation

**Requirements:** Python 3.11+ (developed on 3.12, test suite verified on 3.11), IBM Quantum account (free tier — only needed for the real-QPU backend; everything else runs locally)

```bash
pip install -r requirements.txt
```

**IBM API key:** get it at https://quantum.ibm.com → Account → API Token

**.env file:**
```
IBM_API_KEY=your_token_here
IBM_INSTANCE=your_instance_name
```

---

## Execution strategies

| Strategy | Behavior | Best for |
|---|---|---|
| `responsive` | Fallback immediately if estimated queue exceeds threshold | Interactive apps, fast testing |
| `accurate` | Always wait for real QPU, never fallback | Research, benchmark runs |
| `adaptive` | Wait up to 30 minutes, then fallback to noisy simulator | Batch jobs, overnight runs |

```python
# Change strategy based on your use case. Pass the circuit so the fallback
# threshold is computed from it instead of falling back to a fixed constant
# (see backends/ibm.py: estimate_exec_s).
adapter = select_backend("ibm_qpu", strategy="accurate", circuit=my_circuit)
```

---

## Architecture

The orchestrator uses a plugin architecture based on an abstract `BackendAdapter` class. Every provider implements the same interface — the orchestrator never knows which provider it is talking to.

```
src/
  orchestrator.py            — CLI entry point: backend selection, strategies, logging
  graph.py                   — comparison plots
  replicas.py                — fixed-condition replica benchmark (the n=100 reference numbers)
  shots_efficiency.py        — fidelity vs shot-count benchmark
  vqe_energy_convergence.py  — VQE energy vs shot-count benchmark
  paths.py                   — output paths anchored to the source file, not the cwd
  backends/
    __init__.py
    base.py          — abstract BackendAdapter (is_available, estimated_queue_s, run, name)
    ibm.py           — IBM superconducting: IBMSimulatorAdapter, IBMQPUAdapter, IBMQPUAdapterAdaptive
    aws.py           — AWS Braket: AWSSimulatorAdapter
    ionq.py          — IonQ trapped-ion: IonQSimulatorAdapter (via Braket density matrix)
    braket_utils.py  — Qiskit-to-Braket circuit conversion, shared by aws.py and ionq.py
  circuits/
    __init__.py
    bell.py    — Bell state (2 qubits) — base validation
    ghz.py     — GHZ state (3 qubits) — medium complexity
    vqe_h2.py  — VQE H₂ molecule — real use case
tests/     — regression suite (fidelity metrics, VQE physics, Qiskit↔Braket round-trip)
examples/  — bell.qasm, a ready-to-run circuit for the --qasm path
results/   — generated figures and NDJSON logs (only the published figures are tracked)
```

**Adding a new provider** is straightforward — implement `BackendAdapter` and register it in `orchestrator.py`. No other changes needed.

---

## Use cases

### 1. Backend benchmarking
Run the built-in circuits and get a comparative analysis across all providers. Useful for researchers and developers who want to know which backend best fits their problem before committing to a provider.

### 2. Run your own circuit
Pass any `.qasm` file and let the orchestrator handle provider selection, queue management, fallback, and result logging automatically. Useful for engineers who want to execute quantum algorithms without managing provider-specific SDKs. Named gates (h, x, y, z, s, sdg, t, tdg, rx, ry, rz, cx, cz, swap, ccx) and any other single-qubit gate convert automatically; unrecognized multi-qubit gates are reported explicitly rather than silently mishandled.

---

## Roadmap

- [x] IBM QPU real measurements with queue/execution time separation
- [x] Multi-provider plugin architecture (IBM, AWS, IonQ)
- [x] Autonomous backend selection (lowest queue, operational check)
- [x] Three execution strategies (responsive, accurate, adaptive)
- [x] 5-backend comparison graph with fidelity and exec time
- [x] GHZ and VQE H₂ circuits
- [x] CLI with --circuit, --strategy, --shots, --qasm flags
- [x] OpenQASM file input support
- [x] JSON structured output (NDJSON)
- [x] Shots efficiency benchmark (10 replicas per shot count)
- [x] Reference replica benchmark (`replicas.py`) — every table number reproducible with one command
- [x] Systematic benchmark across all circuits and backends, including replicated real-QPU measurements
- [x] VQE H₂ energy to chemical accuracy (Z + X basis) with energy-vs-shots convergence analysis
- [x] Minimal regression test suite (fidelity, VQE physics, Qiskit↔Braket bit-order)

---

## Decision log

`Technical_Decisions_Log.md` is the working record kept while building this — 37
dated entries covering why each technical choice was made, what was observed that
led there, and what had to be withdrawn afterwards. It is a raw document, not a
polished one, and it is in the repo because the honest half of this project lives
there: the mis-transcribed Hamiltonian, the endianness bug a symmetric metric could
not see, the conclusions published and then retracted, and the reasoning that
replaced them. If you want to know why something in `src/` is the way it is, that
file is the answer.

---

## Background

This project empirically validates the architectural claims of the thesis *"Perspectives of Quantum Computing in the Architecture of Information Systems and in the Balancing between Cloud and Local Services"* (Bitocchi, University of Perugia, 2026).

The thesis argued — from a systems engineering perspective — that quantum computing is primarily an orchestration problem: queue management, fallback strategies, backend selection, and observability matter more than raw qubit count. This project builds the orchestrator and measures what the thesis only described.

---

## License

MIT
