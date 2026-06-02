from __future__ import annotations

import csv
import sqlite3
import sys
from html import escape
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.process_billing_data import REQUIRED_COLUMNS, build_fact_table, build_tables, clean_billing_data

DB_PATH = ROOT / "data" / "processed" / "cloud_costs.db"
SAMPLE_CSV_PATH = ROOT / "data" / "raw" / "cloud_billing_sample.csv"
VALID_TABLES = {
    "fact_cloud_costs",
    "daily_spend_summary",
    "monthly_spend_summary",
    "team_budget_variance",
    "executive_summary",
}


def read_uploaded_csv(uploaded_file: object) -> list[dict[str, str]]:
    content = uploaded_file.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))
    missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns: {missing_list}")

    rows = list(reader)
    if not rows:
        raise ValueError("Uploaded CSV is empty.")
    return rows


def tables_from_upload(uploaded_file: object) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    raw_rows = read_uploaded_csv(uploaded_file)
    fact_rows = build_fact_table(clean_billing_data(raw_rows))
    summary_tables = build_tables(fact_rows)
    return (
        pd.DataFrame(fact_rows),
        pd.DataFrame(summary_tables["daily_spend_summary"]),
        pd.DataFrame(summary_tables["monthly_spend_summary"]),
        pd.DataFrame(summary_tables["team_budget_variance"]),
        pd.DataFrame(summary_tables["executive_summary"]).iloc[0],
    )


@st.cache_data
def load_table(table_name: str, db_mtime: float) -> pd.DataFrame:
    if table_name not in VALID_TABLES:
        raise ValueError(f"Unsupported table: {table_name}")
    if not DB_PATH.exists():
        st.error("Processed database not found. Run `python etl/process_billing_data.py` first.")
        st.stop()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def currency(value: float) -> str:
    return f"${value:,.2f}"


def percent(numerator: float, denominator: float) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def option_list(values: pd.Series) -> list[str]:
    return ["All"] + sorted(str(value) for value in values.dropna().unique().tolist())


def filtered_fact(data: pd.DataFrame, team: str, project: str, environment: str, service: str) -> pd.DataFrame:
    result = data.copy()
    if team != "All":
        result = result[result["team"] == team]
    if project != "All":
        result = result[result["project"] == project]
    if environment != "All":
        result = result[result["environment"] == environment]
    if service != "All":
        result = result[result["service"] == service]
    return result


def filtered_fact_search(data: pd.DataFrame, team: str, project: str, environment: str, service: str) -> pd.DataFrame:
    result = data.copy()
    filters = {
        "team": team,
        "project": project,
        "environment": environment,
        "service": service,
    }
    for column, value in filters.items():
        cleaned_value = value.strip()
        if cleaned_value:
            result = result[result[column].astype(str).str.contains(cleaned_value, case=False, na=False)]
    return result


def top_group(data: pd.DataFrame, group_name: str) -> tuple[str, float]:
    grouped = data.groupby(group_name)["cost"].sum().sort_values(ascending=False)
    if grouped.empty:
        return "None", 0.0
    return str(grouped.index[0]), float(grouped.iloc[0])


def daily_spend(data: pd.DataFrame) -> pd.DataFrame:
    return data.groupby("billing_date", as_index=False)["cost"].sum().sort_values("billing_date")


def spend_by(data: pd.DataFrame, group_name: str) -> pd.DataFrame:
    return (
        data.groupby(group_name, as_index=False)["cost"]
        .sum()
        .sort_values("cost", ascending=False)
    )


def scale(value: float, value_min: float, value_max: float, output_min: float, output_max: float) -> float:
    if value_max == value_min:
        return (output_min + output_max) / 2
    return output_min + ((value - value_min) / (value_max - value_min)) * (output_max - output_min)


def axis_label(value: str) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return value if len(value) <= 10 else value[:9] + "..."
    if len(value) == 7:
        return parsed.strftime("%b")
    return parsed.strftime("%b %d")


def svg_line_chart(data: pd.DataFrame, x_field: str = "billing_date", value_field: str = "cost", x_label: str = "Date") -> str:
    chart = data.copy()
    chart[value_field] = pd.to_numeric(chart[value_field], errors="coerce").fillna(0)
    if chart.empty:
        return '<div class="chart-card">No data to chart.</div>'

    width, height = 900, 420
    left, right, top, bottom = 82, 38, 32, 112
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_cost = max(float(chart[value_field].max()), 1.0)
    min_cost = 0.0
    rows = chart.to_dict("records")
    points = []
    for index, row in enumerate(rows):
        x = left + (plot_width * index / max(len(rows) - 1, 1))
        y = top + plot_height - scale(float(row[value_field]), min_cost, max_cost, 0, plot_height)
        points.append((x, y, str(row[x_field]), float(row[value_field])))

    line_points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
    y_ticks = []
    for index in range(5):
        value = max_cost * index / 4
        y = top + plot_height - scale(value, min_cost, max_cost, 0, plot_height)
        y_ticks.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" class="live-grid" />'
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" class="axis-text">{value:,.0f}</text>'
        )

    x_labels = []
    for index, (x, _, label, _) in enumerate(points):
        label_limit = 5
        label_step = max(1, round((len(points) - 1) / max(label_limit - 1, 1)))
        if len(points) <= label_limit or index % label_step == 0 or index == len(points) - 1:
            short_label = axis_label(label)
            x_labels.append(
                f'<text x="{x:.1f}" y="{height - 52}" text-anchor="middle" class="axis-text axis-date">{escape(short_label)}</text>'
            )

    circles = "".join(
        f'<circle class="live-point" style="animation-delay:{index * 70}ms" cx="{x:.1f}" cy="{y:.1f}" r="5"><title>{escape(label)}: {currency(cost)}</title></circle>'
        for index, (x, y, label, cost) in enumerate(points)
    )
    first_x, first_y = points[0][:2]
    last_x, last_y = points[-1][:2]
    area_points = f"{line_points} {last_x:.1f},{top + plot_height:.1f} {first_x:.1f},{top + plot_height:.1f}"
    latest_label = points[-1][2]
    latest_cost = points[-1][3]

    return f"""
    <div class="chart-card dark-chart-card">
      <div class="chart-meta">
        <span class="legend-line"></span><strong>{escape(x_label)} trend</strong>
        <span class="chart-hint">{escape(latest_label)}: {currency(latest_cost)}</span>
      </div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="Daily cost trend">
        <defs>
          <linearGradient id="lineAreaGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#58A6FF" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#58A6FF" stop-opacity="0.02" />
          </linearGradient>
        </defs>
        {''.join(y_ticks)}
        <polygon class="chart-area" points="{area_points}" />
        <polyline class="chart-line" points="{line_points}" fill="none" stroke="#58A6FF" stroke-width="3.5" />
        {circles}
        <circle class="live-latest-pulse" cx="{last_x:.1f}" cy="{last_y:.1f}" r="10"></circle>
        <circle class="live-latest-dot" cx="{last_x:.1f}" cy="{last_y:.1f}" r="6"><title>{escape(latest_label)}: {currency(latest_cost)}</title></circle>
        {''.join(x_labels)}
        <text x="{width / 2}" y="{height - 6}" text-anchor="middle" class="axis-title">{escape(x_label)}</text>
        <text x="18" y="{height / 2}" text-anchor="middle" transform="rotate(-90 18,{height / 2})" class="axis-title">Cost</text>
      </svg>
    </div>
    """


