from .base import BackendAdapter
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
        from braket.circuits import Circuit as BraketCircuit

        # Convert Qiskit circuit to Braket circuit
        braket_circuit = self._qiskit_to_braket(circuit)

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

    @staticmethod
    def _qiskit_to_braket(qiskit_circuit):
        """
        Converts a Qiskit QuantumCircuit to a Braket Circuit.
        Handles H and CNOT gates — sufficient for Bell state.
        For more complex circuits, use qiskit-braket-provider.
        """
        from braket.circuits import Circuit, gates

        braket_circuit = Circuit()
        n_qubits = qiskit_circuit.num_qubits

        for instruction in qiskit_circuit.data:
            gate_name = instruction.operation.name
            qubits    = [qiskit_circuit.find_bit(q).index for q in instruction.qubits]

            if gate_name == 'h':
                braket_circuit.h(qubits[0])
            elif gate_name == 'cx':
                braket_circuit.cnot(qubits[0], qubits[1])
            elif gate_name == 'x':
                braket_circuit.x(qubits[0])
            elif gate_name == 'measure':
                pass  # Braket measures all qubits automatically
            else:
                print(f"[AWS] Unsupported gate: {gate_name} — skipped")

        return braket_circuit