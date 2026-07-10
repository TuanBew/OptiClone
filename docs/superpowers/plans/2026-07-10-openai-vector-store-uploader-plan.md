# OpenAI Vector Store Uploader (Task 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `StubUploader` with a real `OpenAIVectorStoreUploader` so the daily delta job uploads changed Markdown articles into an OpenAI Vector Store and attaches it to the existing "Opticlone" assistant, entirely offline-tested.

**Architecture:** A new `uploader/openai_store.py` implements the existing `Uploader` ABC using an injectable `openai.OpenAI` client (tests inject a mock, production constructs a real one). `ArticleFile` gains a `file_id` field and `Uploader.upload()` changes its return type to `dict[int, str]` so `main.py` and `delta/manifest.py` can persist the OpenAI file id assigned to each article, enabling delete-then-replace on the next run.

**Tech Stack:** Python 3.11, `openai==2.45.0` (Vector Stores API is top-level in this SDK version, not under `.beta`; Assistants API remains under `client.beta`), `pytest` + `unittest.mock` for fully offline tests.

## Global Constraints

- No live OpenAI API call anywhere in the test suite or in any task's verification steps — every test injects a mock `client`. (Source: take-home Constraint 4; user has a fixed $10 OpenAI credit budget and the first live run must succeed without retries — see `docs/superpowers/specs/2026-07-10-openai-vector-store-uploader-design.md` "Live Verification".)
- The stub path (`OPENAI_API_KEY` unset) must remain behaviorally identical to today after every task — run the full suite after each task and confirm the pre-existing tests still pass unchanged.
- Do not pass a `chunking_strategy` parameter anywhere — omitting it uses OpenAI's server-side "auto" default, which is the locked chunking strategy for this build.
- Chunk counts are real counts via `client.vector_stores.files.content(...)`, never an estimate — the estimate-fallback path from the original take-home prompt was explicitly dropped during brainstorming (YAGNI; confirmed working on the pinned SDK version).
- One article's upload failure must never abort the whole run — log and continue, per the existing `main.py` philosophy that a single bad article shouldn't kill the daily job.
- Do not rename the repo or name anything `optisigns*`. Do not touch scraper/, `scraper/markdown.py`, or the classification logic in `delta/manifest.py` beyond the one specified signature change.
- Commit after every task (small, clearly-scoped commits — interface change; each uploader increment; main wiring; docs).

---

### Task 1: `ArticleFile.file_id` and `Uploader.upload()` return type

**Files:**
- Modify: `uploader/base.py`
- Test: `tests/test_uploader_base.py` (new)

**Interfaces:**
- Produces: `ArticleFile(article_id: int, slug: str, path: str, content_hash: str, url: str, file_id: str | None = None)` — the `file_id` field is new and defaults to `None`, so every existing call site that constructs `ArticleFile` without it keeps working unchanged.
- Produces: `Uploader.upload(self, files: list[ArticleFile]) -> dict[int, str]` — abstract method's return type annotation changes from `None` to `dict[int, str]` (a mapping of `article_id -> new file_id` for everything uploaded this run). This is a type-hint-only change at this step; concrete subclasses are updated in Tasks 2 and 4-6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_uploader_base.py`:

```python
from uploader.base import ArticleFile


def test_article_file_file_id_defaults_to_none():
    file = ArticleFile(
        article_id=1, slug="one", path="articles/one.md", content_hash="h1", url="https://x/one"
    )
    assert file.file_id is None


def test_article_file_accepts_explicit_file_id():
    file = ArticleFile(
        article_id=1,
        slug="one",
        path="articles/one.md",
        content_hash="h1",
        url="https://x/one",
        file_id="file_abc123",
    )
    assert file.file_id == "file_abc123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_uploader_base.py -v`
Expected: FAIL — `TypeError: ArticleFile.__init__() got an unexpected keyword argument 'file_id'` (second test), since `ArticleFile` has no `file_id` field yet.

- [ ] **Step 3: Add the field and update the abstract method**

Edit `uploader/base.py` to:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ArticleFile:
    article_id: int
    slug: str
    path: str
    content_hash: str
    url: str
    file_id: str | None = None


