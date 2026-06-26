<!-- ctrl+shift+v -->
# Quantum Orchestrator
**Guida di progetto — Mattia Bitocchi**
*Documento di riferimento per il lavoro quotidiano con Claude*

---

## 1. Obiettivo del progetto

Il progetto nasce dalla tua tesi triennale in Ingegneria Informatica (Università di Perugia, A.A. 2025–2026): *"Prospettive del Quantum Computing nell'Architettura dei Sistemi Informatici e nel Bilanciamento tra Servizi Cloud e Locali"*.

La tesi ha argomentato che il quantum computing oggi non è un problema di fisica, è un problema di architettura dei sistemi. Questo è il tuo angolo competitivo: il mercato cerca ingegneri, non fisici.

Il limite della tesi — che è anche la tua opportunità — è che era 100% concettuale: zero codice, zero misure. Il progetto trasforma quella teoria in dati reali.

> **Obiettivo finale**
> Un orchestratore open source che accetta un circuito quantistico, sceglie automaticamente il backend migliore (IBM, AWS, Azure) in base a disponibilità e qualità, esegue il job, logga i risultati e produce grafici comparativi misurati.

---

## 2. Struttura del progetto in 4 fasi

### Fase 1 — Ambiente + orchestratore base (IN CORSO)

Questa è la fase in cui ti trovi adesso. L'obiettivo è costruire il nucleo funzionante dell'orchestratore su IBM Quantum e dimostrare con dati reali ciò che la tesi descriveva in teoria.

#### Cosa devi completare

1. Aggiungere un noise model realistico (calibrato su hardware IBM vero) al simulatore Aer
2. Implementare il circuito VQE per H₂ (idrogeno molecolare) al posto del circuito di test Bell state
3. Implementare il fallback automatico: se la QPU IBM ha coda > soglia, usa il simulatore
4. Strutturare il logging: queue time, execution time, shots, fidelità rispetto al valore esatto
5. Generare i primi grafici comparativi: simulatore ideale vs simulatore con rumore vs QPU reale

#### Struttura della cartella di progetto

| File / Cartella | Contenuto |
|---|---|
| `src/orchestrator.py` | Logica principale: backend selector, esecuzione, logging |
| `src/backends/` | Un file per provider (ibm.py, aws.py, azure.py) — da creare in fase 2 |
| `src/circuits/` | Circuiti riutilizzabili: bell.py, vqe_h2.py |
| `results/` | Log e grafici generati automaticamente dal codice |
| `.env` | API keys (non caricare mai su GitHub) |
| `README.md` | Pitch del progetto + istruzioni di installazione |

---

### Fase 2 — Integrazione multi-provider (il differenziatore)

Questa fase trasforma il progetto da "tutorial Qiskit" a qualcosa di unico. Aggiungi AWS Braket e Azure Quantum come backend, costruendo un'architettura a plugin.

#### Provider da integrare

| Provider | SDK / Libreria | Costo simulatore | Stato |
|---|---|---|---|
| IBM Quantum | `qiskit`, `qiskit-ibm-runtime` | Gratis (Aer locale) | ✅ Attivo |
| AWS Braket | `amazon-braket-sdk` | Gratis (LocalSimulator) | Da integrare |
| Azure Quantum | `azure-quantum` | Gratis (sim locale) | Da integrare |
| IonQ / Quantinuum | Via AWS o Azure | A pagamento | Opzionale |

> 💡 **L'architettura giusta:** crea una classe astratta `BackendAdapter` con metodi `run()` e `get_status()`. Ogni provider implementa questa classe. L'orchestratore non sa a quale provider sta parlando.

---

### Fase 3 — Benchmark e analisi comparativa

Il cuore del progetto. Qui trasformi le tabelle qualitative della tesi in dati misurati reali.

#### Metriche da misurare

- **Fidelità:** quanto il risultato del backend si avvicina al valore esatto teorico (VQE H₂ = -1.1372 Hartree)
- **Latenza:** tempo totale dal submit al risultato (include queue time per QPU reali)
- **Queue time:** quanto si aspetta prima che il job venga eseguito su QPU reale IBM
- **Shots efficiency:** quanti shots servono per ottenere una certa precisione statistica
- **Costo stimato:** per shot, per job, su QPU reale vs simulatore

Output finale: un dashboard con grafici che mostra chi vince per cosa. Non esiste ancora nulla di simile in forma open source semplice.

---

### Fase 4 — Visibilità, articolo e candidature

Quando le fasi 1–3 sono complete, hai tutto il materiale per costruire la tua visibilità.

#### Articolo

Titolo proposto: *"Quantum computing is an orchestration problem: I built a hybrid scheduler and measured what the textbooks only describe."*

Pubblicazione: Medium e dev.to in inglese. LinkedIn post con link al repo e risultati principali.

