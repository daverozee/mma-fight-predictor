from scripts.discover_social_links import score_item


def test_score_item_accepts_strong_instagram_profile_match() -> None:
    candidate = score_item(
        "Anderson Silva",
        {
            "link": "https://www.instagram.com/spiderandersonsilva/",
            "title": "Anderson Silva (@spiderandersonsilva) Instagram photos and videos",
            "snippet": "Official Instagram of UFC and MMA fighter Anderson Silva.",
        },
        'site:instagram.com "Anderson Silva" MMA',
    )

    assert candidate is not None
    assert candidate.url == "https://www.instagram.com/spiderandersonsilva/"
    assert candidate.score >= 72


def test_score_item_rejects_instagram_post_urls() -> None:
    candidate = score_item(
        "Anderson Silva",
        {
            "link": "https://www.instagram.com/p/ABC123/",
            "title": "Anderson Silva training clip",
            "snippet": "A post about Anderson Silva.",
        },
        'site:instagram.com "Anderson Silva" MMA',
    )

    assert candidate is None


def test_score_item_rejects_weak_fan_page_match() -> None:
    candidate = score_item(
        "Ciryl Gane",
        {
            "link": "https://www.instagram.com/mma_highlights_daily/",
            "title": "MMA highlights and fan edits",
            "snippet": "Fan page with a reel mentioning Ciryl Gane.",
        },
        'site:instagram.com "Ciryl Gane" MMA',
    )

    assert candidate is None
