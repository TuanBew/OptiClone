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
