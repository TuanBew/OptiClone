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
