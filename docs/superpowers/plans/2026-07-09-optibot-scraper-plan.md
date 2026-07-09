# OptiBot Scraper + Daily Delta Job Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that scrapes OptiSigns support articles from the Zendesk Help Center API, normalizes them to clean Markdown, detects the daily delta via a persisted content-hash manifest, hands the delta to a pluggable (stub) uploader, and ships as a Dockerized job for a DigitalOcean droplet cron.

**Architecture:** `scraper/zendesk.py` fetches raw article JSON; `scraper/markdown.py` converts HTML → Markdown and writes `<slug>.md`; `delta/manifest.py` classifies each article as added/updated/skipped against a persisted `state/manifest.json`; `uploader/base.py` + `uploader/stub.py` provide the pluggable upload seam (Task 2 will add a real implementation later); `main.py` orchestrates the full run and logs counts.

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4` + `markdownify`, `python-dotenv`, `pytest` + `responses` (test-only), Docker, DigitalOcean Droplet + cron.

## Global Constraints

- Python 3.11+. Dependencies pinned in `requirements.txt` (runtime) / `requirements-dev.txt` (test-only: `pytest`, `responses`).
- Do NOT add the `openai` SDK in this build — reserved for Task 2.
- No secrets hard-coded anywhere. All config read via `os.environ`; `.env.sample` documents placeholders only.
- All automated tests mock Zendesk HTTP via the `responses` library — no live network calls in `pytest`.
- `docker run <image>` must run once and exit 0, with or without `OPENAI_API_KEY` set.
- `ARTICLE_LIMIT` defaults to `50` (per brainstorming decision).
- Commit directly to `main` — this is a brand-new, empty repo (Constraint 3). Keep commits small and logically scoped.
- Repo/deliverables must never be named or reference `optisigns*`.
- Manifest schema: `article_id (str) → {slug, content_hash, updated_at, file_id: null}`. `file_id` stays `null` in this build (reserved for Task 2).
- Content hash is computed over the **converted Markdown body only** (not front-matter, which contains the volatile `updated_at` field) — this is what makes hash comparisons stable across metadata-only touches.

---

### Task 1: Project scaffold & tooling

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `.env.sample`
- Create: `scraper/__init__.py`
- Create: `delta/__init__.py`
- Create: `uploader/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: package directories `scraper/`, `delta/`, `uploader/`, `tests/` that later tasks add modules into.

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.32.3
beautifulsoup4==4.12.3
markdownify==0.13.1
python-dotenv==1.0.1
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
responses==0.25.3
```

- [ ] **Step 3: Create a virtualenv and install dev dependencies**

Run: `python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt` (Windows Git Bash) or `.venv/bin/pip install -r requirements-dev.txt` (Linux/Mac)
Expected: all packages install without error. If a pinned version is unavailable, bump it to the nearest available compatible release and update the requirements file accordingly.

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
state/
logs/
```

- [ ] **Step 5: Create `.env.sample`**

```
# Reserved for Task 2 (OpenAI Vector Store upload) — unused by the stub uploader in this build.
OPENAI_API_KEY=

# Optional cap on how many published articles to pull per run. Defaults to 50 if unset.
ARTICLE_LIMIT=50
```

- [ ] **Step 6: Create empty package `__init__.py` files**

Create each of these as an empty file:
- `scraper/__init__.py`
- `delta/__init__.py`
- `uploader/__init__.py`
- `tests/__init__.py`

- [ ] **Step 7: Verify a clean pytest baseline**

