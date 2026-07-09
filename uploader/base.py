from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ArticleFile:
    article_id: int
    slug: str
    path: str
    content_hash: str
    url: str
    file_id: str | None = None


class Uploader(ABC):
    @abstractmethod
    def upload(self, files: list[ArticleFile]) -> dict[int, str]:
        """Upload the given delta of ArticleFile entries.

        Returns a mapping of article_id -> new file_id for every file
        successfully uploaded this run.
        """
        raise NotImplementedError
