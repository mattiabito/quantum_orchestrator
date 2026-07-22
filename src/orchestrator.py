import sys

# Force UTF-8 stdout/stderr regardless of the terminal/redirect target.
# Without this, Windows falls back to the system codepage (cp1252) whenever
# output isn't an interactive console (e.g. redirected to a file), which
# can't encode the circuit-diagram box-drawing characters or symbols like
# "H2" and crashes with UnicodeEncodeError.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from circuits.bell import create_bell_circuit, compute_fidelity
from circuits.ghz  import create_ghz_circuit, compute_fidelity_ghz
from backends.ibm import (IBMSimulatorAdapter, IBMQPUAdapter,
                           IBMQPUAdapterAdaptive, connect_ibm,
                           pick_best_ibm_backend, ABSOLUTE_TIMEOUT_S)
from backends.aws  import AWSSimulatorAdapter
from backends.ionq import IonQSimulatorAdapter
from graph import plot_backend_comparison
from paths import RESULTS_DIR
import datetime
import os
import json

QUEUE_MULTIPLIER = 20  # fallback if queue > multiplier * estimated exec


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
        threshold = QUEUE_MULTIPLIER * estimated_exec_s

        print(f"[ORCHESTRATOR] Strategy: {strategy.upper()}")
        print(f"[ORCHESTRATOR] Estimated queue: {queue_s}s, threshold: {threshold}s")

        if strategy == "responsive":
            if queue_s > threshold:
                print(f"[ORCHESTRATOR] Queue too long — falling back to noisy simulator")
                return IBMSimulatorAdapter(noisy=True)
            print(f"[ORCHESTRATOR] Queue acceptable — selected: {backend.name}")
            return IBMQPUAdapter(backend, service)

        elif strategy == "accurate":
            print(f"[ORCHESTRATOR] Accurate mode — will wait for real QPU regardless of queue")
            return IBMQPUAdapter(backend, service)

        elif strategy == "adaptive":
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


def compute_fidelity_generic(counts: dict, shots: int,
                             reference_counts: dict, reference_shots: int) -> float:
    """
    Generic fidelity for arbitrary circuits — Hellinger/Bhattacharyya-style
    overlap between an observed distribution and a reference "ideal"
    distribution:

        F = (sum_i sqrt(p_i * q_i))^2

    Unlike circuits.bell.compute_fidelity (which assumes exactly two
    dominant basis states, e.g. |00> and |11>), this works for any
    measurement outcome distribution. Used for custom QASM circuits,
    where the ideal state isn't known in advance — the reference
    distribution is measured directly on the noiseless ideal_simulator
    run of the same circuit instead of being assumed.
    """
    all_states = set(counts) | set(reference_counts)
    overlap = 0.0
    for state in all_states:
        p = counts.get(state, 0) / shots
        q = reference_counts.get(state, 0) / reference_shots
        overlap += (p * q) ** 0.5
    return round(overlap ** 2, 4)


def _make_generic_fidelity_fn(reference_counts: dict, reference_shots: int):
    """Returns a fidelity_fn(counts, shots) closure bound to a reference distribution."""
    return lambda counts, shots: compute_fidelity_generic(
        counts, shots, reference_counts, reference_shots
    )


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


def save_log(log, path=None):
    """
    Appends the job result log to a JSON file.
    Each line is a valid JSON object (newline-delimited JSON / NDJSON format).
    """
    path = path or os.path.join(RESULTS_DIR, "log.json")
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(log) + "\n")
    print(f"[LOG] Saved to {path}")


