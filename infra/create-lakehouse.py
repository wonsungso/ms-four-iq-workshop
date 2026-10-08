"""
Create Fabric Lakehouse and load Zava DIY dataset as Delta tables.

This script:
1. Creates a lakehouse in Microsoft Fabric using the REST API
2. Downloads the Zava DIY dataset (product_data.json, reference_data.json) from GitHub
3. Flattens JSON data into CSV files
4. Uploads CSVs to OneLake (lakehouse Files section)
5. Loads CSVs as Delta tables using the Load Table API
6. Creates or updates a Fabric IQ ontology bound to the lakehouse tables

Environment variables (from .env):
  FABRIC_WORKSPACE_ID  - Existing Fabric workspace GUID
  FABRIC_CAPACITY_ID   - Fabric capacity GUID or ARM resource ID for workspace creation
  FABRIC_TENANT_ID     - Microsoft Entra tenant ID for Fabric auth
  LAKEHOUSE_NAME       - Name for the lakehouse (default: zava-diy-lakehouse)
  FABRIC_ONTOLOGY_ID   - Existing ontology GUID to update, if known
  FABRIC_ONTOLOGY_NAME - Name for the ontology (default: ZavaDIYOntology)
  CREATE_ONTOLOGY      - Create/update ontology after table load (default: true)
  INCLUDE_EMBEDDINGS   - Include vector embeddings in products table (default: false)
  INCLUDE_CATEGORY_RELATIONSHIP - Add a belongsToCategory relationship (Product->Category)
                         to the ontology (default: false). Left disabled by default to keep
                         the ontology minimal for the workshop; re-enable once you've
                         validated it end-to-end if you want the extra relationship.

Note on the Fabric IQ GraphModel: right after tables are loaded, Fabric's first automatic
graph refresh can fail with "GraphNotRefreshable: Graph doesn't have valid content and
cannot be refreshed." This is a timing race with the lakehouse's SQL analytics endpoint
sync, not a schema problem. `wait_for_graph_model_ready()` detects this and retries the
definition push with a delay so the script self-heals instead of leaving a broken graph.
"""

import base64
import csv
import io
import json
import os
import random
import sys
import time
import traceback
import uuid
from datetime import datetime

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

# Configuration
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
ONELAKE_DFS_URL = "https://onelake.dfs.fabric.microsoft.com"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
STORAGE_SCOPE = "https://storage.azure.com/.default"
FABRIC_RETRY_ATTEMPTS = 6
FABRIC_RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/microsoft/ai-tour-26-zava-diy-dataset-plus-mcp"
    "/main/data/database"
)

WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
LAKEHOUSE_NAME = os.getenv("LAKEHOUSE_NAME", "ZavaDIYLakehouse")
WORKSPACE_NAME = os.getenv("FABRIC_WORKSPACE_NAME", "ZavaDIYWorkspace")
FABRIC_CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID", "")
FABRIC_TENANT_ID = os.getenv("FABRIC_TENANT_ID") or os.getenv("AZURE_TENANT_ID", "")
FABRIC_ONTOLOGY_ID = os.getenv("FABRIC_ONTOLOGY_ID", "")
FABRIC_ONTOLOGY_NAME = os.getenv("FABRIC_ONTOLOGY_NAME", "ZavaDIYOntology")
FABRIC_LAB_USER_UPN = os.getenv("FABRIC_LAB_USER_UPN", "")
FABRIC_LAB_USER_OID = os.getenv("FABRIC_LAB_USER_OID", "")
CREATE_ONTOLOGY = os.getenv("CREATE_ONTOLOGY", "true").lower() == "true"
INCLUDE_EMBEDDINGS = os.getenv("INCLUDE_EMBEDDINGS", "false").lower() == "true"
# Kept off by default to keep the ontology minimal; not required by the workshop questions.
INCLUDE_CATEGORY_RELATIONSHIP = os.getenv("INCLUDE_CATEGORY_RELATIONSHIP", "false").lower() == "true"
_CREDENTIAL = None

# Logging
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "create-lakehouse.log")
REPO_ROOT = os.path.dirname(SCRIPT_DIR)


def update_root_env(values: dict):
    """Update the repo root .env file with key=value pairs (append or replace)."""
    env_path = os.path.join(REPO_ROOT, ".env")
    for key, val in values.items():
        set_key(env_path, key, val)


