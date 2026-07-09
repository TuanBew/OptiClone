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

## Verifying the real uploader (do this before scaling up)

The uploader is fully covered by offline tests, but has intentionally never
been run against the real OpenAI API as part of this build — only you, with
your own API key and budget, should decide when that happens. Recommended
order, since OpenAI usage is billed:

1. Confirm `.venv/Scripts/pytest -v` is fully green first.
2. **Back up and clear local state first.** This repo's `state/` directory is
   gitignored but persists across runs on your machine, and if you've scraped
   articles locally before, `state/manifest.json` already tracks them. Running
   the tiny-scope test below without clearing it will likely fetch an article
   that's already recorded with an unchanged hash, get classified `skipped`,
   and never reach the uploader at all — a silent no-op on your one live
   attempt. Move the existing state aside first:
   ```bash
   mv state state_backup   # restore later with: mv state_backup state
   ```
3. Run locally with a tiny scope to exercise the real path end-to-end at
   near-zero cost:
   ```bash
   # In .env: set OPENAI_API_KEY and OPENAI_ASSISTANT_ID, leave
   # OPENAI_VECTOR_STORE_ID empty, and set ARTICLE_LIMIT=1
   .venv/Scripts/python main.py
   ```
   Check the log line `Created new OpenAI Vector Store id=...` and
   `files embedded=1 chunks embedded=N`, then copy the printed vector store
   id into `.env` as `OPENAI_VECTOR_STORE_ID` so the next run reuses it
   instead of creating another one.
4. Run again locally with the same small `ARTICLE_LIMIT` to confirm a
   no-change second run uploads nothing. With an empty delta,
   `OpenAIVectorStoreUploader.upload()` returns immediately without logging
   a `files embedded=...` line at all — the signal to look for instead is
   `main.py`'s own summary line: `Delta complete: added=0 updated=0 skipped=1`.
5. Only after both of those succeed, restore your original `state/`
   (`mv state_backup state`) or start fresh, then raise `ARTICLE_LIMIT` back
   to 50 (or unset it) for a full local run, and follow `docs/deployment.md`
   to set the three OpenAI values as Fly secrets and redeploy the scheduled
   Machine.

Treat any failure in steps 3-4 as a stopping point to fix and re-test
offline first (adding a case to `tests/test_openai_uploader.py` if it
reveals a gap in the mocked coverage) rather than immediately retrying
against the live API.

## Status

Vector-store upload is implemented (`uploader/openai_store.py`) and covered
by an offline, mocked-client test suite (`tests/test_openai_uploader.py`) —
no test ever calls the real OpenAI API. The committed `articles/` snapshot
demonstrates scrape/clean quality independent of the uploader.

Sanity-check screenshot (Playground, asking the Opticlone assistant "How do
I add a YouTube video?", showing cited `Article URL:` lines):

`[screenshot placeholder — to be added after the first live run]`
