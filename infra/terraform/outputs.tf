output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "api_keys_secret_name" {
  value = aws_secretsmanager_secret.api_keys.name
}

output "github_ci_role_arn" {
  description = "Put this in the GitHub repo variable AWS_CI_ROLE_ARN."
  value       = aws_iam_role.github_ci.arn
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}
