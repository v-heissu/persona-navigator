# Personas Navigator

App web per workshop che simula la navigazione di un sito attraverso personas predefinite. Le personas navigano autonomamente o in modo guidato, commentano in tempo reale e rispondono a domande. Ideale per generare ipotesi qualitative durante workshop con clienti.

## Funzionalita'

- **3 Personas predefinite**: Marco (Casual Foodie), Giulia (Active Foodie), Roberto (Super Foodie)
- **Modalita' Guidata**: L'operatore controlla la navigazione e pone domande
- **Modalita' Autonoma**: La persona decide autonomamente dove navigare
- **Rilevamento automatico**: Identifica il tipo di pagina (homepage, menu, booking, etc.)
- **Suggerimenti contestuali**: Domande suggerite in base al tipo di pagina
- **Gestione cookie banner**: Chiusura automatica best-effort
- **Export Markdown**: Esporta la sessione per analisi successiva

## Stack Tecnico

- Python 3.11+
- Streamlit (UI)
- Playwright (browser automation con Chromium)
- Anthropic API (Claude Sonnet con vision)
- Deploy su Railway

## Struttura Progetto

```
personas-navigator/
├── app.py                 # Main Streamlit app
├── personas.py            # Definizioni personas + prompt templates
├── suggestions.py         # Suggerimenti contestuali per tipo pagina
├── browser.py             # Playwright wrapper (screenshot, navigazione)
├── claude_client.py       # Anthropic API wrapper (vision + chat)
├── navigator.py           # Logica navigazione autonoma
├── page_detector.py       # Rilevamento tipo pagina
├── exporter.py            # Export sessione markdown
├── requirements.txt
├── Dockerfile
└── README.md
```

## Installazione Locale

1. Clona il repository:
```bash
git clone <repo-url>
cd personas-navigator
```

2. Crea un virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oppure
venv\Scripts\activate  # Windows
```

3. Installa le dipendenze:
```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

4. Configura la variabile d'ambiente:
```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

5. Avvia l'applicazione:
```bash
streamlit run app.py
```

## Deploy su Railway

1. Crea un nuovo progetto su Railway
2. Connetti il repository GitHub
3. Aggiungi la variabile d'ambiente `ANTHROPIC_API_KEY`
4. Deploy automatico tramite Dockerfile

## Utilizzo

### Setup Sessione
1. Seleziona una persona dal dropdown
2. Inserisci l'URL del sito da analizzare
3. Scegli la modalita': Guidata o Autonoma
4. Se Autonoma: seleziona obiettivo e numero max di pagine
5. Click su "Avvia navigazione"

### Modalita' Guidata
- L'operatore scrive comandi di navigazione ("vai al menu", "scorri", "torna indietro")
- L'operatore pone domande alla persona ("prenoteresti?", "cosa ti manca?")
- La persona risponde sempre in character
- Usa i suggerimenti contestuali per domande rapide

### Modalita' Autonoma
- La persona naviga autonomamente verso l'obiettivo selezionato
- Pausa 3 secondi tra ogni azione per leggibilita'
- Controlli disponibili:
  - **Pausa**: Ferma per fare domande
  - **Salta attesa**: Accelera la navigazione
  - **Stop -> Q&A**: Termina navigazione e passa a domande libere

### Export
- Click su "Esporta MD" per scaricare la sessione in Markdown
- Click su "Nuova sessione" per ricominciare

## Personas

### Marco - Casual Foodie
- 28-45 anni, expertise intermedia
- Cerca occasioni speciali, convivialita', prezzi accessibili
- Tono: diretto, alla mano, colloquiale

### Giulia - Active Foodie
- 35-50 anni, expertise avanzata
- Early adopter, cerca chef emergenti e esperienze uniche
- Tono: competente, fa confronti, nota dettagli

### Roberto - Super Foodie
- 40-65 anni, expertise elevata
- Fine dining settimanale, network gastronomico
- Tono: riflessivo, riferimenti colti, puo' essere tagliente

## Variabili d'Ambiente

| Variabile | Descrizione | Obbligatoria |
|-----------|-------------|--------------|
| `ANTHROPIC_API_KEY` | API key per Claude | Si |

## Limitazioni

- Non supporta siti con login required
- Una sola persona alla volta
- Nessuna persistenza sessioni su database
- Nessuna autenticazione utenti

## Estensioni Future (v2)

- Confronto side-by-side tra personas
- Personas custom uploadabili
- Template per altri settori (hotel, ecommerce, SaaS)
- Riepilogo automatico insight
- Integrazione Notion/Google Docs
- Recording sessione per replay
