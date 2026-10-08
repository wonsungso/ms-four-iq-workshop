import copy
import importlib.util
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

from dotenv import dotenv_values
import requests


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("configure_work_iq", ROOT / "infra" / "configure-work-iq.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
TENANT = "11111111-1111-1111-1111-111111111111"
API = "22222222-2222-2222-2222-222222222222"
CLIENT = "33333333-3333-3333-3333-333333333333"
FIC = "44444444-4444-4444-4444-444444444444"
SCOPE = "55555555-5555-5555-5555-555555555555"


class ConfigureWorkIQTests(unittest.TestCase):
    def setUp(self):
        self.api = {
            "id": API, "appId": API, "identifierUris": [f"api://{API}"],
            "api": {"oauth2PermissionScopes": [{"id": SCOPE, "value": "access_as_user", "isEnabled": True}]},
        }
        self.client = {
            "appId": CLIENT, "publicClient": {"redirectUris": ["http://localhost"]},
            "requiredResourceAccess": [{"resourceAppId": API, "resourceAccess": [{"id": SCOPE, "type": "Scope"}]}],
        }
        self.fic = {
            "id": FIC, "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "subject": "search-principal", "audiences": ["api://AzureADTokenExchange"],
        }
        self.graph = Mock()
        self.graph.app.side_effect = lambda name: self.api if name == "api" else self.client
        self.graph.collection.return_value = [self.fic]
        self.identity = {"tenantId": TENANT, "principalId": "search-principal"}
        self.cli = patch.object(setup, "az_json", side_effect=lambda *args: (
            [{"name": "test-search", "id": "search-resource"}]
            if args[1] == "list" else {"identity": self.identity}
        ))
        self.cli.start()
        self.addCleanup(self.cli.stop)

    def discover(self):
        return setup.discover(self.graph, TENANT, "https://test-search.search.windows.net", "api", "client")

    def test_exact_existing_connection_is_discovered(self):
        self.assertEqual(self.discover(), {
            "WORK_IQ_TENANT_ID": TENANT, "WORK_IQ_APPLICATION_ID": API,
            "WORK_IQ_CLIENT_ID": CLIENT, "WORK_IQ_FEDERATED_CREDENTIAL_ID": FIC,
        })

    def test_missing_or_ambiguous_federated_credential_fails(self):
        for credentials in ([], [self.fic, copy.deepcopy(self.fic)]):
            self.graph.collection.return_value = credentials
            with self.assertRaisesRegex(ValueError, "federated credential"):
                self.discover()

    def test_wrong_principal_or_audience_fails(self):
        for key, value in (("subject", "another-principal"), ("audiences", ["wrong"])):
            wrong = dict(self.fic, **{key: value})
            self.graph.collection.return_value = [wrong]
            with self.assertRaises(ValueError):
                self.discover()

    def test_client_permission_and_redirect_are_required(self):
        for key in ("publicClient", "requiredResourceAccess"):
            original = self.client.pop(key)
            with self.assertRaises(ValueError):
                self.discover()
            self.client[key] = original

    def test_system_assigned_identity_is_required(self):
        self.identity = {"tenantId": TENANT, "userAssignedIdentities": {
            "first": {"principalId": "search-principal"}, "second": {"principalId": "other"},
        }}
        with self.assertRaisesRegex(ValueError, "identity"):
            self.discover()

    def test_missing_cli_login_has_actionable_guidance(self):
        self.cli.stop()
        result = Mock(returncode=1, stderr="ERROR: Please run 'az login' to setup account.")
        with patch.object(setup.shutil, "which", return_value="az"), \
             patch.object(setup.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "az login --use-device-code"):
                setup.az_json("account", "show")

    def test_other_cli_errors_are_preserved(self):
        self.cli.stop()
        result = Mock(returncode=1, stderr="ERROR: AuthorizationFailed")
        with patch.object(setup.shutil, "which", return_value="az"), \
             patch.object(setup.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Azure CLI 실행 실패: ERROR: AuthorizationFailed"):
                setup.az_json("resource", "list")

    def test_missing_cli_login_does_not_write_env(self):
        self.cli.stop()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".env"
            path.write_text("AZURE_SEARCH_SERVICE_ENDPOINT=https://test-search.search.windows.net\n")
            original = path.read_bytes()
            result = Mock(returncode=1, stderr="ERROR: Please run 'az login' to setup account.")
            with patch.object(setup, "ROOT", root), \
                 patch.object(setup.shutil, "which", return_value="az"), \
                 patch.object(setup.subprocess, "run", return_value=result), \
                 patch.object(setup, "Graph") as graph, \
                 patch("sys.argv", ["configure-work-iq.py"]):
                with self.assertRaisesRegex(RuntimeError, "az login --use-device-code"):
                    setup.main()
                graph.assert_not_called()
            self.assertEqual(path.read_bytes(), original)

    def test_atomic_env_update_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = "# User configuration\nWEB_IQ_KEY='test-value'\nWORK_IQ_CLIENT_ID=old\n"
            path.write_text(original, encoding="utf-8")
            settings = self.discover()
            setup.save_settings(path, settings)
            self.assertEqual(dotenv_values(path)["WEB_IQ_KEY"], "test-value")
            for key, value in settings.items():
                self.assertEqual(dotenv_values(path)[key], value)
            self.assertIn("\n\n# Work IQ Configuration\n", path.read_text(encoding="utf-8"))
            setup.save_settings(path, settings)
            self.assertEqual(path.read_text(encoding="utf-8").count("# Work IQ Configuration"), 1)
            for key in settings:
                self.assertEqual(path.read_text(encoding="utf-8").count(f"{key}="), 1)
            saved = path.read_bytes()
            with patch.object(setup, "set_key", side_effect=OSError("write failed")):
                with self.assertRaises(OSError):
                    setup.save_settings(path, settings)
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_verify_only_and_failed_discovery_do_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".env"
            path.write_text("AZURE_SEARCH_SERVICE_ENDPOINT=https://test-search.search.windows.net\n")
            original = path.read_bytes()
            with patch.object(setup, "ROOT", root), patch.object(setup, "Graph", return_value=self.graph), \
                 patch("sys.argv", ["configure-work-iq.py", "--tenant-id", TENANT, "--verify-only",
                                    "--api-app-name", "api", "--client-app-name", "client"]), patch("builtins.print"):
                setup.main()
                self.graph.collection.return_value = []
                with patch("sys.argv", ["configure-work-iq.py", "--tenant-id", TENANT,
                                       "--api-app-name", "api", "--client-app-name", "client"]):
                    with self.assertRaises(ValueError):
                        setup.main()
            self.assertEqual(path.read_bytes(), original)

    def test_duplicate_app_names_fail(self):
        with patch.object(setup.Graph, "__init__", return_value=None):
            graph = setup.Graph(TENANT)
            with patch.object(graph, "collection", return_value=[self.api, self.api]):
                with self.assertRaisesRegex(ValueError, "2개를 찾았습니다"):
                    graph.app("api")

    def test_graph_authorization_error_is_not_app_missing(self):
        with patch.object(setup.Graph, "__init__", return_value=None):
            graph = setup.Graph(TENANT)
            graph.session = Mock()
            graph.session.get.return_value.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
            with self.assertRaisesRegex(requests.HTTPError, "403 Forbidden"):
                graph.app("api")

    def test_graph_pagination_is_read_only_and_checks_destination(self):
        with patch.object(setup.Graph, "__init__", return_value=None):
            graph = setup.Graph(TENANT)
            graph.session = Mock()
            response = Mock()
            response.json.return_value = {"value": [self.api], "@odata.nextLink": "https://example.com/next"}
            graph.session.get.return_value = response
            with self.assertRaisesRegex(ValueError, "다음 페이지 주소"):
                graph.collection("applications")
            self.assertEqual([c[0] for c in graph.session.method_calls], ["get"])

    def test_postprovision_preserves_work_iq_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".env"
            settings = self.discover()
            path.write_text("\n".join(f"{k}={v}" for k, v in settings.items()) + "\n")
            source = (ROOT / "infra" / "setup-env.py").read_text(encoding="utf-8")
            env = {k: "test" for k in (
                "AZURE_SEARCH_SERVICE_ENDPOINT", "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_CHATGPT_DEPLOYMENT", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "AZURE_TENANT_ID",
            )}
            script = root / "infra" / "setup-env.py"
            script.parent.mkdir()
            script.write_text(source, encoding="utf-8")
            with patch.dict("os.environ", env), patch("builtins.print"):
                runpy.run_path(str(script))
            saved = dotenv_values(path)
            for key, value in settings.items():
                self.assertEqual(saved[key], value)
            self.assertIn("\n\n# Work IQ Configuration\n", path.read_text(encoding="utf-8"))
            with patch.dict("os.environ", env), patch("builtins.print"):
                runpy.run_path(str(script))
            self.assertEqual(path.read_text(encoding="utf-8").count("# Work IQ Configuration"), 1)


if __name__ == "__main__":
    unittest.main()
