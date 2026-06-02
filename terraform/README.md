# Terraform Infrastructure

This folder defines the AWS resources for a cloud version of the project.

It creates:

- Raw S3 bucket for uploaded billing CSV files.
- Curated S3 bucket for processed analytics output.
- SNS topic for cost alerts.
- IAM role and policy that a Lambda or scheduled ETL job can use.

Run from this folder after configuring AWS credentials:

```bash
terraform init
terraform plan -var="project_name=cloud-cost-analytics"
terraform apply -var="project_name=cloud-cost-analytics"
```
