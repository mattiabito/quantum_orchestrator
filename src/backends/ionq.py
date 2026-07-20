from .base import BackendAdapter
from .braket_utils import qiskit_to_braket
from circuits.bell import compute_fidelity
import time


class IonQSimulatorAdapter(BackendAdapter):
    """
    IonQ trapped-ion simulator via AWS Braket density matrix simulator.

    IonQ uses trapped-ion qubits (ytterbium ions) — physically different from
    IBM's superconducting qubits. Key differences in error profile:
      - Single-qubit gate error: ~0.03%  (vs IBM ~0.1%)
      - Two-qubit gate error:    ~0.3%   (vs IBM ~1%)
      - Readout error:           ~0.5%   (vs IBM ~2%)

    Generally higher fidelity than superconducting on shallow circuits,
    but slower gate times. Different trade-off, not universally better.
    """

    def __init__(self):
        try:
            from braket.devices import LocalSimulator
            self._device    = LocalSimulator("braket_dm")  # density matrix
            self._available = True
        except ImportError:
            print("[IonQ] amazon-braket-sdk not installed")
            self._available = False
        except Exception as e:
            print(f"[IonQ] Initialization failed: {e}")
            self._available = False

    @property
    def name(self) -> str:
        return "ionq_simulator"

    def is_available(self) -> bool:
        return self._available

    def estimated_queue_s(self) -> float:
        return 0.0

    def run(self, circuit, shots=1024) -> dict:
        # Convert Qiskit circuit to Braket
        braket_circuit = qiskit_to_braket(circuit)

        # Apply IonQ realistic noise profile
        # Single-qubit depolarizing: 0.03%
        for q in range(circuit.num_qubits):
            braket_circuit.depolarizing(q, probability=0.0003)

        # Two-qubit depolarizing on CNOT gates: 0.3%
        # (was missing before — CNOT is the dominant error source on
        # entangled circuits, see Technical Decisions Log 19/07)
        for instruction in circuit.data:
            if instruction.operation.name == 'cx':
                q0, q1 = [circuit.find_bit(q).index for q in instruction.qubits]
                braket_circuit.two_qubit_depolarizing(q0, q1, probability=0.003)

        # Readout error: 0.5% bit flip on each qubit
        for q in range(circuit.num_qubits):
            braket_circuit.bit_flip(q, 0.005)

        t       = time.time()
        task    = self._device.run(braket_circuit, shots=shots)
        result  = task.result()
        elapsed = round(time.time() - t, 3)

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