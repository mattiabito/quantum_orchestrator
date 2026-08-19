"""
VQE circuit for H2 (hydrogen molecule).

Implements the 2-qubit VQE for H2 at equilibrium bond length
(R = 0.735 Angstrom, STO-3G basis) using the parity mapping with a
2-qubit reduction via Z2 symmetries.

Qubit Hamiltonian (parity mapping + 2-qubit reduction):

    H = a_II  * II
      + a_ZI  * Z0
      + a_IZ  * Z1
      + a_ZZ  * Z0 Z1
      + a_XX  * X0 X1

Note this reduced form has a *single* off-diagonal term (X0 X1), not the
symmetric XX + YY pair. Coefficients from the canonical H2 result of
O'Malley et al., Phys. Rev. X 6, 031007 (2016) (also reproduced in the
Qiskit textbook "Simulating Molecules using VQE"). The electronic
coefficients give an electronic ground energy of -1.8573 Hartree; the
constant nuclear-repulsion term at R = 0.735 A (E_nuc = 1/R = +0.7199
Hartree in atomic units) is folded into a_II so that diagonalizing H
yields the total ground-state energy -1.1373 Hartree directly
(exact reference: -1.1372 Hartree). Verified with numpy.linalg.eigvalsh.

Ansatz: a particle-number-conserving single-excitation (Givens) circuit
that starts from the Hartree-Fock reference state |01> and rotates within
the correct symmetry sector span{|01>, |10>}:

    X(q0) -> CX(q0, q1) -> Ry(theta, q1) -> CX(q1, q0)

At the optimal angle this reaches the exact ground state, so both the
fidelity metric (leakage out of the |01>/|10> sector) and the measured
energy (-1.1373 Hartree) are physically meaningful.

Energy is estimated from measurements in two bases:
  - Z basis: gives the diagonal terms II, Z0, Z1, Z0Z1 (~96.5% of the
    energy, -1.0973 Hartree).
  - X basis (Hadamard on both qubits before measuring): gives the
    off-diagonal X0X1 term (the remaining ~3.5%, -0.040 Hartree).
Summing both recovers the full energy to chemical accuracy.
"""

from qiskit import QuantumCircuit
import numpy as np


# Bond length and nuclear repulsion (atomic units: E_nuc = 1/R_bohr).
BOND_LENGTH_ANGSTROM = 0.735
_BOHR_PER_ANGSTROM   = 1.0 / 0.52917721
NUCLEAR_REPULSION    = 1.0 / (BOND_LENGTH_ANGSTROM * _BOHR_PER_ANGSTROM)  # +0.7199 Ha

# 2-qubit reduced H2 Hamiltonian coefficients.
# Electronic part: O'Malley et al., Phys. Rev. X 6, 031007 (2016), R = 0.735 A.
# The nuclear-repulsion constant is folded into the identity term so that
# the eigenvalues of H are already total energies (electronic + nuclear).
_A_II_ELECTRONIC = -1.05237
HAMILTONIAN_COEFFS = {
    "II": _A_II_ELECTRONIC + NUCLEAR_REPULSION,  # -0.33240 (electronic + nuclear)
    "ZI":  0.39793,   # Z on qubit 0
    "IZ": -0.39793,   # Z on qubit 1
    "ZZ": -0.01128,
    "XX":  0.18093,   # single off-diagonal term (no YY in the reduced form)
}

E_EXACT = -1.1372  # Hartree — exact H2 ground-state energy (full CI, STO-3G)


# ── Reference statevector simulation (numpy only) ─────────────────────
# Used to find the optimal angle analytically and deterministically,
# without Aer or scipy (both heavy/fragile on Windows — see Technical
# Decisions Log). Qubit ordering follows Qiskit's little-endian
# convention: basis index i encodes qubit 0 in the least-significant bit.

