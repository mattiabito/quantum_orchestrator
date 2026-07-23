# Quantum Orchestrator

An open source CLI tool that accepts any quantum circuit built from standard gates, autonomously selects the best available backend across IBM Quantum, AWS Braket and IonQ, executes the job with automatic fallback, and returns fidelity measurements and comparison graphs.

## Motivation

Most quantum computing literature describes backend selection, noise impact, and hybrid fallback strategies conceptually. This project implements and **measures** them, producing real comparative data across providers.

Built as an extension of my BSc thesis in Computer Engineering (University of Perugia, 2025–2026): *"Quantum Computing Perspectives in System Architecture and Cloud/Local Service Balancing"*.

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
git clone https://github.com/mattiabitocchi/quantum-orchestrator
cd quantum-orchestrator
pip install -r requirements.txt
cp .env.example .env  # add your IBM API key
python src/orchestrator.py
```

### Run your own circuit
```bash
python src/orchestrator.py --qasm my_circuit.qasm --strategy accurate --shots 2048
```

### Run built-in benchmarks
```bash
python src/orchestrator.py --circuit bell --strategy responsive
python src/orchestrator.py --circuit ghz --strategy responsive
python src/orchestrator.py --circuit vqe --strategy accurate
```

### Shots efficiency benchmark
Runs Bell and GHZ at increasing shot counts (10 replicas each) on the noisy simulator, to see how fidelity converges as shots increase.
```bash
python src/shots_efficiency.py
```

---

## Results

### Bell state (2 qubits, latest run)

| Backend | Fidelity | Queue | Exec |
|---|---|---|---|
| ideal_simulator | 100.00% | 0s | 0.03s |
| noisy_simulator | ~95–97% | 0s | 0.01s |
| ibm_qpu_ibm_marrakesh | 97.95–98.93% | 10–42s | 2s |
| aws_local_simulator | 100.00% | 0s | 0.03s |
| ionq_simulator | 98.73% | 0s | 0.55s |

### GHZ state (3 qubits, 5 replicas on real QPU)

| Backend | Fidelity | Queue | Exec |
|---|---|---|---|
| ideal_simulator | 100.00% | 0s | 0.03s |
| noisy_simulator | 93.47% ± 0.83% | 0s | 0.01s |
| ibm_qpu (fez/marrakesh) | 94.63% ± 1.70% | 10.6–116.6s | 2s |
| aws_local_simulator | 100.00% | 0s | 0.04s |
| ionq_simulator | 97.72–97.89% ± ~0.5% | 0s | 0.8s |

### VQE H₂ (2 qubits, 5 replicas on real QPU)

| Backend | Fidelity | Energy (Hartree) | Queue | Exec |
|---|---|---|---|---|
| ideal_simulator | 100.00% | -0.7432 | 0s | 0.01s |
| noisy_simulator | 95.29% ± 0.70% | ~-0.73 | 0s | 0.01s |
| ibm_qpu (fez/marrakesh) | 97.30% ± 1.79% | ~-0.72 | 10.6–33.4s | 2s |
| aws_local_simulator | 100.00% | -0.7432 | 0s | 0.04s |
| ionq_simulator | 98.68–98.83% ± ~0.3% | ~-0.73 | 0s | 0.6s |

**Key finding — queue vs execution:** real QPU execution takes 2 seconds across all circuits. Queue time ranges from 10 seconds to 61 minutes on the same machine. Queue/execution ratio: up to 1822:1. This is the empirical demonstration of what the QCaaS literature describes only qualitatively.

**Key finding — backend selection affects fidelity, not just queue time:** on VQE H₂, real-QPU fidelity varies from 95.36% (ibm_fez) to 98.60% (ibm_marrakesh) on the identical circuit — replicated measurements (n=5) show this gap is driven by which machine gets selected, not random noise. Autonomous backend selection measurably affects result quality, not only wait time.

**Caveat — IonQ is a calibrated noise-model simulator, not physical hardware.** The `ionq_simulator` numbers above come from a Braket density-matrix simulator with vendor-published error rates, not a measurement on physical trapped-ion hardware. It is not directly equivalent to the IBM QPU rows, which are real hardware measurements. Replicated data (n=5-10) shows IonQ consistently at or above real IBM QPU fidelity on GHZ, but this reflects the noise model's calibration, not a physical hardware comparison — treat it as a reference point, not a "IonQ beats IBM" claim.

**Caveat — VQE H₂ energy is a Z-basis-only partial estimate.** The exact ground-state energy is -1.1372 Hartree; this benchmark's Z-basis-only measurement captures ~65% of it (~-0.7432 Hartree), missing the off-diagonal XX+YY Hamiltonian terms (~0.394 Hartree), which require additional circuit executions with basis-rotation gates. The fidelity metric (dominant-state measurement) is unaffected by this limitation and reflects genuine circuit execution quality.

---

## Installation

**Requirements:** Python 3.12+, IBM Quantum account (free tier)

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
# Change strategy based on your use case
adapter = select_backend("ibm_qpu", strategy="accurate")
```

---

## Architecture

The orchestrator uses a plugin architecture based on an abstract `BackendAdapter` class. Every provider implements the same interface — the orchestrator never knows which provider it is talking to.

```
backends/
  base.py         — abstract BackendAdapter (is_available, estimated_queue_s, run, name)
  ibm.py          — IBM superconducting: IBMSimulatorAdapter, IBMQPUAdapter, IBMQPUAdapterAdaptive
  aws.py          — AWS Braket: AWSSimulatorAdapter
  ionq.py         — IonQ trapped-ion: IonQSimulatorAdapter (via Braket density matrix)
  braket_utils.py — Qiskit-to-Braket circuit conversion, shared by aws.py and ionq.py
circuits/
  bell.py    — Bell state (2 qubits) — base validation
  ghz.py     — GHZ state (3 qubits) — medium complexity
  vqe_h2.py  — VQE H₂ molecule — real use case
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
- [x] Systematic benchmark across all circuits and backends, including replicated real-QPU measurements

---

## Background

This project empirically validates the architectural claims of the thesis *"Perspectives of Quantum Computing in the Architecture of Information Systems and in the Balancing between Cloud and Local Services"* (Bitocchi, University of Perugia, 2026).

The thesis argued — from a systems engineering perspective — that quantum computing is primarily an orchestration problem: queue management, fallback strategies, backend selection, and observability matter more than raw qubit count. This project builds the orchestrator and measures what the thesis only described.

---

## License

MIT
