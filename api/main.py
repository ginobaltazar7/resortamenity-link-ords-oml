"""

ResortAmenity thin API — staff-facing guest briefs as JSON.

Two modes, decided at startup and reported by GET /health:
  CSV mode (default, works on first deploy): briefs are computed from the
  synthetic sample CSVs in DATA_DIR. No database, no secrets.
  Oracle mode (later): when DB_USER, DB_PASSWORD and DB_DSN are all set,
  briefs should come from the live views (v_guest_loyalty_tier and the
  amenity views). That wiring is NOT done yet — oracle_brief() raises a
  clear 501 until it lands, so the API can never silently serve the wrong
  mode. See api/README.md.

Endpoints:
  GET /health           -> {"status": "ok", "mode": "csv" | "oracle"}
  GET /guests           -> ["G001", ..., "G060"] (synthetic guest ids)
  GET /brief/{guest_id} -> visits, total spend, spend by type, favorite
                           items, last stay, loyalty flag, and top-3
                           recommendations, each with a reason.

The brief shape mirrors the static demo (demo/index.html) and the
memory_composer.py rules: same loyalty rule (3+ visits AND spa+ski
spend > JPY 150,000), same recommendation rules (new item in the top
category, most popular untried item, cross-type step-up, popularity
fallback for cold-start guests). The synthetic ground truth
(actually_returned) is never used — it is future knowledge.

Run locally from the repo root:
  pip install -r api/requirements.txt
  uvicorn api.main:app --reload

"""

import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------- config
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_DSN = os.environ.get("DB_DSN", "")
ORACLE_MODE = bool(DB_USER and DB_PASSWORD and DB_DSN)

# Same step-up map as memory_composer.py (a guest's favorite -> the next
# thing to offer). Kept in sync with the composer by hand; if the map
# changes there, change it here too.
STEP_UP = {
    "Shiatsu 60min": "Deep tissue 90min",
    "Deep tissue 90min": "Aromatherapy 45min",
    "Aromatherapy 45min": "Shiatsu 60min",
    "Onsen entry": "Shiatsu 60min",
    "Full-day rental": "Premium ski set",
    "Half-day rental": "Full-day rental",
    "Premium ski set": "Backcountry day",
    "Family ski lesson": "Private powder guide",
    "Private powder guide": "Backcountry day",
    "Backcountry day": "Private powder guide",
}
ITEM_TYPE = {}
for _t, _items in {
    "SPA_TREATMENT": ["Shiatsu 60min", "Deep tissue 90min",
                      "Aromatherapy 45min", "Onsen entry"],
    "SKI_RENTAL": ["Full-day rental", "Half-day rental", "Premium ski set"],
    "PRIVATE_GUIDE": ["Private powder guide", "Backcountry day",
                      "Family ski lesson"],
}.items():
    for _i in _items:
        ITEM_TYPE[_i] = _t

LOYALTY_MIN_VISITS = 3
LOYALTY_MIN_SPA_SKI_JPY = 150000


