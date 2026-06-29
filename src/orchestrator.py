from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
import time
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

IBM_API_KEY  = os.getenv("IBM_API_KEY")
IBM_INSTANCE = os.getenv("IBM_INSTANCE")

# Fallback if estimated queue > QUEUE_MULTIPLIER * estimated execution time
QUEUE_MULTIPLIER   = 10
# Absolute timeout — safety net regardless of queue estimate
ABSOLUTE_TIMEOUT_S = 1800  # 30 minutes

# ─────────────────────────────────────────
# CIRCUIT
# ─────────────────────────────────────────

def create_bell_circuit():
    """Creates a Bell state circuit — used as base test."""
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc

# ─────────────────────────────────────────
# NOISE MODEL
# ─────────────────────────────────────────

def create_realistic_noise_model():
    """
    Noise model calibrated on typical IBM real hardware errors.
    - Single-qubit gate error: ~0.1%
    - Two-qubit gate error (CNOT): ~1%
    - Readout error: ~2%
    """
    noise_model = NoiseModel()
    noise_model.add_all_qubit_quantum_error(
        depolarizing_error(0.001, 1), ['h', 'x', 'rx', 'ry', 'rz']
    )
    noise_model.add_all_qubit_quantum_error(
        depolarizing_error(0.01, 2), ['cx']
    )
    noise_model.add_all_qubit_readout_error(
        ReadoutError([[0.98, 0.02], [0.02, 0.98]])
    )
    return noise_model

# ─────────────────────────────────────────
# IBM — CONNECTION AND AUTONOMOUS SELECTION
# ─────────────────────────────────────────

def connect_ibm():
    """Connects to IBM Quantum and returns the service object."""
    if not IBM_API_KEY:
        return None
    try:
        service = QiskitRuntimeService(
            channel="ibm_cloud",
            token=IBM_API_KEY,
            instance=IBM_INSTANCE
        )
        return service
    except Exception as e:
        print(f"[IBM] Connection failed: {e}")
        return None

def pick_best_ibm_backend(service):
    """
    Autonomously selects the best available IBM backend.
    Criteria: operational + minimum pending jobs.
    Returns (backend, estimated_exec_s, pending_jobs) or (None, 0, 0).
    """
    try:
        candidates = []
        for b in service.backends():
            s = b.status()
            if s.operational:
                candidates.append((b, s.pending_jobs))

        if not candidates:
            print("[IBM] No operational backend available")
            return None, 0, 0

        candidates.sort(key=lambda x: x[1])
        best, pending = candidates[0]

        print(f"[IBM] Available backends (sorted by queue):")
        for b, p in candidates:
            marker = " <- selected" if b.name == best.name else ""
            print(f"       {b.name:<30} pending: {p}{marker}")

        return best, 10, pending  # 10s conservative execution estimate

    except Exception as e:
        print(f"[IBM] Backend selection error: {e}")
        return None, 0, 0

# ─────────────────────────────────────────
# BACKEND SELECTOR
# ─────────────────────────────────────────

