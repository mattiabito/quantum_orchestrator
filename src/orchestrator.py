import sys

# Force UTF-8 stdout/stderr regardless of the terminal/redirect target.
# Without this, Windows falls back to the system codepage (cp1252) whenever
# output isn't an interactive console (e.g. redirected to a file), which
# can't encode the circuit-diagram box-drawing characters or symbols like
# "H2" and crashes with UnicodeEncodeError.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from circuits.bell import create_bell_circuit
from circuits.ghz  import create_ghz_circuit, compute_fidelity_ghz
from backends.ibm import (IBMSimulatorAdapter, IBMQPUAdapter,
                           IBMQPUAdapterAdaptive, connect_ibm,
                           pick_best_ibm_backend, ABSOLUTE_TIMEOUT_S)
from backends.aws  import AWSSimulatorAdapter
from backends.ionq import IonQSimulatorAdapter
from backends.braket_utils import UnsupportedGateError
from graph import plot_backend_comparison
from paths import RESULTS_DIR
import datetime
import os
import json

QUEUE_MULTIPLIER        = 20    # fall back if queue > multiplier * estimated exec
SECONDS_PER_PENDING_JOB = 60    # crude conversion from IBM's pending_jobs count


# ─────────────────────────────────────────
# SCHEDULING ARITHMETIC
# The fallback decision is three small pure functions rather than expressions
# buried inside select_backend, so it can be tested without an IBM connection —
# it is the piece of behaviour the project actually claims (a threshold
# proportional to the submitted circuit, not a fixed cutoff).
# ─────────────────────────────────────────

def queue_estimate_s(pending_jobs: int) -> float:
    """
    Converts IBM's pending_jobs count into a queue estimate, one minute per job.

    Deliberately crude, and known to be wrong in the tail: a single pending job
    once preceded a 3645 s wait. It is the only queue signal the API exposes, so
    the scheduler uses it while never trusting it as an absolute predictor —
    which is why the threshold below is proportional and an absolute timeout
    backstops every attempt.
    """
    return pending_jobs * SECONDS_PER_PENDING_JOB


def fallback_threshold_s(estimated_exec_s: float) -> float:
    """
    The queue time above which waiting stops being worth it, expressed as a
    multiple of how long the job itself is expected to take. Proportional by
    design: an absolute cutoff would be arbitrary given how unreliable the
    queue signal is.
    """
    return QUEUE_MULTIPLIER * estimated_exec_s


def should_fall_back(pending_jobs: int, estimated_exec_s: float) -> bool:
    """True when the estimated queue exceeds the proportional threshold."""
    return queue_estimate_s(pending_jobs) > fallback_threshold_s(estimated_exec_s)


def _no_qpu(strategy: str, reason: str):
    """
    Decides what to do when the real QPU cannot be reached at all — a different
    situation from a queue that is merely too long.

    'accurate' exists precisely to mean "only hardware fidelity will do", so
    substituting a simulator for it would answer a question the caller did not
    ask, and the substituted number would then sit in the log looking like every
    other row. It returns nothing instead, and the caller skips that backend.

    'responsive' and 'adaptive' do fall back — that is their documented job —
    but the resulting adapter is tagged, so the log records that this row is a
    stand-in rather than a simulator run somebody chose.
    """
    if strategy == "accurate":
        print(f"[ORCHESTRATOR] {reason} — 'accurate' will not substitute a "
              f"simulator for hardware. Skipping the QPU backend.")
        return None

    print(f"[ORCHESTRATOR] {reason} — falling back to noisy simulator "
          f"(strategy: {strategy})")
    return IBMSimulatorAdapter(noisy=True, fallback_from="ibm_qpu")


