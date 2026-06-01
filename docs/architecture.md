# Architecture Notes

## Local Version

The local version demonstrates the complete data workflow without needing paid
cloud services or credentials.

```text
Raw billing CSV
  -> Python ETL
  -> cleaned fact and dimension tables
  -> SQLite analytics database
  -> SQL queries and Streamlit dashboard
```

## Cloud Version

The same design can be moved to AWS with small substitutions.

```text
AWS Cost and Usage Report
  -> S3 raw bucket
  -> Lambda or Glue ETL job
  -> S3 curated Parquet files
  -> Athena tables
  -> QuickSight, Power BI, or Streamlit dashboard
  -> CloudWatch metric alarms and SNS notifications
```

## Data Model

- `fact_cloud_costs`: one row per billing line item.
- `dim_date`: calendar fields for trend reporting.
- `dim_service`: cloud provider and service lookup.
- `dim_team`: team, project, and environment allocation lookup.
- `daily_spend_summary`: daily totals with simple spike detection.
- `executive_summary`: total spend, unallocated spend, top service, and forecast.

## Alerting Rules To Add Next

- Daily spend is more than 25% above the rolling 3-day average.
- Untagged spend is greater than 10% of total spend.
- Forecasted month-end spend is above budget.
- A single resource contributes more than 20% of daily spend.