_I = np.eye(2, dtype=complex)
_X = np.array([[0, 1], [1, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)


def _pauli_term(key: str) -> np.ndarray:
    """4x4 matrix for a 2-qubit Pauli string 'AB' (A on qubit 0, B on qubit 1)."""
    m = {"I": _I, "X": _X, "Z": _Z}
    # little-endian: qubit 0 is the inner (least-significant) factor
    return np.kron(m[key[1]], m[key[0]])


def _hamiltonian_matrix() -> np.ndarray:
    H = np.zeros((4, 4), dtype=complex)
    for key, coeff in HAMILTONIAN_COEFFS.items():
        H += coeff * _pauli_term(key)
    return H


def _ry(theta: float) -> np.ndarray:
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([[c, -s], [s, c]], dtype=complex)


def _cx(ctrl: int, tgt: int) -> np.ndarray:
    M = np.zeros((4, 4), dtype=complex)
    for i in range(4):
        bits = [(i >> 0) & 1, (i >> 1) & 1]  # bits[0]=qubit0, bits[1]=qubit1
        if bits[ctrl] == 1:
            bits[tgt] ^= 1
        j = (bits[1] << 1) | bits[0]
        M[j, i] = 1
    return M


def _ansatz_statevector(theta: float) -> np.ndarray:
    """Ideal statevector produced by the ansatz X(0)->CX(0,1)->Ry(t,1)->CX(1,0)."""
    psi = np.array([1, 0, 0, 0], dtype=complex)  # |00>
    psi = np.kron(_I, _X) @ psi          # X on qubit 0  -> |01> (Hartree-Fock)
    psi = _cx(0, 1) @ psi                # CX control 0, target 1
    psi = np.kron(_ry(theta), _I) @ psi  # Ry(theta) on qubit 1
    psi = _cx(1, 0) @ psi                # CX control 1, target 0
    return psi


def _energy_analytical(theta: float) -> float:
    """Exact <psi(theta)|H|psi(theta)> from the ideal statevector (numpy)."""
    psi = _ansatz_statevector(theta)
    H   = _hamiltonian_matrix()
    return float((psi.conj() @ H @ psi).real)


_OPTIMAL_THETA = None


def _get_optimal_theta() -> float:
    """
    Finds the optimal ansatz angle by scanning the analytical energy.

    Deterministic and instant (pure numpy, no Aer/scipy). Replaces the
    previous approach that ran 100 stochastic 8192-shot Aer jobs at import
    time (see Technical Decisions Log).
    """
    thetas   = np.linspace(-np.pi, np.pi, 4001)
    energies = [_energy_analytical(t) for t in thetas]
    idx      = int(np.argmin(energies))
    theta_opt = float(thetas[idx])
    print(f"[VQE] Optimal theta: {theta_opt:.5f} rad")
    print(f"[VQE] Ideal energy at optimum: {energies[idx]:.4f} Hartree "
          f"(exact: {E_EXACT} Hartree)")
    return theta_opt


def _get_theta() -> float:
    global _OPTIMAL_THETA
    if _OPTIMAL_THETA is None:
        _OPTIMAL_THETA = _get_optimal_theta()
    return _OPTIMAL_THETA


# ── Circuit construction ──────────────────────────────────────────────

def create_vqe_h2_circuit(theta: float = None, basis: str = "z") -> QuantumCircuit:
    """
    Creates the VQE ansatz circuit for H2.

    State preparation (particle-conserving single-excitation / Givens):
        X(q0) -> CX(q0, q1) -> Ry(theta, q1) -> CX(q1, q0)

    Starts from the Hartree-Fock reference |01> and rotates within the
    span{|01>, |10>} sector that contains the true ground state. At the
    optimal angle it reaches the exact ground state.

    basis:
      "z" — measure directly (diagonal terms II, Z0, Z1, Z0Z1).
      "x" — Hadamard on both qubits before measuring (off-diagonal X0X1).

    Uses only x / cx / ry / h gates, so it converts cleanly to Braket for
    the AWS and IonQ backends (no controlled-Ry, which braket_utils does
    not support).
    """
    if theta is None:
        theta = _get_theta()

    qc = QuantumCircuit(2, 2)
    qc.x(0)              # Hartree-Fock reference |01>
    qc.cx(0, 1)
    qc.ry(theta, 1)
    qc.cx(1, 0)

    if basis == "x":
        qc.h(0)
        qc.h(1)
    elif basis != "z":
        raise ValueError(f"basis must be 'z' or 'x', got {basis!r}")

    qc.measure([0, 1], [0, 1])
    return qc


# ── Metrics ────────────────────────────────────────────────────────────

def compute_fidelity_vqe(counts: dict, shots: int) -> float:
    """
    VQE H2 fidelity: fraction of shots in the dominant states |01> and |10>.

    At the optimal angle the ansatz produces a state in span{|01>, |10>}.
    Noise causes leakage into |00> and |11>, so this fraction is a direct
    circuit-quality proxy.
    """
    correct = counts.get("01", 0) + counts.get("10", 0)
    return round(correct / shots, 4)


def _expectations_z(counts: dict, shots: int):
    """<Z0>, <Z1>, <Z0 Z1> from Z-basis counts (keys 'q1q0', Qiskit order)."""
    exp_z0 = exp_z1 = exp_zz = 0.0
    for key, n in counts.items():
        q1, q0 = int(key[0]), int(key[1])
        s0 = 1 - 2 * q0   # +1 if qubit0==0 else -1
        s1 = 1 - 2 * q1
        p  = n / shots
        exp_z0 += s0 * p
        exp_z1 += s1 * p
        exp_zz += (s0 * s1) * p
    return exp_z0, exp_z1, exp_zz


def _expectation_xx(counts_x: dict, shots: int) -> float:
    """<X0 X1> from X-basis counts (parity after Hadamard rotation)."""
    exp = 0.0
    for key, n in counts_x.items():
        q1, q0 = int(key[0]), int(key[1])
        parity = 1 - 2 * ((q0 + q1) & 1)  # +1 even, -1 odd
        exp += parity * (n / shots)
    return exp


def compute_energy_h2(counts_z: dict, counts_x: dict,
                      shots_z: int, shots_x: int = None) -> float:
    """
    Full H2 ground-state energy from measurements in two bases.

    Z basis  -> II, Z0, Z1, Z0Z1 (diagonal terms).
    X basis  -> X0X1 (single off-diagonal term).

    Returns total energy in Hartree (electronic + nuclear repulsion,
    since the constant is folded into HAMILTONIAN_COEFFS["II"]).
    At the optimal angle on a noiseless backend this is -1.1373 Hartree.
    """
    if shots_x is None:
        shots_x = shots_z
    exp_z0, exp_z1, exp_zz = _expectations_z(counts_z, shots_z)
    exp_xx                 = _expectation_xx(counts_x, shots_x)

    energy = (HAMILTONIAN_COEFFS["II"]
              + HAMILTONIAN_COEFFS["ZI"] * exp_z0
              + HAMILTONIAN_COEFFS["IZ"] * exp_z1
              + HAMILTONIAN_COEFFS["ZZ"] * exp_zz
              + HAMILTONIAN_COEFFS["XX"] * exp_xx)
    return round(float(energy), 4)


def compute_energy_h2_zdiagonal(counts_z: dict, shots_z: int) -> float:
    """
    Partial energy from the Z basis alone (diagonal terms only).

    Reported alongside the full energy to show how much of the total the
    Z basis already captures (~96.5%, -1.0973 Hartree) and how much the
    X0X1 term contributes (~3.5%). Not the physical ground energy on its
    own — use compute_energy_h2 for that.
    """
    exp_z0, exp_z1, exp_zz = _expectations_z(counts_z, shots_z)
    energy = (HAMILTONIAN_COEFFS["II"]
              + HAMILTONIAN_COEFFS["ZI"] * exp_z0
              + HAMILTONIAN_COEFFS["IZ"] * exp_z1
              + HAMILTONIAN_COEFFS["ZZ"] * exp_zz)
    return round(float(energy), 4)


def circuit_info() -> dict:
    return {
        "name":        "VQE H2",
        "n_qubits":    2,
        "depth":       5,
        "description": "Single-excitation (Givens) VQE ansatz for H2 from the "
                       "Hartree-Fock reference (parity mapping, 2-qubit reduction). "
                       "Hamiltonian: O'Malley et al., Phys. Rev. X 2016. "
                       f"Reference energy: {E_EXACT} Hartree.",
    }
