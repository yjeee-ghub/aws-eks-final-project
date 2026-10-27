# GitHub Actions 인증과 ECR 업로드 권한 구성
module "github_ci" {
  source = "./github_ci"

  project_name = var.project_name

  # ECR 모듈이 생성하는 저장소 5개의 ARN 전달
  ecr_repository_arns = module.ecr.repository_arns
  github_oidc_subject = var.github_oidc_subject
}

# GitHub Actions의 AWS_ROLE_TO_ASSUME 변수에 등록할 값
output "github_actions_role_arn" {
  value = module.github_ci.github_actions_role_arn
}

variable "github_oidc_subject" {
  type    = string
  default = "repo:yjeee-ghub/aws-eks-final-project:ref:refs/heads/main"
}
