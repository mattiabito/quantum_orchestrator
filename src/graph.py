import matplotlib.pyplot as plt


def plot_backend_comparison(log1, log2, log3=None, log4=None, log5=None):
    """
    Generates a bar chart comparing measurement results across backends.
    Supports 2, 3, or 4 backends.
    """
    logs    = [l for l in [log1, log2, log3, log4, log5] if l]
    n_plots = len(logs)

    fig, axes = plt.subplots(1, n_plots, figsize=(6 * n_plots, 5))
    if n_plots == 1:
        axes = [axes]
    else:
        axes = list(axes)

    fig.suptitle("Quantum Orchestrator — Backend Comparison", fontsize=14, fontweight='bold')

    states  = ['00', '01', '10', '11']
    palette = [
        ['#2196F3', '#90CAF9', '#90CAF9', '#2196F3'],  # blue   — ideal
        ['#FF5722', '#FFCCBC', '#FFCCBC', '#FF5722'],  # orange — noisy
        ['#4CAF50', '#C8E6C9', '#C8E6C9', '#4CAF50'],  # green  — QPU
        ['#9C27B0', '#E1BEE7', '#E1BEE7', '#9C27B0'],  # purple — AWS
        ['#F44336', '#FFCDD2', '#FFCDD2', '#F44336'],  # red    — Azure
    ]

    for ax, log, colors in zip(axes, logs, palette):
        values = [log['counts'].get(s, 0) for s in states]
        bars   = ax.bar(states, values, color=colors, edgecolor='white', linewidth=0.5)

        label = log['backend'].replace('ibm_qpu_', 'QPU: ').replace('_', ' ')
        qtime = log.get('queue_time_s', 0)
        title = f"{label}\nFidelity: {log['fidelity']*100:.2f}%"
        if qtime > 0:
            title += f"  |  Queue: {qtime}s"
        title += f"\nExec: {log['execution_time_s']}s"
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Measured state")
        ax.set_ylabel("Counts")
        ax.set_ylim(0, 600)
        ax.axhline(y=512, color='gray', linestyle='--', alpha=0.5, label='Theoretical ideal (512)')

        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 8,
                        str(val), ha='center', va='bottom', fontsize=10)

    # Footer
    d_noisy = (log1['fidelity'] - log2['fidelity']) * 100
    parts   = [f"Ideal→Noisy: -{d_noisy:.2f}%"]

    if log3:
        d_qpu  = (log1['fidelity'] - log3['fidelity']) * 100
        q_time = log3.get('queue_time_s', 0)
        parts.append(f"Ideal→QPU: -{d_qpu:.2f}%  |  QPU queue: {q_time}s")

    if log4:
        d_aws = (log1['fidelity'] - log4['fidelity']) * 100
        parts.append(f"Ideal→AWS: -{d_aws:.2f}%")
    
    if log5:
        d_azure = (log1['fidelity'] - log5['fidelity']) * 100
        parts.append(f"Ideal→Azure: -{d_azure:.2f}%")

    parts.append("Gate error: 0.1% (1Q) / 1% (CNOT)  |  Readout: 2%")

    fig.text(0.5, 0.01, "  |  ".join(parts), ha='center', fontsize=9, color='gray')

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig("results/backend_comparison.png", dpi=150, bbox_inches='tight')
    print("[GRAPH] Saved to results/backend_comparison.png")
    plt.show()


if __name__ == "__main__":
    # Sample data — replace with actual run results
    log_ideal = {
        "backend": "ideal_simulator", "shots": 1024,
        "counts": {"00": 494, "11": 530},
        "fidelity": 1.0, "queue_time_s": 0
    }
    log_noisy = {
        "backend": "noisy_simulator", "shots": 1024,
        "counts": {"00": 508, "11": 485, "01": 16, "10": 15},
        "fidelity": 0.9697, "queue_time_s": 0
    }
    log_qpu = {
        "backend": "ibm_qpu_ibm_kingston", "shots": 1024,
        "counts": {"00": 511, "11": 477, "01": 20, "10": 16},
        "fidelity": 0.9648, "queue_time_s": 3645.6
    }
    log_aws = {
        "backend": "aws_local_simulator", "shots": 1024,
        "counts": {"00": 512, "11": 512},
        "fidelity": 1.0, "queue_time_s": 0
    }
    plot_backend_comparison(log_ideal, log_noisy, log_qpu, log_aws)