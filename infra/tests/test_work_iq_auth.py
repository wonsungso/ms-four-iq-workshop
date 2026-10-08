import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from azure.search.documents.indexes.models import WorkIQKnowledgeSource
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalSemanticIntent,
)


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("work_iq_auth", ROOT / "notebooks" / "work_iq_auth.py")
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
APP_ID = "11111111-1111-1111-1111-111111111111"
TENANT_ID = "22222222-2222-2222-2222-222222222222"
CLIENT_ID = "33333333-3333-3333-3333-333333333333"
CREDENTIAL_ID = "44444444-4444-4444-4444-444444444444"


class WorkIQAuthTests(unittest.TestCase):
    def setUp(self):
        self.factory = patch.object(auth.msal, "PublicClientApplication")
        self.app = self.factory.start().return_value
        self.addCleanup(self.factory.stop)
        self.app.get_accounts.return_value = []
        self.app.initiate_auth_code_flow.return_value = {"auth_uri": "https://login.example", "state": "s"}
        self.app.acquire_token_by_auth_code_flow.return_value = {"access_token": "assertion"}
        self.credential = auth.WorkIQUserCredential(
            tenant_id=TENANT_ID, client_id=CLIENT_ID, application_id=APP_ID,
        )

    def test_required_guid_rejects_missing_and_placeholders(self):
        for value in ("", "your-client-id", "<GUID>"):
            with patch.dict(auth.os.environ, {"WORK_IQ_CLIENT_ID": value}):
                with self.assertRaisesRegex(ValueError, "WORK_IQ_CLIENT_ID"):
                    auth.required_guid("WORK_IQ_CLIENT_ID")
        with patch.dict(auth.os.environ, {"WORK_IQ_CLIENT_ID": CLIENT_ID}):
            self.assertEqual(auth.required_guid("WORK_IQ_CLIENT_ID"), CLIENT_ID)

    def test_pkce_flow_uses_customer_scope_and_does_not_print_assertion(self):
        with patch.object(auth, "getpass", return_value="http://localhost:8400/?code=c&state=s"), \
             patch("builtins.print") as output:
            self.assertEqual(self.credential.get_assertion(), "assertion")
        self.app.initiate_auth_code_flow.assert_called_once_with(
            scopes=[f"api://{APP_ID}/access_as_user"],
            redirect_uri="http://localhost:8400", prompt="select_account",
        )
        self.app.acquire_token_by_auth_code_flow.assert_called_once_with(
            self.app.initiate_auth_code_flow.return_value, {"code": "c", "state": "s"},
        )
        self.assertNotIn("assertion", str(output.call_args_list))
        self.assertNotIn("code=c", str(output.call_args_list))

    def test_cached_token_is_refreshed_before_another_login(self):
        self.app.get_accounts.return_value = [{"home_account_id": "test"}]
        self.app.acquire_token_silent_with_error.return_value = {"access_token": "renewed"}
        self.assertEqual(self.credential.get_assertion(), "renewed")
        self.app.initiate_auth_code_flow.assert_not_called()

    def test_silent_error_requires_reauthentication(self):
        self.app.get_accounts.return_value = [{"home_account_id": "test"}]
        self.app.acquire_token_silent_with_error.return_value = {"error": "interaction_required"}
        with patch.object(auth, "getpass", return_value="http://localhost:8400/?code=c&state=s"), \
             patch("builtins.print"):
            self.assertEqual(self.credential.get_assertion(), "assertion")

    def test_invalid_callback_is_rejected_before_redemption(self):
        for callback in (
            "https://evil.example/?code=c&state=s",
            "http://localhost:8400/?code=c",
            "http://localhost:8400/?state=s",
            "http://localhost:8400/?code=c&state=s&state=other",
            "http://localhost:8400/?code=c&state=s#unexpected",
        ):
            with self.subTest(callback=callback), \
                 patch.object(auth, "getpass", return_value=callback), patch("builtins.print"):
                with self.assertRaises(ValueError):
                    self.credential.get_assertion()
        self.app.acquire_token_by_auth_code_flow.assert_not_called()

    def test_state_validation_failure_is_not_swallowed(self):
        self.app.acquire_token_by_auth_code_flow.side_effect = ValueError("state mismatch")
        with patch.object(auth, "getpass", return_value="http://localhost:8400/?code=c&state=wrong"), \
             patch("builtins.print"):
            with self.assertRaisesRegex(ValueError, "state mismatch"):
                self.credential.get_assertion()

    def test_consent_error_is_not_success(self):
        self.app.acquire_token_by_auth_code_flow.return_value = {
            "error": "access_denied", "error_description": "Admin consent required",
        }
        with patch.object(auth, "getpass", return_value="http://localhost:8400/?error=access_denied&state=s"), \
             patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "access_denied"):
                self.credential.get_assertion()


