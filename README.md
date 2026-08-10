# ResortAmenity-Link

An integration and machine learning engine for Oracle OPERA Cloud via ORDS and OML4SQL.

## Deployment Setup

1. Run Database Initialization:
   ```sql
   @database/schema-setup.sql
   ```
2. Bind REST Endpoints:
   ```sql
   @database/ords-deployment.sql
   ```
3. Initialize OML Models:
   ```sql
   @database/oml-pipelines.sql
   ```
