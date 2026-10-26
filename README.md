# ResortAmenity-Link

An integration engine for Oracle OPERA Cloud via ORDS and OML4SQL.

Links off-property resort amenities (spa treatments, ski rentals, lift tickets, private guides) to Oracle OPERA Cloud guest profiles, so a resort can see how ancillary spend relates to repeat-visit loyalty.

## How it works:
Amenity POS systems POST transactions to an ORDS REST endpoint (`/v1/amenity-transactions`), which lands them in `amenity_transactions` keyed to `opera_guest_id`. Per-guest spend is aggregated in `amenity_analytics_cache`, and a loyalty rule flags repeat guests (3+ amenity visits with combined spa + ski spend over JPY 150,000). The former Naive Bayes model was dropped as tautological — see database/oml-pipelines.sql.

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

- [ ] `amenity_analytics_cache` is write-only right now — nothing populates it.
      Add a `MERGE`-based refresh procedure (or convert it to a materialized
      view) and call it post-ingest or on a schedule.
- [X] The OML loyalty model is tautological: the label is derived from the same
      features fed into it, so Naive Bayes just relearns the CASE rule. Either
      engineer genuinely predictive features (recency, tenure, seasonality) or
      drop the model and keep the rule.
- [X] `specs/payload-spec.json` and `specs/openapi-spec.yaml` disagree on
      `service_details` (required in one, absent in the other;
      `duration_minutes` is meaningless for lift tickets). Align them, and make
      `service_details` optional per amenity type.   