#### Candidature

- **qBraid** — contribuisci una PR al loro repo, poi contatta i founder con link al tuo progetto
- **IQM** (Finlandia/Monaco) — stage strutturato, cercano ingegneri software
- **CINECA** (Bologna) — EuroQCS-Italy, candidatura diretta
- **HPCTRAIN** (EuroHPC) — traineeship 3–6 mesi retribuiti, cut-off settembre 2026, hpctrain.eu

---

## 3. Come collaborare con Claude ogni giorno

Claude non ha memoria tra conversazioni diverse, quindi è importante dargli il contesto giusto all'inizio di ogni sessione.

### Messaggio di riapertura sessione

Ogni volta che riapri Claude, inizia con questo messaggio (adattalo a dove sei arrivato):

> *"Sto lavorando al progetto Quantum Orchestrator — un orchestratore open source Python che confronta circuiti quantistici su più provider (IBM, AWS, Azure). Ho già: [descrivi cosa hai]. Oggi voglio: [obiettivo della sessione]. Ecco il codice attuale: [incolla il codice]"*

### Diario di avanzamento

Aggiorna questa tabella alla fine di ogni sessione:

| Data | Cosa ho fatto | Prossimo passo |
|---|---|---|
| 24/06/2026 | Installato Python 3.12, VS Code, Qiskit. Creato account IBM Quantum. Primo run di orchestrator.py funzionante con Bell state. | Aggiungere noise model realistico |
| 25/06/2026 | Rieseguito orchestrator.py con successo. Discusso visione multi-provider. Creata guida progetto. | Aggiungere noise model realistico ad Aer |
| | | |
| | | |
| | | |
| | | |

### Come incollare il codice a Claude

- Inizia con: *"Ecco il codice attuale di [nome file]:"*
- Incolla tutto il file, non solo la parte problematica
- Poi descrivi cosa vuoi: *"Voglio aggiungere..."*, *"Questo errore..."*, *"Come faccio a..."*

> 💡 Claude legge il codice completo meglio degli spezzoni. Se il file è lungo, incolla comunque tutto — è più efficiente.

---

## 4. Concetti chiave da ricordare

### Glossario essenziale

| Termine | Cosa significa nel tuo progetto |
|---|---|
| **Qubit** | L'unità base del calcolo quantistico. Può essere 0, 1 o una sovrapposizione di entrambi. |
| **Circuito quantistico** | Una sequenza di operazioni (gate) applicate ai qubit. Il tuo orchestratore accetta circuiti come input. |
| **Gate** | Operazione elementare su uno o più qubit. Es: H (Hadamard) crea superposizione, CNOT crea entanglement. |
| **Bell state** | Lo stato entangled più semplice: 2 qubit sempre correlati. Il circuito di test che hai già fatto girare. |
| **VQE** | Algoritmo ibrido classico-quantistico per trovare l'energia minima di una molecola. Il caso d'uso reale. |
| **H₂** | La molecola più semplice da simulare con VQE. Energia esatta = -1.1372 Hartree. Serve come ground truth. |
| **Backend** | Il "computer" su cui gira il circuito: simulatore ideale, simulatore con rumore, o QPU reale. |
| **QPU** | Quantum Processing Unit: il processore quantistico fisico reale (IBM, IonQ, ecc.). |
| **Aer** | Il simulatore locale di Qiskit. Gira sul tuo PC, è gratuito e veloce. |
| **Noise model** | Modello matematico che simula gli errori fisici di una QPU reale. Rende il simulatore più realistico. |
| **Shots** | Numero di volte che il circuito viene eseguito per raccogliere statistiche. Più shots = più precisione. |
| **Fidelità** | Quanto il risultato del backend si avvicina al risultato ideale. La metrica principale del benchmark. |
| **Fallback** | Meccanismo automatico: se la QPU è in coda troppo a lungo, l'orchestratore usa il simulatore. |
| **Backend selector** | Il componente centrale dell'orchestratore che sceglie quale backend usare per ogni job. |

### Link utili

- IBM Quantum dashboard: https://quantum.ibm.com
- Documentazione Qiskit: https://docs.quantum.ibm.com
- AWS Braket: https://aws.amazon.com/braket
- Azure Quantum: https://azure.microsoft.com/products/quantum
- HPCTRAIN (EuroHPC): https://hpctrain.eu
- CINECA carriere: https://cineca.it/lavora-con-noi
- qBraid GitHub: https://github.com/qBraid

---

> **Il tuo vantaggio competitivo**
> Sei un ingegnere dei sistemi in un mercato dominato da fisici. Il gap di talenti è esattamente nel tuo profilo. Nessun altro studente ha un orchestratore multi-provider open source con dati reali che misura ciò che la letteratura descrive solo in teoria. Questo progetto è la tua lettera di presentazione.