class Uploader(ABC):
    @abstractmethod
    def upload(self, files: list[ArticleFile]) -> dict[int, str]:
        """Upload the given delta of ArticleFile entries.

        Returns a mapping of article_id -> new file_id for every file
        successfully uploaded this run.
        """
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_uploader_base.py -v`
Expected: `2 passed`

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `.venv/Scripts/pytest -q`
Expected: `20 passed` (18 pre-existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add uploader/base.py tests/test_uploader_base.py
git commit -m "feat: add ArticleFile.file_id and change Uploader.upload() return type"
```

---

### Task 2: `StubUploader` conforms to the new return type

**Files:**
- Modify: `uploader/stub.py`
- Test: `tests/test_stub_uploader.py`

**Interfaces:**
- Consumes: `Uploader.upload(self, files: list[ArticleFile]) -> dict[int, str]` from Task 1.
- Produces: `StubUploader.upload(files) -> dict[int, str]` — always returns `{}`. All other stub behavior (logging, writing `state/last_delta.json`) is unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_stub_uploader.py` (append, do not remove existing tests):

```python
def test_stub_uploader_upload_returns_empty_dict(tmp_path):
    delta_path = str(tmp_path / "state" / "last_delta.json")
    uploader = StubUploader(delta_path=delta_path)
    files = [
        ArticleFile(article_id=1, slug="one", path="articles/one.md", content_hash="h1", url="https://x/one"),
    ]

    result = uploader.upload(files)

    assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_stub_uploader.py -v`
Expected: FAIL — `assert None == {}` (the current `upload()` has no `return` statement, so it implicitly returns `None`).

- [ ] **Step 3: Add the return statement**

In `uploader/stub.py`, change the method signature and add a `return {}` at the end:

```python
    def upload(self, files: list[ArticleFile]) -> dict[int, str]:
        for file in files:
            logger.info(
                "Would upload: %s (article_id=%s, url=%s)", file.slug, file.article_id, file.url
            )

        directory = os.path.dirname(self.delta_path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uploaded_slugs": [file.slug for file in files],
            "uploaded_count": len(files),
            "articles": [
                {"article_id": file.article_id, "slug": file.slug, "url": file.url}
                for file in files
            ],
        }
        with open(self.delta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_stub_uploader.py -v`
Expected: `3 passed`

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `21 passed`

- [ ] **Step 6: Commit**

```bash
git add uploader/stub.py tests/test_stub_uploader.py
git commit -m "feat: StubUploader.upload() returns empty dict per new interface"
```

---

### Task 3: `update_manifest_entries` accepts a `file_ids` map

**Files:**
- Modify: `delta/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces: `update_manifest_entries(manifest: dict, articles: list, file_ids: dict[int, str] | None = None) -> dict` — when `file_ids` contains an entry for `article.article_id`, that value is written as the manifest entry's `file_id`; otherwise the previously-stored `file_id` is preserved exactly as before. Called with no third argument, behavior is unchanged from today (verified by the two pre-existing tests in this file, which must still pass unmodified).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_manifest.py` (append):

```python
def test_update_manifest_entries_uses_file_ids_map_when_present():
    manifest = {
        "2": {"slug": "two", "content_hash": "hash2-old", "updated_at": "old", "file_id": "file_abc"},
    }
    articles = [make_article(2, "two", "hash2-new", updated_at="2026-02-01T00:00:00Z")]

    new_manifest = update_manifest_entries(manifest, articles, file_ids={2: "file_new"})

    assert new_manifest["2"]["file_id"] == "file_new"


def test_update_manifest_entries_falls_back_to_existing_when_id_not_in_map():
    manifest = {
        "2": {"slug": "two", "content_hash": "hash2-old", "updated_at": "old", "file_id": "file_abc"},
    }
    articles = [make_article(2, "two", "hash2-new")]

    new_manifest = update_manifest_entries(manifest, articles, file_ids={})

    assert new_manifest["2"]["file_id"] == "file_abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_manifest.py -v`
Expected: FAIL — `TypeError: update_manifest_entries() got an unexpected keyword argument 'file_ids'`.

- [ ] **Step 3: Add the parameter**

In `delta/manifest.py`, replace `update_manifest_entries`:

```python
def update_manifest_entries(
    manifest: dict, articles: list, file_ids: dict[int, str] | None = None
) -> dict:
    file_ids = file_ids or {}
    new_manifest = dict(manifest)
    for article in articles:
        key = str(article.article_id)
        existing_file_id = new_manifest.get(key, {}).get("file_id")
        new_manifest[key] = {
            "slug": article.slug,
            "content_hash": article.content_hash,
            "updated_at": article.updated_at,
            "file_id": file_ids.get(article.article_id, existing_file_id),
        }
    return new_manifest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/pytest tests/test_manifest.py -v`
Expected: `7 passed`

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `23 passed`

- [ ] **Step 6: Commit**

```bash
git add delta/manifest.py tests/test_manifest.py
git commit -m "feat: update_manifest_entries accepts a file_ids override map"
```

---

### Task 4: `OpenAIVectorStoreUploader` — construction, vector store reuse/create, assistant attach, new-article upload

**Files:**
- Modify: `requirements.txt`
- Create: `uploader/openai_store.py`
- Test: `tests/test_openai_uploader.py` (new)

**Interfaces:**
- Consumes: `ArticleFile` (with `file_id`) and `Uploader` from `uploader/base.py` (Task 1).
- Produces: `OpenAIVectorStoreUploader(api_key: str, assistant_id: str, vector_store_id: str | None = None, client: openai.OpenAI | None = None)`. `client` is the test seam — production leaves it `None` and a real `OpenAI(api_key=api_key)` is constructed; tests always pass a mock. Produces `upload(files: list[ArticleFile]) -> dict[int, str]` (this task's version handles only new articles — no `file_id` set on the input — and an empty list; Tasks 5 and 6 extend it).
- The mocked `client` in tests must expose (as `MagicMock` attributes, since `MagicMock` auto-creates arbitrary attributes): `client.vector_stores.create`, `client.vector_stores.files.upload_and_poll`, `client.vector_stores.files.content`, `client.beta.assistants.update`.

- [ ] **Step 1: Add and install the `openai` dependency**

Add this line to `requirements.txt`:

```
openai==2.45.0
```

Run: `.venv/Scripts/pip install -r requirements.txt`
Expected: `Successfully installed openai-2.45.0` (or `Requirement already satisfied` if already present in the venv — either is fine).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_openai_uploader.py`:

```python
from unittest.mock import MagicMock

from uploader.base import ArticleFile
from uploader.openai_store import OpenAIVectorStoreUploader


def make_article_file(tmp_path, article_id=1, slug="one", file_id=None, body="# One\n"):
    path = tmp_path / f"{slug}.md"
    path.write_text(body, encoding="utf-8")
    return ArticleFile(
        article_id=article_id,
        slug=slug,
        path=str(path),
        content_hash="hash1",
        url=f"https://support.optisigns.com/hc/en-us/articles/{slug}",
        file_id=file_id,
    )


def make_mock_client():
    client = MagicMock()
    client.vector_stores.files.upload_and_poll.return_value = MagicMock(
        id="file_new1", status="completed", last_error=None
    )
    client.vector_stores.files.content.return_value = [MagicMock(), MagicMock()]
    return client


def test_upload_new_article_records_file_id_and_chunk_count(tmp_path):
    client = make_mock_client()
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [make_article_file(tmp_path)]

    result = uploader.upload(files)

    assert result == {1: "file_new1"}
    client.vector_stores.create.assert_not_called()
    client.beta.assistants.update.assert_called_once_with(
        "asst_test", tool_resources={"file_search": {"vector_store_ids": ["vs_existing"]}}
    )
    _, kwargs = client.vector_stores.files.upload_and_poll.call_args
    assert kwargs["vector_store_id"] == "vs_existing"
    client.vector_stores.files.content.assert_called_once_with(
        file_id="file_new1", vector_store_id="vs_existing"
    )


def test_upload_creates_vector_store_when_none_configured(tmp_path):
    client = make_mock_client()
    client.vector_stores.create.return_value = MagicMock(id="vs_brand_new")
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id=None, client=client
    )
    files = [make_article_file(tmp_path)]

    uploader.upload(files)

    client.vector_stores.create.assert_called_once_with(name="OptiClone Articles")
    assert uploader.vector_store_id == "vs_brand_new"
    _, kwargs = client.vector_stores.files.upload_and_poll.call_args
    assert kwargs["vector_store_id"] == "vs_brand_new"


def test_upload_empty_list_makes_no_client_calls():
    client = make_mock_client()
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )

    result = uploader.upload([])

    assert result == {}
    client.vector_stores.create.assert_not_called()
    client.beta.assistants.update.assert_not_called()
    client.vector_stores.files.upload_and_poll.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uploader.openai_store'`.

