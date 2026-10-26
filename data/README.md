# data/ — SYNTHETIC sample data (not guest data)

Everything in this folder is invented by `generate_synthetic_data.py`.
It is not production data, not guest data, and must never be presented as
either. Its purpose is to let the optional Naive Bayes model
(`database/oml-model-optional.sql`) train and score against outcomes that
are genuinely independent of the loyalty CASE rule — the thing the original
model could never do, because its label was derived from its inputs.

## Files

- `generate_synthetic_data.py` — the generator (standard library only).
  Fixed seed (default 20261026): same seed, same files. Re-run it to
  regenerate or resize: `python3 generate_synthetic_data.py --guests 200`.

- `sample_amenity_transactions.csv` — one row per amenity purchase, in the
  `amenity_transactions` shape: transaction_id, opera_guest_id, amenity_type,
  booking_timestamp, amount_spent_jpy, raw_payload (JSON string). Lift
  tickets carry no `service_details`, demonstrating that the field is
  optional per amenity type.

- `sample_guest_labels.csv` — one row per guest: the
  `amenity_analytics_cache` aggregates plus `actually_returned`, the
  synthetic ground-truth label (1 = guest actually rebooked). This is the
  column a future real model trains on; here it is generated, so it can
  validate the pipeline without real OPERA data.

## How actually_returned is generated (the documented drivers)

```
p(return) = clamp(0.15
                  + 0.07 * amenity_visit_count
                  + 0.12 * (total_spend_jpy / 150000)
                  - 0.02 * months_since_last_stay,
                  0.05, 0.90)
```

then a Bernoulli draw at that probability. Returns rise with frequency,
spend, and recency — the three drivers a real model would hope to find —
with enough noise that no rule recovers the label exactly.

Default run (seed 20261026): 60 guests, 115 transactions, 25% return rate.

## memory_composer.py — the brief composer (not data)

`memory_composer.py` reads the two CSVs above and composes a staff-facing
guest brief plus top-3 amenity recommendations, each with a reason citing
the facts. It is a demo of the hospitality pre-arrival briefing, a brief
composed from guest history for staff, here based on synthetic memory
instead of a live OPERA feed or a real live
["lobby boy"](https://clip.cafe/the-grand-budapest-hotel-2014/what-a-lobby-boy/).


Usage (from inside `data/`):
    python3 memory_composer.py --guest G008   # rich history, loyal guest
    python3 memory_composer.py --guest G001   # cold-start example
    python3 memory_composer.py                # richest-history guest

Design rules (standing):
- Layer 1 — facts: every number and claim is computed from the CSVs.
  Nothing is generated or guessed. An optional Layer 2 (LLM narration)
  may only rephrase these facts, never invent new ones.

- No leakage: `actually_returned` is deliberately NOT used in any brief.
  It is future knowledge; staff at arrival cannot know it.

- Recommendations are rule-based: something new in the guest's top
  category, the most popular untried item, and a cross-type step-up;
  cold-start guests fall back to the most popular items overall.


## What this data must NOT be used for

- Any claim about real guests, real properties, or real return rates.

- Any score presented as a resort prediction. Scores trained here validate
  the pipeline's mechanics only.

- Training a model that ships anywhere near production data. When real
  OPERA rebooking history exists, it replaces this file entirely.
