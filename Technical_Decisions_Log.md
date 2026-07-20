# Quantum Orchestrator — Technical Decisions Log
**Documento di tracciamento decisioni tecniche, osservazioni sperimentali e ragionamenti**

Questo file cattura il *perché* dietro ogni scelta tecnica — non solo cosa è stato fatto (vedi diario nella guida progetto) ma perché, cosa abbiamo osservato che ci ha portato lì, e cosa significa per il report finale.

Va aggiornato ogni volta che emerge una decisione non ovvia, una scoperta sperimentale, o un cambio di direzione. Va caricato nel progetto Claude in modo che sia sempre disponibile come contesto in ogni nuova sessione.

---

## 29/06/2026 — Setup IBM Quantum: da token diretto a Cloud IAM

**Cosa abbiamo osservato:**
Il `.env` dell'utente conteneva `IBM_API_KEY` e `IBM_INSTANCE`, non il classico `IBM_QUANTUM_TOKEN` previsto dalla vecchia documentazione IBM.

**Perché succede:**
IBM ha cambiato il sistema di autenticazione: il nuovo piano "IBM Quantum Platform" (post-2024) usa Cloud IAM invece del token diretto. Questo richiede `channel="ibm_cloud"` invece di `channel="ibm_quantum"`, e il parametro `instance` oltre al token.

**Decisione presa:**
Riscritto `select_backend` per usare `QiskitRuntimeService(channel="ibm_cloud", token=IBM_API_KEY, instance=IBM_INSTANCE)`.

**Rilevanza per il report:**
Da menzionare nella sezione setup/installazione — la documentazione IBM online è spesso disallineata con l'API più recente, un problema reale per chi cerca di replicare il lavoro.

---

## 29/06/2026 — VS Code: working directory e creazione file

**Cosa abbiamo osservato:**
File creati da VS Code non comparivano nella cartella del progetto quando lanciati da terminale (`check_backends.py` non trovato).

**Perché succede:**
VS Code era stato aperto senza la cartella di progetto come root — i file venivano salvati nella home directory (`C:\Users\matti`) invece che in `quantum-orchestrator`.

**Decisione presa:**
Procedura standard: aprire sempre VS Code con `code .` dalla cartella del progetto, o tramite File → Open Folder.

**Rilevanza per il report:**
Nessuna — è un dettaglio di workflow personale, non tecnico/scientifico.

---

## 29/06/2026 — Qiskit Runtime: job.status() è una stringa, non un oggetto

**Cosa abbiamo osservato:**
```
AttributeError: 'str' object has no attribute 'name'
```
nel codice di polling che faceva `status.name == "RUNNING"`.

**Perché succede:**
In `qiskit-ibm-runtime 0.47`, `job.status()` ritorna direttamente una stringa (`"QUEUED"`, `"RUNNING"`, `"DONE"`), non un enum con attributo `.name` come in versioni precedenti dell'SDK.

**Decisione presa:**
Cambiato tutto il confronto da `status.name == "X"` a `status == "X"`.

**Rilevanza per il report:**
Da menzionare come nota tecnica/troubleshooting — le librerie quantum computing cambiano API rapidamente, problema di stabilità per chi sviluppa su queste piattaforme.

---

## 29/06/2026 — Qiskit Runtime: il nome del registro di misura non è fisso

**Cosa abbiamo osservato:**
```
AttributeError: 'DataBin' object has no attribute 'meas'
```
quando si tentava di leggere `pub_result.data.meas.get_counts()`.

**Perché succede:**
Il nome del registro di misura nei risultati SamplerV2 dipende da come il circuito è stato costruito — non è sempre `meas`. Soluzione robusta: leggere dinamicamente il primo registro disponibile con `list(pub_result.data)[0]`.

**Decisione presa:**
```python
register = list(pub_result.data)[0]
counts   = dict(getattr(pub_result.data, register).get_counts())
```

**Rilevanza per il report:**
Nota tecnica minore, utile per chi replica il codice.

---

## 29/06/2026 — SCOPERTA CHIAVE: pending_jobs non predice il tempo di coda reale

