#!/usr/bin/env python3
"""Recreate Fabric ontology, update .env, and rebind Search knowledge source.

Usage:
  python infra/recreate-fabric-ontology.py
  python infra/recreate-fabric-ontology.py --ontology-name ZavaDIYOntology_20260714_090000
  python infra/recreate-fabric-ontology.py --skip-rebind
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
from datetime import datetime
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    FabricOntologyKnowledgeSource,
    FabricOntologyKnowledgeSourceParameters,
)
from dotenv import load_dotenv, set_key

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
LAKEHOUSE_SCRIPT = REPO_ROOT / "infra" / "create-lakehouse.py"

FABRIC_KNOWLEDGE_SOURCE_NAME = "fabric-ontology-knowledge-source"
DEFAULT_LAKEHOUSE_NAME = "ZavaDIYLakehouse"


def _strip_quotes(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def sanitize_ontology_name(name: str) -> str:
    """Fabric ontology names allow letters, digits, and underscore only."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not sanitized:
        sanitized = "ZavaDIYOntology"
    if not sanitized[0].isalpha():
        sanitized = f"Zava_{sanitized}"
    return sanitized[:89]


def generate_default_ontology_name() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"ZavaDIYOntology_{ts}"


def load_create_lakehouse_module():
    spec = importlib.util.spec_from_file_location("create_lakehouse", str(LAKEHOUSE_SCRIPT))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load create-lakehouse.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rebind_fabric_knowledge_source(search_endpoint: str, admin_key: str, workspace_id: str, ontology_id: str) -> None:
    credential = AzureKeyCredential(admin_key)
    client = SearchIndexClient(endpoint=search_endpoint, credential=credential)

    knowledge_source = FabricOntologyKnowledgeSource(
        name=FABRIC_KNOWLEDGE_SOURCE_NAME,
        description="Zava Fabric Ontology 지식 소스",
        fabric_ontology_parameters=FabricOntologyKnowledgeSourceParameters(
            workspace_id=workspace_id,
            ontology_id=ontology_id,
        ),
    )
    client.create_or_update_knowledge_source(knowledge_source=knowledge_source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recreate Fabric ontology and update .env")
    parser.add_argument(
        "--ontology-name",
        default="",
        help="Optional ontology name. If omitted, a timestamped name is generated.",
    )
    parser.add_argument(
        "--skip-rebind",
        action="store_true",
        help="Skip rebinding fabric-ontology-knowledge-source in Azure AI Search.",
    )
    args = parser.parse_args()

    load_dotenv(dotenv_path=ENV_PATH, override=True)

    workspace_id = _strip_quotes(os.getenv("FABRIC_WORKSPACE_ID"))
    lakehouse_name = _strip_quotes(os.getenv("LAKEHOUSE_NAME")) or DEFAULT_LAKEHOUSE_NAME
    search_endpoint = _strip_quotes(os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT"))
    search_admin_key = _strip_quotes(os.getenv("AZURE_SEARCH_ADMIN_KEY"))

    if not workspace_id:
        raise RuntimeError("FABRIC_WORKSPACE_ID is required in .env")
    if not args.skip_rebind and (not search_endpoint or not search_admin_key):
        raise RuntimeError("AZURE_SEARCH_SERVICE_ENDPOINT and AZURE_SEARCH_ADMIN_KEY are required for rebinding")

    raw_name = args.ontology_name.strip() if args.ontology_name else generate_default_ontology_name()
    ontology_name = sanitize_ontology_name(raw_name)

    old_ontology_id = _strip_quotes(os.getenv("FABRIC_ONTOLOGY_ID"))

    # Force create_or_get_ontology to create a new ontology instead of reusing old ID.
    os.environ["FABRIC_ONTOLOGY_ID"] = ""
    set_key(str(ENV_PATH), "FABRIC_ONTOLOGY_ID", "")
    set_key(str(ENV_PATH), "FABRIC_ONTOLOGY_NAME", ontology_name)

    module = load_create_lakehouse_module()

    lakehouse = module.get_existing_lakehouse(workspace_id, lakehouse_name)
    ontology = module.create_or_get_ontology(workspace_id, ontology_name)

    ok = module.update_ontology_definition(workspace_id, ontology["id"], lakehouse["id"])
    if not ok:
        raise RuntimeError("Ontology definition update failed")

    set_key(str(ENV_PATH), "FABRIC_ONTOLOGY_ID", ontology["id"])
    if hasattr(module, "reorder_env_sections"):
        module.reorder_env_sections()

    if not args.skip_rebind:
        rebind_fabric_knowledge_source(
            search_endpoint=search_endpoint,
            admin_key=search_admin_key,
            workspace_id=workspace_id,
            ontology_id=ontology["id"],
        )

    print("=== Fabric Ontology Recreate Complete ===")
    print(f"Old FABRIC_ONTOLOGY_ID: {old_ontology_id or '(empty)'}")
    print(f"New FABRIC_ONTOLOGY_NAME: {ontology_name}")
    print(f"New FABRIC_ONTOLOGY_ID: {ontology['id']}")
    print(f"Workspace ID: {workspace_id}")
    print(f"Lakehouse ID: {lakehouse['id']}")
    print(f"Rebound knowledge source: {not args.skip_rebind}")
    print("Next: rerun Part 3 notebook cell 8, cell 10, cell 12, then check cell 14.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
