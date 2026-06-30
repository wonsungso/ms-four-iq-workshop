
# Lab 532: Azure AI Search로 에이전트형 지식 베이스 구축하기

이 안내서는 Microsoft Build 2026의 **강사 주도** 워크숍 "에이전트형 지식 베이스 구축: Azure AI Search로 한 단계 진화한 RAG" 참가자를 위한 것입니다.

## 랩 개요

이 실습 랩에서는 검색 인덱스, Web IQ MCP 서버, Fabric IQ, Work IQ, 그리고 Work IQ + Fabric IQ 결합 경험으로 이루어진 새롭게 개편된 5부 흐름에 걸쳐 Azure AI Search 지식 베이스를 구축합니다. 랩을 마치면 색인된 데이터, 구조화된 데이터, 업무 데이터, 웹 기반 지식 소스를 혼합한 유연한 지식 베이스를 갖추게 됩니다.

## 사전 요구 사항

이 랩을 최대한 활용하려면 다음에 대한 기본적인 이해가 있어야 합니다.

- **Python 및 Jupyter Notebooks** – Jupyter 환경 안에서 직접 코드 셀을 작성하고 실행하게 됩니다.  
- **Azure 기초** – 리소스 그룹, 스토리지 계정, 인증과 같은 Azure 서비스 및 개념에 대한 친숙함.  
- **검색 증강 생성(RAG)** – LLM이 외부 데이터를 근거로 활용하는 방식에 대한 일반적인 이해가 있으면 에이전트형 검색 흐름을 더 잘 따라갈 수 있습니다.  
- **Azure AI Search 및 OpenAI** – 이러한 서비스가 하는 일(색인, 질의, 임베딩, 완성)에 대한 기본 지식이 있으면 도움이 되지만 필수는 아닙니다.

> [!NOTE]  
> 이 랩에서는 Azure 서비스를 프로비저닝하거나 인프라를 수동으로 배포할 **필요가 없습니다**. Azure AI Search, OpenAI 배포, 데이터 소스를 포함한 필요한 모든 리소스가 미리 생성되어 바로 사용할 수 있도록 준비되어 있습니다.

## 시작하기

먼저 **notebooks/** 폴더를 열고 **part1-standard-foundry-iq-kb.ipynb** 부터 시작하세요. 5개의 노트북을 순서대로 진행합니다.

1. **part1-standard-foundry-iq-kb.ipynb** — 복원된 HR 및 헬스 검색 인덱스로 멀티 소스 지식 베이스 구축
2. **part2-search-mcp-kb.ipynb** — MCP 지식 소스를 통해 Web IQ 추가
3. **part3-fabric-iq-to-kb.ipynb** — Fabric 온톨로지 지식 소스를 통해 Fabric IQ 추가
4. **part4-work-iq-to-kb.ipynb** — Work IQ를 일급 지식 소스로 추가
5. **part5-work-iq-fabric-iq-to-kb.ipynb** — Work IQ와 Fabric IQ를 하나의 지식 베이스에 결합

5개의 노트북을 모두 완료한 후 이 페이지로 돌아와 **Next >** 를 선택하면 마무리 및 요약 섹션을 볼 수 있습니다.

## 토론

기여하거나, 이슈를 제기하거나, 피드백을 제공하고 싶다면 이 저장소에 이슈를 열어 주세요.

이 워크숍이 마음에 들었다면 GitHub에서 저장소에 ⭐를 눌러 주시고 동료나 커뮤니티와 공유해 주세요.

## 소스 코드

이 세션의 소스 코드는 이 저장소의 [notebooks 폴더](../notebooks)에서 확인할 수 있습니다.  
향후 프로젝트의 참고 자료로 활용하거나, 추가 기능으로 확장하거나, Azure AI Search 및 에이전트형 검색 위에 구축한 본인의 솔루션에 통합할 수 있습니다.