def reorder_env_sections():
    """Normalize the repo root .env layout after dotenv.set_key() appends new keys.

    dotenv.set_key() (used by update_root_env above) appends brand-new keys at
    the very end of the file when they don't already exist. That has two side
    effects here:
    - FABRIC_WORKSPACE_ID / FABRIC_ONTOLOGY_ID end up detached from the
      "Fabric configuration" section (next to FABRIC_CAPACITY_ID).
    - The WEB_IQ_KEY block (written last by setup-env.py) gets pushed into
      the middle of the file.

    This re-groups FABRIC_WORKSPACE_ID/FABRIC_ONTOLOGY_ID with
    FABRIC_CAPACITY_ID, moves WEB_IQ_KEY back to the end, and collapses any
    stray blank lines left behind by the moves.
    """
    env_path = os.path.join(REPO_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    fabric_extra = []
    web_iq_block = []
    other_lines = []

    for line in lines:
        if line.startswith("FABRIC_WORKSPACE_ID=") or line.startswith("FABRIC_ONTOLOGY_ID="):
            fabric_extra.append(line)
        elif line.startswith("WEB_IQ_KEY="):
            if other_lines and other_lines[-1].strip().startswith("# Web IQ"):
                web_iq_block.append(other_lines.pop())
            web_iq_block.append(line)
        else:
            other_lines.append(line)

    if fabric_extra:
        for idx, line in enumerate(other_lines):
            if line.startswith("FABRIC_CAPACITY_ID="):
                other_lines[idx + 1 : idx + 1] = fabric_extra
                break
        else:
            other_lines.extend(fabric_extra)

    # Collapse any run of blank lines left behind by the moves above
    collapsed = []
    for line in other_lines:
        if line.strip() == "" and collapsed and collapsed[-1].strip() == "":
            continue
        collapsed.append(line)
    while collapsed and collapsed[-1].strip() == "":
        collapsed.pop()

    if web_iq_block:
        new_content = "\n".join(collapsed) + "\n\n" + "\n".join(web_iq_block) + "\n"
    else:
        new_content = "\n".join(collapsed) + "\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def log_message(message: str):
    """Write message to log file and stdout with timestamp."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_credential():
    """Get the credential used for Fabric API and OneLake calls."""
    global _CREDENTIAL
    if _CREDENTIAL is None:
        # Always use DefaultAzureCredential - it picks up AZURE_CLIENT_ID,
        # AZURE_CLIENT_SECRET, AZURE_TENANT_ID env vars (EnvironmentCredential)
        # which work in headless/subprocess environments (e.g., CI or hosted VMs).
        _CREDENTIAL = DefaultAzureCredential()
    return _CREDENTIAL


def get_fabric_token() -> str:
    """Get an access token for Fabric API."""
    token = get_credential().get_token(FABRIC_SCOPE)
    return token.token


def get_storage_token() -> str:
    """Get an access token for OneLake (Azure Storage)."""
    token = get_credential().get_token(STORAGE_SCOPE)
    return token.token


def fabric_headers() -> dict:
    """Return headers for Fabric API calls."""
    return {
        "Authorization": f"Bearer {get_fabric_token()}",
        "Content-Type": "application/json",
    }


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After from a Fabric throttling response."""
    if value is None:
        return None
    try:
        return max(float(value), 0)
    except (TypeError, ValueError):
        return None


def sleep_for_retry(status_code: int, response: requests.Response, attempt: int) -> float:
    """Return the delay to wait before retrying a throttled or transient request."""
    retry_after = parse_retry_after(response.headers.get("Retry-After"))
    if status_code == 429 and retry_after is not None:
        return retry_after
    return min(2**attempt, 30) + random.uniform(0, 1)


def fabric_request(method: str, url: str, **kwargs) -> requests.Response:
    """Make a Fabric REST call with retry support for throttling and transient failures."""
    request_kwargs = dict(kwargs)
    headers = request_kwargs.pop("headers", None) or fabric_headers()
    timeout = request_kwargs.pop("timeout", 120)

    for attempt in range(1, FABRIC_RETRY_ATTEMPTS + 1):
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=timeout,
            **request_kwargs,
        )

        if response.status_code not in FABRIC_RETRYABLE_STATUS_CODES or attempt == FABRIC_RETRY_ATTEMPTS:
            return response

        delay = sleep_for_retry(response.status_code, response, attempt)
        log_message(
            "Throttled or transient Fabric API failure "
            f"({method} {url} -> HTTP {response.status_code}). "
            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{FABRIC_RETRY_ATTEMPTS})."
        )
        time.sleep(delay)

    raise RuntimeError("Fabric request retry loop exhausted without returning a response")


def fabric_get(url: str) -> requests.Response:
    """GET helper for Fabric REST APIs with throttling-aware retries."""
    return fabric_request("GET", url)


def fabric_post(url: str, payload: dict | None = None) -> requests.Response:
    """POST helper for Fabric REST APIs with throttling-aware retries."""
    return fabric_request("POST", url, json=payload)


def resolve_capacity_id(capacity_id_or_arm: str) -> str:
    """Resolve ARM resource ID or Fabric capacity GUID to the Fabric GUID."""
    # If it's already a GUID (no slashes), return as-is
    if "/" not in capacity_id_or_arm:
        return capacity_id_or_arm

    # It's an ARM resource ID - look up the Fabric GUID via the capacities API
    log_message("Resolving ARM capacity ID to Fabric GUID...")
    url = f"{FABRIC_API_BASE}/capacities"
    resp = fabric_get(url)
    resp.raise_for_status()

    # Extract capacity name from ARM ID (last segment)
    arm_name = capacity_id_or_arm.rstrip("/").split("/")[-1]
    for cap in resp.json().get("value", []):
        if cap["displayName"] == arm_name:
            log_message(f"Resolved capacity: {cap['id']} ({cap['displayName']})")
            return cap["id"]

    log_message(f"ERROR: Could not find Fabric capacity matching '{arm_name}'")
    sys.exit(1)


def create_workspace(name: str, capacity_id: str) -> dict:
    """Create a Fabric workspace assigned to the given capacity."""
    url = f"{FABRIC_API_BASE}/workspaces"
    payload = {"displayName": name, "capacityId": capacity_id}
    log_message(f"Creating workspace '{name}' on capacity {capacity_id[:12]}...")
    resp = fabric_post(url, payload)

    if resp.status_code == 201:
        data = resp.json()
        log_message(f"Workspace created: {data['id']}")
        return data
    elif resp.status_code == 409:
        log_message(f"Workspace '{name}' already exists. Fetching existing...")
        return get_existing_workspace(name)
    else:
        log_message(f"ERROR: Failed to create workspace: {resp.status_code} - {resp.text}")
        sys.exit(1)


def get_existing_workspace(name: str) -> dict:
    """Find an existing workspace by name."""
    url = f"{FABRIC_API_BASE}/workspaces"
    resp = fabric_get(url)
    resp.raise_for_status()
    for ws in resp.json().get("value", []):
        if ws["displayName"] == name:
            log_message(f"Found existing workspace: {ws['id']}")
            return ws
    log_message(f"ERROR: Workspace '{name}' not found.")
    sys.exit(1)


def add_workspace_member(workspace_id: str, user_oid: str, user_email: str, role: str = "Admin"):
    """Add a user to the workspace with the given role (Admin, Member, Contributor, Viewer)."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/roleAssignments"
    payload = {
        "principal": {
            "id": user_oid,
            "type": "User",
        },
        "role": role,
    }
    log_message(f"Adding '{user_email}' (OID: {user_oid}) as {role} to workspace {workspace_id[:12]}...")
    resp = fabric_post(url, payload)
    if resp.status_code in (200, 201):
        log_message(f"User added as {role} successfully.")
    elif resp.status_code == 409:
        log_message(f"User already has a role assignment on this workspace.")
    else:
        log_message(f"WARNING: Failed to add user to workspace: {resp.status_code} - {resp.text}")


def create_lakehouse(workspace_id: str, name: str) -> dict:
    """Create a lakehouse in the specified workspace."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses"
    payload = {"displayName": name}
    log_message(f"Creating lakehouse '{name}'...")
    resp = fabric_post(url, payload)

    if resp.status_code == 201:
        data = resp.json()
        log_message(f"Lakehouse created: {data['id']}")
        return data
    elif resp.status_code == 409:
        log_message(f"Lakehouse '{name}' already exists. Fetching existing...")
        return get_existing_lakehouse(workspace_id, name)
    else:
        log_message(f"ERROR: Failed to create lakehouse: {resp.status_code} - {resp.text}")
        sys.exit(1)


