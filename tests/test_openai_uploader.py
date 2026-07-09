from unittest.mock import MagicMock

from uploader.base import ArticleFile
from uploader.openai_store import OpenAIVectorStoreUploader


def make_article_file(tmp_path, article_id=1, slug="one", file_id=None, body="# One\n"):
    path = tmp_path / f"{slug}.md"
    path.write_text(body, encoding="utf-8")
    return ArticleFile(
        article_id=article_id,
        slug=slug,
        path=str(path),
        content_hash="hash1",
        url=f"https://support.optisigns.com/hc/en-us/articles/{slug}",
        file_id=file_id,
    )


def make_mock_client():
    client = MagicMock()
    client.vector_stores.files.upload_and_poll.return_value = MagicMock(
        id="file_new1", status="completed", last_error=None
    )
    client.vector_stores.files.content.return_value = [MagicMock(), MagicMock()]
    return client


def test_upload_new_article_records_file_id_and_chunk_count(tmp_path):
    client = make_mock_client()
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )
    files = [make_article_file(tmp_path)]

    result = uploader.upload(files)

    assert result == {1: "file_new1"}
    client.vector_stores.create.assert_not_called()
    client.beta.assistants.update.assert_called_once_with(
        "asst_test", tool_resources={"file_search": {"vector_store_ids": ["vs_existing"]}}
    )
    _, kwargs = client.vector_stores.files.upload_and_poll.call_args
    assert kwargs["vector_store_id"] == "vs_existing"
    client.vector_stores.files.content.assert_called_once_with(
        file_id="file_new1", vector_store_id="vs_existing"
    )


def test_upload_creates_vector_store_when_none_configured(tmp_path):
    client = make_mock_client()
    client.vector_stores.create.return_value = MagicMock(id="vs_brand_new")
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id=None, client=client
    )
    files = [make_article_file(tmp_path)]

    uploader.upload(files)

    client.vector_stores.create.assert_called_once_with(name="OptiClone Articles")
    assert uploader.vector_store_id == "vs_brand_new"
    _, kwargs = client.vector_stores.files.upload_and_poll.call_args
    assert kwargs["vector_store_id"] == "vs_brand_new"


def test_upload_empty_list_makes_no_client_calls():
    client = make_mock_client()
    uploader = OpenAIVectorStoreUploader(
        api_key="sk-test", assistant_id="asst_test", vector_store_id="vs_existing", client=client
    )

    result = uploader.upload([])

    assert result == {}
    client.vector_stores.create.assert_not_called()
    client.beta.assistants.update.assert_not_called()
    client.vector_stores.files.upload_and_poll.assert_not_called()
