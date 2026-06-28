# MMA Data Sources

This is the working source map for the ingestion layer. Prefer licensed APIs and documented feeds first. Use scraping only after reviewing robots.txt, terms of service, rate limits, attribution requirements, and commercial-use limits.

## Recommended First Sources

| Source | Best use | Access | Notes |
| --- | --- | --- | --- |
| [BALLDONTLIE MMA API](https://www.balldontlie.io/docs) | Fighters, events, rankings, fights, fight stats, betting odds | API key; free and paid tiers | Best first integration target because it has documented MMA endpoints and a low-cost upgrade path. |
| [The Odds API](https://the-odds-api.com/sports-odds-data/mma-odds.html) | Upcoming MMA/UFC odds and historical odds | API key; free current odds, paid historical odds | Good for market-implied probability and odds movement features. Uses sport key `mma_mixed_martial_arts`. |
| [SportsDataIO MMA/UFC API](https://sportsdata.io/mma-ufc-api) | Schedules, scores, stats, odds, projections, news, images | Commercial API/free trial | Strong production candidate if budget allows. They advertise real-time coverage and a single-source MMA API. |
| [Sportradar MMA API](https://marketplace.sportradar.com/products/652fc88991cb7d6acdef2532) | UFC schedules, live results, profiles, head-to-head stats | Commercial API | Enterprise-grade feed for UFC and Dana White's Contender Series, likely overkill for the first forum demo. |
| [API-Sports MMA API](https://api-sports.io/documentation/mma/v1) | Fighters, fights, seasons, categories, odds | API key | Useful alternative API to compare coverage and pricing. |
| [Oddsmatrix UFC/MMA Data Feed](https://oddsmatrix.com/sports-leagues/ufc-mma-data-feed-api/) | Odds, schedules, results, payouts, live match stats | Commercial API | Sportsbook-oriented feed; evaluate later if odds depth becomes important. |

## Dataset Sources

| Source | Best use | Access | Notes |
| --- | --- | --- | --- |
| Kaggle UFC datasets | Historical model training and feature prototyping | Dataset download | Check each dataset license and freshness before use. Many are scraped from UFCStats. |
| [Hugging Face UFC fight datasets](https://huggingface.co/datasets/xtinkarpiu/ufc-fight-data) | Historical model training | Dataset download | Check dataset card license and upstream terms. The linked dataset describes itself as extracted from ufcstats.com. |

## Scrape Candidates Requiring Review

| Source | Best use | Risk / action |
| --- | --- | --- |
| UFCStats | Fight stats, event results, fighter pages | High-value source, but scraping should wait for terms/robots review and conservative rate limits. |
| Tapology | Upcoming cards, bout listings, fighter pages | Terms review required before scraping. Consider permission or manual import first. |
| Fight Matrix | Rankings and historical rating-style signals | Terms review required. Rankings are proprietary; avoid copying wholesale without permission. |
| Sherdog | Fighter records and event history | Terms review required. Use only if permission and rate limits are clear. |

## Forum Demo Recommendation

For the forum trial, use API-first integrations rather than scraping:

1. BALLDONTLIE for fighters, events, fights, rankings, and fight stats.
2. The Odds API for current moneyline odds on upcoming MMA fights.
3. Kaggle or Hugging Face only for offline model training experiments, not as the live source of truth.

Scraping UFCStats, Tapology, Fight Matrix, or Sherdog can wait until we have explicit terms review, source-specific throttling, and provenance logging.

## Initial Feature Mapping

| Feature group | Candidate sources |
| --- | --- |
| Fighter identity and profile | BALLDONTLIE, SportsDataIO, API-Sports, UFCStats |
| Bout history and outcomes | BALLDONTLIE, SportsDataIO, Sportradar, UFCStats, Kaggle |
| Striking and grappling stats | SportsDataIO, Sportradar, BALLDONTLIE paid tiers, UFCStats |
| Rankings and strength of schedule | BALLDONTLIE rankings, Fight Matrix with permission, derived Elo from stored bouts |
| Odds and market movement | The Odds API, SportsDataIO, BALLDONTLIE paid tiers |
| Recent activity | Events/fights APIs, promotion schedules, stored bout dates |

## Practical Integration Order

1. Use `app/data/source_catalog.json` to map CSV or JSON records into `FighterProfile` and wide `FighterExternalFeature` rows.
2. Start with BALLDONTLIE for fighters/events because it has a documented API and low entry cost.
3. Add The Odds API for upcoming fight odds and market-implied probability.
4. Use Kaggle or Hugging Face datasets offline for historical model training while API coverage matures.
5. Revisit UFCStats, Tapology, Fight Matrix, and Sherdog only after terms review and source-specific throttling.

## Compliance Checklist

- Confirm terms of service and robots.txt before scraping.
- Store source URL, provider, fetched timestamp, and raw external ID for every imported record.
- Keep a provider-level rate limit and backoff policy.
- Do not bypass authentication, paywalls, CAPTCHAs, or technical access controls.
- Do not present sourced data as official unless the provider license permits it.
