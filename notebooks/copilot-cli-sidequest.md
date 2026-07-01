# Copilot CLI 사이드퀘스트: 내 지식 베이스를 MCP 서버로 사용하기

모든 Foundry IQ 지식 베이스는 MCP 서버를 노출하며, GitHub Copilot CLI를 사용해 해당 MCP 서버가 답변할 수 있는 질문을 던질 수 있습니다. 여기 안내를 따라 Copilot CLI를 설정하세요.

## 1. GitHub에 로그인

본인의 GitHub 계정으로 로그인합니다.

## 2. GitHub Copilot CLI에 로그인

VS Code에서 터미널을 엽니다(Terminal > New Terminal).

GitHub Copilot CLI에 로그인합니다.

```powershell
copilot login
```

인증 단계의 일부로, 터미널에 출력되는 8자리 디바이스 코드를 입력하라는 메시지가 표시됩니다.


## 3. 지식 베이스 MCP 서버 추가

노트북 체크포인트 셀이 출력한 명령을 실행합니다. 다음과 같은 형태입니다.

```powershell
copilot mcp add zava-kb "<KB MCP URL>" --header "api-key=<SERVICE KEY>"
```

성공하면 다음과 같은 출력이 표시됩니다.

```
Added server "zava-kb"

zava-kb
  Type: http
  URL: https://fiq-search-2ijs67lu3y3ty.search.windows.net/knowledgebases/multisource-search-knowledge-base/mcp?api-version=2026-05-01-preview
  Headers:
    api-key: ***
  Tools: * (all)
  Source: User
```

## 4. 지식 베이스를 근거로 한 질문하기

방금 실행한 노트북에 해당하는 질문을 Copilot에 던집니다. 예를 들면 다음과 같습니다.

```powershell
copilot -i "Use the Zava knowledge base to answer: what health benefits are available?"
```

"Use Zava knowledge base to answer"라는 접두사 없이 질문해 볼 수도 있지만, 그럴 경우 Copilot CLI 에이전트가 지식 베이스 MCP 서버를 호출하지 않을 수 있습니다. 모델 가중치에서 답하거나 다른 도구를 사용해 답할 수 있기 때문입니다.
