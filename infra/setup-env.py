"""
Write all environment variables needed by notebooks into the repo root .env file.

Notebooks authenticate to
Azure AI Search and Azure OpenAI (via Search's managed identity for vectorizers)
using DefaultAzureCredential, relying on the RBAC role assignments granted in
main.bicep. A user-provided Web IQ key is preserved locally across retries.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from dotenv import dotenv_values, set_key


def resolve_web_iq_resource_id():
    if os.environ.get("DEPLOY_WEB_IQ", "true").strip().lower() == "false":
        return ""
    resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "").strip()
    subscription = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    if not resource_group or not subscription:
        resource_id = os.environ.get("WEB_IQ_RESOURCE_ID", "").strip()
        if resource_id:
            return resource_id
        raise ValueError(
            "Web IQ 조회에 AZURE_RESOURCE_GROUP과 AZURE_SUBSCRIPTION_ID가 필요합니다. "
            "배포할 azd 환경에서 postprovision을 실행하세요."
        )
    executable = shutil.which("az")
    if not executable:
        raise RuntimeError("Azure CLI가 없습니다. Codespaces를 사용하거나 Azure CLI를 설치하세요.")
    result = subprocess.run(
        [
            executable, "resource", "list",
            "--subscription", subscription, "--resource-group", resource_group,
            "--resource-type", "Microsoft.WebIQ/accounts",
            "--query", "[].id", "--output", "json",
        ],
        capture_output=True, text=True, encoding="utf-8", check=False, timeout=90,
    )
    if result.returncode:
        raise RuntimeError(f"Web IQ 리소스 조회 실패: {result.stderr.strip()}")
    resource_ids = json.loads(result.stdout)
    if not isinstance(resource_ids, list) or any(
        not isinstance(value, str) or not value.strip() for value in resource_ids
    ):
        raise ValueError("Azure CLI의 Web IQ 리소스 ID 응답이 올바르지 않습니다.")
    if len(resource_ids) != 1:
        raise ValueError(
            f"리소스 그룹 {resource_group!r}에 Web IQ 계정이 정확히 1개 필요하지만 "
            f"{len(resource_ids)}개를 찾았습니다. 배포 상태와 대상 구독을 확인하세요."
        )
    return resource_ids[0]


web_iq_resource_id = resolve_web_iq_resource_id()

# Preserve a real WEB_IQ_KEY across re-runs (this script rewrites .env from
# scratch every time postprovision runs, so a manually-added key would
# otherwise be wiped out on the next `azd up` / postprovision retry).
env_path = Path(__file__).parents[1] / ".env"
existing = dotenv_values(env_path)
same_deployment = (
    existing.get("AZURE_SEARCH_SERVICE_ENDPOINT") == os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
)
fabric_settings = {
    key: os.environ.get(key) or (existing.get(key, "") if same_deployment else "")
    for key in ("FABRIC_WORKSPACE_ID", "FABRIC_ONTOLOGY_ID")
}
work_iq_settings = {
    key: value for key, value in existing.items()
    if key in (
        "WORK_IQ_TENANT_ID", "WORK_IQ_APPLICATION_ID",
        "WORK_IQ_CLIENT_ID", "WORK_IQ_FEDERATED_CREDENTIAL_ID",
    ) and value
}
web_iq_key = existing.get("WEB_IQ_KEY") or "your-web-iq-key"

env_path.write_text(
    f"""\
# Azure AI Search Configuration
AZURE_SEARCH_SERVICE_ENDPOINT={os.environ['AZURE_SEARCH_SERVICE_ENDPOINT']}

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT={os.environ['AZURE_OPENAI_ENDPOINT']}
AZURE_OPENAI_CHATGPT_DEPLOYMENT={os.environ['AZURE_OPENAI_CHATGPT_DEPLOYMENT']}
AZURE_OPENAI_CHATGPT_MODEL_NAME=gpt-5.4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT={os.environ['AZURE_OPENAI_EMBEDDING_DEPLOYMENT']}

# Tenant and project configuration
AZURE_TENANT_ID={os.environ['AZURE_TENANT_ID']}

# Fabric configuration (populated by lakehouse setup if capacity was deployed)
FABRIC_CAPACITY_ID={os.environ.get('FABRIC_CAPACITY_ID', '')}
FABRIC_WORKSPACE_ID={fabric_settings['FABRIC_WORKSPACE_ID']}
FABRIC_ONTOLOGY_ID={fabric_settings['FABRIC_ONTOLOGY_ID']}

# Web IQ (live web search). The account below is auto-provisioned by azd up.
# Connect WEB_IQ_RESOURCE_ID in the Web IQ Developer Portal (https://webiq.microsoft.ai)
# to create an API key, then replace WEB_IQ_KEY with that key to use Part 2's
# Web IQ knowledge source.
WEB_IQ_RESOURCE_ID={web_iq_resource_id}
""",
    encoding="utf-8",
)
set_key(env_path, "WEB_IQ_KEY", web_iq_key)

if work_iq_settings:
    with env_path.open("a", encoding="utf-8") as stream:
        stream.write("\n# Work IQ Configuration\n")
    for key, value in work_iq_settings.items():
        set_key(env_path, key, value)

print("Created .env file. Search and model access use Entra ID. Web IQ keys are not displayed.")
