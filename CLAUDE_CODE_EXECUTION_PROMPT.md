/superpowers — OptiBot Mini-Clone: Zendesk Scraper → Markdown, deployed as a daily delta job

> **How to use this file:** Paste everything below the line into Claude Code at the root of the repo. It is a single, self-contained build covering Take-Home **Task 1 (scrape → Markdown)** + **Task 3 (daily delta job on DigitalOcean)**. **Task 2 (OpenAI Vector Store upload) is explicitly deferred to a later build** — so the upload step here is a *pluggable stub* that Task 2 will fill in without touching the scraper or delta engine. The superpowers workflow handles internal task breakdown, so there are no external "phase N of M" prompts.

---

## 0. Context Gathering — READ BEFORE DOING ANYTHING

MANDATORY: Before writing any code, recover all locked decisions.

* Read `OptiSigns_Take-Home_Test_Updated.docx` in the repo root — the full assignment, grading rubric, and deliverables. This is the source of truth for scope.
* Read this entire prompt file. Everything here supersedes assumptions.
* Inspect the existing repo state (`git log`, `ls -R`, any existing `README`, `.env.sample`) so you build on what's there rather than duplicating it.
* Use `conversation_search` for `"OptiBot"`, `"Zendesk scraper"`, `"OptiClone"` to recover any prior design decisions.

Do NOT design anything until you have read the assignment doc and confirmed the Zendesk API shape (Section 3).

## 1. Mission — Read Carefully, This Task Is Unique

Build a Python data pipeline that clones the ingestion layer of OptiSigns' support bot ("OptiBot"). End to end it must: pull OptiSigns support articles from the Zendesk Help Center API, normalize each to clean Markdown, and run once per day as a Dockerized job on DigitalOcean that detects **only the delta** (new/changed articles) and logs added/updated/skipped counts. The actual push of that delta into a vector store is handed to a pluggable **uploader interface** whose concrete OpenAI implementation is deferred to Task 2 — for now a stub records exactly what the delta upload *would* send.

This is a **single, self-contained build** for Task 1 + Task 3 — no prior phase to depend on. Task 2 is a defined follow-up that will drop a real uploader into the interface you define here.

Specific scope of this task:
- ✅ DO: **Scraper (Task 1)** — pull ≥ 30 articles from `support.optisigns.com` via the Zendesk Help Center API; convert each article body (HTML) to clean Markdown; save as `<slug>.md`; preserve headings, code blocks, and relative links; strip nav/ads/boilerplate.
- ✅ DO: **Delta job (Task 3)** — a `main.py` entrypoint wrapping scraper + uploader interface; detect new/updated articles via content hash and/or `updated_at`/`edited_at`; determine the delta; log counts of **added / updated / skipped**.
- ✅ DO: **Pluggable uploader interface + stub** — define a small `Uploader.upload(files)` interface and a `StubUploader` that logs each file it would embed and writes the delta set to a run artifact (e.g. `state/last_delta.json`). This is the seam Task 2 plugs the real OpenAI Vector Store client into. Design it so swapping in the real uploader touches **only** this module.
- ✅ DO: **DevOps (Task 3)** — `Dockerfile` such that `docker run <image>` runs the job once and exits 0 (accepting `-e` vars per the contract); deploy on **DigitalOcean** scheduled to run once per day; provide a link to the job logs / last-run artifact; write a ≤ 1-page `README`; provide `.env.sample`.
- ❌ DO NOT: implement the OpenAI Files / Vector Stores API, chunking, or embedding logic. That is **Task 2**. Stop at the `Uploader` interface + stub.
- ❌ DO NOT: build any frontend, chat UI, web server, database, auth, or user management. This is a batch pipeline, not an app.
- ❌ DO NOT: create the Assistant or its system prompt via code — a later manual Playground step (the verbatim system prompt is in Section 6 for reference only, so the Markdown you emit carries citable URLs Task 2 will need).
- ❌ DO NOT: scrape via raw HTML/BeautifulSoup page crawling when the Zendesk API returns clean structured content. Use the API.

## 2. 🚨 Critical Constraints — DO NOT VIOLATE

