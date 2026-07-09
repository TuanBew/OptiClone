# OptiClone

A daily job that pulls OptiSigns support articles from the Zendesk Help Center
API, normalizes them to clean Markdown, detects the delta (added / updated /
skipped) against the previous run, and uploads the delta into an OpenAI
Vector Store attached to the "Opticlone" assistant — see "Status" below.

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
(`uploader/base.py`). With `OPENAI_API_KEY` unset, `main.py` uses a
`StubUploader` that logs what it would embed and writes
`state/last_delta.json` — useful for a dry run with no OpenAI credentials.
With `OPENAI_API_KEY` set (and `OPENAI_ASSISTANT_ID`), `main.py` uses
`OpenAIVectorStoreUploader` (`uploader/openai_store.py`), which:

- Creates an OpenAI Vector Store on first run (or reuses
  `OPENAI_VECTOR_STORE_ID` if already set) and attaches it to the assistant
  via `tool_resources.file_search.vector_store_ids`.
- Uploads each added/updated article's Markdown file, using OpenAI's default
  "auto" chunking (~800 tokens per chunk, ~400 token overlap) — this build
  never passes a custom `chunking_strategy`, since the default suits
  OptiSigns' prose-with-headings articles without tuning.
- On an **update**, deletes the previously-uploaded file from both the
  vector store and the Files API before uploading the new content, so no
  stale embeddings linger.
- Persists the resulting OpenAI file id into `state/manifest.json`'s
  `file_id` field per article, so the next run's update can delete-then-replace it.
- Logs `files embedded=N chunks embedded=M` at the end of every run (`M` is a
  real count from OpenAI's vector-store-file content endpoint, not an
  estimate).
- Never aborts the run over one article's upload failure — a failed article
  keeps its old manifest hash and is retried automatically on the next run.

## Deployment & logs

Runs daily as a [Fly.io scheduled Machine](https://fly.io/docs/machines/flyctl/fly-machine-run/)
(billed only while the job is actually running, not for an idle VM) — see
[`docs/deployment.md`](docs/deployment.md) for setup and how to view job logs /
the last-run artifact (`state/last_delta.json`).

## Docker

```bash
docker build -t opticlone .
docker run --rm --env-file .env -v $(pwd)/state:/app/state -v $(pwd)/logs:/app/logs opticlone
```

Exits 0 with or without `OPENAI_API_KEY` set. When set, also requires
`OPENAI_ASSISTANT_ID` in the same `.env`/`--env-file`.

## Status

Vector-store upload is implemented (`uploader/openai_store.py`) and covered
by an offline, mocked-client test suite (`tests/test_openai_uploader.py`) —
no test ever calls the real OpenAI API. The committed `articles/` snapshot
demonstrates scrape/clean quality independent of the uploader.

Sanity-check screenshot (Playground, asking the Opticlone assistant "How do
I add a YouTube video?", showing cited `Article URL:` lines):

`[screenshot placeholder — to be added after the first live run]`