- [ ] **Step 4: Write the implementation**

Create `uploader/openai_store.py`:

```python
import logging

from openai import OpenAI

from uploader.base import ArticleFile, Uploader

logger = logging.getLogger(__name__)


class OpenAIVectorStoreUploader(Uploader):
    def __init__(
        self,
        api_key: str,
        assistant_id: str,
        vector_store_id: str | None = None,
        client: OpenAI | None = None,
    ):
        self.assistant_id = assistant_id
        self.vector_store_id = vector_store_id
        self.client = client or OpenAI(api_key=api_key)

    def _ensure_vector_store(self) -> str:
        if self.vector_store_id:
            return self.vector_store_id
        vector_store = self.client.vector_stores.create(name="OptiClone Articles")
        self.vector_store_id = vector_store.id
        logger.warning(
            "Created new OpenAI Vector Store id=%s -- persist this as OPENAI_VECTOR_STORE_ID "
            "so future runs reuse it instead of creating a new one.",
            vector_store.id,
        )
        return self.vector_store_id

    def _attach_to_assistant(self, vector_store_id: str) -> None:
        self.client.beta.assistants.update(
            self.assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
        )

    def upload(self, files: list[ArticleFile]) -> dict[int, str]:
        if not files:
            return {}

        vector_store_id = self._ensure_vector_store()
        self._attach_to_assistant(vector_store_id)

        uploaded: dict[int, str] = {}
        files_embedded = 0
        chunks_embedded = 0

        for file in files:
            with open(file.path, "rb") as fh:
                vsf = self.client.vector_stores.files.upload_and_poll(
                    vector_store_id=vector_store_id, file=fh
                )

            uploaded[file.article_id] = vsf.id
            files_embedded += 1
            chunks_embedded += len(
                list(
                    self.client.vector_stores.files.content(
                        file_id=vsf.id, vector_store_id=vector_store_id
                    )
                )
            )

        logger.info("files embedded=%d chunks embedded=%d", files_embedded, chunks_embedded)
        return uploaded
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: `3 passed`

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `26 passed`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt uploader/openai_store.py tests/test_openai_uploader.py
git commit -m "feat: add OpenAIVectorStoreUploader (new-article upload path)"
```