### 🔴 Constraint 1: Idempotent Delta Detection — Never Re-process Unchanged Content
The daily job's core value is acting on **only** what changed. Treating all 400+ articles as "new" every day fails the rubric.

Strictly FORBIDDEN:
- ❌ Wiping and rebuilding the whole manifest every run.
- ❌ Re-emitting an article whose content hash is unchanged as "added" or "updated".
- ❌ Losing track of the mapping between article ID → slug → content hash (→ future `file_id` slot for Task 2).

Mandatory ACTIONS:
- ✅ Persist a manifest/state file (e.g. `state/manifest.json`) mapping `article_id → {slug, content_hash, updated_at, file_id: null}`, stored durably so the next run can diff against it. Reserve the `file_id` field now so Task 2's uploader can populate it without a schema change.
- ✅ On each run: compute hash of the normalized Markdown; classify each article as **added** (not in manifest), **updated** (hash changed), or **skipped** (hash identical); hand only added/updated to the uploader interface.
- ✅ Log the three counts explicitly at the end of every run.

If unsure how the manifest should persist across DigitalOcean runs: STOP and ask the human. The cost of asking is 0.

### 🔴 Constraint 2: No Secrets in the Repo
Any API keys (Zendesk creds if used; the `OPENAI_API_KEY` slot reserved for Task 2) must come from environment variables only — never hard-coded.

Strictly FORBIDDEN:
- ❌ Hard-coding any key, token, or secret anywhere in source, tests, Docker image, or commit history.

Mandatory ACTIONS:
- ✅ Provide `.env.sample` with placeholder keys and no real values (include the `OPENAI_API_KEY` placeholder now so Task 2 needs no env changes).
- ✅ Read all secrets via `os.environ`. `docker run -e ...` is the contract; the job must still run end-to-end with no OpenAI key present, since the stub uploader needs none.

### 🔴 Constraint 3: Branch — Working Directly on `main` Is Fine This Run
This is a brand-new, empty repo, so committing directly to `main` is acceptable for this build. No feature branch or worktree is required. Keep commits small, clear, and logically scoped (scraper, delta, uploader interface, docker, docs). Once real history and collaborators exist, switch back to feature-branch discipline — but not this turn.

### 🔴 Constraint 4: Autonomous Testing — Do Not Ask the Human to Test
You are responsible for running ALL tests. Write them, watch them fail, fix them, watch them pass — autonomously. Mock the Zendesk API and OpenAI API in unit tests so tests run offline and deterministically. Writing "please run..." or "you can verify by..." violates this rule. The one thing the human does manually is the OpenAI Playground assistant setup + the sanity-check screenshot (Section 9).

### 🔴 Constraint 5: Use Sub-Agents
Execute via `subagent-driven-development`. Dispatch a fresh subagent per bite-sized task with two-stage review (spec compliance, then code quality). Do not attempt the whole build in one context. See Workflow Phase 4.

## 3. Project Context — Quick Reference

* Repository: https://github.com/TuanBew/OptiClone  (deliberately cryptic name — do NOT rename it to anything containing "optisigns").
* Core Tech Stack: **Python 3.11+**. Suggested libs: `requests` (Zendesk API), `markdownify` or `html2text` (HTML→Markdown), `python-dotenv`. Do NOT add the `openai` SDK in this build — it belongs to Task 2. Keep dependencies minimal and pinned in `requirements.txt`.
* Data source: **Zendesk Help Center API** for `support.optisigns.com`. Verified working, public, no auth needed for published articles.
* Vector store: **deferred to Task 2** (OpenAI Vector Store). Represented here only by the `Uploader` interface + `StubUploader`.
* Testing Stack: `pytest` with `responses`/`respx` or `unittest.mock` to stub the Zendesk HTTP calls.
* Deployment: **DigitalOcean**, Dockerized, scheduled once per day (App Platform scheduled job, or a droplet cron running the container). Must expose a log link / last-run artifact.