Run: `.venv/Scripts/pytest` (or `.venv/bin/pytest`)
Expected: `no tests ran` (or `collected 0 items`), exit code 0. No import errors.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore .env.sample scraper/__init__.py delta/__init__.py uploader/__init__.py tests/__init__.py
git commit -m "chore: scaffold project structure and pinned dependencies"
```

---

### Task 2: Zendesk API client

**Files:**
- Create: `scraper/zendesk.py`
- Create: `tests/fixtures/zendesk_page_1.json`
- Create: `tests/fixtures/zendesk_page_2.json`
- Test: `tests/test_zendesk.py`

**Interfaces:**
- Produces: `ZENDESK_ARTICLES_URL: str`, `fetch_articles(limit: int | None = None, session: requests.Session | None = None) -> list[dict]` — pages through the Help Center API following `next_page` until exhausted or `limit` reached; filters out `draft: True` articles; returns raw Zendesk article dicts.

- [ ] **Step 1: Create fixture `tests/fixtures/zendesk_page_1.json`**

```json
{
  "articles": [
    {
      "id": 1,
      "title": "Article One",
      "name": "Article One",
      "body": "<h1>Heading</h1><p>Body text with <a href=\"/hc/en-us/articles/2-two\">a link</a>.</p>",
      "html_url": "https://support.optisigns.com/hc/en-us/articles/1-article-one",
      "section_id": 100,
      "locale": "en-us",
      "draft": false,
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-02T00:00:00Z",
      "edited_at": "2025-01-02T00:00:00Z",
      "label_names": []
    },
    {
      "id": 2,
      "title": "Draft Article",
      "name": "Draft Article",
      "body": "<p>Should be excluded</p>",
      "html_url": "https://support.optisigns.com/hc/en-us/articles/2-draft-article",
      "section_id": 100,
      "locale": "en-us",
      "draft": true,
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-02T00:00:00Z",
      "edited_at": "2025-01-02T00:00:00Z",
      "label_names": []
    }
  ],
  "count": 3,
  "page": 1,
  "page_count": 2,
  "next_page": "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100&page=2"
}
```

- [ ] **Step 2: Create fixture `tests/fixtures/zendesk_page_2.json`**

```json
{
  "articles": [
    {
      "id": 3,
      "title": "Article Three",
      "name": "Article Three",
      "body": "<h2>Sub</h2><pre><code>print('hi')</code></pre>",
      "html_url": "https://support.optisigns.com/hc/en-us/articles/3-article-three",
      "section_id": 100,
      "locale": "en-us",
      "draft": false,
      "created_at": "2025-01-03T00:00:00Z",
      "updated_at": "2025-01-04T00:00:00Z",
      "edited_at": "2025-01-04T00:00:00Z",
      "label_names": []
    }
  ],
  "count": 3,
  "page": 2,
  "page_count": 2,
  "next_page": null
}
```

- [ ] **Step 3: Write the failing tests in `tests/test_zendesk.py`**

```python
import json
import os

import responses

from scraper.zendesk import ZENDESK_ARTICLES_URL, fetch_articles

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


@responses.activate
def test_fetch_articles_paginates_and_filters_drafts():
    page1 = load_fixture("zendesk_page_1.json")
    page2 = load_fixture("zendesk_page_2.json")
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page1, status=200)
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page2, status=200)

    articles = fetch_articles()

    assert [a["id"] for a in articles] == [1, 3]


@responses.activate
def test_fetch_articles_respects_limit_without_fetching_next_page():
    page1 = load_fixture("zendesk_page_1.json")
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page1, status=200)

    articles = fetch_articles(limit=1)

    assert len(articles) == 1
    assert articles[0]["id"] == 1
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_zendesk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.zendesk'`

- [ ] **Step 5: Implement `scraper/zendesk.py`**

```python
import requests

ZENDESK_ARTICLES_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"


def fetch_articles(limit: int | None = None, session: requests.Session | None = None) -> list[dict]:
    """Fetch published (non-draft) articles from the Zendesk Help Center API.

    Pages through `next_page` until exhausted or `limit` is reached.
    """
    http = session or requests.Session()
    articles: list[dict] = []
    url = f"{ZENDESK_ARTICLES_URL}?per_page=100&page=1"

    while url:
        response = http.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        for article in data.get("articles", []):
            if article.get("draft"):
                continue
            articles.append(article)
            if limit is not None and len(articles) >= limit:
                return articles

        url = data.get("next_page")

    return articles
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_zendesk.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add scraper/zendesk.py tests/test_zendesk.py tests/fixtures/zendesk_page_1.json tests/fixtures/zendesk_page_2.json
git commit -m "feat: add paginated Zendesk Help Center API client"
```

---

### Task 3: Markdown normalization

**Files:**
- Create: `scraper/markdown.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Consumes: raw Zendesk article dicts as produced by `scraper.zendesk.fetch_articles` (keys: `id`, `title`, `name`, `body`, `html_url`, `updated_at`, `draft`).
- Produces:
  - `@dataclass NormalizedArticle(article_id: int, slug: str, title: str, url: str, updated_at: str, markdown: str, content_hash: str)`
  - `normalize_article(article: dict) -> NormalizedArticle`
  - `write_markdown_file(article: NormalizedArticle, output_dir: str) -> str` (returns the path written)

- [ ] **Step 1: Write the failing tests in `tests/test_markdown.py`**

```python
import os

