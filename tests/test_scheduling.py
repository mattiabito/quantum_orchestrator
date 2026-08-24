"""
Scheduling arithmetic, and the metric edge cases the other test files leave open.

Three groups, each closing a gap the existing suite could not reach:

  1. The fallback decision. The project's central engineering claim is that the
     threshold is a *multiple of a per-circuit execution estimate*, not a fixed
     cutoff. Nothing tested that. These tests pin the proportionality down, and
     would fail if someone quietly replaced it with a constant.

  2. Fidelity and energy on shapes the built-in circuits never produce: a GHZ
     state on more than three qubits, and a Z/X energy estimate where the two
     bases were run with different shot counts. Both are reachable through the
     public API, and both were previously untested — the n-qubit GHZ path exists
     precisely because it was once wrong.

  3. Argument validation at the CLI boundary, checked by actually running the
     CLI, because that is the only place the check lives.
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from circuits.ghz import create_ghz_circuit, compute_fidelity_ghz
from circuits.vqe_h2 import compute_energy_h2, E_EXACT
from backends.ibm import (estimate_exec_s, ESTIMATED_EXEC_S,
                          BASE_QPU_LATENCY_S, PER_DEPTH_LAYER_S)

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
_ORCHESTRATOR = os.path.join(_SRC, "orchestrator.py")


class TestExecutionEstimate(unittest.TestCase):
    """estimate_exec_s must be a real function of the circuit, not a constant."""

    def test_falls_back_to_the_constant_without_a_circuit(self):
        self.assertEqual(estimate_exec_s(None), ESTIMATED_EXEC_S)

    def test_matches_the_documented_formula(self):
        ghz = create_ghz_circuit(n_qubits=3)
        expected = BASE_QPU_LATENCY_S + ghz.depth() * PER_DEPTH_LAYER_S
        self.assertAlmostEqual(estimate_exec_s(ghz), expected, places=2)

    def test_grows_with_circuit_depth(self):
        """A deeper circuit must estimate strictly longer — the whole point."""
        shallow = estimate_exec_s(create_ghz_circuit(n_qubits=2))
        deep    = estimate_exec_s(create_ghz_circuit(n_qubits=12))
        self.assertGreater(deep, shallow)


class TestFallbackThreshold(unittest.TestCase):
    """The threshold is proportional to the job, not a fixed number of seconds."""

    @classmethod
    def setUpClass(cls):
        try:
            from orchestrator import (queue_estimate_s, fallback_threshold_s,
                                      should_fall_back, QUEUE_MULTIPLIER,
                                      SECONDS_PER_PENDING_JOB)
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"orchestrator import unavailable: {e}")
        cls.queue      = staticmethod(queue_estimate_s)
        cls.threshold  = staticmethod(fallback_threshold_s)
        cls.fall_back  = staticmethod(should_fall_back)
        cls.multiplier = QUEUE_MULTIPLIER
        cls.per_job    = SECONDS_PER_PENDING_JOB

    def test_queue_estimate_is_one_minute_per_pending_job(self):
        self.assertEqual(self.queue(0), 0)
        self.assertEqual(self.queue(1), self.per_job)
        self.assertEqual(self.queue(7), 7 * self.per_job)

    def test_threshold_scales_with_the_estimate(self):
        """Doubling the expected execution must double the patience."""
        self.assertEqual(self.threshold(2.0), 2 * self.threshold(1.0))
        self.assertEqual(self.threshold(3.0), self.multiplier * 3.0)

    def test_empty_queue_never_falls_back(self):
        self.assertFalse(self.fall_back(0, estimate_exec_s(None)))

    def test_a_long_queue_falls_back_on_a_short_job(self):
        # 60 pending jobs -> 3600 s estimated queue, against a ~2 s circuit.
        self.assertTrue(self.fall_back(60, estimate_exec_s(create_ghz_circuit(3))))

    def test_the_same_queue_is_tolerated_for_a_longer_job(self):
        """The decision must depend on the circuit, not on the queue alone.

        A queue that is rejected for a 2 s circuit has to be accepted once the
        expected execution is long enough — otherwise the threshold is a fixed
        cutoff wearing a proportional disguise.
        """
        pending = 2                                   # 120 s of estimated queue
        short   = estimate_exec_s(create_ghz_circuit(3))   # ~2.2 s
        long    = 30.0                                     # a much heavier job
        self.assertTrue(self.fall_back(pending, short))
        self.assertFalse(self.fall_back(pending, long))

    def test_crossover_is_exactly_at_the_threshold(self):
        """Equal to the threshold does not fall back; one job more does."""
        exec_s  = 3.0                                  # threshold = 60 s
        pending = int(self.threshold(exec_s) / self.per_job)
        self.assertFalse(self.fall_back(pending, exec_s))
        self.assertTrue(self.fall_back(pending + 1, exec_s))


class TestGHZBeyondThreeQubits(unittest.TestCase):
    """compute_fidelity_ghz infers the register width instead of assuming 3.

    This path exists because it was once hardcoded to '000'/'111', which scored a
    perfectly good 5-qubit GHZ state at ~0. No test covered it, and no CLI flag
    reaches it — create_ghz_circuit is called with n_qubits=3 throughout — so the
    only guard against a regression is here.
    """

    def test_perfect_five_qubit_ghz(self):
        counts = {"00000": 500, "11111": 500}
        self.assertEqual(compute_fidelity_ghz(counts, 1000), 1.0)

    def test_perfect_two_qubit_ghz(self):
        self.assertEqual(compute_fidelity_ghz({"00": 400, "11": 600}, 1000), 1.0)

    def test_leakage_on_five_qubits(self):
        counts = {"00000": 450, "11111": 450, "00001": 50, "10000": 50}
        self.assertEqual(compute_fidelity_ghz(counts, 1000), 0.9)

    def test_explicit_n_qubits_still_honoured(self):
        counts = {"00000": 500, "11111": 500}
        self.assertEqual(compute_fidelity_ghz(counts, 1000, n_qubits=5), 1.0)

    def test_empty_counts_do_not_crash(self):
        self.assertEqual(compute_fidelity_ghz({}, 1000), 0.0)

    def test_circuit_and_metric_agree_on_width(self):
        """The generated circuit and the metric must not disagree about n."""
        for n in (2, 4, 5):
            qc = create_ghz_circuit(n_qubits=n)
            self.assertEqual(qc.num_qubits, n)
            counts = {"0" * n: 500, "1" * n: 500}
            self.assertEqual(compute_fidelity_ghz(counts, 1000), 1.0)


class TestEnergyWithUnequalShots(unittest.TestCase):
    """compute_energy_h2 accepts a different shot count per basis.

    The parameter exists, the default hides it, and nothing exercised it — so a
    caller running the two bases at different depths would have had no guard.
    """

    # Exact outcome probabilities of the optimal ansatz, hardcoded so this test
    # does not depend on the theta scan running first. Z basis: |01> dominates.
    # X basis (after H on both qubits): even parity slightly favoured, which is
    # what carries the X0X1 term.
    Z_PROBS = {"01": 0.987613, "10": 0.012387}
    X_PROBS = {"00": 0.194698, "01": 0.305302,
               "10": 0.305302, "11": 0.194698}

    def _counts(self, shots, probs):
        return {k: int(round(p * shots)) for k, p in probs.items() if p > 0}

    def test_unequal_shots_match_equal_shots(self):
        """The same physics, sampled at two depths, must give the same energy."""
        equal = compute_energy_h2(self._counts(100_000, self.Z_PROBS),
                                  self._counts(100_000, self.X_PROBS), 100_000)
        unequal = compute_energy_h2(self._counts(100_000, self.Z_PROBS),
                                    self._counts(8_000, self.X_PROBS),
                                    100_000, shots_x=8_000)
        self.assertAlmostEqual(equal, E_EXACT, delta=0.001)
        self.assertAlmostEqual(unequal, E_EXACT, delta=0.001)

    def test_forgetting_shots_x_loses_the_off_diagonal_term(self):
        """Normalizing the X counts by the wrong total is not a rounding error.

        It scales <X0X1> by shots_x/shots_z, so the term that the second basis
        exists to recover — worth ~40 mHa, 3.5% of the energy — almost vanishes,
        and the estimate lands above the true ground state. This is exactly the
        failure the shots_x parameter prevents, and it is silent: the number
        still looks like a plausible energy.
        """
        counts_z = self._counts(100_000, self.Z_PROBS)
        counts_x = self._counts(8_000, self.X_PROBS)

        correct = compute_energy_h2(counts_z, counts_x, 100_000, shots_x=8_000)
        wrong   = compute_energy_h2(counts_z, counts_x, 100_000)

        self.assertAlmostEqual(correct, E_EXACT, delta=0.001)
        self.assertGreater(wrong, correct)            # above the true ground
        self.assertGreater(abs(wrong - correct), 0.03)  # most of X0X1 lost


class TestGenericFidelityWithUnequalShots(unittest.TestCase):
    """compute_fidelity_generic normalizes both distributions independently."""

    @classmethod
    def setUpClass(cls):
        try:
            from orchestrator import compute_fidelity_generic
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"orchestrator import unavailable: {e}")
        cls.fn = staticmethod(compute_fidelity_generic)

    def test_same_distribution_different_shot_counts(self):
        """A reference run at a different depth must still score 1.0."""
        observed  = {"00": 500, "11": 500}
        reference = {"00": 4000, "11": 4000}
        self.assertAlmostEqual(self.fn(observed, 1000, reference, 8000), 1.0,
                               places=4)

    def test_half_overlap_survives_unequal_shots(self):
        observed  = {"00": 1000}
        reference = {"00": 4000, "11": 4000}
        self.assertAlmostEqual(self.fn(observed, 1000, reference, 8000), 0.5,
                               places=4)


class TestUnreachableQPU(unittest.TestCase):
    """What happens when the QPU cannot be reached at all.

    This is a different situation from a queue that is merely too long, and the
    strategies must not treat it the same way. It is also not hypothetical: an
    expired IBM credential once sent a run launched with `--strategy accurate`
    straight onto a noisy simulator, and the substituted result went into the
    log looking exactly like every other row.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from orchestrator import _no_qpu
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"orchestrator import unavailable: {e}")
        cls.no_qpu = staticmethod(_no_qpu)

    def test_accurate_refuses_to_substitute(self):
        """'accurate' means only hardware will do — so it returns nothing."""
        self.assertIsNone(self.no_qpu("accurate", "IBM unreachable"))

    def test_responsive_falls_back(self):
        adapter = self.no_qpu("responsive", "IBM unreachable")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.name, "noisy_simulator")

    def test_adaptive_falls_back(self):
        self.assertIsNotNone(self.no_qpu("adaptive", "IBM unreachable"))

    def test_a_fallback_is_tagged_as_one(self):
        """The substitution has to be visible in the data, not just on screen."""
        adapter = self.no_qpu("responsive", "IBM unreachable")
        self.assertEqual(adapter.fallback_from, "ibm_qpu")

    def test_a_deliberate_simulator_is_not_tagged(self):
        """A simulator somebody asked for must stay distinguishable from a
        stand-in — otherwise the tag means nothing."""
        try:
            from orchestrator import select_backend
        except Exception as e:  # pragma: no cover
            self.skipTest(f"orchestrator import unavailable: {e}")
        chosen = select_backend("noisy_simulator")
        self.assertEqual(chosen.name, "noisy_simulator")
        self.assertIsNone(chosen.fallback_from)

    def test_run_job_skips_a_missing_adapter(self):
        """select_backend returning None must not crash the benchmark."""
        try:
            from orchestrator import run_job
        except Exception as e:  # pragma: no cover
            self.skipTest(f"orchestrator import unavailable: {e}")
        self.assertIsNone(run_job(None, create_ghz_circuit(3), shots=16))


class TestCLIArgumentValidation(unittest.TestCase):
    """--shots is validated at the boundary, not deep inside Qiskit.

    Run as a subprocess because argparse's error path calls sys.exit, and
    because the point is precisely that the CLI rejects it before any backend
    is touched.
    """

    def _run(self, *args):
        return subprocess.run([sys.executable, _ORCHESTRATOR, *args],
                              capture_output=True, text=True, timeout=180)

    def test_zero_shots_is_rejected(self):
        result = self._run("--circuit", "bell", "--shots", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--shots must be a positive integer", result.stderr)

    def test_negative_shots_is_rejected(self):
        result = self._run("--circuit", "bell", "--shots", "-5")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--shots must be a positive integer", result.stderr)

    def test_missing_qasm_file_exits_nonzero(self):
        """A typo'd filename must stop, not silently run every built-in."""
        result = self._run("--qasm", "definitely_not_a_real_file.qasm")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("CIRCUIT: Bell state", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
