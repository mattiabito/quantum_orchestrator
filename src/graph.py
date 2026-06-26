import matplotlib.pyplot as plt

def plot_backend_comparison(log1, log2):
    """
    Generates a bar chart comparing the results of two backends.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Quantum Orchestrator — Backend Comparison", fontsize=14, fontweight='bold')

    states = ['00', '01', '10', '11']
    colors_ideal = ['#2196F3', '#90CAF9', '#90CAF9', '#2196F3']
    colors_noisy = ['#FF5722', '#FFCCBC', '#FFCCBC', '#FF5722']

    # Plot 1: ideal simulator
    values1 = [log1['counts'].get(s, 0) for s in states]
    bars1 = axes[0].bar(states, values1, color=colors_ideal, edgecolor='white', linewidth=0.5)
    axes[0].set_title(f"Ideal simulator\nFidelity: {log1['fidelity']*100:.2f}%", fontsize=12)
    axes[0].set_xlabel("Measured state")
    axes[0].set_ylabel("Counts (out of 1024 shots)")
    axes[0].set_ylim(0, 600)
    axes[0].axhline(y=512, color='gray', linestyle='--', alpha=0.5, label='Theoretical ideal')
    for bar, val in zip(bars1, values1):
        if val > 0:
            axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 8,
                         str(val), ha='center', va='bottom', fontsize=10)

    # Plot 2: noisy simulator
    values2 = [log2['counts'].get(s, 0) for s in states]
    bars2 = axes[1].bar(states, values2, color=colors_noisy, edgecolor='white', linewidth=0.5)
    axes[1].set_title(f"Noisy simulator (IBM noise model)\nFidelity: {log2['fidelity']*100:.2f}%", fontsize=12)
    axes[1].set_xlabel("Measured state")
    axes[1].set_ylabel("Counts (out of 1024 shots)")
    axes[1].set_ylim(0, 600)
    axes[1].axhline(y=512, color='gray', linestyle='--', alpha=0.5, label='Theoretical ideal')
    for bar, val in zip(bars2, values2):
        if val > 0:
            axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 8,
                         str(val), ha='center', va='bottom', fontsize=10)

    # Footer note
    degradation = (log1['fidelity'] - log2['fidelity']) * 100
    fig.text(0.5, 0.01,
             f"Noise degradation: {degradation:.2f}%  |  "
             f"Single-qubit gate error: 0.1%  |  Two-qubit gate error (CNOT): 1%  |  Readout error: 2%",
             ha='center', fontsize=9, color='gray')

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig("results/backend_comparison.png", dpi=150, bbox_inches='tight')
    print("[GRAPH] Saved to results/backend_comparison.png")
    plt.show()


if __name__ == "__main__":
    # Sample data from last run — update with your actual results
    log_ideal = {
        "backend": "ideal_simulator",
        "shots": 1024,
        "counts": {"00": 514, "11": 510},
        "fidelity": 1.0
    }
    log_noisy = {
        "backend": "noisy_simulator",
        "shots": 1024,
        "counts": {"00": 477, "11": 499, "10": 22, "01": 26},
        "fidelity": 0.9531
    }

    plot_backend_comparison(log_ideal, log_noisy)