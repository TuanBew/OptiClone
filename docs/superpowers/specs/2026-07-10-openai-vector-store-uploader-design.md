# OptiBot Mini-Clone: Task 2 — Programmatic OpenAI Vector Store Upload

Design spec for Take-Home Task 2: replace `StubUploader` with a real
`OpenAIVectorStoreUploader` behind the existing `Uploader` interface, so the
daily delta job pushes changed Markdown articles into an OpenAI Vector Store
and attaches it to the existing "Opticlone" assistant
(`asst_1C5Q789Hqdbzv9nJsij2DDaI`). Task 1 (scrape → Markdown) and Task 3
(daily delta job, Dockerized, deployed to Fly.io) are already shipped and
unchanged by this build.

## Source of Truth

- `OptiSigns_Take-Home_Test_Updated.docx` §2 — Task 2 requirements.
- The prepared Task 2 execution prompt (pasted into this session) — locked
  interface changes (Section 3), critical constraints, and build scope. This
  spec fills in the design decisions that prompt left open (SDK method
  verification, chunk-counting mechanism, error handling) and records the
  live-verification-under-budget-constraint plan.

## Confirmed SDK Facts (verified by introspecting the installed client, not assumed)

Context7 documentation for `openai-python` was internally inconsistent —
`helpers.md` showed `client.beta.vector_stores.files.upload_and_poll(...)`
while `api.md` showed the same call with no `beta` in the path. Rather than
guess, `openai==2.45.0` was installed into the project venv and the real
client object was introspected directly (`hasattr`, `inspect.signature`,
`inspect.getsource`). Confirmed facts, pinned to this version:

- **Vector Stores are top-level**, not under `.beta`:
  `client.vector_stores.create/retrieve/update/delete`,
  `client.vector_stores.files.*`. **Assistants remain under `.beta`**:
  `client.beta.assistants.update(...)`. This matches the take-home prompt's
  note that the Assistants API sunsets while Vector Stores/File Search
  carries over to the Responses API unchanged — the SDK's own namespacing
  already reflects that split.
- **One call does upload + attach + poll**:
  `client.vector_stores.files.upload_and_poll(vector_store_id=str, file=<binary file handle>)`.
  Its source shows it internally calls `client.files.create(file=file, purpose="assistants")`
  then attaches the resulting file to the vector store and polls to a
  terminal status — so the uploader needs one call per article, not three.
- **It does not raise on failure.** It returns a `VectorStoreFile` with
  `.id`, `.status` (`"in_progress"` never returned by `upload_and_poll`/`poll`
  since they loop until terminal — only `"completed"`, `"cancelled"`, or
  `"failed"`), and `.last_error`. Callers must check `.status` themselves.
- **Delete is two calls, not one.**
  `client.vector_stores.files.delete(file_id, vector_store_id=...)` only
  detaches the file from the store. `client.files.delete(file_id)` separately
  deletes the underlying File object. Both are required to avoid orphaning a
  File object on update (Constraint 2).
- **Chunk counting is real, not an estimate.**
  `client.vector_stores.files.content(file_id=..., vector_store_id=...)`
  returns a paginated list of `FileContentResponse` objects (fields: `.text`,
  `.type`) — one entry per chunk. `len(list(...))` gives the real embedded
  chunk count for that file. Confirmed via `model_fields` on
  `VectorStoreFile` and `FileContentResponse`.
- **Chunking strategy**: omitting the `chunking_strategy` parameter entirely
  (not passing it) uses OpenAI's server-side "auto" default (~800 token
  chunks, ~400 token overlap) — satisfies the take-home prompt's "LOCKED:
  auto-default" requirement with zero extra code to construct a strategy
  object.
- `VectorStoreFile.id` is the value persisted into the manifest as
  `file_id` — the same id used for delete-then-replace on the next run.

**Decision (approved):** because real chunk counting is confirmed working on
the pinned SDK version, the "estimate chunk count as a documented fallback"
path from the original prompt is dropped — it would be unreachable code for a
scenario already ruled out empirically. If a future SDK version ever removes
`content()`, that will surface as a clear test/runtime failure to fix then,
not something to pre-build a silent fallback for now (YAGNI).

## Interface Changes (locked, from the take-home execution prompt)

**`uploader/base.py`**
- `ArticleFile` gains `file_id: str | None = None` — the existing OpenAI file
  id for an updated article, or `None` for a new one.
