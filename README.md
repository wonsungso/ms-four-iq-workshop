<p align="center">
<img src="img/banner-build-26.png" alt="Microsoft Build 2026" width="1200"/>
</p>

# [Microsoft Build 2026](https://build.microsoft.com)

> [!NOTE]
> 이 저장소는 [microsoft/Build26-LAB532-from-data-to-context-agent-ready-knowledge-with-foundry-iq](https://github.com/wonsungso/Build26-LAB532-from-data-to-context-agent-ready-knowledge-with-foundry-iq) 저장소를 기반으로 작성되었으며, 문서와 노트북 콘텐츠를 한국어로 로컬라이징한 버전입니다. 원본 콘텐츠의 모든 권리는 원저작자에게 있습니다.

## 🔥 LAB532: 에이전트형 지식 베이스 구축 - Azure AI Search로 한 단계 진화한 RAG

### 세션 소개

이 실습 랩에서는 에이전트형 검색(agentic retrieval)을 사용해 Azure AI Search 지식 베이스를 구축하고, 다양한 소스 유형으로 이를 확장합니다. 5개의 단계별 노트북 실습을 통해 여러 문서를 기반으로 한 멀티 소스 지식 베이스를 구축하고, MCP를 통한 웹 검색으로 확장하며, Fabric IQ와 Work IQ를 추가하고, 마지막으로 Work IQ와 Fabric IQ를 하나의 지식 베이스에 결합합니다. 랩을 마치면 여러 소스 유형을 혼합한 유연한 에이전트형 지식 베이스를 갖추게 됩니다.

### 🏫 가이드형 세션으로 시작하기

가이드형 랩 세션으로 시작하려면 다음 단계를 따르세요.
- 제공된 자격 증명으로 랩 환경에 로그인합니다
- Visual Studio Code에서 **notebooks/** 폴더를 엽니다
- **part1-standard-foundry-iq-kb.ipynb** 부터 시작하여 5개의 노트북을 순서대로 진행합니다

### 🏠 본인 환경에서 시작하기

[직접 배포 가이드](deploy_yourself.md)의 단계를 따르세요.

### 🧠 학습 성과

이 세션을 마치면 다음을 할 수 있게 됩니다.

- Azure AI Search 에이전트형 검색을 사용해 색인된 엔터프라이즈 콘텐츠 위에 멀티 소스 지식 베이스를 구축합니다
- Web IQ, Fabric IQ, Work IQ 지식 소스로 지식 베이스를 확장합니다
- 여러 소스 유형(색인된 데이터, 구조화된 데이터, 업무 데이터, 웹 기반 데이터)을 하나의 지식 베이스에 결합합니다
- 인용 기반 답변 합성으로 지식 베이스에 질의합니다

### 💻 사용 기술

1. Foundry IQ (Azure AI Search)
1. Azure OpenAI (gpt-5.4-mini, text-embedding-3-large)
1. Model Context Protocol (MCP)
1. Microsoft Fabric IQ 및 Work IQ
1. Python 및 Jupyter Notebooks

### 📚 리소스 및 다음 단계

| 리소스 | 설명 |
|:---------|:------------|
| [Azure AI Search](https://learn.microsoft.com/azure/search/) | Azure AI Search의 전체 기능 |
| [에이전트형 검색을 위한 인덱스 설계](https://learn.microsoft.com/azure/search/search-agentic-retrieval-how-to-index) | 에이전트형 검색을 위한 데이터 구조화 모범 사례 |
| [지식 베이스 만들기](https://learn.microsoft.com/azure/search/search-agentic-retrieval-how-to-create) | 지식 베이스 생성 및 구성 단계별 가이드 |
| [답변 합성](https://learn.microsoft.com/azure/search/search-agentic-retrieval-how-to-synthesize) | 인용이 포함된 근거 기반 답변 생성 |
| [https://aka.ms/build26-next-steps](https://aka.ms/build26-next-steps) | Build 2026 이후 학습 여정의 다음 단계 |

Discord에서 Microsoft Foundry로 무언가를 만드는 여러분과 같은 개발자들을 만나보세요.

[![Microsoft Foundry Discord](https://dcbadge.limes.pink/api/server/nTYy5BXMWG)](https://discord.gg/bSC7dqjAU5)

## 콘텐츠 작성자

<table>
<tr>
    <td align="center"><a href="https://github.com/pamelafox">
        <img src="https://github.com/pamelafox.png" width="100px;" alt="Pamela Fox"/><br />
        <sub><b>Pamela Fox</b></sub></a><br />
            <a href="https://github.com/pamelafox" title="talk">📢</a>
    </td>
    <td align="center"><a href="https://github.com/mattgotteiner">
        <img src="https://github.com/mattgotteiner.png" width="100px;" alt="Matt Gotteiner"/><br />
        <sub><b>Matt Gotteiner</b></sub></a><br />
            <a href="https://github.com/mattgotteiner" title="talk">📢</a>
    </td>
    <td align="center"><a href="https://github.com/aycabas">
        <img src="https://github.com/aycabas.png" width="100px;" alt="Ayca Bas"/><br />
        <sub><b>Ayca Bas</b></sub></a><br />
            <a href="https://github.com/aycabas" title="talk">📢</a>
    </td>
</tr>
</table>

## 기여하기

이 프로젝트는 기여와 제안을 환영합니다. 대부분의 기여는 여러분이 본인의 기여를 사용할 권리를 가지고 있으며 실제로 그 권리를 부여한다는 것을 선언하는 기여자 라이선스 계약(CLA, Contributor License Agreement)에 동의해야 합니다. 자세한 내용은 [기여자 라이선스 계약](https://cla.opensource.microsoft.com)을 참조하세요.

풀 리퀘스트를 제출하면 CLA 봇이 CLA 제공 필요 여부를 자동으로 판단하고 PR에 적절히 표시합니다(예: 상태 확인, 코멘트). 봇이 제공하는 안내를 따르기만 하면 됩니다. CLA는 우리 CLA를 사용하는 모든 저장소에서 한 번만 동의하면 됩니다.

이 프로젝트는 [Microsoft 오픈 소스 행동 강령](https://opensource.microsoft.com/codeofconduct/)을 채택했습니다. 자세한 내용은 [행동 강령 FAQ](https://opensource.microsoft.com/codeofconduct/faq/)를 참조하거나 추가 질문이나 의견이 있으면 [opencode@microsoft.com](mailto:opencode@microsoft.com)으로 문의하세요.

## 상표

이 프로젝트에는 프로젝트, 제품 또는 서비스에 대한 상표나 로고가 포함될 수 있습니다. Microsoft 상표 또는 로고의 승인된 사용은 [Microsoft 상표 및 브랜드 가이드라인](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general)을 따라야 합니다. 이 프로젝트의 수정된 버전에서 Microsoft 상표나 로고를 사용할 때 혼동을 일으키거나 Microsoft의 후원을 암시해서는 안 됩니다. 제3자 상표나 로고의 사용은 해당 제3자의 정책을 따릅니다.
