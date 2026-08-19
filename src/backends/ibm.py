from qiskit import transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
from .base import BackendAdapter
from circuits.bell import compute_fidelity
import time
import os
from dotenv import load_dotenv

load_dotenv()

ABSOLUTE_TIMEOUT_S = 1800  # 30 minutes
ESTIMATED_EXEC_S   = 10    # fallback estimate (seconds) — used only if no circuit
                           # is available yet to measure (see estimate_exec_s below)

# Rough proportional model of real QPU execution time, calibrated against the
# empirical finding that execution on real IBM hardware is stable at ~2s for
# every circuit measured so far (Technical Decisions Log — queue-vs-execution).
# BASE_QPU_LATENCY_S covers fixed job submission/retrieval overhead; PER_GATE_S
# is a conservative per-gate contribution once transpiled. This is intentionally
# coarse (documented as a limitation): it makes the threshold a genuine function
# of the submitted circuit instead of a fixed constant, but the two constants
# below are not empirically fitted per backend.
BASE_QPU_LATENCY_S = 2.0
PER_GATE_S         = 0.05


def estimate_exec_s(circuit=None) -> float:
    """
    Estimates real QPU execution time in seconds for the given circuit.
    Falls back to the conservative ESTIMATED_EXEC_S constant if no circuit
    is provided (e.g. a caller that hasn't wired the circuit through yet).
    """
    if circuit is None:
        return ESTIMATED_EXEC_S
    return round(BASE_QPU_LATENCY_S + circuit.depth() * PER_GATE_S, 2)


# ─────────────────────────────────────────
# STANDALONE FUNCTIONS — used by orchestrator
# ─────────────────────────────────────────

def connect_ibm():
    """Connects to IBM Quantum and returns the service object."""
    api_key  = os.getenv("IBM_API_KEY")
    instance = os.getenv("IBM_INSTANCE")
    if not api_key:
        print("[IBM] IBM_API_KEY not found in .env")
        return None
    try:
        service = QiskitRuntimeService(
            channel="ibm_cloud",
            token=api_key,
            instance=instance
        )
        return service
    except Exception as e:
        print(f"[IBM] Connection failed: {e}")
        return None


def pick_best_ibm_backend(service, circuit=None):
    """
    Autonomously selects the best available IBM backend.
    Criteria: operational + minimum pending jobs.

    circuit: the circuit about to be submitted. When provided, the returned
    execution estimate is a real function of this circuit (see
    estimate_exec_s) instead of the fixed ESTIMATED_EXEC_S constant — this is
    what makes the fallback threshold in select_backend() proportional to the
    job, not a hardcoded cutoff.

    Returns (backend, estimated_exec_s, pending_jobs) or (None, 0, 0).
    """
    exec_s = estimate_exec_s(circuit)
    try:
        # Fetch each backend's status once — b.status() is a network round-trip
        # to IBM, so calling it twice (operational + pending_jobs) doubled the
        # queries. Cache the status object and read both fields from it.
        statuses   = [(b, b.status()) for b in service.backends()]
        candidates = [
            (b, s.pending_jobs)
            for b, s in statuses
            if s.operational
        ]
        if not candidates:
            print("[IBM] No operational backend available")
            return None, exec_s, 0

        candidates.sort(key=lambda x: x[1])
        best, pending = candidates[0]

        print(f"[IBM] Available backends (sorted by queue):")
        for b, p in candidates:
            marker = " <- selected" if b.name == best.name else ""
            print(f"       {b.name:<30} pending: {p}{marker}")

        return best, exec_s, pending

    except Exception as e:
        print(f"[IBM] Backend selection error: {e}")
        return None, exec_s, 0


