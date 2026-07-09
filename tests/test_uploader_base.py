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