---

### Task 5: Delete-then-replace on update

**Files:**
- Modify: `uploader/openai_store.py`
- Test: `tests/test_openai_uploader.py`

**Interfaces:**
- Consumes: `ArticleFile.file_id` (Task 1) — when set, the article being uploaded is an update to a previously-embedded article, and the old OpenAI file must be removed first.
- Produces: `upload()` now handles `file.file_id is not None` by calling `client.vector_stores.files.delete(file_id, vector_store_id=...)` then `client.files.delete(file_id)` before re-uploading, tolerating either call raising (already-deleted id) without aborting the run.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_openai_uploader.py`:

```python
def test_upload_updated_article_deletes_old_file_before_uploading_new(tmp_path):
    client = make_mock_client()
    call_order = []
    client.vector_stores.files.delete.side_effect = lambda *a, **k: call_order.append("delete_vsf")
    client.files.delete.side_effect = lambda *a, **k: call_order.append("delete_file")
    client.vector_stores.files.upload_and_poll.side_effect = (
        lambda *a, **k: call_order.append("upload") or MagicMock(id="file_new1", status="completed", last_error=None)
    )
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [make_article_file(tmp_path, file_id="file_old1")]

    result = uploader.upload(files)

    assert result == {1: "file_new1"}
    client.vector_stores.files.delete.assert_called_once_with("file_old1", vector_store_id="vs_existing")
    client.files.delete.assert_called_once_with("file_old1")
    assert call_order == ["delete_vsf", "delete_file", "upload"]


