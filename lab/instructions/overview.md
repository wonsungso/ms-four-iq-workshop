## 시작하기 전에

<details>
<summary><strong>🔑 랩 자격 증명 (로그인이 필요할 때 클릭하여 펼치기)</strong></summary>

랩을 진행하는 동안 언제든지 가상 머신(Windows)이나 Azure 또는 Microsoft 365 앱(M365 Copilot, SharePoint, Teams 등)에 로그인해야 한다면 아래에 제공된 자격 증명을 사용하세요.

### 가상 머신(Windows) 로그인

가상 머신에 로그인해야 한다면 다음 자격 증명을 사용하세요.

- **사용자 이름**: +++@lab.VirtualMachine(Win11-Pro-Base).Username+++  
- **암호**: +++@lab.VirtualMachine(Win11-Pro-Base).Password+++

### Azure 및 Microsoft 365 로그인

Azure 또는 Microsoft 365 앱에 로그인해야 한다면 다음 자격 증명을 사용하세요.

- **사용자 이름**: +++@lab.CloudPortalCredential(User1).Username+++  
- **임시 액세스 패스(Temporary Access Pass)**: +++@lab.CloudPortalCredential(User1).AccessToken+++

</details>

## 개요

이 실습 랩에서는 에이전트형 검색을 사용해 Azure AI Search 지식 베이스를 구축하고, 이를 Model Context Protocol(MCP) 지식 소스로 확장합니다. 지식 베이스를 색인된 엔터프라이즈 콘텐츠와 라이브 MCP 서버 양쪽에 연결하여 여러 시스템에 걸쳐 근거 기반의 인용이 포함된 답변을 생성할 수 있게 합니다.

5개의 단계별 노트북 실습을 통해 여러 문서를 기반으로 한 멀티 소스 지식 베이스를 구축하고, MCP를 통한 웹 검색 결과로 확장하며, Fabric IQ와 Work IQ를 추가하고, 마지막으로 Work IQ와 Fabric IQ를 하나의 지식 베이스에 결합합니다. 랩을 마치면 여러 소스 유형을 혼합한 유연한 에이전트형 지식 베이스를 갖추게 됩니다.

## 시작하기

아래 단계를 따라 환경을 설정하고 랩을 시작하세요.

### Windows 로그인

가상 머신에서 다음 자격 증명으로 Windows에 로그인하세요.

- **사용자 이름**: +++@lab.VirtualMachine(Win11-Pro-Base).Username+++  
- **암호**: +++@lab.VirtualMachine(Win11-Pro-Base).Password+++

### 랩 저장소 접근

Skillable 환경에 로그인하면 바탕화면의 **Desktop > Build26-LAB532-main** 폴더에 랩 저장소가 이미 클론되어 있는 것을 확인할 수 있습니다.

> 이 폴더에는 랩에 필요한 모든 코드, 노트북, 리소스가 들어 있습니다.

### Visual Studio Code에서 프로젝트 폴더 열기

Visual Studio Code를 열고 **File > Open Folder**를 선택합니다. 그런 다음 바탕화면으로 이동하여 **Build26-LAB532-main** 폴더를 선택하고 **Select Folder**를 선택합니다.

> [!TIP]
> * 파일 작성자를 신뢰할지 묻는 메시지가 표시되면 **Yes, I trust the authors**를 선택하세요.

### 환경 설정 확인

**미리 색인된 데이터가 포함된 Azure AI Search** 및 **Azure OpenAI 배포**를 포함한 필요한 모든 Azure 서비스가 이미 프로비저닝되어 있습니다.

<details>
<summary><strong>📋 미리 구성된 항목 (자세한 내용은 클릭하여 펼치기)</strong></summary>

- **Azure AI Search** - 두 개의 미리 생성된 인덱스가 있는 Standard 계층:
  - **hrdocs:** HR 정책, 직원 핸드북, 직무 라이브러리, 회사 개요
  - **healthdocs:** 건강 보험 플랜, 복리후생 옵션, 보장 세부 정보