from scraper.markdown import NormalizedArticle, normalize_article, write_markdown_file

SAMPLE_ARTICLE = {
    "id": 42,
    "title": "How to Add a YouTube Video",
    "name": "How to Add a YouTube Video",
    "html_url": "https://support.optisigns.com/hc/en-us/articles/42-how-to-add-a-youtube-video",
    "body": (
        "<script>trackPageView();</script>"
        "<h1>How to Add a YouTube Video</h1>"
        "<p>Follow these steps to add a video.</p>"
        "<h2>Steps</h2>"
        "<pre><code>opti add-video --url YOUTUBE_URL</code></pre>"
        "<p>See also <a href=\"/hc/en-us/articles/43-related-article\">this related article</a>.</p>"
        "<div class=\"article-attachments\">Attachment chrome to strip</div>"
        "<p>&nbsp;</p>"
    ),
    "updated_at": "2026-01-01T00:00:00Z",
    "draft": False,
}


def test_normalize_article_preserves_structure_and_strips_boilerplate():
    result = normalize_article(SAMPLE_ARTICLE)

    assert isinstance(result, NormalizedArticle)
    assert result.article_id == 42
    assert result.slug == "42-how-to-add-a-youtube-video"
    assert "# How to Add a YouTube Video" in result.markdown
    assert "## Steps" in result.markdown
    assert "```" in result.markdown
    assert "opti add-video --url YOUTUBE_URL" in result.markdown
    assert "/hc/en-us/articles/43-related-article" in result.markdown
    assert "Attachment chrome to strip" not in result.markdown
    assert "trackPageView" not in result.markdown
    assert (
        "Article URL: https://support.optisigns.com/hc/en-us/articles/42-how-to-add-a-youtube-video"
        in result.markdown
    )


def test_content_hash_ignores_updated_at_but_reflects_body_changes():
    same_body_later_timestamp = dict(SAMPLE_ARTICLE, updated_at="2026-06-01T00:00:00Z")
    result_a = normalize_article(SAMPLE_ARTICLE)
    result_b = normalize_article(same_body_later_timestamp)
    assert result_a.content_hash == result_b.content_hash

    changed_body = dict(SAMPLE_ARTICLE, body="<h1>Different</h1><p>Changed content.</p>")
    result_c = normalize_article(changed_body)
    assert result_c.content_hash != result_a.content_hash


