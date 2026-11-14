# BeforeYouSign

**Rent with clarity.** A rental-first, free-to-host web application for evaluating apartments, houses and commercial premises before signing a lease.

## Live website
Once GitHub Pages finishes deploying: https://rashidodata.github.io/beforeyousign/

## Features
- Rental asking price per square metre and monthly housing-cost breakdown.
- Rent comparisons using tenant-provided comparable listings or imported CSV.
- Upfront moving and renovation costs amortized over a planned tenancy.
- Explainable price flags, evidence notes and downloadable JSON analysis.
- Neighborhood discovery links for schools, nurseries, supermarkets, markets, parks and public transport.
- Responsive desktop and mobile layouts.

**Important:** This is a prototype. The site does not retrieve verified live property listings, report actual walking distances or conduct automatic AI photo inspection. Demo comparable listings are fictional and must not be treated as market evidence.

## Development
The static frontend lives in `index.html`. Open it in a browser or run `python -m http.server 8000` locally. GitHub Pages builds and publishes automatically through `.github/workflows/pages.yml`.

## Security
Never commit API secrets. Browser-only websites cannot safely keep OpenAI or real-estate data provider keys private. AI-powered photo assessments and automatic proprietary listing comparisons require a separate secure API/backend.

## GitHub Pages
Go to **Settings → Pages** and choose **GitHub Actions** under Build and deployment, if GitHub has not configured it automatically. The `pages.yml` workflow publishes the root directory after every push to the default `master` branch.

## Scope
This is an experimental decision-support application, not a formal valuation, building inspection or legal opinion.
