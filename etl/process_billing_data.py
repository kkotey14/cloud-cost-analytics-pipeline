from __future__ import annotations

import argparse
import calendar
import csv
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "cloud_billing_sample.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed"
DEFAULT_DB_PATH = DEFAULT_OUTPUT_DIR / "cloud_costs.db"

REQUIRED_COLUMNS = {
    "billing_date",
    "cloud_provider",
    "account_id",
    "service",
    "region",
    "usage_type",
    "cost",
    "currency",
    "environment",
    "team",
    "project",
    "resource_id",
    "tags",
}

TABLE_ORDER = (
    "fact_cloud_costs",
    "dim_date",
    "dim_service",
    "dim_team",
    "daily_spend_summary",
    "executive_summary",
)


def normalize_text(value: object, fallback: str = "unknown") -> str:
    text = "" if value is None else str(value).strip()
    return text.lower() if text else fallback


def load_raw_billing(path: Path) -> list[dict[str, str]]:
    """Read the raw billing CSV and validate the expected source schema."""
    if not path.exists():
        raise FileNotFoundError(f"Raw billing file not found: {path}")

    with path.open(newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns: {missing_list}")

        rows = list(reader)
        if not rows:
            raise ValueError(f"Raw billing file is empty: {path}")
        return rows


def parse_cost(value: str) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def parse_billing_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def is_unallocated(environment: str, team: str, project: str, tags: str) -> bool:
    return environment == "unknown" or team == "unknown" or project == "unallocated" or not tags


def clean_billing_data(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Normalize raw line items into consistent analytics fields."""
    cleaned = []
    for row in raw:
        tags = (row.get("tags") or "").strip()
        environment = normalize_text(row.get("environment"))
        team = normalize_text(row.get("team"))
        project = normalize_text(row.get("project"))
        service = (row.get("service") or "").strip()
        billing_date = parse_billing_date(row["billing_date"])

        cleaned.append(
            {
                "billing_date": billing_date,
                "cloud_provider": normalize_text(row.get("cloud_provider")).upper(),
                "account_id": (row.get("account_id") or "").strip(),
                "service": service,
                "region": normalize_text(row.get("region")),
                "usage_type": (row.get("usage_type") or "").strip(),
                "cost": parse_cost(row.get("cost", "0")),
                "currency": (row.get("currency") or "USD").strip().upper(),
                "environment": environment,
                "team": team,
                "project": project,
                "resource_id": normalize_text(row.get("resource_id")),
                "tags": tags,
                "is_tagged": bool(tags),
                "is_unallocated": is_unallocated(environment, team, project, tags),
            }
        )

    return sorted(
        cleaned,
        key=lambda item: (item["billing_date"], item["account_id"], item["service"], item["resource_id"]),
    )


def build_fact_table(cleaned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create the main billing fact table with stable row identifiers."""
    fact = []
    for index, row in enumerate(cleaned, start=1):
        fact.append(
            {
                "cost_id": index,
                "billing_date": row["billing_date"],
                "cloud_provider": row["cloud_provider"],
                "account_id": row["account_id"],
                "service": row["service"],
                "region": row["region"],
                "usage_type": row["usage_type"],
                "cost": row["cost"],
                "currency": row["currency"],
                "environment": row["environment"],
                "team": row["team"],
                "project": row["project"],
                "resource_id": row["resource_id"],
                "is_tagged": int(row["is_tagged"]),
                "is_unallocated": int(row["is_unallocated"]),
            }
        )
    return fact


def build_dimensions(fact: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build small lookup tables used by dashboards and SQL analysis."""
    unique_dates = sorted({row["billing_date"] for row in fact})
    dim_date = []
    for value in unique_dates:
        date_value = datetime.strptime(value, "%Y-%m-%d")
        dim_date.append(
            {
                "billing_date": value,
                "year": date_value.year,
                "month": date_value.month,
                "month_name": calendar.month_name[date_value.month],
                "day": date_value.day,
                "weekday": calendar.day_name[date_value.weekday()],
            }
        )

    service_keys = sorted({(row["service"], row["cloud_provider"]) for row in fact}, key=lambda item: (item[1], item[0]))
    dim_service = [
        {"service_id": index, "service": service, "cloud_provider": provider}
        for index, (service, provider) in enumerate(service_keys, start=1)
    ]

    team_keys = sorted({(row["team"], row["project"], row["environment"]) for row in fact})
    dim_team = [
        {"team_project_id": index, "team": team, "project": project, "environment": environment}
        for index, (team, project, environment) in enumerate(team_keys, start=1)
    ]

    return {"dim_date": dim_date, "dim_service": dim_service, "dim_team": dim_team}


def build_summary_tables(fact: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build dashboard-ready rollups and simple cost monitoring signals."""
    daily_totals: defaultdict[str, float] = defaultdict(float)
    service_totals: defaultdict[str, float] = defaultdict(float)
    unallocated_spend = 0.0

    for row in fact:
        daily_totals[row["billing_date"]] += row["cost"]
        service_totals[row["service"]] += row["cost"]
        if row["is_unallocated"]:
            unallocated_spend += row["cost"]

    daily_spend_summary = []
    rolling_values: list[float] = []
    for billing_date in sorted(daily_totals):
        daily_cost = round(daily_totals[billing_date], 2)
        rolling_values.append(daily_cost)
        window = rolling_values[-3:]
        rolling_average = round(sum(window) / len(window), 2)
        daily_spend_summary.append(
            {
                "billing_date": billing_date,
                "cost": daily_cost,
                "rolling_3_day_avg": rolling_average,
                "is_spike": int(daily_cost > rolling_average * 1.25),
            }
        )

    total_spend = round(sum(row["cost"] for row in fact), 2)
    elapsed_days = len(daily_totals)
    last_date = datetime.strptime(max(daily_totals), "%Y-%m-%d")
    days_in_month = calendar.monthrange(last_date.year, last_date.month)[1]
    forecast = round((total_spend / elapsed_days) * days_in_month, 2)
    top_service = max(service_totals.items(), key=lambda item: item[1])[0]

    return {
        "daily_spend_summary": daily_spend_summary,
        "executive_summary": [
            {
                "total_spend": total_spend,
                "elapsed_days": elapsed_days,
                "forecasted_month_end_spend": forecast,
                "unallocated_spend": round(unallocated_spend, 2),
                "top_service": top_service,
            }
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_type(value: Any) -> str:
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def write_sqlite_table(conn: sqlite3.Connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    quoted_table = quote_identifier(table_name)
    quoted_columns = [quote_identifier(column) for column in columns]
    column_defs = ", ".join(f"{column} {sqlite_type(rows[0][raw_column])}" for column, raw_column in zip(quoted_columns, columns))
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    conn.execute(f"CREATE TABLE {quoted_table} ({column_defs})")
    conn.executemany(
        f"INSERT INTO {quoted_table} ({', '.join(quoted_columns)}) VALUES ({placeholders})",
        [[row[column] for column in columns] for row in rows],
    )


def build_tables(fact: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    tables = {"fact_cloud_costs": fact}
    tables.update(build_dimensions(fact))
    tables.update(build_summary_tables(fact))
    return tables


def iter_ordered_tables(tables: dict[str, list[dict[str, Any]]]) -> Iterable[tuple[str, list[dict[str, Any]]]]:
    for table_name in TABLE_ORDER:
        yield table_name, tables[table_name]


def write_outputs(fact: list[dict[str, Any]], output_dir: Path, db_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = build_tables(fact)

    for table_name, rows in iter_ordered_tables(tables):
        write_csv(output_dir / f"{table_name}.csv", rows)

    with sqlite3.connect(db_path) as conn:
        for table_name, rows in iter_ordered_tables(tables):
            write_sqlite_table(conn, table_name, rows)
        conn.commit()


def run_pipeline(
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    raw = load_raw_billing(input_path)
    cleaned = clean_billing_data(raw)
    fact = build_fact_table(cleaned)
    write_outputs(fact, output_dir, db_path)
    summary = build_summary_tables(fact)["executive_summary"][0]
    return {"rows_processed": len(fact), **summary}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process cloud billing data into analytics-ready outputs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to raw cloud billing CSV.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for processed outputs.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="SQLite database output path.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run_pipeline(args.input, args.output_dir, args.db_path)
    print(f"Processed billing data written to {args.output_dir}")
    print(f"SQLite database written to {args.db_path}")
    print(f"Rows processed: {result['rows_processed']}")
    print(f"Total spend: ${result['total_spend']:,.2f}")
    print(f"Forecasted month-end spend: ${result['forecasted_month_end_spend']:,.2f}")