def test_upload_updated_article_continues_if_old_file_already_gone(tmp_path):
    client = make_mock_client()
    client.vector_stores.files.delete.side_effect = Exception("404 not found")
    client.files.delete.side_effect = Exception("404 not found")
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [make_article_file(tmp_path, file_id="file_old1")]

    result = uploader.upload(files)

    assert result == {1: "file_new1"}
    client.vector_stores.files.upload_and_poll.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: FAIL on both new tests — `client.vector_stores.files.delete.assert_called_once_with(...)` raises `AssertionError: Expected 'delete' to have been called once. Called 0 times.` (current code never checks `file.file_id`).

- [ ] **Step 3: Add the delete-then-replace step**

In `uploader/openai_store.py`, inside the `for file in files:` loop in `upload()`, insert before the `with open(file.path, "rb") as fh:` line:

```python
        for file in files:
            if file.file_id:
                try:
                    self.client.vector_stores.files.delete(
                        file.file_id, vector_store_id=vector_store_id
                    )
                except Exception:
                    logger.warning(
                        "Could not detach old vector-store file id=%s for article_id=%s "
                        "(already gone?)", file.file_id, file.article_id, exc_info=True,
                    )
                try:
                    self.client.files.delete(file.file_id)
                except Exception:
                    logger.warning(
                        "Could not delete old File object id=%s for article_id=%s "
                        "(already gone?)", file.file_id, file.article_id, exc_info=True,
                    )

            with open(file.path, "rb") as fh:
                vsf = self.client.vector_stores.files.upload_and_poll(
                    vector_store_id=vector_store_id, file=fh
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: `5 passed`

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `28 passed`

- [ ] **Step 6: Commit**

```bash
git add uploader/openai_store.py tests/test_openai_uploader.py
git commit -m "feat: delete-then-replace superseded OpenAI file on article update"
```

---

### Task 6: Handle non-`completed` status without aborting the run

**Files:**
- Modify: `uploader/openai_store.py`
- Test: `tests/test_openai_uploader.py`

**Interfaces:**
- Produces: `upload()` checks `vsf.status`; only `"completed"` records an id and counts chunks. Any other status (`"failed"`, `"cancelled"`) logs at `ERROR` with `vsf.last_error` and moves on to the next file — that article's `article_id` is absent from the returned map, so `update_manifest_entries` will leave its old `content_hash` in place and it will be reclassified as "updated" (retried) on the next run.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_openai_uploader.py`:

