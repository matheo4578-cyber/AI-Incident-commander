terraform {
  required_version = ">= 1.7.0"
  required_providers {
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    aws     = { source = "hashicorp/aws", version = ">= 5.80, < 7.0" }
    tls     = { source = "hashicorp/tls", version = "~> 4.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags { tags = local.tags }
}