def get_existing_lakehouse(workspace_id: str, name: str) -> dict:
    """Find an existing lakehouse by name."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses"
    resp = fabric_get(url)
    resp.raise_for_status()
    for lh in resp.json().get("value", []):
        if lh["displayName"] == name:
            log_message(f"Found existing lakehouse: {lh['id']}")
            return lh
    log_message(f"ERROR: Lakehouse '{name}' not found in workspace.")
    sys.exit(1)


def get_lakehouse_properties(workspace_id: str, lakehouse_id: str) -> dict:
    """Get lakehouse properties including OneLake paths."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
    resp = fabric_get(url)
    resp.raise_for_status()
    return resp.json()


def download_json(filename: str) -> dict:
    """Download a JSON file from the GitHub repository."""
    url = f"{GITHUB_RAW_BASE}/{filename}"
    log_message(f"Downloading {filename}...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.json()


def flatten_products(product_data: dict) -> list[dict]:
    """Flatten nested product_data.json into a flat list of product records."""
    rows = []
    categories = product_data.get("main_categories", {})
    for category_name, category_data in categories.items():
        seasonal = category_data.get("washington_seasonal_multipliers", [])
        seasonal_str = ";".join(str(s) for s in seasonal) if seasonal else ""

        for product_type_name, products in category_data.items():
            if product_type_name == "washington_seasonal_multipliers":
                continue
            if not isinstance(products, list):
                continue
            for product in products:
                row = {
                    "category": category_name,
                    "product_type": product_type_name,
                    "name": product.get("name", ""),
                    "sku": product.get("sku", ""),
                    "price": product.get("price", 0),
                    "description": product.get("description", ""),
                    "stock_level": product.get("stock_level", 0),
                    "image_path": product.get("image_path", ""),
                    "seasonal_multipliers": seasonal_str,
                }
                if INCLUDE_EMBEDDINGS:
                    img_emb = product.get("image_embedding", [])
                    desc_emb = product.get("description_embedding", [])
                    row["image_embedding"] = json.dumps(img_emb) if img_emb else ""
                    row["description_embedding"] = (
                        json.dumps(desc_emb) if desc_emb else ""
                    )
                rows.append(row)
    return rows


def flatten_stores(reference_data: dict) -> list[dict]:
    """Flatten stores from reference_data.json."""
    rows = []
    for store_name, config in reference_data.get("stores", {}).items():
        rows.append(
            {
                "store_name": store_name,
                "rls_user_id": config.get("rls_user_id", ""),
                "customer_distribution_weight": config.get(
                    "customer_distribution_weight", 0
                ),
                "order_frequency_multiplier": config.get(
                    "order_frequency_multiplier", 0
                ),
                "order_value_multiplier": config.get("order_value_multiplier", 0),
            }
        )
    return rows


def flatten_year_weights(reference_data: dict) -> list[dict]:
    """Flatten year weights from reference_data.json."""
    rows = []
    for year, weight in reference_data.get("year_weights", {}).items():
        rows.append({"year": int(year), "weight": weight})
    return rows


def flatten_categories(product_data: dict) -> list[dict]:
    """Extract unique categories with their seasonal multipliers."""
    rows = []
    categories = product_data.get("main_categories", {})
    for category_name, category_data in categories.items():
        seasonal = category_data.get("washington_seasonal_multipliers", [])
        row = {"category_name": category_name}
        for i, month in enumerate(
            ["jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec"]
        ):
            row[f"multiplier_{month}"] = seasonal[i] if i < len(seasonal) else 1.0
        rows.append(row)
    return rows


def to_csv_bytes(rows: list[dict]) -> bytes:
    """Convert a list of dicts to CSV bytes."""
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def upload_to_onelake(
    workspace_id: str, lakehouse_id: str, filename: str, data: bytes
):
    """Upload a file to the lakehouse Files section via OneLake ADLS SDK."""
    service_client = DataLakeServiceClient(
        account_url=ONELAKE_DFS_URL, credential=get_credential()
    )

    filesystem_name = workspace_id
    directory_path = f"{lakehouse_id}/Files"

    file_system_client = service_client.get_file_system_client(filesystem_name)
    directory_client = file_system_client.get_directory_client(directory_path)
    file_client = directory_client.get_file_client(filename)

    log_message(f"Uploading {filename} ({len(data):,} bytes)...")
    file_client.upload_data(data, overwrite=True)
    log_message(f"Uploaded {filename}")


def load_table(
    workspace_id: str, lakehouse_id: str, table_name: str, filename: str
) -> str:
    """Submit a Load Table request and return the full polling URL."""
    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/lakehouses/{lakehouse_id}/tables/{table_name}/load"
    )
    payload = {
        "relativePath": f"Files/{filename}",
        "pathType": "File",
        "mode": "Overwrite",
        "formatOptions": {"header": True, "delimiter": ",", "format": "Csv"},
    }
    log_message(f"Loading table '{table_name}' from {filename}...")
    resp = fabric_post(url, payload)

    if resp.status_code == 202:
        location = resp.headers.get("Location", "")
        log_message(f"Load initiated for '{table_name}'")
        return location
    else:
        log_message(f"ERROR: Load failed for '{table_name}': {resp.status_code} - {resp.text}")
        return ""


def poll_operation(
    workspace_id: str, lakehouse_id: str, poll_url: str, timeout: int = 300
) -> bool:
    """Poll a load operation using the Location URL until complete or timeout."""
    if not poll_url:
        return False

    start = time.time()
    while time.time() - start < timeout:
        resp = fabric_get(poll_url)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", data.get("Status", ""))
            percent = data.get("percentComplete", data.get("PercentComplete", 0))

            if status in ("Succeeded", "succeeded", 3):
                log_message(f"  Operation complete (100%)")
                return True
            elif status in ("Failed", "failed", 4):
                error = data.get("error", data.get("Error", "Unknown error"))
                log_message(f"  Operation FAILED: {error}")
                return False
            else:
                time.sleep(10)
        elif resp.status_code == 202:
            # Still in progress
            time.sleep(10)
        else:
            log_message(f"  Poll response: {resp.status_code}")
            time.sleep(10)

    log_message(f"  Operation TIMEOUT after {timeout}s")
    return False


