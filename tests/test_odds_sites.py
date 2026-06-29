import json

from app.odds_sites import load_odds_sites


def test_load_odds_sites_reads_catalog(tmp_path) -> None:
    odds_path = tmp_path / "odds.json"
    odds_path.write_text(
        json.dumps(
            {
                "updated": "2026-06-29",
                "notice": "Test notice",
                "sections": [
                    {
                        "name": "Sportsbooks",
                        "summary": "Books",
                        "sites": [
                            {
                                "name": "DraftKings",
                                "url": "https://sportsbook.draftkings.com/leagues/mma/ufc",
                                "coverage": "UFC odds",
                                "region": "US",
                                "kind": "sportsbook",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    catalog = load_odds_sites(odds_path)

    assert catalog["sections"][0]["sites"][0]["name"] == "DraftKings"
