# Live Feed Acquisition Plan

The ingestion connector reads local files or live URLs from `app/data/source_catalog.json`. Sources can be CSV or JSON, can use environment variables in URLs and headers, can page through cursor-based APIs, and can store unmapped provider fields as wide external fighter features.

## API-First Sources

| Source | Status | What we can import | Key / cost notes |
| --- | --- | --- | --- |
| [BALLDONTLIE MMA API](https://mma.balldontlie.io/) | Ready to configure | Fighters immediately on the free tier; fights, rankings, fight stats, and odds on paid tiers | Requires `BALLDONTLIE_API_KEY`. Free tier includes leagues, events, fighters; ALL-STAR is listed at $9.99/mo; GOAT at $39.99/mo. |
| [The Odds API](https://the-odds-api.com/sports-odds-data/mma-odds.html) | Ready to configure | Current and upcoming MMA fight odds | Requires `THE_ODDS_API_KEY`. Current odds are available on the free plan; historical odds require a paid plan. |
| [SportsDataIO MMA/UFC](https://sportsdata.io/mma-ufc-api) | Commercial candidate | Fighter profiles, schedules, scores, stats, odds, projections, news, images | Free trial/commercial plan. Better for production if budget allows. |
| [Sportradar MMA API](https://marketplace.sportradar.com/products/652fc88991cb7d6acdef2532) | Enterprise candidate | UFC schedules, live results, profiles, head-to-head stats | Commercial/enterprise. |
| [API-Sports MMA](https://api-sports.io/documentation/mma/v1) | Alternative API candidate | Fighters, fights, seasons, categories, odds | Requires API key. |

## Fighter Image Sources

| Source | Status | What we can import | Key / cost notes |
| --- | --- | --- | --- |
| [Wikidata P18 + Wikimedia Commons](https://www.wikidata.org/wiki/Property:P18) | Partially implemented | Open fighter images attached to Wikidata items, backed by Commons files | No API key. Best first source for permissive images, but coverage is uneven and every image still needs attribution/provenance. |
| [MediaWiki Imageinfo API](https://www.mediawiki.org/wiki/API:Imageinfo) | Candidate enhancement | Direct Commons thumbnail URLs and metadata for known file names | No API key. Useful for validating thumbnail URLs and dimensions. |
| [SportsDataIO MMA/UFC](https://sportsdata.io/mma-ufc-api) | Commercial candidate | Fighter data, news, and images from one licensed feed | Free trial/commercial plan. Strong production candidate if budget allows. |
| [Sportradar Images API](https://developer.sportradar.com/images-and-editorials/reference/images-overview) | Enterprise candidate | Player headshots and sports image libraries | Commercial/enterprise. Best fit when licensed, high-quality headshots are needed at scale. |
| Official promotion sites | Permission-needed candidate | Athlete profile photos directly from UFC, PFL, ONE, etc. | Prefer API/partner permission or explicit license review before automated collection. |

The scheduled worker currently improves images with bounded Wikimedia-style lookups and
image URL health checks. It avoids broad scraping by default.

## Scraping Candidates

| Source | Finding | Recommendation |
| --- | --- | --- |
| UFCStats | Public site and high-value source; third-party scrapers exist, but commercial use still needs terms review. | Use only after a terms/robots review and with throttling, cache, and provenance. |
| Tapology | Public pages contain upcoming cards and fighter pages, but broad automated collection should be reviewed first. | Do not scrape for the public app without explicit review or permission. |
| Sherdog | Public pages contain fighter records and events, but broad automated collection should be reviewed first. | Treat as permission-needed before broad scraping. |
| Fight Matrix | Rankings and historical ratings are valuable but proprietary. | Prefer permission/partnership over scraping rankings. |

## Current Catalog Templates

The catalog includes two live templates that are skipped unless their environment variables are present:

- `BALLDONTLIE_API_KEY` enables `balldontlie-fighters-live`.
- `THE_ODDS_API_KEY` enables `the-odds-api-mma-current`.

The default BALLDONTLIE template imports up to 5 pages of 25 fighters per run to stay polite on low-tier API limits. Increase `pagination.max_pages` only after confirming the account's current rate limit.

Run:

```powershell
python scripts/import_data.py
```

Without keys, the importer uses the local sample and supplemental feeds. With keys, it also pulls the enabled live feeds.

## Next Engineering Steps

1. Add provider-specific normalization for BALLDONTLIE fighter fields such as inches-to-centimeters and date-of-birth-to-age.
2. Add live odds normalization that maps both fighters in a matchup, not only the event-level row.
3. Add `Event`, `Bout`, `RankingSnapshot`, and `OddsSnapshot` tables so live sources are not forced into fighter-level features only.
4. Add licensed image provider connectors for SportsDataIO or Sportradar when an account is available.
5. Add a source status page for import counts, last run, and provider errors.

## Current Import Shape

Live API records are stored as wide external features even when they are not complete enough to be prediction-ready `FighterProfile` rows. A fighter becomes prediction-ready only after the app has the full required profile fields: age, height, reach, record, finishing rates, takedown metrics, and strike pace.