def poll_fabric_operation(operation_url: str, timeout: int = 300) -> bool:
    """Poll a Fabric long-running operation URL until it completes."""
    if not operation_url:
        return True

    start = time.time()
    while time.time() - start < timeout:
        resp = fabric_get(operation_url)
        if resp.status_code not in (200, 202):
            log_message(f"  Operation poll failed: {resp.status_code} - {resp.text}")
            return False

        data = resp.json() if resp.text else {}
        status = data.get("status", "")
        if status == "Succeeded":
            log_message("  Operation complete (100%)")
            return True
        if status == "Failed":
            log_message(f"  Operation FAILED: {json.dumps(data.get('error', data))}")
            return False

        retry_after = resp.headers.get("Retry-After")
        delay = int(retry_after) if retry_after and retry_after.isdigit() else 5
        time.sleep(delay)

    log_message(f"  Operation TIMEOUT after {timeout}s")
    return False


def create_definition_part(path: str, payload: dict) -> dict:
    """Create a Fabric item definition part with an inline base64 JSON payload."""
    json_payload = json.dumps(payload, separators=(",", ":"))
    encoded = base64.b64encode(json_payload.encode("utf-8")).decode("ascii")
    return {"path": path, "payload": encoded, "payloadType": "InlineBase64"}


def make_entity_parts(
    entity_id: int,
    entity_name: str,
    table_name: str,
    columns: list[dict],
    key_property: str,
    display_property: str,
    workspace_id: str,
    lakehouse_id: str,
) -> list[dict]:
    """Build ontology entity and lakehouse table binding definition parts."""
    properties = []
    property_bindings = []
    for offset, column in enumerate(columns, start=1):
        property_id = str((entity_id * 100) + offset)
        properties.append(
            {
                "id": property_id,
                "name": column["name"],
                "valueType": column["type"],
            }
        )
        property_bindings.append(
            {
                "sourceColumnName": column["source"],
                "targetPropertyId": property_id,
            }
        )

    property_ids = {prop["name"]: prop["id"] for prop in properties}
    definition = {
        "id": str(entity_id),
        "namespace": "usertypes",
        "baseEntityTypeId": None,
        "name": entity_name,
        "entityIdParts": [property_ids[key_property]],
        "displayNamePropertyId": property_ids[display_property],
        "namespaceType": "Custom",
        "visibility": "Visible",
        "properties": properties,
        "timeseriesProperties": [],
    }
    binding_id = str(uuid.uuid4())
    binding = {
        "id": binding_id,
        "dataBindingConfiguration": {
            "dataBindingType": "NonTimeSeries",
            "timestampColumnName": None,
            "propertyBindings": property_bindings,
            "sourceTableProperties": {
                "sourceType": "LakehouseTable",
                "workspaceId": workspace_id,
                "itemId": lakehouse_id,
                "sourceTableName": table_name,
            },
        },
    }
    return [
        create_definition_part(f"EntityTypes/{entity_id}/definition.json", definition),
        create_definition_part(
            f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json", binding
        ),
    ]


def make_relationship_parts(
    relationship_id: int,
    relationship_name: str,
    source_entity_id: int,
    target_entity_id: int,
    workspace_id: str,
    lakehouse_id: str,
    data_table_name: str,
    source_key_column: str,
    source_key_property_id: str,
    target_key_column: str,
    target_key_property_id: str,
) -> list[dict]:
    """Build ontology relationship type and contextualization (edge) definition parts.

    The contextualization binds the relationship to an existing lakehouse table that
    already contains both the source entity's key column and a column matching the
    target entity's key, so no separate join table is needed here.
    """
    definition = {
        "namespace": "usertypes",
        "id": str(relationship_id),
        "name": relationship_name,
        "namespaceType": "Custom",
        "source": {"entityTypeId": str(source_entity_id)},
        "target": {"entityTypeId": str(target_entity_id)},
    }
    contextualization_id = str(uuid.uuid4())
    contextualization = {
        "id": contextualization_id,
        "dataBindingTable": {
            "sourceType": "LakehouseTable",
            "workspaceId": workspace_id,
            "itemId": lakehouse_id,
            "sourceTableName": data_table_name,
        },
        "sourceKeyRefBindings": [
            {"sourceColumnName": source_key_column, "targetPropertyId": source_key_property_id}
        ],
        "targetKeyRefBindings": [
            {"sourceColumnName": target_key_column, "targetPropertyId": target_key_property_id}
        ],
    }
    return [
        create_definition_part(f"RelationshipTypes/{relationship_id}/definition.json", definition),
        create_definition_part(
            f"RelationshipTypes/{relationship_id}/Contextualizations/{contextualization_id}.json",
            contextualization,
        ),
    ]


def zava_entity_specs() -> list[tuple]:
    """Return the shared entity schema for JSON and TMDL ontology definitions."""
    # Ontology property names must be identifier-safe; source maps to lakehouse column names.
    return [
        (
            1001,
            "Product",
            "products",
            [
                {"name": "sku", "source": "sku", "type": "String"},
                {"name": "name", "source": "name", "type": "String"},
                {"name": "category", "source": "category", "type": "String"},
                {"name": "productType", "source": "product_type", "type": "String"},
                {"name": "price", "source": "price", "type": "Double"},
                {"name": "description", "source": "description", "type": "String"},
                {"name": "stockLevel", "source": "stock_level", "type": "BigInt"},
                {"name": "imagePath", "source": "image_path", "type": "String"},
                {
                    "name": "seasonalMultipliers",
                    "source": "seasonal_multipliers",
                    "type": "String",
                },
            ],
            "sku",
            "name",
        ),
        (
            1002,
            "Category",
            "categories",
            [
                {"name": "categoryName", "source": "category_name", "type": "String"},
                {"name": "multiplierJan", "source": "multiplier_jan", "type": "Double"},
                {"name": "multiplierFeb", "source": "multiplier_feb", "type": "Double"},
                {"name": "multiplierMar", "source": "multiplier_mar", "type": "Double"},
                {"name": "multiplierApr", "source": "multiplier_apr", "type": "Double"},
                {"name": "multiplierMay", "source": "multiplier_may", "type": "Double"},
                {"name": "multiplierJun", "source": "multiplier_jun", "type": "Double"},
                {"name": "multiplierJul", "source": "multiplier_jul", "type": "Double"},
                {"name": "multiplierAug", "source": "multiplier_aug", "type": "Double"},
                {"name": "multiplierSep", "source": "multiplier_sep", "type": "Double"},
                {"name": "multiplierOct", "source": "multiplier_oct", "type": "Double"},
                {"name": "multiplierNov", "source": "multiplier_nov", "type": "Double"},
                {"name": "multiplierDec", "source": "multiplier_dec", "type": "Double"},
            ],
            "categoryName",
            "categoryName",
        ),
        (
            1003,
            "Store",
            "stores",
            [
                {"name": "storeName", "source": "store_name", "type": "String"},
                {"name": "rlsUserId", "source": "rls_user_id", "type": "String"},
                {
                    "name": "customerDistributionWeight",
                    "source": "customer_distribution_weight",
                    "type": "Double",
                },
                {
                    "name": "orderFrequencyMultiplier",
                    "source": "order_frequency_multiplier",
                    "type": "Double",
                },
                {
                    "name": "orderValueMultiplier",
                    "source": "order_value_multiplier",
                    "type": "Double",
                },
            ],
            "storeName",
            "storeName",
        ),
        (
            1004,
            "YearWeight",
            "year_weights",
            [
                {"name": "year", "source": "year", "type": "BigInt"},
                {"name": "weight", "source": "weight", "type": "Double"},
            ],
            "year",
            "year",
        ),
    ]


