import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def plot_backend_comparison(log1, log2, log3=None):
    n_plots = 3 if log3 else 2
    fig, axes = plt.subplots(1, n_plots, figsize=(6 * n_plots, 5))
    if n_plots == 2:
        axes = list(axes)  # keep indexing consistent
    fig.suptitle("Quantum Orchestrator — Backend Comparison", fontsize=14, fontweight='bold')

    states = ['00', '01', '10', '11']
    palette = [
        ['#2196F3', '#90CAF9', '#90CAF9', '#2196F3'],  # blue — ideal
        ['#FF5722', '#FFCCBC', '#FFCCBC', '#FF5722'],  # orange — noisy
        ['#4CAF50', '#C8E6C9', '#C8E6C9', '#4CAF50'],  # green — QPU
    ]
    logs = [log1, log2] + ([log3] if log3 else [])

    for i, (ax, log, colors) in enumerate(zip(axes, logs, palette)):
        values = [log['counts'].get(s, 0) for s in states]
        bars   = ax.bar(states, values, color=colors, edgecolor='white', linewidth=0.5)

        label = log['backend'].replace('ibm_qpu_', 'QPU: ').replace('_', ' ')
        qtime = log.get('queue_time_s', 0)
        title = f"{label}\nFidelity: {log['fidelity']*100:.2f}%"
        if qtime > 0:
            title += f"  |  Queue: {qtime}s"
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Measured state")
        ax.set_ylabel("Counts")
        ax.set_ylim(0, 600)
        ax.axhline(y=512, color='gray', linestyle='--', alpha=0.5)

        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 8,
                        str(val), ha='center', va='bottom', fontsize=10)

    # Footer
    degradation = (log1['fidelity'] - log2['fidelity']) * 100
    footer = (f"Noise degradation (ideal→noisy): {degradation:.2f}%  |  "
              f"Gate error: 0.1% (1Q) / 1% (CNOT)  |  Readout error: 2%")
    fig.text(0.5, 0.01, footer, ha='center', fontsize=9, color='gray')

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig("results/backend_comparison.png", dpi=150, bbox_inches='tight')
    print("[GRAPH] Saved to results/backend_comparison.png")
    plt.show()


if __name__ == "__main__":
    log_ideal = {
        "backend": "ideal_simulator", "shots": 1024,
        "counts": {"00": 514, "11": 510},
        "fidelity": 1.0, "queue_time_s": 0
    }
    log_noisy = {
        "backend": "noisy_simulator", "shots": 1024,
        "counts": {"00": 477, "11": 499, "10": 22, "01": 26},
        "fidelity": 0.9531, "queue_time_s": 0
    }
    plot_backend_comparison(log_ideal, log_noisy)