```python
def test_upload_skips_recording_id_when_status_failed(tmp_path):
    client = make_mock_client()
    client.vector_stores.files.upload_and_poll.return_value = MagicMock(
        id="file_x", status="failed", last_error=MagicMock(message="embedding failed")
    )
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [make_article_file(tmp_path)]

    result = uploader.upload(files)

    assert result == {}
    client.vector_stores.files.content.assert_not_called()


def test_upload_continues_processing_remaining_files_after_one_fails(tmp_path):
    client = make_mock_client()
    failed = MagicMock(id="file_fail", status="failed", last_error=MagicMock(message="boom"))
    ok = MagicMock(id="file_ok", status="completed", last_error=None)
    client.vector_stores.files.upload_and_poll.side_effect = [failed, ok]
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [
        make_article_file(tmp_path, article_id=1, slug="one"),
        make_article_file(tmp_path, article_id=2, slug="two"),
    ]

    result = uploader.upload(files)

    assert result == {2: "file_ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: FAIL on both new tests — `assert {1: 'file_x'} == {}` (current code records an id regardless of status).

- [ ] **Step 3: Add the status check**

In `uploader/openai_store.py`, replace the block after `upload_and_poll` is called:

```python
            if vsf.status != "completed":
                logger.error(
                    "Upload failed for article_id=%s slug=%s status=%s last_error=%s",
                    file.article_id, file.slug, vsf.status, vsf.last_error,
                )
                continue

            uploaded[file.article_id] = vsf.id
            files_embedded += 1
            chunks_embedded += len(
                list(
                    self.client.vector_stores.files.content(
                        file_id=vsf.id, vector_store_id=vector_store_id
                    )
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_openai_uploader.py -v`
Expected: `7 passed`

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `30 passed`

- [ ] **Step 6: Commit**

```bash
git add uploader/openai_store.py tests/test_openai_uploader.py
git commit -m "feat: skip recording file_id and continue when a vector-store upload fails"
```

---

### Task 7: Wire the real uploader into `main.py`

**Files:**
- Modify: `main.py`
- Modify: `.env.sample`
- Test: `tests/test_main_e2e.py`

**Interfaces:**
- Consumes: `OpenAIVectorStoreUploader` (Tasks 4-6), `StubUploader` (Task 2), `update_manifest_entries(..., file_ids=...)` (Task 3), `ArticleFile.file_id` (Task 1).
- Produces: `build_uploader() -> Uploader` — selects `OpenAIVectorStoreUploader` when `OPENAI_API_KEY` is set (raising `ValueError` if `OPENAI_ASSISTANT_ID` is missing in that case), else `StubUploader`. `run()` populates each delta `ArticleFile.file_id` from the manifest's existing entry and threads `uploader.upload(...)`'s returned map into `update_manifest_entries(...)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main_e2e.py` (add these imports at the top alongside the existing ones):

```python
from uploader.openai_store import OpenAIVectorStoreUploader
from uploader.stub import StubUploader
```

Append these test functions:

```python
def test_build_uploader_returns_stub_when_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    uploader = main_module.build_uploader()
    assert isinstance(uploader, StubUploader)


def test_build_uploader_returns_openai_uploader_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_ASSISTANT_ID", "asst_test")
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)
    uploader = main_module.build_uploader()
    assert isinstance(uploader, OpenAIVectorStoreUploader)
    assert uploader.assistant_id == "asst_test"
    assert uploader.vector_store_id is None


def test_build_uploader_raises_when_assistant_id_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_ASSISTANT_ID", raising=False)
    with pytest.raises(ValueError, match="OPENAI_ASSISTANT_ID"):
        main_module.build_uploader()


@responses.activate
def test_updated_article_preserves_existing_file_id_when_using_stub(tmp_path, monkeypatch):
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=ARTICLES_PAGE_1, status=200)

    articles_dir = tmp_path / "articles"
    manifest_path = tmp_path / "state" / "manifest.json"
    delta_path = tmp_path / "state" / "last_delta.json"

    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(articles_dir))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(delta_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ARTICLE_LIMIT", "10")

    assert main_module.run() == 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["1"]["file_id"] = "file_existing123"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    changed_page = json.loads(json.dumps(ARTICLES_PAGE_1))
    changed_page["articles"][0]["body"] = "<h1>Article One</h1><p>Changed body text.</p>"
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=changed_page, status=200)

    assert main_module.run() == 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest_after = json.load(f)
    assert manifest_after["1"]["file_id"] == "file_existing123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_main_e2e.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'build_uploader'` (and `ModuleNotFoundError` is already resolved since `uploader.openai_store` exists from Task 4, but `build_uploader` does not exist yet in `main.py`).

- [ ] **Step 3: Wire it up**

In `main.py`, change the imports at the top to:

```python
import logging
import os
import sys

from dotenv import load_dotenv

from delta.manifest import classify, load_manifest, save_manifest, update_manifest_entries
from scraper.markdown import normalize_article, write_markdown_file
from scraper.zendesk import ZENDESK_ARTICLES_URL, fetch_articles
from uploader.base import ArticleFile, Uploader
from uploader.openai_store import OpenAIVectorStoreUploader
from uploader.stub import StubUploader
```

Add this function after `get_article_limit()`:

```python
def build_uploader() -> Uploader:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return StubUploader(delta_path=DELTA_PATH)

    assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")
    if not assistant_id:
        raise ValueError(
            "OPENAI_API_KEY is set but OPENAI_ASSISTANT_ID is missing; "
            "set both or neither to select the real uploader."
        )
    return OpenAIVectorStoreUploader(
        api_key=api_key,
        assistant_id=assistant_id,
        vector_store_id=os.environ.get("OPENAI_VECTOR_STORE_ID") or None,
    )
```