def build_zava_ontology_definition(workspace_id: str, lakehouse_id: str) -> dict:
    """Build the legacy JSON ontology definition for existing old-experience items."""
    parts = [
        create_definition_part(
            ".platform",
            {"metadata": {"type": "Ontology", "displayName": FABRIC_ONTOLOGY_NAME}},
        ),
        create_definition_part("definition.json", {}),
    ]
    for spec in zava_entity_specs():
        parts.extend(make_entity_parts(*spec, workspace_id, lakehouse_id))

    # Relationship (edge): each Product belongs to a Category. The "products" table
    # already has a "category" column matching Category's key ("categoryName"), so it
    # doubles as the relationship's data-binding table -- no separate join table needed.
    # Property IDs follow make_entity_parts's `str((entity_id * 100) + offset)` scheme:
    # Product.sku is entity 1001's 1st column -> "100101"; Category.categoryName is
    # entity 1002's 1st column -> "100201".
    if INCLUDE_CATEGORY_RELATIONSHIP:
        parts.extend(
            make_relationship_parts(
                relationship_id=2001,
                relationship_name="belongsToCategory",
                source_entity_id=1001,  # Product
                target_entity_id=1002,  # Category
                workspace_id=workspace_id,
                lakehouse_id=lakehouse_id,
                data_table_name="products",
                source_key_column="sku",
                source_key_property_id="100101",  # Product.sku
                target_key_column="category",
                target_key_property_id="100201",  # Category.categoryName
            )
        )

    return {"definition": {"parts": parts}}


def create_tmdl_part(path: str, text: str) -> dict:
    return {
        "path": path,
        "payload": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "payloadType": "InlineBase64",
    }


def build_zava_tmdl_definition(
    workspace_id: str, lakehouse_properties: dict, platform_part: dict
) -> dict:
    """Bind the same workshop entities through DirectLake in new-experience items."""
    endpoint = lakehouse_properties["properties"]["sqlEndpointProperties"]
    if endpoint.get("provisioningStatus") != "Success":
        raise RuntimeError("Lakehouse SQL analytics endpoint is not ready.")
    server = endpoint["connectionString"]
    lakehouse_id = lakehouse_properties["id"]
    lakehouse_name = lakehouse_properties["displayName"]
    source_url = f"{ONELAKE_DFS_URL}/{workspace_id}/{lakehouse_id}"
    parts = [
        platform_part,
        create_tmdl_part("database.tmdl", "database\n\tcompatibilityLevel: 1000000\n"),
        create_tmdl_part("namespaces/default.tmdl", "namespace default\n"),
        create_tmdl_part(
            "expressions.tmdl",
            "expression DatabaseQuery =\n"
            "\t\tlet\n"
            f"\t\t\tSource = AzureStorage.DataLake({json.dumps(source_url)}, "
            "[HierarchicalNavigation=true])\n"
            "\t\tin\n\t\t\tSource\n",
        ),
    ]
    model = ["model Model", "", "ref namespace default"]
    types = {"String": "string", "Double": "double", "BigInt": "int64"}
    for _, entity, table, columns, key, _ in zava_entity_specs():
        table_lines = [f"table {table}"]
        entity_lines = [
            f"entity {entity}",
            f"\tbackingTable: {table}",
            f"\tkeyProperty: {key}",
        ]
        for column in columns:
            name, source = column["name"], column["source"]
            data_type = types[column["type"]]
            table_lines.extend([
                "", f"\tcolumn {source}", f"\t\tdataType: {data_type}",
                f"\t\tsourceColumn: {source}",
            ])
            entity_lines.extend([
                "", f"\tproperty {name}", f"\t\tdataType: {data_type}",
                "", "\t\tbackingConfiguration", f"\t\t\tvalueColumn: {table}.{source}",
            ])
        table_lines.extend([
            "", f"\tpartition {table} = entity", "\t\tmode: directLake",
            "\t\tsource", f"\t\t\tentityName: {table}",
            "\t\t\texpressionSource: DatabaseQuery",
            "", f"\t\tannotation ONT_WorkspaceId = {workspace_id}",
            "", f"\t\tannotation ONT_ItemId = {lakehouse_id}",
            "", "\t\tannotation ONT_ItemKind = Lakehouse",
            "", f"\t\tannotation ONT_ItemName = {lakehouse_name}",
            "", f"\t\tannotation ONT_SqlEndpoint = {server}",
            "", f"\t\tannotation ONT_SqlDatabase = {lakehouse_name}",
        ])
        parts.extend([
            create_tmdl_part(f"tables/{table}.tmdl", "\n".join(table_lines) + "\n"),
            create_tmdl_part(f"entities/{entity}.tmdl", "\n".join(entity_lines) + "\n"),
        ])
        model.extend([f"ref table {table}", f"ref entity {entity}"])
    if INCLUDE_CATEGORY_RELATIONSHIP:
        parts.extend([
            create_tmdl_part(
                "relationships.tmdl",
                "relationship product_category\n"
                "\tfromColumn: products.category\n\ttoColumn: categories.category_name\n",
            ),
            create_tmdl_part(
                "entityRelationships.tmdl",
                "entityRelationship belongsToCategory\n"
                "\tfromEntity: Product\n\ttoEntity: Category\n"
                "\n\tbackingConfiguration\n\t\trelationship: product_category\n",
            ),
        ])
    parts.append(create_tmdl_part("model.tmdl", "\n".join(model) + "\n"))
    return {"definition": {"parts": parts}}


