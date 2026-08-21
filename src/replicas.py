"""
Reference replica benchmark — fixed condition, many replicas.

This is the script behind the n=100 reference rows in README.md and in the
article: it runs one circuit N times on one local simulator backend at a fixed
shot count and reports the mean and standard deviation of the fidelity (and,
for the VQE circuit, of the measured ground-state energy).

How this differs from the two convergence benchmarks:
  - shots_efficiency.py and vqe_energy_convergence.py *sweep* the shot count
    with 10 replicas per point, to show a trend across shot counts.
  - this script *fixes* the shot count and raises the replica count, to pin
    down a single reference value precisely enough to quote in a table.

Statistical note (worth keeping straight when reading the output):
the reported "std" is the dispersion between individual runs — a property of
the noise model at that shot count — and it does NOT shrink as N grows. What
shrinks as 1/sqrt(N) is "sem", the standard error on the mean, i.e. how well
the mean itself is pinned down. Raising N from 10 to 100 buys a solid mean,
not tighter error bars.

Usage:
    python src/replicas.py --all
    python src/replicas.py --circuit vqe --backend ionq --n 100 --shots 1024
    python src/replicas.py --all --n 20 --out results/replicas_quick.json
"""

import sys

# Same reason as orchestrator.py: Windows falls back to cp1252 whenever stdout
# is not an interactive console, which cannot encode the symbols printed below.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from circuits.bell import create_bell_circuit, compute_fidelity
from circuits.ghz import create_ghz_circuit, compute_fidelity_ghz
from circuits.vqe_h2 import (create_vqe_h2_circuit, compute_fidelity_vqe,
                             compute_energy_h2, E_EXACT)
from backends.ibm import IBMSimulatorAdapter
from backends.aws import AWSSimulatorAdapter
from backends.ionq import IonQSimulatorAdapter
from paths import RESULTS_DIR

import argparse
import datetime
import json
import os
import time

import numpy as np

DEFAULT_N     = 100
DEFAULT_SHOTS = 1024

# Only local, free, repeatable backends belong here. A real QPU replica costs
# queue time and IBM quota, so hardware numbers stay at the small sample the
# orchestrator collects run by run — see the Limitations section of the README.
BACKENDS = {
    "ideal": lambda: IBMSimulatorAdapter(noisy=False),
    "noisy": lambda: IBMSimulatorAdapter(noisy=True),
    "aws":   AWSSimulatorAdapter,
    "ionq":  IonQSimulatorAdapter,
}

CIRCUITS = ("bell", "ghz", "vqe")


def _one_replica(adapter, circuit_name, shots):
    """
    Runs the circuit once and returns (fidelity, energy_or_None).

    VQE needs two circuits per replica — the Z basis carries the fidelity and
    the diagonal Hamiltonian terms, the X basis carries the single X0X1 term —
    so a VQE replica is two backend jobs, not one.
    """
    if circuit_name == "bell":
        counts = adapter.run(create_bell_circuit(), shots=shots)["counts"]
        return compute_fidelity(counts, shots), None

    if circuit_name == "ghz":
        counts = adapter.run(create_ghz_circuit(n_qubits=3), shots=shots)["counts"]
        return compute_fidelity_ghz(counts, shots), None

    if circuit_name == "vqe":
        counts_z = adapter.run(create_vqe_h2_circuit(basis="z"), shots=shots)["counts"]
        counts_x = adapter.run(create_vqe_h2_circuit(basis="x"), shots=shots)["counts"]
        return (compute_fidelity_vqe(counts_z, shots),
                compute_energy_h2(counts_z, counts_x, shots))

    raise ValueError(f"unknown circuit {circuit_name!r}")


