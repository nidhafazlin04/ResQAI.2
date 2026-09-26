# ResQAI — Installable Emergency Web App

ResQAI is an AI-powered emergency message triage and rescue alert prototype.

## Features

- Text emergency reporting
- Browser microphone recording
- Whisper speech-to-text
- Groq-based emergency triage
- CRITICAL / HIGH / MEDIUM / LOW priority
- Emergency type classification
- Location capture
- Incident grouping using text similarity + distance
- Responder voice alert generation
- Alert history
- Twilio SMS integration when configured
- PWA installation on supported browsers
- Offline UI caching

## Important architecture note

The PWA frontend does not contain the Groq or Twilio secrets. They stay on the backend.

The in-memory `alerts` list is suitable for a demo. For a real deployment, use a database such as PostgreSQL.

## Local setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Create `.env` from `.env.example` and set the variables.

For local testing, export the variables in your shell or use a dotenv package if desired.

Run:

```bash
python app.py
```

Open:

http://127.0.0.1:5000

## Production

Use:

```bash
gunicorn app:app
```

Set all secrets as deployment-provider environment variables.

## Safety

ResQAI is intended to assist human rescue teams. It does not replace emergency services or professional responders. For actual emergencies, users should also contact the appropriate local emergency service.
