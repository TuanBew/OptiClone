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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("optibot")

ARTICLES_DIR = "articles"
MANIFEST_PATH = "state/manifest.json"
DELTA_PATH = "state/last_delta.json"


def get_article_limit() -> int | None:
    raw = os.environ.get("ARTICLE_LIMIT", "50")
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid ARTICLE_LIMIT={raw!r}: expected an integer (or an empty string for no limit)."
        ) from exc


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


def run() -> int:
    load_dotenv()
    limit = get_article_limit()

    logger.info("Fetching articles from Zendesk (limit=%s)...", limit)
    raw_articles = fetch_articles(limit=limit)
    if not raw_articles:
        logger.error("No articles fetched from Zendesk; aborting run.")
        return 1

    normalized = []
    written_paths: dict[int, str] = {}
    for raw in raw_articles:
        try:
            article = normalize_article(raw)
            written_paths[article.article_id] = write_markdown_file(article, ARTICLES_DIR)
            normalized.append(article)
        except Exception:
            logger.warning("Failed to normalize article id=%s", raw.get("id"), exc_info=True)

    manifest = load_manifest(MANIFEST_PATH)
    delta_result = classify(normalized, manifest)

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

    logger.info(
        "Delta complete: added=%d updated=%d skipped=%d",
        len(delta_result.added),
        len(delta_result.updated),
        delta_result.skipped_count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
