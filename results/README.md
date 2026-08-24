# results/ — measured data and figures

Everything in this folder is output, not source: it is produced by the scripts in
`src/` and kept in the repo so that any number quoted in the main README can be
checked without re-running anything. This file says what each artefact is, which
command regenerates it, and — where it matters — when it was measured and against
which version of the code.

## Current — regenerate with one command

| File | Produced by | What it holds |
|---|---|---|
| `replicas.json` | `python src/replicas.py --all` | The n=100 reference rows in the README tables: mean and standard deviation of fidelity (and VQE energy) per circuit and backend, at 1024 shots. |
| `shots_efficiency.json` / `.png` | `python src/shots_efficiency.py` | Bell and GHZ fidelity from 128 to 4096 shots, 10 replicas per point. |
| `vqe_energy_convergence.json` / `.png` | `python src/vqe_energy_convergence.py` | VQE H₂ energy from 128 to 8192 shots, 10 replicas per point, on the three local backends. |

The `±` reported in these files is the spread between individual runs — a property
of the noise model at that shot count. It does not shrink as replicas are added.
What shrinks is the standard error on the mean (`fidelity_sem`, `energy_sem` in
`replicas.json`), which is what makes a mean quotable.

## Append-only run log

`log.jsonl` — one JSON object per backend run, written by `orchestrator.py` on
every execution (newline-delimited JSON). This is the raw record behind the
real-hardware numbers, including the five GHZ runs across `ibm_fez` and
`ibm_marrakesh` that the README's backend-selection finding is built on, and the
two post-fix VQE runs on `ibm_kingston`.

Two things to know before reading it as a dataset:

- **It spans several versions of the code.** Entries before 23 July 2026 were
  produced with a VQE ansatz and Hamiltonian later found to be wrong (their
  dominant count is `00` and their energy is around −0.72 Ha); entries before that
  date also predate the IonQ noise-model fix. They are kept for traceability and
  are *not* used in any published table.
- **A `noisy_simulator` entry is not always a simulator run by choice.** When IBM
  is unreachable or the queue exceeds the fallback threshold, the `ibm_qpu` slot
  falls back to the noisy simulator, so a full run can log two `noisy_simulator`
  lines. Records written from 24 August 2026 onwards carry a `fallback_from`
  field in that case, naming the backend that was requested — filter on it to
  separate stand-ins from simulator runs somebody chose. Earlier records have no
  such field, so for those, group by backend with the double-entry in mind.

The 3,645-second queue measurement that the queue-to-execution figure is built on
predates this log file (29 June 2026) and is recorded in commit `86ab7ae` rather
than here.

## Published figures

| File | Used by |
|---|---|
| `queue_vs_execution.png` | the article's opening figure — the 1822:1 ratio |
| `architecture.png` | the architecture section |
| `shots_efficiency.png` | the shots-efficiency section |
| `vqe_energy_convergence.png` | the statistical-vs-systematic-error section |

## Historical snapshots — read the date before quoting

These per-circuit comparison charts are kept because their IBM QPU panels are real
hardware measurements that cannot be regenerated without spending IBM quota. But
they are snapshots, not current output, and **no published table or figure is
derived from them**:

| File | Measured | Caveat |
|---|---|---|
| `ghz_comparison.png` | 20 Jul 2026 | IonQ panel predates the 23 July noise-model fix (noise is now interleaved with the gates, so it scales with depth); the IonQ fidelity shown is lower than the current model gives. |
| `bell_comparison.png` | 22 Jul 2026 | Same IonQ caveat. |
| `custom_comparison.png` | 22 Jul 2026 | Same IonQ caveat; generated from a custom QASM run. |
| `vqe_comparison.png` | 21 Aug 2026 | Current code, but taken without IBM credentials — the third panel is a noisy-simulator fallback, not a QPU. |

To regenerate the current-code version of any of these:
`python src/orchestrator.py --circuit {bell,ghz,vqe}`.
