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
        self.app.initiate_device_flow.return_value = {
            "verification_uri": "https://microsoft.com/devicelogin",
            "user_code": "ABC123", "device_code": "private-device-code", "expires_at": 123,
        }
        self.app.acquire_token_by_device_flow.return_value = {"access_token": "assertion"}
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

    def test_device_flow_uses_customer_scope_and_does_not_print_secrets(self):
        with patch("builtins.print") as output:
            self.assertEqual(self.credential.get_assertion(), "assertion")
        self.app.initiate_device_flow.assert_called_once_with(
            scopes=[f"api://{APP_ID}/access_as_user"],
        )
        self.app.acquire_token_by_device_flow.assert_called_once_with(
            self.app.initiate_device_flow.return_value,
        )
        self.assertNotIn("assertion", str(output.call_args_list))
        self.assertNotIn("private-device-code", str(output.call_args_list))
        self.assertNotIn("localhost", str(output.call_args_list))
        self.assertIn("코드 ABC123", str(output.call_args_list))
        self.app.initiate_auth_code_flow.assert_not_called()

    def test_cached_token_is_refreshed_before_another_login(self):
        self.app.get_accounts.return_value = [{"home_account_id": "test"}]
        self.app.acquire_token_silent_with_error.return_value = {"access_token": "renewed"}
        self.assertEqual(self.credential.get_assertion(), "renewed")
        self.app.initiate_device_flow.assert_not_called()

    def test_silent_error_requires_reauthentication(self):
        self.app.get_accounts.return_value = [{"home_account_id": "test"}]
        self.app.acquire_token_silent_with_error.return_value = {"error": "interaction_required"}
        with patch("builtins.print"):
            self.assertEqual(self.credential.get_assertion(), "assertion")

    def test_device_flow_start_errors_stop_before_polling(self):
        self.app.initiate_device_flow.return_value = {
            "error": "invalid_client", "error_description": "App not found",
        }
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "invalid_client"):
                self.credential.get_assertion()
        self.app.acquire_token_by_device_flow.assert_not_called()

    def test_incomplete_device_flow_is_rejected(self):
        self.app.initiate_device_flow.return_value = {"user_code": "ABC123"}
        with self.assertRaisesRegex(RuntimeError, "invalid_device_flow"):
            self.credential.get_assertion()
        self.app.acquire_token_by_device_flow.assert_not_called()

    def test_device_flow_expiry_denial_and_public_client_errors_are_not_success(self):
        for error in ("expired_token", "authorization_declined", "invalid_client"):
            self.app.acquire_token_by_device_flow.return_value = {
                "error": error, "error_description": "Detailed provider error",
            }
            with self.subTest(error=error), patch("builtins.print"):
                with self.assertRaisesRegex(RuntimeError, error):
                    self.credential.get_assertion()

    def test_polling_exception_is_not_swallowed(self):
        self.app.acquire_token_by_device_flow.side_effect = RuntimeError("network failed")
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "network failed"):
                self.credential.get_assertion()

    def test_consent_error_is_not_success(self):
        self.app.acquire_token_by_device_flow.return_value = {
            "error": "access_denied", "error_description": "Admin consent required",
        }
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "access_denied"):
                self.credential.get_assertion()