Replace the body of `run()` from the `delta_files = [...]` line through `save_manifest(new_manifest, MANIFEST_PATH)` with:

```python
    delta_files = [
        ArticleFile(
            article_id=article.article_id,
            slug=article.slug,
            path=written_paths[article.article_id],
            content_hash=article.content_hash,
            url=article.url,
            file_id=manifest.get(str(article.article_id), {}).get("file_id"),
        )
        for article in (delta_result.added + delta_result.updated)
    ]

    uploader = build_uploader()
    uploaded = uploader.upload(delta_files)

    new_manifest = update_manifest_entries(
        manifest, delta_result.added + delta_result.updated, file_ids=uploaded
    )
    save_manifest(new_manifest, MANIFEST_PATH)
```

- [ ] **Step 4: Update `.env.sample`**

Replace its contents with:

```
# Set to enable the real OpenAI Vector Store uploader. Leave unset (or empty)
# to use the StubUploader, which needs no OpenAI credentials.
OPENAI_API_KEY=

# Required when OPENAI_API_KEY is set. The existing "Opticlone" assistant,
# created once in the OpenAI Playground (model gpt-4o-mini, File Search on).
OPENAI_ASSISTANT_ID=asst_1C5Q789Hqdbzv9nJsij2DDaI

# Optional. Reuses an existing Vector Store instead of creating a new one.
# Left empty on first run, the uploader creates one and logs its id at
# WARNING level -- copy that id here (and set it as a Fly secret) afterward.
OPENAI_VECTOR_STORE_ID=

# Optional cap on how many published articles to pull per run. Defaults to 50 if unset.
ARTICLE_LIMIT=50
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_main_e2e.py -v`
Expected: `9 passed`

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/pytest -q`
Expected: `34 passed`

- [ ] **Step 7: Commit**

```bash
git add main.py .env.sample tests/test_main_e2e.py
git commit -m "feat: wire OpenAIVectorStoreUploader into main.py behind OPENAI_API_KEY"
```

---

### Task 8: Update `docs/deployment.md` for the three OpenAI Fly secrets

**Files:**
- Modify: `docs/deployment.md`

**Interfaces:**
- No code interfaces. This task only updates deployment documentation to reflect that the job can now upload for real.

- [ ] **Step 1: Replace the OPENAI_API_KEY step**

In `docs/deployment.md`, replace this list item:

```
4. Set `OPENAI_API_KEY` as a Fly secret if you ever want to pass one (leave
   unset for this build — the stub uploader needs none):
   ```
   fly secrets set OPENAI_API_KEY=... --app opticlone-job
   ```
