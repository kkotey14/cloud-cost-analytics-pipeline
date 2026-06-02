# Cloud Cost Analytics Pipeline

A portfolio-ready analytics project for cloud engineering and data analyst roles.
It ingests cloud billing records, cleans and models the data, stores analytics
tables in SQLite, and powers SQL analysis plus a Streamlit dashboard.

The app runs locally without AWS credentials, but the project now includes a
cloud-ready path: the ETL can read `s3://` billing files, Terraform defines AWS
storage and alerting infrastructure, and an alert script can send cost spike
reports to Slack or email.

## Architecture

```text
data/raw/cloud_billing_sample.csv
        |
        v
etl/process_billing_data.py
        |
        +--> data/processed/fact_cloud_costs.csv
        +--> data/processed/dim_date.csv
        +--> data/processed/dim_service.csv
        +--> data/processed/dim_team.csv
        +--> data/processed/monthly_spend_summary.csv
        +--> data/processed/team_budget_variance.csv
        +--> data/processed/cloud_costs.db
        |
        v
sql/*.sql + dashboard/app.py + alerts/send_alerts.py
```

## What It Answers

- Which cloud services cost the most?
- Which teams, projects, and environments drive spend?
- How much cost is untagged or poorly allocated?
- Did spend spike compared with recent history?
- What is the projected month-end spend?
- How does this month compare to last month?
- Which teams are over or near budget?

## Dashboard Features

- Browser upload for your own billing CSV.
- Clear overview cards for spend, forecast, ownership issues, services, teams,
  resources, and data quality.
- Budget slider to compare projected month-end spend against a target.
- Guided tabs for overview, cost exploration, problem areas, and organized data.
- Animated custom SVG charts with plain-text tables behind every visual.
- Team budget variance reporting from `config/team_budgets.csv`.
- Multi-month trend and month-over-month change analysis.
- Mixed-color visual system with simple labels so non-technical users can
  understand the dashboard quickly.
- Download button for the cleaned billing table.

## Quick Start

From the project folder:

```bash
cd /Users/kingsleykotey/cloud-cost-analytics-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python etl/process_billing_data.py
streamlit run dashboard/app.py
```

Then open [http://localhost:8501](http://localhost:8501).

## Upload Your Own Data In The Website

The dashboard has a CSV uploader in the left sidebar.

1. Open the dashboard at [http://localhost:8501](http://localhost:8501).
2. Click **Upload billing CSV** in the sidebar.
3. Choose your CSV file.
4. The dashboard will validate the file, organize the data, and update the
   charts automatically.
5. Click **Download organized billing table** at the bottom to export the
   cleaned version of the current filtered view.

Your uploaded CSV must include these columns:

```text
account_id
billing_date
cloud_provider
cost
currency
environment
project
region
resource_id
service
tags
team
usage_type
```

If you want to see the correct format, use the **Download CSV Template** button
inside the sidebar.

If you already installed the dependencies, you can restart the dashboard with:

```bash
cd /Users/kingsleykotey/cloud-cost-analytics-pipeline
source .venv/bin/activate
streamlit run dashboard/app.py
```

You can also use the `Makefile` shortcuts:

```bash
make install
make run-etl
make dashboard
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

Check that every SQL file runs against the generated SQLite database:

```bash
make sql-check
```

## S3 Input Support

Local file input:

```bash
python etl/process_billing_data.py --input data/raw/cloud_billing_sample.csv
```

S3 input after configuring AWS credentials:

```bash
python etl/process_billing_data.py --input s3://your-raw-billing-bucket/cloud_billing.csv
```

The S3 path uses `boto3`, which is included in `requirements.txt`.

## Budget Variance

Team monthly budgets live in:

```text
config/team_budgets.csv
```

The ETL creates `team_budget_variance.csv` and a matching SQLite table. The
dashboard shows whether each team is on track, near budget, over budget, or
missing a budget.

## Alerts

Generate an alert report locally:

```bash
python alerts/send_alerts.py
```

Send to Slack:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
python alerts/send_alerts.py
```

Send by email by setting `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`ALERT_EMAIL_FROM`, and `ALERT_EMAIL_TO`.

## Terraform

The `terraform/` folder defines:

- Raw billing S3 bucket.
- Curated analytics S3 bucket.
- SNS topic for cost alerts.
- IAM role and policy for a future Lambda or scheduled ETL job.

Run:

```bash
cd terraform
terraform init
terraform plan
```

## How To Use This Project

Most of the time, use the dashboard:

1. Open the dashboard with `streamlit run dashboard/app.py`.
2. Upload your billing CSV from the sidebar, or use the included sample data.
3. Use the filters for team, project, environment, and service.
4. Look for the main insights:
   - highest-cost service
   - spend by team
   - unallocated or untagged cost
   - daily spikes
   - forecasted month-end spend

Use the command-line ETL when you want saved processed files:

1. Run the ETL with `python etl/process_billing_data.py`.
2. Review the generated files in `data/processed/`.
3. Run SQL examples from the `sql/` folder against `data/processed/cloud_costs.db`.

Example SQL command:

```bash
sqlite3 data/processed/cloud_costs.db < sql/cost_by_service.sql
```

## Project Structure

```text
cloud-cost-analytics-pipeline/
├── data/
│   ├── raw/cloud_billing_sample.csv
│   └── processed/
├── alerts/send_alerts.py
├── config/team_budgets.csv
├── dashboard/app.py
├── docs/architecture.md
├── etl/process_billing_data.py
├── sql/
│   ├── cost_by_service.sql
│   ├── daily_spend_trend.sql
│   ├── monthly_spend.sql
│   ├── top_resources.sql
│   └── untagged_cost.sql
├── tests/test_etl.py
├── terraform/
├── requirements.txt
└── README.md
```

## Portfolio Talking Points

- Built an end-to-end cloud cost analytics pipeline using Python, SQL, SQLite,
  and Streamlit to identify cost drivers, untagged resources, and spend trends.
- Modeled raw billing data into fact and dimension tables for dashboarding and
  reusable SQL analysis.
- Implemented cost anomaly flags and month-end forecasting logic for practical
  cloud finance monitoring.
- Added team budget variance, month-over-month trend analysis, S3 ingestion
  support, Terraform infrastructure, and Slack/email cost alerting.

## What To Do Next

For the next stronger version:

1. Package the ETL as a Lambda function and trigger it from S3 object uploads.
2. Store curated output as Parquet in S3 and query it with Athena.
3. Add CloudWatch schedules for daily alert checks.
4. Add a Power BI or Tableau dashboard screenshot to the README.
5. Write a short insights section explaining where costs are high and what you
   recommend reducing.

## Resume Bullets

- Built a cloud cost analytics pipeline that processes AWS-style billing data
  into fact and dimension tables for SQL analysis and dashboard reporting.
- Created a Streamlit dashboard to monitor total spend, month-end forecast,
  top services, cost spikes, and unallocated cloud spend.
- Implemented automated data quality checks and unit tests for billing schema
  validation, allocation flags, and generated analytics outputs.