### Verified Zendesk API facts (build against these, not assumptions)
* List endpoint: `GET https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100&page=N`
* Pagination: response includes `count`, `page`, `page_count`, `next_page`. ~406 articles across pages — page through `next_page` until null.
* Each article object includes: `id`, `title`, `name`, `body` (HTML string), `html_url` (the canonical public article URL — use for citations and the `Article URL:` metadata), `section_id`, `locale`, `draft`, `created_at`, `updated_at`, `edited_at`, `label_names`.
* Filter out `draft: true` articles. Use `html_url` slug (or a slugified `title`) for the `<slug>.md` filename.
* For delta detection, `updated_at`/`edited_at` are useful signals but the **authoritative** trigger is the content hash of the normalized Markdown (timestamps can move without meaningful content change).

Business logic that must remain intact:
* **≥ 30 articles** ingested (there are 400+; a sensible cap or full pull is fine — document the choice).
* **Clean Markdown** — headings, code blocks, and relative links preserved; Zendesk nav chrome, ad blocks, and empty wrapper tags removed.
* **Delta detection** on the daily run, with added/updated/skipped logged; the delta handed to the uploader interface.

Locked architecture (do not change):
* Content hash + persisted manifest is the single source of truth for delta decisions — not filesystem timestamps.
* Uploader is a **pluggable module** behind a small interface (`Uploader.upload(files)`). This build ships `StubUploader` (logs + writes the delta artifact); **Task 2** adds `OpenAIVectorStoreUploader` behind the same interface with zero changes to scraper/delta/main.
* `main.py` orchestrates: `scrape() → normalize() → diff(manifest) → uploader.upload(delta) → write_manifest() → log_counts()`.

Completed work: **None — greenfield build** (aside from the assignment doc and repo scaffold). Task 2 is the planned follow-up.

## 4. Build Scope — What Gets Created

TARGET STATE: Zendesk API → scraper → Markdown files → delta diff vs manifest → `Uploader` interface (stub for now), all driven by `main.py` inside a Docker container run daily on DigitalOcean.

| Component | Status | Notes |
| :--- | :--- | :--- |
| `scraper/zendesk.py` | ➕ Added | Paginated fetch of published articles from the Help Center API |
| `scraper/markdown.py` | ➕ Added | HTML→Markdown normalization; strip nav/ads; preserve headings/code/links; write `<slug>.md` |
| `uploader/base.py` + `uploader/stub.py` | ➕ Added | Pluggable `Uploader` interface + `StubUploader` (logs delta, writes `state/last_delta.json`). Task 2 adds `openai_store.py` here. |
| `delta/manifest.py` | ➕ Added | Load/save manifest, content hashing, added/updated/skipped classification |
| `main.py` | ➕ Added | Entrypoint orchestrating scrape → diff → uploader.upload → log; exits 0 |
| `Dockerfile` | ➕ Added | `docker run <image>` runs once, exits 0 (accepts `-e` vars) |
| DigitalOcean daily schedule | ➕ Added | Scheduled job config + documented log link |
| `.env.sample` | ➕ Added | `OPENAI_API_KEY` (reserved for Task 2, unused now), optional `ARTICLE_LIMIT` |
| `README.md` (≤ 1 page) | ➕ Added | Setup, run locally, delta strategy, log link, note that upload is stubbed pending Task 2 |
| `tests/` | ➕ Added | Unit tests w/ mocked Zendesk; delta-logic tests; one end-to-end dry run against the stub |

## 5. Workflow — Execute In Strict Order (Superpowers Skills)

**Phase 1 — `brainstorming`** (before code): Refine requirements through questions, confirm the manifest-persistence approach on DigitalOcean, and confirm the `Uploader` interface shape (so Task 2 slots in cleanly). Present the design in sections. Save the design doc. **Wait for human approval.**

**Phase 2 — Project setup** (no worktree needed — work on `main`): Initialize the repo scaffold, `requirements.txt`, and venv. Verify a clean `pytest` baseline. Make an initial commit on `main`.

**Phase 3 — `writing-plans`**: Break work into 2–5 minute tasks with exact file paths, complete code, and verification steps. **Wait for human approval of the plan.**

**Phase 4 — `subagent-driven-development`**: Dispatch a fresh subagent per task with two-stage review (spec compliance, then code quality). This is mandatory (Constraint 5).

