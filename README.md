# Cloud Cost Analytics Pipeline

An interactive cloud cost dashboard for analyzing AWS-style billing data. The app cleans raw billing records, organizes them into analytics-ready tables, and helps users understand cost trends, ownership gaps, budget variance, and cost spikes.

Built as a portfolio project for **cloud engineering**, **data analyst**, and **analytics engineering** roles.

## Live Demo

[Open the Cloud Cost Analytics Dashboard](https://cloud-cost-analytics-pipeline-jhusqf4lp4yfcqyevroawy.streamlit.app/)

## What The App Does

- Upload a cloud billing CSV or use the included sample data.
- Clean and standardize billing fields such as service, team, project, environment, resource, and cost.
- Show total spend, forecasted month-end spend, top services, team spend, and data quality.
- Filter costs by team, project, environment, and service.
- Identify daily cost spikes and spend missing clear ownership.
- Generate alert reports with adjustable thresholds.
- Export organized billing data for reporting, SQL analysis, or follow-up work.

## Dashboard Sections

- **Overview:** high-level spend summary, forecast, budget check, ownership cleanup, and data quality.
- **Explore Costs:** filters and charts for understanding spend by service, team, and selected billing data.
- **Problem Areas:** cost spikes, missing ownership, and high-cost resources to investigate.
- **Alerts:** threshold controls, alert status, downloadable alert report, and optional Slack/email delivery.
- **Data:** cleaned billing records with export support.

## Screenshots

### Overview

<img src="docs/screenshots/overview.png" alt="Overview dashboard showing spend summary, ownership cleanup, insights, and budget check" width="900">

### Explore Costs

<img src="docs/screenshots/explore-costs-filtered.png" alt="Explore Costs view showing filtered spend summary and daily trend chart" width="900">

### Problem Areas

<img src="docs/screenshots/problem-areas.png" alt="Problem Areas view showing cost spikes, missing ownership, and resources to investigate" width="900">

### Organized Data

<img src="docs/screenshots/organized-data.png" alt="Organized billing data table showing cleaned cloud billing records" width="900">

## Tech Stack

- **Python** for ETL, validation, alert logic, and data processing
- **Pandas** for cleaning and aggregation
- **SQLite** for local analytics storage
- **SQL** for reusable cost analysis queries
- **Streamlit** for the interactive dashboard
- **Terraform** for an AWS infrastructure blueprint
- **AWS-ready design** with optional S3 input and SNS alert planning

## Data Pipeline

```text
Billing CSV or S3 object
        |
        v
ETL processing
        |
        +-- cleaned fact table
        +-- daily spend summary
        +-- monthly spend summary
        +-- team budget variance
        +-- executive summary
        |
        v
Streamlit dashboard + CSV exports + SQLite database
```

## Data Questions Answered

- Which cloud services cost the most?
- Which teams and projects own the most spend?
- How much spend is missing ownership or tags?
- Are there daily cost spikes?
- What is the projected month-end bill?
- How is spend changing month over month?
- Which teams are over, near, or under budget?

## Run Locally

```bash
git clone <repository-url>
cd cloud-cost-analytics-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python etl/process_billing_data.py
streamlit run dashboard/app.py
```

Then open the Streamlit URL shown in your terminal, usually:

```text
http://localhost:8501
```

If that port is busy, Streamlit may use another port such as `8502`.

## CSV Format

The dashboard accepts CSV files with these columns:

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

If no file is uploaded, the app uses included sample data. The sidebar also includes a **Download CSV Template** button.

## Alerts

The dashboard includes an **Alerts** tab that can:

- Flag daily cost spikes.
- Flag spend missing ownership.
- Let users adjust alert thresholds.
- Generate a downloadable alert report.
- Show Slack/email delivery options when environment variables are configured.

Run the same alert report from the command line:

```bash
python alerts/send_alerts.py
```

Optional delivery settings:

```text
SLACK_WEBHOOK_URL
SMTP_HOST
SMTP_USERNAME
SMTP_PASSWORD
ALERT_EMAIL_FROM
ALERT_EMAIL_TO
```

## Optional Cloud Infrastructure

The `terraform/` folder contains an AWS infrastructure blueprint for a cloud-hosted version of the pipeline:

- S3 bucket for raw billing files
- S3 bucket for processed analytics outputs
- SNS topic for cost alerts
- IAM role and policy for future scheduled processing

Preview the infrastructure:

```bash
cd terraform
terraform init
terraform plan
```

## Project Structure

```text
cloud-cost-analytics-pipeline/
├── alerts/              # Alert report and delivery logic
├── config/              # Team budget targets
├── dashboard/           # Streamlit dashboard
├── data/                # Raw and processed sample data
├── docs/                # Architecture notes and screenshots
├── etl/                 # Billing data cleaning and transformations
├── sql/                 # Reusable SQL analysis queries
├── terraform/           # AWS infrastructure blueprint
├── tests/               # ETL tests
├── requirements.txt
└── README.md
```

## Why This Project Matters

Cloud bills can be difficult to understand when costs are spread across services, teams, projects, and environments. This project shows how raw billing data can be turned into clear analytics, ownership reporting, budget checks, and alerting workflows that cloud and data teams can act on.
