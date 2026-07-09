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
