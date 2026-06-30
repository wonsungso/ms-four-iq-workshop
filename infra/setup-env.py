"""
Write all environment variables needed by notebooks into the repo root .env file.
Fetches API keys (not available as Bicep outputs) via the management REST API
using AzureDeveloperCliCredential (azd token) — no az CLI required.
"""
import os
from pathlib import Path

import requests
from azure.identity import AzureDeveloperCliCredential

# Fetch API keys via management REST API
cred = AzureDeveloperCliCredential()
token = cred.get_token("https://management.azure.com/.default").token

sub = os.environ["AZURE_SUBSCRIPTION_ID"]
rg = os.environ["AZURE_RESOURCE_GROUP"]
headers = {"Authorization": f"Bearer {token}"}


def post(url):
    response = requests.post(url, headers=headers, timeout=120)
    response.raise_for_status()
    return response.json()


search_name = os.environ["AZURE_SEARCH_SERVICE_NAME"]
search_key = post(
    f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
    f"/providers/Microsoft.Search/searchServices/{search_name}"
    f"/listAdminKeys?api-version=2023-11-01"
)["primaryKey"]

openai_name = os.environ["AZURE_OPENAI_SERVICE_NAME"]
openai_key = post(
    f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
    f"/providers/Microsoft.CognitiveServices/accounts/{openai_name}"
    f"/listKeys?api-version=2023-05-01"
)["key1"]

# Write .env with all values
env_path = Path(__file__).parents[1] / ".env"
env_path.write_text(
    f"""\
# Azure AI Search Configuration
AZURE_SEARCH_SERVICE_ENDPOINT={os.environ['AZURE_SEARCH_SERVICE_ENDPOINT']}
AZURE_SEARCH_ADMIN_KEY={search_key}

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT={os.environ['AZURE_OPENAI_ENDPOINT']}
AZURE_OPENAI_KEY={openai_key}
AZURE_OPENAI_CHATGPT_DEPLOYMENT={os.environ['AZURE_OPENAI_CHATGPT_DEPLOYMENT']}
AZURE_OPENAI_CHATGPT_MODEL_NAME=gpt-5.4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT={os.environ['AZURE_OPENAI_EMBEDDING_DEPLOYMENT']}

# Tenant and project configuration
AZURE_TENANT_ID={os.environ['AZURE_TENANT_ID']}

# Fabric configuration (populated by lakehouse setup if capacity was deployed)
FABRIC_CAPACITY_ID={os.environ.get('FABRIC_CAPACITY_ID', '')}
""",
    encoding="utf-8",
)

print("Created .env file")