def svg_bar_chart(data: pd.DataFrame, x_field: str) -> str:
    chart = data.copy()
    chart["cost"] = pd.to_numeric(chart["cost"], errors="coerce").fillna(0)
    total_cost = float(chart["cost"].sum())
    chart = chart.sort_values("cost", ascending=False).head(8)
    if chart.empty:
        return '<div class="chart-card">No data to chart.</div>'

    width = 760
    row_height = 48
    top, bottom = 42, 26
    left, right = 190, 112
    height = top + bottom + row_height * len(chart)
    plot_width = width - left - right
    max_cost = max(float(chart["cost"].max()), 1.0)
    top_row = chart.iloc[0]
    top_label = str(top_row[x_field])
    top_cost = float(top_row["cost"])

    vertical_guides = []
    for index in range(4):
        x = left + plot_width * index / 3
        vertical_guides.append(f'<line x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - bottom + 2}" class="live-grid" />')

    bars = []
    labels = []
    value_labels = []
    for index, row in enumerate(chart.to_dict("records")):
        value = float(row["cost"])
        label = str(row[x_field])
        bar_width = scale(value, 0, max_cost, 0, plot_width)
        y = top + index * row_height + 11
        label_y = y + 17
        bars.append(
            f'<rect class="chart-bar horizontal-bar" style="animation-delay:{index * 55}ms" x="{left}" y="{y:.1f}" width="{bar_width:.1f}" height="22" rx="6">'
            f'<title>{escape(label)}: {currency(value)}</title></rect>'
        )
        short_label = label if len(label) <= 20 else label[:18] + "..."
        labels.append(
            f'<text x="{left - 14}" y="{label_y:.1f}" text-anchor="end" class="axis-text bar-name">{escape(short_label)}</text>'
        )
        value_labels.append(
            f'<text x="{min(left + bar_width + 10, width - right + 8):.1f}" y="{label_y:.1f}" text-anchor="start" class="bar-value">{currency(value)}</text>'
        )

    return f"""
    <div class="chart-card dark-chart-card">
      <div class="chart-meta">
        <span class="legend-bar"></span><strong>Spend by {escape(x_field.replace('_', ' ').title())}</strong>
        <span class="chart-hint">Top: {escape(top_label)} {currency(top_cost)} | Total: {currency(total_cost)}</span>
      </div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="Cost by {escape(x_field)}">
        <defs>
          <linearGradient id="barGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#58A6FF" />
            <stop offset="100%" stop-color="#FF9900" />
          </linearGradient>
        </defs>
        {''.join(vertical_guides)}
        {''.join(bars)}
        {''.join(value_labels)}
        {''.join(labels)}
      </svg>
    </div>
    """


