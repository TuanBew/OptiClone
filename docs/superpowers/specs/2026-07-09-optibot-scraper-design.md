# OptiBot Mini-Clone: Zendesk Scraper → Markdown → Daily Delta Job

Design spec for Take-Home Task 1 (scrape → Markdown) + Task 3 (daily delta job on
DigitalOcean). Task 2 (OpenAI Vector Store upload) is explicitly out of scope for
this build — represented only by a pluggable `Uploader` interface + `StubUploader`.

## Source of Truth

- `OptiSigns_Take-Home_Test_Updated.docx` — the assignment, grading rubric, deliverables.
- `CLAUDE_CODE_EXECUTION_PROMPT.md` — locked architecture and constraints for this build.

Grading weights confirmed from the assignment doc: Scrape & clean quality (25 pts),
API-based vector-store upload (20 pts, deferred to Task 2), Daily job deployment &
logs (15 pts), Code clarity + README (10 pts), bonus tests (+5 pts).

## Decisions Made During Brainstorming

1. **State persistence**: A DigitalOcean Droplet (not App Platform) runs the
   container via cron, bind-mounting a host directory into `/app/state` and
   `/app/logs`. Docker's per-run ephemeral filesystem is fine for everything except
   `state/manifest.json` and `state/last_delta.json`, which must survive across
   daily invocations — the bind mount solves this with zero extra cloud services or
   dependencies (no S3/Spaces client, no git-push-from-container hack).
2. **Article scope**: `ARTICLE_LIMIT` defaults to **50** (comfortably clears the
   ≥30 bar, keeps daily runs and the committed snapshot small). Documented in
   `.env.sample`; can be raised or unset for a full ~406-article pull.
3. **Markdown output**: A snapshot of scraped `articles/*.md` is committed to the
   repo (evidence of scrape quality for the 25-pt rubric line) in addition to being
   regenerated fresh at runtime inside the container on every daily run.

## Architecture & Repo Layout

```
OptiClone/
  main.py                    # orchestrates scrape → normalize → diff → upload → log
  scraper/
    zendesk.py                 # paginated Zendesk Help Center API client
    markdown.py                 # HTML → clean Markdown, strips nav/ads, injects front-matter + "Article URL:" line
  delta/
    manifest.py                  # load/save manifest.json, content hashing, added/updated/skipped classification
  uploader/
    base.py                      # Uploader ABC: upload(files: list[ArticleFile]) -> None
    stub.py                       # StubUploader: logs + writes state/last_delta.json
  articles/                    # committed snapshot of scraped Markdown
  state/                        # gitignored — runtime manifest/delta, lives on droplet's bind-mounted volume
  logs/                         # gitignored — droplet-only, daily cron output
  tests/
    fixtures/                    # recorded Zendesk API JSON pages for offline mocking
    test_zendesk.py, test_markdown.py, test_manifest.py, test_main_e2e.py
  Dockerfile
  requirements.txt / requirements-dev.txt
  .env.sample / .gitignore
  README.md
```

## Data Flow

1. **`scraper/zendesk.py`** — pages through
   `GET https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100&page=N`,
   following `next_page` until null or `ARTICLE_LIMIT` is reached. Filters out
   `draft: true` articles.
2. **`scraper/markdown.py`** — converts each article's `body` HTML to Markdown via
   `markdownify` (BeautifulSoup-based; handles messy Zendesk HTML more reliably
   than `html2text`), stripping nav/ad wrapper elements before conversion and
   preserving headings, code blocks, and relative links. Writes `articles/<slug>.md`
   with front-matter and a literal `Article URL:` line:

   ```
   ---
   title: ...
   article_id: ...
   updated_at: ...
   ---
   Article URL: https://support.optisigns.com/hc/en-us/articles/...

   <converted body>
   ```

   The literal `Article URL:` line matters: Task 2's assistant system prompt
   ("Cite up to 3 'Article URL:' lines per reply") greps for it to build citations.
