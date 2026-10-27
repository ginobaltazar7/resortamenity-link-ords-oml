# Resort Amenity thin API

This API serves staff-facing guest briefs as JSON, with the same brief shape and rules as `demo/index.html` and `data/memory_composer.py`:

- Loyalty rule: 3+ visits AND spa+ski spend over JPY 150,000 (~USD 1,000).
- Recommendations: a new item in the guest's top category, the most popular untried item, a cross-type step-up, and a popularity fallback.
- Remembered memory notes, with prep actions and suggested questions derived from them.

The synthetic ground truth (`actually_returned`) is never used in briefs.


## Run locally (from the repo root)

```
pip install -r api/requirements.txt
uvicorn api.main:app --reload
```

Then:

```
curl localhost:8000/health
curl localhost:8000/guests
curl localhost:8000/brief/G008   # richest history, loyal guest
curl localhost:8000/brief/G001   # cold-start example
```

`GET /health` reports the live mode (`csv` or `oracle`) and the guest
count, so you can always see which mode is serving.

## Modes

- **CSV mode (default, works on first deploy):** briefs are computed
  from the synthetic CSVs in `DATA_DIR` (default: repo `data/`).
  No database, no secrets.

- **Oracle mode (next step):** set `DB_USER`, `DB_PASSWORD`, and
  `DB_DSN` in the Render Dashboard (never in the repo) and the API
  switches mode — but `oracle_brief()` in `api/main.py` is still a stub
  that returns 501 until the live-view query is written. That is
  deliberate: the API must fail loudly, never silently serve CSVs
  while claiming to be live.

## Oracle TODO (once the OCI Autonomous DB exists)

1. Create the Autonomous DB, deploy `database/schema-setup.sql` and
   `database/oml-pipelines.sql`, and populate the cache (item 6).

2. Download the DB wallet; upload it as a Render **Secret File**
   (Dashboard → service → Secret Files) and point the connection at it.

3. Implement `oracle_brief()` with `oracledb` thin mode:
   visits/spend/loyalty from `v_guest_loyalty_tier`, items from
   `v_amenity_deep_analytics`. Keep the response shape identical so the
   demo page works against either mode.
   
4. Restrict CORS in `api/main.py` before serving any real guest data
   (it is wide open now because the data is synthetic and public).

## Render

Deploy via the Blueprint: Dashboard → New → Blueprint → select this
repo. `render.yaml` at the repo root creates the static demo site and
this web service. Free tier: the web service sleeps after inactivity
(first request after idle takes ~30–60s to wake); the static site does
not sleep. A future live mode for the demo page (fetching `/brief/<id>`
instead of the embedded data) is a one-endpoint change in
`demo/index.html` once Oracle mode is live.