# ---------------------------------------------------------------- CSV mode
def load_csv_briefs(data_dir: Path) -> dict:
    """Compute one brief per guest from the synthetic CSVs.

    Returns {guest_id: brief-dict}. Empty dict if the CSVs are absent
    (the API still boots; /guests is empty and /brief 404s).
    """
    tx_path = data_dir / "sample_amenity_transactions.csv"
    if not tx_path.exists():
        print(f"WARNING: {tx_path} not found — running with no guests.")
        return {}
    by_guest: dict = defaultdict(list)
    popularity: Counter = Counter()
    with open(tx_path, newline="") as f:
        for t in csv.DictReader(f):
            by_guest[t["opera_guest_id"]].append(t)
            payload = json.loads(t["raw_payload"])
            if payload.get("service_details"):
                popularity[payload["service_details"]["item_name"]] += 1

    briefs = {}
    for gid, rows in by_guest.items():
        by_type: Counter = Counter()
        items: Counter = Counter()
        last_stay = None
        total = 0
        for t in rows:
            by_type[t["amenity_type"]] += int(t["amount_spent_jpy"])
            total += int(t["amount_spent_jpy"])
            payload = json.loads(t["raw_payload"])
            if payload.get("service_details"):
                items[payload["service_details"]["item_name"]] += 1
            ts = datetime.fromisoformat(t["booking_timestamp"])
            last_stay = ts if last_stay is None or ts > last_stay else last_stay
        visits = len(rows)
        spa_ski = by_type["SPA_TREATMENT"] + by_type["SKI_RENTAL"]
        loyal = visits >= LOYALTY_MIN_VISITS \
            and spa_ski > LOYALTY_MIN_SPA_SKI_JPY
        top_type = by_type.most_common(1)[0][0] if by_type else None
        tried = set(items)
        recs = []
        if top_type:
            for item, _ in popularity.most_common():
                if ITEM_TYPE.get(item) == top_type and item not in tried:
                    recs.append({"item": item,
                                 "reason": f"most popular "
                                 f"{top_type.lower().replace('_', ' ')} "
                                 f"item they haven't tried"})
                    break
        for item, _ in popularity.most_common():
            if item not in tried and item not in [r["item"] for r in recs]:
                recs.append({"item": item,
                             "reason": "most popular amenity across all guests"})
                break
        if items:
            fav = items.most_common(1)[0][0]
            nxt = STEP_UP.get(fav)
            if nxt and nxt not in tried \
                    and nxt not in [r["item"] for r in recs]:
                recs.append({"item": nxt,
                             "reason": f"a step up from their favorite, {fav}"})
        for item, _ in popularity.most_common():
            if len(recs) >= 3:
                break
            if item not in tried and item not in [r["item"] for r in recs]:
                recs.append({"item": item, "reason": "popular fallback"})
        briefs[gid] = {
            "guest_id": gid,
            "visits": visits,
            "total_spend_jpy": total,
            "spend_by_type_jpy": dict(by_type.most_common()),
            "favorite_items": [{"item": i, "times": n}
                               for i, n in items.most_common(3)],
            "last_stay": last_stay.date().isoformat() if last_stay else None,
            "loyal": loyal,
            "recommendations": recs[:3],
            "synthetic": True,
        }
    return briefs


# ---------------------------------------------------------------- Oracle mode
def oracle_brief(guest_id: str) -> dict:
    """
    
    TODO (next step, once the OCI Autonomous DB exists).

    Query the live views (v_guest_loyalty_tier for visits/spend/loyalty,
    v_amenity_deep_analytics for items) with oracledb thin mode,
    using DB_USER / DB_PASSWORD / DB_DSN plus the wallet secret file.
    Deliberately a stub: it must fail loudly, never fall back to CSVs
    silently, once Oracle mode is switched on.

    """
    raise HTTPException(
        status_code=501,
        detail="Oracle mode is switched on but the live-view query is not "
               "wired yet. See api/README.md (Oracle TODO).")


# ---------------------------------------------------------------- app
app = FastAPI(title="ResortAmenity brief API")
# The demo page will call this from another Render domain, so CORS is
# open for now. The data is synthetic and public. Restrict origins
# before serving any real guest data.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

BRIEFS = {} if ORACLE_MODE else load_csv_briefs(DATA_DIR)


@app.get("/health")
def health():
    return {"status": "ok",
            "mode": "oracle" if ORACLE_MODE else "csv",
            "guests": len(BRIEFS)}


@app.get("/guests")
def guests():
    return sorted(BRIEFS)


@app.get("/brief/{guest_id}")
def brief(guest_id: str):
    if ORACLE_MODE:
        return oracle_brief(guest_id)
    if guest_id not in BRIEFS:
        raise HTTPException(status_code=404, detail="unknown guest")
    return BRIEFS[guest_id]
