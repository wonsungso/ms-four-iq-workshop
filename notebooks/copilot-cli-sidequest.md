# Copilot CLI 사이드퀘스트: 내 지식 베이스를 MCP 서버로 사용하기

Foundry IQ 지식 베이스는 MCP 서버 엔드포인트를 제공합니다. GitHub Copilot CLI에 연결해 방금 만든 지식 베이스에 질문할 수 있습니다.

## 1. GitHub 계정 준비

GitHub Copilot CLI를 사용할 수 있는 본인의 GitHub 계정을 준비합니다. GitHub 로그인과 Azure 로그인은 별개입니다.

## 2. GitHub Copilot CLI 설치 및 로그인

VS Code에서 터미널을 엽니다(Terminal > New Terminal). Codespaces에서 `copilot` 명령이 없다면 설치합니다.

```bash
curl -fsSL https://gh.io/copilot-install | bash
```

설치 후 로그인합니다.

```bash
copilot login
```

터미널에 출력되는 주소를 열고 디바이스 코드를 입력합니다.

## 3. 지식 베이스 MCP 서버 추가

Part 1 또는 Part 2의 **Copilot CLI 보너스 셀**을 실행하고 출력된 명령을 본인의 터미널에서 실행합니다. 셀이 현재 Search 엔드포인트, 지식 베이스 이름, API 버전을 사용하므로 별도로 주소를 조합할 필요가 없습니다.

기존 `zava-kb` 서버가 있다면 먼저 제거하고 새 명령을 실행합니다.

```bash
copilot mcp remove zava-kb
```

인증 헤더는 Search API 키가 아니라 Entra ID 액세스 토큰을 사용하는 `Authorization` 헤더입니다. 셀이 출력한 토큰이나 명령을 공유하거나 저장소에 저장하지 마세요. 등록한 MCP 설정에도 토큰이 포함되므로 실습 후 제거합니다.

성공 시 `Added server "zava-kb"`가 표시됩니다. URL의 Search 서비스와 지식 베이스 이름이 방금 실행한 Part의 설정과 일치하는지 확인하세요.

> 토큰이 만료되어 인증 오류가 나면 Azure 로그인 상태를 확인하고 보너스 셀을 다시 실행합니다. 기존 서버를 제거한 뒤 새 토큰을 사용하는 명령으로 다시 등록하세요.

## 4. 지식 베이스를 근거로 한 질문하기

방금 실행한 노트북에 해당하는 질문을 Copilot에 던집니다.

```bash
copilot -i "Zava 지식 베이스를 사용해 답변해 줘: 어떤 건강 복리후생을 이용할 수 있나요?"
```

접두사 없이 질문하면 지식 베이스 MCP 서버를 호출하지 않고 모델 자체 지식이나 다른 도구로 답할 수 있습니다. 실제 MCP 도구가 호출되었는지 확인하세요.

Part 4/6의 Work IQ는 별도 사용자 인증이 필요합니다. 이 사이드퀘스트는 Part 1/2의 보너스 셀을 대상으로 하며 Work IQ 로그인 절차를 대신하지 않습니다.

## 5. 실습 후 정리

```bash
copilot mcp remove zava-kb
```
