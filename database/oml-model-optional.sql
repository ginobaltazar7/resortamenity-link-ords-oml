-- oml-model-optional.sql — OPTIONAL Naive Bayes loyalty model (default OFF)
--
-- Purpose: preserves the Naive Bayes modelling capability for the
-- ResortAmenity-Link repo as an opt-in module, without making it live.
-- Nothing in the main pipeline calls this file. Loading it only creates the
-- procedure below; the model itself is built only when you explicitly call
-- build_retention_model('Y').
--
-- WHY IT IS OFF BY DEFAULT (read before enabling):
--   The model this file builds was dropped from oml-pipelines.sql on
--   2026-10-26 (commit 890a5b3) because it was tautological: its label,
--   is_repeat_loyal_guest, was derived from the same five columns it trained
--   on, so Naive Bayes only relearned the CASE rule it was handed. The
--   probability it returned looked like confidence in a real prediction;
--   it was confidence in reproducing a rule.
--
-- TWO PRECONDITIONS FOR ENABLING — both must hold first:
--   1. Item 6 done: amenity_analytics_cache must actually be populated
--      (MERGE refresh proc + scheduler job). The training view reads from
--      the cache; on an empty cache the model build has nothing to learn
--      from and will fail.
--   2. Real labels: the training view's label MUST be replaced with actual
--      OPERA rebooking history (did the guest actually return?) before any
--      score is used for a decision. Enabling with the CASE-derived label
--      still in place reproduces the tautology — the procedure says so
--      out loud when it runs. Genuinely predictive features to add at that
--      point: recency, frequency, seasonality from booking_timestamp.
--
-- HOW TO ENABLE:
--   EXEC build_retention_model('Y');
--   This replaces v_guest_propensity_scores (rule version) with the
--   model-scored version.
--
-- HOW TO DISABLE (restore the rule):
--   Re-run @database/oml-pipelines.sql. Its guarded DROP removes the model
--   and recreates the rule views. Do not hand-edit the views to switch back;
--   oml-pipelines.sql is the single source of truth for the rule version.
--
-- WHY THE FLAG IS VARCHAR2 'Y'/'N' AND NOT BOOLEAN:
--   A string literal is callable from SQL*Plus, SQLcl, and ORDS without
--   PL/SQL boolean plumbing. Anything other than 'Y' or 'N' raises an error
--   rather than silently doing nothing.
--
-- Original model code: commit 456a74e3af53 (2026-10-12). Machinery below is
-- verbatim from that version; only the wrapper and the label TODO are new.

CREATE OR REPLACE PROCEDURE build_retention_model(p_enabled IN VARCHAR2 DEFAULT 'N') AS
  v_flag VARCHAR2(1) := UPPER(TRIM(p_enabled));
  v_setlst DBMS_DATA_MINING.setting_list;
BEGIN
  IF v_flag NOT IN ('Y', 'N') THEN
    RAISE_APPLICATION_ERROR(-20001, 'build_retention_model: p_enabled must be ''Y'' or ''N''.');
  END IF;

  IF v_flag = 'N' THEN
    DBMS_OUTPUT.PUT_LINE('Retention model NOT built (default OFF). Rule views in oml-pipelines.sql stay live.');
    DBMS_OUTPUT.PUT_LINE('To enable: EXEC build_retention_model(''Y''); — only after item 6 (cache population) and real rebooking labels.');
    RETURN;
  END IF;

  DBMS_OUTPUT.PUT_LINE('WARNING: building RESORT_RETENTION_MODEL from the CASE-derived label reproduces the documented tautology.');
  DBMS_OUTPUT.PUT_LINE('Scores will mirror the rule until the label is replaced with actual OPERA rebooking history. Do not use for decisions.');

  -- Training view. TODO (blocking for any real use): replace the CASE-derived
  -- label with actual OPERA rebooking history. Until that happens, this view
  -- exists to preserve the model's structure, not to produce trusted scores.
  EXECUTE IMMEDIATE '
    CREATE OR REPLACE VIEW v_oml_training_data AS
    SELECT opera_guest_id, total_spa_spend_jpy, total_ski_spend_jpy, total_lift_spend_jpy, total_guide_spend_jpy, amenity_visit_count,
      CASE WHEN amenity_visit_count >= 3 AND (total_spa_spend_jpy + total_ski_spend_jpy) > 150000 THEN 1 ELSE 0 END AS is_repeat_loyal_guest
    FROM amenity_analytics_cache';

  -- Model settings + build (verbatim machinery from 456a74e3af53).
  BEGIN DBMS_DATA_MINING.drop_model('RESORT_RETENTION_MODEL'); EXCEPTION WHEN OTHERS THEN NULL; END;
  v_setlst(DBMS_DATA_MINING.algo_name) := DBMS_DATA_MINING.algo_naive_bayes;
  v_setlst(DBMS_DATA_MINING.prep_auto) := DBMS_DATA_MINING.prep_auto_on;
  BEGIN EXECUTE IMMEDIATE 'DROP TABLE oml_model_settings'; EXCEPTION WHEN OTHERS THEN NULL; END;
  EXECUTE IMMEDIATE 'CREATE TABLE oml_model_settings (setting_name VARCHAR2(30), setting_value VARCHAR2(4000))';
  FOR i IN 1..v_setlst.COUNT LOOP
    INSERT INTO oml_model_settings VALUES (v_setlst(i).setting_name, v_setlst(i).setting_value);
  END LOOP;
  COMMIT;
  DBMS_DATA_MINING.create_model(
    model_name          => 'RESORT_RETENTION_MODEL',
    mining_function    => DBMS_DATA_MINING.classification,
    data_table_name    => 'v_oml_training_data',
    case_id_column_name => 'opera_guest_id',
    target_column_name => 'is_repeat_loyal_guest',
    settings_table_name => 'oml_model_settings'
  );

  -- Model-scored propensity view (replaces the rule version while enabled).
  EXECUTE IMMEDIATE '
    CREATE OR REPLACE VIEW v_guest_propensity_scores AS
    SELECT
      opera_guest_id,
      total_spa_spend_jpy,
      total_ski_spend_jpy,
      total_lift_spend_jpy,
      total_guide_spend_jpy,
      amenity_visit_count,
      PREDICTION(RESORT_RETENTION_MODEL USING total_spa_spend_jpy, total_ski_spend_jpy, total_lift_spend_jpy, total_guide_spend_jpy, amenity_visit_count) AS predicted_loyal_guest,
      PREDICTION_PROBABILITY(RESORT_RETENTION_MODEL, 1 USING total_spa_spend_jpy, total_ski_spend_jpy, total_lift_spend_jpy, total_guide_spend_jpy, amenity_visit_count) AS loyalty_probability
    FROM amenity_analytics_cache';

  DBMS_OUTPUT.PUT_LINE('Model built; v_guest_propensity_scores now reports model scores.');
END;
/
