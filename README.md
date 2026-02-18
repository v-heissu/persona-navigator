# Persona Navigator

App web per analizzare siti attraverso personas predefinite o personalizzate. Le personas navigano in modo guidato, commentano in tempo reale e rispondono a domande. Ideale per generare ipotesi qualitative durante workshop con clienti o audit UX.

## Come Funziona

1. **Scegli una persona** - Utente tipo (foodie), esperto UX/CRO, o crea la tua
2. **Inserisci l'URL** - Il sito da analizzare
3. **Naviga e interagisci** - Clicca, scrolla, chiedi opinioni
4. **Genera insights** - Report strutturato con raccomandazioni

## Funzionalita'

### Personas

- **Marco - Casual Foodie**: 28-45 anni, cerca convivialita' e occasioni speciali
- **Giulia - Active Foodie**: 35-50 anni, early adopter, cerca esperienze uniche
- **Roberto - Super Foodie**: 40-65 anni, fine dining settimanale, network gastronomico
- **Alex - UX/CRO Specialist**: Esperto UX e ottimizzazione conversioni, analizza usabilita' e friction points

### Crea la Tua Persona

Puoi creare personas temporanee per la sessione:
- Scegli un'icona tra 15 emoji disponibili
- Inserisci nome, descrizione breve e profilo completo
- La persona viene aggiunta al dropdown e selezionata automaticamente

### Interazione con il Sito

- **Click per navigare** - Clicca su link, bottoni e menu come faresti normalmente
- **Analizza** - La persona analizza quello che vede nella schermata corrente
- **Evidenzia area** - Seleziona un'area specifica e chiedi un parere
- **Scrolla tutto** - La persona scrolla l'intera pagina e da' una valutazione completa
- **Chat** - Fai domande, chiedi opinioni o dai comandi di navigazione

### Contesto Automatico

- Clicca "Auto" accanto al campo contesto per generare automaticamente una descrizione del sito usando AI
- Il contesto aiuta la persona a capire cosa sta navigando

### Analisi Insights

Al termine della sessione:
- Genera un report strutturato con raccomandazioni
- Copia il report con un click per incollarlo altrove
- Esporta la sessione completa in Markdown

## Stack Tecnico

- **Backend**: Python 3.11+, FastAPI
- **Frontend**: HTML/CSS/JavaScript vanilla
- **Browser**: Playwright con Chromium headless
- **AI**: Google Gemini API (Vision + Text)
- **Deploy**: Railway con Docker

## Struttura Progetto

```
persona-navigator/
├── app.py                 # FastAPI backend con WebSocket
├── ai_client.py           # Gemini API wrapper (vision + chat)
├── personas.py            # Definizioni personas + prompt templates
├── browser_manager.py     # Playwright wrapper (screenshot, navigazione)
├── static/
│   └── index.html         # Frontend single-page app
├── requirements.txt
├── Dockerfile
├── railway.toml
└── README.md
```

## Installazione Locale

### 1. Clona il repository

```bash
git clone <repo-url>
cd persona-navigator
```

### 2. Crea un virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oppure
venv\Scripts\activate  # Windows
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

### 4. Configura la variabile d'ambiente

```bash
export GEMINI_API_KEY=your_api_key_here
```

Oppure crea un file `.env`:
```
GEMINI_API_KEY=your_api_key_here
```

### 5. Avvia l'applicazione

```bash
python app.py
```

L'app sara' disponibile su `http://localhost:8000`

## Deploy su Railway

1. Crea un nuovo progetto su Railway
2. Connetti il repository GitHub
3. Aggiungi la variabile d'ambiente `GEMINI_API_KEY`
4. Deploy automatico tramite Dockerfile

## Utilizzo Passo-Passo

### Setup Iniziale

1. **Seleziona persona**: Scegli dal dropdown o crea una nuova
2. **Inserisci URL**: L'indirizzo completo del sito (es. `https://example.com`)
3. **Contesto (opzionale)**: Descrivi il sito o usa "Auto" per generarlo con AI
4. **Avvia**: Click su "Avvia Ispezione"

### Durante la Sessione

- **Navigare**: Clicca direttamente sulla preview del sito
- **Analisi rapida**: Bottone "Analizza" per reazione alla persona alla pagina corrente
- **Area specifica**: Bottone "Evidenzia" per selezionare e chiedere parere su un'area
- **Full page**: Bottone "Scrolla tutto" per analisi completa della pagina
- **Domande libere**: Scrivi nella chat per interagire con la persona

### Generare Insights

1. Naviga alcune pagine del sito
2. Click su "Genera Insights" nella sidebar
3. Attendi l'analisi (puo' richiedere qualche secondo)
4. Il report include:
   - Reazioni chiave
   - Cosa ha funzionato
   - Cosa non ha funzionato
   - Bisogni non soddisfatti
   - Raccomandazioni prioritizzate
5. Usa "Copia" per copiare il report negli appunti

### Esportare la Sessione

Click su "Esporta MD" per scaricare l'intera conversazione in formato Markdown.

## Variabili d'Ambiente

| Variabile | Descrizione | Obbligatoria |
|-----------|-------------|--------------|
| `GEMINI_API_KEY` | API key per Google Gemini | Si |
| `PORT` | Porta del server (default: 8000) | No |

## Limitazioni

- Non supporta siti con login required
- Una sola persona alla volta per sessione
- Personas create sono temporanee (non persistono tra sessioni)
- Nessuna autenticazione utenti

## Tips per Risultati Migliori

- **Contesto preciso**: Un buon contesto aiuta la persona a capire cosa sta guardando
- **Naviga diverse pagine**: Piu' pagine esplori, migliori saranno gli insights
- **Fai domande specifiche**: "Prenoteresti qui?" e' meglio di "Cosa ne pensi?"
- **Usa la persona giusta**: Alex UX per audit tecnici, personas foodie per prospettiva utente
