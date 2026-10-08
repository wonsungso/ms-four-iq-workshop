"""Customer-app user assertions for Work IQ's delegated OBO flow."""

from getpass import getpass
import os
import re
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import msal


def device_code_prompt(verification_uri, user_code, expires_on):
    print(f"브라우저에서 {verification_uri} 를 열고 코드 {user_code} 를 입력하세요.", flush=True)


def login_azure_cli(subscription: str = "") -> None:
    """Sign in the CLI without a terminal-only subscription picker."""
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI가 없습니다. Codespaces를 사용하거나 Azure CLI를 설치하세요.")
    print("Azure 로그인: 아래 주소와 코드로 로그인하세요. 이미 로그인했어도 다시 실행할 수 있습니다.", flush=True)
    environment = dict(os.environ, AZURE_CORE_LOGIN_EXPERIENCE_V2="off")
    with subprocess.Popen(
        [executable, "login", "--use-device-code", "--output", "none"],
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            prompt = re.search(r"open the page (\S+) and enter the code (\S+)", line)
            if prompt:
                device_code_prompt(prompt[1], prompt[2], None)
            else:
                print(line, end="", flush=True)
        if process.wait():
            raise RuntimeError("Azure 로그인이 실패했습니다. 위 오류를 확인하고 이 셀을 다시 실행하세요.")
    if subscription.strip():
        subprocess.run(
            [executable, "account", "set", "--subscription", subscription.strip()],
            check=True,
        )
    account = subprocess.run(
        [executable, "account", "show", "--query", "name", "--output", "tsv"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    print(f"Azure 로그인 완료. 선택된 구독: {account.stdout.strip()}")
    print("Search를 배포한 구독인지 확인하세요. 다르면 subscription에 구독 ID 또는 이름을 입력하고 다시 실행하세요.")


def callback_response(callback: str, state: str) -> dict[str, str]:
    try:
        parsed = urlparse(callback.strip())
        valid_address = (
            parsed.scheme == "http" and parsed.hostname == "localhost"
            and parsed.port == 8400 and parsed.path in ("", "/") and not parsed.fragment
        )
    except ValueError:
        valid_address = False
    if not valid_address:
        raise ValueError(
            "로그인 후 브라우저 주소창의 http://localhost:8400/?code=...&state=... 전체 주소를 복사하세요. "
            "처음 출력된 로그인 링크나 Codespaces의 전달된 포트 주소는 입력하지 마세요."
        )
    params = parse_qs(parsed.query)
    if any(len(values) != 1 for values in params.values()):
        raise ValueError("주소에 중복된 로그인 정보가 있습니다. 주소창의 전체 주소를 다시 복사하세요.")
    response = {key: values[0] for key, values in params.items()}
    if not response.get("state") or not (response.get("code") or response.get("error")):
        raise ValueError(
            "로그인 완료 정보가 없는 주소입니다. 로그인 후 code와 state가 포함된 전체 주소를 복사하세요. "
            "http://localhost:8400 만 입력하면 안 됩니다."
        )
    if response["state"] != state:
        raise ValueError("이전 로그인 주소입니다. 이번 셀에서 출력한 링크로 로그인한 뒤 새 주소를 복사하세요.")
    return response


def required_guid(name: str) -> str:
    value = os.environ.get(name, "").strip()
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(
            f"{name}에 올바른 ID가 필요합니다. "
            "Part 4 시작 준비의 환경 변수 자동 설정 셀을 실행하세요."
        ) from exc


class WorkIQUserCredential:
    """Acquire and refresh an app-audience token without storing secrets on disk."""

    def __init__(self, *, tenant_id: str, client_id: str, application_id: str):
        self.scope = f"api://{application_id}/access_as_user"
        self.app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

    def get_assertion(self) -> str:
        accounts = self.app.get_accounts()
        result = (
            self.app.acquire_token_silent_with_error([self.scope], account=accounts[0])
            if accounts else None
        )
        if not result or "access_token" not in result:
            # The manual loopback callback also works when the notebook runs in Codespaces.
            flow = self.app.initiate_auth_code_flow(
                scopes=[self.scope],
                redirect_uri="http://localhost:8400",
                prompt="select_account",
            )
            if "auth_uri" not in flow:
                raise RuntimeError("Work IQ 로그인을 시작하지 못했습니다. 앱 설정을 확인하고 다시 실행하세요.")
            print("Work IQ: 아래 링크를 열고 데모 이메일이 있는 Microsoft 365 계정으로 로그인하세요.")
            print(flow["auth_uri"])
            print(
                "로그인 후 브라우저 주소창의 http://localhost:8400/?code=...&state=... 전체 주소를 "
                "복사해 아래 입력란에 붙여 넣고 Enter를 누르세요. 연결 오류 화면이어도 괜찮습니다. "
                "Codespaces 포트는 열 필요가 없습니다. 이 주소를 공유하거나 저장하지 마세요."
            )
            for attempt in range(3):
                callback = getpass("로그인 후 전체 주소 붙여넣기 (입력 내용 숨김): ")
                try:
                    response = callback_response(callback, flow["state"])
                except ValueError as exc:
                    print(str(exc))
                    if attempt == 2:
                        raise ValueError("주소를 3회 확인하지 못했습니다. 셀을 다시 실행해 로그인하세요.") from None
                else:
                    break
            # MSAL verifies state and redeems the code with its generated PKCE verifier.
            result = self.app.acquire_token_by_auth_code_flow(flow, response)
        if not result or "access_token" not in result:
            error = (result or {}).get("error", "no_token")
            description = (result or {}).get("error_description", "로그인 결과를 받지 못했습니다.")
            raise RuntimeError(f"Work IQ 로그인 실패. 앱 권한과 관리자 동의를 확인하세요: {error}: {description}")
        return result["access_token"]