class NotebookWorkIQTests(unittest.TestCase):
    def source(self, part, cell_id):
        name = {
            3: "part3-fabric-iq-to-kb.ipynb",
            4: "part4-work-iq-to-kb.ipynb",
            5: "part5-except-workiq-kb.ipynb",
            6: "part6-work-iq-fabric-iq-to-kb.ipynb",
        }[part]
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

    def test_login_cells_call_shared_cli_login_for_both_parts(self):
        for part, cell_id in ((4, "a4c11f01"), (6, "a6c11f01")):
            with self.subTest(part=part), patch.dict("sys.modules", {"work_iq_auth": auth}), \
                 patch("importlib.reload", return_value=auth) as reload, \
                 patch.object(auth, "login_azure_cli") as login:
                exec(self.source(part, cell_id), {})
                reload.assert_called_once_with(auth)
                login.assert_called_once_with("")

    def test_login_cells_refresh_stale_module_before_using_new_function(self):
        for part, cell_id in ((4, "a4c11f01"), (6, "a6c11f01")):
            stale = SimpleNamespace()
            login = Mock()

            def refresh(module):
                self.assertIs(module, stale)
                module.login_azure_cli = login
                return module

            with self.subTest(part=part), patch.dict("sys.modules", {"work_iq_auth": stale}), \
                 patch("importlib.reload", side_effect=refresh):
                exec(self.source(part, cell_id), {})
            login.assert_called_once_with("")

    def test_login_cells_explain_outdated_file_after_reload(self):
        for part, cell_id in ((4, "a4c11f01"), (6, "a6c11f01")):
            stale = SimpleNamespace()
            with self.subTest(part=part), patch.dict("sys.modules", {"work_iq_auth": stale}), \
                 patch("importlib.reload", return_value=stale):
                with self.assertRaisesRegex(RuntimeError, "git pull --ff-only"):
                    exec(self.source(part, cell_id), {})

    def test_fabric_device_login_uses_korean_prompt(self):
        credential = Mock()
        context = {"WORK_IQ_TENANT_ID": TENANT_ID, "WORK_IQ_CLIENT_ID": CLIENT_ID,
                   "WORK_IQ_APPLICATION_ID": APP_ID, "AZURE_TENANT_ID": TENANT_ID,
                   "WorkIQUserCredential": Mock(return_value=credential)}
        with patch.dict("sys.modules", {"work_iq_auth": auth}), \
             patch("azure.identity.DeviceCodeCredential") as factory, patch("builtins.print"):
            exec(self.source(6, "60e73b50"), context)
        self.assertIs(factory.call_args.kwargs["prompt_callback"], auth.device_code_prompt)
        factory.return_value.get_token.assert_called_once_with("https://search.azure.com/.default")

    def test_other_fabric_parts_use_same_korean_prompt(self):
        for part, cell_id in ((3, "b26670fa"), (5, "0359e3aa")):
            with self.subTest(part=part), patch.dict("sys.modules", {"work_iq_auth": auth}), \
                 patch("azure.identity.DeviceCodeCredential") as factory, patch("builtins.print"):
                exec(self.source(part, cell_id), {"AZURE_TENANT_ID": TENANT_ID})
            self.assertIs(factory.call_args.kwargs["prompt_callback"], auth.device_code_prompt)
            factory.return_value.get_token.assert_called_once_with("https://search.azure.com/.default")

    def test_work_iq_login_cells_use_shared_device_flow_credential(self):
        for part, cell_id in ((4, "01889729"), (6, "60e73b50")):
            context = {
                "WORK_IQ_TENANT_ID": TENANT_ID, "WORK_IQ_CLIENT_ID": CLIENT_ID,
                "WORK_IQ_APPLICATION_ID": APP_ID, "AZURE_TENANT_ID": TENANT_ID,
                "WorkIQUserCredential": Mock(return_value=Mock()),
            }
            with self.subTest(part=part), patch.dict("sys.modules", {"work_iq_auth": auth}), \
                 patch("azure.identity.DeviceCodeCredential"), patch("builtins.print"):
                exec(self.source(part, cell_id), context)
            context["WorkIQUserCredential"].assert_called_once_with(
                tenant_id=TENANT_ID, client_id=CLIENT_ID, application_id=APP_ID,
            )
            context["WorkIQUserCredential"].return_value.get_assertion.assert_called_once_with()

    def test_demo_email_login_preserves_graph_client_and_uses_korean_prompt(self):
        tree = ast.parse(self.source(4, "46755bcf"))
        assignment = next(
            node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "graph_credential"
                    for target in node.targets)
        )
        factory = Mock()
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), "<email-login>", "exec"), {
            "DeviceCodeCredential": factory, "AZURE_TENANT_ID": TENANT_ID,
            "device_code_prompt": auth.device_code_prompt,
        })
        factory.assert_called_once_with(
            tenant_id=TENANT_ID, prompt_callback=auth.device_code_prompt,
            client_id="14d82eec-204b-4c2f-b7e8-296a70dab67e",
        )

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
                def result(kind, names):
                    return SimpleNamespace(
                        activity=[SimpleNamespace(
                            type=kind, error=None,
                            as_dict=lambda i=i, name=name: {
                                "type": kind, "id": i, "knowledgeSourceName": name,
                            },
                        ) for i, name in enumerate(names)],
                        references=[SimpleNamespace(type=kind, activity_source=i) for i in range(len(names))],
                        response=[SimpleNamespace(content=[SimpleNamespace(text="answer")])],
                    )
                factory.return_value.retrieve.side_effect = (
                    [
                        result("fabricOntology", [context["FABRIC_KNOWLEDGE_SOURCE_NAME"]]),
                        result("workIQ", [context["WORK_KNOWLEDGE_SOURCE_NAME"]]),
                        result("searchIndex", [context["HR_KNOWLEDGE_SOURCE_NAME"], context["HEALTH_KNOWLEDGE_SOURCE_NAME"]]),
                        result("mcpServer", [context["WEB_KNOWLEDGE_SOURCE_NAME"]]),
                    ] if part == 6 else [result("workIQ", [context["WORK_KNOWLEDGE_SOURCE_NAME"]])]
                )
                exec(self.source(part, retrieval_id), context)
                self.assertEqual(factory.call_args.kwargs["api_version"], "2026-08-01-preview")
                calls = factory.return_value.retrieve.call_args_list
                work_call = calls[1] if part == 6 else calls[0]
                self.assertEqual(work_call.kwargs["query_work_iq_source_authorization"], "work-token")
                self.assertNotIn("query_source_authorization", work_call.kwargs)
                work_wire = work_call.kwargs["retrieval_request"].as_dict()
                self.assertIn("intents", work_wire)
                self.assertNotIn("messages", work_wire)
                for call in calls:
                    for param in call.kwargs["retrieval_request"].as_dict()["knowledgeSourceParams"]:
                        self.assertIn(param["kind"], {"searchIndex", "workIQ", "fabricOntology", "mcpServer"})
                if part == 6:
                    self.assertEqual(len(calls), 4)
                    self.assertEqual(calls[0].kwargs["query_source_authorization"], "fabric-token")
                    self.assertNotIn("query_work_iq_source_authorization", calls[0].kwargs)
                    fabric_params = calls[0].kwargs["retrieval_request"].as_dict()["knowledgeSourceParams"]
                    for param in fabric_params:
                        if param["kind"] != "fabricOntology":
                            self.assertTrue(param["neverQuerySource"])
                    params = work_wire["knowledgeSourceParams"]
                    self.assertTrue(next(p for p in params if p["knowledgeSourceName"] == "fabric-ontology-knowledge-source")["neverQuerySource"])
                    expected = [
                        {context["FABRIC_KNOWLEDGE_SOURCE_NAME"]},
                        {context["WORK_KNOWLEDGE_SOURCE_NAME"]},
                        {context["HR_KNOWLEDGE_SOURCE_NAME"], context["HEALTH_KNOWLEDGE_SOURCE_NAME"]},
                        {context["WEB_KNOWLEDGE_SOURCE_NAME"]},
                    ]
                    for call, names in zip(calls, expected):
                        wire = call.kwargs["retrieval_request"].as_dict()
                        enabled = {p["knowledgeSourceName"] for p in wire["knowledgeSourceParams"]
                                   if not p.get("neverQuerySource")}
                        self.assertEqual(enabled, names)
                        for param in wire["knowledgeSourceParams"]:
                            if param["knowledgeSourceName"] in names and param["kind"] != "mcpServer":
                                self.assertTrue(param["alwaysQuerySource"])
                        if call is not work_call:
                            self.assertNotIn("query_work_iq_source_authorization", call.kwargs)
                    self.assertNotIn("벤치마크", work_wire["intents"][0]["search"])
                    self.assertNotIn("예산", work_wire["intents"][0]["search"])
                    self.assertEqual(len(context["result"].references), 5)

    def test_part6_rejects_source_errors_missing_references_and_wrong_source(self):
        names = {
            "HR_KNOWLEDGE_SOURCE_NAME": "hr",
            "HEALTH_KNOWLEDGE_SOURCE_NAME": "health",
            "WORK_KNOWLEDGE_SOURCE_NAME": "work",
            "FABRIC_KNOWLEDGE_SOURCE_NAME": "fabric",
            "WEB_KNOWLEDGE_SOURCE_NAME": "web",
        }

        def response(kind, sources, references=True, error=None):
            return SimpleNamespace(
                activity=[SimpleNamespace(
                    type=kind, error=error,
                    as_dict=lambda i=i, name=name: {
                        "type": kind, "id": i, "knowledgeSourceName": name, "error": error,
                    },
                ) for i, name in enumerate(sources)],
                references=[SimpleNamespace(type=kind, activity_source=i)
                            for i in range(len(sources))] if references else [],
                response=[SimpleNamespace(content=[SimpleNamespace(text="answer")])],
            )

        for case in ("work-only", "missing-web-reference", "wrong-web-source", "web-error", "missing-health"):
            with self.subTest(case=case), \
                 patch("azure.search.documents.knowledgebases.KnowledgeBaseRetrievalClient") as factory, \
                 patch("IPython.display.display") as display, patch("builtins.print") as output:
                results = [
                    response("fabricOntology", ["fabric"]),
                    response("workIQ", ["work"]),
                    response("searchIndex", ["hr"] if case == "missing-health" else ["hr", "health"]),
                    response(
                        "mcpServer", ["work"] if case == "wrong-web-source" else ["web"],
                        references=case != "missing-web-reference",
                        error={"code": "Unauthorized"} if case == "web-error" else None,
                    ),
                ]
                if case == "work-only":
                    results[2] = response("workIQ", ["work"])
                factory.return_value.retrieve.side_effect = results
                context = self.context()
                context.update(names, json=json, KNOWLEDGE_BASE_NAME="test-kb",
                               work_iq_credential=Mock(), fabric_user_credential=Mock())
                with self.assertRaisesRegex(RuntimeError, "조회 검증 실패"):
                    exec(self.source(6, "115e8899"), context)
                display.assert_not_called()
                self.assertTrue(output.called)

    def test_notebooks_parse_and_have_no_saved_outputs(self):
        for path in (ROOT / "notebooks").glob("part*.ipynb"):
            nb = json.loads(path.read_text(encoding="utf-8"))
            cell_ids = [c["id"] for c in nb["cells"] if "id" in c]
            self.assertEqual(len(set(cell_ids)), len(cell_ids))
            self.assertIn('print("환경 변수를 불러왔습니다.")',
                          "".join("".join(c["source"]) for c in nb["cells"]))
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


class AzureCLILoginTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock()
        self.process.stdout = iter([
            "To sign in, use a web browser to open the page https://microsoft.com/devicelogin "
            "and enter the code ABC123 to authenticate.\n",
        ])
        self.process.wait.return_value = 0
        self.popen = patch.object(auth.subprocess, "Popen")
        self.launch = self.popen.start()
        self.launch.return_value.__enter__.return_value = self.process
        self.addCleanup(self.popen.stop)

    def test_streamed_device_prompt_and_subscription_selection(self):
        with patch.object(auth.shutil, "which", return_value="az"), \
             patch.object(auth.subprocess, "run", return_value=Mock(stdout="workshop\n")) as run, \
             patch("builtins.print") as output:
            auth.login_azure_cli(" subscription-id ")
        self.assertEqual(self.launch.call_args.args[0],
                         ["az", "login", "--use-device-code", "--output", "none"])
        self.assertEqual(self.launch.call_args.kwargs["env"]["AZURE_CORE_LOGIN_EXPERIENCE_V2"], "off")
        self.assertEqual(self.launch.call_args.kwargs["stdin"], auth.subprocess.DEVNULL)
        self.assertEqual(run.call_args_list[0].args[0],
                         ["az", "account", "set", "--subscription", "subscription-id"])
        self.assertIn("코드 ABC123", str(output.call_args_list))
        self.assertNotIn("To sign in", str(output.call_args_list))

    def test_default_subscription_is_not_changed(self):
        with patch.object(auth.shutil, "which", return_value="az"), \
             patch.object(auth.subprocess, "run", return_value=Mock(stdout="workshop\n")) as run, \
             patch("builtins.print"):
            auth.login_azure_cli()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][1:3], ["account", "show"])

    def test_failed_login_stops_before_subscription_access(self):
        self.process.wait.return_value = 1
        with patch.object(auth.shutil, "which", return_value="az"), \
             patch.object(auth.subprocess, "run") as run, patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "로그인이 실패"):
                auth.login_azure_cli()
        run.assert_not_called()

    def test_missing_cli_has_korean_guidance(self):
        with patch.object(auth.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Azure CLI가 없습니다"):
                auth.login_azure_cli()
        self.launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
