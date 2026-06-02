from __future__ import annotations

import argparse
import json
import os
import smtplib
import sqlite3
import ssl
import urllib.request
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "processed" / "cloud_costs.db"


def query_rows(db_path: Path, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(sql, params))


def build_alert_message(db_path: Path, spike_threshold: float, ownership_threshold: float) -> str:
    daily_spikes = query_rows(
        db_path,
        """
        SELECT billing_date, cost, rolling_3_day_avg
        FROM daily_spend_summary
        WHERE is_spike = 1 OR cost >= ?
        ORDER BY billing_date DESC
        """,
        (spike_threshold,),
    )
    budget_variance = query_rows(
        db_path,
        """
        SELECT billing_month, team, actual_spend, monthly_budget, variance, status
        FROM team_budget_variance
        WHERE status IN ('over budget', 'watch')
        ORDER BY billing_month DESC, variance DESC
        """,
    )
    summary = query_rows(db_path, "SELECT total_spend, unallocated_spend, forecasted_month_end_spend FROM executive_summary")[0]
    ownership_rate = (float(summary["unallocated_spend"]) / float(summary["total_spend"])) if float(summary["total_spend"]) else 0.0

    lines = ["Cloud Cost Alert Report", ""]
    lines.append(f"Total spend: ${float(summary['total_spend']):,.2f}")
    lines.append(f"Forecasted month-end spend: ${float(summary['forecasted_month_end_spend']):,.2f}")
    lines.append(f"Unallocated spend: ${float(summary['unallocated_spend']):,.2f}")
    lines.append("")

    if daily_spikes:
        lines.append("Cost spikes:")
        for row in daily_spikes:
            lines.append(
                f"- {row['billing_date']}: ${float(row['cost']):,.2f} "
                f"(3-day avg ${float(row['rolling_3_day_avg']):,.2f})"
            )
    else:
        lines.append(f"No daily spend above ${spike_threshold:,.2f}.")
    lines.append("")

    if budget_variance:
        lines.append("Budget variance:")
        for row in budget_variance:
            lines.append(
                f"- {row['billing_month']} {row['team']}: {row['status']} by "
                f"${float(row['variance']):,.2f} on ${float(row['actual_spend']):,.2f} actual spend"
            )
    else:
        lines.append("No teams are over budget or near budget.")
    lines.append("")

    if ownership_rate >= ownership_threshold:
        lines.append(f"Ownership cleanup needed: {ownership_rate * 100:.1f}% of spend is unallocated.")
    else:
        lines.append(f"Ownership cleanup is below threshold: {ownership_rate * 100:.1f}%.")

    return "\n".join(lines)


def post_slack(message: str) -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False

    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    return True


def send_email(message: str) -> bool:
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("ALERT_EMAIL_FROM")
    recipient = os.getenv("ALERT_EMAIL_TO")
    if not all([host, username, password, sender, recipient]):
        return False

    email = EmailMessage()
    email["Subject"] = "Cloud Cost Alert Report"
    email["From"] = sender
    email["To"] = recipient
    email.set_content(message)

    port = int(os.getenv("SMTP_PORT", "465"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context) as server:
        server.login(username, password)
        server.send_message(email)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send cloud cost alerts to Slack or email.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--spike-threshold", type=float, default=500.0, help="Daily spend amount that should trigger a spike alert.")
    parser.add_argument("--ownership-threshold", type=float, default=0.10, help="Unallocated spend percentage that should trigger an ownership alert.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    alert_message = build_alert_message(args.db_path, args.spike_threshold, args.ownership_threshold)
    print(alert_message)
    delivered = [post_slack(alert_message), send_email(alert_message)]
    if not any(delivered):
        print("\nNo Slack or email settings found. Set SLACK_WEBHOOK_URL or SMTP_* variables to send alerts.")
