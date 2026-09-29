terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Local state keeps the first run simple. Before sharing this stack, move state to
  # an S3 bucket with versioning + encryption (backend "s3" with use_lockfile = true).
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "triagegpt"
      ManagedBy = "terraform"
      Repo      = "Papuzzio/sast-llm-triage"
    }
  }
}
