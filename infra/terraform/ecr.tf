data "aws_iam_policy_document" "kms_account_admin" {
  # checkov:skip=CKV_AWS_111:KMS key policy; "*" means this key only
  # checkov:skip=CKV_AWS_356:KMS key policy; "*" means this key only
  # checkov:skip=CKV_AWS_109:KMS key policy; account root must administer its own key
  # Explicit key policy: the account root administers the key, and IAM policies
  # (like the scoped ones in this stack) decide who may use it.
  statement {
    sid       = "AccountAdmin"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_key" "ecr" {
  description             = "${var.name} ECR image encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_account_admin.json
}

resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE" # a pushed tag can never be overwritten
  force_delete         = true        # lets `terraform destroy` remove a repo with images in it

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.ecr.arn
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 20 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}
