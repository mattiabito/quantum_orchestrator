from .base import BackendAdapter
from .braket_utils import qiskit_to_braket
from circuits.bell import compute_fidelity
import time


class AWSSimulatorAdapter(BackendAdapter):
    """
    AWS Braket LocalSimulator — runs locally, no AWS account needed.
    Equivalent to IBM's Aer for local testing.
    """

    def __init__(self):
        try:
            from braket.devices import LocalSimulator
            self._device = LocalSimulator()
            self._available = True
        except ImportError:
            print("[AWS] amazon-braket-sdk not installed — run: pip install amazon-braket-sdk")
            self._available = False

    @property
    def name(self) -> str:
        return "aws_local_simulator"

    def is_available(self) -> bool:
        return self._available

    def estimated_queue_s(self) -> float:
        return 0.0

    def run(self, circuit, shots=1024) -> dict:
        # Convert Qiskit circuit to Braket circuit
        braket_circuit = qiskit_to_braket(circuit)

        t      = time.time()
        task   = self._device.run(braket_circuit, shots=shots)
        result = task.result()
        elapsed = round(time.time() - t, 3)

        # Braket returns measurement counts as {tuple: count}
        # Convert to Qiskit-style string keys: '00', '11', etc.
        counts = {
            "".join(str(b) for b in k): v
            for k, v in result.measurement_counts.items()
        }

        return {
            "backend":          self.name,
            "shots":            shots,
            "counts":           counts,
            "execution_time_s": elapsed,
            "queue_time_s":     0,
            "fidelity":         compute_fidelity(counts, shots),
        }