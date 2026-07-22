class UnsupportedGateError(Exception):
    """Raised when a QASM circuit contains a gate that can't be converted to Braket."""
    pass


def qiskit_to_braket(qiskit_circuit):
    """
    Converts a Qiskit QuantumCircuit to a Braket Circuit.

    Named gates: h, x, y, z, s, sdg, t, tdg, rx, ry, rz, cx, cz, swap, ccx.
    Any other single-qubit gate (u, u1, u2, u3, custom gates, ...) falls
    back to a generic unitary-matrix conversion — safe because a single
    target qubit has no ordering ambiguity. Unrecognized multi-qubit gates
    raise UnsupportedGateError instead of silently dropping them, since a
    wrong qubit-ordering guess there would silently corrupt the circuit
    (see Technical Decisions Log, 22/07 — this used to skip and stay
    quiet about it, which is worse).

    Shared by AWSSimulatorAdapter and IonQSimulatorAdapter — both run on
    Braket devices and need the same conversion.
    """
    from braket.circuits import Circuit

    braket_circuit = Circuit()

    for instruction in qiskit_circuit.data:
        gate_name = instruction.operation.name
        qubits    = [qiskit_circuit.find_bit(q).index for q in instruction.qubits]

        if gate_name == 'h':
            braket_circuit.h(qubits[0])
        elif gate_name == 'x':
            braket_circuit.x(qubits[0])
        elif gate_name == 'y':
            braket_circuit.y(qubits[0])
        elif gate_name == 'z':
            braket_circuit.z(qubits[0])
        elif gate_name == 's':
            braket_circuit.s(qubits[0])
        elif gate_name == 'sdg':
            braket_circuit.si(qubits[0])
        elif gate_name == 't':
            braket_circuit.t(qubits[0])
        elif gate_name == 'tdg':
            braket_circuit.ti(qubits[0])
        elif gate_name == 'rx':
            braket_circuit.rx(qubits[0], instruction.operation.params[0])
        elif gate_name == 'ry':
            braket_circuit.ry(qubits[0], instruction.operation.params[0])
        elif gate_name == 'rz':
            braket_circuit.rz(qubits[0], instruction.operation.params[0])
        elif gate_name == 'cx':
            braket_circuit.cnot(qubits[0], qubits[1])
        elif gate_name == 'cz':
            braket_circuit.cz(qubits[0], qubits[1])
        elif gate_name == 'swap':
            braket_circuit.swap(qubits[0], qubits[1])
        elif gate_name == 'ccx':
            braket_circuit.ccnot(qubits[0], qubits[1], qubits[2])
        elif gate_name in ('measure', 'barrier'):
            pass  # measurement handled by shots-based sampling, barrier has no physical effect
        elif len(qubits) == 1:
            # Generic fallback for any other single-qubit gate (u, u1, u2, u3,
            # custom gates, ...) — no ordering ambiguity for a single target.
            try:
                matrix = instruction.operation.to_matrix()
            except Exception as e:
                raise UnsupportedGateError(
                    f"Gate '{gate_name}' has no matrix representation: {e}"
                )
            braket_circuit.unitary(matrix=matrix, targets=qubits)
            print(f"[Braket] Gate '{gate_name}' converted via generic unitary matrix")
        else:
            raise UnsupportedGateError(
                f"Gate '{gate_name}' on {len(qubits)} qubits has no named or "
                f"generic Braket conversion — refusing to silently drop it."
            )

    return braket_circuit
