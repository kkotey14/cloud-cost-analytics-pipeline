# Cloud Cost Analytics Pipeline

A portfolio-ready analytics project for cloud engineering and data analyst roles.
It ingests cloud billing records, cleans and models the data, stores analytics
tables in SQLite, and powers SQL analysis plus a Streamlit dashboard.

The first implementation is local-first so it can run without AWS credentials.
The structure maps cleanly to a cloud version later: raw CSV files become S3
objects, the ETL can run in Lambda or Glue, SQLite can be replaced by Athena or
PostgreSQL, and alerts can be sent through SNS or Slack.

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
        +--> data/processed/cloud_costs.db
        |
        v
sql/*.sql + dashboard/app.py
```

## What It Answers

- Which cloud services cost the most?
- Which teams, projects, and environments drive spend?
- How much cost is untagged or poorly allocated?
- Did spend spike compared with recent history?
- What is the projected month-end spend?

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

If you want to see the correct format, use the **Download sample CSV** button
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
├── terraform/README.md
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

## What To Do Next

For a stronger cloud engineering version:

1. Add Terraform for an S3 raw bucket, S3 curated bucket, Lambda function, Athena
   database, and SNS topic.
2. Move `data/raw/cloud_billing_sample.csv` into S3.
3. Trigger the ETL from Lambda when a new billing file lands.
4. Store curated output as Parquet in S3 and query it with Athena.
5. Add a CloudWatch alarm or SNS alert when unallocated spend crosses a threshold.

For a stronger data analyst version:

1. Add more months of sample billing data.
2. Add budget targets by team and project.
3. Create variance SQL: actual spend versus budget.
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
