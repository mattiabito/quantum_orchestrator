from qiskit import QuantumCircuit


def create_ghz_circuit(n_qubits: int = 3) -> QuantumCircuit:
    """
    GHZ (Greenberger-Horne-Zeilinger) state circuit.

    Creates maximally entangled state across n qubits:
      |GHZ⟩ = (|00...0⟩ + |11...1⟩) / √2

    Ideal measurement: 50% |000⟩ + 50% |111⟩, zero all others.
    Fidelity = (counts['000'] + counts['111']) / shots

    Compared to Bell state (2 qubits, depth 3):
      - 3 qubits, depth 3
      - More sensitive to noise: errors on any qubit break the state
      - Better discriminator between backends
    """
    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def compute_fidelity_ghz(counts: dict, shots: int, n_qubits: int = 3) -> float:
    """
    GHZ fidelity: ideal = 50% |000⟩ + 50% |111⟩.
    Fidelity = (counts['000'] + counts['111']) / shots
    """
    all_zeros = '0' * n_qubits
    all_ones  = '1' * n_qubits
    correct   = counts.get(all_zeros, 0) + counts.get(all_ones, 0)
    return round(correct / shots, 4)


def circuit_info() -> dict:
    return {
        "name":        "GHZ state",
        "n_qubits":    3,
        "depth":       4,
        "description": "Maximally entangled 3-qubit state. Medium-complexity benchmark circuit."
    }