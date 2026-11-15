"""Idempotent lightweight upgrades for databases created before derived metrics.

The project does not ship a production migration framework; create_all covers
fresh databases, and these guarded ALTER statements upgrade an existing
database in place.  Legacy trade-off snapshots and trial plans keep their
original shape and remain readable.
"""
from sqlalchemy import text


def _column_exists(conn, table, column):
    rows = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"),
        {'t': table, 'c': column}).fetchall()
    return bool(rows)


def _table_exists(conn, table):
    rows = conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t"), {'t': table}).fetchall()
    return bool(rows)


def _ensure_columns(conn):
    if _table_exists(conn, 'criteria'):
        if not _column_exists(conn, 'criteria', 'kind'):
            conn.execute(text("ALTER TABLE criteria ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'base'"))
        if not _column_exists(conn, 'criteria', 'formula'):
            conn.execute(text("ALTER TABLE criteria ADD COLUMN formula VARCHAR(600) NOT NULL DEFAULT ''"))
        if not _column_exists(conn, 'criteria', 'dims'):
            conn.execute(text("ALTER TABLE criteria ADD COLUMN dims JSON NULL"))
            conn.execute(text("UPDATE criteria SET dims = CASE code "
                              "WHEN 'absorption' THEN JSON_ARRAY(0,0,0,0,0) "
                              "WHEN 'impact' THEN JSON_ARRAY(0,1,0,0,0) "
                              "WHEN 'carbon' THEN JSON_ARRAY(1,1,0,0,0) "
                              "WHEN 'price' THEN JSON_ARRAY(1,0,0,0,1) "
                              "WHEN 'thickness' THEN JSON_ARRAY(1,0,0,0,0) "
                              "ELSE JSON_ARRAY(0,0,0,0,0) END"))
        if not _column_exists(conn, 'criteria', 'version'):
            conn.execute(text("ALTER TABLE criteria ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
    if _table_exists(conn, 'material_samples'):
        for column in ('absorption', 'impact', 'carbon', 'price', 'thickness'):
            # MySQL has no direct "drop not null if present"; MODIFY is idempotent.
            conn.execute(text(f"ALTER TABLE material_samples MODIFY COLUMN {column} DOUBLE NULL"))
    if _table_exists(conn, 'decision_runs') and not _column_exists(conn, 'decision_runs', 'definition_version'):
        conn.execute(text("ALTER TABLE decision_runs ADD COLUMN definition_version VARCHAR(64) NOT NULL DEFAULT ''"))


def _ensure_schema_upgrades(engine):
    # The guarded ALTERs and information_schema probes are MySQL-specific; on
    # other dialects create_all already produces the current full schema.
    if engine.dialect.name != 'mysql':
        return
    with engine.begin() as conn:
        _ensure_columns(conn)
