from .base import BackendAdapter
from circuits.bell import compute_fidelity
import time


class AzureSimulatorAdapter(BackendAdapter):
    """
    Azure Quantum local simulator — runs locally, no Azure account needed.
    Uses azure-quantum with the built-in sparse state simulator.
    """

    def __init__(self):
        try:
            from azure.quantum.qiskit import AzureQuantumProvider
            # Local simulator — no credentials needed
            self._provider  = AzureQuantumProvider(resource_id="", location="eastus")
            self._backend   = self._provider.get_backend("microsoft.simulator.sparse")
            self._available = True
        except ImportError:
            print("[Azure] azure-quantum not installed — "
                  "run: pip install azure-quantum")
            self._available = False
        except Exception as e:
            print(f"[Azure] Initialization failed: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "azure_local_simulator"

    def is_available(self) -> bool:
        return self._available

    def estimated_queue_s(self) -> float:
        return 0.0

    def run(self, circuit, shots=1024) -> dict:
        from qiskit import transpile

        transpiled = transpile(circuit, backend=self._backend)
        t          = time.time()
        job        = self._backend.run(transpiled, shots=shots)
        result     = job.result()
        elapsed    = round(time.time() - t, 3)

        counts = result.get_counts()

        return {
            "backend":          self.name,
            "shots":            shots,
            "counts":           counts,
            "execution_time_s": elapsed,
            "queue_time_s":     0,
            "fidelity":         compute_fidelity(counts, shots),
        }