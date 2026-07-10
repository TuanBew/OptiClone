import json

import pytest
import responses

import main as main_module
from uploader.openai_store import OpenAIVectorStoreUploader
from uploader.stub import StubUploader


class RecordingUploader:
    def __init__(self):
        self.received_files = []

    def upload(self, files):
        self.received_files.extend(files)
        return {f.article_id: f.file_id for f in files}


class PartialFailureUploader:
    def __init__(self, fail_article_ids):
        self.fail_article_ids = set(fail_article_ids)

    def upload(self, files):
        return {
            f.article_id: (f.file_id or "new_file_id")
            for f in files
            if f.article_id not in self.fail_article_ids
        }


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


def test_get_article_limit_defaults_to_50(monkeypatch):
    monkeypatch.delenv("ARTICLE_LIMIT", raising=False)
    assert main_module.get_article_limit() == 50


def test_get_article_limit_empty_string_means_no_limit(monkeypatch):
    monkeypatch.setenv("ARTICLE_LIMIT", "")
    assert main_module.get_article_limit() is None


def test_get_article_limit_raises_clear_error_for_non_numeric_value(monkeypatch):
    monkeypatch.setenv("ARTICLE_LIMIT", "abc")
    with pytest.raises(ValueError, match="ARTICLE_LIMIT"):
        main_module.get_article_limit()


@responses.activate
def test_run_returns_1_when_zero_articles_fetched(tmp_path, monkeypatch):
    empty_page = {"articles": [], "count": 0, "page": 1, "page_count": 1, "next_page": None}
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=empty_page, status=200)

    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(tmp_path / "articles"))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(tmp_path / "state" / "manifest.json"))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(tmp_path / "state" / "last_delta.json"))

    assert main_module.run() == 1


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


@responses.activate
def test_run_populates_file_id_for_updated_and_none_for_added(tmp_path, monkeypatch):
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=ARTICLES_PAGE_1, status=200)

    articles_dir = tmp_path / "articles"
    manifest_path = tmp_path / "state" / "manifest.json"
    delta_path = tmp_path / "state" / "last_delta.json"

    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(articles_dir))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(delta_path))
    monkeypatch.setenv("ARTICLE_LIMIT", "10")

    recorder = RecordingUploader()
    monkeypatch.setattr(main_module, "build_uploader", lambda: recorder)

    assert main_module.run() == 0
    assert len(recorder.received_files) == 1
    assert recorder.received_files[0].article_id == 1
    assert recorder.received_files[0].file_id is None

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["1"]["file_id"] = "file_existing123"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    changed_page = json.loads(json.dumps(ARTICLES_PAGE_1))
    changed_page["articles"][0]["body"] = "<h1>Article One</h1><p>Changed body text.</p>"
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=changed_page, status=200)

    recorder.received_files.clear()
    assert main_module.run() == 0
    assert len(recorder.received_files) == 1
    assert recorder.received_files[0].article_id == 1
    assert recorder.received_files[0].file_id == "file_existing123"


@responses.activate
def test_failed_update_does_not_roll_manifest_hash_forward_and_is_retried(tmp_path, monkeypatch):
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=ARTICLES_PAGE_1, status=200)

    articles_dir = tmp_path / "articles"
    manifest_path = tmp_path / "state" / "manifest.json"
    delta_path = tmp_path / "state" / "last_delta.json"
    monkeypatch.setattr(main_module, "ARTICLES_DIR", str(articles_dir))
    monkeypatch.setattr(main_module, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(main_module, "DELTA_PATH", str(delta_path))
    monkeypatch.setenv("ARTICLE_LIMIT", "10")

    succeeding_uploader = PartialFailureUploader(fail_article_ids=set())
    monkeypatch.setattr(main_module, "build_uploader", lambda: succeeding_uploader)
    assert main_module.run() == 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest_after_first_run = json.load(f)
    original_hash = manifest_after_first_run["1"]["content_hash"]

    changed_page = json.loads(json.dumps(ARTICLES_PAGE_1))
    changed_page["articles"][0]["body"] = "<h1>Article One</h1><p>Changed body text.</p>"
    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=changed_page, status=200)

    failing_uploader = PartialFailureUploader(fail_article_ids={1})
    monkeypatch.setattr(main_module, "build_uploader", lambda: failing_uploader)
    assert main_module.run() == 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest_after_failed_update = json.load(f)
    assert manifest_after_failed_update["1"]["content_hash"] == original_hash

    responses.add(responses.GET, main_module.ZENDESK_ARTICLES_URL, json=changed_page, status=200)
    succeeding_uploader_2 = PartialFailureUploader(fail_article_ids=set())
    monkeypatch.setattr(main_module, "build_uploader", lambda: succeeding_uploader_2)
    assert main_module.run() == 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest_final = json.load(f)
    assert manifest_final["1"]["content_hash"] != original_hash
