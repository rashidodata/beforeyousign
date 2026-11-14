# Licensed-provider evaluation checklist

**Status: NOT RUN.** We do not have credentials, known commercial-reuse rights, or current published per-call pricing. No paid provider calls should be made until these are resolved.

## Candidates

| Provider | Capability known from public docs | Unresolved |
| --- | --- | --- |
| Idealista official Search API | Advertised access by application to integrate property information | Individual ID detail lookup, limits, price, commercial use rights |
| OpenData API (independent) | Documents `/api/project/idealista/property-details` with `propertyId`, `location`, `language` | License to republish/source rights, rate limits, per-request cost |
| Apify community actors | Various third-party listing import programs | Rights, maintenance/availability, cost per listing, reliability |

The last two are **not authorized Idealista integrations by default**. Provider availability is not proof of permission to use or republish data. Never enable a scraper or proxy bypass on the public app.

## Pilot protocol (after licensing approval)

1. Collect 10–20 *real rental* listing URLs, covering flats/houses, popular and outlying neighborhoods, different floor levels, furnished/unfurnished units and at least one withdrawn/expired ad. Include only listings the agreement permits us to access.
2. Save them in a local CSV with header `url` (no private contacts). **Do not commit this file.**
3. Run `python scripts/evaluate_provider.py your-listings.csv`: dry-run only, no credits.
4. After verifying API costs and setting backend environment credentials, run with `--confirm-paid-requests` to measure validity and field coverage. Review against the actual listing manually to estimate accuracy.
5. Record: success rate, fields populated correctly (rent, built area, bedrooms, floor, town), photos rights, latency, extraction freshness, withdrawn ads, and total charged cost.
6. Do not publish raw provider responses. Never expose landlord/agent contact details, photos or exact addresses that the listing hides.

Minimum launch bar: 90%+ ID resolution, 95%+ exact rent/area on active rental listings, credible per-request costs, written rights to use data, and documented caching/republication limits. These are **targets**, not measured results.

## Application for official Idealista API

Submit the draft in [`idealista-application.md`](idealista-application.md) via https://developers.idealista.com/access-request using the project owner's approved name and email. This file is a prepared draft; it has **not** been submitted.