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
    (this used to skip such gates and stay quiet about it, which meant the
    circuit executed on Braket was not the circuit the user submitted, while
    the fidelity was reported as if the comparison were valid).

    Measurements must be the identity map (every qubit i into classical bit i)
    or absent; a partial or remapped measurement raises UnsupportedGateError,
    because Braket samples all qubits in index order and cannot honor a custom
    measure map.

    Shared by AWSSimulatorAdapter and IonQSimulatorAdapter — both run on
    Braket devices and need the same conversion.
    """
    from braket.circuits import Circuit

    braket_circuit = Circuit()
    measurements   = []  # (qubit_index, clbit_index) pairs, validated at the end

    # Pad every qubit with an identity so idle qubits are not dropped from the
    # measurement. Braket only samples qubits that appear in the circuit, so a
    # qubit with no gate (e.g. qubit 1 in an "X on qubit 0" circuit) would be
    # omitted, yielding a count key shorter than the Qiskit reference (e.g. '1'
    # instead of '01'). Identity is a no-op for circuits where every qubit is
    # already active (Bell/GHZ/VQE), so historical data is unaffected.
    for q in range(qiskit_circuit.num_qubits):
        braket_circuit.i(q)

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
        elif gate_name == 'measure':
            # Braket samples every qubit in index order at the end, so it can't
            # honor an arbitrary measure map. Record the mapping and validate it
            # is the identity (qubit i -> classical bit i) after the loop —
            # anything else would diverge from the Qiskit reference distribution.
            clbit = qiskit_circuit.find_bit(instruction.clbits[0]).index
            measurements.append((qubits[0], clbit))
        elif gate_name == 'barrier':
            pass  # barrier has no physical effect
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

    # Fail loud if the circuit uses a non-identity measurement map. Braket
    # samples all qubits in index order, so a partial measurement or a remapped
    # classical register (e.g. `measure q[1] -> c[0];`) would misalign the count
    # bitstring against the Qiskit reference. Rather than silently produce wrong
    # fidelity, reject it — consistent with the fail-loud policy for unsupported
    # gates above. Circuits with no measurement,
    # or that measure every qubit i into classical bit i, pass through.
    if measurements:
        n        = qiskit_circuit.num_qubits
        mapping  = dict(measurements)
        identity = (len(measurements) == n
                    and len(mapping) == n
                    and all(mapping.get(i) == i for i in range(n)))
        if not identity:
            raise UnsupportedGateError(
                "Non-identity or partial measurement map is not supported on the "
                "Braket backends: Braket samples all qubits in order, so a custom "
                "measure map (measuring a subset, or remapping classical bits) "
                "would diverge from the Qiskit reference distribution. Measure "
                "every qubit with qubit i -> classical bit i, or run this circuit "
                "on the IBM backends."
            )

    return braket_circuit
