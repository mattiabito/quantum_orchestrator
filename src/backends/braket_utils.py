def qiskit_to_braket(qiskit_circuit):
    """
    Converts a Qiskit QuantumCircuit to a Braket Circuit.
    Handles H, X, CNOT and RY gates — sufficient for Bell, GHZ and VQE H2.
    For more complex circuits, use qiskit-braket-provider.

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
        elif gate_name == 'cx':
            braket_circuit.cnot(qubits[0], qubits[1])
        elif gate_name == 'x':
            braket_circuit.x(qubits[0])
        elif gate_name == 'ry':
            angle = instruction.operation.params[0]
            braket_circuit.ry(qubits[0], angle)
        elif gate_name == 'measure':
            pass  # Braket measures all qubits automatically
        else:
            print(f"[Braket] Unsupported gate: {gate_name} — skipped")

    return braket_circuit
