"""
Write all environment variables needed by notebooks into the repo root .env file.

Notebooks authenticate to
Azure AI Search and Azure OpenAI (via Search's managed identity for vectorizers)
using DefaultAzureCredential, relying on the RBAC role assignments granted in
main.bicep. A user-provided Web IQ key is preserved locally across retries.
"""
import os
from pathlib import Path
from dotenv import dotenv_values, set_key

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
WEB_IQ_RESOURCE_ID={os.environ.get('WEB_IQ_RESOURCE_ID', '')}
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