**Cosa abbiamo osservato:**
Primo run su `ibm_kingston` con **1 solo pending job**: tempo totale **20+ minuti**, poi confermato a **3645.6 secondi (60 minuti 45 secondi)**.
Run successivi su `ibm_fez` e `ibm_marrakesh` con pending jobs comparabili (1-6): tempi totali di **10-23 secondi**.

**Perché succede:**
IBM non gestisce una coda FIFO semplice. La schedulazione dipende da fattori interni non esposti via API: priorità, stato di calibrazione della macchina in quel momento, manutenzione, tipo di circuito. Il campo `pending_jobs` è necessario ma non sufficiente per stimare il tempo di attesa reale.

**Decisione presa:**
1. Implementato fallback **adattivo** basato su soglia proporzionale (non assoluta): `threshold = QUEUE_MULTIPLIER * estimated_exec_s` invece di un valore fisso.
2. Implementato **timeout assoluto** di sicurezza (`ABSOLUTE_TIMEOUT_S = 1800`, 30 minuti) come rete di sicurezza indipendente dalla stima.
3. Implementato **backend selector autonomo** che sceglie sempre il backend con minor pending jobs tra quelli disponibili, invece di un nome hardcoded.

**Rilevanza per il report — ALTA:**
Questo è uno dei risultati empirici più forti del progetto. Dimostra che:
- La metrica "pending jobs" esposta dalle API pubbliche non è affidabile come singolo predittore
- La selezione autonoma del backend (provare il migliore disponibile, non un nome fisso) ha impatto misurabile sulle performance: stessa richiesta, stesso giorno, da 60 minuti a 10 secondi a seconda di quale macchina viene scelta
- Conferma empiricamente l'argomento centrale della tesi: il quantum computing è un problema di **architettura/orchestrazione**, non solo di hardware

---

## 29/06/2026 — Dato chiave: rapporto esecuzione/coda

**Cosa abbiamo osservato:**
Su `ibm_marrakesh`, IBM stesso dichiara "Estimated QR usage: 4s" nel dashboard, mentre il job è rimasto in stato Pending per quasi un'ora.
Misura finale: **execution time = 2s, queue time = 3645.6s**. Rapporto coda/esecuzione: **1822:1**.

**Perché succede:**
Conferma diretta che il collo di bottiglia del quantum computing as a service non è il calcolo quantistico in sé (che è already fast — 2-4 secondi) ma l'accesso/scheduling del servizio cloud.

**Rilevanza per il report — ALTA:**
Citazione diretta per l'abstract/intro dell'articolo: *"for every second of quantum computation, the user waited up to 30 minutes in queue"*. Questo è il dato che trasforma l'argomento qualitativo della tesi (Capitolo 2: "l'accesso a una QPU può dipendere da code e disponibilità variabile") in un numero misurato.

---

## 29/06/2026 — Decisione architetturale: tre strategie di esecuzione configurabili

**Cosa abbiamo osservato (ragionamento dell'utente):**
Con soglia fissa di fallback, lavori "appena più pesanti" del previsto vengono tagliati fuori automaticamente — rischio di escludere casi d'uso legittimi (es. un job da 20 minuti che in un'applicazione reale sarebbe accettabile, ma viene scartato da una soglia troppo aggressiva).

**Perché è un problema reale:**
Un'unica policy di fallback non può soddisfare contemporaneamente: (a) chi vuole risposta rapida sempre, (b) chi vuole risultati QPU reali a tutti i costi, (c) chi può aspettare ma non vuole bloccare indefinitamente.

**Decisione presa:**
Implementate tre strategie esplicite e configurabili:
- `responsive` — fallback immediato se la coda stimata supera la soglia (default, per uso interattivo/testing)
- `accurate` — aspetta sempre la QPU reale, mai fallback (per ricerca/benchmark seri)
- `adaptive` — aspetta fino al timeout assoluto, poi fallback automatico (per batch job/run notturni)

