data "aws_availability_zones" "available" {
  # checkov:skip=CKV_AWS_394:only the first two zones are used (slice below), so new AZs cannot change the result
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

# Two AZs, nodes in private subnets, one NAT gateway (cost over HA for a demo stack).
module "vpc" {
  # checkov:skip=CKV_TF_1:registry module pinned by version; .terraform.lock.hcl pins provider hashes
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.7"

  name = "${var.name}-vpc"
  cidr = "10.40.0.0/16"
  azs  = local.azs

  private_subnets = ["10.40.1.0/24", "10.40.2.0/24"]
  public_subnets  = ["10.40.101.0/24", "10.40.102.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  # VPC flow logs to CloudWatch, 7-day retention.
  enable_flow_log                                 = true
  create_flow_log_cloudwatch_log_group            = true
  create_flow_log_cloudwatch_iam_role             = true
  flow_log_cloudwatch_log_group_retention_in_days = 7

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}
