import matplotlib.pyplot as plt
import os


def plot_backend_comparison(log1, log2, log3=None, log4=None, log5=None,
                            title="Backend Comparison",
                            filename="results/backend_comparison.png"):
    """
    Generates a bar chart comparing measurement results across backends.
    Supports 2 to 5 backends dynamically.

    Parameters:
      log1      — ideal simulator (required)
      log2      — noisy simulator (required)
      log3      — IBM QPU or fallback (optional)
      log4      — AWS local simulator (optional)
      log5      — IonQ simulator (optional)
      title     — chart subtitle, shown after "Quantum Orchestrator —"
      filename  — output path for the saved PNG
    """
    # Collect only non-None logs
    logs    = [l for l in [log1, log2, log3, log4, log5] if l]
    n_plots = len(logs)

    fig, axes = plt.subplots(1, n_plots, figsize=(6 * n_plots, 5))

    # Handle single-plot edge case
    if n_plots == 1:
        axes = [axes]
    else:
        axes = list(axes)

    fig.suptitle(f"Quantum Orchestrator — {title}", fontsize=14, fontweight='bold')

    # Auto-detect state space from counts across all logs
    # Works for both Bell (2 qubits, 4 states) and GHZ (3 qubits, 8 states)
    all_states = set()
    for log in logs:
        all_states.update(log['counts'].keys())
    states = sorted(all_states)

    # Color palette per backend slot
    # blue — ideal, orange — noisy, green — QPU, purple — AWS, red — IonQ
    palette = [
        '#2196F3',  # blue   — ideal simulator
        '#FF5722',  # orange — noisy simulator
        '#4CAF50',  # green  — IBM QPU
        '#9C27B0',  # purple — AWS
        '#F44336',  # red    — IonQ
    ]

    # Theoretical ideal count per state
    # Bell and GHZ both have 2 ideal states → shots/2 each at default 1024 shots
    shots           = log1.get('shots', 1024)
    ideal_per_state = shots / 2

    for ax, log, color in zip(axes, logs, palette):
        values = [log['counts'].get(s, 0) for s in states]
        bars   = ax.bar(states, values, color=color, edgecolor='white', linewidth=0.5)

        # Title: backend name + fidelity + queue time if relevant + exec time
        label     = log['backend'].replace('ibm_qpu_', 'QPU: ').replace('_', ' ')
        qtime     = log.get('queue_time_s', 0)
        title_str = f"{label}\nFidelity: {log['fidelity']*100:.2f}%"
        if qtime > 0:
            title_str += f"  |  Queue: {qtime}s"
        title_str += f"\nExec: {log['execution_time_s']}s"
        ax.set_title(title_str, fontsize=10)

        ax.set_xlabel("Measured state")
        ax.set_ylabel("Counts")
        ax.set_ylim(0, shots * 0.65)  # dynamic headroom above bars

        # Dashed line at theoretical ideal count per state
        ax.axhline(y=ideal_per_state, color='gray', linestyle='--',
                   alpha=0.5, label=f'Theoretical ideal ({int(ideal_per_state)})')

        # Count labels above each bar
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + shots * 0.008,
                        str(val), ha='center', va='bottom', fontsize=9)

    # Footer: fidelity deltas and noise model parameters
    parts = []

    d_noisy = (log1['fidelity'] - log2['fidelity']) * 100
    parts.append(f"Ideal→Noisy: -{d_noisy:.2f}%")

    if log3:
        d_qpu  = (log1['fidelity'] - log3['fidelity']) * 100
        q_time = log3.get('queue_time_s', 0)
        parts.append(f"Ideal→QPU: -{d_qpu:.2f}%  |  QPU queue: {q_time}s")

    if log4:
        d_aws = (log1['fidelity'] - log4['fidelity']) * 100
        parts.append(f"Ideal→AWS: -{d_aws:.2f}%")

    if log5:
        d_ionq = (log1['fidelity'] - log5['fidelity']) * 100
        parts.append(f"Ideal→IonQ: -{d_ionq:.2f}%")

    parts.append("Gate error: 0.1% (1Q) / 1% (CNOT)  |  Readout: 2%")

    fig.text(0.5, 0.01, "  |  ".join(parts), ha='center', fontsize=9, color='gray')

    plt.tight_layout(rect=[0, 0.05, 1, 1])

    # Ensure output directory exists before saving
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"[GRAPH] Saved to {filename}")
    plt.show()


if __name__ == "__main__":
    # Sample data — Bell state, replace with actual run results
    log_ideal = {
        "backend": "ideal_simulator", "shots": 1024,
        "counts": {"00": 494, "11": 530},
        "fidelity": 1.0, "queue_time_s": 0, "execution_time_s": 0.022
    }
    log_noisy = {
        "backend": "noisy_simulator", "shots": 1024,
        "counts": {"00": 508, "11": 485, "01": 16, "10": 15},
        "fidelity": 0.9697, "queue_time_s": 0, "execution_time_s": 0.010
    }
    log_qpu = {
        "backend": "ibm_qpu_ibm_marrakesh", "shots": 1024,
        "counts": {"00": 511, "11": 477, "01": 20, "10": 16},
        "fidelity": 0.9648, "queue_time_s": 11.4, "execution_time_s": 2.0
    }
    log_aws = {
        "backend": "aws_local_simulator", "shots": 1024,
        "counts": {"00": 512, "11": 512},
        "fidelity": 1.0, "queue_time_s": 0, "execution_time_s": 0.033
    }
    log_ionq = {
        "backend": "ionq_simulator", "shots": 1024,
        "counts": {"00": 509, "11": 496, "01": 9, "10": 10},
        "fidelity": 0.9814, "queue_time_s": 0, "execution_time_s": 0.5
    }

    plot_backend_comparison(log_ideal, log_noisy, log_qpu, log_aws, log_ionq,
                            title="Bell State (2 qubits)",
                            filename="results/bell_comparison.png")