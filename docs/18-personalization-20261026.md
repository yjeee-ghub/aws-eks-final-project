# 새 계정 개인화 — 2026-10-26

코드 설정 변경 기록이며 AWS 실배포 기록이 아닙니다. docs/01~17의 과거 검증 기록은 당시의 증거로 보존합니다.

| 항목 | 새 설정 |
|---|---|
| 계정 | 683668078297 |
| 프로필 / IAM 사용자 | 512-team01 |
| 프로젝트 | aws-eks-final-project |
| 리전 | ap-northeast-2 |
| GitHub | yjeee-ghub/aws-eks-final-project (public) |
| 도메인 | server / argocd / grafana.aws-yjeee.com |
| 메일 발신 | yoonjoung429@gmail.com |

공통 설정은 scripts/ops/environment.json입니다. backend·이미지 주소·IAM ARN·승인 정책·관리 화면·검증·복원·삭제 대상 검사도 함께 변경했습니다. 협업자는 yobi84-sy, yonginfra, yunjun1208이고 다른 팀원의 승인 1개를 유지합니다.

운영 SNS는 팀원 네 주소를 구독합니다. 관리자 주문 메일은 주소별 처리 기록을 사용합니다. SES 접수 후 기록 저장 실패 시 중복 가능성은 남습니다. 최초 앱 관리자 이메일은 실행 때 입력합니다.

## 배포 전 확인

- hostedZoneId는 빈 값입니다. 전체 구성에서는 새 공개 Hosted Zone을 만들고 ID와 네임서버를 출력합니다. 기존 zone을 쓰려면 새 계정의 정확한 ID를 설정합니다.
- ACM 발급에는 네임서버 연결이 필요합니다. 현재 전체 apply는 인증서 검증까지 기다리므로 오늘의 DNS 없는 기반 인프라 실행 절차는 별도로 준비해야 합니다.
- OIDC subject는 기본 repo:owner/repository:ref:refs/heads/main 형식입니다. 저장소의 실제 subject customization 여부를 배포 전에 확인합니다.
- 이전 팀 이미지 digest와 release 실행 ID를 제거했습니다. 앱 배포 전에 새 계정에서 5개 이미지를 전체 빌드·게시해야 합니다. lab-v1은 아직 게시가 확인되지 않은 초기 태그입니다.
- AWS 버전·한도·권한·STS 계정과 기존 자원은 생성 전에 검증합니다.

## 다음 실행 범위

state S3, VPC·서브넷·라우팅·NAT, IAM, EKS·기본 노드 3대, 비공개 RDS, ECR 등 기반 인프라의 plan을 검토합니다. kubectl 접속·노드 Ready·임시 Pod 외부 통신·DB 쿼리를 확인합니다. 도메인·앱·모니터링·CI/CD·메일은 후속 단계입니다.

## 로컬 검증

- Python 단위·통합 모의 테스트 115개 통과. Windows DPAPI 검사는 샌드박스 밖에서 동일 사용자 암호화·복호화 확인. 테스트 실행 시 번들 Python 경로를 PATH 앞에 추가했습니다.
- Terraform 세 루트의 validate 성공, Kubernetes 모의 배치 테스트 3개 통과.
- backend·공통 환경·Ingress 도메인 일치 검사와 초기 release 선언 검사 통과.
- 활성 코드에서 이전 계정·프로필·도메인·저장소 주소 잔존 검사 완료. legacy와 과거 검증 문서는 역사 기록으로 유지합니다.
- AWS apply·DNS 전환·GitHub push/설정 변경은 수행하지 않았습니다.
