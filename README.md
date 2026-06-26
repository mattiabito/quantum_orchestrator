# Quantum Orchestrator

An open-source Python orchestrator that benchmarks quantum circuits across multiple backends — ideal simulator, noisy simulator, and real IBM QPU — measuring what most textbooks only describe in theory.

## Motivation

Most quantum computing literature describes backend selection, noise impact, and hybrid fallback strategies conceptually. This project implements and **measures** them, producing real comparative data across providers.

Built as an extension of my BSc thesis in Computer Engineering (University of Perugia, 2025–2026): *"Quantum Computing Perspectives in System Architecture and Cloud/Local Service Balancing"*.

## What it does

- Accepts a quantum circuit and runs it on multiple backends
- Selects the best backend automatically based on availability and quality
- Measures and compares fidelity, execution time, and noise degradation
- Logs all results and generates comparative charts
- Falls back to simulator automatically when QPU queue exceeds threshold

## Current backends

| Backend | Provider | Cost |
|---|---|---|
| Ideal simulator | IBM Qiskit Aer | Free |
| Noisy simulator (realistic IBM noise model) | IBM Qiskit Aer | Free |
| Real QPU | IBM Quantum | Free tier |
| AWS Braket simulator | Amazon | Free (coming soon) |
| Azure Quantum simulator | Microsoft | Free (coming soon) |

## Results so far

Running a Bell state circuit (1024 shots):

| Backend | Fidelity | Noise degradation |
|---|---|---|
| Ideal simulator | 100.00% | — |
| Noisy simulator (IBM noise model) | ~95.3% | ~4.7% |
| Real IBM QPU | coming soon | coming soon |

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/quantum-orchestrator.git
cd quantum-orchestrator
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Usage

```bash
# Run the orchestrator
python src/orchestrator.py

# Generate comparison charts
python src/graph.py
```

## Configuration

Copy `.env.example` to `.env` and add your IBM Quantum API key:

IBM_API_KEY=your_key_here
IBM_INSTANCE=your_instance_here

## Project structure

quantum-orchestrator/
├── src/
│   ├── orchestrator.py     # Core logic: backend selector, job execution, logging
│   └── graph.py            # Comparative charts generator
├── results/                # Auto-generated logs and charts
├── requirements.txt        # Python dependencies
└── README.md