def get_ontology_definition(workspace_id: str, ontology_id: str) -> dict:
    """Read the persisted definition, including asynchronous getDefinition results."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies/{ontology_id}/getDefinition"
    response = fabric_post(url, {})
    response.raise_for_status()
    if response.status_code == 202:
        operation_url = response.headers.get("Location", "")
        if not operation_url or not poll_fabric_operation(operation_url):
            raise RuntimeError("Ontology getDefinition operation did not complete.")
        response = fabric_get(operation_url.rstrip("/") + "/result")
        response.raise_for_status()
    return response.json()["definition"]


def is_tmdl_definition(definition: dict) -> bool:
    return any(part["path"] == "database.tmdl" for part in definition["parts"])


def verify_ontology_bindings(
    workspace_id: str, ontology_id: str, lakehouse_id: str
) -> bool:
    """Fail if a successful API update did not persist the expected data bindings."""
    definition = get_ontology_definition(workspace_id, ontology_id)
    saved = {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["parts"]
    }
    if is_tmdl_definition(definition):
        properties = get_lakehouse_properties(workspace_id, lakehouse_id)
        endpoint = properties["properties"]["sqlEndpointProperties"]
        expression = saved.get("expressions.tmdl", "")
        source = (
            f"Source = AzureStorage.DataLake("
            f"{json.dumps(f'{ONELAKE_DFS_URL}/{workspace_id}/{lakehouse_id}')}, "
            "[HierarchicalNavigation=true])"
        )
        if source not in {line.strip() for line in expression.splitlines()}:
            raise RuntimeError("Ontology has no binding to the expected OneLake source.")
        for _, entity, table, columns, key, _ in zava_entity_specs():
            entity_lines = {
                line.strip() for line in saved.get(f"entities/{entity}.tmdl", "").splitlines()
            }
            table_lines = {
                line.strip() for line in saved.get(f"tables/{table}.tmdl", "").splitlines()
            }
            expected_entity = [f"entity {entity}", f"backingTable: {table}", f"keyProperty: {key}"]
            expected_entity.extend(f"property {column['name']}" for column in columns)
            expected_entity.extend(f"valueColumn: {table}.{column['source']}" for column in columns)
            expected_table = [
                f"table {table}", "mode: directLake", f"entityName: {table}",
                "expressionSource: DatabaseQuery",
                f"annotation ONT_WorkspaceId = {workspace_id}",
                f"annotation ONT_ItemId = {lakehouse_id}",
                "annotation ONT_ItemKind = Lakehouse",
                f"annotation ONT_ItemName = {properties['displayName']}",
                f"annotation ONT_SqlEndpoint = {endpoint['connectionString']}",
                f"annotation ONT_SqlDatabase = {properties['displayName']}",
            ]
            expected_table.extend(f"column {column['source']}" for column in columns)
            expected_table.extend(f"sourceColumn: {column['source']}" for column in columns)
            if not all(value in entity_lines for value in expected_entity) or not all(
                value in table_lines for value in expected_table
            ):
                raise RuntimeError(f"Ontology data binding was not persisted for {entity}.")
    else:
        bindings = [
            json.loads(text)["dataBindingConfiguration"]
            for path, text in saved.items() if "/DataBindings/" in path
        ]
        for entity_id, entity, table, columns, _, _ in zava_entity_specs():
            expected_properties = {
                (column["source"], str(entity_id * 100 + offset))
                for offset, column in enumerate(columns, start=1)
            }
            if not any(
                binding["sourceTableProperties"].get("workspaceId") == workspace_id
                and binding["sourceTableProperties"].get("itemId") == lakehouse_id
                and binding["sourceTableProperties"].get("sourceTableName") == table
                and expected_properties <= {
                    (prop["sourceColumnName"], prop["targetPropertyId"])
                    for prop in binding.get("propertyBindings", [])
                }
                for binding in bindings
            ):
                raise RuntimeError(f"Ontology data binding was not persisted for {entity}.")
    log_message("Verified persisted data bindings for Product, Category, Store and YearWeight.")
    return True


def get_existing_ontology(workspace_id: str, name: str) -> dict | None:
    """Find an existing ontology in the specified workspace by display name."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies"
    resp = fabric_get(url)
    resp.raise_for_status()
    for ontology in resp.json().get("value", []):
        if ontology.get("displayName") == name:
            return ontology
    return None


def create_or_get_ontology(workspace_id: str, name: str) -> dict:
    """Create a Fabric IQ ontology item, or reuse an existing one with the same name."""
    if FABRIC_ONTOLOGY_ID:
        log_message(f"Using existing ontology ID from FABRIC_ONTOLOGY_ID: {FABRIC_ONTOLOGY_ID}")
        return {"id": FABRIC_ONTOLOGY_ID, "displayName": name}

    existing = get_existing_ontology(workspace_id, name)
    if existing:
        log_message(f"Found existing ontology: {existing['id']}")
        return existing

    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies"
    payload = {
        "displayName": name,
        "description": "Ontology for the Zava DIY lakehouse data.",
    }
    log_message(f"Creating ontology '{name}'...")
    try:
        resp = fabric_post(url, payload)
    except (requests.ConnectionError, requests.Timeout):
        log_message(
            "Ontology creation response was lost. Checking for the persisted item "
            "before considering another create request."
        )
        existing = get_existing_ontology(workspace_id, name)
        if existing:
            log_message(f"Recovered created ontology after transport failure: {existing['id']}")
            return existing
        raise
    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(f"Failed to create ontology: {resp.status_code} - {resp.text}")

    operation_url = resp.headers.get("Location", "")
    if operation_url and not poll_fabric_operation(operation_url):
        raise RuntimeError(f"Ontology '{name}' creation operation failed to complete.")

    # Fabric ontology create can complete asynchronously with an empty response body.
    for _ in range(12):
        existing = get_existing_ontology(workspace_id, name)
        if existing:
            log_message(f"Ontology created: {existing['id']}")
            return existing
        time.sleep(5)

    raise RuntimeError(f"Ontology '{name}' was not found after create completed.")


