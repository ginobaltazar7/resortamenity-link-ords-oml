#!/usr/bin/env python3
"""

memory_composer.py — compose a staff-facing guest brief + amenity
recommendations from the synthetic memory (the sample CSVs).

This is the hospitality pre-arrival briefing, rebuilt on synthetic data:
a "memory composer" takes everything known about a guest and composes it
into something staff can act on at arrival — who they are, what they spend
on, what the property remembers about them, what to prepare, and what to
offer them. The brief's structure — arrival intel, remembered notes, prep
actions, suggested offers, suggested questions — is inspired by
chain-recall, a staff-facing guest-brief prototype from the May 2026
Anthropic hackathon (DareDev256/chain-recall). Pattern reference only:
no code was copied, and this project is not affiliated with chain-recall
or its authors (its license is listed as NOASSERTION).

ARCHITECTURE (the part that matters):
  Layer 1 — FACTS (this script). Every number and claim below is computed
  from the CSVs. Nothing is generated, guessed, or phrased by a model.
  If an AI ever narrates this brief, it may only rephrase these facts and it must ideally not invent new ones.

  Layer 2 — NARRATIVE (optional, not this script). An LLM may turn the
  facts into flowing staff-facing prose. It sits on top of Layer 1 and
  never replaces it. PARKED as a future feature (2026-10-27 decision):
  it needs an API key and the no-invention guardrail, so it is not built
  here.

NO-LEAKAGE RULE:
  sample_guest_labels.csv carries actually_returned, the synthetic
  ground truth (did the guest actually rebook?). That column is FUTURE
  knowledge and is deliberately NOT used anywhere in the brief. Staff
  at arrival cannot know it. It exists only to validate models later.
  A brief that cited it would be cheating in exactly the way the
  dropped Naive Bayes model cheated.

MEMORY NOTES (sample_guest_memory.csv):
  Light hospitality preferences only, in five categories: SKI, SPA,
  ONSEN, DINING, CHILDREN. SKI / SPA / ONSEN / CHILDREN notes are
  derived from the guest's own purchase patterns, with wording that
  respects the counts (one booking is "has booked", never "regular").
  DINING notes are seeded stated preferences — things a guest would
  tell staff at check-in — because the scaffold carries no dining feed.
  Prep actions and suggested questions are derived from these notes by
  fixed rules below, never invented per guest.

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
    python3 memory_composer.py --demo-json    # all guests as JSON, for
                                              # embedding in demo/index.html

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

LOYALTY_RULE = "3+ visits AND spa+ski spend > JPY 150,000"


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
    memory = defaultdict(list)
    try:
        for r in csv.DictReader(open("sample_guest_memory.csv")):
            memory[r["opera_guest_id"]].append((r["category"], r["note"]))
    except FileNotFoundError:
        pass  # older checkouts without the memory file still compose
    return by_guest, labels, popularity, memory


def memory_depth(visits):
    if visits >= 5:
        return "Deep memory"
    if visits >= 2:
        return "Growing memory"
    return "First impression"


def prep_actions(notes):
    """Fixed rules: remembered note -> something staff should prepare."""
    actions = []
    for cat, note in notes:
        if cat == "CHILDREN":
            actions.append("Set the room up family-style and confirm "
                           "family lesson times.")
        elif cat == "SKI":
            if "Backcountry" in note:
                actions.append("Confirm the guide booking for the "
                               "backcountry day.")
            elif "premium" in note:
                actions.append("Hold the premium ski set for arrival day.")
            else:
                actions.append("Confirm ski rental sizes for arrival day.")
        elif cat == "SPA":
            if "Deep tissue" in note:
                actions.append("Reserve the usual Deep tissue 90min slot.")
            else:
                actions.append("Reserve a spa treatment slot for arrival "
                               "evening.")
        elif cat == "ONSEN":
            if note.startswith("Hasn't"):
                actions.append("Mention the evening onsen at check-in.")
            else:
                actions.append("Leave the evening onsen hours card in the "
                               "room.")
        elif cat == "DINING":
            if "Early dinner" in note:
                actions.append("Flag an early dinner seating.")
            elif "quiet table" in note:
                actions.append("Request a quiet table for dinner.")
            else:
                actions.append("Have local dinner recommendations ready at "
                               "check-in.")
    seen = set()
    out = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def suggested_questions(notes, fav, visits):
    """Verbatim staff scripts, derived from notes and the favorite item."""
    qs = []
    cats = {c for c, _ in notes}
    if fav:
        qs.append(f"Welcome back — shall I book your usual {fav}?")
    if "CHILDREN" in cats:
        qs.append("Shall I confirm the family lesson times for this stay?")
    if any(c == "ONSEN" and n.startswith("Hasn't") for c, n in notes):
        qs.append("Have you tried the evening onsen? Guests who enjoy the "
                  "spa usually love it.")
    if "DINING" in cats:
        qs.append("Would you like me to hold an early dinner seating after "
                  "your ski day?")
    if visits <= 1 and not qs:
        qs.append("Is this your first stay with us? I can walk you through "
                  "the spa and ski options.")
    return qs[:3]


def compose_brief(gid, by_guest, labels, popularity, memory):
    rows = by_guest.get(gid, [])
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

    notes = memory.get(gid, [])
    fav = items.most_common(1)[0][0] if items else None
    return {
        "guest_id": gid,
        "visits": visits,
        "total_spend_jpy": total,
        "spend_by_type_jpy": dict(by_type.most_common()),
        "favorite_items": [{"item": i, "times": n}
                           for i, n in items.most_common(3)],
        "days_since_last_stay": days_since,
        "loyal": loyal,
        "memory_depth": memory_depth(visits),
        "memory_notes": [{"category": c, "note": n} for c, n in notes],
        "prep_actions": prep_actions(notes),
        "recommendations": [{"item": i, "reason": r} for i, r in recs[:3]],
        "suggested_questions": suggested_questions(notes, fav, visits),
        "composed_from": {
            "transactions": len(rows),
            "memory_notes": len(notes),
            "loyalty_rule": LOYALTY_RULE,
        },
        "synthetic": True,
    }


def format_text(b):
    def plural(noun, count):
        return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
    lines = []
    lines.append(f"=== Guest brief: {b['guest_id']} (SYNTHETIC memory — demo only) ===")
    lines.append(f"Memory: {b['memory_depth']} — {plural('visit', b['visits'])}, "
                 f"{plural('remembered note', len(b['memory_notes']))}")
    lines.append(f"Visits: {b['visits']} | Total spend: JPY {b['total_spend_jpy']:,}")
    if b["spend_by_type_jpy"]:
        shares = ", ".join(
            f"{t.lower().replace('_', ' ')} JPY {v:,} "
            f"({v / b['total_spend_jpy']:.0%})"
            for t, v in b["spend_by_type_jpy"].items())
        lines.append(f"Spend by type: {shares}")
    if b["favorite_items"]:
        lines.append("Favorite items: " + ", ".join(
            f"{f['item']} x{f['times']}" for f in b["favorite_items"]))
    if b["days_since_last_stay"] is not None:
        lines.append(f"Last stay: {b['days_since_last_stay']} days ago")
    lines.append(f"Loyalty rule ({LOYALTY_RULE}): "
                 f"{'YES — repeat loyal guest' if b['loyal'] else 'not yet'}")
    lines.append("")
    lines.append("What we remember:")
    if b["memory_notes"]:
        for note in b["memory_notes"]:
            lines.append(f"  [{note['category']}] {note['note']}")
    else:
        lines.append("  (nothing remembered yet — first impression)")
    lines.append("")
    lines.append("Prep actions (for staff):")
    if b["prep_actions"]:
        for a in b["prep_actions"]:
            lines.append(f"  - {a}")
    else:
        lines.append("  - First-visit welcome — introduce the spa and ski "
                     "options.")
    lines.append("")
    lines.append("Suggested offers (staff-facing; reasons cite the facts above):")
    for i, r in enumerate(b["recommendations"], 1):
        lines.append(f"  {i}. {r['item']} — {r['reason']}.")
    if not b["recommendations"]:
        lines.append("  (no recommendation — no history and no popularity data)")
    lines.append("")
    lines.append("Suggested questions (things to say at arrival):")
    for q in b["suggested_questions"]:
        lines.append(f'  - "{q}"')
    lines.append("")
    lines.append(f"How this brief was composed: "
                 f"{plural('amenity purchase', b['composed_from']['transactions'])}, "
                 f"loyalty rule ({LOYALTY_RULE}), "
                 f"{plural('remembered note', b['composed_from']['memory_notes'])}. "
                 f"Facts only — nothing generated.")
    lines.append("Note: actually_returned (synthetic ground truth) was NOT used "
                 "in this brief — it is future knowledge, not arrival knowledge.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guest", default=None)
    ap.add_argument("--demo-json", action="store_true",
                    help="print all guests as JSON for demo/index.html")
    args = ap.parse_args()
    by_guest, labels, popularity, memory = load()
    if args.demo_json:
        out = {}
        for gid in sorted(by_guest):
            out[gid] = compose_brief(gid, by_guest, labels, popularity,
                                     memory)
        print(json.dumps(out))
        return
    gid = args.guest
    if gid is None:
        gid = max(by_guest.items(), key=lambda kv: len(kv[1]))[0]
    print(format_text(compose_brief(gid, by_guest, labels, popularity,
                                    memory)))


if __name__ == "__main__":
    main()
