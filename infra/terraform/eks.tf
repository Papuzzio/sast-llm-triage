data "aws_caller_identity" "current" {}

module "eks" {
  # checkov:skip=CKV_TF_1:registry module pinned by version; .terraform.lock.hcl pins provider hashes
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = var.name
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public API endpoint, locked to your IP. Private endpoint also on for the nodes.
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.admin_cidrs
  cluster_endpoint_private_access      = true

  # Kubernetes Secrets are envelope-encrypted with a KMS key the module creates.
  # (Module default; spelled out so the intent is visible.)
  create_kms_key = true
  cluster_encryption_config = {
    resources = ["secrets"]
  }

  # Control-plane audit + authenticator logs to CloudWatch.
  cluster_enabled_log_types              = ["api", "audit", "authenticator"]
  cloudwatch_log_group_retention_in_days = 7

  # Access entries (not the legacy aws-auth ConfigMap). Whoever runs apply is admin.
  authentication_mode                      = "API"
  enable_cluster_creator_admin_permissions = true

  access_entries = {
    github_ci = {
      principal_arn = aws_iam_role.github_ci.arn
      policy_associations = {
        app_namespace_edit = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
          access_scope = {
            type       = "namespace"
            namespaces = [var.app_namespace]
          }
        }
      }
    }
  }

  cluster_addons = {
    coredns                = {}
    kube-proxy             = {}
    eks-pod-identity-agent = {}
    vpc-cni = {
      before_compute = true
      # Turns on NetworkPolicy enforcement in the VPC CNI; without this the
      # NetworkPolicy in deploy/k8s is accepted but not enforced.
      configuration_values = jsonencode({
        enableNetworkPolicy = "true"
      })
    }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = [var.node_instance_type]
      min_size       = 1
      max_size       = 2
      desired_size   = 2

      # IMDSv2 only, hop limit 1: pods can't reach the node's instance role.
      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 1
      }
    }
  }
}
