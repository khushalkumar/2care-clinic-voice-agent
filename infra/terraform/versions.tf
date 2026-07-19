terraform {
  backend "s3" {}

  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.90"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = "2care-clinic-voice-agent"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