def svg_monthly_trend_chart(data: pd.DataFrame) -> str:
    chart = data.copy()
    chart["monthly_spend"] = pd.to_numeric(chart["monthly_spend"], errors="coerce").fillna(0)
    chart["mom_change"] = pd.to_numeric(chart["mom_change"], errors="coerce").fillna(0)
    chart["mom_change_percent"] = pd.to_numeric(chart["mom_change_percent"], errors="coerce").fillna(0)
    if chart.empty:
        return '<div class="chart-card">No monthly data to chart.</div>'

    width, height = 900, 390
    left, right, top, bottom = 76, 36, 34, 62
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_cost = max(float(chart["monthly_spend"].max()), 1.0)
    rows = chart.to_dict("records")

    y_ticks = []
    for index in range(5):
        value = max_cost * index / 4
        y = top + plot_height - scale(value, 0, max_cost, 0, plot_height)
        y_ticks.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" class="live-grid" />'
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" class="live-axis">${value:,.0f}</text>'
        )

    points = []
    labels = []
    for index, row in enumerate(rows):
        month = str(row["billing_month"])
        spend = float(row["monthly_spend"])
        center_x = left + (plot_width * index / max(len(rows) - 1, 1))
        point_y = top + plot_height - scale(spend, 0, max_cost, 0, plot_height)
        points.append((center_x, point_y, month, spend))
        labels.append(
            f'<text x="{center_x:.1f}" y="{height - 30}" text-anchor="middle" class="live-axis month-label">{escape(month)}</text>'
        )

    def smooth_path(point_list: list[tuple[float, float, str, float]]) -> str:
        if len(point_list) == 1:
            x, y, _, _ = point_list[0]
            return f"M {x:.1f} {y:.1f}"
        path = [f"M {point_list[0][0]:.1f} {point_list[0][1]:.1f}"]
        for index in range(len(point_list) - 1):
            x0, y0 = point_list[max(index - 1, 0)][:2]
            x1, y1 = point_list[index][:2]
            x2, y2 = point_list[index + 1][:2]
            x3, y3 = point_list[min(index + 2, len(point_list) - 1)][:2]
            c1x = x1 + (x2 - x0) / 6
            c1y = y1 + (y2 - y0) / 6
            c2x = x2 - (x3 - x1) / 6
            c2y = y2 - (y3 - y1) / 6
            path.append(f"C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, {x2:.1f} {y2:.1f}")
        return " ".join(path)

    line_path = smooth_path(points)
    first_x, first_y = points[0][:2]
    last_x, last_y = points[-1][:2]
    area_path = f"{line_path} L {last_x:.1f} {top + plot_height:.1f} L {first_x:.1f} {top + plot_height:.1f} Z"
    circles = "".join(
        f'<circle class="live-point" style="animation-delay:{500 + index * 110}ms" cx="{x:.1f}" cy="{y:.1f}" r="5">'
        f'<title>{escape(month)}: {currency(spend)}</title></circle>'
        for index, (x, y, month, spend) in enumerate(points)
    )
    last_month = str(rows[-1]["billing_month"])
    last_spend = float(rows[-1]["monthly_spend"])
    last_change = float(rows[-1]["mom_change"])
    last_percent = float(rows[-1]["mom_change_percent"])
    direction = "up" if last_change > 0 else "down" if last_change < 0 else "flat"
    status_text = "No prior month" if len(rows) == 1 else f"{last_percent:+.1f}% vs previous month"

    return f"""
    <div class="monthly-monitor">
      <div class="live-chart-header">
        <div>
          <div class="live-chart-title">Monthly Spend Monitor</div>
          <div class="live-chart-subtitle">Spend trend across billing months.</div>
        </div>
        <div class="live-chart-stat">
          <span>Current Month</span>
          <strong>{currency(last_spend)}</strong>
          <small class="{direction}">{escape(status_text)}</small>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="Monthly spend trend">
        <defs>
          <linearGradient id="monthlyAreaGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#58A6FF" stop-opacity="0.34" />
            <stop offset="100%" stop-color="#58A6FF" stop-opacity="0.02" />
          </linearGradient>
        </defs>
        {''.join(y_ticks)}
        <path class="live-area" d="{area_path}" />
        <path class="live-line" d="{line_path}" />
        {circles}
        <circle class="live-latest-pulse" cx="{last_x:.1f}" cy="{last_y:.1f}" r="11"></circle>
        <circle class="live-latest-dot" cx="{last_x:.1f}" cy="{last_y:.1f}" r="6">
          <title>{escape(last_month)}: {currency(last_spend)}</title>
        </circle>
        {''.join(labels)}
      </svg>
    </div>
    """


def format_table(data: pd.DataFrame) -> pd.DataFrame:
    table = data.copy()
    for column in table.columns:
        if column in {"cost", "actual_spend", "monthly_budget", "variance", "monthly_spend", "previous_month_spend", "mom_change"}:
            table[column] = table[column].map(lambda value: currency(float(value)))
        elif column in {"budget_used_percent", "mom_change_percent"}:
            table[column] = table[column].map(lambda value: f"{float(value):.1f}%")
        elif column.startswith("is_"):
            table[column] = table[column].map(lambda value: "Yes" if int(value) else "No")
    return table


def show_table(data: pd.DataFrame, max_rows: int | None = None) -> None:
    table = format_table(data.head(max_rows) if max_rows else data)
    st.markdown(
        f'<div class="table-wrap">{table.to_html(index=False, classes="clean-table", escape=False)}</div>',
        unsafe_allow_html=True,
    )


def count_distinct(data: pd.DataFrame, column: str) -> int:
    return int(data[column].nunique())


def quality_score(data: pd.DataFrame) -> int:
    if data.empty:
        return 0
    ownership_rate = 1 - (float(data["is_unallocated"].sum()) / len(data))
    positive_cost_rate = float((data["cost"] > 0).sum()) / len(data)
    tagged_rate = float(data["is_tagged"].sum()) / len(data)
    return round(((ownership_rate * 0.5) + (positive_cost_rate * 0.25) + (tagged_rate * 0.25)) * 100)


