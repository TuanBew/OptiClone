import json
import os

import responses

from scraper.zendesk import ZENDESK_ARTICLES_URL, fetch_articles

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


@responses.activate
def test_fetch_articles_paginates_and_filters_drafts():
    page1 = load_fixture("zendesk_page_1.json")
    page2 = load_fixture("zendesk_page_2.json")
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page1, status=200)
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page2, status=200)

    articles = fetch_articles()

    assert [a["id"] for a in articles] == [1, 3]


@responses.activate
def test_fetch_articles_respects_limit_without_fetching_next_page():
    page1 = load_fixture("zendesk_page_1.json")
    responses.add(responses.GET, ZENDESK_ARTICLES_URL, json=page1, status=200)

    articles = fetch_articles(limit=1)

    assert len(articles) == 1
    assert articles[0]["id"] == 1


@responses.activate
def test_fetch_articles_with_zero_limit_returns_empty_without_request():
    # No responses registered: any HTTP call would raise ConnectionError,
    # proving the early return happens before pagination starts.
    articles = fetch_articles(limit=0)

    assert articles == []
