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

> **⚠️ ENTRY RITRATTATA (23/07/2026).** La conclusione qui sotto ("Z-basis
> cattura solo ~65% dell'energia, mancano XX+YY per ~0.394 Hartree") è una
> **diagnosi errata**, scoperta dalla revisione del professore. Il plateau a
> -0.7432 Hartree non era un limite di misura ma il minimo esatto raggiungibile
> da un ansatz nel settore di simmetria sbagliato, su un Hamiltoniano con
> coefficienti errati. Con Hamiltoniano corretto (O'Malley 2016) e ansatz
> Hartree-Fock il tool raggiunge -1.1373 Hartree (chemical accuracy). Vedi
> l'entry del 23/07/2026 per la correzione completa. Testo originale mantenuto
> sotto per tracciabilità del percorso decisionale.

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

> **Correzione 20/07/2026:** il confronto puntuale IonQ 98.34% vs QPU 97.66% qui sotto era basato su un singolo run per backend — vedi entry di correzione più sotto ("Correzione metodologica: singolo run non basta per confrontare backend"). Il fix IonQ resta valido, il confronto numerico esatto no.

---

## 20/07/2026 — VQE H2 benchmark completo su 5 backend

**Cosa abbiamo osservato:**
Primo run VQE H2 (2 qubit, 1024 shots, theta ottimale trovato via scan: -0.03173 rad) su tutti e 5 i backend:
ideal_simulator 100.00% (E=-0.7432) | noisy_simulator 96.09% (E=-0.7267) | ibm_qpu_ibm_marrakesh (QPU reale) 99.12% (E=-0.7262), queue 10.6s | aws_local_simulator 100.00% (E=-0.7432) | ionq_simulator 98.73% (E=-0.7444).

**Decisione presa:**
Nessuna modifica al codice. Dato conservato come primo punto dati VQE completo su 5 backend (vedi `results/vqe_comparison.png` e `results/log.json`).

**Rilevanza per il report — ALTA:**
Punto dati di riferimento (fidelity ~95-99% su tutti i backend, confermando la dichiarazione qualitativa già loggata l'01/07). Il confronto diretto col run GHZ va letto insieme alla correzione metodologica sotto.

> **Correzione 20/07/2026:** la conclusione originale di questa entry ("QPU reale batte IonQ, direzione opposta a GHZ") è stata ritirata — basata su un singolo run per backend, differenza troppo piccola per essere distinguibile dal rumore di campionamento. Vedi entry di correzione più sotto.

---

## 20/07/2026 — Correzione metodologica: singolo run non basta per confrontare backend

**Cosa abbiamo osservato:**
Le due entry precedenti (GHZ e VQE) confrontavano IonQ vs QPU reale usando un singolo run per backend, concludendo che la direzione del confronto (chi ha fidelity più alta) dipendesse dal circuito. L'utente ha correttamente fatto notare che le differenze in gioco (0.4-0.7 punti percentuali) sono piccole abbastanza da poter essere semplice rumore di campionamento, non un effetto reale — esattamente l'errore metodologico già identificato e corretto il 29/06 sullo shots-efficiency (singolo run per punto → conclusioni premature).

**Perché succede:**
Stesso meccanismo del 29/06: i noise model sono stocastici, un singolo run a 1024 shots ha varianza di campionamento non trascurabile su differenze di questa dimensione. Non avevamo applicato qui la stessa disciplina (repliche multiple) già stabilita per lo shots-efficiency.

**Decisione presa:**
Rieseguiti GHZ e VQE con 10 repliche a 1024 shots su ideal/noisy/AWS/IonQ (i 4 backend simulati, eseguibili senza account IBM):

| Backend | GHZ mean ± std | VQE mean ± std |
|---|---|---|
| noisy_simulator | 93.47% ± 0.83% | 95.29% ± 0.70% |
| aws_local_simulator | 100.00% ± 0.00% | 100.00% ± 0.00% |
| ionq_simulator | 97.72% ± 0.48% | 98.68% ± 0.41% |

Confrontando con i singoli valori QPU reale già misurati (GHZ 97.66%, VQE 99.12%): su GHZ, QPU (97.66%) cade dentro la distribuzione IonQ (97.72% ± 0.48%) — nessuna differenza significativa. Su VQE, QPU (99.12%) è circa 1 deviazione standard sopra la media IonQ (98.68% ± 0.41%) — indicazione debole, non conclusiva, di una differenza reale (e comunque non replicata sul lato QPU). **La conclusione "la direzione del confronto dipende dal circuito" non è supportata dai dati — va ritirata.**

**Rilevanza per il report — ALTA:**
Punto di onestà metodologica da includere esplicitamente: confrontare backend richiede repliche anche per il benchmark systematico (non solo per lo shots-efficiency), specialmente quando le differenze sono piccole. Il QPU reale resta limitato a un singolo campione per run (costa quota reale ripeterlo) — va dichiarato come tale nel report, non usato per affermazioni di ranking assoluto senza repliche. Se si vuole un confronto IonQ-vs-QPU statisticamente solido, servono repliche anche sul QPU reale (costo: tempo di coda reale moltiplicato per il numero di repliche) — decisione da prendere con l'utente in base al budget di quota IBM disponibile.

---

## 20/07/2026 — Repliche QPU reale completate (5x GHZ, 5x VQE): IonQ-vs-QPU ora statisticamente supportato

**Cosa abbiamo osservato:**
L'utente ha eseguito manualmente 5 repliche GHZ e 5 repliche VQE con `--strategy accurate` (10 submission reali sulla QPU IBM). Il selector ha scelto backend diversi run per run (minimo pending jobs tra `ibm_fez`/`ibm_marrakesh`/`ibm_kingston`).

GHZ — QPU (backend misto, n=5): 94.63% ± 1.70% (valori: 97.27, 94.04, 95.31, 93.26, 93.26 — 4 run su `ibm_fez`, 1 su `ibm_marrakesh`). IonQ (n=5, stesso venv utente): 97.89% ± 0.60%. Coda QPU: 10.6-116.6s (media 40.6s).

VQE — QPU (backend misto, n=5): 97.30% ± 1.79% (valori: 95.51, 95.21, 98.83, 98.34, 98.63). Di cui **solo `ibm_fez` (n=2): 95.36% media** vs **solo `ibm_marrakesh` (n=3): 98.60% media**. IonQ (n=5): 98.83% ± 0.12%. Coda QPU: 10.6-33.4s (media 23.5s).

**Perché è rilevante:**
1. Su GHZ, con repliche vere il gap IonQ (97.89±0.60%) vs QPU (94.63±1.70%) è ora reale e statisticamente supportato (~1.9 deviazioni standard della QPU separano le medie) — conferma la direzione originariamente osservata (e poi correttamente ritirata per mancanza di repliche), stavolta con evidenza solida.
2. Su VQE il quadro è più sfumato: la varianza della QPU (±1.79%) è quasi interamente spiegata da **quale macchina è stata selezionata**, non da rumore casuale — `ibm_marrakesh` (98.60% media) supera nettamente `ibm_fez` (95.36% media) sullo stesso circuito. Questo è di per sé un risultato interessante e coerente con l'argomento centrale della tesi: la selezione autonoma del backend ha un impatto misurabile sulle performance, non solo sul tempo di coda (già dimostrato il 29/06) ma anche sulla fidelity ottenuta.
3. IonQ resta comunque il valore più alto e più stabile (std piccolo, 0.12-0.60%) in entrambi i circuiti — coerente col fatto che è un simulatore con noise model fisso, mentre la QPU riflette variabilità hardware reale (calibrazione, macchina selezionata, crosstalk).

**Decisione presa:**
Nessuna modifica al codice. Dati conservati come misura di riferimento per Bell/GHZ/VQE nel report. Cancellati (su richiesta dell'utente) gli script/file temporanei usati per la replica (`run_replicas.ps1`, `manual_replicas_ghz.txt`, `manual_replicas_vqe.txt`) — il codice del progetto non è stato toccato da questo test.

**Rilevanza per il report — ALTA:**
Sostituisce le entry precedenti (single-run, poi ritirate) con dati solidi da 5 repliche reali. Da includere nella sezione risultati: il gap IonQ-vs-QPU su GHZ è confermato reale (non rumore), mentre su VQE la fonte primaria di variabilità è la scelta del backend IBM, non il rumore casuale — supporto quantitativo diretto alla tesi su selezione autonoma del backend. Caveat da mantenere: n=5 non è il gold standard n=10 già usato per lo shots-efficiency, e tutte le misure sono state raccolte nella stessa sessione (~1 ora) — lo stato di calibrazione delle macchine IBM in quel momento non è necessariamente rappresentativo di altri momenti (vedi 29/06, coda `ibm_kingston` fino a 3645s in altre occasioni).

---

## 22/07/2026 — Bell rilanciato post-fix: dati aggiornati su tutti e 5 i backend

**Cosa abbiamo osservato:**
`--circuit bell --strategy accurate` rilanciato dopo il fix IonQ (19/07) e gli altri cambi di sessione: ideal_simulator 100.00% | noisy_simulator 96.58% | ibm_qpu_ibm_marrakesh 98.54% (queue 21.7s) | aws_local_simulator 100.00% | ionq_simulator 98.73%.

**Perché è rilevante:**
Singolo run (n=1), quindi nessuna conclusione forte sulla direzione IonQ-vs-QPU da questo dato isolato — lezione già applicata in questa sessione. Il valore IonQ (98.73%) resta comunque dentro il range già misurato prima del fix (98.14-99.41%): Bell ha un solo CNOT (come VQE), quindi l'impatto del fix a due qubit è più contenuto che su GHZ (due CNOT) — coerente con quanto già osservato.

**Decisione presa:**
Nessuna modifica al codice. `results/bell_comparison.png` e `results/log.json` aggiornati con dati correnti, sostituendo la versione del 3 luglio (pre-fix).

**Rilevanza per il report — MEDIA:**
Dato di riferimento aggiornato per la tabella misure finale. Se si vuole un confronto IonQ-vs-QPU statisticamente solido anche su Bell (come fatto per GHZ/VQE), servirebbero repliche multiple — non fatto qui, singolo run sufficiente solo come punto di riferimento post-fix.

---

## 22/07/2026 — README e Guida Progetto: comando d'esempio QASM custom era sbagliato

**Cosa abbiamo osservato:**
Il comando d'esempio per il "Caso d'uso 2" (eseguire un circuito QASM personalizzato) in README e Guida Progetto usava `--circuit file.qasm`, ma il flag CLI effettivo è `--qasm` (`--circuit` accetta solo `bell`/`ghz`/`vqe`/`all`). Anche `--circuit vqe_h2` nella sezione "Run built-in benchmarks" del README era sbagliato (il valore corretto è `vqe`).

**Perché succede:**
Refuso di documentazione risalente probabilmente a una versione precedente della CLI, mai aggiornato dopo l'implementazione finale degli argomenti argparse.

**Decisione presa:**
Corretti entrambi i comandi in README.md e Quantum_Orchestrator_Guida_Progetto.md.

**Rilevanza per il report — MEDIA:**
Bug di riproducibilità concreto: chiunque avesse seguito il README/Guida alla lettera per il caso d'uso pubblicizzato come principale ("esegui il tuo circuito") avrebbe ricevuto un errore argparse. Da controllare sempre che i comandi in un README pubblico siano stati effettivamente testati, non solo scritti a mano.

---

## 20/07/2026 — L'import scipy.optimize in vqe_h2.py non era mai usato

**Cosa abbiamo osservato:**
Verificando il blocco Windows Application Control (entry precedente), `from scipy.optimize import minimize_scalar` in `vqe_h2.py` non veniva mai chiamato nel resto del file — `_get_optimal_theta()` usa uno scan brute-force con numpy (`np.linspace` + `np.argmin`), non `minimize_scalar`.

**Perché succede:**
Import residuo, probabilmente da una versione precedente dell'implementazione che usava l'ottimizzatore scipy, poi sostituita dallo scan manuale senza rimuovere l'import.

**Decisione presa:**
Rimosso l'import morto. Verificato (con scipy.optimize forzatamente bloccato in sandbox) che il circuito VQE si crea con lo stesso theta ottimale di prima, senza toccare scipy.optimize in nessun modo — VQE ora dipende solo da numpy.

**Rilevanza per il report — MEDIA:**
Risolve il blocco Windows Application Control della entry precedente alla radice invece di limitarsi a isolarlo, e semplifica l'installazione per chi replica il progetto (una dipendenza pesante e fragile su Windows in meno).

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

---

## 22/07/2026 — Hardening pre-pubblicazione: path assoluti, encoding, requirements.txt, repo hygiene

**Cosa abbiamo osservato:**
Passata di verifica end-to-end richiesta esplicitamente ("controllare ogni angolo e sfumatura prima di andare avanti") ha trovato quattro problemi latenti, mai emersi prima perché mai testati nelle condizioni giuste: (1) lo stdout crashava con `UnicodeEncodeError` su Windows quando l'output veniva rediretto su file invece che stampato su console interattiva; (2) lanciare lo script da dentro `src/` invece che dalla root del progetto ricreava silenziosamente una cartella `src/results/` duplicata — stesso sintomo già ripulito manualmente il 29-30/06 senza allora capirne la causa; (3) `requirements.txt` era un dump grezzo di `pip freeze` (~150 pacchetti, incluso Azure Quantum SDK abbandonato e tool Jupyter mai usati) ed era codificato in UTF-16LE invece di UTF-8; (4) `Quantum_Orchestrator_Guida_Progetto.md` era elencato in `.gitignore` ma restava comunque tracciato da git (committato prima di essere aggiunto al gitignore), quindi sarebbe finito nel repo pubblico nonostante l'intento contrario.

**Perché succede:**
(1) Windows usa la codepage di sistema (cp1252) per stdout quando non è collegato a una console interattiva, incapace di codificare i caratteri box-drawing dei diagrammi circuitali. (2) tutti i path `results/...` in `orchestrator.py`, `graph.py`, `shots_efficiency.py` erano relativi alla working directory invece che ancorati alla posizione dello script. (3)/(4) entrambi retaggi di comandi PowerShell (`pip freeze >`, commit fatto prima del gitignore) mai rivisti dopo.

**Decisione presa:**
(1) `sys.stdout.reconfigure(encoding="utf-8")` / `sys.stderr.reconfigure(encoding="utf-8")` a inizio `orchestrator.py`. (2) creato `src/paths.py` con `RESULTS_DIR` assoluto ancorato a `__file__`, adottato nei tre file. (3) `requirements.txt` riscritto con i soli 7 pacchetti realmente importati (verificato via grep), versioni pinnate, UTF-8 pulito. (4) `git rm --cached Quantum_Orchestrator_Guida_Progetto.md` — il file resta sul disco e nel `.gitignore`, ma esce dal tracking futuro. Aggiunto anche `.gitattributes` (`* text=auto`) per normalizzare CRLF/LF tra Windows e ambienti Linux/CI, standard per repo pubblici multipiattaforma.

**Rilevanza per il report — ALTA:**
Tutti e quattro sono bug di riproducibilità reali che avrebbero colpito chiunque provasse a clonare ed eseguire il repo pubblico da zero su Windows (il target realistico per un tool che confronta backend quantistici) — non solo dettagli estetici. Da menzionare nella sezione metodologica/limitazioni: testare sempre gli strumenti nelle condizioni in cui un utente reale li userà (redirect su file, cartella di lavoro diversa, `pip install` pulito), non solo nelle condizioni in cui sono stati sviluppati.

---

## 22/07/2026 — Conversione Qiskit→Braket: da skip silenzioso a conversione generica + fail loud

**Cosa abbiamo osservato:**
`braket_utils.qiskit_to_braket()` (usato da AWS e IonQ) convertiva solo 4 gate (h, x, cx, ry). Qualunque altro gate — anche banali come S, T, Z, presenti in praticamente ogni circuito non-Bell — veniva silenziosamente scartato con una singola riga di print, senza interrompere l'esecuzione. Il circuito eseguito su AWS/IonQ era quindi diverso da quello caricato dall'utente, ma la fidelity generica (Hellinger, introdotta il 19/07) veniva comunque calcolata e mostrata come se il confronto fosse valido. Riprodotto con un test diretto: un circuito con h/s/t/z/cx risultava, lato Braket, con s/t/z silenziosamente assenti. Il path IBM (ideal/noisy simulator via Aer, QPU reale via transpile) non ha questo problema — non passa da questa funzione.

**Perché succede:**
La funzione era stata scritta deliberatamente minimale, sufficiente solo per Bell/GHZ/VQE H2 (l'unico uso previsto all'inizio). Quando è stato aggiunto il supporto per QASM arbitrari (19/07), la funzione di conversione non è stata ampliata di conseguenza — il README promette "pass any OpenQASM file" ma la conversione reale copriva un sottoinsieme molto più piccolo, senza nessun segnale d'errore per l'utente.

**Decisione presa:**
Riprogettata la conversione su tre livelli, non solo ampliato l'elenco:
1. Gate nominati espliciti (h, x, y, z, s, sdg, t, tdg, rx, ry, rz, cx, cz, swap, ccx) — mappano 1:1 su metodi dell'API Braket documentata (`circ.si()` per S-dagger, `circ.ti()` per T-dagger — nomi diversi da Qiskit, verificato sulla developer guide AWS).
2. Fallback generico per qualunque altro gate a **un solo qubit** (u, u1, u2, u3, gate custom): conversione tramite la sua matrice unitaria (`instruction.operation.to_matrix()` → `braket_circuit.unitary(matrix=..., targets=...)`), sicura perché un singolo qubit target non ha ambiguità di ordinamento.
3. Qualunque gate non nominato **su più qubit** (es. iSwap, gate custom multi-qubit) solleva `UnsupportedGateError` invece di essere scartato — l'ordinamento dei qubit in un fallback generico multi-qubit è l'unico punto dove Qiskit e Braket potrebbero non coincidere senza verifica, quindi si preferisce fermarsi con un errore esplicito piuttosto che rischiare un dato silenziosamente sbagliato.
`orchestrator.py` intercetta `UnsupportedGateError` sui soli backend AWS/IonQ del path QASM custom e salta quel backend con un messaggio esplicito (stesso trattamento già riservato a un backend non disponibile), senza interrompere il resto del confronto. Corretto in parallelo un bug collegato: un file `--qasm` non trovato/malformato causava un fallback silenzioso all'esecuzione di bell+ghz+vqe su tutti i backend invece di fermarsi — ora esce subito con errore esplicito.

**Limite dichiarato — da esplicitare nell'articolo:**
"Qualunque circuito QASM" è vero nella pratica per qualunque circuito composto da gate unitari standard (che copre la stragrande maggioranza dei casi reali/didattici), ma non è un supporto universale: gate multi-qubit non tra quelli nominati esplicitamente (es. iSwap, gate custom a 2+ qubit) non vengono convertiti — il tool si ferma con un errore invece di produrre un dato scorretto. Verificato con un vero SDK Braket (1.110.1, non solo una classe `Circuit` fittizia): circuito con h/sdg/tdg/u3/cz/swap eseguito correttamente su `aws_local_simulator` e `ionq_simulator`, `si`/`ti` instradati correttamente per sdg/tdg, il fallback generico su `u3` attivato con il messaggio atteso, e un gate multi-qubit non riconosciuto (iSwap) solleva `UnsupportedGateError` come previsto invece di essere scartato in silenzio.

**Rilevanza per il report — ALTA:**
Questo è il caso concreto da citare per spiegare quanta libertà ha davvero la feature "inserisci il tuo circuito": non è una conversione universale (richiederebbe una libreria dedicata come qiskit-braket-provider, scartata per non aggiungere una dipendenza extra vicino alla scadenza), ma una conversione esplicita per i gate standard più una via generica sicura per qualunque gate a singolo qubit — con un confine netto e dichiarato (non silenzioso) per i gate multi-qubit non comuni. Citazione utile: "the tool converts arbitrary single-qubit gates generically via their unitary matrix, and explicitly refuses — rather than silently mishandles — multi-qubit gates outside a fixed named set, to avoid an unverified qubit-ordering assumption."

---

## 22/07/2026 — Rifinitura fix gate: noise model IonQ esteso a cz/swap, ccx dichiarato non modellato, print fidelity fuorviante corretto

**Cosa abbiamo osservato:**
Due strascichi minori dell'ampliamento della conversione gate di oggi. (1) `ionq.py` applicava il depolarizing a due qubit solo ai gate `cx`: ora che `cz` e `swap` vengono convertiti correttamente, venivano eseguiti senza il loro rumore a due qubit — circuito giusto, modello di rumore incompleto per quei gate. (2) Il run di riferimento `ideal_simulator` nel path QASM custom stampava in console una fidelity calcolata con la formula di Bell (es. "0.00%" o altri valori senza senso su circuiti a 3 qubit) prima che il codice la sovrascrivesse a 1.0 per il salvataggio — il dato salvato era sempre corretto, ma l'output a schermo poteva sembrare un fallimento.

**Perché succede:**
(1) Il controllo `if instruction.operation.name == 'cx'` non è stato aggiornato quando sono stati aggiunti `cz`/`swap` alla conversione. (2) `run_job()` stampa `result['fidelity']` subito dopo `adapter.run()`, che per `IBMSimulatorAdapter` calcola sempre di default `compute_fidelity` (formula Bell) — l'override a 1.0 avveniva dopo, in `orchestrator.py`, quindi dopo la stampa.

**Decisione presa:**
(1) Esteso il controllo a `('cx', 'cz', 'swap')`. `ccx` (Toffoli, 3 qubit) resta esplicitamente NON modellato — non esiste un canale di rumore a due qubit direttamente applicabile a 3 qubit, e costruire un'approssimazione arbitraria (es. rumore su ogni coppia) sarebbe stata una scelta arbitraria e non giustificata; meglio dichiararlo apertamente con un warning a schermo (`[IonQ] Warning: ccx (Toffoli) has no two-qubit noise model applied`) che inventare un numero. (2) `fidelity_fn=lambda counts, shots: 1.0` passato direttamente a `run_job()` per il run di riferimento, invece di sovrascrivere il dizionario dopo — stampa e dato salvato ora coincidono sempre.

**Rilevanza per il report — MEDIA:**
Esempio concreto di scelta metodologica onesta invece di un'approssimazione comoda: per Toffoli si è preferito dichiarare esplicitamente "non modellato" piuttosto che inventare un modello di rumore multi-qubit non validato. Utile per la sezione metodologica come esempio di trasparenza attiva sui limiti del noise model.

---

## 22/07/2026 — Limitazioni note e accettate del progetto (riferimento consolidato per la sezione Limitazioni dell'articolo)

Non è un nuovo bug o una nuova decisione — è un indice, richiesto esplicitamente per l'onestà scientifica del report, di tutti i punti in cui il progetto ha scelto consapevolmente un'approssimazione pragmatica invece di una soluzione completa. Ogni punto rimanda alla entry originale per i dettagli; qui c'è solo la sintesi e la giustificazione, pensata per essere trasportata quasi direttamente nella sezione "Limitations" dell'articolo.

1. **Il noise model non è calibrato sul backend reale effettivamente selezionato.** `noisy_simulator` usa parametri fissi "tipici" (0.1% singolo qubit, 1% CNOT, 2% readout per IBM; 0.03/0.3/0.5% per IonQ), non i parametri di calibrazione reali di `ibm_fez` o `ibm_marrakesh` a seconda di quale viene scelto quella run. È un modello di rumore generico usato come termine di paragone, non una replica del backend specifico misurato nello stesso confronto. Giustificazione: calibrare dinamicamente il modello richiederebbe interrogare le API di calibrazione IBM ad ogni run (dati non sempre disponibili in tempo reale, e comunque un'informazione che il noise model "generico" non pretende di catturare) — fuori scope per un tool che confronta *categorie* di backend, non predice la fidelity esatta di una macchina specifica.

2. **Le soglie di queue/timeout sono costanti scelte, non misurate.** `ESTIMATED_EXEC_S = 10` e `ABSOLUTE_TIMEOUT_S = 1800` (`backends/ibm.py`) sono stime ragionevoli ma fisse, non derivate da una misurazione empirica per ogni combinazione circuito/shots/backend. Le tre strategie (responsive/accurate/adaptive) sono corrette nella logica ma il loro punto di soglia esatto è un parametro di design, non un valore calibrato.

3. **I circuiti testati sono piccoli e poco profondi (2-3 qubit, profondità 3-5).** Bell, GHZ e VQE H2 minimale sono scelti apposta per isolare l'effetto backend/noise dal rumore di un circuito complesso, ma questo significa che i risultati (es. il rapporto queue/execution 1822:1, il gap IonQ-vs-QPU) non sono stati verificati su circuiti più grandi o più profondi, dove l'accumulo di errore per gate potrebbe cambiare il quadro. Da dichiarare come limite di generalizzabilità, non solo come scelta di design.

4. **Il supporto per circuiti QASM custom è per circuiti puramente unitari + misura finale, non per circuiti dinamici.** Nessun supporto per misura intermedia, reset, o gate condizionati classicamente (`if`) — non presenti in OpenQASM 2.0 "base" ma disponibili in alcune estensioni. Il tool assume un circuito "classico": tutti i gate, poi tutte le misure alla fine.

5. **Riferimenti alle limitazioni già documentate in dettaglio altrove, per completezza dell'indice:** IonQ è un simulatore calibrato, non hardware fisico (29/06); ~~VQE H2 misura solo la base Z, ~65% dell'energia totale (20/07)~~ **[SUPERATO 23/07: era una diagnosi errata; il tool ora misura l'energia completa di H₂ a chemical accuracy con misura Z+X, -1.1373 Ha — vedi entry 23/07]**; la fidelity generica per QASM richiede che `ideal_simulator` sia trattabile classicamente, quindi non scala a circuiti troppo grandi (19/07); la conversione Braket copre gate nominati + fallback generico a singolo qubit, i gate multi-qubit non comuni sollevano un errore esplicito invece di essere approssimati (22/07); il noise model IonQ non modella `ccx` (22/07, sopra).

**Rilevanza per il report — ALTA:**
Questo è l'indice da cui partire per scrivere la sezione Limitations dell'articolo. Il filo conduttore comune a tutti i punti: ogni volta che il progetto ha lasciato correre un'approssimazione, lo ha fatto dichiarandolo esplicitamente (a schermo, nel codice, o qui) invece di nasconderlo — la trasparenza sui limiti è essa stessa un risultato metodologico del progetto, non solo una nota a margine.

---

## 23/07/2026 — REVISIONE DEL PROFESSORE: bug fisico VQE H₂ — Hamiltoniano sbagliato + ansatz nel settore sbagliato, corretti

**Cosa abbiamo osservato:**
La code review del professore (commit `8d00f05`) ha sollevato che le affermazioni fisiche del benchmark VQE non corrispondono all'Hamiltoniano codificato. Verifica indipendente con `numpy.linalg.eigvalsh` sui `HAMILTONIAN_COEFFS` di `vqe_h2.py`: autovalori `[-1.4556, -0.7432, -0.6361, -0.4073]`. **-1.1372 Hartree (l'energia esatta di H₂, dichiarata come ground truth del benchmark) non è un autovalore di quell'Hamiltoniano.** Inoltre lo stato fondamentale di quell'Hamiltoniano (E=-1.4556) vive in span{|01⟩,|10⟩}, mentre l'ansatz `Ry(θ)→CX` produceva solo stati in span{|00⟩,|11⟩}, il cui minimo raggiungibile è esattamente -0.7432 — il "plateau" che avevamo osservato l'01/07 e interpretato come limite della misura Z-basis.

**Perché succede:**
Due errori indipendenti sommati.
1. **Coefficienti Hamiltoniani errati.** I valori in `HAMILTONIAN_COEFFS` (attribuiti a Kandala et al. 2017) erano mal trascritti/mal assegnati: davano ground -1.4556, non -1.1372. Inoltre contenevano una coppia simmetrica XX+YY, mentre la forma ridotta a 2 qubit corretta (parity mapping + riduzione Z2) ha **un solo termine off-diagonale X₀X₁**, non XX+YY.
2. **Ansatz nel settore di simmetria sbagliato.** `Ry(θ)|00⟩→CX` resta in span{|00⟩,|11⟩}; il ground state vero è nel settore a numero di particelle 1, span{|01⟩,|10⟩}. Partendo da |00⟩ senza uno stato di riferimento Hartree-Fock, l'ansatz non poteva fisicamente raggiungere l'energia vera, indipendentemente da θ.

Conseguenza: la conclusione dell'01/07 ("Z-basis cattura ~65% dell'energia, mancano i termini XX+YY per ~0.394 Hartree") **era una diagnosi errata**. Il -0.7432 non era una stima parziale ma il minimo *esatto e completo* raggiungibile da quell'ansatz su quell'Hamiltoniano sbagliato — misurare in base X/Y non avrebbe recuperato nessuna energia mancante.

**Cosa funziona davvero (verificato numericamente, non fidandoci di trascrizioni):**
Set canonico O'Malley et al., *Phys. Rev. X* 6, 031007 (2016), H₂ STO-3G a R=0.735 Å:
`II=-1.05237, Z₀=+0.39793, Z₁=-0.39793, Z₀Z₁=-0.01128, X₀X₁=+0.18093` (un solo termine XX). Parte elettronica: ground -1.8573 Ha. Ripiegando la repulsione nucleare (E_nuc = 1/R = +0.7199 Ha) nel termine identità, `eigvalsh` dà ground **-1.13729 Ha** = esatto (-1.1372) ✓. Lo stato fondamentale vive in span{|01⟩,|10⟩}, come previsto.

Ansatz corretto (single-excitation / Givens, conserva il numero di particelle), soli gate `x/cx/ry` (convertibili su Braket): `X(q0) → CX(0,1) → Ry(θ,1) → CX(1,0)`, che parte dallo stato Hartree-Fock |01⟩ e ruota dentro il settore giusto. Raggiunge esattamente -1.13729 a θ_opt≈2.9185, zero leakage. Verificata anche la catena di misura completa: energia ricostruita da conteggi misurati (Aer reale, 10⁵ shot) = -1.1375 Ha (entro rumore statistico), fidelity 1.0, base Z da sola = -1.0975 Ha (96.5% dell'energia), il termine X₀X₁ (base X, un circuito extra con H sui due qubit) aggiunge il restante 3.5%.

**Decisione presa:**
1. `vqe_h2.py` riscritto: coefficienti corretti con repulsione nucleare esplicita, ansatz Hartree-Fock+Givens, `compute_energy_h2(counts_z, counts_x, ...)` che stima l'energia completa da due basi (Z per i termini diagonali, X per X₀X₁), `compute_energy_h2_zdiagonal()` per riportare la frazione Z-only (96.5%), `compute_fidelity_vqe` aggiornata ai nuovi stati dominanti |01⟩/|10⟩.
2. `_get_optimal_theta()` ora fa uno scan analitico dell'energia in solo numpy (deterministico, istantaneo) invece dei 100 job Aer stocastici a 8192 shot all'import — risolve anche il nit della review sul codice morto `_energy_analytical` e sulla dipendenza da scipy/Aer al momento della creazione del circuito.
3. `orchestrator.py`: blocco VQE esegue due circuiti (base Z e base X) su ogni backend e combina l'energia; stampa aggiornata con la nuova narrativa.
4. Scelta consapevole misura completa Z+X (concordata con l'utente) invece della sola base Z: raddoppia i job VQE sulla QPU reale ma restituisce l'energia fisica vera, misurata non assunta — coerente con l'etica del progetto ("misuro ciò che la letteratura descrive").

**Conseguenza sui dati:** tutti i dati VQE storici (fidelity e energia, README/Guida/log) sono stati prodotti con l'ansatz e le metriche vecchie e vanno **rimisurati** con il codice corretto — stesso trattamento del fix IonQ del 19/07. Solo i valori deterministici ideal/AWS (fidelity 100%, E=-1.1373) sono già confermati.

**Verifica ancora aperta:** il path AWS/IonQ (conversione Braket) non è stato eseguito live in sandbox (ambiente non persistente, install braket troppo pesante), ma è coperto per costruzione — i gate `x/cx/ry/h` sono tutti nella lista supportata da `braket_utils` e già validati contro il vero SDK Braket il 22/07. Da confermare nel primo run reale dell'utente. **[AGGIORNAMENTO: il run reale ha subito rivelato il bug endianness #1 — vedi entry sotto.]**

**Rilevanza per il report — ALTA (e cambia in meglio il claim):**
La vecchia narrativa "il tool misura solo il 65% dell'energia di H₂" era sbagliata *e più debole* di quella vera. Con il setup corretto il tool **misura l'energia di ground state di H₂ a chemical accuracy (-1.1373 vs -1.1372 Ha)**: la base Z cattura il 96.5%, un solo circuito extra in base X recupera il termine X₀X₁ restante. È un claim molto più forte e ora corretto — da riscrivere così nell'articolo prima della bozza. Lezione metodologica trasversale (da includere in "Methodology"/"Lessons Learned"): una check di sanità fisica banale — `eigvalsh(H)[0] ≈ E_exact` — avrebbe intercettato subito il bug; è ora un test da inserire nella suite (vedi punto #7 della review). Un risultato "plausibile e stabile" (-0.7432 riproducibile su tutti i backend) non è garanzia di correttezza: era esatto per l'Hamiltoniano sbagliato.

---

## 23/07/2026 — Bug endianness Braket↔Qiskit (review #1) smascherato dal nuovo VQE, corretto

**Cosa abbiamo osservato:**
Primo re-measure VQE post-fix (`--circuit vqe --strategy accurate`, 1024 shot). L'energia sui backend Braket era palesemente sbagliata mentre la fidelity sembrava perfetta:

| Backend | Counts dominante | Energia (Z+X) | Fidelity |
|---|---|---|---|
| ideal_simulator (Qiskit) | `01` (1008) | -1.1412 ✓ | 100.00% |
| ibm_qpu_ibm_kingston (Qiskit) | `01` (994) | -1.1155 ✓ | 98.24% |
| aws_local_simulator (Braket) | **`10`** (1011) | **+0.4234** ✗ | 100.00% |
| ionq_simulator (Braket) | **`10`** (996) | **+0.4055** ✗ | 99.02% |

I backend Braket riportavano `10` dove Qiskit riportava `01`: bit invertiti. La fidelity restava a 100%/99% perché `compute_fidelity_vqe` somma `01`+`10` (simmetrica → immune all'inversione), ma l'energia dipende da `⟨Z₀⟩` e `⟨Z₁⟩`, che si scambiano di segno invertendo i qubit → energia con segno ribaltato (+0.45 invece di -1.10 sulla parte Z-diagonale). Verifica numerica: la parte Z-diagonale "buggy" calcolata a mano dai counts AWS dà esattamente +0.4545, identica a quella misurata — riproduzione esatta del bug.

**Perché succede:**
Braket e Qiskit usano convenzioni opposte di ordinamento dei bit: Braket mette il qubit 0 nel bit più a sinistra della stringa dei counts, Qiskit nel più a destra. `aws.py`/`ionq.py` costruivano le chiavi unendo i bit nell'ordine nativo di Braket senza invertirle. È esattamente il bug #1 della review del professore. Era rimasto invisibile perché tutti i benchmark precedenti (Bell `00`/`11`, GHZ `000`/`111`, vecchio VQE `00`/`11`) hanno stati dominanti **palindromi** — invertire la stringa li mappa in sé stessi. Il nuovo ansatz VQE corretto ha stato dominante `01`, **asimmetrico**, e ha reso il bug immediatamente visibile.

**Decisione presa:**
Invertita la bitstring in entrambi gli adapter Braket: `"".join(str(b) for b in k)[::-1]`. Sicuro per i dati storici: Bell/GHZ sono palindromi, l'inversione è un no-op per loro. Verificato che dopo il fix i counts AWS `{'10':1011,'01':13}` diventano `{'01':1011,'10':13}` (allineati a Qiskit) e la parte Z-diagonale torna a -1.0968, in linea con l'ideale (-1.0921, differenza = solo rumore di shot). Restano NON ancora affrontate le due sfaccettature minori del punto #1, rilevanti solo per il path QASM custom (non per Bell/GHZ/VQE che misurano tutti i qubit): (1a) i qubit inattivi vengono scartati da Braket → chiavi più corte del riferimento, da padding; (1b) la mappa di misura (`measure q[i]->c[j]`) viene ignorata. Da fare quando si consolida il caso d'uso 2.

**Rilevanza per il report — ALTA (doppia lezione metodologica):**
1. **Una metrica simmetrica può nascondere un bug asimmetrico.** La fidelity (simmetrica per costruzione su Bell/GHZ/VQE) ha mascherato per settimane un errore di ordinamento dei bit; è emerso solo quando una *seconda* metrica sensibile all'ordine (l'energia) è stata calcolata su uno stato asimmetrico. Argomento diretto per la sezione Methodology: usare metriche con sensibilità diverse, non una sola.
2. **Correggere un bug ne ha rivelato un altro.** Il fix VQE (stato dominante da palindromo `00`/`11` ad asimmetrico `01`) ha trasformato il bug endianness da latente a osservabile — esempio da manuale del perché i test vanno fatti su input asimmetrici (esattamente il test che la review raccomanda al punto #7). Da citare come caso concreto nel report.

---

## 23/07/2026 — Convergenza energia VQE vs shot: rumore statistico vs bias sistematico

**Cosa abbiamo osservato:**
Nuovo benchmark `vqe_energy_convergence.py` (energia VQE vs numero di shot, 10 repliche/punto, 128→8192 shot) su ideal/noisy/IonQ. Dati:

| Shots | ideal E±std (mHa off) | noisy E±std (mHa off) | IonQ E±std (mHa off) |
|---|---|---|---|
| 128  | -1.1470 ± 19.8 mHa (9.8) | -1.0798 ± 14.0 (57.4) | -1.1223 ± 24.7 (14.9) |
| 1024 | -1.1395 ± 6.6 mHa (2.3)  | -1.0845 ± 9.0 (52.7)  | -1.1251 ± 8.9 (12.1) |
| 4096 | **-1.1372 ± 4.2 mHa (0.0)** | -1.0851 ± 4.5 (52.1) | -1.1235 ± 5.5 (13.7) |
| 8192 | -1.1368 ± 2.2 mHa (0.4)  | -1.0857 ± 3.4 (51.5)  | -1.1221 ± 3.3 (15.1) |

Std ideale (128→8192): `[19.8, 8.6, 9.6, 6.6, 4.0, 4.2, 2.2]` mHa — scala pulito come 1/√shots (4× shot → ~½ std).

**Perché è rilevante:**
1. **L'ideale converge all'esatto:** la media entra nella banda di chemical accuracy (±1.6 mHa) da ~2048 shot, e a 4096 shot è -1.1372 esatto (0.0 mHa). Conferma sperimentale, non solo analitica, che l'ansatz+Hamiltoniano sono corretti.
2. **Statistico vs sistematico:** i due backend rumorosi non convergono all'esatto — si fermano su un plateau (noisy ~-1.085, bias ~51 mHa; IonQ ~-1.123, bias ~13 mHa). Più shot restringono le barre d'errore (rumore statistico ∝ 1/√shots) ma non spostano il plateau (bias sistematico del noise model). È la distinzione tra errore statistico (mediabile) ed errore sistematico (non mediabile) resa visibile su un dato reale.
3. **IonQ meno biased di IBM noisy sull'energia** (13 vs 51 mHa): stessa direzione già osservata su fidelity (29/06, 20/07: noise model IonQ ottimistico), ora quantificata su una seconda metrica indipendente — buona conferma incrociata.
4. **Onestà sul claim chemical accuracy:** lo std di singolo run non scende mai sotto 1.6 mHa nel range testato (2.2 mHa anche a 8192). Quindi la chemical accuracy è raggiunta dallo *stimatore mediato* su repliche, non da un singolo run a pochi shot — l'ansatz la raggiunge esattamente (proprietà del circuito), ma dimostrarla su hardware/simulatore richiede o repliche o ~20k+ shot per run.

**Decisione presa:**
Nessuna modifica al codice del tool. Aggiunto `vqe_energy_convergence.py` come benchmark separato (companion di `shots_efficiency.py`). Dati salvati in `results/vqe_energy_convergence.{png,json}`.

**Rilevanza per il report — ALTA:**
Grafico forte e diretto per l'articolo, che unisce due fili del progetto: la disciplina delle repliche (dal 29/06) e la storia del bias IonQ. Frase citabile: *"shot noise averages out as 1/√N and the ideal estimator reaches chemical accuracy, but the noise-model bias is systematic — additional shots shrink the error bars without moving the plateau, cleanly separating statistical from systematic error on a measured observable."* Da affiancare al grafico shots-efficiency della fidelity: uno mostra la convergenza della varianza, l'altro la distinzione varianza-vs-bias sull'energia.

---

## 23/07/2026 — Suite di test minima (review #7): ha stanato subito il facet 1a dell'endianness

**Cosa abbiamo osservato:**
Aggiunta la suite di test minima raccomandata dalla review (`tests/`, `unittest` stdlib, nessuna nuova dipendenza), tre file: `test_fidelity.py` (funzioni di fidelity su counts sintetici), `test_vqe_physics.py` (sanity fisica VQE, incluso `eigvalsh(H)[0] ≈ E_exact`), `test_braket_endianness.py` (round-trip Qiskit↔Braket su circuito **asimmetrico**). 18 test totali. Al primo run, il test endianness su AWS ha fallito con un errore inatteso: circuito "X sul qubit 0" (qubit 1 inattivo) → i backend Braket restituivano `{'1': 2000}`, chiave di **un solo carattere** invece di `01`. Non era il facet principale dell'endianness (già corretto con l'inversione della bitstring), ma il **facet 1a della review**: Braket campiona solo i qubit che compaiono nel circuito, quindi un qubit inattivo viene omesso dalla stringa dei counts.

**Perché succede:**
Il facet 1a era stato dichiarato "aperto, rilevante solo per QASM custom" nella entry endianness precedente. Il test l'ha materializzato con un circuito minimale asimmetrico con qubit inattivo — esattamente lo scenario che un utente del caso d'uso 2 potrebbe passare. Bell/GHZ/VQE non lo attivano perché hanno tutti i qubit attivi.

**Decisione presa:**
1. Corretto 1a in `braket_utils.qiskit_to_braket()`: padding con identità (`braket_circuit.i(q)`) su ogni qubit `range(num_qubits)` prima della conversione dei gate, così ogni qubit compare nel circuito Braket e viene misurato. No-op per i circuiti con tutti i qubit attivi (Bell/GHZ/VQE) → dati storici non toccati. Dopo il fix i 3 test endianness passano.
2. Suite eseguibile con `python -m unittest discover -s tests`. I test che richiedono l'ambiente completo (fidelity generica → `qiskit_ibm_runtime`) si auto-skippano invece di fallire.
3. Resta aperto il solo facet 1b (mappa di misura `measure q[i]->c[j]` ignorata, rilevante solo per QASM custom che misurano un sottoinsieme o rimappano i bit classici) — nessun built-in lo attiva; da affrontare se/quando si consolida il caso d'uso 2.

**Rilevanza per il report — ALTA (meta-punto):**
Esempio concreto e citabile del valore dei test: la suite ha trovato un bug reale (1a) **lo stesso giorno in cui è stata scritta**, su un input asimmetrico — esattamente la classe di input che la review indicava come necessaria e che i circuiti simmetrici del progetto non potevano coprire. Rafforza la lezione già emersa oggi (metrica simmetrica nasconde bug asimmetrico): non solo le metriche, ma anche i *test* vanno progettati su casi asimmetrici. I due test-chiave (`eigvalsh` e round-trip asimmetrico) sono ora una rete di regressione permanente contro i due bug severità-alta corretti oggi.

---

## 23/07/2026 — Rumore IonQ ora interlacciato coi gate (review #3): scala con la profondità

**Cosa abbiamo osservato:**
La review (#3) ha rilevato, dumpando la lista di istruzioni Braket, che in `ionq.py` tutti i canali di rumore erano appesi **alla fine** del circuito: il depolarizing a singolo qubit una volta per *qubit* (non per gate) e quello a due qubit dopo tutti i gate. Due conseguenze: (a) un circuito profondo 100 riceveva lo stesso rumore 1-qubit di uno profondo 1; (b) col rumore dopo tutti i gate, un errore a metà circuito non si propagava attraverso i gate successivi.

**Perché succede:**
La prima implementazione (29/06) applicava il rumore in blocco alla fine perché sufficiente per i circuiti piccoli iniziali. Braket applica il rumore nella posizione in cui compare nello stream di istruzioni — quindi appenderlo alla fine lo scollega dalla profondità del circuito.

**Decisione presa:**
Riscritta l'applicazione del rumore in `ionq.py` usando `Circuit.apply_gate_noise(...)`, il metodo idiomatico di Braket che inserisce il canale **subito dopo ogni gate** del tipo indicato, nella posizione giusta dello stream:
- `Depolarizing(0.0003)` su ogni gate a 1 qubit (H, X, Y, Z, S, Si, T, Ti, Rx, Ry, Rz) — ora una volta *per gate*, non per qubit;
- `TwoQubitDepolarizing(0.003)` su ogni gate entangling (CNot, CZ, Swap) — ora interlacciato tra i gate, così l'errore si propaga;
- `bit_flip(0.005)` di readout resta alla fine (è genuinamente un errore di misura).
Guardie `has_1q`/`has_2q` per non chiamare `apply_gate_noise` su tipi di gate assenti. `ccx` resta non modellato (nessun equivalente 2-qubit diretto su 3 qubit, come 22/07). Gate generici a singolo qubit che diventano `Unitary` (u/u1/u2/u3 via fallback braket_utils) non sono coperti dalla lista nominata — gap minore dichiarato, nessun circuito built-in lo attiva. Tassi di errore invariati (0.03% / 0.3% / 0.5%): è cambiata la *posizione* del rumore, non la sua intensità.

**Verifiche (con vero SDK Braket):**
1. Dump istruzioni: DEPO(0.0003) dopo ogni gate 1q, TwoQubitDepolarizing dopo ogni CNot tra i gate, BitFlip alla fine — interlacciamento confermato.
2. Scala con la profondità: `H + Z^n + H` (ideale |0⟩) dà fidelity `0.9996 / 0.9977 / 0.9903 / 0.9591` per n = `0 / 10 / 50 / 200` — il rumore cresce con la profondità, mentre col vecchio modello sarebbe stato costante.
3. GHZ via adapter reale: dominante 000/111, fidelity 0.9822.

**Conseguenza sui dati — IonQ da rimisurare:**
Tutte le misure IonQ storiche (Bell/GHZ/VQE in README/Guida/log) usano il vecchio modello e vanno rimisurate — stesso trattamento del fix IonQ del 19/07. In particolare per GHZ il nuovo modello applica il depolarizing 1q solo dove c'è un gate a singolo qubit (solo H su q0), non su q1/q2 che prima ricevevano rumore 1q spurio pur non avendo gate a singolo qubit — quindi la fidelity IonQ tende a salire leggermente rispetto ai dati pre-fix. Non tocca IBM (Aer/QPU non passano da questa funzione) né AWS (simulatore ideale senza rumore).

**Rilevanza per il report — MEDIA-ALTA:**
Chiude l'ultimo punto di sostanza della review. Rilevante ora che il tool pubblicizza circuiti QASM arbitrari (profondità variabile): il noise model IonQ è ora fisicamente sensato sulla profondità, non solo sul conteggio dei gate entangling. Collegamento diretto alla domanda aperta più volte nel log (29/06, 20/07: "perché IonQ resta ottimista?") — parte della risposta era anche questa, il rumore non scalava con la profondità. Da rieseguire il benchmark IonQ e aggiornare i numeri prima dell'articolo.

---

## 23/07/2026 — Repliche di riferimento dei simulatori fissate a n=100

**Cosa abbiamo osservato:**
La tabella-confronto fidelity/energia (Bell/GHZ/VQE × backend) usa come riferimento la media su repliche dei backend simulati (noisy Aer, IonQ). I simulatori girano in locale a costo zero, quindi lo standard per queste medie di riferimento è **n=100 repliche a 1024 shot**. Il QPU reale resta a n=5: ogni replica costa tempo di coda + quota IBM, quindi lì il campione è deliberatamente contenuto.

Dati n=100 (1024 shot), fidelity:

| Circuito | noisy (n=100) | IonQ (n=100) |
|---|---|---|
| Bell | 95.53% ± 0.67% | 98.86% ± 0.31% |
| GHZ  | 93.00% ± 0.86% | 98.15% ± 0.49% |
| VQE  | 95.11% ± 0.71% | 98.67% ± 0.37% |

Energia VQE (Z+X, 1024 shot, n=100): noisy -1.0877 ± 0.011 Ha (bias ~50 mHa); IonQ -1.1236 ± 0.008 Ha (bias ~14 mHa).

**Perché è rilevante — nota statistica da non dimenticare:**
Le medie coincidono coi valori a campione più piccolo (differenze < rumore). **Il "± std" riportato è la dispersione tra run singoli** (una proprietà del rumore a 1024 shot) e **non si stringe aumentando le repliche** — a stringersi è l'*errore sulla media* (std/√n, cioè quanto è fissata la media): da ~0.27% a ~0.086% passando da n=10 a n=100. Quindi n=100 non serve a barre d'errore più strette (quelle restano ~uguali), ma a una **media di riferimento solida**. Attenzione a non descriverlo come "barre più strette" nell'articolo.

**Decisione presa:**
Nessuna modifica al codice del tool. Dati n=100 generati con lo stesso codice e gli stessi noise model del repo (riproducibili). Aggiornate le tabelle di articolo, README e Guida. Gli **studi di convergenza** (shots-efficiency e energia-vs-shot) restano a **n=10 per punto**: sono sweep di tendenza su molti valori di shot, non confronti a condizione singola, e n=10/punto è lo standard per quel tipo di grafico.

**Rilevanza per il report — MEDIA:**
Rende la metà simulata delle tabelle statisticamente robusta senza costo di quota; il QPU reale a n=5 va presentato come scelta motivata (hardware razionato), non come statistica insufficiente — è già così nella sezione Limitazioni dell'articolo.

---
