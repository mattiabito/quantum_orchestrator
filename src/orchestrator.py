from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
import time
import datetime

def create_bell_circuit():
    """Creates a Bell state circuit — used as base test."""
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc

def create_realistic_noise_model():
    """
    Noise model calibrated on typical IBM real hardware errors.
    - Single-qubit gate error: ~0.1%
    - Two-qubit gate error (CNOT): ~1%
    - Readout error: ~2%
    """
    noise_model = NoiseModel()

    single_qubit_error = depolarizing_error(0.001, 1)
    noise_model.add_all_qubit_quantum_error(single_qubit_error, ['h', 'x', 'rx', 'ry', 'rz'])

    two_qubit_error = depolarizing_error(0.01, 2)
    noise_model.add_all_qubit_quantum_error(two_qubit_error, ['cx'])

    readout = ReadoutError([[0.98, 0.02], [0.02, 0.98]])
    noise_model.add_all_qubit_readout_error(readout)

    return noise_model

def select_backend(preference="ideal_simulator"):
    """
    Backend selector — the core of the orchestrator.
    Chooses the backend based on preference and availability.
    """
    if preference == "ideal_simulator":
        print("[BACKEND] Selected: ideal simulator (no noise)")
        return AerSimulator(), "ideal_simulator"

    elif preference == "noisy_simulator":
        print("[BACKEND] Selected: noisy simulator (realistic IBM noise model)")
        noise_model = create_realistic_noise_model()
        simulator = AerSimulator(noise_model=noise_model)
        return simulator, "noisy_simulator"

    else:
        print("[BACKEND] Unknown backend, falling back to ideal simulator")
        return AerSimulator(), "fallback_simulator"

def compute_fidelity(counts, shots):
    """
    Computes fidelity against the ideal Bell state.
    Ideal Bell state: 50% '00' and 50% '11', zero '01' and '10'.
    Fidelity = (counts '00' + counts '11') / total shots
    """
    correct = counts.get('00', 0) + counts.get('11', 0)
    fidelity = correct / shots
    return round(fidelity, 4)

def run_job(circuit, backend, backend_name, shots=1024):
    """Runs the circuit on the selected backend and logs the results."""
    print(f"\n--- Running job ---")
    print(f"Backend: {backend_name}")
    print(f"Shots: {shots}")

    start = time.time()
    job = backend.run(circuit, shots=shots)
    result = job.result()
    end = time.time()

    counts = result.get_counts()
    execution_time = round(end - start, 3)
    fidelity = compute_fidelity(counts, shots)

    print(f"Execution time: {execution_time}s")
    print(f"Counts: {counts}")
    print(f"Fidelity: {fidelity * 100:.2f}%")

    return {
        "backend": backend_name,
        "shots": shots,
        "counts": counts,
        "execution_time_s": execution_time,
        "fidelity": fidelity,
        "timestamp": datetime.datetime.now().isoformat()
    }

def save_log(log, path="results/log.txt"):
    """Saves the job log to file."""
    with open(path, "a") as f:
        f.write(str(log) + "\n")
    print(f"[LOG] Saved to {path}")

if __name__ == "__main__":
    print("=== Quantum Orchestrator v0.2 ===\n")

    circuit = create_bell_circuit()
    print("Bell state circuit:")
    print(circuit.draw())

    # Run 1: ideal simulator
    backend1, name1 = select_backend("ideal_simulator")
    log1 = run_job(circuit, backend1, name1)
    save_log(log1)

    # Run 2: noisy simulator (realistic IBM noise model)
    backend2, name2 = select_backend("noisy_simulator")
    log2 = run_job(circuit, backend2, name2)
    save_log(log2)

    # Summary
    print("\n=== Results summary ===")
    print(f"Ideal simulator fidelity:  {log1['fidelity'] * 100:.2f}%")
    print(f"Noisy simulator fidelity:  {log2['fidelity'] * 100:.2f}%")
    print(f"Noise degradation:         {(log1['fidelity'] - log2['fidelity']) * 100:.2f}%")
    print("\n=== Done ===")