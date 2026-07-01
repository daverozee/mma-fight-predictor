from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote_plus, urlencode, urlparse
import json
import re
import urllib.request

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

POSITIVE_TERMS = {
    "champion",
    "wins",
    "win streak",
    "dominant",
    "impressive",
    "knockout",
    "submission",
    "favored",
    "favorite",
    "healthy",
    "ready",
    "ranked",
    "contender",
    "title shot",
    "upset win",
    "returns",
}

NEGATIVE_TERMS = {
    "loss",
    "loses",
    "lost",
    "injury",
    "injured",
    "suspended",
    "arrested",
    "withdraws",
    "withdrawal",
    "missed weight",
    "upset loss",
    "decline",
    "struggles",
    "out",
}

SearchFn = Callable[[str, str, str, int], list[dict[str, object]]]


def sample_matchup_sentiment(
    fighter_a_name: str,
    fighter_b_name: str,
    api_key: str | None,
    engine_id: str | None,
    results_per_fighter: int = 5,
    search_fn: SearchFn | None = None,
) -> dict[str, object]:
    if not api_key or not engine_id:
        return {
            "requested": True,
            "available": False,
            "status": "not_configured",
            "summary": "Online pulse was not available for this matchup.",
        }

    search = search_fn or google_search
    try:
        fighter_a = sample_fighter_sentiment(
            fighter_a_name,
            api_key,
            engine_id,
            results_per_fighter,
            search,
        )
        fighter_b = sample_fighter_sentiment(
            fighter_b_name,
            api_key,
            engine_id,
            results_per_fighter,
            search,
        )
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return {
            "requested": True,
            "available": False,
            "status": "error",
            "summary": "Online pulse was not available for this matchup.",
        }

    sample_size = fighter_a["sample_size"] + fighter_b["sample_size"]
    if sample_size == 0:
        return {
            "requested": True,
            "available": False,
            "status": "empty",
            "summary": "Online pulse was not available for this matchup.",
        }

    edge = sentiment_edge(fighter_a, fighter_b)
    summary = sentiment_summary(edge, fighter_a_name, fighter_b_name)
    return {
        "requested": True,
        "available": True,
        "status": "ready",
        "source_label": "Search sample",
        "sample_size": sample_size,
        "fighter_a": fighter_a,
        "fighter_b": fighter_b,
        "edge": edge,
        "summary": summary,
    }


def search_fighter_article_links(
    fighter_name: str,
    api_key: str | None,
    engine_id: str | None,
    limit: int = 3,
    search_fn: SearchFn | None = None,
) -> dict[str, object]:
    if not api_key or not engine_id:
        return {"available": False, "status": "not_configured", "articles": []}

    search = search_fn or google_search
    try:
        items = search(
            api_key,
            engine_id,
            f'"{fighter_name}" MMA fighter news fight',
            max(3, limit),
        )
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"available": False, "status": "error", "articles": []}

    articles = article_links_from_items(items, limit)
    return {
        "available": bool(articles),
        "status": "ready" if articles else "empty",
        "articles": articles,
    }


def fallback_fighter_media_links(fighter_name: str, limit: int = 3) -> list[dict[str, str]]:
    encoded = quote_plus(f'"{fighter_name}" MMA')
    name_only = quote_plus(fighter_name)
    candidates = [
        {
            "title": f"{fighter_name} MMA news",
            "url": f"https://news.google.com/search?q={encoded}",
            "source": "Google News",
            "snippet": "Current news coverage, fight-week updates, interviews, and recaps.",
        },
        {
            "title": f"{fighter_name} coverage on MMA Fighting",
            "url": f"https://www.mmafighting.com/search?q={encoded}",
            "source": "MMA Fighting",
            "snippet": "Editorial coverage, event previews, post-fight analysis, and media notes.",
        },
        {
            "title": f"{fighter_name} search on Sherdog",
            "url": f"https://www.sherdog.com/search?SearchTxt={name_only}",
            "source": "Sherdog",
            "snippet": "Fighter news, bout records, interviews, and profile references.",
        },
        {
            "title": f"{fighter_name} MMA headlines",
            "url": f"https://www.google.com/search?q={encoded}+fighter+news",
            "source": "Google Search",
            "snippet": "Broad public search results for recent fighter coverage.",
        },
    ]
    return candidates[: max(0, limit)]


def article_links_from_items(items: list[dict[str, object]], limit: int = 3) -> list[dict[str, str]]:
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in items:
        url = clean_text(item.get("link") or item.get("formattedUrl"))
        title = clean_text(item.get("title"))
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)
        articles.append(
            {
                "title": title,
                "url": url,
                "source": source_label(url),
                "snippet": clean_text(item.get("snippet")),
            }
        )
        if len(articles) >= limit:
            break
    return articles


def sample_fighter_sentiment(
    fighter_name: str,
    api_key: str,
    engine_id: str,
    results_per_fighter: int,
    search_fn: SearchFn,
) -> dict[str, object]:
    query = f'"{fighter_name}" MMA UFC fight news odds'
    items = search_fn(api_key, engine_id, query, results_per_fighter)
    scored_items = [score_search_item(item) for item in items]
    scored_items = [item for item in scored_items if item["source"]]
    if not scored_items:
        score = 0.0
    else:
        score = round(sum(item["score"] for item in scored_items) / len(scored_items), 3)
    sources = sorted({item["source"] for item in scored_items})
    return {
        "name": fighter_name,
        "score": score,
        "label": sentiment_label(score),
        "sample_size": len(scored_items),
        "sources": sources[:6],
    }


def google_search(api_key: str, engine_id: str, query: str, results_per_fighter: int) -> list[dict]:
    params = {
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": max(1, min(results_per_fighter, 10)),
    }
    request = urllib.request.Request(
        f"{GOOGLE_CSE_ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": "mma-fight-predictor/0.1 (sentiment sampler)"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("items", [])


def score_search_item(item: dict[str, object]) -> dict[str, object]:
    title = clean_text(item.get("title"))
    snippet = clean_text(item.get("snippet"))
    link = clean_text(item.get("link") or item.get("formattedUrl"))
    text = f"{title} {snippet}"
    return {
        "source": source_label(link),
        "score": sentiment_score(text),
    }


def sentiment_score(text: str) -> float:
    normalized = normalize_text(text)
    positive = count_terms(normalized, POSITIVE_TERMS)
    negative = count_terms(normalized, NEGATIVE_TERMS)
    total = positive + negative
    if total == 0:
        return 0.0
    return round((positive - negative) / total, 3)


def count_terms(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def sentiment_edge(fighter_a: dict[str, object], fighter_b: dict[str, object]) -> str:
    score_a = float(fighter_a["score"])
    score_b = float(fighter_b["score"])
    if abs(score_a - score_b) < 0.08:
        return "Even"
    return str(fighter_a["name"] if score_a > score_b else fighter_b["name"])


def sentiment_summary(edge: str, fighter_a_name: str, fighter_b_name: str) -> str:
    if edge == "Even":
        return f"Recent online coverage is balanced between {fighter_a_name} and {fighter_b_name}."
    return f"Recent online coverage tilts more positive for {edge}."


def sentiment_label(score: float) -> str:
    if score >= 0.18:
        return "Positive"
    if score <= -0.18:
        return "Negative"
    return "Neutral"


def clean_text(value: object) -> str:
    return str(value or "").strip()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def source_label(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    return host or parsed.path[:40]
