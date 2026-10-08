"""Discover existing Work IQ registrations and save notebook settings to .env."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
from uuid import UUID

from dotenv import dotenv_values, set_key, unset_key
import requests


ROOT = Path(__file__).resolve().parents[1]
WORK_IQ_API_ID = "fdcc1f02-fc51-4226-8753-f668596af7f7"


def az_json(*args):
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI가 없습니다. Codespaces를 사용하거나 Azure CLI를 설치하세요.")
    result = subprocess.run(
        [executable, *args, "--output", "json"], capture_output=True, text=True,
        encoding="utf-8", check=False,
    )
    if result.returncode:
        if "Please run 'az login'" in result.stderr:
            raise RuntimeError(
                "Azure CLI에 로그인되어 있지 않습니다. Part 4/6의 Azure 로그인 셀을 실행하세요. "
                "터미널에서는 az login --use-device-code 를 실행할 수 있습니다. "
                "Search를 배포한 구독을 선택한 뒤 설정 셀을 다시 실행하세요. "
                "브라우저나 azd 로그인과는 별개입니다. "
                f"원래 오류: {result.stderr.strip()}"
            )
        raise RuntimeError(f"Azure CLI 실행 실패: {result.stderr.strip()}")
    return json.loads(result.stdout)


def guid(value):
    return str(UUID(value))


def only(items, description):
    if len(items) != 1:
        raise ValueError(
            f"{description} 항목이 정확히 1개 필요하지만 {len(items)}개를 찾았습니다. "
            "앱 등록과 선택된 Azure 구독을 확인하세요."
        )
    return items[0]


class Graph:
    def __init__(self, tenant_id):
        token = az_json(
            "account", "get-access-token", "--tenant", tenant_id,
            "--scope", "https://graph.microsoft.com/.default",
        )["accessToken"]
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def collection(self, path, params=None):
        url = f"https://graph.microsoft.com/v1.0/{path}"
        items = []
        while url:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com":
                raise ValueError("Microsoft Graph의 다음 페이지 주소가 올바르지 않습니다.")
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            items.extend(data["value"])
            url = data.get("@odata.nextLink")
            params = None
        return items

    def app(self, name):
        escaped = name.replace("'", "''")
        return only(self.collection("applications", {
            "$filter": f"displayName eq '{escaped}'",
            "$select": "id,appId,identifierUris,api,publicClient,requiredResourceAccess",
        }), f"app named {name!r}")


def discover(graph, tenant_id, endpoint, api_name, client_name):
    host = urlparse(endpoint).hostname
    if urlparse(endpoint).scheme != "https" or not host or not host.endswith(".search.windows.net"):
        raise ValueError("azd up 실행 후 .env의 AZURE_SEARCH_SERVICE_ENDPOINT를 확인하세요.")
    search_name = host.removesuffix(".search.windows.net")
    resources = az_json("resource", "list", "--resource-type", "Microsoft.Search/searchServices")
    resource = only([r for r in resources if r["name"] == search_name], f"Search service {search_name!r}")
    search = az_json("resource", "show", "--ids", resource["id"], "--api-version", "2025-05-01")
    identity = search.get("identity", {})
    principal = identity.get("principalId")
    if not principal or not identity.get("tenantId"):
        raise ValueError("Part 4 시작 준비에서 Search의 시스템 할당 관리 ID(identity)를 켜세요.")
    search_tenant = guid(identity["tenantId"])
    api = graph.app(api_name)
    client = graph.app(client_name)
    api_id, client_id = guid(api["appId"]), guid(client["appId"])
    if api_id == WORK_IQ_API_ID or api_id == client_id:
        raise ValueError("Microsoft Work IQ 앱 대신 별도의 연결 앱과 로그인 앱을 등록하세요.")
    if f"api://{api_id}" not in api.get("identifierUris", []):
        raise ValueError("연결 앱의 API 노출에서 api://<application-id>를 설정하세요.")
    scope = only([
        s for s in api.get("api", {}).get("oauth2PermissionScopes", [])
        if s.get("value") == "access_as_user" and s.get("isEnabled")
    ], "enabled access_as_user scope")
    permissions = client.get("requiredResourceAccess", [])
    if not any(
        r["resourceAppId"] == api_id and
        any(p["id"] == scope["id"] and p["type"] == "Scope" for p in r["resourceAccess"])
        for r in permissions
    ):
        raise ValueError("로그인 앱에 연결 앱의 access_as_user 권한을 추가하세요.")
    if "http://localhost" not in client.get("publicClient", {}).get("redirectUris", []):
        raise ValueError("로그인 앱의 모바일/데스크톱 리디렉션 URI로 http://localhost를 등록하세요.")
    credentials = graph.collection(f"applications/{guid(api['id'])}/federatedIdentityCredentials")
    credential = only([
        c for c in credentials
        if c["issuer"].rstrip("/") == f"https://login.microsoftonline.com/{search_tenant}/v2.0"
        and c["subject"] == principal
        and c["audiences"] == ["api://AzureADTokenExchange"]
    ], "federated credential matching the Search managed identity")
    return {
        "WORK_IQ_TENANT_ID": guid(tenant_id),
        "WORK_IQ_APPLICATION_ID": api_id,
        "WORK_IQ_CLIENT_ID": client_id,
        "WORK_IQ_FEDERATED_CREDENTIAL_ID": guid(credential["id"]),
    }


def save_settings(path, settings):
    original = path.read_text(encoding="utf-8")
    fd, name = tempfile.mkstemp(prefix=".work-iq-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(original)
        existing = dotenv_values(temporary)
        for key in settings:
            if key in existing:
                unset_key(temporary, key)
        lines = [
            line for line in temporary.read_text(encoding="utf-8").splitlines()
            if line != "# Work IQ Configuration"
        ]
        content = "\n".join(lines).rstrip()
        temporary.write_text(
            (content + "\n\n" if content else "") + "# Work IQ Configuration\n",
            encoding="utf-8",
        )
        for key, value in settings.items():
            set_key(temporary, key, value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-app-name", default="fouriq-workiq-api")
    parser.add_argument("--client-app-name", default="fouriq-workiq-client")
    parser.add_argument("--tenant-id", help="App tenant. Defaults to the Azure CLI account tenant.")
    parser.add_argument("--verify-only", action="store_true", help="Check without updating .env.")
    args = parser.parse_args()
    path = ROOT / ".env"
    if not path.exists():
        raise ValueError("먼저 azd up을 실행해 Search 주소가 포함된 .env를 생성하세요.")
    env = dotenv_values(path)
    tenant = guid(args.tenant_id or az_json("account", "show")["tenantId"])
    graph = Graph(tenant)
    try:
        settings = discover(
            graph, tenant, env.get("AZURE_SEARCH_SERVICE_ENDPOINT", ""),
            args.api_app_name, args.client_app_name,
        )
    finally:
        graph.session.close()
    if args.verify_only:
        print("Work IQ 앱과 Search 관리 ID 연결을 확인했습니다. 파일은 변경하지 않았습니다.")
    else:
        save_settings(path, settings)
        print("Work IQ 환경 변수 4개를 .env에 저장했습니다. 앱이나 권한은 변경하지 않았습니다.")
    print("관리자 동의와 결제 설정은 별도로 완료되어 있어야 합니다. Part 4/6을 계속 진행하세요.")


if __name__ == "__main__":
    main()
