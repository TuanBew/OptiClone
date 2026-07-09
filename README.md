# OptiClone

A daily job that pulls OptiSigns support articles from the Zendesk Help Center
API, normalizes them to clean Markdown, and detects the delta (added / updated /
skipped) against the previous run. Vector-store upload is **stubbed** in this
build — see "Status" below.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # .venv/bin/pip on Linux/Mac
cp .env.sample .env
```

## Run locally

```bash
.venv/Scripts/python main.py
```

Reads `ARTICLE_LIMIT` from `.env` (defaults to 50 published articles). Writes
`articles/<slug>.md`, `state/manifest.json`, and `state/last_delta.json`, then
logs `added=N updated=N skipped=N`.

## Run tests

```bash
.venv/Scripts/pytest -v
```

All tests mock the Zendesk API via the `responses` library — no live network
required.

## Delta strategy

Each article's Markdown body is hashed (SHA-256) and compared against
`state/manifest.json` from the previous run:
- **added** — article id not seen before
- **updated** — hash differs from the recorded one
- **skipped** — hash identical (Zendesk's `updated_at`/`edited_at` can drift
  without meaningful content change, so the hash — not the timestamp — is the
  authoritative signal)

Only added/updated articles are handed to the `Uploader` interface
(`uploader/base.py`). This build ships a `StubUploader` that logs what it would
embed and writes `state/last_delta.json`. A later build drops in a real
`OpenAIVectorStoreUploader` behind the same interface with no changes to the
scraper, delta logic, or `main.py`.

## Deployment & logs

Runs daily via cron on a DigitalOcean Droplet — see [`docs/deployment.md`](docs/deployment.md)
for setup and how to view job logs / the last-run artifact
(`state/last_delta.json`).

## Docker

```bash
docker build -t opticlone .
docker run --rm --env-file .env -v $(pwd)/state:/app/state -v $(pwd)/logs:/app/logs opticlone
```

Exits 0 with or without `OPENAI_API_KEY` set.

## Status

Vector-store upload (OpenAI Files/Vector Stores API, chunking, embeddings) is
**not implemented yet** — that's a follow-up build. This build stops at the
pluggable `Uploader` interface + `StubUploader`, and the committed `articles/`
snapshot demonstrates scrape/clean quality in the meantime.
