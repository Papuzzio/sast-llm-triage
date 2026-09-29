# The API keys live in AWS Secrets Manager. Terraform creates the empty secret;
# you put the values in with the AWS CLI, so the keys never enter Terraform state.
resource "aws_kms_key" "secrets" {
  description             = "${var.name} Secrets Manager encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_account_admin.json
}

resource "aws_secretsmanager_secret" "api_keys" {
  # checkov:skip=CKV2_AWS_57:third-party LLM API keys cannot be rotated by a Secrets Manager Lambda; rotate manually
  name                    = "${var.name}/api-keys"
  description             = "ANTHROPIC_API_KEY and GEMINI_API_KEY for TriageGPT (JSON)."
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 0 # demo stack: allow immediate delete on destroy
}

# External Secrets Operator reads that one secret via EKS Pod Identity.
# The role is bound to a single service account and can read a single secret.
data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "${var.name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

data "aws_iam_policy_document" "read_api_keys" {
  statement {
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [aws_secretsmanager_secret.api_keys.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.secrets.arn]
  }
}

resource "aws_iam_role_policy" "external_secrets" {
  name   = "read-api-keys"
  role   = aws_iam_role.external_secrets.id
  policy = data.aws_iam_policy_document.read_api_keys.json
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  cluster_name    = module.eks.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}
