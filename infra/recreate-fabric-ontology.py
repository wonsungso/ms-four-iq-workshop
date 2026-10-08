#!/usr/bin/env python3
"""Repair or recreate Fabric ontology bindings and rebind Search knowledge source.

Usage:
  python infra/recreate-fabric-ontology.py
  python infra/recreate-fabric-ontology.py --ontology-name ZavaDIYOntology_20260714_090000
  python infra/recreate-fabric-ontology.py --skip-rebind
  python infra/recreate-fabric-ontology.py --repair-existing
  python infra/recreate-fabric-ontology.py --verify-only
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
from datetime import datetime
from pathlib import Path

from azure.identity import DefaultAzureCredential
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


def rebind_fabric_knowledge_source(search_endpoint: str, workspace_id: str, ontology_id: str) -> None:
    credential = DefaultAzureCredential()
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
    parser = argparse.ArgumentParser(description="Repair, verify, or recreate Fabric ontology bindings")
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--repair-existing",
        action="store_true",
        help="Repair bindings on FABRIC_ONTOLOGY_ID without creating any resources.",
    )
    mode.add_argument(
        "--verify-only",
        action="store_true",
        help="Check persisted bindings on FABRIC_ONTOLOGY_ID without changing resources or .env.",
    )
    args = parser.parse_args()
    if args.ontology_name and (args.repair_existing or args.verify_only):
        parser.error("--ontology-name cannot be used with --repair-existing or --verify-only")

    load_dotenv(dotenv_path=ENV_PATH, override=True)

    workspace_id = _strip_quotes(os.getenv("FABRIC_WORKSPACE_ID"))
    lakehouse_name = _strip_quotes(os.getenv("LAKEHOUSE_NAME")) or DEFAULT_LAKEHOUSE_NAME
    search_endpoint = _strip_quotes(os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT"))

    if not workspace_id:
        raise RuntimeError("FABRIC_WORKSPACE_ID is required in .env")
    if not args.skip_rebind and not args.verify_only and not search_endpoint:
        raise RuntimeError("AZURE_SEARCH_SERVICE_ENDPOINT is required in .env for rebinding")

    raw_name = args.ontology_name.strip() if args.ontology_name else generate_default_ontology_name()
    ontology_name = sanitize_ontology_name(raw_name)

    old_ontology_id = _strip_quotes(os.getenv("FABRIC_ONTOLOGY_ID"))

    if args.repair_existing or args.verify_only:
        if not old_ontology_id:
            raise RuntimeError("FABRIC_ONTOLOGY_ID is required for repair or verification.")
    module = load_create_lakehouse_module()

    lakehouse = module.get_existing_lakehouse(workspace_id, lakehouse_name)
    if args.verify_only:
        module.verify_ontology_bindings(workspace_id, old_ontology_id, lakehouse["id"])
        print("Persisted ontology data bindings verified. No resources or .env values changed.")
        return 0
    if args.repair_existing:
        response = module.fabric_get(
            f"{module.FABRIC_API_BASE}/workspaces/{workspace_id}/ontologies/{old_ontology_id}"
        )
        response.raise_for_status()
        ontology = response.json()
        ontology_name = ontology["displayName"]
        module.FABRIC_ONTOLOGY_NAME = ontology_name
    else:
        module.FABRIC_ONTOLOGY_ID = ""
        module.FABRIC_ONTOLOGY_NAME = ontology_name
        ontology = module.create_or_get_ontology(workspace_id, ontology_name)

    ok = module.update_ontology_definition(workspace_id, ontology["id"], lakehouse["id"])
    if not ok:
        raise RuntimeError("Ontology definition update failed")

    graph_ready = module.wait_for_graph_model_ready(workspace_id, ontology["id"], lakehouse["id"])
    if not graph_ready:
        raise RuntimeError("GraphModel readiness verification failed. Existing .env values were preserved.")

    if not args.skip_rebind:
        rebind_fabric_knowledge_source(
            search_endpoint=search_endpoint,
            workspace_id=workspace_id,
            ontology_id=ontology["id"],
        )

    set_key(str(ENV_PATH), "FABRIC_ONTOLOGY_ID", ontology["id"])
    set_key(str(ENV_PATH), "FABRIC_ONTOLOGY_NAME", ontology_name)
    module.reorder_env_sections()

    print("=== Fabric Ontology Binding Repair Complete ===" if args.repair_existing else "=== Fabric Ontology Recreate Complete ===")
    print(f"Old FABRIC_ONTOLOGY_ID: {old_ontology_id or '(empty)'}")
    print(f"New FABRIC_ONTOLOGY_NAME: {ontology_name}")
    print(f"New FABRIC_ONTOLOGY_ID: {ontology['id']}")
    print(f"Workspace ID: {workspace_id}")
    print(f"Lakehouse ID: {lakehouse['id']}")
    print(f"Rebound knowledge source: {not args.skip_rebind}")
    print("Persisted bindings verified. Live query execution has not been verified by this command.")
    print("Next: rerun Part 3 from environment loading, then verify Fabric activity and references.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