def test_write_markdown_file_writes_expected_path(tmp_path):
    article = normalize_article(SAMPLE_ARTICLE)
    output_dir = str(tmp_path / "articles")

    path = write_markdown_file(article, output_dir)

    assert path == os.path.join(output_dir, "42-how-to-add-a-youtube-video.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert content == article.markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.markdown'`

- [ ] **Step 3: Implement `scraper/markdown.py`**

```python
import hashlib
import os
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert

STRIP_TAGS = ["script", "style", "nav", "iframe"]
STRIP_CLASS_KEYWORDS = [
    "article-attachments",
    "promoted-articles",
    "table-of-contents",
    "callout-nav",
    "meta-info",
]


@dataclass
class NormalizedArticle:
    article_id: int
    slug: str
    title: str
    url: str
    updated_at: str
    markdown: str
    content_hash: str


def _is_effectively_empty(tag) -> bool:
    if tag.get_text(strip=True):
        return False
    if tag.find(["img", "a", "pre", "code", "table"]):
        return False
    return True


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all(True):
        class_str = " ".join(tag.get("class") or [])
        if any(keyword in class_str for keyword in STRIP_CLASS_KEYWORDS):
            tag.decompose()

    for tag in soup.find_all(["div", "p", "span"]):
        if _is_effectively_empty(tag):
            tag.decompose()


def html_to_markdown(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    _strip_boilerplate(soup)
    markdown = md_convert(str(soup), heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


def slugify_url(html_url: str) -> str:
    return html_url.rstrip("/").split("/")[-1]


def render_file_content(article: dict, body_markdown: str) -> str:
    title = article.get("title") or article.get("name") or ""
    front_matter = (
        "---\n"
        f"title: {title}\n"
        f"article_id: {article['id']}\n"
        f"updated_at: {article.get('updated_at', '')}\n"
        "---\n"
    )
    url_line = f"Article URL: {article['html_url']}\n"
    return f"{front_matter}\n{url_line}\n{body_markdown}\n"


def normalize_article(article: dict) -> NormalizedArticle:
    body_markdown = html_to_markdown(article.get("body") or "")
    slug = slugify_url(article["html_url"])
    file_content = render_file_content(article, body_markdown)
    content_hash = hashlib.sha256(body_markdown.encode("utf-8")).hexdigest()

    return NormalizedArticle(
        article_id=article["id"],
        slug=slug,
        title=article.get("title") or article.get("name") or "",
        url=article["html_url"],
        updated_at=article.get("updated_at", ""),
        markdown=file_content,
        content_hash=content_hash,
    )


def write_markdown_file(article: NormalizedArticle, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{article.slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(article.markdown)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_markdown.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/markdown.py tests/test_markdown.py
git commit -m "feat: add HTML-to-Markdown normalization with boilerplate stripping"
```

---

### Task 4: Manifest & delta classification

**Files:**
- Create: `delta/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `scraper.markdown.NormalizedArticle` (fields: `article_id`, `slug`, `content_hash`, `updated_at`).
- Produces:
  - `load_manifest(path: str) -> dict`
  - `save_manifest(manifest: dict, path: str) -> None` (atomic write)
  - `@dataclass DeltaResult(added: list[NormalizedArticle], updated: list[NormalizedArticle], skipped_count: int)`
  - `classify(normalized_articles: list[NormalizedArticle], manifest: dict) -> DeltaResult`
  - `update_manifest_entries(manifest: dict, articles: list[NormalizedArticle]) -> dict`

- [ ] **Step 1: Write the failing tests in `tests/test_manifest.py`**

```python
from delta.manifest import (
    classify,
    load_manifest,
    save_manifest,
    update_manifest_entries,
)
from scraper.markdown import NormalizedArticle


def make_article(article_id, slug, content_hash, updated_at="2026-01-01T00:00:00Z"):
    return NormalizedArticle(
        article_id=article_id,
        slug=slug,
        title=slug,
        url=f"https://support.optisigns.com/hc/en-us/articles/{slug}",
        updated_at=updated_at,
        markdown=f"# {slug}",
        content_hash=content_hash,
    )


def test_classify_added_updated_skipped():
    manifest = {
        "1": {"slug": "one", "content_hash": "hash1", "updated_at": "old", "file_id": None},
        "2": {"slug": "two", "content_hash": "hash2-old", "updated_at": "old", "file_id": "file_abc"},
    }
    articles = [
        make_article(1, "one", "hash1"),
        make_article(2, "two", "hash2-new"),
        make_article(3, "three", "hash3"),
    ]

    result = classify(articles, manifest)

    assert [a.article_id for a in result.added] == [3]
    assert [a.article_id for a in result.updated] == [2]
    assert result.skipped_count == 1


def test_update_manifest_entries_preserves_file_id_and_updates_hash():
    manifest = {
        "2": {"slug": "two", "content_hash": "hash2-old", "updated_at": "old", "file_id": "file_abc"},
    }
    articles = [make_article(2, "two", "hash2-new", updated_at="2026-02-01T00:00:00Z")]

    new_manifest = update_manifest_entries(manifest, articles)

    assert new_manifest["2"]["content_hash"] == "hash2-new"
    assert new_manifest["2"]["file_id"] == "file_abc"
    assert new_manifest["2"]["updated_at"] == "2026-02-01T00:00:00Z"


def test_update_manifest_entries_adds_new_entry_with_null_file_id():
    new_manifest = update_manifest_entries({}, [make_article(3, "three", "hash3")])
    assert new_manifest["3"] == {
        "slug": "three",
        "content_hash": "hash3",
        "updated_at": "2026-01-01T00:00:00Z",
        "file_id": None,
    }


def test_save_and_load_manifest_roundtrip(tmp_path):
    path = str(tmp_path / "state" / "manifest.json")
    manifest = {"1": {"slug": "one", "content_hash": "hash1", "updated_at": "t", "file_id": None}}

    save_manifest(manifest, path)
    loaded = load_manifest(path)

    assert loaded == manifest


def test_load_manifest_missing_file_returns_empty_dict(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    assert load_manifest(path) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'delta.manifest'`

- [ ] **Step 3: Implement `delta/manifest.py`**

```python
import json
import os
import tempfile
from dataclasses import dataclass

from scraper.markdown import NormalizedArticle


@dataclass
class DeltaResult:
    added: list
    updated: list
    skipped_count: int


def load_manifest(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: dict, path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".manifest_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def classify(normalized_articles: list, manifest: dict) -> DeltaResult:
    added: list[NormalizedArticle] = []
    updated: list[NormalizedArticle] = []
    skipped_count = 0

    for article in normalized_articles:
        existing = manifest.get(str(article.article_id))
        if existing is None:
            added.append(article)
        elif existing.get("content_hash") != article.content_hash:
            updated.append(article)
        else:
            skipped_count += 1

    return DeltaResult(added=added, updated=updated, skipped_count=skipped_count)


def update_manifest_entries(manifest: dict, articles: list) -> dict:
    new_manifest = dict(manifest)
    for article in articles:
        key = str(article.article_id)
        existing_file_id = new_manifest.get(key, {}).get("file_id")
        new_manifest[key] = {
            "slug": article.slug,
            "content_hash": article.content_hash,
            "updated_at": article.updated_at,
            "file_id": existing_file_id,
        }
    return new_manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_manifest.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add delta/manifest.py tests/test_manifest.py
git commit -m "feat: add manifest persistence and added/updated/skipped delta classification"
```

---

### Task 5: Uploader interface + stub

**Files:**
- Create: `uploader/base.py`
- Create: `uploader/stub.py`
- Test: `tests/test_stub_uploader.py`

**Interfaces:**
- Produces:
  - `@dataclass ArticleFile(article_id: int, slug: str, path: str, content_hash: str, url: str)`
  - `class Uploader(ABC)` with abstract `upload(self, files: list[ArticleFile]) -> None`
  - `class StubUploader(Uploader)` with `__init__(self, delta_path: str = "state/last_delta.json")` and `upload(self, files: list[ArticleFile]) -> None` — logs each file, writes `delta_path` as JSON `{"timestamp": str, "uploaded_slugs": list[str], "uploaded_count": int, "articles": [{"article_id", "slug", "url"}]}`.

- [ ] **Step 1: Write the failing test in `tests/test_stub_uploader.py`**

```python
import json
import logging

from uploader.base import ArticleFile
from uploader.stub import StubUploader


def test_stub_uploader_logs_and_writes_delta_artifact(tmp_path, caplog):
    delta_path = str(tmp_path / "state" / "last_delta.json")
    uploader = StubUploader(delta_path=delta_path)
    files = [
        ArticleFile(article_id=1, slug="one", path="articles/one.md", content_hash="h1", url="https://x/one"),
        ArticleFile(article_id=2, slug="two", path="articles/two.md", content_hash="h2", url="https://x/two"),
    ]

    with caplog.at_level(logging.INFO):
        uploader.upload(files)

    assert "one" in caplog.text
    assert "two" in caplog.text

    with open(delta_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["uploaded_count"] == 2
    assert set(payload["uploaded_slugs"]) == {"one", "two"}
    assert "timestamp" in payload
    assert {"article_id": 1, "slug": "one", "url": "https://x/one"} in payload["articles"]


def test_stub_uploader_handles_empty_delta(tmp_path):
    delta_path = str(tmp_path / "state" / "last_delta.json")
    uploader = StubUploader(delta_path=delta_path)

    uploader.upload([])

    with open(delta_path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["uploaded_count"] == 0
    assert payload["uploaded_slugs"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_stub_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'uploader.base'`

- [ ] **Step 3: Implement `uploader/base.py`**

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


class Uploader(ABC):
    @abstractmethod
    def upload(self, files: list) -> None:
        """Upload the given delta of ArticleFile entries."""
        raise NotImplementedError
```

- [ ] **Step 4: Implement `uploader/stub.py`**

```python
import json
import logging
import os
from datetime import datetime, timezone

from uploader.base import ArticleFile, Uploader

logger = logging.getLogger(__name__)


class StubUploader(Uploader):
    def __init__(self, delta_path: str = "state/last_delta.json"):
        self.delta_path = delta_path

    def upload(self, files: list) -> None:
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_stub_uploader.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add uploader/base.py uploader/stub.py tests/test_stub_uploader.py
git commit -m "feat: add pluggable Uploader interface and StubUploader"
```

---

### Task 6: main.py orchestrator + end-to-end test

**Files:**
- Create: `main.py`
- Test: `tests/test_main_e2e.py`

**Interfaces:**
- Consumes: `scraper.zendesk.fetch_articles`, `scraper.markdown.normalize_article`, `scraper.markdown.write_markdown_file`, `delta.manifest.load_manifest`, `delta.manifest.save_manifest`, `delta.manifest.classify`, `delta.manifest.update_manifest_entries`, `uploader.base.ArticleFile`, `uploader.stub.StubUploader`.
- Produces: module-level constants `ARTICLES_DIR`, `MANIFEST_PATH`, `DELTA_PATH` (monkeypatchable by tests); `get_article_limit() -> int | None`; `run() -> int` (0 on success, 1 if zero articles fetched).

- [ ] **Step 1: Write the failing end-to-end test in `tests/test_main_e2e.py`**

```python
import json

import responses

import main as main_module

ARTICLES_PAGE_1 = {
    "articles": [
        {
            "id": 1,
            "title": "Article One",
            "name": "Article One",
            "body": "<h1>Article One</h1><p>Body text.</p>",
            "html_url": "https://support.optisigns.com/hc/en-us/articles/1-article-one",
            "section_id": 100,
            "locale": "en-us",
            "draft": False,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-02T00:00:00Z",
            "edited_at": "2025-01-02T00:00:00Z",
            "label_names": [],
        }
    ],
    "count": 1,
    "page": 1,
    "page_count": 1,
    "next_page": None,
}


@responses.activate
def test_first_run_added_second_run_all_skipped(tmp_path, monkeypatch):
    responses.add(
        responses.GET,
        main_module.ZENDESK_ARTICLES_URL,
        json=ARTICLES_PAGE_1,
        status=200,
    )
    responses.add(
        responses.GET,
        main_module.ZENDESK_ARTICLES_URL,
        json=ARTICLES_PAGE_1,
        status=200,
    )

    articles_dir = tmp_path / "articles"
    manifest_path = tmp_path / "state" / "manifest.json"
    delta_path = tmp_path / "state" / "last_delta.json"

    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(articles_dir))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(delta_path))
    monkeypatch.setenv("ARTICLE_LIMIT", "10")

    exit_code = main_module.run()
    assert exit_code == 0
    assert (articles_dir / "1-article-one.md").exists()

    with open(delta_path, encoding="utf-8") as f:
        first_delta = json.load(f)
    assert first_delta["uploaded_count"] == 1
    assert first_delta["uploaded_slugs"] == ["1-article-one"]

    exit_code_2 = main_module.run()
    assert exit_code_2 == 0

    with open(delta_path, encoding="utf-8") as f:
        second_delta = json.load(f)
    assert second_delta["uploaded_count"] == 0


@responses.activate
def test_run_returns_1_when_zero_articles_fetched(tmp_path, monkeypatch):
    empty_page = {"articles": [], "count": 0, "page": 1, "page_count": 1, "next_page": None}
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=empty_page, status=200)

    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(tmp_path / "articles"))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(tmp_path / "state" / "manifest.json"))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(tmp_path / "state" / "last_delta.json"))

    assert main_module.run() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/test_main_e2e.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implement `main.py`**

```python
import logging
import os
import sys

from dotenv import load_dotenv

from delta.manifest import classify, load_manifest, save_manifest, update_manifest_entries
from scraper.markdown import normalize_article, write_markdown_file
from scraper.zendesk import ZENDESK_ARTICLES_URL, fetch_articles
from uploader.base import ArticleFile
from uploader.stub import StubUploader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("optibot")

ARTICLES_DIR = "articles"
MANIFEST_PATH = "state/manifest.json"
DELTA_PATH = "state/last_delta.json"


def get_article_limit() -> int | None:
    raw = os.environ.get("ARTICLE_LIMIT", "50")
    if raw is None or raw == "":
        return None
    return int(raw)


def run() -> int:
    load_dotenv()
    limit = get_article_limit()

    logger.info("Fetching articles from Zendesk (limit=%s)...", limit)
    raw_articles = fetch_articles(limit=limit)
    if not raw_articles:
        logger.error("No articles fetched from Zendesk; aborting run.")
        return 1

    normalized = []
    for raw in raw_articles:
        try:
            article = normalize_article(raw)
            write_markdown_file(article, ARTICLES_DIR)
            normalized.append(article)
        except Exception:
            logger.warning("Failed to normalize article id=%s", raw.get("id"), exc_info=True)

    manifest = load_manifest(MANIFEST_PATH)
    delta_result = classify(normalized, manifest)

    delta_files = [
        ArticleFile(
            article_id=article.article_id,
            slug=article.slug,
            path=os.path.join(ARTICLES_DIR, f"{article.slug}.md"),
            content_hash=article.content_hash,
            url=article.url,
        )
        for article in (delta_result.added + delta_result.updated)
    ]

    uploader = StubUploader(delta_path=DELTA_PATH)
    uploader.upload(delta_files)

    new_manifest = update_manifest_entries(manifest, delta_result.added + delta_result.updated)
    save_manifest(new_manifest, MANIFEST_PATH)

    logger.info(
        "Delta complete: added=%d updated=%d skipped=%d",
        len(delta_result.added),
        len(delta_result.updated),
        delta_result.skipped_count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_main_e2e.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/pytest -v`
Expected: all tests across `tests/test_zendesk.py`, `tests/test_markdown.py`, `tests/test_manifest.py`, `tests/test_stub_uploader.py`, `tests/test_main_e2e.py` pass.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main_e2e.py
git commit -m "feat: add main.py orchestrator wiring scrape -> diff -> upload -> log"
```

---

### Task 7: Dockerfile + build/run verification

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `main.py`, `scraper/`, `delta/`, `uploader/`, `requirements.txt` (all prior tasks).
- Produces: a buildable image whose `docker run` entrypoint executes `python main.py` and exits 0.

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
tests/
docs/
state/
logs/
.env
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY scraper/ scraper/
COPY delta/ delta/
COPY uploader/ uploader/

RUN mkdir -p state logs articles

ENTRYPOINT ["python", "main.py"]
```

- [ ] **Step 3: Build the image**

Run: `docker build -t opticlone .`
Expected: build completes successfully. If the `docker` CLI is unavailable in this environment, note that explicitly rather than skipping silently — this step must be verified once Docker is available.

- [ ] **Step 4: Run the image without an OpenAI key, with the state/logs volumes mounted**

Run (from repo root): `mkdir -p /tmp/opticlone_state /tmp/opticlone_logs && docker run --rm -v /tmp/opticlone_state:/app/state -v /tmp/opticlone_logs:/app/logs opticlone; echo "exit code: $?"`
Expected: `exit code: 0`; `/tmp/opticlone_state/manifest.json` exists afterward.

- [ ] **Step 5: Run the image a second time against the same mounted state, confirming idempotent skip behavior**

Run: `docker run --rm -v /tmp/opticlone_state:/app/state -v /tmp/opticlone_logs:/app/logs opticlone; echo "exit code: $?"`
Expected: `exit code: 0`; log output shows `added=0 updated=0 skipped=N` where N matches the article count from the first run.

- [ ] **Step 6: Run the image with `-e OPENAI_API_KEY=...` to confirm passing the reserved var doesn't break anything**

Run: `docker run --rm -e OPENAI_API_KEY=sk-fake-placeholder -v /tmp/opticlone_state:/app/state -v /tmp/opticlone_logs:/app/logs opticlone; echo "exit code: $?"`
Expected: `exit code: 0`

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: add Dockerfile and .dockerignore for containerized daily job"
```

---

### Task 8: Generate committed `articles/` snapshot

**Files:**
- Create: `articles/*.md` (generated output, committed as evidence of scrape quality)

**Interfaces:**
- Consumes: `main.py` `run()` against the live Zendesk API (not mocked — this is a one-time real content-generation step, not a unit test).

- [ ] **Step 1: Run the scraper for real against the live Zendesk API**

Run: `.venv/Scripts/python main.py` (uses the default `ARTICLE_LIMIT=50` from `.env.sample`/environment)
Expected: exits 0; `articles/` contains at least 30 `<slug>.md` files; `state/manifest.json` and `state/last_delta.json` are created (these stay gitignored per `.gitignore`).

- [ ] **Step 2: Spot-check a handful of generated files**

Open 2-3 files under `articles/` and confirm: a top-of-file `Article URL:` line, preserved headings (`#`/`##`), no leftover `<script>`/nav chrome, and readable Markdown body.

- [ ] **Step 3: Confirm the count clears the rubric bar**

Run: `ls articles | wc -l` (or `Get-ChildItem articles | Measure-Object | Select -Expand Count` in PowerShell)
Expected: ≥ 30.

- [ ] **Step 4: Commit the snapshot**

```bash
git add articles/
git commit -m "feat: commit initial scraped articles/ snapshot as scrape-quality evidence"
```

---

### Task 9: README + deployment docs

**Files:**
- Create: `README.md`
- Create: `docs/deployment.md`

**Interfaces:**
- Consumes: nothing (documentation only); references file paths and commands established in Tasks 1-8.

- [ ] **Step 1: Create `docs/deployment.md`**

```markdown
# Deployment: DigitalOcean Droplet + Daily Cron

1. Create a small DigitalOcean Droplet from the "Docker" marketplace image (Ubuntu + Docker pre-installed).
2. SSH in and clone this repo:
   ```
   git clone <repo-url> /root/opticlone
   cd /root/opticlone
   ```
3. Create `/root/opticlone/.env` from `.env.sample` (leave `OPENAI_API_KEY` blank; this build's stub uploader needs none).
4. Build the image once:
   ```
   docker build -t opticlone .
   ```
5. Create the persistent state/log directories on the droplet's disk:
   ```
   mkdir -p /root/opticlone/state /root/opticlone/logs
   ```
6. Add a daily cron entry (`crontab -e`):
   ```
   0 6 * * * cd /root/opticlone && docker run --rm --env-file .env \
     -v /root/opticlone/state:/app/state -v /root/opticlone/logs:/app/logs opticlone \
     >> /root/opticlone/logs/cron-$(date +\%F).log 2>&1
   ```
   The bind-mounted `state/` directory is what makes delta detection work across runs — the container itself is fully ephemeral, but the manifest lives on the droplet's disk between invocations.

## Viewing job logs

SSH into the droplet and tail the latest log:
```
ssh root@<droplet-ip>
tail -f /root/opticlone/logs/cron-$(date +%F).log
```
Or inspect the last run's summary directly:
```
cat /root/opticlone/state/last_delta.json
```
```

- [ ] **Step 2: Create `README.md`**

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/deployment.md
git commit -m "docs: add README and DigitalOcean deployment guide"
```

---

### Task 10: Final verification pass

**Files:** none created — verification only.

**Interfaces:** none.

- [ ] **Step 1: Run the full test suite one more time**

Run: `.venv/Scripts/pytest -v`
Expected: all tests pass, zero failures/errors.

- [ ] **Step 2: Confirm no secrets are present anywhere**

Run: `grep -rniE "sk-[a-zA-Z0-9]{10,}|api[_-]?key\s*=\s*['\"][^'\"]+['\"]" --include="*.py" --include="*.env*" .`
Expected: no matches (aside from the empty placeholder in `.env.sample`).

- [ ] **Step 3: Confirm `.gitignore` is keeping `state/`, `logs/`, `.env` out of git**

Run: `git status --porcelain`
Expected: no `state/`, `logs/`, or `.env` entries listed as untracked-but-should-be-tracked; working tree otherwise clean after Task 9's commit.

- [ ] **Step 4: Confirm the committed `articles/` snapshot count**

Run: `ls articles | wc -l`
Expected: ≥ 30.

- [ ] **Step 5: Review `git log` for clean, logically-scoped commit history**

Run: `git log --oneline`
Expected: one commit per task (scaffold, Zendesk client, Markdown normalization, manifest/delta, uploader, main.py, Dockerfile, articles snapshot, docs) — no giant catch-all commits.

- [ ] **Step 6: Summarize completion against the design's success criteria**

Confirm each checkbox in `docs/superpowers/specs/2026-07-09-optibot-scraper-design.md`'s success criteria (scrape, uploader seam, delta job, DevOps, testing, security, quality) is satisfied, and report this to the user.
