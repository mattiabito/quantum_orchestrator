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

        # Braket returns measurement counts as {tuple: count}.
        # Braket and Qiskit use opposite bit orderings: Braket puts qubit 0
        # in the leftmost bit, Qiskit in the rightmost. Reverse the bitstring
        # so the keys match the Qiskit reference distribution — otherwise any
        # asymmetric state (e.g. the VQE |01> state) is silently mislabeled
        # (e.g. '01' <-> '10'), which corrupts every bit-order-dependent
        # metric such as the VQE energy. Bell/GHZ are palindromes, so this
        # reversal is a no-op for them (their historical data is unaffected).
        counts = {
            "".join(str(b) for b in k)[::-1]: v
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