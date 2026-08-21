"""
VQE H2 physics sanity checks.

The single most important test here — `eigvalsh(H)[0] ≈ E_EXACT` — would have
caught the mis-transcribed Hamiltonian bug immediately: the old coefficients
had a ground eigenvalue of -1.4556 Hartree, not the physical -1.1372.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from circuits.vqe_h2 import (
    E_EXACT,
    HAMILTONIAN_COEFFS,
    compute_energy_h2,
    compute_energy_h2_zdiagonal,
    _hamiltonian_matrix,
    _ansatz_statevector,
    _energy_analytical,
    _get_theta,
)

# chemical accuracy = 1.6 mHartree; allow a small multiple for tolerances
CHEM_ACC = 0.0016


def _basis_probs(psi):
    """Z-basis probabilities as Qiskit-style keys 'q1q0'."""
    return {f"{(i >> 1) & 1}{i & 1}": abs(psi[i]) ** 2 for i in range(4)}


def _apply_h_both(psi):
    """Apply Hadamard to both qubits (rotate into the X basis)."""
    H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
    I = np.eye(2, dtype=complex)
    psi = np.kron(I, H) @ psi   # qubit 0
    psi = np.kron(H, I) @ psi   # qubit 1
    return psi


def _counts_from_probs(probs, shots):
    return {k: int(round(v * shots)) for k, v in probs.items() if v > 1e-12}


class TestHamiltonian(unittest.TestCase):
    def test_ground_eigenvalue_matches_exact(self):
        """The sanity check that would have caught the mis-transcribed H."""
        ground = float(np.linalg.eigvalsh(_hamiltonian_matrix())[0].real)
        self.assertAlmostEqual(ground, E_EXACT, delta=CHEM_ACC)

    def test_single_off_diagonal_term(self):
        """The parity/Z2-reduced 2-qubit H2 has one off-diagonal term (X0X1).

        Other reductions of the same molecule do carry a symmetric XX + YY
        pair (O'Malley et al. 2016, Eq. 1, uses one); this test pins down which
        form the module implements, so a future edit cannot quietly mix the two.
        """
        self.assertIn("XX", HAMILTONIAN_COEFFS)
        self.assertNotIn("YY", HAMILTONIAN_COEFFS)


class TestAnsatz(unittest.TestCase):
    def test_reaches_ground_at_optimal_theta(self):
        theta = _get_theta()
        self.assertAlmostEqual(_energy_analytical(theta), E_EXACT, delta=CHEM_ACC)

    def test_state_lives_in_correct_sector(self):
        """Ground state must live in span{|01>, |10>}, not span{|00>, |11>}."""
        psi = _ansatz_statevector(_get_theta())
        leakage = abs(psi[0]) ** 2 + abs(psi[3]) ** 2  # |00> + |11>
        self.assertLess(leakage, 1e-6)


class TestEnergyEstimation(unittest.TestCase):
    """compute_energy_h2 on exact (noiseless) counts must recover the energy."""

    def setUp(self):
        self.shots = 1_000_000  # large -> counts approximate exact probabilities
        psi = _ansatz_statevector(_get_theta())
        self.counts_z = _counts_from_probs(_basis_probs(psi), self.shots)
        self.counts_x = _counts_from_probs(_basis_probs(_apply_h_both(psi)), self.shots)

    def test_full_energy_reaches_exact(self):
        e = compute_energy_h2(self.counts_z, self.counts_x, self.shots)
        self.assertAlmostEqual(e, E_EXACT, delta=CHEM_ACC)

    def test_zdiagonal_is_partial(self):
        """Z-diagonal alone is ~96.5% of the energy (~-1.097), not the full value."""
        e_z = compute_energy_h2_zdiagonal(self.counts_z, self.shots)
        self.assertAlmostEqual(e_z, -1.097, delta=0.005)
        self.assertGreater(e_z, E_EXACT)  # partial estimate is above the true ground


if __name__ == "__main__":
    unittest.main(verbosity=2)
