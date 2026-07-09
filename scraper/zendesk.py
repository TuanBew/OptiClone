import requests

ZENDESK_ARTICLES_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"


def fetch_articles(limit: int | None = None, session: requests.Session | None = None) -> list[dict]:
    """Fetch published (non-draft) articles from the Zendesk Help Center API.

    Pages through `next_page` until exhausted or `limit` is reached.
    """
    if limit is not None and limit <= 0:
        return []

    http = session or requests.Session()
    articles: list[dict] = []
    url = f"{ZENDESK_ARTICLES_URL}?per_page=100&page=1"

    while url:
        response = http.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        for article in data.get("articles", []):
            if article.get("draft"):
                continue
            articles.append(article)
            if limit is not None and len(articles) >= limit:
                return articles

        url = data.get("next_page")

    return articles