def update_ontology_definition(
    workspace_id: str, ontology_id: str, lakehouse_id: str
) -> bool:
    """Replace the ontology definition with Zava DIY lakehouse entity bindings."""
    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/ontologies/{ontology_id}/updateDefinition"
    )
    current = get_ontology_definition(workspace_id, ontology_id)
    if is_tmdl_definition(current):
        platform = next(part for part in current["parts"] if part["path"] == ".platform")
        payload = build_zava_tmdl_definition(
            workspace_id, get_lakehouse_properties(workspace_id, lakehouse_id), platform
        )
        log_message("Using new-experience TMDL ontology definition.")
    else:
        payload = build_zava_ontology_definition(workspace_id, lakehouse_id)
    log_message("Updating ontology definition with Zava DIY entity bindings...")
    resp = fabric_post(url, payload)
    if resp.status_code not in (200, 202):
        log_message(
            f"ERROR: Failed to start ontology definition update: "
            f"{resp.status_code} - {resp.text}"
        )
        return False

    operation_url = resp.headers.get("Location", "")
    if resp.status_code == 202 and not operation_url:
        raise RuntimeError("Ontology update returned 202 without an operation Location.")
    if operation_url and not poll_fabric_operation(operation_url):
        return False
    return verify_ontology_bindings(workspace_id, ontology_id, lakehouse_id)


