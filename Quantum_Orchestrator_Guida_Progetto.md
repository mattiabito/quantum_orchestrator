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
python src/orchestrator.py --qasm mio_algoritmo.qasm --strategy accurate --shots 2048
```
Per ingegneri che hanno un circuito quantistico proprio e vogliono eseguirlo sul backend migliore disponibile senza gestire IBM vs AWS vs IonQ, code e fallback.

---

## 3. Architettura

```
src/
  orchestrator.py        — logica principale: backend selector, strategie, logging
  graph.py               — grafici comparativi
  shots_efficiency.py    — benchmark shots efficiency (10 repliche/punto, 128-4096 shots)
  backends/
    base.py              — classe astratta BackendAdapter
    ibm.py               — IBM superconduttivo (simulatore Aer + QPU reale)
    aws.py               — AWS Braket simulatore locale
    ionq.py              — IonQ trapped-ion (via Braket)
    braket_utils.py      — conversione Qiskit→Braket condivisa da aws.py e ionq.py
  circuits/
    bell.py              — Bell state (2 qubit) — circuito di validazione
    ghz.py               — GHZ state (3 qubit) — complessità media
    vqe_h2.py            — VQE per molecola H₂ — caso d'uso reale
results/
  log.json               — log append-only dei job (NDJSON, un oggetto JSON per riga)
  bell_comparison.png    — grafico comparativo Bell state (più recente)
  ghz_comparison.png     — grafico comparativo GHZ state
  vqe_comparison.png     — grafico comparativo VQE H₂
  custom_comparison.png — grafico comparativo ultimo circuito QASM custom eseguito
  shots_efficiency.png   — grafico convergenza statistica shots
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