- `Uploader.upload()` changes return type: `def upload(self, files: list[ArticleFile]) -> dict[int, str]` —
  maps `article_id → new file_id` for everything uploaded this run.

**`uploader/stub.py`**
- Conforms to the new signature: returns `{}`. Keeps writing
  `state/last_delta.json` exactly as before so `test_main_e2e.py` stays green.

**`delta/manifest.py`**
- `update_manifest_entries(manifest, articles, file_ids=None)` — writes each
  article's new `file_id` from the `file_ids` map when present, falling back
  to the existing stored `file_id` otherwise (preserves today's stub-path
  behavior with no map).

**`main.py`**
- Populates `ArticleFile.file_id` from `manifest[str(article_id)]["file_id"]`
  for updated articles (new articles get `None`, matching the dataclass
  default).
- Selects `OpenAIVectorStoreUploader` when `OPENAI_API_KEY` is set in the
  environment, else `StubUploader` — this is the only branch point; no other
  code path changes based on the key's presence.
- Captures `uploaded = uploader.upload(delta_files)` and threads it into
  `update_manifest_entries(..., file_ids=uploaded)`.

Every change stays backward-compatible with the stub path: a no-key run and
all pre-existing tests behave identically to today.

## `OpenAIVectorStoreUploader` — Architecture

New file: `uploader/openai_store.py`.

```python
class OpenAIVectorStoreUploader(Uploader):
    def __init__(
        self,
        api_key: str,
        assistant_id: str,
        vector_store_id: str | None = None,
        client: "openai.OpenAI | None" = None,
    ):
        ...
```

The optional `client` param is the test seam: production code leaves it
unset and a real `OpenAI(api_key=api_key)` is constructed; tests inject a
`MagicMock` so nothing touches the network (Constraint 4).

Two private methods keep the Assistants-API dependency isolated from vector
store / upload logic, per Constraint 1 — when Assistants sunsets, only
`_attach_to_assistant` needs to change:

- `_ensure_vector_store() -> str` — reuses `self.vector_store_id` if set;
  else `client.vector_stores.create(name="OptiClone Articles")`, logs the new
  id at `WARNING` (visible without verbose logging, since a human must copy
  it into `.env`/Fly secrets to avoid a new store being created next run).
- `_attach_to_assistant(vector_store_id) -> None` —
  `client.beta.assistants.update(self.assistant_id, tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}})`.
  Idempotent; safe to call every run.

### `upload(files)` data flow

1. `vector_store_id = self._ensure_vector_store()`
2. `self._attach_to_assistant(vector_store_id)`
3. For each `ArticleFile`, in order:
   - If `file.file_id` is set (update case): call
     `client.vector_stores.files.delete(file.file_id, vector_store_id=...)`
     then `client.files.delete(file.file_id)`. Each wrapped in its own
     try/except — a 404 on an already-gone id logs a warning and continues;
     it must not block re-uploading the new content.
   - `vsf = client.vector_stores.files.upload_and_poll(vector_store_id=..., file=open(file.path, "rb"))`.
   - If `vsf.status == "completed"`: record `article_id → vsf.id` in the
     result map; count chunks via
     `len(list(client.vector_stores.files.content(file_id=vsf.id, vector_store_id=...)))`
     and add to a running total.
   - If `vsf.status == "failed"` (or `"cancelled"`): log the article slug and
     `vsf.last_error` at `ERROR`, do **not** record an id for it, continue to
     the next file. A failed article's manifest entry keeps its old
     content_hash, so it's classified as "updated" again next run and
     retried automatically — it is not silently marked done.
4. Log `files embedded=N chunks embedded=M` once, using the successful count
   and the running chunk total.
5. Return the `{article_id: file_id}` map (only successful uploads appear).

**Error handling philosophy:** one article's failure must not abort the run —
this matches the existing `main.py` philosophy (a bad article is logged and
skipped, not fatal). Only genuinely-embedded articles get a `file_id`
recorded, so the manifest naturally retries failures next run without any
special-cased retry logic.

## Testing (Constraint 4 — mocked client, fully offline)

`tests/test_openai_uploader.py` builds a `MagicMock()` standing in for the
injected `client`, configuring `.vector_stores.files.upload_and_poll.return_value`
to a fake object with `.id` / `.status="completed"` / `.last_error=None`, and
`.vector_stores.files.content.return_value` to a list of 2-3 fake chunk
objects (asserting the logged chunk count matches). Cases:

