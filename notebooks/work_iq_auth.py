"""Customer-app user assertions for Work IQ's delegated OBO flow."""

from getpass import getpass
import os
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import msal


def required_guid(name: str) -> str:
    value = os.environ.get(name, "").strip()
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an app, tenant or credential GUID. "
            "Complete deploy_yourself.md section 3, then run "
            "python infra/configure-work-iq.py from the repository root."
        ) from exc


class WorkIQUserCredential:
    """Acquire and refresh an app-audience token without storing secrets on disk."""

    def __init__(self, *, tenant_id: str, client_id: str, application_id: str):
        self.scope = f"api://{application_id}/access_as_user"
        self.app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

    def get_assertion(self) -> str:
        accounts = self.app.get_accounts()
        result = (
            self.app.acquire_token_silent_with_error([self.scope], account=accounts[0])
            if accounts else None
        )
        if not result or "access_token" not in result:
            # The manual loopback callback also works when the notebook runs in Codespaces.
            flow = self.app.initiate_auth_code_flow(
                scopes=[self.scope],
                redirect_uri="http://localhost:8400",
                prompt="select_account",
            )
            if "auth_uri" not in flow:
                raise RuntimeError("MSAL could not start the Work IQ authorization code flow.")
            print("Work IQ: open this URL and sign in with your Microsoft 365 account:")
            print(flow["auth_uri"])
            print(
                "After sign-in, copy the full http://localhost:8400 callback URL from "
                "the browser address bar, even if the browser shows a connection error. "
                "Paste it below. Do not share or save the URL."
            )
            callback = getpass("Work IQ callback URL (hidden): ").strip()
            parsed = urlparse(callback)
            if (
                parsed.scheme != "http"
                or parsed.hostname != "localhost"
                or parsed.port != 8400
                or parsed.path not in ("", "/")
                or parsed.fragment
            ):
                raise ValueError("Expected the full http://localhost:8400 callback URL.")
            params = parse_qs(parsed.query)
            if any(len(values) != 1 for values in params.values()):
                raise ValueError("The callback URL contains duplicate authorization parameters.")
            response = {key: values[0] for key, values in params.items()}
            if not response.get("state") or not (response.get("code") or response.get("error")):
                raise ValueError("The callback URL is missing OAuth state or authorization code.")
            # MSAL verifies state and redeems the code with its generated PKCE verifier.
            result = self.app.acquire_token_by_auth_code_flow(flow, response)
        if not result or "access_token" not in result:
            error = (result or {}).get("error", "no_token")
            description = (result or {}).get("error_description", "No user assertion returned.")
            raise RuntimeError(f"Work IQ sign-in failed: {error}: {description}")
        return result["access_token"]
