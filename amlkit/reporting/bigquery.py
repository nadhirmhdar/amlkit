"""BigQuery export for compliance analytics.

Exports key compliance tables from the SQLite database to BigQuery for
dashboards, trend analysis, and regulatory reporting.  No PII is exported
beyond what is structurally required for compliance analytics (customer
reference codes, risk ratings, alert statuses).

Environment variables:
    GCP_PROJECT_ID   — Google Cloud project (required)
    BQ_DATASET       — BigQuery dataset name (default: amlkit_analytics)

Usage:
    from amlkit.reporting.bigquery import export_all
    from amlkit.db import connect
    conn = connect()
    export_all(conn, org_id=1, project="my-project")
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

GCP_PROJECT_ID: str | None = os.environ.get("GCP_PROJECT_ID")
BQ_DATASET: str = os.environ.get("BQ_DATASET", "amlkit_analytics")

# BigQuery table schemas keyed by table name.
# Types: STRING, INTEGER, FLOAT64, BOOL, TIMESTAMP, JSON
_SCHEMAS: dict[str, list[dict]] = {
    "screenings": [
        {"name": "id",            "type": "INTEGER"},
        {"name": "org_id",        "type": "INTEGER"},
        {"name": "customer_id",   "type": "INTEGER"},
        {"name": "ubo_id",        "type": "INTEGER"},
        {"name": "query_name",    "type": "STRING"},
        {"name": "trigger",       "type": "STRING"},
        {"name": "algorithm",     "type": "STRING"},
        {"name": "threshold",     "type": "FLOAT64"},
        {"name": "candidates",    "type": "INTEGER"},
        {"name": "hits",          "type": "INTEGER"},
        {"name": "datasets_used", "type": "STRING"},
        {"name": "run_at",        "type": "TIMESTAMP"},
    ],
    "alerts": [
        {"name": "id",               "type": "INTEGER"},
        {"name": "org_id",           "type": "INTEGER"},
        {"name": "screening_id",     "type": "INTEGER"},
        {"name": "entity_id",        "type": "INTEGER"},
        {"name": "score",            "type": "FLOAT64"},
        {"name": "matched_name",     "type": "STRING"},
        {"name": "status",           "type": "STRING"},
        {"name": "disposition",      "type": "STRING"},
        {"name": "dispositioned_at", "type": "TIMESTAMP"},
        {"name": "created_at",       "type": "TIMESTAMP"},
    ],
    "risk_assessments": [
        {"name": "id",              "type": "INTEGER"},
        {"name": "org_id",          "type": "INTEGER"},
        {"name": "customer_id",     "type": "INTEGER"},
        {"name": "score",           "type": "FLOAT64"},
        {"name": "rating",          "type": "STRING"},
        {"name": "factors",         "type": "STRING"},
        {"name": "ruleset_version", "type": "STRING"},
        {"name": "requires_edd",    "type": "BOOL"},
        {"name": "assessed_at",     "type": "TIMESTAMP"},
        {"name": "next_review",     "type": "TIMESTAMP"},
    ],
    "transactions": [
        {"name": "id",                  "type": "INTEGER"},
        {"name": "org_id",              "type": "INTEGER"},
        {"name": "customer_id",         "type": "INTEGER"},
        {"name": "reference",           "type": "STRING"},
        {"name": "direction",           "type": "STRING"},
        {"name": "method",              "type": "STRING"},
        {"name": "amount",              "type": "FLOAT64"},
        {"name": "currency",            "type": "STRING"},
        {"name": "amount_aed",          "type": "FLOAT64"},
        {"name": "counterparty_country","type": "STRING"},
        {"name": "occurred_at",         "type": "TIMESTAMP"},
        {"name": "created_at",          "type": "TIMESTAMP"},
    ],
    "transaction_alerts": [
        {"name": "id",               "type": "INTEGER"},
        {"name": "org_id",           "type": "INTEGER"},
        {"name": "transaction_id",   "type": "INTEGER"},
        {"name": "customer_id",      "type": "INTEGER"},
        {"name": "rule_key",         "type": "STRING"},
        {"name": "severity",         "type": "STRING"},
        {"name": "detail",           "type": "STRING"},
        {"name": "status",           "type": "STRING"},
        {"name": "disposition",      "type": "STRING"},
        {"name": "dispositioned_at", "type": "TIMESTAMP"},
        {"name": "created_at",       "type": "TIMESTAMP"},
    ],
    "reports": [
        {"name": "id",           "type": "INTEGER"},
        {"name": "org_id",       "type": "INTEGER"},
        {"name": "customer_id",  "type": "INTEGER"},
        {"name": "alert_id",     "type": "INTEGER"},
        {"name": "report_type",  "type": "STRING"},
        {"name": "reference",    "type": "STRING"},
        {"name": "status",       "type": "STRING"},
        {"name": "created_at",   "type": "TIMESTAMP"},
        {"name": "submitted_at", "type": "TIMESTAMP"},
    ],
    "customers_meta": [
        {"name": "id",              "type": "INTEGER"},
        {"name": "org_id",          "type": "INTEGER"},
        {"name": "reference",       "type": "STRING"},
        {"name": "customer_type",   "type": "STRING"},
        {"name": "nationality",     "type": "STRING"},
        {"name": "country",         "type": "STRING"},
        {"name": "sector",          "type": "STRING"},
        {"name": "delivery_channel","type": "STRING"},
        {"name": "is_cash_intensive","type": "BOOL"},
        {"name": "status",          "type": "STRING"},
        {"name": "onboarded_at",    "type": "TIMESTAMP"},
        {"name": "created_at",      "type": "TIMESTAMP"},
    ],
    "adverse_media_screenings": [
        {"name": "id",                  "type": "INTEGER"},
        {"name": "org_id",              "type": "INTEGER"},
        {"name": "customer_id",         "type": "INTEGER"},
        {"name": "trigger",             "type": "STRING"},
        {"name": "provider",            "type": "STRING"},
        {"name": "window_months",       "type": "INTEGER"},
        {"name": "status",              "type": "STRING"},
        {"name": "articles_considered", "type": "INTEGER"},
        {"name": "findings",            "type": "INTEGER"},
        {"name": "severity",            "type": "STRING"},
        {"name": "run_at",              "type": "TIMESTAMP"},
    ],
}

# SQL queries to extract each table.  customers is renamed customers_meta
# and only non-PII columns are selected.
_QUERIES: dict[str, str] = {
    "screenings": """
        SELECT id, org_id, customer_id, ubo_id, query_name, trigger, algorithm,
               threshold, candidates, hits, datasets_used, run_at
        FROM screenings WHERE org_id = ?
    """,
    "alerts": """
        SELECT a.id, a.org_id, a.screening_id, a.entity_id, a.score,
               a.matched_name, a.status, a.disposition, a.dispositioned_at,
               a.created_at
        FROM alerts a WHERE a.org_id = ?
    """,
    "risk_assessments": """
        SELECT id, org_id, customer_id, score, rating, factors,
               ruleset_version, requires_edd, assessed_at, next_review
        FROM risk_assessments WHERE org_id = ?
    """,
    "transactions": """
        SELECT id, org_id, customer_id, reference, direction, method,
               amount, currency, amount_aed, counterparty_country,
               occurred_at, created_at
        FROM transactions WHERE org_id = ?
    """,
    "transaction_alerts": """
        SELECT id, org_id, transaction_id, customer_id, rule_key, severity,
               detail, status, disposition, dispositioned_at, created_at
        FROM transaction_alerts WHERE org_id = ?
    """,
    "reports": """
        SELECT id, org_id, customer_id, alert_id, report_type, reference,
               status, created_at, submitted_at
        FROM reports WHERE org_id = ?
    """,
    "customers_meta": """
        SELECT id, org_id, reference, customer_type, nationality, country,
               sector, delivery_channel, is_cash_intensive, status,
               onboarded_at, created_at
        FROM customers WHERE org_id = ?
    """,
    "adverse_media_screenings": """
        SELECT id, org_id, customer_id, trigger, provider, window_months,
               status, articles_considered, findings, severity, run_at
        FROM adverse_media_screenings WHERE org_id = ?
    """,
}


def _bq_client():
    from google.cloud import bigquery
    return bigquery.Client()


def _ensure_dataset(client, project: str, dataset_id: str) -> None:
    from google.cloud import bigquery
    from google.cloud.exceptions import Conflict
    ds = bigquery.Dataset(f"{project}.{dataset_id}")
    ds.location = "US"
    try:
        client.create_dataset(ds)
    except Conflict:
        pass  # already exists


def _ensure_table(client, project: str, dataset_id: str,
                   table_name: str) -> None:
    from google.cloud import bigquery
    from google.cloud.exceptions import Conflict

    schema = [
        bigquery.SchemaField(
            f["name"],
            f["type"],
            mode="NULLABLE",
        )
        for f in _SCHEMAS[table_name]
    ]
    table_ref = f"{project}.{dataset_id}.{table_name}"
    table = bigquery.Table(table_ref, schema=schema)
    try:
        client.create_table(table)
    except Conflict:
        pass  # already exists


def _coerce_row(row: sqlite3.Row, fields: list[dict]) -> dict[str, Any]:
    """Convert a sqlite3.Row to a dict suitable for BigQuery insertion."""
    result: dict[str, Any] = {}
    for field in fields:
        name = field["name"]
        val = row[name] if name in row.keys() else None
        ftype = field["type"]
        if val is None:
            result[name] = None
        elif ftype == "TIMESTAMP":
            # SQLite stores timestamps as ISO-8601 strings
            result[name] = val  # BigQuery accepts ISO strings
        elif ftype == "BOOL":
            result[name] = bool(val)
        elif ftype == "FLOAT64":
            result[name] = float(val)
        elif ftype == "INTEGER":
            result[name] = int(val) if val is not None else None
        else:
            result[name] = str(val) if val is not None else None
    return result


def export_table(
    conn: sqlite3.Connection,
    org_id: int,
    table_name: str,
    project: str,
    dataset_id: str = BQ_DATASET,
) -> int:
    """Export one table for org_id to BigQuery.  Returns row count inserted."""
    from google.cloud import bigquery

    client = _bq_client()
    _ensure_dataset(client, project, dataset_id)
    _ensure_table(client, project, dataset_id, table_name)

    query = _QUERIES[table_name]
    fields = _SCHEMAS[table_name]

    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, (org_id,)).fetchall()
    if not rows:
        return 0

    bq_rows = [_coerce_row(r, fields) for r in rows]

    table_ref = f"{project}.{dataset_id}.{table_name}"
    errors = client.insert_rows_json(table_ref, bq_rows)
    if errors:
        raise RuntimeError(
            f"BigQuery insert errors for {table_name}: {errors[:5]}"
        )
    return len(bq_rows)


def export_all(
    conn: sqlite3.Connection,
    org_id: int,
    project: str | None = None,
    dataset_id: str = BQ_DATASET,
) -> dict[str, int]:
    """Export all analytics tables for org_id.  Returns {table: row_count}."""
    project = project or GCP_PROJECT_ID
    if not project:
        raise ValueError(
            "Google Cloud project ID is required. "
            "Set GCP_PROJECT_ID or pass project= explicitly."
        )

    results: dict[str, int] = {}
    for table_name in _SCHEMAS:
        n = export_table(conn, org_id, table_name, project, dataset_id)
        results[table_name] = n
    return results
