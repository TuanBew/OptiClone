import logging

from openai import OpenAI

from uploader.base import ArticleFile, Uploader

logger = logging.getLogger(__name__)


class OpenAIVectorStoreUploader(Uploader):
    def __init__(
        self,
        api_key: str,
        assistant_id: str,
        vector_store_id: str | None = None,
        client: OpenAI | None = None,
    ):
        self.assistant_id = assistant_id
        self.vector_store_id = vector_store_id
        self.client = client or OpenAI(api_key=api_key)

    def _ensure_vector_store(self) -> str:
        if self.vector_store_id:
            return self.vector_store_id
        vector_store = self.client.vector_stores.create(name="OptiClone Articles")
        self.vector_store_id = vector_store.id
        logger.warning(
            "Created new OpenAI Vector Store id=%s -- persist this as OPENAI_VECTOR_STORE_ID "
            "so future runs reuse it instead of creating a new one.",
            vector_store.id,
        )
        return self.vector_store_id

    def _attach_to_assistant(self, vector_store_id: str) -> None:
        self.client.beta.assistants.update(
            self.assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
        )

    def upload(self, files: list[ArticleFile]) -> dict[int, str]:
        if not files:
            return {}

        vector_store_id = self._ensure_vector_store()
        self._attach_to_assistant(vector_store_id)

        uploaded: dict[int, str] = {}
        files_embedded = 0
        chunks_embedded = 0

        for file in files:
            with open(file.path, "rb") as fh:
                vsf = self.client.vector_stores.files.upload_and_poll(
                    vector_store_id=vector_store_id, file=fh
                )

            uploaded[file.article_id] = vsf.id
            files_embedded += 1
            chunks_embedded += len(
                list(
                    self.client.vector_stores.files.content(
                        file_id=vsf.id, vector_store_id=vector_store_id
                    )
                )
            )

        logger.info("files embedded=%d chunks embedded=%d", files_embedded, chunks_embedded)
        return uploaded
