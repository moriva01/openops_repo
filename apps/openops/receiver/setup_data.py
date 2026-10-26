"""Provision this application's read-only datasource view; never change Zetaris internals."""
import os
import re
import urllib.error
from psycopg import sql
from receiver.server import connection
from receiver.zetaris import ADAPTER

VIEW = """CREATE OR REPLACE VIEW monitor_samples AS SELECT event_id::text AS event_id, host_id, hostname,
extract(epoch FROM observed_at)::double precision AS observed_epoch,
(payload#>>'{host,cpu_used_percent}')::double precision AS cpu_percent,
(payload#>>'{host,memory,used_percent}')::double precision AS memory_percent,
(payload#>>'{host,disk,used_percent}')::double precision AS disk_percent,
(payload#>>'{application,reachable}')::boolean AS app_reachable,
(payload#>>'{application,oldest_pending_age_seconds}')::double precision AS oldest_pending_seconds,
(payload#>>'{application,delivered_last_60_seconds}')::double precision AS throughput,
(payload#>>'{application,records,rejected}')::double precision AS rejected_total,
(SELECT (p->>'pending_output')::double precision FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='voice') AS voice_pending,
(SELECT (p->>'output_enabled')::boolean FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='voice') AS voice_output_enabled,
(payload#>>'{systemd_units,tmc-api}')::text AS api_process,
(payload#>>'{systemd_units,tmc-mediation}')::text AS mediation_process,
(payload#>>'{systemd_units,tmc-delivery}')::text AS delivery_process,
(SELECT (p->>'pending_output')::double precision FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='sms') AS sms_pending,
(SELECT (p->>'pending_output')::double precision FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='data') AS data_pending,
(SELECT (p->>'output_enabled')::boolean FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='sms') AS sms_output_enabled,
(SELECT (p->>'output_enabled')::boolean FROM jsonb_array_elements(payload#>'{application,portals}') p WHERE p->>'kind'='data') AS data_output_enabled
FROM telemetry_events"""

def main():
    with connection() as db:
        db.execute(VIEW)
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='openops_zetaris'").fetchone():
            db.execute(sql.SQL("CREATE ROLE openops_zetaris LOGIN PASSWORD {}").format(sql.Literal(os.environ["OPENOPS_ZETARIS_DB_PASSWORD"])))
        db.execute("GRANT CONNECT ON DATABASE openops TO openops_zetaris")
        db.execute("GRANT USAGE ON SCHEMA public TO openops_zetaris")
        db.execute("GRANT SELECT ON monitor_samples TO openops_zetaris")
    print("Application view and read-only PostgreSQL account ready; credential omitted.")
    print("Read-only Zetaris preflight:")
    for statement in ("SELECT 1", "SHOW LIGHTNING DATABASES", "SHOW DATASOURCES"):
        reply = ADAPTER.query(statement, 20)
        print(statement, str(reply.get("records", reply.get("data", reply)))[:1500])
    sources = ADAPTER.query("SHOW DATASOURCES").get("data", [])
    if not any("openops_pg" in row for row in sources):
        password = os.environ["OPENOPS_ZETARIS_DB_PASSWORD"]
        assert re.fullmatch(r"[A-Za-z0-9_-]+", password)
        statement = ('CREATE DATASOURCE openops_pg DESCRIBE BY "OpenOps monitoring read-only view" OPTIONS '
                     '(jdbcdriver "org.postgresql.Driver", jdbcurl "jdbc:postgresql://openops-db-1:5432/openops", '
                     'username "openops_zetaris", password "' + password + '", fetchsize "1000")')
        print('Registering openops_pg -> application PostgreSQL, read-only account; password omitted.')
        try:
            result = ADAPTER.query(statement)
            print("Datasource creation response:", str(result.get("data", []))[:300])
        except urllib.error.HTTPError as error:
            detail = error.read().decode().replace(password, "[redacted]")
            raise RuntimeError("Zetaris registration failed: " + detail[:800]) from None
    tables = ADAPTER.query('SHOW DATASOURCE TABLES openops_pg').get('data', [])
    if not any('monitor_samples' in str(row) for row in tables):
        print("Registering monitor_samples view metadata")
        result = ADAPTER.query('REGISTER DATASOURCE TABLE "monitor_samples" FROM openops_pg')
        print("View registration:", str(result.get("data", []))[:400])
    ADAPTER.query('REFRESH DATASOURCE TABLES FROM openops_pg')
    result = ADAPTER.query("SELECT event_id,voice_pending,delivery_process FROM openops_pg.monitor_samples ORDER BY observed_epoch DESC LIMIT 1", 1)
    print("Live source verified; returned rows:",len(result.get('data',[])))

if __name__ == "__main__":
    main()
