"""
VQE H2 energy-convergence benchmark — energy vs shot count, with multiple
replicas per point, to show how the measured ground-state energy converges
toward the exact value and how shot noise compares to chemical accuracy.

Companion to shots_efficiency.py (which does the same for fidelity). The
energy is estimated from two measurement bases per replica:
  - Z basis: diagonal Hamiltonian terms (~96.5% of the energy)
  - X basis: the single off-diagonal X0X1 term (~3.5%)

Chemical accuracy is 1.6 mHartree (0.0016 Ha). At low shot counts the
per-run scatter is larger than this band, so a single low-shot run cannot
by itself demonstrate chemical accuracy even though the ansatz reaches it
exactly — that is the point this benchmark makes quantitatively.
"""

from circuits.vqe_h2 import (create_vqe_h2_circuit, compute_energy_h2,
                             compute_fidelity_vqe, E_EXACT)
from backends.ibm import IBMSimulatorAdapter
from backends.ionq import IonQSimulatorAdapter
from paths import RESULTS_DIR
import matplotlib.pyplot as plt
import numpy as np
import json
import os
import time

SHOT_VALUES = [128, 256, 512, 1024, 2048, 4096, 8192]
N_REPLICAS  = 10                 # repeat each shot count N times
CHEMICAL_ACCURACY = 0.0016       # Hartree (1.6 mHa)


def run_energy_convergence(adapter, label):
    """
    Runs the VQE (Z + X circuits) at each shot count N_REPLICAS times,
    recording mean and std of the measured energy and fidelity.
    """
    vqe_z = create_vqe_h2_circuit(basis="z")
    vqe_x = create_vqe_h2_circuit(basis="x")
    results = []

    print(f"\n=== VQE energy convergence — {label} "
          f"({N_REPLICAS} replicas per point) ===")

    for shots in SHOT_VALUES:
        energies, fidelities = [], []
        t_total = time.time()

        for _ in range(N_REPLICAS):
            counts_z = adapter.run(vqe_z, shots=shots)["counts"]
            counts_x = adapter.run(vqe_x, shots=shots)["counts"]
            energies.append(compute_energy_h2(counts_z, counts_x, shots))
            fidelities.append(compute_fidelity_vqe(counts_z, shots))

        mean_e, std_e = np.mean(energies), np.std(energies)
        mean_f, std_f = np.mean(fidelities), np.std(fidelities)
        elapsed       = round((time.time() - t_total) / N_REPLICAS, 4)

        # fraction of replicas landing within chemical accuracy of exact
        within = np.mean([abs(e - E_EXACT) <= CHEMICAL_ACCURACY for e in energies])

        print(f"Shots: {shots:<6} E: {mean_e:.4f} ± {std_e:.4f} Ha  "
              f"|E-exact|: {abs(mean_e - E_EXACT)*1000:.1f} mHa  "
              f"within chem.acc.: {within*100:.0f}%  "
              f"fidelity: {mean_f*100:.2f}%")

        results.append({
            "backend":         label,
            "shots":           shots,
            "energy_mean":     round(float(mean_e), 4),
            "energy_std":      round(float(std_e), 4),
            "fidelity_mean":   round(float(mean_f), 4),
            "fidelity_std":    round(float(std_f), 4),
            "frac_within_chem_acc": round(float(within), 3),
            "avg_exec_s":      elapsed,
            "n_replicas":      N_REPLICAS,
        })

    return results


def plot_energy_convergence(series, filename=None, show=False):
    """
    Plots mean energy vs shots with std-dev error bars for each backend,
    plus the exact ground energy and the chemical-accuracy band.

    series: dict {label: (results_list, color)}
    The PNG is always saved; pass show=True (CLI: --show) to also open a window.
    """
    filename = filename or os.path.join(RESULTS_DIR, "vqe_energy_convergence.png")
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.suptitle("Quantum Orchestrator — VQE H₂ Energy Convergence vs Shots",
                 fontsize=14, fontweight="bold")

    shots_axis = SHOT_VALUES

    # exact ground energy + chemical accuracy band
    ax.axhline(E_EXACT, color="black", linestyle="--", linewidth=1.2,
               label=f"Exact ground state ({E_EXACT} Ha)")
    ax.axhspan(E_EXACT - CHEMICAL_ACCURACY, E_EXACT + CHEMICAL_ACCURACY,
               color="green", alpha=0.15, label="Chemical accuracy (±1.6 mHa)")

    for label, (results, color) in series.items():
        x    = [r["shots"] for r in results]
        mean = [r["energy_mean"] for r in results]
        std  = [r["energy_std"] for r in results]
        ax.errorbar(x, mean, yerr=std, marker="o", color=color,
                    linewidth=2, capsize=4, label=label)

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Shots (log scale)")
    ax.set_ylabel("Measured energy (Hartree)  ±  std dev")
    ax.set_title(f"{N_REPLICAS} replicas per point, error bars = std dev")
    ax.grid(True, alpha=0.3)
    ax.set_xticks(shots_axis)
    ax.set_xticklabels(shots_axis)
    ax.legend()

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"\n[GRAPH] Saved to {filename}")
    if show:
        plt.show()
    plt.close()


def save_results(results, path=None):
    path = path or os.path.join(RESULTS_DIR, "vqe_energy_convergence.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[LOG] Saved to {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VQE H2 energy convergence benchmark")
    parser.add_argument("--show", action="store_true",
                        help="Open the plot in a window (PNG is always saved)")
    args = parser.parse_args()

    # Local, free, deterministic backends — the core convergence story.
    # (Real QPU replicas cost quota; run those via the orchestrator and add
    # the point manually if desired.)
    ideal_results = run_energy_convergence(
        IBMSimulatorAdapter(noisy=False), "ideal_simulator")
    noisy_results = run_energy_convergence(
        IBMSimulatorAdapter(noisy=True), "noisy_simulator")

    series = {
        "ideal_simulator": (ideal_results, "#2196F3"),
        "noisy_simulator": (noisy_results, "#FF5722"),
    }

    # IonQ is also a local Braket simulator — include it if available.
    ionq = IonQSimulatorAdapter()
    if ionq.is_available():
        ionq_results = run_energy_convergence(ionq, "ionq_simulator")
        series["ionq_simulator"] = (ionq_results, "#E91E63")
    else:
        ionq_results = []

    all_results = ideal_results + noisy_results + ionq_results
    save_results(all_results)
    plot_energy_convergence(series, show=args.show)

    # ── Convergence analysis ────────────────────────────────────────
    print("\n=== Energy convergence analysis (ideal simulator) ===")
    std_trend = [r["energy_std"] for r in ideal_results]
    err_trend = [abs(r["energy_mean"] - E_EXACT) for r in ideal_results]
    print(f"Std dev trend (128→8192 shots): "
          f"{[round(s*1000, 2) for s in std_trend]} mHa")
    print(f"|mean - exact| trend:           "
          f"{[round(e*1000, 2) for e in err_trend]} mHa")
    print(f"Chemical accuracy band:         ±{CHEMICAL_ACCURACY*1000:.1f} mHa")
    # first shot count where the ideal std dev drops below chemical accuracy
    below = [r["shots"] for r in ideal_results
             if r["energy_std"] <= CHEMICAL_ACCURACY]
    if below:
        print(f"Std dev first within chemical accuracy at: {below[0]} shots")
    else:
        print("Std dev never within chemical accuracy in the tested range — "
              "energy scatter stays above 1.6 mHa even at 8192 shots.")
