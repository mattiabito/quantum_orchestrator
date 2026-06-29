from circuits.bell import create_bell_circuit
from backends.ibm import (IBMSimulatorAdapter, IBMQPUAdapter,
                           IBMQPUAdapterAdaptive, connect_ibm,
                           pick_best_ibm_backend)
import datetime
import os

QUEUE_MULTIPLIER   = 20   # fallback if queue > multiplier * estimated exec
ESTIMATED_EXEC_S   = 10   # conservative execution estimate (seconds)
ABSOLUTE_TIMEOUT_S = 1800  # 30 minutes

def select_backend(preference="ideal_simulator", strategy="responsive"):
    """
    Returns the appropriate BackendAdapter based on preference and strategy.

    preference:
      "ideal_simulator"  — local Aer, no noise
      "noisy_simulator"  — local Aer, realistic IBM noise model
      "ibm_qpu"          — real IBM QPU, autonomous selection

    strategy (applies only to ibm_qpu):
      "responsive"  — fallback immediately if queue > threshold.
                      Best for: interactive apps, fast iteration, testing.
      "accurate"    — always wait for real QPU, no fallback.
                      Best for: research, when QPU fidelity is required.
      "adaptive"    — wait up to ABSOLUTE_TIMEOUT_S, then fallback.
                      Best for: batch jobs, overnight runs, best-effort quality.
    """
    if preference == "ideal_simulator":
        return IBMSimulatorAdapter(noisy=False)

    elif preference == "noisy_simulator":
        return IBMSimulatorAdapter(noisy=True)

    elif preference == "ibm_qpu":
        service = connect_ibm()
        if service is None:
            print("[ORCHESTRATOR] IBM unreachable — falling back to noisy simulator")
            return IBMSimulatorAdapter(noisy=True)

        backend, estimated_exec_s, pending = pick_best_ibm_backend(service)

        if backend is None:
            print("[ORCHESTRATOR] No backend available — falling back to noisy simulator")
            return IBMSimulatorAdapter(noisy=True)

        queue_s   = pending * 60
        threshold = QUEUE_MULTIPLIER * ESTIMATED_EXEC_S

        print(f"[ORCHESTRATOR] Strategy: {strategy.upper()}")
        print(f"[ORCHESTRATOR] Estimated queue: {queue_s}s, threshold: {threshold}s")

        if strategy == "responsive":
            # Fallback immediately if queue exceeds threshold
            if queue_s > threshold:
                print(f"[ORCHESTRATOR] Queue too long — falling back to noisy simulator")
                return IBMSimulatorAdapter(noisy=True)
            print(f"[ORCHESTRATOR] Queue acceptable — selected: {backend.name}")
            return IBMQPUAdapter(backend, service)

        elif strategy == "accurate":
            # Always use real QPU — never fallback, wait as long as needed
            print(f"[ORCHESTRATOR] Accurate mode — will wait for real QPU regardless of queue")
            return IBMQPUAdapter(backend, service)

        elif strategy == "adaptive":
            # Wait up to ABSOLUTE_TIMEOUT_S, then fallback
            if queue_s > threshold:
                print(f"[ORCHESTRATOR] Queue long ({queue_s}s) — will attempt QPU "
                      f"with {ABSOLUTE_TIMEOUT_S//60}min timeout before fallback")
            return IBMQPUAdapterAdaptive(backend, service)

        else:
            print(f"[ORCHESTRATOR] Unknown strategy '{strategy}' — using responsive")
            if queue_s > threshold:
                return IBMSimulatorAdapter(noisy=True)
            return IBMQPUAdapter(backend, service)

    else:
        print(f"[ORCHESTRATOR] Unknown preference — using ideal simulator")
        return IBMSimulatorAdapter(noisy=False)


def run_job(adapter, circuit, shots=1024) -> dict:
    """Runs the circuit on the given adapter and returns the result log."""
    print(f"\n--- Running job ---")
    print(f"Backend: {adapter.name}")
    print(f"Shots:   {shots}")

    result = adapter.run(circuit, shots=shots)
    result["timestamp"] = datetime.datetime.now().isoformat()

    print(f"Counts:         {result['counts']}")
    print(f"Fidelity:       {result['fidelity'] * 100:.2f}%")
    print(f"Execution time: {result['execution_time_s']}s")
    print(f"Queue time:     {result['queue_time_s']}s")
    return result


def save_log(log, path="results/log.txt"):
    """Appends the job result log to file."""
    os.makedirs("results", exist_ok=True)
    with open(path, "a") as f:
        f.write(str(log) + "\n")
    print(f"[LOG] Saved to {path}")


if __name__ == "__main__":
    print("=== Quantum Orchestrator v0.5 ===\n")

    circuit = create_bell_circuit()
    print(circuit.draw())

    # Run 1 — ideal simulator
    adapter1 = select_backend("ideal_simulator")
    log1     = run_job(adapter1, circuit)
    save_log(log1)

    # Run 2 — noisy simulator
    adapter2 = select_backend("noisy_simulator")
    log2     = run_job(adapter2, circuit)
    save_log(log2)

    # Run 3 — real IBM QPU (autonomous selection + adaptive fallback)
    adapter3 = select_backend("ibm_qpu", strategy="responsive")
    log3     = run_job(adapter3, circuit)
    save_log(log3)

    # Run 4 — AWS Braket local simulator
    from backends.aws import AWSSimulatorAdapter
    adapter4 = AWSSimulatorAdapter()
    if adapter4.is_available():
        log4 = run_job(adapter4, circuit)
        save_log(log4)
    else:
        log4 = None
        print("[ORCHESTRATOR] AWS Braket not available — skipping")

    # Run 5 — IonQ trapped-ion simulator (via AWS Braket)
    from backends.ionq import IonQSimulatorAdapter
    adapter5 = IonQSimulatorAdapter()
    if adapter5.is_available():
        log5 = run_job(adapter5, circuit)
        save_log(log5)
    else:
        log5 = None
        print("[ORCHESTRATOR] IonQ simulator not available — skipping")

    # Plot
    from graph import plot_backend_comparison
    plot_backend_comparison(log1, log2, log3, log4, log5)

    # Summary
    print("\n=== Results summary ===")
    for log in [l for l in [log1, log2, log3, log4, log5] if l]:
        print(f"{log['backend']:<35}  fidelity: {log['fidelity']*100:.2f}%  "
              f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")
    print("\n=== Done ===")