def select_backend(preference="ideal_simulator", strategy="responsive", circuit=None):
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

    circuit: the circuit about to be submitted (applies only to ibm_qpu).
      Passed through to pick_best_ibm_backend so the fallback threshold is
      computed from this specific circuit (see ibm.estimate_exec_s) rather
      than a fixed constant. Optional — if omitted, a conservative constant
      is used instead (see ibm.ESTIMATED_EXEC_S).
    """
    if preference == "ideal_simulator":
        return IBMSimulatorAdapter(noisy=False)

    elif preference == "noisy_simulator":
        return IBMSimulatorAdapter(noisy=True)

    elif preference == "ibm_qpu":
        service = connect_ibm()
        if service is None:
            return _no_qpu(strategy, "IBM unreachable (credentials or network)")

        backend, estimated_exec_s, pending = pick_best_ibm_backend(service, circuit=circuit)

        if backend is None:
            return _no_qpu(strategy, "no operational IBM backend available")

        queue_s   = queue_estimate_s(pending)
        threshold = fallback_threshold_s(estimated_exec_s)
        too_long  = should_fall_back(pending, estimated_exec_s)

        exec_source = "from circuit" if circuit is not None else "no circuit given, fallback constant"
        print(f"[ORCHESTRATOR] Strategy: {strategy.upper()}")
        print(f"[ORCHESTRATOR] Estimated exec: {estimated_exec_s}s ({exec_source})")
        print(f"[ORCHESTRATOR] Estimated queue: {queue_s}s, threshold: {threshold}s")

        if strategy == "responsive":
            if too_long:
                print(f"[ORCHESTRATOR] Queue too long — falling back to noisy simulator")
                return IBMSimulatorAdapter(noisy=True, fallback_from="ibm_qpu")
            print(f"[ORCHESTRATOR] Queue acceptable — selected: {backend.name}")
            return IBMQPUAdapter(backend, service, queue_estimate_s=queue_s)

        elif strategy == "accurate":
            print(f"[ORCHESTRATOR] Accurate mode — will wait for real QPU regardless of queue")
            return IBMQPUAdapter(backend, service, queue_estimate_s=queue_s)

        elif strategy == "adaptive":
            if too_long:
                print(f"[ORCHESTRATOR] Queue long ({queue_s}s) — will attempt QPU "
                      f"with {ABSOLUTE_TIMEOUT_S//60}min timeout before fallback")
            return IBMQPUAdapterAdaptive(backend, service, queue_estimate_s=queue_s)

        else:
            print(f"[ORCHESTRATOR] Unknown strategy '{strategy}' — using responsive")
            if too_long:
                return IBMSimulatorAdapter(noisy=True, fallback_from="ibm_qpu")
            return IBMQPUAdapter(backend, service, queue_estimate_s=queue_s)

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


def run_job(adapter, circuit, shots=1024, fidelity_fn=None) -> dict | None:
    """
    Runs the circuit on the given adapter and returns the result log, or None
    if the backend failed and was skipped (see the RuntimeError branch below).

    fidelity_fn: optional custom fidelity function — defaults to Bell state fidelity.

    adapter may be None when the requested backend could not be provided at all
    (see _no_qpu) — there is nothing to run, and the caller skips it.
    """
    if adapter is None:
        print(f"\n--- Skipping job — requested backend unavailable ---")
        return None

    print(f"\n--- Running job ---")
    print(f"Backend: {adapter.name}")
    print(f"Shots:   {shots}")

    try:
        result = adapter.run(circuit, shots=shots)
    except RuntimeError as e:
        # A real QPU job can time out or come back in a non-DONE state
        # (see backends/ibm.py:_run_on_qpu). 'responsive' and 'accurate'
        # deliberately do not auto-fallback to a simulator on this path —
        # that would silently substitute the answer — so instead of letting
        # the exception abort the whole benchmark run (every other backend
        # and circuit still queued after this one), skip just this backend
        # and let the caller continue.
        print(f"[ORCHESTRATOR] {adapter.name} failed: {e} — skipping this backend")
        return None

    # Apply custom fidelity function if provided
    if fidelity_fn is not None:
        result["fidelity"] = fidelity_fn(result["counts"], shots)

    # Record the queue estimate the scheduler acted on next to the queue time
    # actually observed. On the IBM path the fallback decision is taken one
    # level up, in select_backend(), before this adapter existed; the adapter
    # carries that number forward so every log line can be checked against
    # what really happened. That comparison is the whole point of Section 4:
    # the estimate and the outcome are not the same quantity.
    result["queue_estimate_s"] = adapter.estimated_queue_s()
    result["timestamp"]        = datetime.datetime.now().isoformat()

    # If this backend is standing in for another, say so in the record. Without
    # it a fallback row is indistinguishable from a simulator run somebody chose
    # — and a full benchmark then logs two identical-looking noisy_simulator
    # lines, which quietly double-counts in any per-backend aggregation.
    substituting = getattr(adapter, "fallback_from", None)
    if substituting:
        result["fallback_from"] = substituting
        print(f"NOTE:           this row substitutes for '{substituting}' "
              f"— not the backend that was requested")

    print(f"Counts:         {result['counts']}")
    print(f"Fidelity:       {result['fidelity'] * 100:.2f}%")
    print(f"Execution time: {result['execution_time_s']}s")
    print(f"Queue time:     {result['queue_time_s']}s "
          f"(estimated: {result['queue_estimate_s']}s)")
    return result


def save_log(log, path=None):
    """
    Appends the job result log to a JSON file.
    Each line is a valid JSON object (newline-delimited JSON / NDJSON format).
    """
    path = path or os.path.join(RESULTS_DIR, "log.jsonl")
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

    # argparse type=int accepts 0 and negatives; both reach Aer and fail deep
    # inside Qiskit with a traceback that says nothing useful to a CLI user.
    if args.shots < 1:
        parser.error(f"--shots must be a positive integer, got {args.shots}")

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
            sys.exit(1)  # don't silently fall back to running all built-in
                         # benchmarks on a typo'd/missing filename

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

        b_adapter3 = select_backend("ibm_qpu", strategy=args.strategy, circuit=bell)
        b_log3     = run_job(b_adapter3, bell, shots=args.shots)
        if b_log3: save_log(b_log3)

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

        g_adapter3 = select_backend("ibm_qpu", strategy=args.strategy, circuit=ghz)
        g_log3     = run_job(g_adapter3, ghz, shots=args.shots,
                             fidelity_fn=compute_fidelity_ghz)
        if g_log3: save_log(g_log3)

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
        # Imported here, not at module top, so a broken/missing VQE module
        # can't break bell/ghz (vqe_h2.py no longer depends on scipy since
        # the analytical theta scan replaced the stochastic search, but the
        # lazy import is kept as a general isolation guard).
        try:
            from circuits.vqe_h2 import (create_vqe_h2_circuit, compute_fidelity_vqe,
                                         compute_energy_h2, compute_energy_h2_zdiagonal,
                                         E_EXACT)
        except ImportError as e:
            print(f"[VQE] Could not import VQE module — skipping VQE benchmark: {e}")
            run_vqe = False

    if run_vqe:
        print("\n" + "=" * 50)
        print("CIRCUIT: VQE H₂ (2 qubits — single-excitation ansatz)")
        print("=" * 50)

        # Two measurement circuits share the same state preparation:
        #   Z basis -> diagonal terms II, Z0, Z1, Z0Z1 (~96.5% of the energy)
        #   X basis -> the single off-diagonal term X0X1 (the remaining ~3.5%)
        # Summing both recovers the full ground-state energy (-1.1373 Ha) to
        # chemical accuracy. The Z-basis run also carries the fidelity metric.
        vqe_z = create_vqe_h2_circuit(basis="z")
        vqe_x = create_vqe_h2_circuit(basis="x")
        print(vqe_z.draw())

        def run_vqe_backend(adapter):
            """Runs both bases on one backend, returns the Z-basis log with
            full and Z-diagonal energy attached (or None if unavailable, or
            if the QPU job itself failed/timed out — see run_job)."""
            if adapter is None or not adapter.is_available():
                return None
            log_z = run_job(adapter, vqe_z, shots=args.shots,
                            fidelity_fn=compute_fidelity_vqe)
            if log_z is None:
                return None
            try:
                result_x = adapter.run(vqe_x, shots=args.shots)
            except RuntimeError as e:
                print(f"[ORCHESTRATOR] {adapter.name} X-basis run failed: {e} — "
                      f"skipping this backend (Z-basis result discarded, energy "
                      f"needs both bases)")
                return None
            log_z["energy_hartree"]       = compute_energy_h2(
                log_z["counts"], result_x["counts"], args.shots)
            log_z["energy_zdiag_hartree"] = compute_energy_h2_zdiagonal(
                log_z["counts"], args.shots)
            print(f"Energy (Z+X):   {log_z['energy_hartree']} Hartree "
                  f"(Z-diagonal only: {log_z['energy_zdiag_hartree']})")
            save_log(log_z)
            return log_z

        v_log1 = run_vqe_backend(select_backend("ideal_simulator"))
        v_log2 = run_vqe_backend(select_backend("noisy_simulator"))
        v_log3 = run_vqe_backend(select_backend("ibm_qpu", strategy=args.strategy, circuit=vqe_z))
        v_log4 = run_vqe_backend(AWSSimulatorAdapter())
        v_log5 = run_vqe_backend(IonQSimulatorAdapter())

        plot_backend_comparison(v_log1, v_log2, v_log3, v_log4, v_log5,
                                title=f"VQE H₂ (2 qubits — Z+X basis) — {args.shots} shots",
                                filename=os.path.join(RESULTS_DIR, "vqe_comparison.png"))

    # ── Custom QASM circuit ───────────────────────────────────────
    if custom_circuit is not None:
        print("\n" + "=" * 50)
        print(f"CIRCUIT: {custom_name} (custom QASM)")
        print("=" * 50)

        # ideal_simulator runs first — its distribution is the reference
        # for a generic fidelity metric on the other backends, since a
        # custom circuit's ideal state isn't known in advance like Bell/GHZ/VQE
        # Reference run — perfect match with itself by definition. Fidelity is
        # passed as fidelity_fn (not set after the fact) so the console print
        # shows 100% immediately instead of a leftover Bell-formula value that
        # means nothing for an arbitrary circuit.
        q_adapter1 = select_backend("ideal_simulator")
        q_log1     = run_job(q_adapter1, custom_circuit, shots=args.shots,
                             fidelity_fn=lambda counts, shots: 1.0)
        save_log(q_log1)

        generic_fidelity_fn = _make_generic_fidelity_fn(q_log1["counts"], args.shots)

        q_adapter2 = select_backend("noisy_simulator")
        q_log2     = run_job(q_adapter2, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn)
        save_log(q_log2)

        q_adapter3 = select_backend("ibm_qpu", strategy=args.strategy, circuit=custom_circuit)
        q_log3     = run_job(q_adapter3, custom_circuit, shots=args.shots,
                             fidelity_fn=generic_fidelity_fn)
        if q_log3: save_log(q_log3)

        q_log4 = None
        q_adapter4 = AWSSimulatorAdapter()
        if q_adapter4.is_available():
            try:
                q_log4 = run_job(q_adapter4, custom_circuit, shots=args.shots,
                                 fidelity_fn=generic_fidelity_fn)
                save_log(q_log4)
            except UnsupportedGateError as e:
                print(f"[AWS] Skipping — {e}")

        q_log5 = None
        q_adapter5 = IonQSimulatorAdapter()
        if q_adapter5.is_available():
            try:
                q_log5 = run_job(q_adapter5, custom_circuit, shots=args.shots,
                                 fidelity_fn=generic_fidelity_fn)
                save_log(q_log5)
            except UnsupportedGateError as e:
                print(f"[IonQ] Skipping — {e}")

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
        print("\nVQE H₂ (full ground-state energy — Z + X basis):")
        print(f"  Exact ground state:      {E_EXACT} Hartree (full CI, STO-3G)")
        print(f"  Z-diagonal terms alone:  ~-1.0973 Hartree (~96.5% of the energy)")
        print(f"  X0X1 term adds:          ~-0.0400 Hartree (~3.5%, needs X basis)")
        for log in [l for l in [v_log1, v_log2, v_log3, v_log4, v_log5] if l]:
            print(f"  {log['backend']:<35} "
                  f"E = {log['energy_hartree']} Hartree  "
                  f"(Z-only: {log.get('energy_zdiag_hartree', 'n/a')})  "
                  f"fidelity: {log['fidelity']*100:.2f}%")

    if custom_circuit is not None:
        print(f"\nCustom QASM: {custom_name}")
        for log in [l for l in [q_log1, q_log2, q_log3, q_log4, q_log5] if l]:
            print(f"  {log['backend']:<35} fidelity: {log['fidelity']*100:.2f}%  "
                  f"exec: {log['execution_time_s']}s  queue: {log['queue_time_s']}s")

    print("\n=== Done ===")