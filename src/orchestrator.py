from circuits.bell import create_bell_circuit, compute_fidelity
from circuits.ghz  import create_ghz_circuit, compute_fidelity_ghz
from backends.ibm import (IBMSimulatorAdapter, IBMQPUAdapter,
                           IBMQPUAdapterAdaptive, connect_ibm,
                           pick_best_ibm_backend)
from graph import plot_backend_comparison
from backends.aws  import AWSSimulatorAdapter
from backends.ionq import IonQSimulatorAdapter
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


def run_job(adapter, circuit, shots=1024, fidelity_fn=None) -> dict:
    """
    Runs the circuit on the given adapter and returns the result log.
    fidelity_fn: optional custom fidelity function — defaults to Bell state fidelity.
    """
    print(f"\n--- Running job ---")
    print(f"Backend: {adapter.name}")
    print(f"Shots:   {shots}")

    result = adapter.run(circuit, shots=shots)

    # Apply custom fidelity function if provided
    if fidelity_fn is not None:
        result["fidelity"] = fidelity_fn(result["counts"], shots)

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
    import argparse

    # ── CLI argument parsing ──────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Quantum Orchestrator — multi-provider quantum circuit scheduler"
    )
    parser.add_argument(
        "--circuit",
        choices=["bell", "ghz", "all"],
        default="all",
        help="Circuit to run: bell, ghz, or all (default: all)"
    )
    parser.add_argument(
        "--strategy",
        choices=["responsive", "accurate", "adaptive"],
        default="responsive",
        help="Execution strategy for IBM QPU (default: responsive)"
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=1024,
        help="Number of shots per job (default: 1024)"
    )
    args = parser.parse_args()

    print(f"=== Quantum Orchestrator v0.6 ===")
    print(f"Circuit: {args.circuit}  |  Strategy: {args.strategy}  |  Shots: {args.shots}\n")

    run_bell = args.circuit in ("bell", "all")
    run_ghz  = args.circuit in ("ghz", "all")

    from graph import plot_backend_comparison

    # ── Bell state benchmark ──────────────────────────────────────
    if run_bell:
        print("=" * 50)
        print("CIRCUIT: Bell state (2 qubits)")
        print("=" * 50)

        bell = create_bell_circuit()
        print(bell.draw())

        b_adapter1 = select_backend("ideal_simulator")
        b_log1     = run_job(b_adapter1, bell, shots=args.shots)
        save_log(b_log1)

        b_adapter2 = select_backend("noisy_simulator")
        b_log2     = run_job(b_adapter2, bell, shots=args.shots)
        save_log(b_log2)

        b_adapter3 = select_backend("ibm_qpu", strategy=args.strategy)
        b_log3     = run_job(b_adapter3, bell, shots=args.shots)
        save_log(b_log3)

        b_adapter4 = AWSSimulatorAdapter()
        b_log4     = run_job(b_adapter4, bell, shots=args.shots) if b_adapter4.is_available() else None
        if b_log4: save_log(b_log4)

        b_adapter5 = IonQSimulatorAdapter()
        b_log5     = run_job(b_adapter5, bell, shots=args.shots) if b_adapter5.is_available() else None
        if b_log5: save_log(b_log5)

        plot_backend_comparison(b_log1, b_log2, b_log3, b_log4, b_log5,
                                title=f"Bell State (2 qubits) — {args.shots} shots",
                                filename="results/bell_comparison.png")

    # ── GHZ state benchmark ───────────────────────────────────────
    if run_ghz:
        print("\n" + "=" * 50)
        print("CIRCUIT: GHZ state (3 qubits)")
        print("=" * 50)

        ghz = create_ghz_circuit(n_qubits=3)
        print(ghz.draw())

        g_adapter1 = select_backend("ideal_simulator")
        g_log1     = run_job(g_adapter1, ghz, shots=args.shots, fidelity_fn=compute_fidelity_ghz)
        save_log(g_log1)

        g_adapter2 = select_backend("noisy_simulator")
        g_log2     = run_job(g_adapter2, ghz, shots=args.shots, fidelity_fn=compute_fidelity_ghz)
        save_log(g_log2)

        g_adapter3 = select_backend("ibm_qpu", strategy=args.strategy)
        g_log3     = run_job(g_adapter3, ghz, shots=args.shots, fidelity_fn=compute_fidelity_ghz)
        save_log(g_log3)

        g_adapter4 = AWSSimulatorAdapter()
        g_log4     = run_job(g_adapter4, ghz, shots=args.shots, fidelity_fn=compute_fidelity_ghz) if g_adapter4.is_available() else None
        if g_log4: save_log(g_log4)

        g_adapter5 = IonQSimulatorAdapter()
        g_log5     = run_job(g_adapter5, ghz, shots=args.shots, fidelity_fn=compute_fidelity_ghz) if g_adapter5.is_available() else None
        if g_log5: save_log(g_log5)

        plot_backend_comparison(g_log1, g_log2, g_log3, g_log4, g_log5,
                                title=f"GHZ State (3 qubits) — {args.shots} shots",
                                filename="results/ghz_comparison.png")

    # ── Results summary ───────────────────────────────────────────
    print("\n=== Results summary ===")

    if run_bell:
        print("\nBell state:")
        for log in [l for l in [b_log1, b_log2, b_log3, b_log4, b_log5] if l]:
            print(f"  {log['backend']:<35} fidelity: {log['fidelity']*100:.2f}%  "
                  f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")

    if run_ghz:
        print("\nGHZ state:")
        for log in [l for l in [g_log1, g_log2, g_log3, g_log4, g_log5] if l]:
            print(f"  {log['backend']:<35} fidelity: {log['fidelity']*100:.2f}%  "
                  f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")

    print("\n=== Done ===")