"""
Qiskit <-> Braket round-trip on an ASYMMETRIC circuit.

This is the test that would have caught the endianness bug. It must use an
asymmetric state: a symmetric one (Bell |00>/|11>, GHZ |000>/|111>) is a
palindrome and maps to itself under bit reversal, so it cannot detect the
bug — which is exactly why it stayed hidden until the VQE |01> state.

Circuit: X on qubit 0 only, on 2 qubits. Qiskit reports this as '01'
(qubit 0 is the rightmost bit). The Braket adapters must report the same,
not '10'.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qiskit import QuantumCircuit


def _asymmetric_circuit():
    qc = QuantumCircuit(2, 2)
    qc.x(0)  # excite qubit 0 only -> Qiskit key '01'
    qc.measure([0, 1], [0, 1])
    return qc


def _dominant_key(counts):
    return max(counts, key=counts.get)


class TestBraketEndianness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from backends.aws import AWSSimulatorAdapter
            from backends.ionq import IonQSimulatorAdapter
            cls.AWS = AWSSimulatorAdapter
            cls.IonQ = IonQSimulatorAdapter
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"Braket SDK unavailable: {e}")

    def test_qiskit_reference_is_01(self):
        """Sanity: the Qiskit/Aer reference itself labels this state '01'."""
        try:
            from qiskit_aer import AerSimulator
        except Exception as e:  # pragma: no cover
            self.skipTest(f"Aer unavailable: {e}")
        counts = AerSimulator().run(_asymmetric_circuit(), shots=2000).result().get_counts()
        self.assertEqual(_dominant_key(counts), "01")

    def test_aws_matches_qiskit_convention(self):
        adapter = self.AWS()
        if not adapter.is_available():
            self.skipTest("AWS LocalSimulator not available")
        counts = adapter.run(_asymmetric_circuit(), shots=2000)["counts"]
        # Must be '01' (Qiskit convention), NOT '10' (raw Braket order)
        self.assertEqual(_dominant_key(counts), "01",
                         f"endianness bug: got {counts}, expected dominant '01'")

    def test_ionq_matches_qiskit_convention(self):
        adapter = self.IonQ()
        if not adapter.is_available():
            self.skipTest("IonQ simulator not available")
        counts = adapter.run(_asymmetric_circuit(), shots=2000)["counts"]
        self.assertEqual(_dominant_key(counts), "01",
                         f"endianness bug: got {counts}, expected dominant '01'")


class TestMeasurementMap(unittest.TestCase):
    """Non-identity / partial measurement maps must fail loud, not silently
    produce a misaligned distribution (Braket samples all qubits in order)."""

    @classmethod
    def setUpClass(cls):
        try:
            from backends.braket_utils import qiskit_to_braket, UnsupportedGateError
            cls.convert = staticmethod(qiskit_to_braket)
            cls.err = UnsupportedGateError
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"Braket SDK unavailable: {e}")

    def test_identity_measure_ok(self):
        qc = QuantumCircuit(2, 2)
        qc.x(0)
        qc.measure([0, 1], [0, 1])
        self.convert(qc)  # must not raise

    def test_remapped_measure_rejected(self):
        qc = QuantumCircuit(2, 2)
        qc.x(0)
        qc.measure(0, 1)
        qc.measure(1, 0)  # classical bits swapped
        with self.assertRaises(self.err):
            self.convert(qc)

    def test_partial_measure_rejected(self):
        qc = QuantumCircuit(2, 2)
        qc.x(0)
        qc.measure(0, 0)  # only qubit 0 measured
        with self.assertRaises(self.err):
            self.convert(qc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
