# Whoop Insights

A third-party web dashboard that surfaces the deeper Whoop analytics the official app doesn't — long-range trends past Whoop's 6-month cap, and proper strength-trainer progression (per-exercise weight curves, e1RM, PRs).

Mobile-first. Backend in Python/Flask, store in SQLite.

## Quick start (5 minutes, no Whoop credentials needed)

You need Python 3.10+ and `git`.

```bash
git clone <this-repo>
cd whoopInsights

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env                # default settings work for local demo

python app.py
```

Open http://localhost:5000 — sample data is seeded automatically so the Trends and Strength pages render immediately. Browse to `/strength` and pick an exercise to see the headline progression view.

## Hooking up your real Whoop account

1. Register a developer app at https://developer-dashboard.whoop.com.
2. Set the **redirect URI** to `http://localhost:5000/auth/callback` (add your production URL too once you deploy).
3. Copy the `Client ID` and `Client Secret` into `.env`:
   ```
   WHOOP_CLIENT_ID=...
   WHOOP_CLIENT_SECRET=...
   USE_SAMPLE_DATA=false
   ```
4. Restart the app. Click **Connect Whoop** on the homepage. After authorising, hit **Sync now** to pull your last 12 months of cycles, sleeps, and workouts.

> **API rate limits:** Whoop's default app cap is ~60-80 connected users. Apply for an increase early via the developer dashboard — community reports say it can take weeks.

## Project layout

```
app.py                 Flask entry, blueprint registration, sample-data seeding
config.py              env-driven config (Whoop creds, DB path)
db.py                  SQLite schema and connection helpers
seed.py                Realistic sample data (180 days + 24 weeks of lifts)
whoop/
  oauth.py             Whoop OAuth2 authorize / token / refresh
  client.py            Whoop API client with auto-pagination & token refresh
  sync.py              Pulls cycles, recoveries, sleeps, workouts -> SQLite
analytics/
  strength.py          Per-exercise progression: top weight, e1RM, PRs, volume
  trends.py            Long-range daily series for HRV, RHR, recovery, etc.
routes/
  auth.py              /auth/login, /auth/callback, /auth/logout
  dashboard.py         /, /trends, /sync
  strength.py          /strength, /strength/<exercise>
templates/             Mobile-first Jinja templates (Pico.css)
static/                style.css + app.js (Chart.js wiring)
```

## Open question: per-set Whoop strength data

The headline product wedge — per-exercise weight progression — depends on Whoop exposing per-set/per-rep data via their API. Their public docs aren't conclusive. The schema (`strength_sets`) is ready either way:

- **If the API exposes it:** `whoop/sync.py` extracts it via `_extract_strength_sets()` (probes a few likely shapes — confirm and tighten once we see a real workout response from your account).
- **If it doesn't:** we add a manual entry UI. The schema and analytics stay identical.

This needs a real Whoop account with Strength Trainer history to verify. Highest priority once you have credentials.

## Roadmap

Built:
- OAuth + sync + SQLite store
- Long-range trends past Whoop's 6-month cap (HRV, RHR, recovery, strain, sleep performance, sleep duration)
- Strength progression: top weight, e1RM (Epley), volume, PR detection per exercise

Next:
- Manual strength-set entry (covers us if the API doesn't expose per-set data)
- Multi-variable Journal correlations with statistical confidence
- Training-load model (ATL/CTL/form, acute:chronic ratio)
- Anomaly/illness early-warning (Z-scores on rolling HRV/RHR/respiratory rate)
- Sleep-debt rolling curve
- Annual report PDF export

## License

TBD.