class NotebookWorkIQTests(unittest.TestCase):
    def source(self, part, cell_id):
        name = "part4-work-iq-to-kb.ipynb" if part == 4 else "part6-work-iq-fabric-iq-to-kb.ipynb"
        nb = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
        return "".join(next(c["source"] for c in nb["cells"] if c["id"] == cell_id))

    def context(self):
        return {
            "AZURE_SEARCH_SERVICE_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_API_VERSION": "2026-08-01-preview",
            "search_credential": Mock(), "WORK_IQ_APPLICATION_ID": APP_ID,
            "WORK_IQ_FEDERATED_CREDENTIAL_ID": CREDENTIAL_ID, "WORK_IQ_TENANT_ID": TENANT_ID,
            "HRDOCS_INDEX": "hrdocs", "HEALTHDOCS_INDEX": "healthdocs",
            "FABRIC_WORKSPACE_ID": TENANT_ID, "FABRIC_ONTOLOGY_ID": APP_ID, "WEB_IQ_KEY": "test",
        }

    def test_source_configuration_roundtrip_for_both_parts(self):
        for part, cell_id in ((4, "9504b339"), (6, "f27502fc")):
            with self.subTest(part=part), \
                 patch("azure.search.documents.indexes.SearchIndexClient") as factory, \
                 patch("builtins.print"):
                client = factory.return_value
                client.get_knowledge_source.side_effect = lambda name: next(
                    call.kwargs["knowledge_source"] for call in client.create_or_update_knowledge_source.call_args_list
                    if call.kwargs["knowledge_source"].name == name
                )
                context = self.context()
                exec(self.source(part, cell_id), context)
                wire = context["work_knowledge_source"].as_dict()
                self.assertEqual(wire["workIQParameters"]["entraAppAuthentication"], {
                    "applicationId": APP_ID, "federatedCredentialId": CREDENTIAL_ID, "tenantId": TENANT_ID,
                })
                self.assertEqual(WorkIQKnowledgeSource(wire).as_dict(), wire)
                self.assertEqual(factory.call_args.kwargs["api_version"], "2026-08-01-preview")

    def test_retrieval_uses_dedicated_headers_and_separated_sources(self):
        for part, source_id, retrieval_id in (
            (4, "9504b339", "ac01b5b5"), (6, "f27502fc", "115e8899"),
        ):
            with self.subTest(part=part), \
                 patch("azure.search.documents.indexes.SearchIndexClient") as index_factory, \
                 patch("azure.search.documents.knowledgebases.KnowledgeBaseRetrievalClient") as factory, \
                 patch("IPython.display.display"), patch("builtins.print"):
                index = index_factory.return_value
                index.get_knowledge_source.side_effect = lambda name: next(
                    c.kwargs["knowledge_source"] for c in index.create_or_update_knowledge_source.call_args_list
                    if c.kwargs["knowledge_source"].name == name
                )
                context = self.context()
                exec(self.source(part, source_id), context)
                context.update(
                    KNOWLEDGE_BASE_NAME="test-kb", work_iq_credential=Mock(),
                    fabric_user_credential=Mock(),
                )
                context["work_iq_credential"].get_assertion.return_value = "work-token"
                context["fabric_user_credential"].get_token.return_value.token = "fabric-token"
                def result(kind):
                    return SimpleNamespace(
                        activity=[SimpleNamespace(type=kind, error=None, as_dict=lambda: {"type": kind})],
                        references=[SimpleNamespace(type=t) for t in ([kind] if kind == "fabricOntology" else ["workIQ", "mcpServer"])],
                        response=[SimpleNamespace(content=[SimpleNamespace(text="answer")])],
                    )
                factory.return_value.retrieve.side_effect = (
                    [result("fabricOntology"), result("workIQ")] if part == 6 else [result("workIQ")]
                )
                exec(self.source(part, retrieval_id), context)
                self.assertEqual(factory.call_args.kwargs["api_version"], "2026-08-01-preview")
                calls = factory.return_value.retrieve.call_args_list
                work_call = calls[-1]
                self.assertEqual(work_call.kwargs["query_work_iq_source_authorization"], "work-token")
                self.assertNotIn("query_source_authorization", work_call.kwargs)
                work_wire = work_call.kwargs["retrieval_request"].as_dict()
                self.assertIn("intents", work_wire)
                self.assertNotIn("messages", work_wire)
                for call in calls:
                    for param in call.kwargs["retrieval_request"].as_dict()["knowledgeSourceParams"]:
                        self.assertIn(param["kind"], {"searchIndex", "workIQ", "fabricOntology", "mcpServer"})
                if part == 6:
                    self.assertEqual(calls[0].kwargs["query_source_authorization"], "fabric-token")
                    self.assertNotIn("query_work_iq_source_authorization", calls[0].kwargs)
                    fabric_params = calls[0].kwargs["retrieval_request"].as_dict()["knowledgeSourceParams"]
                    for param in fabric_params:
                        if param["kind"] != "fabricOntology":
                            self.assertTrue(param["neverQuerySource"])
                    params = work_wire["knowledgeSourceParams"]
                    self.assertTrue(next(p for p in params if p["knowledgeSourceName"] == "fabric-ontology-knowledge-source")["neverQuerySource"])

    def test_notebooks_parse_and_have_no_saved_outputs(self):
        for part in (4, 6):
            name = "part4-work-iq-to-kb.ipynb" if part == 4 else "part6-work-iq-fabric-iq-to-kb.ipynb"
            nb = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
            for cell in nb["cells"]:
                if cell["cell_type"] == "code":
                    ast.parse("".join(cell["source"]))
                    self.assertEqual(cell["outputs"], [])
                    self.assertIsNone(cell["execution_count"])

    def test_latest_intent_shape(self):
        wire = KnowledgeBaseRetrievalRequest(
            intents=[KnowledgeRetrievalSemanticIntent(search="demo")],
        ).as_dict()
        self.assertEqual(wire["intents"], [{"search": "demo", "type": "semantic"}])


if __name__ == "__main__":
    unittest.main()