### Fase 3 — Benchmark sistematici + CLI ✅ COMPLETATA
- [x] Circuito GHZ (3 qubit, complessità media)
- [x] Circuito VQE H₂ (caso d'uso reale, ground truth = -1.1372 Hartree)
- [x] Analisi shots efficiency (256 → 4096 shots)
- [x] CLI con argparse (--circuit, --strategy, --shots, --qasm)
- [x] Supporto file QASM (esegui qualsiasi circuito personalizzato)
- [x] Output JSON strutturato (NDJSON)
- [x] Benchmark sistematico su tutti i circuiti e backend (Bell, GHZ, VQE H₂ × 5 backend, incluse repliche statistiche su QPU reale)

### Fase 4 — Pubblicazione e candidature
- [ ] Articolo: *"Quantum computing is an orchestration problem: I built a hybrid scheduler and measured what the textbooks only describe"*
- [ ] Pubblicazione: Medium + dev.to in inglese, post LinkedIn
- [ ] qBraid — contributo PR + contatto founder
- [ ] IQM Finlandia/Monaco — candidatura stage strutturato
- [ ] CINECA Bologna — candidatura diretta EuroQCS-Italy
- [ ] HPCTRAIN EuroHPC — traineeship retribuito 3–6 mesi, scadenza settembre 2026

---

## 5. Misure raccolte finora

| Circuito | Backend | Fidelità | Coda | Esecuzione | Note |
|---|---|---|---|---|---|
| Bell state | ideal_simulator | 100.00% | 0s | ~0.03s | |
| Bell state | noisy_simulator | ~95–97% | 0s | ~0.01s | |
| Bell state | ibm_qpu_ibm_kingston | 96.48% | 3645s | 2s | run 29/06 |
| Bell state | ibm_qpu_ibm_fez | 94.53–95.41% | 10–11s | 2s | run 29/06 |
| Bell state | ibm_qpu_ibm_marrakesh | 97.95–98.93%, 98.54% | 11–42s, 21.7s | 2s | range 29/06 + refresh 22/07 post-fix |
| Bell state | aws_local_simulator | 100.00% | 0s | ~0.03s | |
| Bell state | ionq_simulator | 98.73% | 0s | ~0.55s | post-fix noise model (19/07), singolo run 22/07 — sostituisce il vecchio 98.14–99.41% pre-fix |
| GHZ state | ideal_simulator | 100.00% | 0s | ~0.03s | |
| GHZ state | noisy_simulator | 93.47% ± 0.83% | 0s | ~0.01s | n=10 repliche |
| GHZ state | ibm_qpu (fez/marrakesh) | 94.63% ± 1.70% | 10.6–116.6s | 2s | n=5 repliche, 20/07 — 93.97% media su ibm_fez (n=4) |
| GHZ state | aws_local_simulator | 100.00% | 0s | ~0.04s | |
| GHZ state | ionq_simulator | 97.72–97.89% ± 0.48–0.60% | 0s | ~0.8s | n=10 (sandbox) + n=5 (venv utente), 20/07 |
| VQE H₂ | ideal_simulator | 100.00% | 0s | ~0.01s | E = -0.7432 Hartree (limite Z-basis, non un errore) |
| VQE H₂ | noisy_simulator | 95.29% ± 0.70% | 0s | ~0.01s | n=10 repliche |
| VQE H₂ | ibm_qpu (fez/marrakesh) | 97.30% ± 1.79% | 10.6–33.4s | 2s | n=5 repliche, 20/07 — 95.36% su ibm_fez (n=2) vs 98.60% su ibm_marrakesh (n=3) |
| VQE H₂ | aws_local_simulator | 100.00% | 0s | ~0.04s | |
| VQE H₂ | ionq_simulator | 98.68–98.83% ± 0.12–0.41% | 0s | ~0.35–0.8s | n=10 (sandbox) + n=5 (venv utente), 20/07 |

**Dati empirici chiave:**
- Esecuzione reale su QPU = 2 secondi, stabile su tutti i circuiti. Il tempo di coda varia da 10s a 3645s (61 minuti) sulla stessa macchina. Rapporto coda/esecuzione: fino a 1822:1. Dimostra empiricamente l'affermazione della tesi sulla latenza come collo di bottiglia dominante del QCaaS.
- Con repliche vere (n=5 su QPU reale), il gap di fidelità IonQ-vs-QPU su GHZ è confermato reale (94.63% vs 97.89%, quasi 2 deviazioni standard di separazione) — non rumore di campionamento.
- Su VQE H₂, la varianza della QPU reale è spiegata soprattutto da **quale macchina IBM viene selezionata** (ibm_fez 95.36% vs ibm_marrakesh 98.60% sullo stesso circuito) — prova quantitativa diretta che la selezione autonoma del backend incide sulla fidelity ottenuta, non solo sul tempo di coda.
- Il confronto IonQ-vs-QPU reale non è equivalente: IonQ è un simulatore con noise model calibrato, la QPU è hardware fisico misurato. Va sempre dichiarato nel report (vedi caveat nel README).

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
| 01/07/2026 | Sviluppato circuito VQE H₂ (ansatz Ry+CX, theta ottimale via scan analitico). Scoperto limite fondamentale: misure Z-basis catturano solo ~65% dell'energia totale (termini XX+YY mancanti) — dichiarato esplicitamente, non un bug. PySCF non installabile su Windows senza compiler C — abbandonato, usati coefficienti Hamiltoniani da letteratura (Kandala et al. 2017). Tool dichiarato feature-complete: 3 circuiti, 5 backend, 3 strategie, CLI completa, QASM, JSON, shots efficiency. | Fase 4: revisione codice, benchmark sistematico completo, articolo |
| 19/07/2026 | Revisione completa del codice con Claude: 14 problemi identificati (bug, dati, documentazione). Corretto bug serio: il noise model IonQ mancava del canale di errore a due qubit sul CNOT — le misure precedenti sovrastimavano la fidelità IonQ. Implementata fidelity generica (Hellinger) per circuiti QASM custom, scope limitato a QASM per non invalidare i dati Bell/GHZ/VQE esistenti. Pulizia codice: import morti rimossi, ionq.py disaccoppiato da aws.py (nuovo modulo braket_utils.py), IBMQPUAdapterAdaptive ora eredita da IBMQPUAdapter, costanti timeout centralizzate, circuit_info() aggiunta a ghz.py. | Rifare benchmark sistematico GHZ/VQE con codice corretto |
| 20/07/2026 | Rifatto benchmark GHZ e VQE H₂ su tutti e 5 i backend. Risolti due bug legati a Windows: import scipy non necessario in vqe_h2.py causava crash anche su Bell/GHZ (bloccato da un criterio di Application Control) — rimosso, VQE ora dipende solo da numpy. Errore metodologico commesso e corretto nella stessa sessione: conclusioni premature da un singolo run per backend (differenze piccole = rumore di campionamento, non effetto reale) — corretto con 5-10 repliche. Risultato solido: gap IonQ-vs-QPU reale su GHZ confermato (94.63% ± 1.70% vs 97.89% ± 0.60%, n=5); su VQE la varianza della QPU è spiegata soprattutto dalla macchina selezionata (ibm_fez 95.36% vs ibm_marrakesh 98.60%) — prova quantitativa che la selezione autonoma del backend conta anche per la fidelity, non solo per il tempo di coda. | Rilanciare Bell, aggiornare README/Guida Progetto con dati reali |
| 22/07/2026 | Bell rilanciato post-fix su tutti e 5 i backend (98.73% IonQ, 98.54% QPU reale, singolo run di riferimento). Verificati e rimossi file obsoleti: `backend_comparison.png` pre-refactor, cartella `src/results/` duplicata, `log.txt` superato da `log.json`. Sincronizzata documentazione: roadmap Fase 3 marcata completa in README e Guida Progetto, tabella misure aggiornata con dati GHZ/VQE, caveat IonQ-vs-QPU e limite Z-basis VQE aggiunti al README pubblico. | Fase 4: bozza articolo |

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
