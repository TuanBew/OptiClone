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