- **Added** article → `upload_and_poll` called once, no delete calls, id
  recorded in the returned map, chunk count reflects the mocked `content()`
  list length.
- **Updated** article (`file_id` set) → both
  `vector_stores.files.delete` and `client.files.delete` are called with the
  old id *before* `upload_and_poll` is called for the new content; new id
  overwrites the old one in the returned map.
- **Skipped** articles never reach `upload()` at all — already guaranteed by
  `main.py` only passing `added + updated` to the uploader; no new test
  needed for this uploader specifically.
- **Failed** status (`vsf.status = "failed"`) → no id recorded for that
  article, no exception raised, the run continues to process remaining
  files.
- **No-change second run** → `main.py`/e2e level: `upload()` called with an
  empty list makes zero SDK calls (asserted via `client.vector_stores.files.upload_and_poll.assert_not_called()`).
- `tests/test_stub_uploader.py` and `tests/test_main_e2e.py` are updated only
  for the new `upload() -> dict` return type; behavior stays green.

No live network access anywhere in the test suite. No optional live smoke
test is added to the automated suite — see "Live Verification" below for how
the real API gets exercised, and it is manual/human-gated, not something
`pytest` runs.

## Live Verification — Staged Rollout Under a Fixed Budget

The user has **$10 of OpenAI API credit total** for this build, with an
explicit instruction: the first live run against the real API must succeed
without needing retries. This changes how the real API gets touched, not
just the code:

1. **No live OpenAI API call happens during this build without the user's
   explicit go-ahead for that specific call.** The implementation phase
   produces code verified entirely against the mocked client.
2. Once the mocked suite is green and reviewed, the recommended path to
   first real verification is a **local run with `ARTICLE_LIMIT` set to 1 or
   2** (not the full ~50-article default) — this exercises the entire real
   path (vector store create, per-file upload+poll, assistant attach, chunk
   count logging) at near-zero cost before committing to the full delta.
3. Only after that small run is confirmed clean does the full-scale run (via
   `docker run` locally, then the Fly.io scheduled Machine with real Fly
   secrets) happen — and even then, `OPENAI_VECTOR_STORE_ID` from step 2 is
   reused, not recreated, since the design already treats vector-store
   creation as create-once/reuse-after.
4. If a live call does fail, the response is to stop and diagnose with the
   user, not to blindly retry — matching the "one try, must go well" intent.

This section exists to make the rollout plan explicit in the spec, not just
as a verbal aside — the implementation plan's final task will reference it
rather than silently including a "run this against the real API" step.

## Build Scope

| Component | Status | Notes |
| :--- | :--- | :--- |
| `uploader/openai_store.py` | ➕ Added | `OpenAIVectorStoreUploader` |
| `uploader/base.py` | ✏️ Changed | `ArticleFile.file_id`; `upload() -> dict[int,str]` |
| `uploader/stub.py` | ✏️ Changed | Conform to new return type |
| `delta/manifest.py` | ✏️ Changed | `update_manifest_entries(..., file_ids=None)` |
| `main.py` | ✏️ Changed | Populate `file_id`; select uploader; persist returned ids |
| `.env.sample` | ✏️ Updated | `OPENAI_ASSISTANT_ID`, `OPENAI_VECTOR_STORE_ID` |
| `requirements.txt` | ✏️ Updated | `openai==2.45.0` (pinned, matches existing style) |
| `docs/deployment.md` | ✏️ Updated | Fly secrets for the three OpenAI env vars |
| `README.md` | ✏️ Updated | Chunking strategy, counts, screenshot placeholder, un-stub Status |
| `tests/test_openai_uploader.py` | ➕ Added | Mocked-client add/update/failed/no-change cases |
| `tests/test_stub_uploader.py`, `tests/test_main_e2e.py` | ✏️ Adjusted | New `upload()` return type only |

## Out of Scope (confirmed)

- Rewriting the scraper, Markdown normalizer, or delta-classification logic.
- Creating or editing the assistant / its system prompt via code (already
  exists in the Playground).
- Responses API implementation (sunset is noted; build targets Assistants).
- Running `fly deploy`, setting real Fly secrets, or the Playground
  screenshot — manual human steps, reported at the end, not performed here.
- Any live OpenAI API call during implementation — see "Live Verification."
- Renaming the repo or naming anything `optisigns*`.