def select_backend(preference="ideal_simulator"):
    """
    Returns (backend, name, service).
    service is None for simulators.

    preference:
      "ideal_simulator"  — local Aer, no noise
      "noisy_simulator"  — local Aer, realistic IBM noise model
      "ibm_qpu"          — real IBM QPU, autonomous selection + adaptive fallback
    """
    if preference == "ideal_simulator":
        print("[BACKEND] Selected: ideal simulator (no noise)")
        return AerSimulator(), "ideal_simulator", None

    elif preference == "noisy_simulator":
        print("[BACKEND] Selected: noisy simulator (realistic IBM noise model)")
        return AerSimulator(noise_model=create_realistic_noise_model()), "noisy_simulator", None

    elif preference == "ibm_qpu":
        service = connect_ibm()
        if service is None:
            print("[BACKEND] IBM unreachable — falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        backend, estimated_exec_s, pending = pick_best_ibm_backend(service)

        if backend is None:
            print("[BACKEND] No backend available — falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        # Adaptive fallback: estimated queue vs estimated execution time
        estimated_queue_s = pending * 60  # conservative: 60s per pending job
        threshold         = QUEUE_MULTIPLIER * estimated_exec_s

        if estimated_queue_s > threshold:
            print(f"[BACKEND] Estimated queue {estimated_queue_s}s > threshold {threshold}s "
                  f"— falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        print(f"[BACKEND] Selected: real QPU ({backend.name}), "
              f"pending: {pending}, queue threshold: {threshold}s")
        return backend, f"ibm_qpu_{backend.name}", service

    else:
        print("[BACKEND] Unknown preference — falling back to ideal simulator")
        return AerSimulator(), "fallback_ideal_simulator", None

# ─────────────────────────────────────────
# JOB RUNNER
# ─────────────────────────────────────────

def run_job(circuit, backend, backend_name, shots=1024, service=None):
    """Runs the circuit on the selected backend and returns a result log."""
    print(f"\n--- Running job ---")
    print(f"Backend: {backend_name}")
    print(f"Shots:   {shots}")

    t_start     = time.time()
    is_real_qpu = (service is not None) and backend_name.startswith("ibm_qpu_")

    if is_real_qpu:
        result_data = _run_on_qpu(circuit, backend, backend_name, shots)
    else:
        result_data = _run_on_simulator(circuit, backend, backend_name, shots)

    result_data["timestamp"]    = datetime.datetime.now().isoformat()
    result_data["total_time_s"] = round(time.time() - t_start, 3)

    print(f"Counts:         {result_data['counts']}")
    print(f"Fidelity:       {result_data['fidelity'] * 100:.2f}%")
    print(f"Execution time: {result_data['execution_time_s']}s")
    print(f"Queue time:     {result_data['queue_time_s']}s")
    return result_data


def _run_on_simulator(circuit, backend, backend_name, shots):
    t      = time.time()
    result = backend.run(circuit, shots=shots).result()
    counts = result.get_counts()
    return {
        "backend":          backend_name,
        "shots":            shots,
        "counts":           counts,
        "execution_time_s": round(time.time() - t, 3),
        "queue_time_s":     0,
        "fidelity":         compute_fidelity(counts, shots),
    }


def _run_on_qpu(circuit, backend, backend_name, shots):
    """
    Runs on real IBM QPU using SamplerV2.
    Measures queue time and execution time separately via job.metrics().
    """
    transpiled = transpile(circuit, backend=backend, optimization_level=1)
    print(f"[QPU] Circuit transpiled — depth: {transpiled.depth()}, "
          f"gates: {transpiled.size()}, qubits: {transpiled.num_qubits}")

    sampler  = Sampler(backend)
    t_submit = time.time()
    job      = sampler.run([transpiled], shots=shots)
    print(f"[QPU] Job submitted — ID: {job.job_id()}")
    print(f"[QPU] Polling every 10s (timeout: {ABSOLUTE_TIMEOUT_S // 60} min)...")

    while True:
        status  = job.status()
        elapsed = time.time() - t_submit
        print(f"[QPU] Status: {status}  ({int(elapsed)}s elapsed)")

        if status in ("DONE", "ERROR", "CANCELLED"):
            break

        if elapsed > ABSOLUTE_TIMEOUT_S:
            print(f"[QPU] Absolute timeout reached ({ABSOLUTE_TIMEOUT_S}s) — cancelling job")
            try:
                job.cancel()
            except Exception:
                pass
            raise RuntimeError("QPU job timed out — rerun with noisy simulator fallback")

        time.sleep(10)

    t_done = time.time()

    if status != "DONE":
        raise RuntimeError(f"QPU job ended with status: {status}")

    pub_result = job.result()[0]
    register   = list(pub_result.data)[0]
    counts     = dict(getattr(pub_result.data, register).get_counts())

    # Precise timing from IBM metrics
    try:
        metrics    = job.metrics()
        exec_time  = round(metrics.get("usage", {}).get("seconds", 10), 1)
        queue_time = round((t_done - t_submit) - exec_time, 1)
    except Exception:
        exec_time  = 10.0
        queue_time = round((t_done - t_submit) - exec_time, 1)

    return {
        "backend":          backend_name,
        "shots":            shots,
        "counts":           counts,
        "execution_time_s": exec_time,
        "queue_time_s":     max(0, queue_time),
        "fidelity":         compute_fidelity(counts, shots),
    }

# ─────────────────────────────────────────
# FIDELITY
# ─────────────────────────────────────────

def compute_fidelity(counts, shots):
    """
    Bell state fidelity: ideal = 50% |00> + 50% |11>.
    Fidelity = (counts['00'] + counts['11']) / shots
    """
    correct = counts.get('00', 0) + counts.get('11', 0)
    return round(correct / shots, 4)

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

def save_log(log, path="results/log.txt"):
    """Appends the job result log to file."""
    os.makedirs("results", exist_ok=True)
    with open(path, "a") as f:
        f.write(str(log) + "\n")
    print(f"[LOG] Saved to {path}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=== Quantum Orchestrator v0.4 ===\n")

    circuit = create_bell_circuit()
    print(circuit.draw())

    # Run 1 — ideal simulator
    b1, n1, s1 = select_backend("ideal_simulator")
    log1 = run_job(circuit, b1, n1, service=s1)
    save_log(log1)

    # Run 2 — noisy simulator
    b2, n2, s2 = select_backend("noisy_simulator")
    log2 = run_job(circuit, b2, n2, service=s2)
    save_log(log2)

    # Run 3 — real IBM QPU (autonomous selection + adaptive fallback)
    b3, n3, s3 = select_backend("ibm_qpu")
    log3 = run_job(circuit, b3, n3, service=s3)
    save_log(log3)

    # Plot comparison
    from graph import plot_backend_comparison
    plot_backend_comparison(log1, log2, log3)

    # Summary
    print("\n=== Results summary ===")
    for log in [log1, log2, log3]:
        print(f"{log['backend']:<35}  fidelity: {log['fidelity']*100:.2f}%  "
              f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")
    print("\n=== Done ===")