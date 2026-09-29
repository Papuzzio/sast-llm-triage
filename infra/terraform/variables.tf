variable "region" {
  description = "AWS region for every resource in this stack."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for the cluster, VPC and registry."
  type        = string
  default     = "triagegpt"
}

variable "kubernetes_version" {
  description = "EKS control-plane version. Pick one inside standard support (aws eks describe-cluster-versions)."
  type        = string
  default     = "1.33"
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint. Set this to your own IP as x.x.x.x/32."
  type        = list(string)

  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0")
    error_message = "admin_cidrs must be set and must not be 0.0.0.0/0. Use your own IP as x.x.x.x/32."
  }
}

variable "node_instance_type" {
  description = "Instance type for the managed node group."
  type        = string
  default     = "t3.medium"
}

variable "github_repo" {
  description = "owner/repo allowed to assume the CI role through GitHub OIDC."
  type        = string
  default     = "Papuzzio/sast-llm-triage"
}

variable "create_github_oidc_provider" {
  description = "Set false if this AWS account already has the token.actions.githubusercontent.com OIDC provider."
  type        = bool
  default     = true
}

variable "app_namespace" {
  description = "Kubernetes namespace the app (and the CI deploy permission) is scoped to."
  type        = string
  default     = "triagegpt"
}