**Rilevanza per il report — ALTA:**
Questo è il punto di svolta concettuale del progetto: da "benchmark tool" a "orchestratore vero". Citabile testualmente: l'utente ha osservato che "l'obiettivo è che il servizio possa fronteggiare quanti più casi possibili al fine che l'utente possa trovarsi accomodato nel suo uso e non tagliato fuori per via delle sue necessità" — è la frase guida dell'architettura a strategie multiple.

---

## 29/06/2026 — Scelta IonQ al posto di Azure Quantum

**Cosa abbiamo osservato:**
Tentativo di integrare Azure Quantum come terzo provider è fallito: l'errore `Azure Quantum workspace not fully specified` mostra che Azure Quantum **non ha un vero simulatore locale standalone** — richiede sempre una connessione a un workspace Azure Cloud configurato, anche solo per simulare.

**Perché è rilevante:**
Azure come "simulatore locale" sarebbe stato funzionalmente identico a IBM Aer (entrambi simulatori ideali, fidelity 100%) — nessun valore aggiunto reale al confronto comparativo, solo complessità di setup (account, workspace, billing) senza beneficio scientifico.

**Decisione presa:**
Sostituito Azure con **IonQ** (trapped-ion, via AWS Braket density matrix simulator), già accessibile con l'SDK AWS esistente, nessun account aggiuntivo necessario.

**Motivazione tecnica della scelta:**
IonQ usa tecnologia fisica diversa da IBM — trapped-ion (ioni di itterbio manipolati con laser) invece di superconducting qubits. Questo aggiunge un punto dati architetturalmente diverso, non solo un altro simulatore ideale. Noise model IonQ implementato con parametri realistici: gate singolo ~0.03% (vs IBM ~0.1%), CNOT ~0.3% (vs IBM ~1%), readout ~0.5% (vs IBM ~2%).

**Rilevanza per il report — MEDIA-ALTA:**
Permette un confronto comparativo tra due paradigmi hardware fisici diversi (superconducting vs trapped-ion), non solo tra provider software. Giustificazione esplicita da includere nella sezione metodologica: "Azure was excluded because its local simulator requires cloud workspace configuration with no architectural difference from IBM Aer; IonQ was chosen instead for its distinct physical qubit technology."

---

## 29/06/2026 — Osservazione: IonQ simulator supera la QPU IBM reale in fidelità

**Cosa abbiamo osservato:**
Su più run, `ionq_simulator` ha mostrato fidelità sistematicamente più alta (98.14%-99.41%) della QPU IBM reale (94.34%-98.93%), nonostante IonQ sia "solo" un simulatore con noise model, non hardware fisico.

**Perché succede:**
Il noise model IonQ implementato usa parametri di errore ottimistici basati sulle specifiche dichiarate dal vendor, che non catturano necessariamente tutte le fonti di rumore reali (crosstalk, drift di calibrazione, errori SPAM completi) presenti su una QPU fisica reale.

**Decisione presa:**
Nessuna modifica al codice — il dato viene mantenuto e commentato esplicitamente.

