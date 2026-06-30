"""
Shots efficiency benchmark — with multiple replicas per shot count
to average out simulator stochastic noise and reveal true convergence.
"""

from circuits.bell import create_bell_circuit, compute_fidelity
from circuits.ghz   import create_ghz_circuit, compute_fidelity_ghz
from backends.ibm   import IBMSimulatorAdapter
import matplotlib.pyplot as plt
import numpy as np
import json
import time

SHOT_VALUES = [128, 256, 512, 1024, 2048, 4096]
N_REPLICAS  = 10  # repeat each shot count N times and average


def run_shots_efficiency(circuit, fidelity_fn, label, noisy: bool = True):
    """
    Runs the given circuit at each shot count N_REPLICAS times,
    records mean and standard deviation of fidelity.
    """
    adapter = IBMSimulatorAdapter(noisy=noisy)
    results = []

    print(f"\n=== Shots efficiency — {label} ({N_REPLICAS} replicas per point) ===")

    for shots in SHOT_VALUES:
        fidelities = []
        t_total = time.time()

        for _ in range(N_REPLICAS):
            result = adapter.run(circuit, shots=shots)
            fid    = fidelity_fn(result["counts"], shots)
            fidelities.append(fid)

        mean_fid = np.mean(fidelities)
        std_fid  = np.std(fidelities)
        elapsed  = round((time.time() - t_total) / N_REPLICAS, 4)

        print(f"Shots: {shots:<6} Mean fidelity: {mean_fid*100:.2f}%  "
              f"Std: {std_fid*100:.3f}%  Avg exec: {elapsed}s")

        results.append({
            "circuit":          label,
            "shots":            shots,
            "fidelity_mean":    round(mean_fid, 4),
            "fidelity_std":     round(std_fid, 4),
            "execution_time_s": elapsed,
            "n_replicas":       N_REPLICAS,
        })

    return results


def plot_comparison(bell_results, ghz_results, filename="results/shots_efficiency.png"):
    """
    Plots mean fidelity vs shots with error bars (std dev) for both circuits.
    """
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.suptitle("Quantum Orchestrator — Shots Efficiency: Bell vs GHZ",
                 fontsize=14, fontweight='bold')

    bell_shots = [r["shots"] for r in bell_results]
    bell_mean  = [r["fidelity_mean"] * 100 for r in bell_results]
    bell_std   = [r["fidelity_std"] * 100 for r in bell_results]

    ghz_shots  = [r["shots"] for r in ghz_results]
    ghz_mean   = [r["fidelity_mean"] * 100 for r in ghz_results]
    ghz_std    = [r["fidelity_std"] * 100 for r in ghz_results]

    ax.errorbar(bell_shots, bell_mean, yerr=bell_std, marker='o', color='#2196F3',
               linewidth=2, capsize=4, label='Bell (2 qubits)')
    ax.errorbar(ghz_shots, ghz_mean, yerr=ghz_std, marker='s', color='#9C27B0',
               linewidth=2, capsize=4, label='GHZ (3 qubits)')

    ax.set_xscale('log', base=2)
    ax.set_xlabel("Shots (log scale)")
    ax.set_ylabel("Mean fidelity (%)  ±  std dev")
    ax.set_title(f"Fidelity convergence — {N_REPLICAS} replicas per point, error bars = std dev")
    ax.grid(True, alpha=0.3)
    ax.set_xticks(bell_shots)
    ax.set_xticklabels(bell_shots)
    ax.legend()

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\n[GRAPH] Saved to {filename}")
    plt.show()


def save_results(results, path="results/shots_efficiency.json"):
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[LOG] Saved to {path}")


if __name__ == "__main__":
    bell = create_bell_circuit()
    ghz  = create_ghz_circuit(n_qubits=3)

    bell_results = run_shots_efficiency(bell, compute_fidelity, "bell", noisy=True)
    ghz_results  = run_shots_efficiency(ghz, compute_fidelity_ghz, "ghz", noisy=True)

    all_results = bell_results + ghz_results
    save_results(all_results)
    plot_comparison(bell_results, ghz_results)

    # ── Statistical analysis ────────────────────────────────────────
    print("\n=== Convergence analysis (mean ± std) ===")
    bell_gap = (bell_results[-1]["fidelity_mean"] - ghz_results[-1]["fidelity_mean"]) * 100
    print(f"Bell final: {bell_results[-1]['fidelity_mean']*100:.2f}% ± {bell_results[-1]['fidelity_std']*100:.3f}%")
    print(f"GHZ final:  {ghz_results[-1]['fidelity_mean']*100:.2f}% ± {ghz_results[-1]['fidelity_std']*100:.3f}%")
    print(f"Gap (Bell - GHZ) at 4096 shots: {bell_gap:.2f}%")

    # Check if std dev shrinks with more shots (true convergence signal)
    bell_std_trend = [r["fidelity_std"] for r in bell_results]
    ghz_std_trend  = [r["fidelity_std"] for r in ghz_results]
    print(f"\nBell std dev trend (128→4096 shots): {[round(s*100,3) for s in bell_std_trend]}")
    print(f"GHZ std dev trend (128→4096 shots):  {[round(s*100,3) for s in ghz_std_trend]}")