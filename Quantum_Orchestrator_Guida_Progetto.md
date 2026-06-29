# Quantum Orchestrator
**Guida di progetto — Mattia Bitocchi**
*Documento di riferimento per il lavoro quotidiano con Claude*

---

## 1. Panoramica del progetto

Nato dalla tesi triennale in Ingegneria Informatica (Università di Perugia, A.A. 2025–2026):
*"Prospettive del Quantum Computing nell'Architettura dei Sistemi Informatici e nel Bilanciamento tra Servizi Cloud e Locali"*

**Argomento centrale della tesi:** il quantum computing oggi non è un problema di fisica, è un problema di architettura dei sistemi. Questo è il tuo angolo competitivo: il mercato cerca ingegneri, non fisici.

**Il gap che la tesi ha lasciato aperto — e che questo progetto riempie:**
La tesi era 100% concettuale: zero codice, zero misure. Ogni affermazione ("fallback al simulatore", "overhead della coda", "backend selector") era un'asserzione plausibile, mai misurata. Questo progetto trasforma quelle asserzioni in dati reali.

---

## 2. Cos'è questo progetto

**Quantum Orchestrator** è uno strumento CLI open source che:

1. Accetta qualsiasi circuito quantistico (built-in o file QASM personalizzato)
2. Seleziona autonomamente il backend migliore tra IBM, AWS e IonQ in base a tempo di coda, storico di fidelità e strategia di esecuzione
3. Esegue il job con fallback automatico se la QPU non è disponibile
4. Restituisce misure di fidelità, queue time, execution time e grafici comparativi

### Due casi d'uso

**Caso d'uso 1 — Benchmark dei backend**
Esegui i circuiti built-in (Bell, GHZ, VQE H₂) e ottieni un'analisi comparativa su tutti i provider. Per ricercatori e sviluppatori che vogliono capire quale backend usare per il loro problema. Non richiede codice oltre alle API key.

**Caso d'uso 2 — Esegui il tuo circuito**
```bash
python orchestrator.py --circuit mio_algoritmo.qasm --strategy accurate --shots 2048
```
Per ingegneri che hanno un circuito quantistico proprio e vogliono eseguirlo sul backend migliore disponibile senza gestire IBM vs AWS vs IonQ, code e fallback.

---

## 3. Architettura

```
src/
  orchestrator.py        — logica principale: backend selector, strategie, logging
  graph.py               — grafici comparativi
  backends/
    base.py              — classe astratta BackendAdapter
    ibm.py               — IBM superconduttivo (simulatore Aer + QPU reale)
    aws.py               — AWS Braket simulatore locale
    ionq.py              — IonQ trapped-ion (via Braket)
  circuits/
    bell.py              — Bell state (2 qubit) — circuito di validazione
    ghz.py               — GHZ state (3 qubit) — complessità media
    vqe_h2.py            — VQE per molecola H₂ — caso d'uso reale
results/
  log.txt                — log append-only dei job
  backend_comparison.png — grafico comparativo più recente
.env                     — API key (non caricare mai su GitHub)
README.md                — pitch pubblico + istruzioni di installazione
```

### Interfaccia BackendAdapter

Ogni provider implementa la stessa interfaccia:
```python
class BackendAdapter(ABC):
    def is_available(self) -> bool
    def estimated_queue_s(self) -> float
    def run(self, circuit, shots) -> dict
    def name -> str
```
L'orchestratore non sa mai con quale provider sta parlando.

### Strategie di esecuzione

| Strategia | Comportamento | Ideale per |
|---|---|---|
| `responsive` | Fallback immediato se la coda supera la soglia | Uso interattivo, iterazione rapida |
| `accurate` | Aspetta sempre la QPU reale, nessun fallback | Ricerca, quando la fidelità QPU è necessaria |
| `adaptive` | Aspetta fino al timeout, poi fallback | Batch job, run notturni |

---

## 4. Roadmap

### Fase 1 — Orchestratore base ✅ COMPLETATA
- Connessione QPU reale IBM con misure reali
- Simulatori ideale e rumoroso
- Noise model realistico calibrato su hardware IBM
- Fallback automatico con soglia adattiva
- Grafici comparativi con fidelità, queue time, exec time

### Fase 2 — Architettura multi-provider ✅ COMPLETATA
- Architettura a plugin BackendAdapter
- IBM QPU selezione autonoma (ibm_fez, ibm_marrakesh, ibm_kingston)
- AWS Braket LocalSimulator
- IonQ trapped-ion simulator
- Tre strategie di esecuzione: responsive, accurate, adaptive
- Grafico comparativo a 5 backend con exec time

