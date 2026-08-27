"""
Write all environment variables needed by notebooks into the repo root .env file.

Entra ID-only auth: no API keys are fetched or written. Notebooks authenticate to
Azure AI Search and Azure OpenAI (via Search's managed identity for vectorizers)
using DefaultAzureCredential, relying on the RBAC role assignments granted in
main.bicep.
"""
import os
from pathlib import Path

# Preserve a real WEB_IQ_KEY across re-runs (this script rewrites .env from
# scratch every time postprovision runs, so a manually-added key would
# otherwise be wiped out on the next `azd up` / postprovision retry).
env_path = Path(__file__).parents[1] / ".env"
web_iq_key = "your-web-iq-key"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("WEB_IQ_KEY="):
            existing_value = line.split("=", 1)[1].strip()
            if existing_value and existing_value != "your-web-iq-key":
                web_iq_key = existing_value
            break

# Write .env with all values (no API keys - Entra ID auth only)
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

# Web IQ (live web search) - replace with your own key to use Part 2's Web IQ knowledge source
WEB_IQ_KEY={web_iq_key}
""",
    encoding="utf-8",
)

print("Created .env file (Entra ID auth only, no API keys)")
