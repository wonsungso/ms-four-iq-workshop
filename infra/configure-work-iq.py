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

from dotenv import dotenv_values, set_key
import requests


ROOT = Path(__file__).resolve().parents[1]
WORK_IQ_API_ID = "fdcc1f02-fc51-4226-8753-f668596af7f7"


def az_json(*args):
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI is not installed. Use Codespaces or install Azure CLI first.")
    result = subprocess.run(
        [executable, *args, "--output", "json"], capture_output=True, text=True,
        encoding="utf-8", check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Azure CLI failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def guid(value):
    return str(UUID(value))


def only(items, description):
    if len(items) != 1:
        raise ValueError(
            f"Expected exactly one {description}, found {len(items)}. "
            "Check the app registrations and selected Azure subscription."
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
                raise ValueError("Unexpected Microsoft Graph pagination URL.")
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
        raise ValueError("Set AZURE_SEARCH_SERVICE_ENDPOINT in .env after azd up.")
    search_name = host.removesuffix(".search.windows.net")
    resources = az_json("resource", "list", "--resource-type", "Microsoft.Search/searchServices")
    resource = only([r for r in resources if r["name"] == search_name], f"Search service {search_name!r}")
    search = az_json("resource", "show", "--ids", resource["id"], "--api-version", "2025-05-01")
    identity = search.get("identity", {})
    principal = identity.get("principalId")
    if not principal or not identity.get("tenantId"):
        raise ValueError("Enable the Search system-assigned managed identity as described in section 3-3.")
    search_tenant = guid(identity["tenantId"])
    api = graph.app(api_name)
    client = graph.app(client_name)
    api_id, client_id = guid(api["appId"]), guid(client["appId"])
    if api_id == WORK_IQ_API_ID or api_id == client_id:
        raise ValueError("Use separate customer API and login apps, not the Microsoft Work IQ app.")
    if f"api://{api_id}" not in api.get("identifierUris", []):
        raise ValueError("The API app must expose api://<application-id>.")
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
        raise ValueError("The login app is missing the API app's access_as_user permission.")
    if "http://localhost" not in client.get("publicClient", {}).get("redirectUris", []):
        raise ValueError("Register http://localhost as a mobile/desktop redirect URI on the login app.")
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
        raise ValueError("Run azd up first to create .env with the Search endpoint.")
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
        print("Existing Work IQ apps and Search identity connection verified. No files changed.")
    else:
        save_settings(path, settings)
        print("Saved all four WORK_IQ settings to .env. No apps or permissions changed.")
    print("Admin consent and billing access must already be configured. Continue with Part 4/6.")


if __name__ == "__main__":
    main()
