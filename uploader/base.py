from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ArticleFile:
    article_id: int
    slug: str
    path: str
    content_hash: str
    url: str


class Uploader(ABC):
    @abstractmethod
    def upload(self, files: list[ArticleFile]) -> None:
        """Upload the given delta of ArticleFile entries."""
        raise NotImplementedError
