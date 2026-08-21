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
        from braket.circuits import Gate
        from braket.circuits.noises import Depolarizing, TwoQubitDepolarizing

        # Convert Qiskit circuit to Braket
        braket_circuit = qiskit_to_braket(circuit)

        # Apply the IonQ noise profile INTERLEAVED with the gates, not appended
        # at the end. apply_gate_noise inserts each channel right after every
        # matching gate in the instruction stream, which fixes two problems of
        # the previous end-of-circuit approach:
        #   (a) single-qubit depolarizing is now applied once per 1q GATE, not
        #       once per qubit — so noise scales with circuit depth (a depth-100
        #       circuit no longer receives the same 1q noise as a depth-1 one);
        #   (b) two-qubit depolarizing sits between the entangling gates, so a
        #       mid-circuit error propagates through the subsequent gates instead
        #       of being tacked on after everything.
        # Error rates unchanged: 1q ~0.03%, 2q ~0.3% (CNOT/CZ/SWAP), readout ~0.5%.
        SINGLE_QUBIT_GATES = [Gate.H, Gate.X, Gate.Y, Gate.Z, Gate.S, Gate.Si,
                              Gate.T, Gate.Ti, Gate.Rx, Gate.Ry, Gate.Rz]
        TWO_QUBIT_GATES    = [Gate.CNot, Gate.CZ, Gate.Swap]

        gate_names = {instr.operation.name for instr in circuit.data}
        has_1q = bool(gate_names & {'h', 'x', 'y', 'z', 's', 'sdg',
                                    't', 'tdg', 'rx', 'ry', 'rz'})
        has_2q = bool(gate_names & {'cx', 'cz', 'swap'})

        if has_1q:
            braket_circuit.apply_gate_noise(
                Depolarizing(0.0003), target_gates=SINGLE_QUBIT_GATES)
        if has_2q:
            braket_circuit.apply_gate_noise(
                TwoQubitDepolarizing(0.003), target_gates=TWO_QUBIT_GATES)

        # ccx (Toffoli, 3 qubits) still has no two-qubit noise model — a 3-qubit
        # gate has no direct two_qubit_depolarizing equivalent, and inventing one
        # would be an unvalidated approximation.
        # Generic single-qubit gates that route to a Braket Unitary (u/u1/u2/u3
        # and custom gates via braket_utils' fallback) are likewise not covered
        # by the named-gate list above — a known, documented gap for exotic
        # custom-QASM circuits; all built-in circuits use named gates only.
        if 'ccx' in gate_names:
            print("[IonQ] Warning: ccx (Toffoli) has no two-qubit noise "
                  "model applied — result fidelity for this gate is optimistic")

        # Readout error: 0.5% bit flip on each qubit, applied last (measurement).
        for q in range(circuit.num_qubits):
            braket_circuit.bit_flip(q, 0.005)

        t       = time.time()
        task    = self._device.run(braket_circuit, shots=shots)
        result  = task.result()
        elapsed = round(time.time() - t, 3)

        # Reverse the bitstring: Braket orders qubit 0 leftmost, Qiskit
        # rightmost. Without this, asymmetric states (e.g. the VQE |01>
        # state) are mislabeled ('01' <-> '10') and bit-order-dependent
        # metrics like the VQE energy come out wrong. Bell/GHZ are
        # palindromes, so this is a no-op for them. (See braket bit-order
        # note in aws.py — same root cause, same fix.)
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