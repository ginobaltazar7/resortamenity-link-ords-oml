# ResortAmenity-Link
Off-property amenity spend, linked to OPERA guest loyalty.

Links off-property resort amenities (spa treatments, ski rentals, lift tickets, private guides) to Oracle OPERA Cloud guest profiles, so a resort or hotel property can see how ancillary spend relates to repeat-visit loyalty.

## How it works:
Amenity POS systems POST transactions to an ORDS REST endpoint (`/v1/amenity-transactions`), which lands them in `amenity_transactions` keyed to `opera_guest_id`. Per-guest spend is aggregated in `amenity_analytics_cache`, and a loyalty rule flags repeat guests (3+ amenity visits with combined spa + ski spend over JPY 150,000). The former Naive Bayes model was dropped as tautological — see database/oml-pipelines.sql.

The loyalty threshold (3+ visits, JPY 150,000 or ~USD 1,000 combined spa + ski spend) is a tunable constant, denominated in yen for the scaffold's original market but can be retuned to the deploying property's currency and price level. Nothing else in the system is market-specific.

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

- [ ] `amenity_analytics_cache` is write-only right now and not populated. 
      Add a `MERGE`-based refresh procedure (or convert it to a materialized
      view) and call it post-ingest or on a schedule.
- [X] The OML loyalty model was tautological: the label was derived from the same
      features fed into it, so Naive Bayes just relearned the CASE rule.
      Resolved 2026-10-26: model dropped, CASE kept as documented rule (commit 890a5b3).
- [X] `specs/payload-spec.json` and `specs/openapi-spec.yaml` disagreed on
      `service_details` (required in one, absent in the other;
      `duration_minutes` is meaningless for lift tickets).
      Resolved 2026-10-26: service_details optional in both specs; view reads guarded with JSON_EXISTS (commits 908129a, fb58a0c, 62cc264).
