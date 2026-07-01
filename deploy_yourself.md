# 내 Azure 구독에 직접 배포하기

이 폴더에는 지식 베이스 인프라를 본인의 Azure 구독에 배포하기 위한 리소스가 들어 있습니다.

## 사전 요구 사항

- 리소스를 생성할 수 있는 충분한 권한이 있는 **Azure 구독**
- 설치된 **Azure Developer CLI (azd)** ([설치 가이드](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd))
- 설치 및 구성된 **Azure CLI** ([설치 가이드](https://learn.microsoft.com/cli/azure/install-azure-cli))
- 설치된 **Python 3.10+**
- **Git** (이 저장소를 클론하기 위해)
- Jupyter 확장이 설치된 **VS Code** 또는 **GitHub Codespaces** (권장)

### 필요한 Azure 권한

다음 작업을 수행할 권한이 필요합니다.

- 리소스 그룹 생성
- Bicep 템플릿 배포
- 다음 항목의 생성 및 관리:
  - Azure AI Search 서비스
  - Microsoft Foundry 프로젝트
  - Azure OpenAI 모델 배포
- Azure RBAC 역할 할당

## 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/wonsungso/ms-four-iq-workshop.git
cd ms-four-iq-workshop
```

### 2. Python 가상 환경 생성

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. azd로 배포

```bash
azd auth login
azd up
```

이 명령은 다음을 수행합니다.

- 모든 Azure 리소스 프로비저닝 (AI Search, Foundry 프로젝트, OpenAI 모델, Fabric 용량)
- API 키를 가져와 필요한 모든 변수가 담긴 `.env` 파일 작성
- 검색 인덱스 생성 및 샘플 데이터 업로드
- Zava DIY 데이터셋과 온톨로지로 Fabric Lakehouse 설정

> **참고:** 이메일 시딩(Part 4 - Work IQ를 위해 호스팅된 Skillable 워크샵에서 사용)은 `Mail.Send` 애플리케이션 권한이 있는 서비스 주체가 필요하며 직접 배포 시에는 **실행되지 않습니다**. Part 4에서는 대신 본인의 Mail 데이터를 사용합니다.

### 4. 워크샵 시작

VS Code에서 [notebooks](./notebooks) 폴더를 열고 **`part1-standard-foundry-iq-kb.ipynb` 부터 시작**하세요.

## 정리

모든 리소스를 삭제하고 지속적인 과금을 피하려면:

```bash
azd down
```

## 추가 리소스

- [Azure AI Search 문서](https://learn.microsoft.com/azure/search/)
- [Azure OpenAI 서비스 문서](https://learn.microsoft.com/azure/ai-services/openai/)
- [Azure Bicep 문서](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Microsoft Foundry 커뮤니티 Discord](https://aka.ms/AIFoundryDiscord-Ignite25)
