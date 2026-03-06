# Financial Analyst Agent (v1, Local macOS)

A local multi-agent financial analysis service using free-tier model/tool APIs first.

## What this v1 does
- Exposes API endpoints:
  - `POST /v1/analyze`
  - `GET /v1/jobs/{job_id}`
  - `GET /v1/reports/{job_id}`
- Pulls free-source evidence from:
  - SEC EDGAR (`submissions`, `companyfacts`)
  - FMP / Alpha Vantage (market data, fallback)
  - BLS / BEA (macro, optional)
  - Brave Search API (news discovery, optional)
- Routes LLM calls across free providers in order:
  - Groq -> OpenRouter -> GitHub Models -> Hugging Face -> local deterministic fallback

## macOS setup
```bash
cd /Users/vincent/Desktop/FinancialAnalystAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set keys you have. Minimum recommended:
- `SEC_USER_AGENT` (must be valid for SEC fair access, use your real email)
- One model key: `GROQ_API_KEY` or `OPENROUTER_API_KEY`
- One market data key: `FMP_API_KEY` or `ALPHA_VANTAGE_API_KEY`

## Run API server
```bash
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open UI in browser:
```text
http://127.0.0.1:8000/
```

## Deploy frontend on GitHub Pages
This repo is ready for GitHub Pages deploy from either branch root or `/docs`.
If GitHub does not let you save `/ (root)`, use `/docs`.

1. Push this repo to GitHub.
2. Go to `Settings -> Pages`.
3. Under `Build and deployment`, set:
   - Source: `Deploy from a branch`
   - Branch: `main` (or your branch)
   - Folder: `/docs` (recommended when root cannot be saved)
4. Open your Pages URL (for example: `https://<user>.github.io/<repo>/`).
5. In the UI, set `API Base URL` to your backend URL (for example: `https://your-api.example.com`).

Notes:
- `API Base URL` is saved in browser local storage.
- You can override it via URL query param: `?api_base=https://your-api.example.com`.
- Leave it empty only when frontend and backend are served from the same origin.

Backend CORS is enabled for local origins and `https://*.github.io` by default.
Optional environment overrides:
- `CORS_ALLOW_ORIGINS` (comma-separated)
- `CORS_ALLOW_ORIGIN_REGEX`

## Analyze a ticker (API)
```bash
curl -s -X POST http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"MSFT","horizon_days":365,"depth":"deep","include_macro":true}'
```

Then poll job and fetch report:
```bash
curl -s http://127.0.0.1:8000/v1/jobs/<job_id>
curl -s http://127.0.0.1:8000/v1/reports/<job_id>
curl -s 'http://127.0.0.1:8000/v1/reports/<job_id>/readable?lang=en'
curl -s 'http://127.0.0.1:8000/v1/reports/<job_id>/readable?lang=zh'
curl -s 'http://127.0.0.1:8000/v1/reports/<job_id>/readable?lang=both'
```

## One-off CLI run
```bash
source .venv/bin/activate
python run_once.py MSFT --horizon-days 365 --depth deep
```

## Thorough runner (any US ticker)
```bash
source .venv/bin/activate
python run_stock_thorough.py AAPL --horizon-days 365
```

## Notes
- If all cloud LLM free quotas are exhausted, v1 uses a local deterministic fallback so job completion still works.
- `NewsAPI` is intentionally not wired for production use due free-plan restrictions.
- Deep mode now supports any US ticker with correlation-selected peers from a broad US universe.
- Report output now includes English and Chinese narratives (`narrative_en`, `narrative_zh`).
- Report output now includes a reliability breakdown (`reliability`) with:
  - `grade` (A-E)
  - `trustworthy_for_decisions` (true only when confidence >= 0.90)
  - component-level score contributions
- CLI defaults to readable bilingual narratives. Use `--json` for full JSON.
- Built-in front-end UI is served from `/` and supports English/Chinese/Both reading modes.
- This is a v1 baseline; valuation is intentionally simple and should be replaced with full fundamental models in v2.
