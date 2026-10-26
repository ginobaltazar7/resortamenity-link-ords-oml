#!/usr/bin/env python3
"""Generate SYNTHETIC sample data for ResortAmenity-Link.

This data is invented. It is not guest data, not production data, and must
never be presented as either. Its purpose is to let the optional Naive Bayes
model (database/oml-model-optional.sql) train and score against outcomes
that are genuinely independent of the loyalty CASE rule — the thing the
original model could never do, because its label was derived from its inputs.

Usage:
    python3 generate_synthetic_data.py [--guests N] [--seed N]

Outputs (same directory):
    sample_amenity_transactions.csv  — one row per amenity purchase, in the
        amenity_transactions shape: transaction_id, opera_guest_id,
        amenity_type, booking_timestamp, amount_spent_jpy, raw_payload
        (raw_payload is a JSON string; lift tickets carry no service_details,
        demonstrating that the field is optional per amenity type).
    sample_guest_labels.csv          — one row per guest: the
        amenity_analytics_cache aggregates plus actually_returned, the
        synthetic ground-truth label (1 = guest actually rebooked).
        This is the column a future real model trains on; here it is
        generated, so it can validate the pipeline without real OPERA data.

How actually_returned is generated (the documented drivers):
    p(return) = clamp(0.15
                      + 0.07 * amenity_visit_count
                      + 0.12 * (total_spend_jpy / 150000)
                      - 0.02 * months_since_last_stay,
                      0.05, 0.90)
    then a Bernoulli draw at that probability, plus ordinary randomness in
    visits, spend, and dates. So returns rise with frequency, spend, and
    recency — the three drivers a real model would hope to find — with
    enough noise that no rule recovers the label exactly.

Determinism: fixed seed (default 20261026). Same seed, same files.
Standard library only — no third-party packages needed.
"""

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta

SEED = 20261026

# Spend ranges per amenity type (JPY), roughly resort-plausible.
SPEND_RANGES = {
    "SPA_TREATMENT": (15000, 80000),
    "SKI_RENTAL": (12000, 50000),
    "LIFT_TICKET": (5000, 15000),
    "PRIVATE_GUIDE": (30000, 100000),
}
TYPE_WEIGHTS = [("SPA_TREATMENT", 0.35), ("SKI_RENTAL", 0.30),
                ("LIFT_TICKET", 0.20), ("PRIVATE_GUIDE", 0.15)]

SPA_ITEMS = [("Shiatsu 60min", 60), ("Onsen entry", 120),
             ("Aromatherapy 45min", 45), ("Deep tissue 90min", 90)]
SKI_ITEMS = [("Full-day rental", 480), ("Half-day rental", 240),
             ("Premium ski set", 480)]
GUIDE_ITEMS = [("Private powder guide", 420), ("Backcountry day", 540),
               ("Family ski lesson", 180)]


def pick_type(rng):
    x = rng.random()
    acc = 0.0
    for name, w in TYPE_WEIGHTS:
        acc += w
        if x <= acc:
            return name
    return TYPE_WEIGHTS[-1][0]


def service_details(rng, amenity_type):
    """service_details per amenity type; lift tickets omit it entirely."""
    if amenity_type == "SPA_TREATMENT":
        name, mins = rng.choice(SPA_ITEMS)
    elif amenity_type == "SKI_RENTAL":
        name, mins = rng.choice(SKI_ITEMS)
    elif amenity_type == "PRIVATE_GUIDE":
        name, mins = rng.choice(GUIDE_ITEMS)
    else:  # LIFT_TICKET — optional field, omitted
        return None
    return {"item_name": name, "duration_minutes": mins}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guests", type=int, default=60)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    today = datetime(2026, 10, 26)
    tx_rows, label_rows = [], []
    tx_n = 0
    for g in range(1, args.guests + 1):
        guest_id = f"G{g:03d}"
        # Visits skew low: most guests come 1-3 times, a few many more.
        visits = max(1, int(rng.expovariate(1 / 2.5)))
        totals = {t: 0 for t in SPEND_RANGES}
        last_stay = None
        for _ in range(visits):
            atype = pick_type(rng)
            lo, hi = SPEND_RANGES[atype]
            amount = rng.randint(lo, hi)
            days_ago = rng.randint(5, 365)
            ts = today - timedelta(days=days_ago)
            if last_stay is None or ts > last_stay:
                last_stay = ts
            details = service_details(rng, atype)
            payload = {"service_details": details} if details else {}
            tx_n += 1
            tx_rows.append({
                "transaction_id": f"TX{tx_n:05d}",
                "opera_guest_id": guest_id,
                "amenity_type": atype,
                "booking_timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "amount_spent_jpy": amount,
                "raw_payload": json.dumps(payload),
            })
            totals[atype] += amount
        total_spend = sum(totals.values())
        months_since = (today - last_stay).days / 30.0
        p = 0.15 + 0.07 * visits + 0.12 * (total_spend / 150000) - 0.02 * months_since
        p = min(0.90, max(0.05, p))
        label_rows.append({
            "opera_guest_id": guest_id,
            "total_spa_spend_jpy": totals["SPA_TREATMENT"],
            "total_ski_spend_jpy": totals["SKI_RENTAL"],
            "total_lift_spend_jpy": totals["LIFT_TICKET"],
            "total_guide_spend_jpy": totals["PRIVATE_GUIDE"],
            "amenity_visit_count": visits,
            "last_stay_date": last_stay.strftime("%Y-%m-%d"),
            "actually_returned": 1 if rng.random() < p else 0,
        })

    with open("sample_amenity_transactions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(tx_rows[0].keys()))
        w.writeheader()
        w.writerows(tx_rows)
    with open("sample_guest_labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(label_rows[0].keys()))
        w.writeheader()
        w.writerows(label_rows)

    ret = sum(r["actually_returned"] for r in label_rows)
    print(f"guests: {len(label_rows)}, transactions: {len(tx_rows)}, "
          f"return rate: {ret}/{len(label_rows)} ({ret / len(label_rows):.0%})")


if __name__ == "__main__":
    main()