3. **`delta/manifest.py`** — loads `state/manifest.json` (`{}` if missing), computes
   a SHA-256 hash of each newly generated Markdown file, and classifies each
   article as:
   - **added** — article_id not present in the manifest
   - **updated** — hash differs from the manifest's recorded hash
   - **skipped** — hash identical

   Only added+updated articles are handed to the uploader. Manifest entries are
   `article_id → {slug, content_hash, updated_at, file_id: null}` — `file_id` is
   reserved (always `null` in this build) so Task 2's uploader can populate it
   without a schema migration. Manifest writes are atomic (write to a temp file,
   then `os.replace`) so a mid-run crash can't corrupt state.
4. **`uploader/base.py` + `uploader/stub.py`** — `Uploader` is a small ABC:
   `upload(self, files: list[ArticleFile]) -> None`. `StubUploader.upload(files)`
   logs each file it "would" embed and writes `state/last_delta.json` (added slugs,
   updated slugs, skipped count, timestamp). Task 2 drops in
   `OpenAIVectorStoreUploader` behind the same interface — scraper, delta, and
   `main.py` do not change.
5. **`main.py`** — orchestrates
   `scrape() → normalize() → diff(manifest) → uploader.upload(delta) → write_manifest() → log_counts()`.
   Logs `added=N updated=N skipped=N` at the end of every run. Exits 0 on success,
   including when individual articles fail to normalize (logged as a warning,
   skipped, run continues — one bad article must not kill the whole job). Exits 1
   only if the entire scrape yields zero articles (e.g., Zendesk API unreachable),
   since a green exit code on a silently-empty run would defeat the purpose of the
   daily job.

## Testing

All tests run offline against mocked Zendesk HTTP calls via the `responses`
library — no live network access required:

- `test_zendesk.py` — pagination stops at `next_page: null`; draft articles are
  filtered out; `ARTICLE_LIMIT` cap is respected.
- `test_markdown.py` — headings/code blocks/relative links are preserved; nav/ads
  are stripped; front-matter and the `Article URL:` line are present.
- `test_manifest.py` — added/updated/skipped classification is correct; hashes are
  stable across runs with unchanged content; atomic write survives a simulated
  crash mid-write.
- `test_main_e2e.py` — a full dry run against mocked Zendesk + `StubUploader`
  asserts `state/last_delta.json` is written correctly, and that a second run with
  unchanged content logs **all-skipped**.

## DevOps

- **Dockerfile**: `python:3.11-slim` base, installs `requirements.txt`,
  `ENTRYPOINT ["python", "main.py"]`. Must build and run successfully with or
  without `OPENAI_API_KEY` set (the stub uploader needs no key).
- **Deployment**: a small DigitalOcean Droplet (Docker pre-installed via a
  marketplace image) clones the repo and builds the image once. A daily cron entry
  runs:
  ```
  0 6 * * * cd /root/OptiClone && docker run --rm --env-file .env \
    -v $(pwd)/state:/app/state -v $(pwd)/logs:/app/logs opticlone \
    >> logs/cron-$(date +\%F).log 2>&1
  ```
- **README** (≤ 1 page) documents: setup, how to run locally, the delta strategy,
  the SSH + `tail` command reviewers use as the "job logs" link (this is a private
  droplet, not a public dashboard), the committed `articles/` snapshot as evidence
  of scrape quality, and an explicit note that vector-store upload is stubbed
  pending Task 2.

## Out of Scope (confirmed)

- OpenAI Files/Vector Stores API, embeddings, chunking, the `openai` SDK — Task 2.
- Any frontend, chat UI, web server, REST API, or database.
- Creating the Assistant or its system prompt via code (manual Playground step).
- The sanity-check screenshot — part of Task 2 after the real upload works.
- Renaming the repo or naming anything `optisigns*`.
