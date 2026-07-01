# 내 Azure 구독에 직접 배포하기

이 폴더에는 지식 베이스 인프라를 본인의 Azure 구독에 배포하기 위한 리소스가 들어 있습니다.

## 사전 요구 사항

- 리소스를 생성할 수 있는 충분한 권한이 있는 **Azure 구독**
- **GitHub 계정** (GitHub Codespaces 사용)

> 로컬 환경에서 진행하려면 [로컬 환경에서 배포하기](#로컬-환경에서-배포하기) 섹션의 추가 요구 사항을 참고하세요.

### 필요한 Azure 권한

다음 작업을 수행할 권한이 필요합니다.

- 리소스 그룹 생성
- Bicep 템플릿 배포
- 다음 항목의 생성 및 관리:
  - Azure AI Search 서비스
  - Microsoft Foundry 프로젝트
  - Azure OpenAI 모델 배포
- Azure RBAC 역할 할당

## 빠른 시작 (GitHub Codespaces)

이 저장소는 [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json)을 통해 Python, Azure CLI, azd, Jupyter 확장이 미리 설치된 Codespace 환경을 제공합니다. 별도 로컬 설치 없이 바로 시작할 수 있습니다.

### 1. Codespace 생성

- GitHub에서 [wonsungso/ms-four-iq-workshop](https://github.com/wonsungso/ms-four-iq-workshop) 저장소로 이동합니다
- **Code → Codespaces 탭 → "Create codespace on main"** 을 클릭합니다
- 컨테이너가 빌드되는 동안 잠시 기다립니다(`notebooks/requirements.txt`가 자동으로 설치됩니다)
- Codespace가 열리면 VS Code 웹 또는 데스크톱 앱에서 Terminal을 엽니다(Terminal > New Terminal)

### 2. azd로 배포

```bash
azd auth login
azd up
```

이 명령은 다음을 수행합니다.

- 모든 Azure 리소스 프로비저닝 (AI Search, Foundry 프로젝트, OpenAI 모델, Fabric 용량)
- API 키를 가져와 필요한 모든 변수가 담긴 `.env` 파일 작성
- 검색 인덱스 생성 및 샘플 데이터 업로드
- Zava DIY 데이터셋과 온톨로지로 Fabric Lakehouse 설정

> **참고:** 이메일 시딩(Part 4 - Work IQ용)은 `Mail.Send` 애플리케이션 권한이 있는 서비스 주체가 필요하며 직접 배포 시에는 **실행되지 않습니다**. Part 4에서는 대신 본인의 Mail 데이터를 사용합니다.

### 3. 워크샵 시작

VS Code에서 [notebooks](./notebooks) 폴더를 열고 **[part1-standard-foundry-iq-kb.ipynb](./notebooks/part1-standard-foundry-iq-kb.ipynb) 부터 시작**하세요.

## 로컬 환경에서 배포하기

Codespaces 대신 로컬 VS Code에서 진행하려면 다음이 추가로 필요합니다.

- 설치된 **Azure Developer CLI (azd)** ([설치 가이드](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd))
- 설치 및 구성된 **Azure CLI** ([설치 가이드](https://learn.microsoft.com/cli/azure/install-azure-cli))
- 설치된 **Python 3.10+**
- **Git** (이 저장소를 클론하기 위해)
- Jupyter 확장이 설치된 **VS Code**

또는 로컬에 **Docker**와 VS Code **Dev Containers** 확장이 설치되어 있다면, 클론 후 폴더를 열 때 뜨는 "Reopen in Container" 안내를 선택해 Codespaces와 동일한 컨테이너 환경을 로컬에서 사용할 수 있습니다.

### 1. 저장소 클론

```bash
git clone https://github.com/wonsungso/ms-four-iq-workshop.git
cd ms-four-iq-workshop
```

### 2. Python 가상 환경 생성

Dev Container를 사용하는 경우 이 단계는 건너뛰세요(컨테이너 자체가 격리된 환경입니다).

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **참고 (Windows):** Windows에서는 `venv`가 실행 파일을 `bin/`이 아닌 `Scripts/`에 생성합니다.
>
> ```bash
> source .venv/Scripts/activate
> ```

### 3. azd로 배포 및 워크샵 시작

위 [빠른 시작 (GitHub Codespaces)](#빠른-시작-github-codespaces)의 2~3단계와 동일하게 `azd auth login`, `azd up`을 실행한 뒤 노트북을 시작하세요.

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
