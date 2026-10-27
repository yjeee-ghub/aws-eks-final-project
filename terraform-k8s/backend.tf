# 버킷은 terraform-state-bootstrap에서 별도로 준비합니다. DynamoDB 없이 S3 네이티브 잠금 사용.
terraform {
  backend "s3" {
    bucket              = "aws-eks-final-project-state-683668078297-ap-northeast-2"
    key                 = "aws-eks-final-project/k8s/terraform.tfstate"
    region              = "ap-northeast-2"
    profile             = "512-team01"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["683668078297"]
  }
}
