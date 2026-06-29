from qiskit import QuantumCircuit


def create_bell_circuit() -> QuantumCircuit:
    """Bell state circuit — base test for backend comparison."""
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def compute_fidelity(counts: dict, shots: int) -> float:
    """
    Bell state fidelity: ideal = 50% |00> + 50% |11>.
    Fidelity = (counts['00'] + counts['11']) / shots
    """
    correct = counts.get('00', 0) + counts.get('11', 0)
    return round(correct / shots, 4)