def _run_on_qpu(circuit, backend, backend_name, shots, timeout_s=ABSOLUTE_TIMEOUT_S):
    """
    Core QPU execution logic — shared by all IBM QPU adapters.
    Raises RuntimeError on timeout or job failure.
    """
    transpiled = transpile(circuit, backend=backend, optimization_level=1)
    print(f"[IBM QPU] Transpiled — depth: {transpiled.depth()}, "
          f"gates: {transpiled.size()}, qubits: {transpiled.num_qubits}")

    sampler  = Sampler(backend)
    t_submit = time.time()
    job      = sampler.run([transpiled], shots=shots)
    print(f"[IBM QPU] Job submitted — ID: {job.job_id()}")
    print(f"[IBM QPU] Polling every 10s (timeout: {timeout_s // 60} min)...")

    while True:
        status  = job.status()
        elapsed = time.time() - t_submit
        print(f"[IBM QPU] Status: {status}  ({int(elapsed)}s elapsed)")

        if status in ("DONE", "ERROR", "CANCELLED"):
            break

        if elapsed > timeout_s:
            print(f"[IBM QPU] Timeout reached ({timeout_s}s) — cancelling job")
            try:
                job.cancel()
            except Exception:
                pass
            raise RuntimeError("IBM QPU job timed out")

        time.sleep(10)

    if status != "DONE":
        raise RuntimeError(f"IBM QPU job ended with status: {status}")

    pub_result = job.result()[0]
    register   = list(pub_result.data)[0]
    counts     = dict(getattr(pub_result.data, register).get_counts())

    try:
        metrics    = job.metrics()
        exec_time  = round(metrics.get("usage", {}).get("seconds", 10), 1)
        queue_time = round((time.time() - t_submit) - exec_time, 1)
    except Exception:
        exec_time  = 10.0
        queue_time = round((time.time() - t_submit) - exec_time, 1)

    return {
        "backend":          backend_name,
        "shots":            shots,
        "counts":           counts,
        "execution_time_s": exec_time,
        "queue_time_s":     max(0, queue_time),
        "fidelity":         compute_fidelity(counts, shots),
    }


# ─────────────────────────────────────────
# ADAPTERS
# ─────────────────────────────────────────

class IBMSimulatorAdapter(BackendAdapter):
    """Local Aer simulator — ideal or noisy."""

    def __init__(self, noisy: bool = False):
        self._noisy   = noisy
        self._backend = AerSimulator(
            noise_model=self._build_noise_model() if noisy else None
        )

    @staticmethod
    def _build_noise_model():
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

    @property
    def name(self) -> str:
        return "noisy_simulator" if self._noisy else "ideal_simulator"

    def is_available(self) -> bool:
        return True

    def estimated_queue_s(self) -> float:
        return 0.0

    def run(self, circuit, shots=1024) -> dict:
        t      = time.time()
        result = self._backend.run(circuit, shots=shots).result()
        counts = result.get_counts()
        return {
            "backend":          self.name,
            "shots":            shots,
            "counts":           counts,
            "execution_time_s": round(time.time() - t, 3),
            "queue_time_s":     0,
            "fidelity":         compute_fidelity(counts, shots),
        }


class IBMQPUAdapter(BackendAdapter):
    """
    Real IBM QPU.
    Used by both 'responsive' and 'accurate' strategies.
    Receives backend and service from orchestrator — no internal connection logic.
    """

    def __init__(self, backend, service, queue_estimate_s: float = 0.0):
        self._backend = backend
        self._service = service
        # Estimate computed by pick_best_ibm_backend/select_backend at
        # selection time (pending_jobs * 60) — stored here so the interface
        # method below reports the real number the orchestrator acted on,
        # instead of the placeholder 0.0 every adapter used to return
        # regardless of provider (queue decisions happen *before* an adapter
        # is constructed, so this is informational/for logging, not the
        # value select_backend() itself branches on).
        self._queue_estimate_s = queue_estimate_s

    @property
    def name(self) -> str:
        return f"ibm_qpu_{self._backend.name}" if self._backend else "ibm_qpu_unavailable"

    def is_available(self) -> bool:
        return self._backend is not None

    def estimated_queue_s(self) -> float:
        return self._queue_estimate_s

    def run(self, circuit, shots=1024) -> dict:
        return _run_on_qpu(circuit, self._backend, self.name, shots,
                           timeout_s=ABSOLUTE_TIMEOUT_S)


class IBMQPUAdapterAdaptive(IBMQPUAdapter):
    """
    Real IBM QPU — adaptive strategy.
    Waits up to ABSOLUTE_TIMEOUT_S, then falls back to noisy simulator automatically.
    Unlike IBMQPUAdapter, never raises — always returns a result.
    """

    def run(self, circuit, shots=1024) -> dict:
        try:
            return _run_on_qpu(circuit, self._backend, self.name, shots,
                               timeout_s=ABSOLUTE_TIMEOUT_S)
        except RuntimeError:
            print("[IBM QPU Adaptive] Timeout — falling back to noisy simulator")
            return IBMSimulatorAdapter(noisy=True).run(circuit, shots)