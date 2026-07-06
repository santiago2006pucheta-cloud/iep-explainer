# IEP Explainer

Paste or upload your child's IEP and get a plain-language explanation, possible gaps, and questions to bring to the meeting.

## Why I built this

An IEP (Individualized Education Program) is one of the most important documents in a kid's education, but it's written in dense special-education jargon — present levels, measurable annual goals, related services, FAPE, LRE — that leaves a lot of parents nodding along in the meeting without really understanding what they just agreed to. I wanted a tool that takes that document and turns it into plain language, flags the spots that look thin or vague, and hands the parent a short list of good questions so they walk into the next meeting informed instead of just hoping for the best.

## What it does

You paste the text of your child's IEP, or upload the document as a PDF or `.txt` file, and IEP Explainer returns three things: a plain-language summary of what the document actually says, a list of possible gaps or weak spots worth looking into, and a set of specific questions to bring to your next IEP meeting. It reads directly from whatever text you provide — pasted or extracted from the uploaded file — and works from that alone.

## Tech stack

- **Python** + **Flask** backend
- **OpenAI API** (model `gpt-4o`) via the official `openai` Python SDK
- **pypdf** for server-side PDF text extraction
- Vanilla **HTML/CSS/JS** frontend with a small, self-contained markdown-to-HTML renderer
- No frontend frameworks, no external CDNs — everything ships local

## How it works

The browser sends either an uploaded file or pasted text to Flask's `/api/explain` endpoint. Flask extracts the IEP text server-side (parsing PDFs with `pypdf` when a file is uploaded) and calls the OpenAI API with that text — the API key never touches the browser. The model's response, structured as three markdown sections, comes back as JSON and is split and rendered into three distinct cards entirely client-side.

## Run it locally

1. Clone the repo and `cd` into `iep-explainer/`
2. Create and activate a virtual environment:
   ```
   python -m venv venv && source venv/bin/activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Copy the env template and add your key:
   ```
   cp .env.example .env
   ```
   Then open `.env` and set `OPENAI_API_KEY` to your own key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
5. Run the app:
   ```
   python app.py
   ```
6. Open **http://localhost:5000**

## Privacy

IEPs contain sensitive information about a child. The text you paste or upload is sent to OpenAI's API solely to generate the explanation, and this app does not store it. Consider removing your child's name (and other identifying details) before submitting.

## Note

This is a preparation aid to help you understand your IEP — not legal or educational advice.
