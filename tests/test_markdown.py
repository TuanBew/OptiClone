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
