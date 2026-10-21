"""Customer-app user assertions for Work IQ's delegated OBO flow."""

import os
import re
import shutil
import subprocess
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
            flow = self.app.initiate_device_flow(scopes=[self.scope])
            if not all(flow.get(key) for key in ("device_code", "user_code", "verification_uri")):
                error = flow.get("error", "invalid_device_flow")
                description = flow.get("error_description", "로그인 코드를 받지 못했습니다.")
                raise RuntimeError(
                    "Work IQ 로그인 시작 실패. 로그인 앱의 '퍼블릭 클라이언트 흐름 허용'과 "
                    f"테넌트의 디바이스 코드 로그인 정책을 확인하세요: {error}: {description}"
                )
            print("Work IQ: 데모 이메일이 있는 Microsoft 365 계정으로 로그인하세요.", flush=True)
            device_code_prompt(flow["verification_uri"], flow["user_code"], flow.get("expires_at"))
            print("브라우저에서 로그인을 완료하면 이 셀이 자동으로 계속됩니다. 코드를 공유하지 마세요.", flush=True)
            result = self.app.acquire_token_by_device_flow(flow)
        if not result or "access_token" not in result:
            error = (result or {}).get("error", "no_token")
            description = (result or {}).get("error_description", "로그인 결과를 받지 못했습니다.")
            raise RuntimeError(
                "Work IQ 로그인 실패. 로그인 앱의 '퍼블릭 클라이언트 흐름 허용'을 켜고 "
                "앱 권한과 관리자 동의를 확인하세요. 테넌트 정책에서 디바이스 코드 로그인을 "
                f"차단한다면 관리자에게 문의하세요: {error}: {description}"
            )
        return result["access_token"]
