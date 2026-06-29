from qiskit import transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError
from .base import BackendAdapter
import time
import os
from dotenv import load_dotenv

load_dotenv()

ABSOLUTE_TIMEOUT_S = 1800  # 30 minutes


class IBMSimulatorAdapter(BackendAdapter):
    """Local Aer simulator — ideal or noisy."""

    def __init__(self, noisy: bool = False):
        self._noisy = noisy
        self._backend = AerSimulator(
            noise_model=self._build_noise_model() if noisy else None
        )

    @staticmethod
    def _build_noise_model():
        noise_model = NoiseModel()
        noise_model.add_all_qubit_quantum_error(
            depolarizing_error(0.001, 1), ['h', 'x', 'rx', 'ry', 'rz']
        )
        noise_model.add_all_qubit_quantum_error(
            depolarizing_error(0.01, 2), ['cx']
        )
        from qiskit_aer.noise import ReadoutError as RE
        noise_model.add_all_qubit_readout_error(
            RE([[0.98, 0.02], [0.02, 0.98]])
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
        from circuits.bell import compute_fidelity
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
    """Real IBM QPU — autonomous backend selection."""

    def __init__(self):
        self._service = None
        self._backend = None
        self._pending  = 0
        self._connect()

    def _connect(self):
        api_key  = os.getenv("IBM_API_KEY")
        instance = os.getenv("IBM_INSTANCE")
        if not api_key:
            print("[IBM] IBM_API_KEY not found in .env")
            return
        try:
            self._service = QiskitRuntimeService(
                channel="ibm_cloud",
                token=api_key,
                instance=instance
            )
            self._backend, self._pending = self._pick_best_backend()
        except Exception as e:
            print(f"[IBM] Connection failed: {e}")

    def _pick_best_backend(self):
        candidates = [
            (b, b.status().pending_jobs)
            for b in self._service.backends()
            if b.status().operational
        ]
        if not candidates:
            return None, 0
        candidates.sort(key=lambda x: x[1])
        best, pending = candidates[0]
        print(f"[IBM] Available backends (sorted by queue):")
        for b, p in candidates:
            marker = " <- selected" if b.name == best.name else ""
            print(f"       {b.name:<30} pending: {p}{marker}")
        return best, pending

    @property
    def name(self) -> str:
        return f"ibm_qpu_{self._backend.name}" if self._backend else "ibm_qpu_unavailable"

    def is_available(self) -> bool:
        return self._backend is not None

    def estimated_queue_s(self) -> float:
        return self._pending * 60  # conservative: 60s per pending job

    def run(self, circuit, shots=1024) -> dict:
        from circuits.bell import compute_fidelity
        transpiled = transpile(circuit, backend=self._backend, optimization_level=1)
        print(f"[IBM QPU] Transpiled — depth: {transpiled.depth()}, "
              f"gates: {transpiled.size()}, qubits: {transpiled.num_qubits}")

        sampler  = Sampler(self._backend)
        t_submit = time.time()
        job      = sampler.run([transpiled], shots=shots)
        print(f"[IBM QPU] Job submitted — ID: {job.job_id()}")
        print(f"[IBM QPU] Polling every 10s (timeout: {ABSOLUTE_TIMEOUT_S // 60} min)...")

        while True:
            status  = job.status()
            elapsed = time.time() - t_submit
            print(f"[IBM QPU] Status: {status}  ({int(elapsed)}s elapsed)")
            if status in ("DONE", "ERROR", "CANCELLED"):
                break
            if elapsed > ABSOLUTE_TIMEOUT_S:
                print("[IBM QPU] Absolute timeout — cancelling job")
                try:
                    job.cancel()
                except Exception:
                    pass
                raise RuntimeError("IBM QPU job timed out")
            time.sleep(10)

        if job.status() != "DONE":
            raise RuntimeError(f"IBM QPU job ended with status: {job.status()}")

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
            "backend":          self.name,
            "shots":            shots,
            "counts":           counts,
            "execution_time_s": exec_time,
            "queue_time_s":     max(0, queue_time),
            "fidelity":         compute_fidelity(counts, shots),
        }