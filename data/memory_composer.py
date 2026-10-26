#!/usr/bin/env python3
"""

memory_composer.py — compose a staff-facing guest brief + amenity
recommendations from the synthetic memory (the sample CSVs).

This is the hospitality pre-arrival briefing, rebuilt on synthetic data:
a "memory composer" takes everything known about a guest and composes it
into something staff can act on at arrival — who they are, what they spend
on, and what to offer them.

ARCHITECTURE (the part that matters):
  Layer 1 — FACTS (this script). Every number and claim below is computed
  from the CSVs. Nothing is generated, guessed, or phrased by a model.
  If an AI ever narrates this brief, it may only rephrase these facts and it must ideally not invent new ones.

  Layer 2 — NARRATIVE (optional, not this script). An LLM may turn the
  facts into flowing staff-facing prose. It sits on top of Layer 1 and
  never replaces it.

NO-LEAKAGE RULE:
  sample_guest_labels.csv carries actually_returned, the synthetic
  ground truth (did the guest actually rebook?). That column is FUTURE
  knowledge and is deliberately NOT used anywhere in the brief. Staff
  at arrival cannot know it. It exists only to validate models later.
  A brief that cited it would be cheating in exactly the way the
  dropped Naive Bayes model cheated.

RECOMMENDATIONS (rule-based, top 3, each with a reason citing facts):
  1. Something new in the guest's top category by spend.
  2. The most popular item across all guests that this guest hasn't tried.
  3. A cross-type step-up (skier without a guide -> guided day; spa guest
     -> a longer treatment), or the next most popular untried item.
  Cold start (0-1 visits): all three fall back to the most popular items
  overall — the segment default, not silence.

Usage:
    python3 memory_composer.py --guest G008
    python3 memory_composer.py --guest G001   # cold-start example
    python3 memory_composer.py                # richest-history guest

"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime

TODAY = datetime(2026, 10, 26)
# Item -> a complementary next step, for the cross-type rule.
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


def load():
    tx = list(csv.DictReader(open("sample_amenity_transactions.csv")))
    labels = {r["opera_guest_id"]: r
              for r in csv.DictReader(open("sample_guest_labels.csv"))}
    by_guest = defaultdict(list)
    for t in tx:
        by_guest[t["opera_guest_id"]].append(t)
    popularity = Counter()
    for t in tx:
        p = json.loads(t["raw_payload"])
        if p.get("service_details"):
            popularity[p["service_details"]["item_name"]] += 1
    return by_guest, labels, popularity


def compose(gid, by_guest, labels, popularity):
    rows = by_guest.get(gid, [])
    lab = labels.get(gid)
    visits = len(rows)
    total = sum(int(t["amount_spent_jpy"]) for t in rows)
    by_type = Counter()
    items = Counter()
    last = None
    for t in rows:
        by_type[t["amenity_type"]] += int(t["amount_spent_jpy"])
        p = json.loads(t["raw_payload"])
        if p.get("service_details"):
            items[p["service_details"]["item_name"]] += 1
        ts = datetime.fromisoformat(t["booking_timestamp"])
        last = ts if last is None or ts > last else last
    days_since = (TODAY - last).days if last else None
    spa_ski = by_type["SPA_TREATMENT"] + by_type["SKI_RENTAL"]
    loyal = visits >= 3 and spa_ski > 150000
    top_type = by_type.most_common(1)[0][0] if by_type else None
    tried = set(items)

    recs = []
    # 1. Something new in the top category.
    if top_type:
        for item, _ in popularity.most_common():
            if ITEM_TYPE.get(item) == top_type and item not in tried:
                recs.append((item, f"most popular {top_type.lower().replace('_', ' ')} item they haven't tried"))
                break
    # 2. Most popular overall, untried.
    for item, _ in popularity.most_common():
        if item not in tried and item not in [r[0] for r in recs]:
            recs.append((item, "most popular amenity across all guests"))
            break
    # 3. Cross-type step-up from their favorite item.
    if items:
        fav = items.most_common(1)[0][0]
        nxt = STEP_UP.get(fav)
        if nxt and nxt not in tried and nxt not in [r[0] for r in recs]:
            recs.append((nxt, f"a step up from their favorite, {fav}"))
    # Fill with popularity fallback (also the whole cold-start path).
    for item, _ in popularity.most_common():
        if len(recs) >= 3:
            break
        if item not in tried and item not in [r[0] for r in recs]:
            recs.append((item, "popular fallback"))

    lines = []
    lines.append(f"=== Guest brief: {gid} (SYNTHETIC memory — demo only) ===")
    lines.append(f"Visits: {visits} | Total spend: JPY {total:,}")
    if by_type:
        shares = ", ".join(
            f"{t.lower().replace('_', ' ')} JPY {v:,} ({v / total:.0%})"
            for t, v in by_type.most_common())
        lines.append(f"Spend by type: {shares}")
    if items:
        lines.append("Favorite items: " + ", ".join(
            f"{i} x{n}" for i, n in items.most_common(3)))
    if days_since is not None:
        lines.append(f"Last stay: {days_since} days ago")
    lines.append(f"Loyalty rule (3+ visits, spa+ski over JPY 150,000): "
                 f"{'YES — repeat loyal guest' if loyal else 'not yet'}")
    lines.append("")
    lines.append("Suggested offers (staff-facing; reasons cite the facts above):")
    for i, (item, reason) in enumerate(recs[:3], 1):
        lines.append(f"  {i}. {item} — {reason}.")
    if not recs:
        lines.append("  (no recommendation — no history and no popularity data)")
    lines.append("")
    lines.append("Note: actually_returned (synthetic ground truth) was NOT used "
                 "in this brief — it is future knowledge, not arrival knowledge.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guest", default=None)
    args = ap.parse_args()
    by_guest, labels, popularity = load()
    gid = args.guest
    if gid is None:
        gid = max(by_guest.items(), key=lambda kv: len(kv[1]))[0]
    print(compose(gid, by_guest, labels, popularity))


if __name__ == "__main__":
    main()