```

with:

```
4. Set the three OpenAI secrets so the job uses the real
   `OpenAIVectorStoreUploader` instead of the stub. Leave all three unset to
   keep using the stub (e.g. for a dry run):
   ```
   fly secrets set OPENAI_API_KEY=sk-... --app opticlone-job
   fly secrets set OPENAI_ASSISTANT_ID=asst_1C5Q789Hqdbzv9nJsij2DDaI --app opticlone-job
   fly secrets set OPENAI_VECTOR_STORE_ID=vs_... --app opticlone-job
   ```
   `OPENAI_VECTOR_STORE_ID` should be set only *after* a first successful run
   has created one and logged its id (see the README's "Verifying the real
   uploader" section) — leaving it unset on the very first run is expected
   and correct; the uploader creates the store itself.
```

- [ ] **Step 2: Verify the doc change didn't break anything**

Run: `.venv/Scripts/pytest -q`
Expected: `34 passed` (docs-only change; confirms nothing else in the repo state was disturbed)

- [ ] **Step 3: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: update Fly secrets for the real OpenAI uploader"
```

---

### Task 9: Update `README.md` — chunking, counts, screenshot placeholder, un-stub Status

**Files:**
- Modify: `README.md`

**Interfaces:**
- No code interfaces. Documentation only.

- [ ] **Step 1: Replace the opening summary line**

Replace:

```
A daily job that pulls OptiSigns support articles from the Zendesk Help Center
API, normalizes them to clean Markdown, and detects the delta (added / updated /
skipped) against the previous run. Vector-store upload is **stubbed** in this
build — see "Status" below.
```

with:

```
A daily job that pulls OptiSigns support articles from the Zendesk Help Center
API, normalizes them to clean Markdown, detects the delta (added / updated /
skipped) against the previous run, and uploads the delta into an OpenAI
Vector Store attached to the "Opticlone" assistant — see "Status" below.
```

- [ ] **Step 2: Extend the "Delta strategy" section**

Replace:

```
Only added/updated articles are handed to the `Uploader` interface
(`uploader/base.py`). This build ships a `StubUploader` that logs what it would
embed and writes `state/last_delta.json`. A later build drops in a real
`OpenAIVectorStoreUploader` behind the same interface with no changes to the
scraper, delta logic, or `main.py`.
```

with:

```
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
```

- [ ] **Step 3: Update the "Docker" section note**

Replace:

```
Exits 0 with or without `OPENAI_API_KEY` set.
```

with:

```
Exits 0 with or without `OPENAI_API_KEY` set. When set, also requires
`OPENAI_ASSISTANT_ID` in the same `.env`/`--env-file`.
```

- [ ] **Step 4: Replace the "Status" section**

Replace:

```
## Status

Vector-store upload (OpenAI Files/Vector Stores API, chunking, embeddings) is
**not implemented yet** — that's a follow-up build. This build stops at the
pluggable `Uploader` interface + `StubUploader`, and the committed `articles/`
snapshot demonstrates scrape/clean quality in the meantime.
```

with:

```
## Status

Vector-store upload is implemented (`uploader/openai_store.py`) and covered
by an offline, mocked-client test suite (`tests/test_openai_uploader.py`) —
no test ever calls the real OpenAI API. The committed `articles/` snapshot
demonstrates scrape/clean quality independent of the uploader.

Sanity-check screenshot (Playground, asking the Opticlone assistant "How do
I add a YouTube video?", showing cited `Article URL:` lines):

`[screenshot placeholder — to be added after the first live run]`
```

- [ ] **Step 5: Verify the doc change didn't break anything**

Run: `.venv/Scripts/pytest -q`
Expected: `34 passed`

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: describe the real OpenAI uploader in README, un-stub Status"
```

---

### Task 10: Document the staged live-verification rollout (no live API calls performed)

**Files:**
- Modify: `README.md`

**Interfaces:**
- No code interfaces. This task adds documentation only, and its review must confirm it does not introduce, suggest running, or perform any call to the real OpenAI API — it describes a manual procedure for the human to follow later.

- [ ] **Step 1: Add a new section to `README.md`, immediately before `## Status`**

Insert:

```
## Verifying the real uploader (do this before scaling up)

The uploader is fully covered by offline tests, but has intentionally never
been run against the real OpenAI API as part of this build — only you, with
your own API key and budget, should decide when that happens. Recommended
order, since OpenAI usage is billed:

1. Confirm `.venv/Scripts/pytest -v` is fully green first.
2. Run locally with a tiny scope to exercise the real path end-to-end at
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
3. Run again locally with the same small `ARTICLE_LIMIT` to confirm a
   no-change second run logs `files embedded=0` (nothing re-uploaded).
4. Only after both of those succeed, raise `ARTICLE_LIMIT` back to 50 (or
   unset it) for a full local run, then follow `docs/deployment.md` to set
   the three OpenAI values as Fly secrets and redeploy the scheduled Machine.

Treat any failure in steps 2-3 as a stopping point to fix and re-test
offline first (adding a case to `tests/test_openai_uploader.py` if it
reveals a gap in the mocked coverage) rather than immediately retrying
against the live API.
```

- [ ] **Step 2: Run the full suite one final time**

Run: `.venv/Scripts/pytest -q`
Expected: `34 passed`

- [ ] **Step 3: Confirm no task in this plan added a live API call**

Run: `grep -rn "OpenAI(" uploader/ main.py` and confirm the only non-test construction site is the `client or OpenAI(api_key=api_key)` line in `uploader/openai_store.py`'s `__init__` (a client is *constructed*, which makes no network call by itself — `OpenAI()` is lazy). Confirm no file under `tests/` constructs a real `OpenAI(...)` client or omits injecting `client=`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the staged live-verification rollout for the real uploader"
```
