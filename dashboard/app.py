from __future__ import annotations

import csv
import sqlite3
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.process_billing_data import REQUIRED_COLUMNS, build_fact_table, build_summary_tables, clean_billing_data

DB_PATH = ROOT / "data" / "processed" / "cloud_costs.db"
SAMPLE_CSV_PATH = ROOT / "data" / "raw" / "cloud_billing_sample.csv"
VALID_TABLES = {
    "fact_cloud_costs",
    "daily_spend_summary",
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


def tables_from_upload(uploaded_file: object) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    raw_rows = read_uploaded_csv(uploaded_file)
    fact_rows = build_fact_table(clean_billing_data(raw_rows))
    summary_tables = build_summary_tables(fact_rows)
    return (
        pd.DataFrame(fact_rows),
        pd.DataFrame(summary_tables["daily_spend_summary"]),
        pd.DataFrame(summary_tables["executive_summary"]).iloc[0],
    )


@st.cache_data
def load_table(table_name: str) -> pd.DataFrame:
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


def show_metric_help(label: str, value: object, help_text: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Cloud Cost Analytics", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    .metric-card {
        min-height: 138px;
        background: #111827;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 18px 18px 16px;
        color: #f8fafc;
    }
    .metric-label {
        color: #cbd5e1;
        font-size: 0.88rem;
        font-weight: 700;
        margin-bottom: 10px;
    }
    .metric-value {
        color: #ffffff;
        font-size: 1.55rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 14px;
        overflow-wrap: anywhere;
    }
    .metric-help {
        color: #94a3b8;
        font-size: 0.9rem;
        line-height: 1.35;
    }
    div[data-testid="stCaptionContainer"] {
        color: #94a3b8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Cloud Cost Analytics")
st.caption("Upload cloud billing data and see where the money is going.")

with st.sidebar:
    st.header("Start Here")
    uploaded_file = st.file_uploader("Upload your billing CSV", type=["csv"])
    st.download_button(
        "Download sample CSV",
        data=SAMPLE_CSV_PATH.read_text(),
        file_name="cloud_billing_sample.csv",
        mime="text/csv",
    )
    st.info("No file yet? The dashboard uses sample data automatically.")
    with st.expander("CSV columns needed"):
        st.code("\n".join(sorted(REQUIRED_COLUMNS)))

if uploaded_file is not None:
    try:
        fact, daily, summary = tables_from_upload(uploaded_file)
        data_source = uploaded_file.name
        st.success(f"Using uploaded file: {uploaded_file.name}")
    except Exception as exc:
        st.error(str(exc))
        st.stop()
else:
    fact = load_table("fact_cloud_costs")
    daily = load_table("daily_spend_summary")
    summary = load_table("executive_summary").iloc[0]
    data_source = "included sample data"

total_spend = float(summary["total_spend"])
forecasted_spend = float(summary["forecasted_month_end_spend"])
unallocated_spend = float(summary["unallocated_spend"])
top_service = str(summary["top_service"])
top_team, top_team_spend = top_group(fact, "team")

st.write(f"Data source: **{data_source}**")

overview_tab, explore_tab, problem_tab, data_tab = st.tabs(
    ["Overview", "Explore Costs", "Problem Areas", "Data"]
)

with overview_tab:
    st.subheader("Quick Summary")
    metric_cols = st.columns(4)
    with metric_cols[0]:
        show_metric_help("Total Spend", currency(total_spend), "How much this data has cost so far.")
    with metric_cols[1]:
        show_metric_help("Month-End Estimate", currency(forecasted_spend), "Projected cost if spending continues at this pace.")
    with metric_cols[2]:
        show_metric_help("Needs Ownership", currency(unallocated_spend), "Spend missing a clear team, project, environment, or tag.")
    with metric_cols[3]:
        show_metric_help("Highest Service", top_service, "The cloud service with the largest total cost.")

    st.progress(
        min(unallocated_spend / total_spend, 1.0) if total_spend else 0,
        text=f"{percent(unallocated_spend, total_spend)} of spend needs ownership cleanup",
    )

    insight_cols = st.columns(3)
    with insight_cols[0]:
        st.info(f"Biggest service cost: **{top_service}**.")
    with insight_cols[1]:
        st.info(f"Biggest team spend: **{top_team}** at **{currency(top_team_spend)}**.")
    with insight_cols[2]:
        st.info(f"The projected monthly bill is **{currency(forecasted_spend)}**.")

    st.subheader("Daily Cost Trend")
    st.line_chart(daily_spend(fact), x="billing_date", y="cost")

with explore_tab:
    st.subheader("Filter The Data")
    filter_cols = st.columns(4)
    teams = option_list(fact["team"])
    projects = option_list(fact["project"])
    environments = option_list(fact["environment"])
    services = option_list(fact["service"])

    selected_team = filter_cols[0].selectbox("Team", teams)
    selected_project = filter_cols[1].selectbox("Project", projects)
    selected_environment = filter_cols[2].selectbox("Environment", environments)
    selected_service = filter_cols[3].selectbox("Service", services)

    filtered = filtered_fact(fact, selected_team, selected_project, selected_environment, selected_service)

    if filtered.empty:
        st.warning("No billing records match the selected filters.")
        st.stop()

    st.subheader("Filtered Daily Trend")
    st.line_chart(daily_spend(filtered), x="billing_date", y="cost")

    left, right = st.columns(2)

    with left:
        st.subheader("Spend by Service")
        st.bar_chart(spend_by(filtered, "service"), x="service", y="cost")

    with right:
        st.subheader("Spend by Team")
        st.bar_chart(spend_by(filtered, "team"), x="team", y="cost")

with problem_tab:
    st.subheader("Costs To Investigate")
    st.caption("These areas usually matter because they can point to waste, missing ownership, or surprise bills.")

    issue_cols = st.columns(2)
    with issue_cols[0]:
        st.subheader("Cost Spikes")
        spikes = daily[daily["is_spike"] == 1]
        if spikes.empty:
            st.success("No daily cost spikes detected.")
        else:
            st.dataframe(spikes.sort_values("billing_date", ascending=False), use_container_width=True, hide_index=True)

    with issue_cols[1]:
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
            st.dataframe(untagged, use_container_width=True, hide_index=True)

    st.subheader("Top 10 Resources")
    top_resources = (
        fact.groupby(["resource_id", "service", "team", "project", "environment"], as_index=False)["cost"]
        .sum()
        .sort_values("cost", ascending=False)
        .head(10)
    )
    st.dataframe(top_resources, use_container_width=True, hide_index=True)

with data_tab:
    st.subheader("Organized Billing Data")
    st.dataframe(fact.sort_values("billing_date", ascending=False), use_container_width=True, hide_index=True)
    st.download_button(
        "Download organized billing table",
        data=fact.to_csv(index=False),
        file_name="organized_cloud_costs.csv",
        mime="text/csv",
    )
