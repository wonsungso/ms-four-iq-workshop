import ast
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "infra" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    with patch("dotenv.load_dotenv"):
        spec.loader.exec_module(module)
    return module


lakehouse = load_script("create-lakehouse")
recovery = load_script("recreate-fabric-ontology")
PROPERTIES = {
    "id": "lakehouse",
    "displayName": "TestLakehouse",
    "properties": {
        "sqlEndpointProperties": {
            "id": "test-sql-endpoint",
            "connectionString": "test.datawarehouse.fabric.microsoft.com",
            "provisioningStatus": "Success",
        }
    }
}
PLATFORM = lakehouse.create_definition_part(
    ".platform", {"metadata": {"type": "Ontology", "displayName": "TestOntology"}}
)


class OntologyBindingsTests(unittest.TestCase):
    def setUp(self):
        self.log = patch.object(lakehouse, "log_message")
        self.log.start()
        self.addCleanup(self.log.stop)

    def tmdl(self):
        return lakehouse.build_zava_tmdl_definition("workspace", PROPERTIES, PLATFORM)["definition"]

    def verify(self, definition):
        with patch.object(lakehouse, "get_ontology_definition", return_value=definition), \
             patch.object(lakehouse, "get_lakehouse_properties", return_value=PROPERTIES):
            return lakehouse.verify_ontology_bindings("workspace", "ontology", "lakehouse")

    def test_lost_create_response_reuses_persisted_item(self):
        existing = {"id": "created-ontology", "displayName": "TestOntology"}
        with patch.object(lakehouse, "FABRIC_ONTOLOGY_ID", ""), \
             patch.object(lakehouse, "get_existing_ontology", side_effect=[None, existing]), \
             patch.object(lakehouse, "fabric_post", side_effect=lakehouse.requests.ConnectionError):
            self.assertEqual(
                lakehouse.create_or_get_ontology("workspace", "TestOntology"), existing
            )

    def test_lost_create_response_without_item_is_not_success(self):
        with patch.object(lakehouse, "FABRIC_ONTOLOGY_ID", ""), \
             patch.object(lakehouse, "get_existing_ontology", return_value=None), \
             patch.object(lakehouse, "fabric_post", side_effect=lakehouse.requests.Timeout):
            with self.assertRaises(lakehouse.requests.Timeout):
                lakehouse.create_or_get_ontology("workspace", "TestOntology")

    def test_new_and_legacy_definitions_have_all_bindings(self):
        self.assertTrue(self.verify(self.tmdl()))
        legacy = lakehouse.build_zava_ontology_definition("workspace", "lakehouse")["definition"]
        self.assertTrue(self.verify(legacy))

    def test_tmdl_expression_types_and_relationship(self):
        with patch.object(lakehouse, "INCLUDE_CATEGORY_RELATIONSHIP", True):
            parts = {
                p["path"]: base64.b64decode(p["payload"]).decode()
                for p in self.tmdl()["parts"]
            }
        expression = parts["expressions.tmdl"]
        self.assertIn("let\n", expression)
        self.assertIn("\t\tin\n", expression)
        self.assertIn(
            'AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/workspace/lakehouse", '
            '[HierarchicalNavigation=true])', expression
        )
        self.assertNotIn("Sql.Database", expression)
        self.assertIn("annotation ONT_ItemKind = Lakehouse", parts["tables/products.tmdl"])
        self.assertIn("annotation ONT_SqlDatabase = TestLakehouse", parts["tables/products.tmdl"])
        self.assertNotIn("schemaName: dbo", parts["tables/products.tmdl"])
        self.assertIn("\tproperty stockLevel\n\t\tdataType: int64", parts["entities/Product.tmdl"])
        self.assertIn("\tproperty price\n\t\tdataType: double", parts["entities/Product.tmdl"])
        self.assertIn("\t\t\tvalueColumn: products.product_type", parts["entities/Product.tmdl"])
        self.assertIn("\tbackingConfiguration\n\t\trelationship: product_category", parts["entityRelationships.tmdl"])

    def test_unready_sql_endpoint_is_rejected(self):
        properties = copy.deepcopy(PROPERTIES)
        properties["properties"]["sqlEndpointProperties"]["provisioningStatus"] = "InProgress"
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            lakehouse.build_zava_tmdl_definition("workspace", properties, PLATFORM)

    def test_empty_and_partial_definitions_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "not persisted"):
            self.verify({"parts": []})
        definition = self.tmdl()
        definition["parts"] = [p for p in definition["parts"] if p["path"] != "entities/Product.tmdl"]
        with self.assertRaisesRegex(RuntimeError, "Product"):
            self.verify(definition)

    def test_wrong_endpoint_and_prefix_matches_are_rejected(self):
        for path, old, new, error in (
            ("expressions.tmdl", "/workspace/lakehouse", "/workspace/wrong-lakehouse", "OneLake"),
            ("tables/products.tmdl", "annotation ONT_ItemKind = Lakehouse", "", "Product"),
            ("tables/products.tmdl", "annotation ONT_ItemId = lakehouse", "annotation ONT_ItemId = wrong", "Product"),
            ("tables/products.tmdl", "annotation ONT_WorkspaceId = workspace", "annotation ONT_WorkspaceId = wrong", "Product"),
            ("tables/products.tmdl", "annotation ONT_SqlDatabase = TestLakehouse", "annotation ONT_SqlDatabase = test-sql-endpoint", "Product"),
            ("tables/products.tmdl", "annotation ONT_SqlEndpoint = test.datawarehouse.fabric.microsoft.com", "annotation ONT_SqlEndpoint = wrong", "Product"),
            ("entities/Product.tmdl", "valueColumn: products.stock_level", "valueColumn: products.stock_level_extra", "Product"),
            ("entities/Product.tmdl", "property stockLevel", "property incorrectStockLevel", "Product"),
            ("tables/products.tmdl", "sourceColumn: stock_level", "sourceColumn: wrong_stock", "Product"),
        ):
            with self.subTest(path=path, replacement=new):
                definition = self.tmdl()
                part = next(p for p in definition["parts"] if p["path"] == path)
                text = base64.b64decode(part["payload"]).decode().replace(old, new)
                part["payload"] = base64.b64encode(text.encode()).decode()
                with self.assertRaisesRegex(RuntimeError, error):
                    self.verify(definition)

    def test_wrong_legacy_lakehouse_is_rejected(self):
        definition = lakehouse.build_zava_ontology_definition("workspace", "other-lakehouse")["definition"]
        with self.assertRaisesRegex(RuntimeError, "Product"):
            self.verify(definition)

    def test_http_success_without_persisted_bindings_is_rejected(self):
        response = Mock(status_code=200, headers={})
        with patch.object(lakehouse, "get_ontology_definition", return_value={"parts": []}), \
             patch.object(lakehouse, "fabric_post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "not persisted"):
                lakehouse.update_ontology_definition("workspace", "ontology", "lakehouse")

    def test_async_definition_readback(self):
        response = Mock(status_code=202, headers={"Location": "https://api.fabric.microsoft.com/v1/operations/test"})
        result = Mock()
        result.json.return_value = {"definition": self.tmdl()}
        with patch.object(lakehouse, "fabric_post", return_value=response), \
             patch.object(lakehouse, "poll_fabric_operation", return_value=True) as poll, \
             patch.object(lakehouse, "fabric_get", return_value=result) as get:
            self.assertTrue(lakehouse.is_tmdl_definition(lakehouse.get_ontology_definition("workspace", "ontology")))
            poll.assert_called_once_with(response.headers["Location"])
            get.assert_called_once_with(response.headers["Location"] + "/result")

    def test_missing_async_location_is_rejected(self):
        response = Mock(status_code=202, headers={})
        with patch.object(lakehouse, "fabric_post", return_value=response), \
             patch.object(lakehouse, "get_ontology_definition", return_value={"parts": []}):
            with self.assertRaisesRegex(RuntimeError, "Location"):
                lakehouse.update_ontology_definition("workspace", "ontology", "lakehouse")
        with patch.object(lakehouse, "fabric_post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "did not complete"):
                lakehouse.get_ontology_definition("workspace", "ontology")

    def test_tmdl_does_not_wait_for_legacy_graph(self):
        with patch.object(lakehouse, "get_ontology_definition", return_value=self.tmdl()), \
             patch.object(lakehouse, "verify_ontology_bindings", return_value=True) as verify, \
             patch.object(lakehouse, "find_graph_model_item") as find:
            self.assertTrue(lakehouse.wait_for_graph_model_ready("workspace", "ontology", "lakehouse"))
            verify.assert_called_once_with("workspace", "ontology", "lakehouse")
            find.assert_not_called()


class RecoveryTests(unittest.TestCase):
    def run_recovery(self, args, module):
        with patch.dict(os.environ, {
            "FABRIC_WORKSPACE_ID": "workspace",
            "FABRIC_ONTOLOGY_ID": "existing-ontology",
            "LAKEHOUSE_NAME": "TestLakehouse",
            "AZURE_SEARCH_SERVICE_ENDPOINT": "https://test.search.windows.net",
        }), patch.object(recovery, "load_dotenv"), \
             patch.object(recovery, "load_create_lakehouse_module", return_value=module), \
             patch("sys.argv", ["recreate-fabric-ontology.py", *args]), \
             patch.object(recovery, "set_key") as write, \
             patch.object(recovery, "rebind_fabric_knowledge_source") as rebind:
            return recovery.main(), write, rebind

    def test_verify_only_does_not_mutate_resources_or_env(self):
        module = Mock()
        module.get_existing_lakehouse.return_value = {"id": "lakehouse"}
        result, write, rebind = self.run_recovery(["--verify-only"], module)
        self.assertEqual(result, 0)
        module.verify_ontology_bindings.assert_called_once_with("workspace", "existing-ontology", "lakehouse")
        module.create_or_get_ontology.assert_not_called()
        module.update_ontology_definition.assert_not_called()
        module.fabric_post.assert_not_called()
        write.assert_not_called()
        rebind.assert_not_called()

    def test_failed_repair_or_rebind_preserves_env(self):
        for failure in ("definition", "readiness", "rebind"):
            with self.subTest(failure=failure):
                module = Mock()
                module.get_existing_lakehouse.return_value = {"id": "lakehouse"}
                module.fabric_get.return_value.json.return_value = {
                    "id": "existing-ontology", "displayName": "TestOntology"
                }
                module.update_ontology_definition.return_value = failure != "definition"
                module.wait_for_graph_model_ready.return_value = failure != "readiness"
                with patch.dict(os.environ, {
                    "FABRIC_WORKSPACE_ID": "workspace", "FABRIC_ONTOLOGY_ID": "existing-ontology",
                    "AZURE_SEARCH_SERVICE_ENDPOINT": "https://test.search.windows.net",
                }), patch.object(recovery, "load_dotenv"), \
                     patch.object(recovery, "load_create_lakehouse_module", return_value=module), \
                     patch("sys.argv", ["recovery", "--repair-existing"]), \
                     patch.object(recovery, "set_key") as write, \
                     patch.object(recovery, "rebind_fabric_knowledge_source", side_effect=RuntimeError("rebind")):
                    with self.assertRaises(RuntimeError):
                        recovery.main()
                    write.assert_not_called()
                    module.create_or_get_ontology.assert_not_called()


class NotebookValidationTests(unittest.TestCase):
    def test_notebook_syntax_and_cleared_outputs(self):
        for filename in (
            "part2-search-mcp-kb.ipynb", "part3-fabric-iq-to-kb.ipynb",
            "part4-work-iq-to-kb.ipynb", "part5-except-workiq-kb.ipynb",
            "part6-work-iq-fabric-iq-to-kb.ipynb",
        ):
            notebook = json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    source = "".join(cell["source"])
                    ast.parse(source, filename=filename)
                    self.assertIsNone(cell["execution_count"])
                    self.assertEqual(cell["outputs"], [])

    def test_required_external_sources_reject_errors_and_missing_references(self):
        for filename, cell_id, required_types in (
            ("part2-search-mcp-kb.ipynb", "58fd44c6", {"mcpServer"}),
            ("part4-work-iq-to-kb.ipynb", "ac01b5b5", {"workIQ"}),
            ("part5-except-workiq-kb.ipynb", "c638792b", {"mcpServer"}),
            ("part6-work-iq-fabric-iq-to-kb.ipynb", "115e8899", {"mcpServer", "workIQ"}),
        ):
            notebook = json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8"))
            source = next("".join(c["source"]) for c in notebook["cells"] if c["id"] == cell_id)
            start = source.index("source_errors =")
            end = source.index("fabric_answer =" if "fabric_answer =" in source else "display(Markdown", start)
            validation = source[start:end]
            for reference_types in (required_types, set(), *({t} for t in required_types)):
                for has_error in (False, True):
                    with self.subTest(filename=filename, references=reference_types, has_error=has_error):
                        error = {"message": "Source authentication or entitlement failed"} if has_error else None
                        activity = SimpleNamespace(error=error, as_dict=lambda: {"error": error})
                        context = {
                            "result": SimpleNamespace(
                                activity=[activity],
                                references=[SimpleNamespace(type=t) for t in reference_types],
                            ),
                            "json": json,
                        }
                        with patch("builtins.print"):
                            if not has_error and required_types.issubset(reference_types):
                                exec(validation, context)
                            else:
                                with self.assertRaises(RuntimeError):
                                    exec(validation, context)

    def test_part3_rejects_partial_fabric_success(self):
        notebook = json.loads((ROOT / "notebooks" / "part3-fabric-iq-to-kb.ipynb").read_text(encoding="utf-8"))
        source = next("".join(c["source"]) for c in notebook["cells"] if c["id"] == "0b5f69ae")
        validation = source[source.index("fabric_activities ="):source.index("display(Markdown(result.response")]
        activity = SimpleNamespace(type="fabricOntology", as_dict=lambda: {"type": "fabricOntology"})
        failure = SimpleNamespace(type="fabricOntology", as_dict=lambda: {"type": "fabricOntology", "error": {"code": "InvalidAgentRetrievalRequest"}})
        reference = SimpleNamespace(type="fabricOntology")
        for activities, references, succeeds in (([], [reference], False), ([failure], [reference], False), ([activity], [], False), ([activity], [reference], True)):
            with self.subTest(succeeds=succeeds, activities=activities, references=references):
                context = {"result": SimpleNamespace(activity=activities, references=references), "json": json}
                if succeeds:
                    exec(validation, context)
                else:
                    with self.assertRaisesRegex(RuntimeError, "Fabric IQ"):
                        exec(validation, context)

    def test_parts5_and6_reject_failures_and_accept_retry_success(self):
        activity = SimpleNamespace(type="fabricOntology", as_dict=lambda: {"type": "fabricOntology"})
        error = SimpleNamespace(type="fabricOntology", as_dict=lambda: {"type": "fabricOntology", "error": {"code": "InvalidAgentRetrievalRequest"}})
        reference = SimpleNamespace(type="fabricOntology")
        valid = SimpleNamespace(activity=[activity], references=[reference])
        failures = (
            SimpleNamespace(activity=[], references=[reference]),
            SimpleNamespace(activity=[error], references=[reference]),
            SimpleNamespace(activity=[activity], references=[]),
        )
        for filename, cell_id in (
            ("part5-except-workiq-kb.ipynb", "c638792b"),
            ("part6-work-iq-fabric-iq-to-kb.ipynb", "115e8899"),
        ):
            notebook = json.loads((ROOT / "notebooks" / filename).read_text(encoding="utf-8"))
            source = next("".join(c["source"]) for c in notebook["cells"] if c["id"] == cell_id)
            validation = source[source.index("MAX_FABRIC_ATTEMPTS ="):source.index("other_result =")]
            for failed in failures:
                for succeeds in (False, True):
                    with self.subTest(filename=filename, succeeds=succeeds, failure=failed):
                        client = Mock()
                        client.retrieve.side_effect = [failed, valid if succeeds else failed]
                        context = {
                            "knowledge_base_client": client,
                            "fabric_request": object(), "user_token": "test-user-token",
                            "fabric_user_credential": Mock(),
                            "json": json, "time": time,
                        }
                        with patch.object(time, "sleep"), patch("builtins.print"):
                            if succeeds:
                                exec(validation, context)
                                self.assertIs(context["fabric_result"], valid)
                            else:
                                with self.assertRaisesRegex(RuntimeError, "Fabric IQ"):
                                    exec(validation, context)
                        self.assertEqual(client.retrieve.call_count, 2)


if __name__ == "__main__":
    unittest.main()
