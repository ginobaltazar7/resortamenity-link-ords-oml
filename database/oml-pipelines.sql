-- oml-pipelines.sql — FIXED
-- Change: rewrote the garbled v_guest_propensity_scores view.
-- Also: case ID (opera_guest_id) excluded from the PREDICTION inputs.
-- Training view + model build unchanged.

CREATE OR REPLACE VIEW v_oml_training_data AS
SELECT opera_guest_id, total_spa_spend_jpy, total_ski_spend_jpy, total_lift_spend_jpy, total_guide_spend_jpy, amenity_visit_count,
  CASE WHEN amenity_visit_count >= 3 AND (total_spa_spend_jpy + total_ski_spend_jpy) > 150000 THEN 1 ELSE 0 END AS is_repeat_loyal_guest
FROM amenity_analytics_cache;

DECLARE
  v_setlst DBMS_DATA_MINING.setting_list;
BEGIN
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
END;
/

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
FROM amenity_analytics_cache;