def run_replicas(circuit_name: str, backend_name: str,
                 n: int = DEFAULT_N, shots: int = DEFAULT_SHOTS) -> dict:
    """
    Runs one (circuit, backend) condition n times and returns a result record.
    Raises RuntimeError if the backend is not available — a missing SDK must
    not silently turn into a missing row.
    """
    adapter = BACKENDS[backend_name]()
    if not adapter.is_available():
        raise RuntimeError(f"backend {backend_name!r} is not available "
                           f"({adapter.name}) — cannot produce a reference row")

    fidelities, energies = [], []
    t_total = time.time()

    for i in range(n):
        fid, energy = _one_replica(adapter, circuit_name, shots)
        fidelities.append(fid)
        if energy is not None:
            energies.append(energy)
        if (i + 1) % 25 == 0 or i + 1 == n:
            print(f"    {i + 1}/{n} replicas", flush=True)

    elapsed = time.time() - t_total

    def stats(values):
        arr = np.asarray(values, dtype=float)
        # ddof=1: these are samples of a distribution, not the population.
        std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
        return float(arr.mean()), std, (std / np.sqrt(arr.size) if arr.size else 0.0)

    fid_mean, fid_std, fid_sem = stats(fidelities)

    record = {
        "circuit":        circuit_name,
        "backend":        adapter.name,
        "shots":          shots,
        "n_replicas":     n,
        "fidelity_mean":  round(fid_mean, 4),
        "fidelity_std":   round(fid_std, 4),
        "fidelity_sem":   round(fid_sem, 5),
        "avg_exec_s":     round(elapsed / n, 4),
        "timestamp":      datetime.datetime.now().isoformat(timespec="seconds"),
    }

    line = (f"  {circuit_name:<5} {adapter.name:<20} "
            f"fidelity {fid_mean * 100:6.2f}% ± {fid_std * 100:.2f}% "
            f"(sem {fid_sem * 100:.3f}%)")

    if energies:
        e_mean, e_std, e_sem = stats(energies)
        record.update({
            "energy_mean":     round(e_mean, 4),
            "energy_std":      round(e_std, 4),
            "energy_sem":      round(e_sem, 5),
            "energy_bias_mha": round((e_mean - E_EXACT) * 1000, 1),
        })
        line += (f"  |  E {e_mean:.4f} ± {e_std:.4f} Ha "
                 f"(bias {(e_mean - E_EXACT) * 1000:+.1f} mHa)")

    print(line, flush=True)
    return record


def save_results(records, path=None):
    path = path or os.path.join(RESULTS_DIR, "replicas.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"\n[LOG] Saved to {path}")


def print_markdown_table(records):
    """Prints the records as the fidelity table used in README/article."""
    by_key = {(r["circuit"], r["backend"]): r for r in records}
    backends = ["ideal_simulator", "noisy_simulator",
                "aws_local_simulator", "ionq_simulator"]

    print("\n=== Fidelity table (paste-ready) ===")
    print("| Circuit | " + " | ".join(b.replace("_", " ") for b in backends) + " |")
    print("|---" * (len(backends) + 1) + "|")
    for circuit in CIRCUITS:
        cells = []
        for b in backends:
            r = by_key.get((circuit, b))
            if r is None:
                cells.append("—")
            elif r["fidelity_std"] == 0.0:
                cells.append(f"{r['fidelity_mean'] * 100:.2f}%")
            else:
                cells.append(f"{r['fidelity_mean'] * 100:.2f}% ± "
                             f"{r['fidelity_std'] * 100:.2f}%")
        print(f"| {circuit} | " + " | ".join(cells) + " |")

    print("\n=== VQE energy ===")
    for b in backends:
        r = by_key.get(("vqe", b))
        if r and "energy_mean" in r:
            print(f"  {b:<20} E = {r['energy_mean']:.4f} ± {r['energy_std']:.4f} Ha"
                  f"   (bias {r['energy_bias_mha']:+.1f} mHa, "
                  f"sem {r['energy_sem'] * 1000:.2f} mHa)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reference replica benchmark — fixed shots, many replicas"
    )
    parser.add_argument("--circuit", choices=CIRCUITS, default=None,
                        help="Circuit to replicate (default: all, with --all)")
    parser.add_argument("--backend", choices=sorted(BACKENDS), default=None,
                        help="Backend to replicate on (default: all, with --all)")
    parser.add_argument("--all", action="store_true",
                        help="Run every circuit on every local backend")
    parser.add_argument("--n", type=int, default=DEFAULT_N,
                        help=f"Number of replicas (default: {DEFAULT_N})")
    parser.add_argument("--shots", type=int, default=DEFAULT_SHOTS,
                        help=f"Shots per replica (default: {DEFAULT_SHOTS})")
    parser.add_argument("--out", type=str, default=None,
                        help="Output JSON path (default: results/replicas.json)")
    args = parser.parse_args()

    if args.n < 1:
        parser.error(f"--n must be a positive integer, got {args.n}")
    if args.shots < 1:
        parser.error(f"--shots must be a positive integer, got {args.shots}")
    if not args.all and (args.circuit is None or args.backend is None):
        parser.error("specify --circuit and --backend, or pass --all")

    circuits = CIRCUITS if args.all else (args.circuit,)
    backends = sorted(BACKENDS) if args.all else (args.backend,)

    print(f"=== Reference replicas — n={args.n}, shots={args.shots} ===")

    records = []
    for circuit_name in circuits:
        print(f"\n[{circuit_name.upper()}]")
        for backend_name in backends:
            print(f"  running on {backend_name}...", flush=True)
            records.append(run_replicas(circuit_name, backend_name,
                                        n=args.n, shots=args.shots))

    save_results(records, path=args.out)
    print_markdown_table(records)
