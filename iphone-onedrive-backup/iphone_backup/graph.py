"""Microsoft OneDrive access via the Microsoft Graph API.

Auth uses MSAL's device-code flow (a public desktop client — no client
secret). Tokens are cached to disk so you only sign in once; the refresh
token keeps future runs silent.

Docs: https://learn.microsoft.com/graph/api/driveitem-createuploadsession
"""

from __future__ import annotations

import time
from pathlib import Path

from .remote_paths import encode_graph_path


def _requests():
    """Import `requests` lazily so offline commands work before deps install."""
    try:
        import requests  # noqa: PLC0415
        return requests
    except ImportError as e:  # pragma: no cover
        raise UploadError(
            "The 'requests' package is required for OneDrive access. "
            "Install dependencies: pip install -r requirements.txt"
        ) from e

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
# Delegated scope for personal + work accounts. MSAL adds openid/profile/
# offline_access automatically, so do NOT list them here.
SCOPES = ["Files.ReadWrite"]
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024  # 4 MiB — Graph's cutoff for a single PUT


class AuthError(RuntimeError):
    pass


class UploadError(RuntimeError):
    pass


class OneDriveClient:
    def __init__(self, client_id: str, tenant: str, token_cache_path: Path,
                 chunk_size_bytes: int = 10 * 1024 * 1024):
        if not client_id:
            raise AuthError(
                "No Azure client_id configured. Run `iphone-backup init` and follow "
                "the app-registration steps in the README."
            )
        self.client_id = client_id
        self.tenant = tenant
        self.token_cache_path = Path(token_cache_path)
        self.chunk_size_bytes = chunk_size_bytes
        self._app = None
        self._cache = None
        self._session_obj = None

    @property
    def _session(self):
        if self._session_obj is None:
            self._session_obj = _requests().Session()
        return self._session_obj

    # ---- auth ---------------------------------------------------------------

    def _build_app(self):
        import msal  # imported lazily so pure-logic tests don't need it

        self._cache = msal.SerializableTokenCache()
        if self.token_cache_path.exists():
            self._cache.deserialize(self.token_cache_path.read_text())

        authority = f"https://login.microsoftonline.com/{self.tenant}"
        self._app = msal.PublicClientApplication(
            self.client_id, authority=authority, token_cache=self._cache
        )

    def _save_cache(self) -> None:
        if self._cache is not None and self._cache.has_state_changed:
            self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_path.write_text(self._cache.serialize())

    def sign_in(self, prompt=print) -> None:
        """Interactive device-code sign-in. Call once; token is then cached."""
        if self._app is None:
            self._build_app()
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise AuthError(f"Failed to start device flow: {flow.get('error_description', flow)}")
        prompt("\n" + flow["message"] + "\n")
        result = self._app.acquire_token_by_device_flow(flow)
        self._save_cache()
        if "access_token" not in result:
            raise AuthError(f"Sign-in failed: {result.get('error_description', result)}")

    def _access_token(self) -> str:
        if self._app is None:
            self._build_app()
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise AuthError(
                "Not signed in (or the cached token expired and could not refresh). "
                "Run `iphone-backup login`."
            )
        self._save_cache()
        return result["access_token"]

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._access_token()}"}
        if extra:
            h.update(extra)
        return h

    def whoami(self) -> dict:
        r = self._request("GET", f"{GRAPH_ROOT}/me")
        return r.json()

    # ---- HTTP with retry ----------------------------------------------------

    def _request(self, method: str, url: str, *, headers=None, retries=5, **kwargs):
        attempt = 0
        while True:
            attempt += 1
            resp = self._session.request(
                method, url, headers=self._headers(headers), timeout=120, **kwargs
            )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= retries:
                delay = _retry_after(resp, attempt)
                time.sleep(delay)
                continue
            return resp

    def _put_chunk(self, upload_url: str, data: bytes, headers: dict, retries=5):
        # Upload-session PUTs use the pre-authorized upload URL (no bearer header).
        attempt = 0
        while True:
            attempt += 1
            resp = self._session.put(upload_url, headers=headers, data=data, timeout=300)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= retries:
                time.sleep(_retry_after(resp, attempt))
                continue
            return resp

    # ---- upload -------------------------------------------------------------

    def upload_file(self, local_path: Path, remote_path: str) -> dict:
        """Upload one file to OneDrive at remote_path (relative to the drive root).

        Existing files at the same path are replaced. Returns the DriveItem JSON.
        """
        local_path = Path(local_path)
        size = local_path.stat().st_size
        if size < SIMPLE_UPLOAD_LIMIT:
            return self._simple_upload(local_path, remote_path)
        return self._session_upload(local_path, remote_path, size)

    def _simple_upload(self, local_path: Path, remote_path: str) -> dict:
        enc = encode_graph_path(remote_path)
        url = (
            f"{GRAPH_ROOT}/me/drive/root:/{enc}:/content"
            "?@microsoft.graph.conflictBehavior=replace"
        )
        with open(local_path, "rb") as f:
            data = f.read()
        resp = self._request(
            "PUT", url, headers={"Content-Type": "application/octet-stream"}, data=data
        )
        if resp.status_code not in (200, 201):
            raise UploadError(f"Upload failed ({resp.status_code}): {resp.text[:500]}")
        return resp.json()

    def _session_upload(self, local_path: Path, remote_path: str, size: int) -> dict:
        enc = encode_graph_path(remote_path)
        create_url = f"{GRAPH_ROOT}/me/drive/root:/{enc}:/createUploadSession"
        body = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
        resp = self._request("POST", create_url, json=body)
        if resp.status_code not in (200, 201):
            raise UploadError(
                f"Could not create upload session ({resp.status_code}): {resp.text[:500]}"
            )
        upload_url = resp.json()["uploadUrl"]

        chunk = self.chunk_size_bytes
        with open(local_path, "rb") as f:
            start = 0
            while start < size:
                block = f.read(chunk)
                end = start + len(block) - 1
                headers = {
                    "Content-Length": str(len(block)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                }
                resp = self._put_chunk(upload_url, block, headers)
                if resp.status_code in (200, 201):
                    return resp.json()  # final chunk returns the DriveItem
                if resp.status_code != 202:
                    self._cancel_session(upload_url)
                    raise UploadError(
                        f"Chunk upload failed ({resp.status_code}) at byte {start}: "
                        f"{resp.text[:500]}"
                    )
                start = end + 1
        raise UploadError("Upload session ended without a completion response.")

    def _cancel_session(self, upload_url: str) -> None:
        try:
            self._session.delete(upload_url, timeout=30)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


def _retry_after(resp, attempt: int) -> float:
    hdr = resp.headers.get("Retry-After")
    if hdr:
        try:
            return float(hdr)
        except ValueError:
            pass
    return min(2 ** attempt, 60)  # exponential backoff, capped at 60s