def top_resources(data: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    return (
        data.groupby(["resource_id", "service", "team", "project", "environment"], as_index=False)["cost"]
        .sum()
        .sort_values("cost", ascending=False)
        .head(limit)
    )


def explain_budget_status(forecast: float, budget: float) -> str:
    if budget <= 0:
        return "Set a budget to compare forecasted spend."
    difference = forecast - budget
    if difference > 0:
        return f"Projected to exceed budget by {currency(difference)}."
    return f"Projected to stay {currency(abs(difference))} under budget."


def selected_filter_summary(team: str, project: str, environment: str, service: str) -> str:
    filters = {
        "Team": team,
        "Project": project,
        "Environment": environment,
        "Service": service,
    }
    active = [f"{name}: {value}" for name, value in filters.items() if value != "All"]
    return "All billing records" if not active else " | ".join(active)


def date_range_label(data: pd.DataFrame) -> str:
    if data.empty:
        return "No dates"
    dates = pd.to_datetime(data["billing_date"])
    return f"{dates.min().date()} to {dates.max().date()}"


def chart_summary(data: pd.DataFrame, group_name: str) -> str:
    if data.empty:
        return "No matching records."
    label, amount = top_group(data, group_name)
    return f"{label} is highest at {currency(amount)}."


def show_metric_help(label: str, value: object, help_text: str, accent: str = "blue") -> None:
    st.markdown(
        f"""
        <div class="metric-card accent-{accent}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def callout(title: str, body: str, tone: str = "info") -> None:
    st.markdown(
        f"""
        <div class="callout callout-{tone}">
            <div class="callout-title">{title}</div>
            <div class="callout-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def story_card(step: str, title: str, body: str, accent: str) -> None:
    st.markdown(
        f"""
        <div class="story-card story-{accent}">
            <div class="story-step">{step}</div>
            <div class="story-title">{title}</div>
            <div class="story-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Cloud Cost Analytics", layout="wide")

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        background: #F7F8FA;
        color: #1F2937;
    }
    [data-testid="stHeader"] {
        background: rgba(247, 248, 250, 0.94);
    }
    [data-testid="stSidebar"] {
        background: #FFFFFF;
        border-right: 1px solid #E5E7EB;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] li {
        color: #1F2937;
    }
    [data-testid="stSidebar"] .st-emotion-cache-1wivap2,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #1F2937;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    .app-hero {
        border: 1px solid #232F3E;
        border-radius: 8px;
        padding: 26px 28px;
        background: linear-gradient(135deg, #232F3E 0%, #1F2937 62%, #31445C 100%);
        margin-bottom: 18px;
        box-shadow: 0 10px 28px rgba(35, 47, 62, 0.18);
    }
    .app-hero h1 {
        margin: 0 0 8px;
        font-size: 2.4rem;
        line-height: 1.1;
        color: #FFFFFF;
    }
    .app-hero p {
        color: #E5E7EB;
        font-size: 1rem;
        margin: 0;
        max-width: 920px;
    }
    .hero-accent {
        width: 84px;
        height: 5px;
        background: #FF9900;
        border-radius: 999px;
        margin-bottom: 16px;
    }
    .workflow-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 14px 0 8px;
    }
    .workflow-step {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 14px;
        background: #ffffff;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    .workflow-step strong {
        color: #1F2937;
        display: block;
        margin-bottom: 6px;
    }
    .workflow-step span {
        color: #4B5563;
        font-size: 0.9rem;
        line-height: 1.35;
    }
    .metric-card {
        min-height: 138px;
        background: #ffffff;
        border: 1px solid #E5E7EB;
        border-top: 4px solid #FF9900;
        border-radius: 8px;
        padding: 18px 18px 16px;
        color: #1F2937;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    }
    .accent-blue { border-top-color: #38BDF8; }
    .accent-teal { border-top-color: #FF9900; }
    .accent-amber { border-top-color: #FF9900; }
    .accent-red { border-top-color: #DC2626; }
    .accent-green { border-top-color: #16A34A; }
    .accent-violet { border-top-color: #232F3E; }
    .accent-cyan { border-top-color: #38BDF8; }
    .accent-slate { border-top-color: #6B7280; }
    .metric-label {
        color: #4B5563;
        font-size: 0.88rem;
        font-weight: 700;
        margin-bottom: 10px;
    }
    .metric-value {
        color: #1F2937;
        font-size: 1.42rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 14px;
        overflow-wrap: normal;
        word-break: normal;
    }
    .metric-help {
        color: #6B7280;
        font-size: 0.9rem;
        line-height: 1.35;
    }
    .callout {
        border-radius: 8px;
        padding: 15px 16px;
        margin-bottom: 12px;
        border: 1px solid #E5E7EB;
        background: #ffffff;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    .callout-title {
        color: #1F2937;
        font-weight: 800;
        margin-bottom: 6px;
    }
    .callout-body {
        color: #4B5563;
        line-height: 1.45;
    }
    .callout-good {
        border-color: #16A34A;
        background: #F0FDF4;
    }
    .callout-warn {
        border-color: #FF9900;
        background: #FFF7E8;
    }
    .callout-info {
        border-color: #38BDF8;
        background: #EFF9FF;
    }
    .story-card {
        min-height: 150px;
        border-radius: 8px;
        padding: 16px;
        border: 1px solid #E5E7EB;
        background: #ffffff;
        margin-bottom: 12px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    .story-step {
        display: inline-block;
        padding: 4px 9px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 800;
        color: #232F3E;
        background: #FF9900;
        margin-bottom: 10px;
    }
    .story-title {
        color: #1F2937;
        font-weight: 800;
        font-size: 1.02rem;
        margin-bottom: 6px;
    }
    .story-body {
        color: #4B5563;
        line-height: 1.45;
        font-size: 0.94rem;
    }
    .story-teal { border-top: 4px solid #FF9900; }
    .story-blue { border-top: 4px solid #38BDF8; }
    .story-amber { border-top: 4px solid #FF9900; }
    .story-red { border-top: 4px solid #DC2626; }
    .plain-list {
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 18px 20px;
        background: #ffffff;
        color: #4B5563;
        line-height: 1.65;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    .clean-table {
        width: 100%;
        min-width: 680px;
        border-collapse: separate;
        border-spacing: 0;
        background: #FFFFFF;
        color: #1F2937;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
        font-size: 0.92rem;
    }
    .table-wrap {
        width: 100%;
        overflow-x: auto;
        margin-bottom: 18px;
        border-radius: 8px;
    }
    .clean-table th {
        background: #232F3E;
        color: #FFFFFF;
        text-align: left;
        padding: 11px 12px;
        font-weight: 800;
        border-bottom: 1px solid #E5E7EB;
    }
    .clean-table td {
        background: #FFFFFF;
        color: #1F2937;
        padding: 10px 12px;
        border-bottom: 1px solid #EEF2F7;
    }
    .clean-table tr:nth-child(even) td {
        background: #F7F8FA;
    }
    .clean-table tr:last-child td {
        border-bottom: 0;
    }
    .chart-card {
        width: 100%;
        background:
            radial-gradient(circle at 80% 0%, rgba(88, 166, 255, 0.16), transparent 34%),
            linear-gradient(180deg, #111827 0%, #0D1117 100%);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        box-shadow: 0 18px 38px rgba(15, 23, 42, 0.18);
        padding: 20px 22px 12px;
        margin-bottom: 18px;
        overflow-x: auto;
    }
    .chart-meta {
        display: flex;
        align-items: center;
        gap: 9px;
        color: #F9FAFB;
        font-size: 0.9rem;
        margin: 2px 4px 10px;
    }
    .chart-hint {
        color: #8B949E;
        margin-left: auto;
        font-size: 0.84rem;
    }
    .legend-line {
        display: inline-block;
        width: 28px;
        height: 3px;
        background: #38BDF8;
        border-radius: 999px;
    }
    .legend-bar {
        display: inline-block;
        width: 14px;
        height: 14px;
        background: #38BDF8;
        border-radius: 3px;
    }
    .live-chart-card {
        background:
            linear-gradient(180deg, rgba(255, 153, 0, 0.08), rgba(255, 255, 255, 0) 32%),
            #FFFFFF;
    }
    .live-chart-panel {
        width: 100%;
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: #0D1117;
        box-shadow: 0 18px 36px rgba(15, 23, 42, 0.16);
        padding: 24px 26px 14px;
        margin: 16px 0 20px;
        overflow-x: auto;
    }
    .monthly-monitor {
        width: 100%;
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.2);
        background:
            radial-gradient(circle at 80% 0%, rgba(88, 166, 255, 0.16), transparent 34%),
            linear-gradient(180deg, #111827 0%, #0D1117 100%);
        box-shadow: 0 18px 38px rgba(15, 23, 42, 0.22);
        padding: 24px 26px 14px;
        margin: 16px 0 20px;
        overflow-x: auto;
    }
    .monthly-monitor svg {
        display: block;
        min-width: 0;
        width: 100%;
    }
    .live-chart-panel svg {
        display: block;
        min-width: 700px;
        width: 100%;
    }
    .live-chart-header {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        align-items: flex-start;
        margin-bottom: 8px;
    }
    .live-chart-title {
        color: #F9FAFB;
        font-weight: 800;
        font-size: 1.08rem;
        margin-bottom: 5px;
    }
    .live-chart-subtitle {
        color: #8B949E;
        font-size: 0.94rem;
    }
    .live-chart-stat {
        text-align: right;
        min-width: 190px;
    }
    .live-chart-stat span {
        color: #6B7280;
        display: block;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 5px;
    }
    .live-chart-stat strong {
        color: #F9FAFB;
        display: block;
        font-size: 1.25rem;
        line-height: 1.2;
    }
    .live-chart-stat small {
        color: #8B949E;
        display: block;
        margin-top: 5px;
        font-size: 0.78rem;
    }
    .live-chart-stat small.up { color: #86EFAC; }
    .live-chart-stat small.down { color: #FCA5A5; }
    .live-chart-stat small.flat { color: #93C5FD; }
    .live-grid {
        stroke: rgba(148, 163, 184, 0.16);
        stroke-dasharray: 4 6;
    }
    .live-axis {
        fill: #8B949E;
        font-size: 12px;
        font-weight: 700;
    }
    .live-area {
        fill: url(#monthlyAreaGradient);
        opacity: 0;
        animation: live-fade 0.55s ease-out 0.25s forwards;
    }
    .live-line {
        fill: none;
        stroke: #58A6FF;
        stroke-width: 4;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-dasharray: 2600;
        stroke-dashoffset: 2600;
        filter: drop-shadow(0 0 8px rgba(88, 166, 255, 0.42));
        animation: draw-line 1.25s ease-out forwards;
    }
    .live-point {
        fill: #FF9900;
        stroke: #0D1117;
        stroke-width: 3;
        opacity: 0;
        animation: point-pop 0.35s ease-out forwards;
    }
    .live-latest-dot {
        fill: #58A6FF;
        stroke: #FFFFFF;
        stroke-width: 3;
        filter: drop-shadow(0 0 8px rgba(88, 166, 255, 0.7));
    }
    .live-latest-pulse {
        fill: rgba(88, 166, 255, 0.2);
        stroke: rgba(88, 166, 255, 0.65);
        transform-box: fill-box;
        transform-origin: center;
        animation: live-pulse 1.7s ease-out infinite;
    }
    @keyframes live-fade {
        to { opacity: 1; }
    }
    @keyframes live-pulse {
        0% { transform: scale(0.72); opacity: 0.9; }
        70% { transform: scale(1.85); opacity: 0; }
        100% { transform: scale(1.85); opacity: 0; }
    }
    .chart-card svg {
        width: 100%;
        min-width: 0;
        display: block;
    }
    .chart-area {
        fill: url(#lineAreaGradient);
        opacity: 0;
        animation: live-fade 0.55s ease-out 0.25s forwards;
    }
    .chart-line {
        stroke-dasharray: 10000;
        stroke-dashoffset: 10000;
        stroke-linecap: round;
        stroke-linejoin: round;
        filter: drop-shadow(0 0 8px rgba(88, 166, 255, 0.42));
        animation: draw-line 1.05s ease-out forwards;
    }
    .chart-point {
        transform-box: fill-box;
        transform-origin: center;
        opacity: 0;
        animation: point-pop 0.42s ease-out forwards;
    }
    .chart-bar {
        fill: url(#barGradient);
        transform-box: fill-box;
        transform-origin: left center;
        animation: bar-grow-x 0.65s ease-out both;
        filter: drop-shadow(0 8px 10px rgba(15, 23, 42, 0.22));
    }
    .bar-name {
        fill: #F3F4F6;
        font-size: 15px;
        font-weight: 800;
    }
    .monthly-bar {
        fill: url(#monthlyGradient);
        transform-box: fill-box;
        transform-origin: bottom;
        animation: bar-grow 0.78s cubic-bezier(.2,.8,.2,1) both;
        filter: drop-shadow(0 8px 10px rgba(35, 47, 62, 0.12));
    }
    .monthly-line {
        filter: drop-shadow(0 3px 5px rgba(35, 47, 62, 0.18));
    }
    .month-label {
        font-weight: 800;
    }
    .month-value {
        fill: #232F3E;
        font-size: 13px;
        font-weight: 800;
    }
    .mom-badge {
        height: 24px;
        line-height: 24px;
        border-radius: 999px;
        text-align: center;
        font-size: 12px;
        font-weight: 800;
        border: 1px solid #E5E7EB;
        background: #FFFFFF;
        color: #1F2937;
        box-shadow: 0 5px 12px rgba(15, 23, 42, 0.08);
        animation: point-pop 0.42s ease-out both;
    }
    .mom-badge.positive {
        background: #ECFDF5;
        border-color: #16A34A;
        color: #166534;
    }
    .mom-badge.negative {
        background: #FEF2F2;
        border-color: #DC2626;
        color: #991B1B;
    }
    .mom-badge.neutral {
        background: #EFF9FF;
        border-color: #38BDF8;
        color: #075985;
    }
    @keyframes draw-line {
        to { stroke-dashoffset: 0; }
    }
    @keyframes point-pop {
        0% { opacity: 0; transform: scale(0.35); }
        100% { opacity: 1; transform: scale(1); }
    }
    @keyframes bar-grow {
        0% { transform: scaleY(0.05); opacity: 0.25; }
        100% { transform: scaleY(1); opacity: 1; }
    }
    @keyframes bar-grow-x {
        0% { transform: scaleX(0.04); opacity: 0.25; }
        100% { transform: scaleX(1); opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
        .chart-line, .chart-point, .chart-bar {
            animation: none;
            opacity: 1;
            stroke-dashoffset: 0;
        }
    }
    .axis-text {
        fill: #D1D5DB;
        font-size: 15px;
        font-weight: 700;
    }
    .axis-date {
        fill: #E5E7EB;
        font-size: 16px;
        font-weight: 800;
    }
    .axis-title {
        fill: #D1D5DB;
        font-size: 16px;
        font-weight: 700;
    }
    .bar-value {
        fill: #F9FAFB;
        font-size: 13px;
        font-weight: 800;
        paint-order: stroke;
        stroke: #0D1117;
        stroke-width: 4px;
        stroke-linejoin: round;
    }
    @media (max-width: 900px) {
        .workflow-grid {
            grid-template-columns: 1fr;
        }
        .app-hero h1 {
            font-size: 1.9rem;
        }
    }
    div[data-testid="stCaptionContainer"] {
        color: #6B7280;
    }
    div[data-testid="stTabs"] button {
        color: #1F2937 !important;
        font-weight: 700;
        background: transparent !important;
        border: 0 !important;
    }
    div[data-testid="stTabs"] button * {
        color: #1F2937 !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #232F3E !important;
        border-bottom-color: #FF9900 !important;
    }
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stFileUploader"] button,
    div[data-testid="stButton"] button {
        background: #232F3E !important;
        color: #FFFFFF !important;
        border: 1px solid #232F3E !important;
        font-weight: 700;
    }
    div[data-testid="stDownloadButton"] button *,
    div[data-testid="stFileUploader"] button *,
    div[data-testid="stButton"] button * {
        color: #FFFFFF !important;
    }
    div[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button {
        width: 100%;
        min-height: 44px;
        border-radius: 8px;
    }
    div[data-testid="stFileUploader"] section {
        background: #F7F8FA !important;
        border: 1px dashed #CBD5E1 !important;
        border-radius: 8px !important;
        padding: 12px !important;
    }
    div[data-testid="stFileUploader"] section > div {
        color: #1F2937 !important;
    }
    div[data-testid="stFileUploader"] small {
        color: #6B7280 !important;
    }
    div[data-testid="stFileUploader"] button {
        min-height: 38px;
        border-radius: 8px;
        padding: 0 14px;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
        display: none !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] div {
        color: #1F2937 !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] small {
        color: #6B7280 !important;
    }
    div[data-testid="stFileUploader"] ul {
        display: none !important;
    }
    div[data-testid="stDownloadButton"] button:hover,
    div[data-testid="stFileUploader"] button:hover,
    div[data-testid="stButton"] button:hover {
        background: #FF9900 !important;
        color: #232F3E !important;
        border-color: #FF9900 !important;
    }
    div[data-testid="stDownloadButton"] button:hover *,
    div[data-testid="stFileUploader"] button:hover *,
    div[data-testid="stButton"] button:hover * {
        color: #232F3E !important;
    }
    button[data-testid="stBaseButton-elementToolbar"] {
        display: none !important;
    }
    label, [data-testid="stWidgetLabel"] {
        color: #1F2937 !important;
    }
    div[role="radiogroup"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 8px;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }
    div[role="radiogroup"] label,
    div[role="radiogroup"] label * {
        color: #1F2937 !important;
    }
    div[role="radiogroup"] label {
        background: #F7F8FA;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 8px 13px;
        min-height: 38px;
    }
    div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: #232F3E;
        border-color: #FF9900;
    }
    div[role="radiogroup"] label:has(input:checked) *,
    div[role="radiogroup"] label:has(input:checked) p {
        color: #FFFFFF !important;
    }
    div[role="radiogroup"] svg {
        fill: #FF9900 !important;
        color: #FF9900 !important;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"],
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background: #FFFFFF !important;
        color: #1F2937 !important;
        border-color: #CBD5E1 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"] * {
        color: #1F2937 !important;
        fill: #1F2937 !important;
    }
    div[data-testid="stSelectbox"] svg {
        color: #1F2937 !important;
        fill: #1F2937 !important;
    }
    [data-baseweb="popover"] [role="listbox"],
    [data-baseweb="popover"] ul,
    [data-baseweb="menu"] ul {
        background: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
    }
    [data-baseweb="popover"] li,
    [data-baseweb="menu"] li,
    [role="option"] {
        background: #FFFFFF !important;
        color: #1F2937 !important;
    }
    [data-baseweb="popover"] li:hover,
    [data-baseweb="menu"] li:hover,
    [role="option"]:hover {
        background: #FFF7E8 !important;
        color: #1F2937 !important;
    }
    input,
    textarea,
    [contenteditable="true"],
    [data-baseweb="input"] input {
        background: #FFFFFF !important;
        color: #1F2937 !important;
        border-color: #CBD5E1 !important;
    }
    input::placeholder,
    textarea::placeholder {
        color: #6B7280 !important;
        opacity: 1 !important;
    }
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [role="dialog"],
    [data-testid="stPopover"] {
        background: #FFFFFF !important;
        color: #1F2937 !important;
    }
    [data-baseweb="popover"] div,
    [data-baseweb="menu"] div {
        background-color: #FFFFFF !important;
        color: #1F2937 !important;
    }
    [data-baseweb="popover"] *,
    [data-baseweb="menu"] *,
    [role="dialog"] *,
    [data-testid="stPopover"] * {
        color: #1F2937 !important;
    }
    [data-baseweb="select"] {
        background: #FFFFFF !important;
        border-color: #CBD5E1 !important;
    }
    [data-baseweb="select"] *,
    [data-baseweb="select"] svg {
        color: #1F2937 !important;
        fill: #1F2937 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-hero">
        <div class="hero-accent"></div>
        <h1>Cloud Cost Analytics</h1>
        <p>
            A simple dashboard for understanding cloud bills. Upload a CSV,
            find the biggest cost drivers, catch missing ownership, compare
            spend against a budget, and export organized data.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Start Here")
    st.caption("Use the sample data or upload your own CSV.")
    uploaded_file = st.file_uploader("Upload your billing CSV", type=["csv"])
    if uploaded_file is not None:
        st.success(f"File ready: {uploaded_file.name}")
    else:
        st.info("No upload yet. Sample data is active.")
    st.download_button(
        "Download CSV Template",
        data=SAMPLE_CSV_PATH.read_text(),
        file_name="cloud_billing_template.csv",
        mime="text/csv",
    )
    st.divider()
    st.subheader("Steps")
    st.markdown(
        """
        1. Upload CSV
        2. Review Overview
        3. Explore Costs
        4. Check Problems
        5. Download Results
        """
    )
    st.divider()
    st.subheader("Explain it simply")
    st.markdown(
        """
        This app answers:

        - What are we spending?
        - Who owns the spend?
        - What service costs most?
        - Are there problem areas?
        """
    )
    with st.expander("CSV columns needed"):
        st.code("\n".join(sorted(REQUIRED_COLUMNS)))

if uploaded_file is not None:
    try:
        fact, daily, monthly, team_budget_variance, summary = tables_from_upload(uploaded_file)
        data_source = uploaded_file.name
        st.success(f"Using uploaded file: {uploaded_file.name}")
    except Exception as exc:
        st.error(str(exc))
        st.stop()
else:
    db_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0
    fact = load_table("fact_cloud_costs", db_mtime)
    daily = load_table("daily_spend_summary", db_mtime)
    monthly = load_table("monthly_spend_summary", db_mtime)
    team_budget_variance = load_table("team_budget_variance", db_mtime)
    summary = load_table("executive_summary", db_mtime).iloc[0]
    data_source = "included sample data"

total_spend = float(summary["total_spend"])
forecasted_spend = float(summary["forecasted_month_end_spend"])
unallocated_spend = float(summary["unallocated_spend"])
top_service = str(summary["top_service"])
top_team, top_team_spend = top_group(fact, "team")
quality = quality_score(fact)
record_count = len(fact)

st.markdown(
    """
    <div class="workflow-grid">
        <div class="workflow-step"><strong>1. Upload</strong><span>Use sample billing data or upload your own CSV.</span></div>
        <div class="workflow-step"><strong>2. Clean</strong><span>The app standardizes fields and flags missing ownership.</span></div>
        <div class="workflow-step"><strong>3. Analyze</strong><span>Charts show services, teams, trends, and resources.</span></div>
        <div class="workflow-step"><strong>4. Export</strong><span>Download organized results for reporting or SQL work.</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write(f"Data source: **{data_source}** | Records analyzed: **{record_count}**")

selected_section = st.radio(
    "Dashboard section",
    ["Overview", "Explore Costs", "Problem Areas", "Data"],
    horizontal=True,
    label_visibility="collapsed",
    key="dashboard_section",
)

if selected_section == "Overview":
    st.subheader("Quick Summary")
    metric_cols = st.columns(4)
    with metric_cols[0]:
        show_metric_help("Total Spend", currency(total_spend), "How much this data has cost so far.", "teal")
    with metric_cols[1]:
        show_metric_help("Month-End Estimate", currency(forecasted_spend), "Projected cost if spending continues at this pace.", "blue")
    with metric_cols[2]:
        show_metric_help("Needs Ownership", currency(unallocated_spend), "Spend missing a clear team, project, environment, or tag.", "red")
    with metric_cols[3]:
        show_metric_help("Highest Service", top_service, "The cloud service with the largest total cost.", "amber")

    second_metric_cols = st.columns(4)
    with second_metric_cols[0]:
        show_metric_help("Data Quality", f"{quality}/100", "Score based on ownership, tags, and valid costs.", "green")
    with second_metric_cols[1]:
        show_metric_help("Services", count_distinct(fact, "service"), "Number of different cloud services found.", "violet")
    with second_metric_cols[2]:
        show_metric_help("Teams", count_distinct(fact, "team"), "Number of teams or owners in the billing data.", "cyan")
    with second_metric_cols[3]:
        show_metric_help("Resources", count_distinct(fact, "resource_id"), "Number of unique cloud resources found.", "slate")

    st.progress(
        min(unallocated_spend / total_spend, 1.0) if total_spend else 0,
        text=f"{percent(unallocated_spend, total_spend)} of spend needs ownership cleanup",
    )

    st.subheader("What This Means")
    insight_cols = st.columns(4)
    with insight_cols[0]:
        story_card("Insight 1", "Main cost driver", f"<strong>{top_service}</strong> is the biggest service cost.", "teal")
    with insight_cols[1]:
        story_card("Insight 2", "Largest owner", f"<strong>{top_team}</strong> owns the highest spend: <strong>{currency(top_team_spend)}</strong>.", "blue")
    with insight_cols[2]:
        story_card("Insight 3", "Forecast", f"At this pace, the estimated monthly bill is <strong>{currency(forecasted_spend)}</strong>.", "amber")
    with insight_cols[3]:
        story_card("Insight 4", "Cleanup", f"<strong>{percent(unallocated_spend, total_spend)}</strong> of spend needs ownership cleanup.", "red")

    st.subheader("Budget Check")
    default_budget = max(1000, int(round(forecasted_spend / 500) * 500))
    st.caption("Enter a monthly budget to compare it against the forecast.")
    preset_cols = st.columns(4)
    preset_values = [5000, 10000, 15000, 20000]
    for index, preset in enumerate(preset_values):
        if preset_cols[index].button(currency(preset), key=f"budget_preset_{preset}"):
            st.session_state["monthly_budget_target"] = preset

    if "monthly_budget_target" not in st.session_state:
        st.session_state["monthly_budget_target"] = default_budget

    monthly_budget = st.number_input(
        "Monthly budget target",
        min_value=0,
        max_value=100000,
        value=int(st.session_state["monthly_budget_target"]),
        step=500,
        help="Type your target budget or use one of the preset buttons.",
    )
    st.session_state["monthly_budget_target"] = int(monthly_budget)
    budget_tone = "warn" if forecasted_spend > monthly_budget else "good"
    callout("Budget status", explain_budget_status(forecasted_spend, monthly_budget), budget_tone)

    st.subheader("Daily Cost Trend")
    st.markdown(svg_line_chart(daily_spend(fact)), unsafe_allow_html=True)
    with st.expander("Daily trend values"):
        show_table(daily_spend(fact))

    st.subheader("Monthly Trend")
    st.caption("Month-over-month analysis shows whether spend is rising, falling, or stable across billing months.")
    st.markdown(svg_monthly_trend_chart(monthly), unsafe_allow_html=True)
    show_table(monthly)

    st.subheader("Team Budget Variance")
    st.caption("Compares each team's actual monthly spend with the monthly budget in config/team_budgets.csv.")
    if team_budget_variance.empty:
        st.info("No team budget variance data available.")
    else:
        show_table(team_budget_variance.sort_values(["billing_month", "variance"], ascending=[False, False]))

if selected_section == "Explore Costs":
    st.subheader("Filter The Data")
    st.caption("Choose values found in the billing data. Select All to include every value.")
    team_options = option_list(fact["team"])
    project_options = option_list(fact["project"])
    environment_options = option_list(fact["environment"])
    service_options = option_list(fact["service"])

    filter_cols = st.columns(4)
    selected_team = filter_cols[0].selectbox("Team", team_options)
    selected_project = filter_cols[1].selectbox("Project", project_options)
    selected_environment = filter_cols[2].selectbox("Environment", environment_options)
    selected_service = filter_cols[3].selectbox("Service", service_options)

    filtered = filtered_fact(fact, selected_team, selected_project, selected_environment, selected_service)

    if filtered.empty:
        st.warning("No billing records match the selected filters.")
        st.stop()

    filtered_total = float(filtered["cost"].sum())
    st.subheader("What You Are Viewing")
    context_cols = st.columns(4)
    with context_cols[0]:
        show_metric_help("Selected Data", selected_filter_summary(selected_team, selected_project, selected_environment, selected_service), "The current filter selection.", "amber")
    with context_cols[1]:
        show_metric_help("Filtered Spend", currency(filtered_total), "Total spend for the selected data.", "teal")
    with context_cols[2]:
        show_metric_help("Rows", len(filtered), "Billing records included in the charts.", "cyan")
    with context_cols[3]:
        show_metric_help("Date Range", date_range_label(filtered), "Dates included in the selected data.", "blue")

    st.subheader("Filtered Daily Trend")
    callout(
        "Chart context",
        f"Showing daily spend for <strong>{selected_filter_summary(selected_team, selected_project, selected_environment, selected_service)}</strong> across <strong>{date_range_label(filtered)}</strong>.",
        "info",
    )
    daily_filtered = daily_spend(filtered)
    st.markdown(svg_line_chart(daily_filtered), unsafe_allow_html=True)
    with st.expander("Daily trend values"):
        show_table(daily_filtered)

    st.subheader("Spend by Service")
    service_spend = spend_by(filtered, "service")
    st.caption(chart_summary(filtered, "service"))
    st.markdown(svg_bar_chart(service_spend, "service"), unsafe_allow_html=True)
    with st.expander("Service spend values"):
        show_table(service_spend)

    st.subheader("Spend by Team")
    team_spend = spend_by(filtered, "team")
    st.caption(chart_summary(filtered, "team"))
    st.markdown(svg_bar_chart(team_spend, "team"), unsafe_allow_html=True)
    with st.expander("Team spend values"):
        show_table(team_spend)

    st.subheader("Filtered Summary Table")
    summary_by_project = (
        filtered.groupby(["team", "project", "environment"], as_index=False)["cost"]
        .sum()
        .sort_values("cost", ascending=False)
    )
    show_table(summary_by_project)

if selected_section == "Problem Areas":
    st.subheader("Costs To Investigate")
    st.caption("These areas usually matter because they can point to waste, missing ownership, or surprise bills.")

    if unallocated_spend > 0:
        callout(
            "Ownership cleanup needed",
            f"{currency(unallocated_spend)} is missing a clear owner. In real cloud teams, this makes chargeback and accountability harder.",
            "warn",
        )
    else:
        callout("Ownership looks clean", "Every line item has enough team, project, environment, and tag information.", "good")

    st.subheader("Cost Spikes")
    spikes = daily[daily["is_spike"] == 1]
    if spikes.empty:
        st.success("No daily cost spikes detected.")
    else:
        show_table(spikes.sort_values("billing_date", ascending=False))

    st.subheader("Spend Missing Ownership")
    untagged = (
        fact[fact["is_unallocated"] == 1]
        .groupby(["team", "project", "environment"], as_index=False)["cost"]
        .sum()
        .sort_values("cost", ascending=False)
    )
    if untagged.empty:
        st.success("No unallocated or untagged spend found.")
    else:
        show_table(untagged)

    st.subheader("Top 10 Resources")
    show_table(top_resources(fact))

if selected_section == "Data":
    st.subheader("Organized Billing Data")
    st.caption("This is the cleaned table created from the uploaded billing file.")
    show_table(fact.sort_values("billing_date", ascending=False), max_rows=100)
    st.download_button(
        "Download organized billing table",
        data=fact.to_csv(index=False),
        file_name="organized_cloud_costs.csv",
        mime="text/csv",
    )
