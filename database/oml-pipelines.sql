-- Previous ML version preserved in git history: commit 456a74e3af53 (2026-10-12).
-- oml-pipelines.sql — ITEM 7 REVISION (2026-10-25)
-- Decision: drop the Naive Bayes loyalty model. The old training view defined
-- is_repeat_loyal_guest as a CASE over the same five columns the model trained
-- on, so the model only relearned the rule it was handed — a tautology, not a
-- prediction. The CASE survives as a documented business rule below, and the
-- propensity view now reports the rule directly instead of a model score.
--
-- TODO (revisit when real OPERA rebooking data is available):
--   Replace this rule with a real model: source the label from actual OPERA
--   rebooking history (did the guest actually return?) and engineer predictive
--   features from booking_timestamp (recency, frequency, seasonality). Until
--   that data exists, do NOT reintroduce a model trained on this rule —
--   it would be the same tautology again.

-- Guarded drop: remove the stale model so nothing downstream keeps scoring
-- against a model this file no longer builds.
BEGIN
  BEGIN DBMS_DATA_MINING.drop_model('RESORT_RETENTION_MODEL'); EXCEPTION WHEN OTHERS THEN NULL; END;
END;
/

-- The loyalty rule, stated honestly as a rule (not a model target):
-- a guest counts as a repeat loyal guest at 3+ amenity visits with combined
-- spa + ski spend over JPY 150,000.
CREATE OR REPLACE VIEW v_guest_loyalty_tier AS
SELECT opera_guest_id, total_spa_spend_jpy, total_ski_spend_jpy, total_lift_spend_jpy, total_guide_spend_jpy, amenity_visit_count,
  CASE WHEN amenity_visit_count >= 3 AND (total_spa_spend_jpy + total_ski_spend_jpy) > 150000 THEN 1 ELSE 0 END AS is_repeat_loyal_guest
FROM amenity_analytics_cache;

-- Replaces v_guest_propensity_scores: same column shape for downstream
-- consumers, but the "prediction" is the rule above, and loyalty_probability
-- is NULL because a rule has no probability — that NULL is the honest signal
-- that no model is scoring this anymore.
CREATE OR REPLACE VIEW v_guest_propensity_scores AS
SELECT
  opera_guest_id,
  total_spa_spend_jpy,
  total_ski_spend_jpy,
  total_lift_spend_jpy,
  total_guide_spend_jpy,
  amenity_visit_count,
  is_repeat_loyal_guest AS predicted_loyal_guest,
  CAST(NULL AS NUMBER) AS loyalty_probability
FROM v_guest_loyalty_tier;