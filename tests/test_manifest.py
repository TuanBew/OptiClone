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
