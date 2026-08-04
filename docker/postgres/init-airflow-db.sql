-- Creates the Airflow metadata database on first Postgres volume init only.
-- If postgres_data already exists, drop the volume or run manually:
--   CREATE DATABASE airflow;

CREATE DATABASE airflow;