**Rilevanza per il report — MEDIA:**
Punto di onestà metodologica importante: va dichiarato chiaramente che il confronto "IonQ" nel progetto è un *simulatore con noise model calibrato*, non hardware fisico reale — a differenza del dato IBM che è hardware reale misurato. Il confronto diretto fidelità-vs-fidelità tra i due non è equivalente; va specificato nel report per evitare conclusioni fuorvianti ("IonQ è migliore di IBM" sarebbe un'affermazione non supportata dai dati raccolti).

> **Aggiornamento 19/07/2026:** causa reale identificata — non solo parametri vendor ottimistici, ma un bug nel noise model (canale di errore a due qubit mancante). Vedi entry sotto. Dati IonQ da rimisurare.

---

## 29/06/2026 — Validazione: la complessità del circuito (Bell vs GHZ) come benchmark proxy

**Cosa abbiamo osservato (domanda dell'utente):**
Dubbio se il Bell state (2 qubit, circuito di validazione più semplice usato in tutto il progetto) fosse un proxy sufficiente per circuiti più complessi, o se servisse validare anche su GHZ (3 qubit) prima di prendere decisioni architetturali basate solo su Bell.

**Primo tentativo (fallito metodologicamente):**
Shots efficiency testato con **una singola run per valore di shots** — risultato: curve Bell/GHZ caotiche, che si incrociavano senza pattern interpretabile su 10 ripetizioni manuali dell'intero esperimento.

**Causa del problema:**
Il noise model usa `depolarizing_error`, intrinsecamente stocastico — ogni chiamata a `backend.run()` ricampiona gli errori casualmente. Una singola misura per punto non distingue "vera convergenza" da "rumore della singola osservazione".

**Correzione metodologica:**
Riscritto lo script con **10 repliche per ogni valore di shots**, misurando media e deviazione standard invece del singolo valore puntuale.

**Risultato pulito (dati validati 29/06/2026):**
```
Bell fidelity (mean): 95.55% → 95.39% → 95.45% → 95.66% → 95.60% → 95.72%  (128→4096 shots)
GHZ fidelity (mean):  92.73% → 93.05% → 92.50% → 92.60% → 92.92% → 93.11%  (128→4096 shots)

Bell std dev: 1.31% → 1.03% → 0.68% → 0.56% → 0.51% → 0.29%
GHZ std dev:  3.05% → 1.77% → 0.97% → 0.74% → 0.55% → 0.53%

Gap Bell-GHZ a 4096 shots: 2.61%
```

**Interpretazione:**
1. Il gap di fidelità Bell-GHZ (~2.6%) è **reale, stabile e consistente** su tutto il range di shots — non rumore, ma effetto strutturale della profondità del circuito (più gate = più accumulo di errore).
2. La vera firma della convergenza statistica è la **riduzione della deviazione standard** con l'aumento degli shots (entrambi i circuiti dimezzano abbondantemente lo std dev da 128 a 4096 shots), non la stabilità del valore medio (che era già relativamente stabile anche a pochi shots).
3. GHZ parte con std dev quasi 3 volte più alto di Bell a 128 shots (3.05% vs 1.31%) — un circuito più complesso ha più varianza con pochi shots, converge comunque ma più lentamente.
4. **Punto di convergenza pratico identificato: 1024-2048 shots** — oltre questa soglia lo std dev scende sotto 0.6% per entrambi i circuiti, guadagni marginali oltre questo punto.

**Decisione presa:**
- Bell state confermato come proxy valido per il comportamento *generale* di rumore di base (readout error, errore gate singolo) e per l'analisi di convergenza statistica.
- Bell state NON è sufficiente da solo per catturare l'effetto della profondità del circuito — necessario mantenere GHZ (o circuiti più complessi come VQE H₂) nel benchmark suite per misurare la degradazione legata alla complessità.
- Il default di 1024 shots usato in tutti i run precedenti del progetto è confermato come scelta valida, non arbitraria — retroattivamente giustificato dal dato di convergenza.

**Rilevanza per il report — ALTA:**
Sezione metodologica importante. Da includere: "1024 shots are sufficient for stable fidelity estimation on circuits up to 3 qubits; beyond that, additional shots primarily reduce variance rather than shift the mean fidelity. Circuit depth introduces a measurable and stable fidelity gap (~2.6% between 2-qubit and 3-qubit entangled states under the same noise model), independent of shot count." Inoltre, da menzionare la lezione metodologica stessa: l'importanza di repliche multiple per distinguere segnale da rumore stocastico in un noise model probabilistico — rilevante per chiunque replichi benchmark simili.

---

## 29/06/2026 — Decisione strategica: pubblicazione unica (benchmark + orchestratore) invece di due separate

**Cosa abbiamo osservato (domanda dell'utente):**
Valutata l'opzione di pubblicare due articoli distinti — uno sul benchmark (per chi vuole solo valutare/confrontare backend) e uno sull'orchestratore vero (per chi ha un circuito da eseguire), per servire meglio i due profili di utente del progetto.

**Vincoli concreti considerati:**
Cut-off HPCTRAIN settembre 2026; candidature qBraid, IQM, CINECA. Tempo limitato.

**Decisione presa:**
Pubblicazione unica strutturata in due parti narrative: Parte 1 (benchmark — "i measured what the textbooks only describe") e Parte 2 (orchestratore — "then I built a scheduler that acts on those measurements"). Eccezione valutata ma non ancora confermata: eventuale pubblicazione anticipata del solo benchmark a luglio se utile per una PR a qBraid prima di settembre.

**Rilevanza per il report:**
Definisce la struttura narrativa dell'intero articolo finale. Da rivisitare se i tempi di sviluppo dovessero allungarsi.

---

## 29/06/2026 — Due casi d'uso espliciti del progetto (definizione architetturale)

**Cosa abbiamo osservato (ragionamento dell'utente):**
Riflessione su come comunicare il valore del progetto a due tipi di utente diversi: chi vuole solo valutare/confrontare backend per scopi di ricerca (usa i circuiti built-in), e chi ha un proprio circuito su cui lavorare e vuole eseguirlo al meglio senza gestire manualmente provider/codе/fallback.

**Decisione presa:**
Architettura esplicitamente pensata per supportare entrambi i casi d'uso fin dall'inizio (l'orchestratore già accetta qualunque `QuantumCircuit` Qiskit, non solo Bell/GHZ):
- **Caso d'uso 1 (benchmarking):** esecuzione dei circuiti built-in, nessun setup oltre le API key
- **Caso d'uso 2 (custom circuit):** CLI con `--circuit file.qasm`, supporto OpenQASM pianificato per Fase 3

**Rilevanza per il report — ALTA:**
Definisce la value proposition del progetto nel README e nell'articolo. Da non perdere: l'osservazione che senza questo tool, un ingegnere che vuole eseguire un circuito su QPU reale deve gestire manualmente autenticazione multi-provider, monitoraggio coda, timeout, conversione formati, raccolta risultati — il progetto comprime tutto questo in una riga di comando.

---

## 29/06/2026 — Nota su gestione sessioni Claude e memoria persistente

**Cosa abbiamo osservato (domanda dell'utente):**
Preoccupazione esplicita su come preservare il ragionamento e le sfumature emerse durante le sessioni di sviluppo, dato che Claude non ha memoria tra conversazioni diverse — rischio di perdere il "perché" dietro le scelte tecniche al momento di scrivere il report finale.

**Decisione presa:**
Creazione di questo documento (`Technical_Decisions_Log.md`) come memoria esterna strutturata, separato dal diario di avanzamento nella guida progetto (che cattura il "cosa", non il "perché"). Il file va caricato nel progetto Claude e aggiornato a ogni sessione rilevante; ogni nuova chat che lavora sul progetto deve essere istruita a leggerlo e contribuire ad aggiornarlo.

**Rilevanza per il report:**
Meta-decisione di processo, non tecnica — ma essenziale per la qualità finale del report, che dipenderà dalla completezza di questo log.

---

## Note per l'uso di questo file

- Ogni nuova sessione di lavoro su Quantum Orchestrator dovrebbe iniziare leggendo questo file (caricarlo nel progetto Claude lo rende automaticamente disponibile).
- Quando emerge una decisione non ovvia, un'osservazione sperimentale sorprendente, o una scelta architetturale con motivazione non banale, va aggiunta una nuova entry seguendo il formato: **Cosa abbiamo osservato** → **Perché succede** → **Decisione presa** → **Rilevanza per il report**.
- Decisioni poi scartate vanno comunque mantenute nel log (non cancellate) con una nota esplicita che indica che sono state superate — il percorso decisionale completo, inclusi i vicoli ciechi, ha valore per la sezione "Methodology" e "Lessons Learned" del report finale.

## 01/07/2026 — VQE H₂: impossibilità stima energetica completa da Z-basis sola

**Cosa abbiamo osservato:**
Dopo numerosi tentativi con ansatz e parametri diversi, il simulatore
ideale converge sempre a E ≈ -0.74 Hartree invece di -1.1372 Hartree.
L'ottimizzatore empirico (scan su 100 valori di theta) conferma che
-0.7432 Hartree è il minimo raggiungibile con misure Z-basis sola.

**Perché succede:**
Il Hamiltoniano H₂ contiene termini off-diagonali XX e YY che
contribuiscono ~0.39 Hartree all'energia totale. Questi richiedono
misure in basi X e Y (circuiti aggiuntivi con rotazioni di base).
Con un singolo circuito in base Z è fisicamente impossibile ottenere
l'energia esatta — non è un problema di parametri o ansatz, è un
limite fondamentale della misura in base singola.

**Decisione presa:**
Mantenuto il benchmark VQE con due metriche separate e oneste:
1. Fidelità = frazione di shots negli stati dominanti (|00⟩ e |11⟩)
2. Energia Z-basis = stima parziale (~65% energia totale) con
   disclaimer esplicito nel codice e nell'output

**Rilevanza per il report — ALTA:**
Punto di onestà metodologica pubblicabile. Dimostra che l'orchestratore
esegue correttamente circuiti VQE (fidelità ~95-99% su tutti i backend),
ma la stima energetica completa richiede misure multi-basis. Dichiarazione
nel report: "Full VQE energy estimation requires Z, X and Y basis
measurements. This benchmark implements Z-basis only, capturing ~65%
of the Hamiltonian energy. The XX+YY contribution (~0.394 Hartree)
requires additional circuit executions with basis rotations."

---

## 01/07/2026 — PySCF non installabile su Windows senza compilatore C

**Cosa abbiamo osservato:**
pip install pyscf fallisce su Windows con errore CMake:
"nmake not found", "CMAKE_C_COMPILER not set".

**Perché succede:**
PySCF richiede compilazione di codice C/Fortran. Su Windows questo
richiede Visual Studio Build Tools (~3GB) non installato nell'ambiente.

**Decisione presa:**
Abbandonato l'approccio PySCF. Usati coefficienti Hamiltoniani esatti
dalla letteratura (Kandala et al., Nature 549, 2017) con ottimizzazione
empirica del theta sul simulatore locale.

**Rilevanza per il report — BASSA:**
Nota tecnica per sezione requisiti: PySCF richiede Linux/Mac o WSL.

---

## 20/07/2026 — scipy.optimize bloccato da Windows Application Control, isolato da vqe_h2

**Cosa abbiamo osservato:**
`python orchestrator.py --circuit ghz` falliva con `ImportError: DLL load failed while importing pyduccfft` durante l'import di `scipy.optimize` dentro `vqe_h2.py`, nonostante GHZ non usi scipy in nessun modo.

**Perché succede:**
`orchestrator.py` importava tutti e tre i moduli circuiti (bell, ghz, vqe_h2) in cima al file, indipendentemente da `--circuit`. `vqe_h2.py` importa `scipy.optimize` a livello di modulo, e quell'import fa scattare il caricamento di `scipy.fft._duccfft` (componente nativo), bloccato da un criterio di controllo applicazioni di Windows (probabile Smart App Control). Il traceback si ferma esattamente su questo import — non su `backends.ibm` (che pure usa scipy indirettamente via `qiskit_ibm_runtime`) — coerente col fatto che Bell/GHZ su QPU reale avevano già funzionato in precedenza sulla stessa macchina.

**Decisione presa:**
Import di `circuits.vqe_h2` spostato da livello di modulo a dentro il blocco `if run_vqe:` in `orchestrator.py`, con try/except `ImportError` che disattiva solo il benchmark VQE (stampando un errore chiaro) invece di far crashare l'intero programma. Bell e GHZ sono ora completamente indipendenti dalla catena di dipendenze di VQE.

**Rilevanza per il report — MEDIA:**
Terzo problema di fragilità dell'ambiente Windows per questo progetto (dopo l'auth IBM Cloud IAM del 29/06 e PySCF del 01/07) — pattern ricorrente da menzionare nella sezione Requirements/Installation: Windows richiede più attenzione di Linux/Mac per le dipendenze scientifiche di questo tool. Il fix qui è di isolamento (un circuito rotto non blocca gli altri), non risolve il blocco a monte — per eseguire VQE resta necessario sbloccare scipy lato Windows (Smart App Control / Windows Defender Application Control) o reinstallare scipy con un backend FFT diverso.

---

## 20/07/2026 — GHZ benchmark completo su 5 backend: impatto reale del fix noise model IonQ

**Cosa abbiamo osservato:**
Primo run GHZ (3 qubit, 1024 shots) su tutti e 5 i backend dopo il fix del 19/07 al noise model IonQ:
ideal_simulator 100.00% | noisy_simulator 93.36% | ibm_qpu_ibm_marrakesh (QPU reale) 97.66%, queue 10.6s, exec 2s | aws_local_simulator 100.00% | ionq_simulator 98.34%.

**Perché è rilevante:**
Con l'errore CNOT ora applicato, IonQ (98.34%) resta leggermente sopra la QPU IBM reale (97.66%) — gap di 0.68 punti percentuali, molto più ridotto di quanto osservato su Bell prima del fix (dove IonQ arrivava fino a 99.41% contro un minimo IBM reale di 94.34%, gap fino a ~5 punti). Il fix ha funzionato nella direzione attesa — ha ridotto il vantaggio artificiale di IonQ — ma non l'ha eliminato del tutto: coerente con l'ipotesi già loggata il 29/06 che i parametri di rumore IonQ restino comunque ottimistici rispetto a hardware fisico reale.

**Decisione presa:**
Nessuna ulteriore modifica al codice. Dato conservato come primo punto dati GHZ completo su 5 backend (vedi `results/ghz_comparison.png` e `results/log.json`).

**Rilevanza per il report — ALTA:**
Primo dato quantitativo che conferma l'efficacia del fix del 19/07 su un circuito diverso da quello usato per il debug (GHZ, non Bell) — buona evidenza che la correzione generalizza. Utile per una sezione "Methodology"/"Validation" dell'articolo: mostra il processo scoperta → fix → validazione con dati reali, non solo un'affermazione teorica.

---

## 01/07/2026 — Fase 3 completata: feature set finale del tool

**Cosa abbiamo costruito:**
- 3 circuiti built-in: Bell (2 qubit), GHZ (3 qubit), VQE H₂ (2 qubit)
- 5 backend: ideal simulator, noisy simulator, IBM QPU reale,
  AWS LocalSimulator, IonQ trapped-ion simulator
- 3 strategie: responsive, accurate, adaptive
- CLI completa: --circuit, --strategy, --shots, --qasm
- Supporto QASM: qualsiasi circuito standard come input
- Output JSON strutturato (NDJSON)
- Shots efficiency benchmark con analisi statistica (10 repliche/punto)
- Backend selector autonomo con fallback adattivo

**Decisione presa:**
Tool dichiarato feature-complete per la pubblicazione.
Fase 4 = articolo, README finale, visibilità, candidature.

**Rilevanza per il report — ALTA:**
Questo è il progetto finito. Tutto ciò che viene dopo è comunicazione.

---

## 19/07/2026 — Correzione: noise model IonQ mancava del canale di errore a due qubit

**Cosa abbiamo osservato:**
Code review ha rilevato che `ionq.py` dichiarava nel docstring un errore a due qubit CNOT di ~0.3% ("vs IBM ~1%"), ma il metodo `run()` applicava solo depolarizing single-qubit (0.03%) e bit-flip di readout (0.5%) — nessun canale di errore sul CNOT.

**Perché succede:**
Omissione risalente alla prima implementazione (29/06): il canale single-qubit + readout è stato scritto ma non è mai stato completato con il canale a due qubit corrispondente al valore già dichiarato nel docstring.

**Decisione presa:**
Aggiunto `braket_circuit.two_qubit_depolarizing(q0, q1, probability=0.003)` su ogni gate CNOT del circuito originale (iterando `circuit.data`), applicato dopo il depolarizing single-qubit e prima del bit-flip di readout. Verificato in sandbox isolata che il canale viene correttamente inserito nel circuito Braket risultante.

**Rilevanza per il report — ALTA:**
Corregge l'osservazione del 29/06 ("IonQ simulator supera la QPU IBM reale in fidelità"): quell'entry ipotizzava "parametri vendor ottimistici" come causa, ma la causa reale (almeno parziale) era un canale di errore mancante nel codice, non solo una scelta di parametri. Tutte le misure IonQ raccolte finora (README, Guida Progetto, tabella misure) sono state prodotte SENZA questo canale e vanno considerate obsolete — da rimisurare prima della pubblicazione.

---

## 19/07/2026 — Fidelity generica per circuiti QASM custom (Hellinger fidelity)

**Cosa abbiamo osservato:**
La fidelity per circuiti QASM caricati dall'utente (`--qasm`) usava sempre la formula di Bell (frazione di conteggi su `|00⟩`/`|11⟩`), priva di senso per circuiti con distribuzione ideale diversa da 2 stati dominanti equiprobabili. Stesso problema nel grafico comparativo: la linea "ideal count" assumeva sempre `shots/2` su 2 stati.

**Perché succede:**
`run_job()` applica di default `compute_fidelity` da `bell.py` quando non viene passata una `fidelity_fn` esplicita; il ramo QASM custom in `orchestrator.py` non ne passava una specifica.

**Decisione presa:**
Implementata `compute_fidelity_generic()` in `orchestrator.py`: fidelity di Hellinger F = (Σ√(pᵢ·qᵢ))² tra la distribuzione osservata e quella misurata sul run `ideal_simulator` dello stesso circuito, usato come riferimento invece che assunto. Scope limitato deliberatamente ai soli circuiti QASM custom — Bell/GHZ/VQE mantengono le formule esistenti (già corrette per quei tre casi) per non invalidare i dati storici già raccolti su 5 backend. `graph.py` aggiornato in parallelo: la linea di riferimento ora legge i conteggi reali di `log1` per stato invece di assumere 2 stati a `shots/2`, e l'asse Y usa headroom dinamico sul valore massimo osservato — generalizza a qualunque distribuzione senza toccare i valori di fidelity già misurati sui circuiti built-in.

**Rilevanza per il report — MEDIA-ALTA:**
Rende il "Caso d'uso 2 — Esegui il tuo circuito" del README onesto per qualunque QASM, non solo per circuiti Bell-like. Da menzionare nella sezione metodologica: "the tool reports fidelity for arbitrary circuits by measuring the ideal-simulator distribution directly rather than assuming its shape, and computing Hellinger fidelity against it." Verificato con test numerici sintetici (self-match=1.0, distribuzione uniforme vs concentrata=0.5, caso QASM multi-stato=0.91) e generazione grafico su circuito sintetico a 3 stati dominanti + 2 di leakage, senza errori. `results/custom_comparison.png` esistente è stato generato con la vecchia formula Bell — va rigenerato con un nuovo run `--qasm` prima della pubblicazione.

**Limite intrinseco — da dichiarare esplicitamente nel report:**
La fidelity generica dipende dal poter eseguire il circuito su `ideal_simulator` locale come riferimento. Per circuiti QASM grandi o profondi, questo riferimento diventa esso stesso costoso da calcolare (simulazione classica di stato pieno, scaling esponenziale nel numero di qubit) — quindi il metodo generalizza la *definizione* di fidelity a qualunque circuito, ma non rimuove il limite fondamentale della simulazione classica come termine di paragone. Non è un limite nuovo introdotto da questa fix: Bell/GHZ/VQE hanno già oggi lo stesso vincolo (girano anch'essi su `ideal_simulator` come baseline), ma qui va dichiarato esplicitamente perché il caso d'uso 2 del README promette di accettare "qualsiasi circuito QASM personalizzato" senza qualificare questo limite. Citazione utile per l'articolo: "fidelity for arbitrary circuits is bounded by the tractability of classically simulating the same circuit as a noiseless reference — a limitation shared with any classical-simulation-based benchmark, not specific to this tool."
