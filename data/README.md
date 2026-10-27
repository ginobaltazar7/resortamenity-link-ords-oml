# data/ — SYNTHETIC sample data (not guest data)

The sample data in this folder is invented by `generate_synthetic_data.py`. It is not production data, and not guest data. 

The transactions feed the demo briefs; the labels exist for the optional model: `actually_returned` is a stochastic outcome (a probability from visits, spend, and recency), not derived from the loyalty CASE rule. 

So unlike the original labels, it doesn't hand a model the rule's own answer. That model (`database/oml-model-optional.sql`) is OFF by default and stays that way until item 6 and real OPERA labels.


## Files

- `generate_synthetic_data.py` — the generator (standard library only).
  Fixed seed (default 20261026): same seed, same files. Re-run it to
  regenerate or resize: `python3 generate_synthetic_data.py --guests 200`.
  `--regulars N` (default 10) adds a cohort of rich-history guests
  (5-9 visits each) numbered after the base guests; they are generated
  after base memory, so base rows are byte-identical with or without
  them. `--regulars 0` gives base guests only.

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

- `sample_guest_memory.csv` — remembered notes, one row per note:
  opera_guest_id, category, note. Light hospitality preferences only,
  in five categories: SKI (skiing and winter activities), SPA, ONSEN,
  DINING (dinner and meals), CHILDREN (whether guests travel with
  children). SKI / SPA / ONSEN / CHILDREN notes are derived from the
  guest's own purchase patterns, with wording that respects the counts
  (one booking is "has booked", never "regular"). DINING notes are
  seeded stated preferences — things a guest would tell staff at
  check-in — because the scaffold carries no dining feed. Nothing here
  is clinical, sensitive, or identifying: every note is invented demo
  data, same as the rest of this folder.

## How `actually_returned` is generated (the documented drivers)

```
p(return) = clamp(0.15
                  + 0.07 * amenity_visit_count
                  + 0.12 * (total_spend_jpy / 150000)
                  - 0.02 * months_since_last_stay,
                  0.05, 0.90)
```

How to read the formula: it is a linear probability model, so each number is a scalar weight measured in probability points. 

The intercept (0.15) is the baseline; each visit adds 0.07, each ¥150,000 of total spend adds 0.12, and each month since the last stay subtracts 0.02. 

The three features are the RFM trio: recency, frequency, monetary: the classic customer-segmentation trio from direct marketing and which remains the first answer to "will they come back?" question.

`clamp` pins the result into [0.05, 0.90] so the linear score stays a valid probability and no guest is ever a certain 0 or 1; a Bernoulli draw at that probability then sets the label. These weights are hand-picked design constants, not estimates fitted to data; and recency is the one driver the loyalty CASE rule does not use, which is what keeps the label from being derived from the rule.

Each guest gets a return probability from the formula above, then a Bernoulli draw as mentioned that sets the label. Returns rise with recency, frequency and spend — the three drivers a real model would hope to find — and aremodeled with enough "noise" so that no rule recovers the label exactly.


Default run (seed 20261026): 70 guests (60 base + 10 regulars), 186 transactions, 33% return rate, 155 memory notes. 18 guests have rich histories (5+ visits); G008 (7 visits) is no longer the only one.

## memory_composer.py — the brief composer (not data)

`memory_composer.py` reads the three CSVs above and composes a staff-facing
guest brief: arrival intel (visits, spend, loyalty), what the property
remembers (memory notes), prep actions, top-3 amenity recommendations
each with a reason citing the facts, and suggested questions (verbatim
staff scripts) — plus a composition trace naming its sources. It is a
demo of the hospitality pre-arrival briefing, a brief composed from
guest history for staff, here based on synthetic memory instead of a
live OPERA feed or a real live
["lobby boy"](https://clip.cafe/the-grand-budapest-hotel-2014/what-a-lobby-boy/).

The brief's structure is inspired by chain-recall's staff brief
(pattern reference only, not affiliated — see the root README).

Usage (from inside `data/`):
    python3 memory_composer.py --guest G008   # rich history, loyal guest
    python3 memory_composer.py --guest G001   # cold-start example
    python3 memory_composer.py                # richest-history guest
    python3 memory_composer.py --demo-json    # all guests as JSON, the
                                              # exact data embedded in
                                              # demo/index.html

Design rules (standing):
- Layer 1 — facts: every number and claim is computed from the CSVs.
  Nothing is generated or guessed. An optional Layer 2 (LLM narration)
  may only rephrase these facts, never invent new ones. Layer 2 is
  PARKED as a future feature (2026-10-27 decision): it needs an API key
  and the no-invention guardrail, so it is not built here.

- No leakage: `actually_returned` is deliberately NOT used in any brief.
  It is future knowledge; staff at arrival cannot know it.

- Recommendations are rule-based: something new in the guest's top
  category, the most popular untried item, and a cross-type step-up;
  cold-start guests fall back to the most popular items overall.

- Prep actions and suggested questions are fixed rules over the memory
  notes, never invented per guest. Memory depth ("First impression" /
  "Growing memory" / "Deep memory") follows visit count.


## What this data must NOT be used for

- Any claim about real guests, real properties, or real return rates.

- Any score presented as a resort prediction. Scores trained here validate
  the pipeline's mechanics only.

- Training a model that ships anywhere near production data. When real
  OPERA rebooking history exists, it replaces this file entirely.