**Phase 5 — `test-driven-development`**: RED → GREEN → REFACTOR. Write a failing test, watch it fail, write minimal code, watch it pass, commit. Mock the Zendesk network I/O. Prioritize the delta-classification logic and Markdown normalization as the highest-value test targets.

**Phase 6 — `requesting-code-review`**: Between tasks, review against the plan; report issues by severity. Critical issues block progress.

**Phase 7 — Finish up**: Verify all tests pass, ensure the final state is committed and pushed to `main`, and summarize what shipped. (No branch merge or worktree cleanup needed this run.)

## 6. Reference — Assistant System Prompt (Task 2 / manual, NOT in code here)

For reference only, so the Markdown you emit carries what the future assistant will need to cite. The human sets this verbatim in the Playground during Task 2:

```
You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.
```

Implication for you: preserve each article's public `html_url` in the Markdown (e.g. a top-of-file `Article URL:` line or front-matter) so Task 2's assistant can cite it.

## 7. Architecture Notes — Decisions Already Made

| Decision | Rationale | Implication |
| :--- | :--- | :--- |
| Zendesk Help Center API over HTML crawling | Returns clean structured `body` + metadata | No brittle CSS selectors; reliable `html_url` for citations |
| Content hash as delta trigger (not timestamps) | Timestamps drift without content change | Manifest stores hash per article; skip if unchanged |
| Persisted `manifest.json` | Daily job must diff against last run | Must survive across DigitalOcean runs (commit artifact or durable storage) |
| Pluggable `Uploader` interface + stub | Task 2 adds the real OpenAI client | Swap stub → real impl with no change to scraper/delta/main |
| Markdown front-matter with `Article URL:` | Task 2's assistant must cite source URLs | Normalizer injects URL metadata per file now |

## 8. Environment & Configuration

* Variables (document in `.env.sample`, never commit real values):
  * `OPENAI_API_KEY=<reserved for Task 2; unused by the stub uploader>`
  * `ARTICLE_LIMIT=<optional cap, e.g. 50; omit to pull all published>`
* Docker contract: `docker run <image>` → runs once → exits 0. Must succeed with **no** OpenAI key set, since the stub uploader needs none. (Passing `-e OPENAI_API_KEY=...` must not break it.)

## 9. Success Criteria — When Is This Task Done?

- [ ] Scrape: ≥ 30 published articles pulled via Zendesk API, each saved as clean `<slug>.md` with headings/code blocks/relative links preserved and nav/ads removed.
- [ ] Uploader seam: `Uploader` interface + `StubUploader` in place; the delta is handed to it and recorded (log + `state/last_delta.json`). Swapping in a real uploader would touch only that module.
- [ ] Delta job: `main.py` re-scrapes, detects new/updated via hash, determines the delta, and logs **added / updated / skipped** counts. A second run with no changes logs all-skipped.
- [ ] DevOps: `Dockerfile` builds; `docker run <image>` runs once and exits 0 (with or without an OpenAI key); DigitalOcean daily schedule configured; README links to job logs / last-run artifact.
- [ ] Testing: All `pytest` tests PASS, autonomously, with mocked Zendesk API — including delta-classification and Markdown-normalization coverage plus one end-to-end dry run against the stub.
- [ ] Security: no secrets in source or history; `.env.sample` present; secrets read from env only.
- [ ] Quality: clean, commented, modular code; ≤ 1-page README with setup + local-run + delta strategy + log link + a clear note that vector-store upload is stubbed pending Task 2. Ready for merge.

## 10. Out of Scope — Do Not Do These

- ❌ **Task 2 in any form**: OpenAI Files/Vector Stores API, embeddings, chunking logic, or the `openai` SDK. Stop at the `Uploader` interface + stub.
- ❌ Any frontend, chat UI, web server, REST API, or database.
- ❌ Creating the Assistant or its system prompt via code (later manual Playground step).
- ❌ Taking the sanity-check screenshot ("How do I add a YouTube video?") — that's part of Task 2 after the real upload works.
- ❌ Renaming the repo, or naming anything "optisigns*".
- ❌ Unnecessary dependency upgrades or scope beyond what is defined here.
