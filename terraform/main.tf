terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

resource "aws_s3_bucket" "raw_billing" {
  bucket = "${local.name_prefix}-raw-billing"
}

resource "aws_s3_bucket" "curated_billing" {
  bucket = "${local.name_prefix}-curated-billing"
}

resource "aws_s3_bucket_versioning" "raw_billing" {
  bucket = aws_s3_bucket.raw_billing.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_billing" {
  bucket = aws_s3_bucket.raw_billing.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "curated_billing" {
  bucket = aws_s3_bucket.curated_billing.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_sns_topic" "cost_alerts" {
  name = "${local.name_prefix}-cost-alerts"
}

resource "aws_iam_role" "etl_role" {
  name = "${local.name_prefix}-etl-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "etl_policy" {
  name = "${local.name_prefix}-etl-policy"
  role = aws_iam_role.etl_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_billing.arn,
          "${aws_s3_bucket.raw_billing.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.curated_billing.arn,
          "${aws_s3_bucket.curated_billing.arn}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.cost_alerts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}
