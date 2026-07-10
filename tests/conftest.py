import pytest

import main as main_module


@pytest.fixture(autouse=True)
def no_dotenv_loading(monkeypatch):
    """Prevent tests from ever reading a real local .env file.

    main.run() calls load_dotenv() unconditionally. Without this, a real
    .env on disk (e.g. left over from manual live-verification) would
    silently repopulate OPENAI_API_KEY/OPENAI_ASSISTANT_ID/OPENAI_VECTOR_STORE_ID
    even after a test explicitly unsets them via monkeypatch.delenv, since
    python-dotenv only skips keys that are still present in os.environ at
    load time. That gap let two tests fall through to the real
    OpenAIVectorStoreUploader and upload fake fixture content into the real
    vector store during a local test run.
    """
    monkeypatch.setattr(main_module, "load_dotenv", lambda *args, **kwargs: None)
