-- ords-deployment.sql — FIXED
-- Changes:
--  1. Rewrote the garbled OAuth privilege/client block (duplicated fragments).
--  2. POST handler now binds :body (BLOB) into raw_payload instead of :body_text.
--  3. Duplicate transaction_id returns 409 instead of a generic 400.
--  4. OAUTH.create_client uses the correct p_name parameter (was p_client_name).
-- TODO: replace p_support_email / p_owner placeholders before real use.

DECLARE
  PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
  ORDS.enable_schema(
    p_enabled           => TRUE,
    p_schema            => CURRENT_SCHEMA,
    p_url_mapping_pattern => 'resort_api',
    p_auto_rest         => FALSE
  );

  ORDS.define_service(
    p_module_name => 'v1.amenity.link',
    p_base_path   => 'v1/',
    p_pattern     => 'amenity-transactions',
    p_method      => 'POST',
    p_source_type => ORDS.source_type_plsql,
    p_source      => 'BEGIN
      INSERT INTO amenity_transactions
        (transaction_id, opera_guest_id, amenity_type, booking_timestamp, amount_spent_jpy, raw_payload)
      VALUES
        (:transaction_id, :opera_guest_id, :amenity_type,
         TO_TIMESTAMP_TZ(:booking_timestamp, ''YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM''),
         :amount_spent_jpy, :body);
      :status := 201;
      HTP.print(''{"status": "SUCCESS"}'');
    EXCEPTION
      WHEN DUP_VAL_ON_INDEX THEN
        :status := 409; HTP.print(''{"status": "DUPLICATE"}'');
      WHEN OTHERS THEN
        :status := 400; HTP.print(''{"status": "ERROR"}'');
    END;',
    p_items_per_page => 0
  );

  ORDS.create_role(p_role_name => 'amenity_pos_client_role');

  ORDS.define_privilege(
    p_privilege_name => 'amenity_api_privilege',
    p_roles          => ords_varchar2_table('amenity_pos_client_role'),
    p_label          => 'Amenity ingestion',
    p_description    => 'POST amenity transactions from POS.',
    p_patterns       => ords_varchar2_table('/v1/amenity-transactions'),
    p_modules        => ords_varchar2_table('v1.amenity.link')
  );

  OAUTH.create_client(
    p_name            => 'Niseko_Spa_POS_Integration',
    p_grant_type      => 'client_credentials',
    p_owner           => 'ResortAmenity-Link',
    p_description     => 'POS token entry channel.',
    p_support_email   => 'admin@example.com',
    p_privilege_names => 'amenity_api_privilege'
  );

  OAUTH.grant_client_role(
    p_client_name => 'Niseko_Spa_POS_Integration',
    p_role_name   => 'amenity_pos_client_role'
  );

  COMMIT;
END;
/
