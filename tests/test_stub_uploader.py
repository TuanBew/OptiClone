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


def test_stub_uploader_upload_returns_file_id_passthrough_map(tmp_path):
    delta_path = str(tmp_path / "state" / "last_delta.json")
    uploader = StubUploader(delta_path=delta_path)
    files = [
        ArticleFile(article_id=1, slug="one", path="articles/one.md", content_hash="h1", url="https://x/one"),
        ArticleFile(
            article_id=2, slug="two", path="articles/two.md", content_hash="h2", url="https://x/two",
            file_id="existing_abc",
        ),
    ]

    result = uploader.upload(files)

    assert result == {1: None, 2: "existing_abc"}
