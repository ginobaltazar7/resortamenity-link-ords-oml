# Resort Amenity-Link
> A [lobby boy](https://clip.cafe/the-grand-budapest-hotel-2014/what-a-lobby-boy/) anticipates the client's needs before the needs are needed.

A hospitality pre-arrival guest brief, that links off-property resort amenities (spa treatments, ski rentals, lift tickets, private guides) based on off-property amenity spend, linked to Oracle OPERA Cloud guest profiles, so a resort or hotel property can see how ancillary spend relates to repeat-visit loyalty. [Click here for the demo](https://resortamenity-demo.onrender.com/)

![App Screenshot](docs/resortamenityscreenshot.png?v=2)

## The single-sentence pitch
> Your front desk already knows this guest: every past visit, onsen, spa, and ski booking, every dining preference, and whether they travel with children, because it is all sitting in OPERA already; this brief simply composes that history into one page so staff can anticipate their needs before they are needed.

## How it works:
Amenity POS systems POST transactions to an ORDS REST endpoint (`/v1/amenity-transactions`), which lands them in `amenity_transactions` keyed to `opera_guest_id`. 

Per-guest spend is aggregated in `amenity_analytics_cache`, and a loyalty rule flags repeat guests (3+ amenity visits with combined spa + ski spend over JPY 150,000). 

A Naive Bayes model was considered and built but dropped because it just relearned the CASE rule; see a prior version at commit `456a74e3af53` (opt-in copy in `database/oml-model-optional.sql`, default OFF).

The loyalty threshold (3+ visits, JPY 150,000 or ~USD 1,000 combined spa + ski spend) is a tunable constant, denominated in yen for the scaffold's original market but can be retuned to the deploying property's currency and price level. 

## Status: working scaffold. 

The ingest path and schema are sound. See Roadmap below for the design debt.

## Deployment Setup

1. Run Database Initialization:
   ```sql
   @database/schema-setup.sql
   ```
2. Bind REST Endpoints:
   ```sql
   @database/ords-deployment.sql
   ```
3. Create loyalty views:
   ```sql
   @database/oml-pipelines.sql
   ```

## Roadmap (design debt)

- [ ] Item 6 — `amenity_analytics_cache` is write-only right now and not populated.
      Add a `MERGE`-based refresh procedure (or convert it to a materialized
      view) and call it post-ingest or on a schedule.

- [ ] Layer-2 narration for the guest brief — PARKED as a future feature
      (2026-10-27 decision). An LLM may narrate the Layer-1 facts into
      flowing staff prose, but only with an API key and the no-invention
      guardrail (rephrase facts, never add new ones). Not built yet.

- [X] Item 7 — The OML loyalty model was first built, but it turned out to be circular: the label
      was derived from the same features fed into it, so Naive Bayes just relearned the CASE rule. On 2026-10-26, the model was dropped and the CASE rule kept as the documented rule (commit 890a5b3).

- [X] Item 9 — `specs/payload-spec.json` and `specs/openapi-spec.yaml` disagreed on
      `service_details` (required in one, absent in the other;
      `duration_minutes` is meaningless for lift tickets).
      Resolved 2026-10-26: service_details optional in both specs; view reads guarded with JSON_EXISTS (commits 908129a, fb58a0c, 62cc264).

## Optional model + sample data

- `database/oml-model-optional.sql` — Naive Bayes loyalty model, default OFF. Enable only with `EXEC build_retention_model('Y');`, and only after item 6 (cache population) and real OPERA rebooking labels. See the file header.

- `data/` — SYNTHETIC sample data (not guest data): a generator script, sample transactions and guest labels, `sample_guest_memory.csv` (remembered notes: light hospitality preferences for ski, spa, onsen, dining, children), and `memory_composer.py`, which composes a staff-facing guest brief — arrival intel, what the property remembers, prep actions, top-3 amenity recommendations, suggested questions — from the sample. See `data/README.md`.

- `demo/index.html` — static demo frontend: pick a guest, see the brief. Open the file or serve it statically; no backend, no database. The page links to this repo.

## Inspiration credit

The brief's shape, arrival intel, remembered notes, prep actions, suggested offers, suggested questions, is inspired by chain-recall, a staff-facing guest-brief prototype from the May 2026 Anthropic hackathon, and by the lobby boy scene in *The Grand Budapest Hotel*, whose job is anticipating a guest's needs before they are needed (pattern references only: no code copied, no affiliation).