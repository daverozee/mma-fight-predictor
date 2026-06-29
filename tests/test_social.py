from app.social import normalize_instagram_url


def test_normalize_instagram_url_accepts_handles_and_urls() -> None:
    assert normalize_instagram_url("@fighter.name") == "https://www.instagram.com/fighter.name/"
    assert normalize_instagram_url("fighter_name") == "https://www.instagram.com/fighter_name/"
    assert (
        normalize_instagram_url("https://www.instagram.com/fighter_name/?hl=en")
        == "https://www.instagram.com/fighter_name/"
    )


def test_normalize_instagram_url_rejects_non_instagram_urls() -> None:
    assert normalize_instagram_url("https://example.com/fighter") is None
    assert normalize_instagram_url("not a handle") is None
    assert normalize_instagram_url("https://www.instagram.com/p/ABC123/") is None
