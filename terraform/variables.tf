variable "project_name" {
  description = "Project name used for AWS resource names."
  type        = string
  default     = "cloud-cost-analytics"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for the infrastructure."
  type        = string
  default     = "us-east-1"
}