### Fase 3 — Benchmark sistematici + CLI (IN CORSO)
- [ ] Circuito GHZ (3 qubit, complessità media)
- [ ] Circuito VQE H₂ (caso d'uso reale, ground truth = -1.1372 Hartree)
- [ ] Analisi shots efficiency (256 → 4096 shots)
- [ ] CLI con argparse (--circuit, --strategy, --shots, --output)
- [ ] Supporto file QASM (esegui qualsiasi circuito personalizzato)
- [ ] Output JSON strutturato
- [ ] Benchmark sistematico su tutti i circuiti e backend

### Fase 4 — Pubblicazione e candidature
- [ ] Articolo: *"Quantum computing is an orchestration problem: I built a hybrid scheduler and measured what the textbooks only describe"*
- [ ] Pubblicazione: Medium + dev.to in inglese, post LinkedIn
- [ ] qBraid — contributo PR + contatto founder
- [ ] IQM Finlandia/Monaco — candidatura stage strutturato
- [ ] CINECA Bologna — candidatura diretta EuroQCS-Italy
- [ ] HPCTRAIN EuroHPC — traineeship retribuito 3–6 mesi, scadenza settembre 2026

---

## 5. Misure raccolte finora

| Circuito | Backend | Fidelità | Coda | Esecuzione |
|---|---|---|---|---|
| Bell state | ideal_simulator | 100.00% | 0s | ~0.02s |
| Bell state | noisy_simulator | ~95–97% | 0s | ~0.01s |
| Bell state | ibm_qpu_ibm_kingston | 96.48% | 3645s | 2s |
| Bell state | ibm_qpu_ibm_fez | 94.53–95.41% | 10–11s | 2s |
| Bell state | ibm_qpu_ibm_marrakesh | 97.95–98.93% | 11–42s | 2s |
| Bell state | aws_local_simulator | 100.00% | 0s | ~0.03s |
| Bell state | ionq_simulator | 98.14–99.41% | 0s | ~0.5s |

**Dato empirico chiave:** esecuzione reale su QPU = 2 secondi. Il tempo di coda varia da 10s a 3645s (61 minuti) sulla stessa macchina. Rapporto coda/esecuzione: fino a 1822:1. Questo dimostra empiricamente l'affermazione della tesi sulla latenza come collo di bottiglia dominante del QCaaS.

---

## 6. Workflow quotidiano con Claude

Claude non ha memoria tra sessioni diverse. Inizia ogni sessione con:

> *"Sto lavorando al progetto Quantum Orchestrator — orchestratore open source Python multi-provider (IBM, AWS, IonQ). Ho già: [descrivi lo stato attuale]. Oggi voglio: [obiettivo della sessione]. Ecco il codice attuale: [incolla il codice]"*

### Diario di avanzamento

| Data | Cosa ho fatto | Prossimo passo |
|---|---|---|
| 24/06/2026 | Installato Python 3.12, VS Code, Qiskit. Creato account IBM Quantum. Primo run di orchestrator.py funzionante con Bell state. | Aggiungere noise model realistico |
| 25/06/2026 | Riscritto orchestrator.py in inglese. Aggiunto noise model IBM realistico. Misurata fidelità: ideale 100%, rumore ~95.3%. Creati .gitignore, requirements.txt, README.md. Inizializzato repo Git su GitHub. | Collegare QPU reale IBM |
| 29/06/2026 | Collegata QPU reale IBM. Backend selector autonomo (sceglie coda minima). Run su ibm_fez/ibm_marrakesh: fidelità 94–99%, coda 10–3645s, esecuzione 2s. Fallback adattivo + timeout 30min. Architettura BackendAdapter a plugin: ibm.py, aws.py, ionq.py. Tre strategie: responsive, accurate, adaptive. Grafico a 5 backend con exec time. Aggiornati README e guida progetto. | Fase 3: circuito GHZ, VQE H₂, CLI |

---

## 7. Glossario

| Termine | Significato nel progetto |
|---|---|
| **Qubit** | Unità base dell'informazione quantistica. Può essere 0, 1 o sovrapposizione di entrambi. |
| **Circuito quantistico** | Sequenza di operazioni gate applicate ai qubit. L'orchestratore accetta circuiti come input. |
| **Gate** | Operazione elementare su uno o più qubit. H (Hadamard) crea sovrapposizione, CNOT crea entanglement. |
| **Bell state** | Stato entangled più semplice: 2 qubit sempre correlati. Circuito di validazione base. |
| **GHZ state** | Stato entangled a 3 qubit. Circuito di benchmark a complessità media. |
| **VQE** | Variational Quantum Eigensolver. Algoritmo ibrido classico-quantistico per l'energia molecolare. Il caso d'uso reale. |
| **H₂** | Molecola di idrogeno. Target VQE più semplice. Energia esatta = -1.1372 Hartree. Ground truth del benchmark. |
| **Backend** | Il target computazionale: simulatore ideale, simulatore rumoroso, o QPU reale. |
| **QPU** | Quantum Processing Unit. Il processore quantistico fisico reale (IBM, IonQ, ecc.). |
| **Aer** | Simulatore locale di Qiskit. Gira sul tuo PC, gratuito e veloce. |
| **Noise model** | Modello matematico degli errori hardware della QPU. Rende il simulatore realistico. |
| **Shots** | Numero di volte che il circuito viene eseguito per raccogliere statistiche. Più shots = più precisione. |
| **Fidelità** | Quanto il risultato del backend si avvicina al risultato ideale. Metrica principale del benchmark. |
| **Fallback** | Meccanismo automatico: se la coda QPU supera la soglia, usa il simulatore rumoroso. |
| **Backend selector** | Componente centrale dell'orchestratore che sceglie autonomamente il backend migliore per ogni job. |
| **QASM** | OpenQASM — formato standard aperto per circuiti quantistici. Permette qualsiasi circuito come input. |
| **Transpilation** | Compilazione del circuito per il gate set nativo e la connettività di una QPU specifica. |

---

## 8. Link utili

- IBM Quantum dashboard: https://quantum.ibm.com
- Documentazione Qiskit: https://docs.quantum.ibm.com
- AWS Braket: https://aws.amazon.com/braket
- IonQ: https://ionq.com
- HPCTRAIN (EuroHPC): https://hpctrain.eu
- CINECA carriere: https://cineca.it/lavora-con-noi
- qBraid GitHub: https://github.com/qBraid

---

> **Il tuo vantaggio competitivo**
> Sei un ingegnere dei sistemi in un mercato dominato da fisici.
> Il gap di talenti è esattamente nel tuo profilo.
> Nessun altro studente ha un orchestratore multi-provider open source con dati reali
> che trasforma ciò che la letteratura descrive solo in teoria in evidenza empirica misurata.
> Questo progetto è la tua lettera di presentazione.
