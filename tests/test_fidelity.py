"""
Fidelity functions on synthetic counts — known inputs, known outputs.

These are deterministic unit tests: no backend, no randomness. They lock in
the meaning of each fidelity metric so a future refactor can't silently
change it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from circuits.bell import compute_fidelity
from circuits.ghz import compute_fidelity_ghz
from circuits.vqe_h2 import compute_fidelity_vqe


class TestBellFidelity(unittest.TestCase):
    def test_perfect(self):
        # ideal Bell: only |00> and |11>
        self.assertEqual(compute_fidelity({"00": 500, "11": 500}, 1000), 1.0)

    def test_zero(self):
        # all leakage, no dominant states
        self.assertEqual(compute_fidelity({"01": 500, "10": 500}, 1000), 0.0)

    def test_partial(self):
        self.assertEqual(compute_fidelity({"00": 450, "11": 450, "01": 100}, 1000), 0.9)


class TestGHZFidelity(unittest.TestCase):
    def test_perfect(self):
        self.assertEqual(compute_fidelity_ghz({"000": 500, "111": 500}, 1000), 1.0)

    def test_zero(self):
        self.assertEqual(compute_fidelity_ghz({"010": 500, "101": 500}, 1000), 0.0)

    def test_partial(self):
        self.assertEqual(
            compute_fidelity_ghz({"000": 400, "111": 400, "001": 200}, 1000), 0.8
        )


class TestVQEFidelity(unittest.TestCase):
    def test_perfect(self):
        # corrected VQE ansatz: dominant states are |01> and |10>, NOT |00>/|11>
        self.assertEqual(compute_fidelity_vqe({"01": 900, "10": 100}, 1000), 1.0)

    def test_zero(self):
        # if the dominant states were the wrong (old) pair, fidelity would be 0
        self.assertEqual(compute_fidelity_vqe({"00": 500, "11": 500}, 1000), 0.0)

    def test_partial(self):
        self.assertEqual(
            compute_fidelity_vqe({"01": 850, "10": 50, "00": 100}, 1000), 0.9
        )


class TestGenericFidelity(unittest.TestCase):
    """compute_fidelity_generic lives in orchestrator.py (heavier import)."""

    @classmethod
    def setUpClass(cls):
        try:
            from orchestrator import compute_fidelity_generic
            cls.fn = staticmethod(compute_fidelity_generic)
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"orchestrator import unavailable: {e}")

    def test_self_match(self):
        counts = {"00": 250, "01": 250, "10": 250, "11": 250}
        self.assertAlmostEqual(self.fn(counts, 1000, counts, 1000), 1.0, places=4)

    def test_orthogonal(self):
        obs = {"00": 1000}
        ref = {"11": 1000}
        self.assertAlmostEqual(self.fn(obs, 1000, ref, 1000), 0.0, places=4)

    def test_half_overlap(self):
        obs = {"00": 1000}
        ref = {"00": 500, "11": 500}
        # F = (sqrt(1*0.5))^2 = 0.5
        self.assertAlmostEqual(self.fn(obs, 1000, ref, 1000), 0.5, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