- **Azure OpenAI** - 채팅 완성 및 답변 합성을 위한 **gpt-5.4** 모델과 벡터 임베딩을 위한 **text-embedding-3-large** 모델 배포
- **사전 계산된 벡터** - 384개의 모든 문서 청크가 이미 벡터화되어 색인되어 있음

</details>

#### 환경 변수 확인

1. 메인 프로젝트 폴더 아래의 **.env** 파일을 엽니다.  
2. 다음 환경 변수가 포함되어 있는지 확인합니다.
   - *AZURE_SEARCH_SERVICE_ENDPOINT*
   - *AZURE_SEARCH_ADMIN_KEY*
   - *AZURE_OPENAI_ENDPOINT*
   - *AZURE_OPENAI_KEY*
   - *AZURE_OPENAI_CHATGPT_DEPLOYMENT*
   - *AZURE_OPENAI_CHATGPT_MODEL_NAME*
   - *AZURE_OPENAI_EMBEDDING_DEPLOYMENT*
   - *AZURE_TENANT_ID*
   - *FABRIC_WORKSPACE_ID*
   - *FABRIC_ONTOLOGY_ID*

이러한 변수가 있으면 Azure Portal에서 인덱스를 확인하는 단계로 진행합니다.

#### Azure Portal에서 인덱스 확인

검색 인덱스가 성공적으로 생성되었는지 확인합니다.

1. 웹 브라우저를 열고 +++https://portal.azure.com+++ 으로 이동합니다.
2. 랩 자격 증명으로 로그인합니다.
    - **사용자 이름**: +++@lab.CloudPortalCredential(User1).Username+++  
    - **임시 액세스 패스(Temporary Access Pass)**: +++@lab.CloudPortalCredential(User1).AccessToken+++
3. 상단의 Azure Portal 검색 창에서 +++lab532-search+++ 를 검색하고 AI Search 서비스(*lab532-search-.....* 형태)를 선택합니다.
4. 왼쪽 탐색 메뉴에서 **Search management** > **Indexes**를 선택합니다.
5. 두 개의 인덱스가 보여야 합니다.
   - **hrdocs** - 문서 수 50개를 표시해야 함
   - **healthdocs** - 문서 수 334개를 표시해야 함

인덱스가 존재하고 데이터가 채워져 있으면 환경을 사용할 준비가 된 것입니다. 이제 Jupyter 노트북으로 진행할 수 있습니다.

### Jupyter 노트북 진행하기

이 랩에는 다양한 지식 베이스 및 소스 유형 패턴을 다루는 5개의 단계별 노트북이 포함되어 있습니다.

1. **멀티 소스 검색 인덱스** - 해당 검색 인덱스와 업로드된 파일 위에 지식 베이스 구축
2. **Web IQ 소스** - MCP 지식 소스를 통해 Web IQ를 추가하여 웹 결과를 근거로 답변 생성
3. **Fabric IQ 소스** - Fabric 온톨로지 지식 소스를 통해 Fabric IQ 추가
4. **Work IQ 소스** - 사용자 로그인을 기반으로 인증된 일급 소스로 Work IQ를 지식 베이스에 추가
5. **Work IQ + Fabric IQ** - 업무 데이터와 구조화된 Fabric 데이터를 하나의 지식 베이스에 결합

**notebooks/** 폴더의 **part1-standard-foundry-iq-kb.ipynb** 부터 시작하여 각 노트북을 순서대로 진행하세요.

> [!TIP]
> **보너스: Copilot CLI 사이드퀘스트** - 각 노트북에는 방금 생성한 지식 베이스의 MCP 구성을 출력하는 보너스 섹션이 포함되어 있습니다. **notebooks/copilot-cli-sidequest.md**의 안내를 따라 이를 GitHub Copilot CLI에 추가하고 터미널에서 직접 지식 베이스에 질의해 보세요.
