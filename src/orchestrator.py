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
QUEUE_THRESHOLD_SECONDS = 300  # fallback se coda > 5 minuti

# ─────────────────────────────────────────
# CIRCUIT
# ─────────────────────────────────────────

def create_bell_circuit():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc

# ─────────────────────────────────────────
# NOISE MODEL
# ─────────────────────────────────────────

def create_realistic_noise_model():
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
# IBM QPU — STATUS
# ─────────────────────────────────────────

def get_ibm_backend_status(service, backend_name="ibm_brisbane"):
    try:
        backend = service.backend(backend_name)
        status  = backend.status()
        pending = status.pending_jobs
        estimated_queue_s = pending * 30
        print(f"[QPU STATUS] {backend_name} — operational: {status.operational}, "
              f"pending jobs: {pending}, estimated queue: ~{estimated_queue_s}s")
        return backend, estimated_queue_s
    except Exception as e:
        print(f"[QPU STATUS] Could not reach {backend_name}: {e}")
        return None, float('inf')

# ─────────────────────────────────────────
# BACKEND SELECTOR
# ─────────────────────────────────────────

def select_backend(preference="ideal_simulator", ibm_backend_name="ibm_brisbane"):
    """
    Returns (backend, name, service).
    service is None for simulators, QiskitRuntimeService for real QPU.
    """
    if preference == "ideal_simulator":
        print("[BACKEND] Selected: ideal simulator (no noise)")
        return AerSimulator(), "ideal_simulator", None

    elif preference == "noisy_simulator":
        print("[BACKEND] Selected: noisy simulator (realistic IBM noise model)")
        return AerSimulator(noise_model=create_realistic_noise_model()), "noisy_simulator", None

    elif preference == "ibm_qpu":
        if not IBM_API_KEY:
            print("[BACKEND] IBM_API_KEY not found in .env — falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        print("[BACKEND] Connecting to IBM Quantum (Cloud IAM)...")
        try:
            service = QiskitRuntimeService(
                channel="ibm_cloud",
                token=IBM_API_KEY,
                instance=IBM_INSTANCE
            )
        except Exception as e:
            print(f"[BACKEND] Connection failed: {e} — falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        backend, queue_s = get_ibm_backend_status(service, ibm_backend_name)

        if backend is None or queue_s > QUEUE_THRESHOLD_SECONDS:
            print(f"[BACKEND] Queue too long ({queue_s}s > {QUEUE_THRESHOLD_SECONDS}s) "
                  f"— falling back to noisy simulator")
            return AerSimulator(noise_model=create_realistic_noise_model()), "fallback_noisy_simulator", None

        print(f"[BACKEND] Selected: IBM QPU ({ibm_backend_name})")
        return backend, f"ibm_qpu_{ibm_backend_name}", service

    else:
        print("[BACKEND] Unknown preference — falling back to ideal simulator")
        return AerSimulator(), "fallback_ideal_simulator", None

# ─────────────────────────────────────────
# JOB RUNNER
# ─────────────────────────────────────────

def run_job(circuit, backend, backend_name, shots=1024, service=None):
    print(f"\n--- Running job ---")
    print(f"Backend: {backend_name}")
    print(f"Shots:   {shots}")

    t_start = time.time()
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
    t = time.time()
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
    transpiled = transpile(circuit, backend=backend, optimization_level=1)
    print(f"[QPU] Circuit transpiled — depth: {transpiled.depth()}")

    sampler  = Sampler(backend)
    t_submit = time.time()
    job      = sampler.run([transpiled], shots=shots)
    print(f"[QPU] Job submitted — ID: {job.job_id()}")
    print("[QPU] Polling every 10s...")

    t_running = None
    while True:
        status = job.status() 
        print(f"[QPU] Status: {status}")
        if status == "RUNNING" and t_running is None:
            t_running = time.time()
        if status in ("DONE", "ERROR", "CANCELLED"):
            break
        time.sleep(10)

    t_done = time.time()

    if status != "DONE":
        raise RuntimeError(f"QPU job ended with status: {status}")

    pub_result  = job.result()[0]
    register    = list(pub_result.data)[0]
    counts      = dict(getattr(pub_result.data, register).get_counts())
    
    try:
        metrics       = job.metrics()
        exec_time     = round(metrics.get("usage", {}).get("seconds", 10), 1)
        queue_time    = round((t_done - t_submit) - exec_time, 1)
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
    correct = counts.get('00', 0) + counts.get('11', 0)
    return round(correct / shots, 4)

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

def save_log(log, path="results/log.txt"):
    os.makedirs("results", exist_ok=True)
    with open(path, "a") as f:
        f.write(str(log) + "\n")
    print(f"[LOG] Saved to {path}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=== Quantum Orchestrator v0.3 ===\n")

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

    # Run 3 — real IBM QPU (with automatic fallback)
    b3, n3, s3 = select_backend("ibm_qpu", ibm_backend_name="ibm_kingston")
    log3 = run_job(circuit, b3, n3, service=s3)
    save_log(log3)

    # Summary
    print("\n=== Results summary ===")
    for log in [log1, log2, log3]:
        print(f"{log['backend']:<35}  fidelity: {log['fidelity']*100:.2f}%  "
              f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")
    print("\n=== Done ===")

    # Graph
    from graph import plot_backend_comparison
    plot_backend_comparison(log1, log2, log3)