if __name__ == "__main__":
    import argparse

    # ── CLI argument parsing ──────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Quantum Orchestrator — multi-provider quantum circuit scheduler"
    )
    parser.add_argument(
        "--circuit",
        choices=["bell", "ghz", "vqe", "all"],
        default="all",
        help="Circuit to run: bell, ghz, vqe, or all (default: all)"
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
    parser.add_argument(
        "--qasm",
        type=str,
        default=None,
        help="Path to a .qasm file to run on all backends. "
             "Overrides --circuit if provided."
    )
    args = parser.parse_args()

    print(f"=== Quantum Orchestrator v1.0 ===")
    print(f"Circuit: {args.circuit}  |  Strategy: {args.strategy}  |  Shots: {args.shots}\n")

    # ── QASM custom circuit — overrides --circuit if provided ─────
    custom_circuit = None
    custom_name    = None

    if args.qasm:
        from qiskit import QuantumCircuit as QC
        print(f"[QASM] Loading circuit from: {args.qasm}")
        try:
            custom_circuit = QC.from_qasm_file(args.qasm)
            custom_name    = args.qasm.replace("\\", "/").split("/")[-1]
            print(f"[QASM] Circuit loaded: {custom_name}")
            print(f"[QASM] Qubits: {custom_circuit.num_qubits}, "
                  f"Depth: {custom_circuit.depth()}")
            print(custom_circuit.draw())
            run_bell = False
            run_ghz  = False
            run_vqe  = False
        except Exception as e:
            print(f"[QASM] Error loading file: {e}")
            print("[QASM] Falling back to --circuit flag")
            custom_circuit = None

    if custom_circuit is None:
        run_bell = args.circuit in ("bell", "all")
        run_ghz  = args.circuit in ("ghz", "all")
        run_vqe  = args.circuit in ("vqe", "all")

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
                                filename=os.path.join(RESULTS_DIR, "bell_comparison.png"))

    # ── GHZ state benchmark ───────────────────────────────────────
    if run_ghz:
        print("\n" + "=" * 50)
        print("CIRCUIT: GHZ state (3 qubits)")
        print("=" * 50)

        ghz = create_ghz_circuit(n_qubits=3)
        print(ghz.draw())

        g_adapter1 = select_backend("ideal_simulator")
        g_log1     = run_job(g_adapter1, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz)
        save_log(g_log1)

        g_adapter2 = select_backend("noisy_simulator")
        g_log2     = run_job(g_adapter2, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz)
        save_log(g_log2)

        g_adapter3 = select_backend("ibm_qpu", strategy=args.strategy)
        g_log3     = run_job(g_adapter3, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz)
        save_log(g_log3)

        g_adapter4 = AWSSimulatorAdapter()
        g_log4     = run_job(g_adapter4, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz) if g_adapter4.is_available() else None
        if g_log4: save_log(g_log4)

        g_adapter5 = IonQSimulatorAdapter()
        g_log5     = run_job(g_adapter5, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz) if g_adapter5.is_available() else None
        if g_log5: save_log(g_log5)

        plot_backend_comparison(g_log1, g_log2, g_log3, g_log4, g_log5,
                                title=f"GHZ State (3 qubits) — {args.shots} shots",
                                filename=os.path.join(RESULTS_DIR, "ghz_comparison.png"))

    # ── VQE H₂ benchmark ─────────────────────────────────────────
    if run_vqe:
        # Imported here, not at module top — vqe_h2.py depends on scipy,
        # which shouldn't be a hard requirement for running bell/ghz.
        try:
            from circuits.vqe_h2 import create_vqe_h2_circuit, compute_fidelity_vqe, compute_energy_h2
        except ImportError as e:
            print(f"[VQE] Could not import scipy — skipping VQE benchmark: {e}")
            run_vqe = False

    if run_vqe:
        print("\n" + "=" * 50)
        print("CIRCUIT: VQE H₂ (2 qubits — minimal ansatz)")
        print("=" * 50)

        vqe = create_vqe_h2_circuit()
        print(vqe.draw())

        v_adapter1 = select_backend("ideal_simulator")
        v_log1     = run_job(v_adapter1, vqe, shots=args.shots,
                             fidelity_fn=compute_fidelity_vqe)
        v_log1["energy_hartree"] = compute_energy_h2(v_log1["counts"], args.shots)
        save_log(v_log1)

        v_adapter2 = select_backend("noisy_simulator")
        v_log2     = run_job(v_adapter2, vqe, shots=args.shots,
                             fidelity_fn=compute_fidelity_vqe)
        v_log2["energy_hartree"] = compute_energy_h2(v_log2["counts"], args.shots)
        save_log(v_log2)

        v_adapter3 = select_backend("ibm_qpu", strategy=args.strategy)
        v_log3     = run_job(v_adapter3, vqe, shots=args.shots,
                             fidelity_fn=compute_fidelity_vqe)
        v_log3["energy_hartree"] = compute_energy_h2(v_log3["counts"], args.shots)
        save_log(v_log3)

        v_adapter4 = AWSSimulatorAdapter()
        v_log4     = run_job(v_adapter4, vqe, shots=args.shots,
                             fidelity_fn=compute_fidelity_vqe) if v_adapter4.is_available() else None
        if v_log4:
            v_log4["energy_hartree"] = compute_energy_h2(v_log4["counts"], args.shots)
            save_log(v_log4)

        v_adapter5 = IonQSimulatorAdapter()
        v_log5     = run_job(v_adapter5, vqe, shots=args.shots,
                             fidelity_fn=compute_fidelity_vqe) if v_adapter5.is_available() else None
        if v_log5:
            v_log5["energy_hartree"] = compute_energy_h2(v_log5["counts"], args.shots)
            save_log(v_log5)

        plot_backend_comparison(v_log1, v_log2, v_log3, v_log4, v_log5,
                                title=f"VQE H₂ (2 qubits — Z-basis) — {args.shots} shots",
                                filename=os.path.join(RESULTS_DIR, "vqe_comparison.png"))

    # ── Custom QASM circuit ───────────────────────────────────────
    if custom_circuit is not None:
        print("\n" + "=" * 50)
        print(f"CIRCUIT: {custom_name} (custom QASM)")
        print("=" * 50)

        # ideal_simulator runs first — its distribution is the reference
        # for a generic fidelity metric on the other backends, since a
        # custom circuit's ideal state isn't known in advance like Bell/GHZ/VQE
        q_adapter1 = select_backend("ideal_simulator")
        q_log1     = run_job(q_adapter1, custom_circuit, shots=args.shots)
        q_log1["fidelity"] = 1.0  # reference run — perfect match with itself by definition
        save_log(q_log1)

        generic_fidelity_fn = _make_generic_fidelity_fn(q_log1["counts"], args.shots)

        q_adapter2 = select_backend("noisy_simulator")
        q_log2     = run_job(q_adapter2, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn)
        save_log(q_log2)

        q_adapter3 = select_backend("ibm_qpu", strategy=args.strategy)
        q_log3     = run_job(q_adapter3, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn)
        save_log(q_log3)

        q_adapter4 = AWSSimulatorAdapter()
        q_log4     = run_job(q_adapter4, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn) if q_adapter4.is_available() else None
        if q_log4: save_log(q_log4)

        q_adapter5 = IonQSimulatorAdapter()
        q_log5     = run_job(q_adapter5, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn) if q_adapter5.is_available() else None
        if q_log5: save_log(q_log5)

        plot_backend_comparison(
            q_log1, q_log2, q_log3, q_log4, q_log5,
            title=f"{custom_name} (custom) — {args.shots} shots",
            filename=os.path.join(RESULTS_DIR, "custom_comparison.png")
        )

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

    if run_vqe:
        print("\nVQE H₂ (Z-basis partial energy estimate):")
        print(f"  Exact ground state:      -1.1372 Hartree (full, requires X/Y basis)")
        print(f"  Z-basis estimate limit:  -0.7432 Hartree (this benchmark)")
        print(f"  Missing XX+YY terms:     ~0.3940 Hartree")
        for log in [l for l in [v_log1, v_log2, v_log3, v_log4, v_log5] if l]:
            print(f"  {log['backend']:<35} "
                  f"E = {log['energy_hartree']} Hartree  "
                  f"fidelity: {log['fidelity']*100:.2f}%")

    if custom_circuit is not None:
        print(f"\nCustom QASM: {custom_name}")
        for log in [l for l in [q_log1, q_log2, q_log3, q_log4, q_log5] if l]:
            print(f"  {log['backend']:<35} fidelity: {log['fidelity']*100:.2f}%  "
                  f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")

    print("\n=== Done ===")