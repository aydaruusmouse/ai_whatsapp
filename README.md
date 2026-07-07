# Telesom AI Chatbot

Web app: upload documents or paste a URL, then chat. Answers use only that knowledge. **Somali-first** replies; English when the user writes in English.

**Note:** The Cursor/IDE assistant model cannot be plugged into this app. For a free local stopgap, use [Ollama](https://ollama.com) and set `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` plus `OPENAI_MODEL` (e.g. `llama3.2`).

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit backend/.env — API keys (OpenRouter/OpenAI) + MariaDB (DB_*)
# For UI-only testing without OpenAI: MOCK_LLM=true
```

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

## Notes

- Uploaded files and ingested URLs are stored in **MariaDB/MySQL** (see `DB_*` in `backend/.env`) and survive server restarts. Use **Nadiifi xogta** to clear knowledge for your session only.

### Database (MariaDB / MySQL)

On your server, create a database and user, then set in `backend/.env`:

```sql
CREATE DATABASE telesom_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'telesom'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON telesom_ai.* TO 'telesom'@'localhost';
FLUSH PRIVILEGES;
```

Tables (`sessions`, `chunks`, `session_meta`) are created automatically on first startup.

## Telesom WhatsApp APIs (VAS)

The bot calls live APIs at `https://whatsapp.telesom.com` for:

- VAS subscribe / unsubscribe (always shows offer list first, then check-subscription)
- Exchange rate
- Block wrong transaction
- New fiber installation

Customer phone (`msisdn` / `callsub`) is taken from WhatsApp in production; on the **web UI** enter it in the sidebar **Lambarka (WhatsApp)** field (saved in browser). The bot never asks for the phone number during API flows.
- Supported files: PDF, TXT, MD, CSV, DOC, DOCX. URLs fetch HTML or PDF `Content-Type`.
