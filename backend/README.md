# BeforeYouSign Python API

A FastAPI service for the [GitHub Pages website](https://rashidodata.github.io/beforeyousign/). Static GitHub Pages **cannot** execute Python: this service requires independent HTTPS hosting.

## Deploy to Render Free

1. Connect the public GitHub repository `rashidodata/beforeyousign` to Render.
2. Deploy the repository with `render.yaml` (Blueprint) or create a new Web Service using the build/start commands defined there. Choose **Free**.
3. Wait for Render to return the real HTTPS `*.onrender.com` service URL. Test its `/health` route and `/docs` page.
4. In GitHub, edit the root `api-config.js`: set `window.BYS_API_BASE` to that **verified** URL. The GitHub Pages website will then use the API for listing text extraction, retaining browser-side fallback if the free instance is asleep or unavailable.
5. Configure server-only secrets in the Render dashboard, never in GitHub Pages JavaScript. By default photo analysis and AI extraction are **disabled**.

## API endpoints

- `GET /health` — basic health check.
- `POST /api/listings/parse` — validates an Idealista listing URL and extracts details from **user-provided** description text, not an automated scrape.
- `POST /api/rent/compare` — compares asking €/sqm against user-supplied, size/distance/type-filtered rental comps, never fabricated market data.
- `GET /api/nearby` — named schools, markets, parks, and transport via OpenStreetMap, disabled until appropriately configured. For public use, add shared rate limits, caching, and a suitable geocoder/OSM provider.
- `GET /api/madrid/records` — experimental Madrid urban-license record lookup, not legal clearance.
- `POST /api/listings/ai-extract` — optional AI extract from user-supplied text/screenshots; off until authenticated and metered.
- `POST /api/photos/analyze` — photo-visible features, server-only secrets required. Do not put an operator token in a public site.

## Local smoke test

```bash
python -m pip install -r requirements-api.txt
uvicorn api:app --host 127.0.0.1 --port 8001
curl http://127.0.0.1:8001/health
```

## Limits and privacy

The current MVP is an evidence-led assistant, **not** an appraisal, building inspection, school quality ranking, or legal opinion. It does not automatically fetch Idealista listings; authorized provider API access is required. Do not advertise unavailable endpoints as live features. Avoid uploading rental paperwork and photos before consent, retention controls, authentication, and usage quotas exist. Render Free spins down after inactivity and is not suitable for production SLAs.