def find_graph_model_item(workspace_id: str, ontology_id: str) -> dict | None:
    """Find the GraphModel item Fabric auto-creates alongside an ontology."""
    resp = fabric_get(f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items")
    resp.raise_for_status()
    suffix = ontology_id.replace("-", "")
    for item in resp.json().get("value", []):
        if item.get("type") == "GraphModel" and item.get("displayName", "").endswith(f"_graph_{suffix}"):
            return item
    return None


def get_latest_job_instance(workspace_id: str, item_id: str) -> dict | None:
    """Return the most recently started job instance for a Fabric item, if any."""
    resp = fabric_get(f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}/jobs/instances")
    resp.raise_for_status()
    instances = resp.json().get("value", [])
    if not instances:
        return None
    return max(instances, key=lambda job: job.get("startTimeUtc", ""))


def wait_for_graph_model_ready(
    workspace_id: str,
    ontology_id: str,
    lakehouse_id: str,
    max_attempts: int = 3,
    poll_interval: int = 15,
    poll_timeout: int = 300,
    retry_wait: int = 90,
    new_job_timeout: int = 60,
) -> bool:
    """Wait for the ontology's GraphModel refresh to succeed, retrying on GraphNotRefreshable.

    Right after tables are loaded, Fabric's first automatic graph refresh can fail with
    "GraphNotRefreshable: Graph doesn't have valid content and cannot be refreshed." because
    the lakehouse's SQL analytics endpoint hasn't finished syncing the newly written Delta
    tables yet. This is a timing race, not a schema problem: re-pushing the definition after
    a short wait re-triggers the refresh and it succeeds once the sync catches up.
    """
    if is_tmdl_definition(get_ontology_definition(workspace_id, ontology_id)):
        # New-experience items query DirectLake and do not create the legacy GraphModel.
        return verify_ontology_bindings(workspace_id, ontology_id, lakehouse_id)

    graph_item = find_graph_model_item(workspace_id, ontology_id)
    if not graph_item:
        log_message("WARNING: Could not locate the ontology's GraphModel item to verify readiness.")
        return False

    last_seen_job_id = None

    for attempt in range(1, max_attempts + 1):
        # Fabric doesn't register a new job instance the moment updateDefinition returns,
        # so wait for one with an id different from the last attempt's before evaluating it
        # (otherwise we'd re-read the previous attempt's already-terminal job).
        job = None
        waited = 0
        while waited <= new_job_timeout:
            job = get_latest_job_instance(workspace_id, graph_item["id"])
            if job and job.get("id") != last_seen_job_id:
                break
            time.sleep(poll_interval)
            waited += poll_interval

        waited = 0
        while waited <= poll_timeout:
            job = get_latest_job_instance(workspace_id, graph_item["id"])
            status = job.get("status") if job else None
            if status in ("Completed", "Failed", "Cancelled", "Deduped"):
                break
            time.sleep(poll_interval)
            waited += poll_interval

        last_seen_job_id = job.get("id") if job else last_seen_job_id
        status = job.get("status") if job else None
        if status == "Completed":
            log_message("GraphModel refresh completed successfully.")
            return True

        error_code = (job.get("failureReason") or {}).get("errorCode") if job else None
        log_message(
            f"GraphModel refresh attempt {attempt}/{max_attempts} did not complete "
            f"(status={status}, errorCode={error_code})."
        )
        if attempt == max_attempts:
            return False
        if status == "InProgress":
            log_message("Still building; continuing to wait...")
            continue

        log_message(f"Likely a lakehouse sync race condition. Waiting {retry_wait}s and retrying...")
        time.sleep(retry_wait)
        if not update_ontology_definition(workspace_id, ontology_id, lakehouse_id):
            return False

    return False


def main():
    """Main execution flow."""
    log_message("=" * 60)
    log_message("Fabric Lakehouse Creator - Zava DIY Dataset")
    log_message("=" * 60)

    # Resolve workspace: use provided ID, or create one on the given capacity
    workspace_id = WORKSPACE_ID
    if not workspace_id and FABRIC_CAPACITY_ID:
        # Only resolve the capacity when we actually need it (to create a workspace)
        capacity_guid = resolve_capacity_id(FABRIC_CAPACITY_ID)
        # Persist the resolved GUID immediately so it's available even if later step fails
        update_root_env({"FABRIC_CAPACITY_ID": capacity_guid})
        log_message("Updated repo root .env with FABRIC_CAPACITY_ID")
        log_message("No workspace ID provided. Creating workspace on Fabric capacity...")
        # Use a unique workspace name to avoid collisions with leftover
        # workspaces from previous lab sessions in the same tenant.
        workspace_name = f"ZavaDIY-{uuid.uuid4().hex[:8]}"
        ws = create_workspace(workspace_name, capacity_guid)
        workspace_id = ws["id"]
        update_root_env({"FABRIC_WORKSPACE_ID": workspace_id})
        log_message("Updated repo root .env with FABRIC_WORKSPACE_ID")
    elif not workspace_id:
        workspace_id = input("Enter your Fabric Workspace ID: ").strip()
        if not workspace_id:
            log_message("ERROR: Workspace ID is required (or set FABRIC_CAPACITY_ID to auto-create).")
            sys.exit(1)
        update_root_env({"FABRIC_WORKSPACE_ID": workspace_id})
        log_message("Updated repo root .env with FABRIC_WORKSPACE_ID")
    else:
        update_root_env({"FABRIC_WORKSPACE_ID": workspace_id})
        log_message("Updated repo root .env with FABRIC_WORKSPACE_ID")

    log_message(f"Workspace ID: {workspace_id}")
    log_message(f"Lakehouse Name: {LAKEHOUSE_NAME}")
    log_message(f"Ontology Name: {FABRIC_ONTOLOGY_NAME}")
    log_message(f"Tenant ID: {FABRIC_TENANT_ID or '(default credential tenant)'}")
    log_message(f"Include Embeddings: {INCLUDE_EMBEDDINGS}")

    # Add lab user as Admin so they can see and use the workspace
    if FABRIC_LAB_USER_OID:
        add_workspace_member(workspace_id, FABRIC_LAB_USER_OID, FABRIC_LAB_USER_UPN, "Admin")
    elif FABRIC_LAB_USER_UPN:
        log_message(f"WARNING: No object ID for lab user, cannot add to workspace")

    try:
        total_steps = 6 if CREATE_ONTOLOGY else 5

        # Step 1: Create Lakehouse
        log_message(f"\n[1/{total_steps}] Creating Lakehouse")
        lakehouse = create_lakehouse(workspace_id, LAKEHOUSE_NAME)
        lakehouse_id = lakehouse["id"]

        # Step 2: Get lakehouse properties
        log_message(f"\n[2/{total_steps}] Getting Lakehouse Properties")
        props = get_lakehouse_properties(workspace_id, lakehouse_id)
        onelake_files = props.get("properties", {}).get("oneLakeFilesPath", "")
        log_message(f"OneLake Files Path: {onelake_files}")

        # Step 3: Download and process data
        log_message(f"\n[3/{total_steps}] Downloading and Processing Dataset")
        product_data = download_json("product_data.json")
        reference_data = download_json("reference_data.json")

        tables = {
            "products": (flatten_products(product_data), "products.csv"),
            "categories": (flatten_categories(product_data), "categories.csv"),
            "stores": (flatten_stores(reference_data), "stores.csv"),
            "year_weights": (flatten_year_weights(reference_data), "year_weights.csv"),
        }

        for table_name, (rows, _) in tables.items():
            log_message(f"  {table_name}: {len(rows)} rows")

        # Step 4: Upload CSVs to OneLake
        log_message(f"\n[4/{total_steps}] Uploading CSVs to OneLake")
        for table_name, (rows, filename) in tables.items():
            csv_data = to_csv_bytes(rows)
            upload_to_onelake(workspace_id, lakehouse_id, filename, csv_data)

        # Step 5: Load tables
        log_message(f"\n[5/{total_steps}] Loading Delta Tables")
        operations = {}
        for table_name, (_, filename) in tables.items():
            poll_url = load_table(workspace_id, lakehouse_id, table_name, filename)
            if poll_url:
                operations[table_name] = poll_url

        # Poll all operations
        log_message("\nWaiting for table loads to complete...")
        results = {}
        for table_name, poll_url in operations.items():
            log_message(f"Polling '{table_name}'...")
            results[table_name] = poll_operation(workspace_id, lakehouse_id, poll_url)

        # Summary
        log_message("\n" + "=" * 60)
        log_message("SUMMARY")
        log_message("=" * 60)
        log_message(f"Lakehouse: {LAKEHOUSE_NAME} ({lakehouse_id})")
        log_message(f"Workspace: {workspace_id}")
        log_message("Tables loaded:")
        for table_name in tables:
            success = results.get(table_name, False)
            status = "SUCCESS" if success else "FAILED"
            log_message(f"  {status}: {table_name}")
        table_success = set(results) == set(tables) and all(results.values())

        ontology = None
        ontology_success = True
        if CREATE_ONTOLOGY and table_success:
            log_message(f"\n[6/{total_steps}] Creating Fabric IQ Ontology")
            try:
                ontology = create_or_get_ontology(workspace_id, FABRIC_ONTOLOGY_NAME)
                ontology_success = update_ontology_definition(
                    workspace_id, ontology["id"], lakehouse_id
                )
                status = "SUCCESS" if ontology_success else "FAILED"
                log_message(f"  {status}: {FABRIC_ONTOLOGY_NAME} ({ontology['id']})")

                if ontology_success:
                    log_message("Verifying the ontology's GraphModel refresh (retries on lakehouse sync races)...")
                    graph_ready = wait_for_graph_model_ready(
                        workspace_id, ontology["id"], lakehouse_id
                    )
                    if not graph_ready:
                        ontology_success = False
                        log_message(
                            "  ERROR: GraphModel did not confirm ready after retries. "
                            "Fabric IQ queries may fail until it finishes building; re-run "
                            "this script later or retry the Part 3/5 notebook cell."
                        )
            except Exception as e:
                ontology = None
                ontology_success = False
                log_message(f"  FAILED: Ontology setup failed ({type(e).__name__}: {e})")
                log_message(
                    "  This is often caused by the Fabric IQ Ontology feature not being "
                    "available yet in this tenant/region. Lakehouse and tables were still "
                    "created successfully. Part 3/5 (Fabric IQ) of the workshop may not "
                    "work until this feature becomes available."
                )
        elif CREATE_ONTOLOGY:
            ontology_success = False
            log_message("  FAILED: Skipped ontology setup because table loading failed.")

        log_message("=" * 60)

        if ontology and ontology_success:
            log_message(f"Ontology: {FABRIC_ONTOLOGY_NAME} ({ontology['id']})")
            update_root_env({"FABRIC_ONTOLOGY_ID": ontology["id"]})
            log_message("Updated repo root .env with FABRIC_ONTOLOGY_ID")

        if table_success and ontology_success:
            log_message("\nAll tables and ontology setup completed successfully!")
            return True
        elif table_success:
            log_message(
                "\nERROR: Lakehouse and tables were created successfully, but ontology "
                "setup failed or was unavailable. Repair the existing ontology before "
                "running the Fabric notebooks."
            )
            return False
        else:
            log_message("\nWARNING: Some tables or ontology setup failed.")
            return False

    except Exception as e:
        log_message(f"ERROR: {type(e).__name__}: {str(e)}")
        log_message(f"Traceback:\n{traceback.format_exc()}")
        return False
    finally:
        reorder_env_sections()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
