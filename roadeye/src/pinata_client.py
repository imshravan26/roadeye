import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

PINATA_API_BASE    = "https://api.pinata.cloud"
PINATA_UPLOAD_BASE = "https://uploads.pinata.cloud"
PINATA_JWT_ENV     = "PINATA_JWT"
PINATA_NETWORK     = "public"
PUBLIC_GATEWAY     = "https://gateway.pinata.cloud/ipfs"


@dataclass(frozen=True)
class PinataUploadResult:
    ipfs_cid: str
    size_bytes: int
    timestamp: str
    raw_response: dict[str, Any]


class PinataClient:
    def __init__(
        self,
        jwt_token: str | None = None,
        api_base: str = PINATA_API_BASE,
        upload_base: str = PINATA_UPLOAD_BASE,
        env_var: str = PINATA_JWT_ENV,
        network: str = PINATA_NETWORK,
    ) -> None:
        token = jwt_token or os.getenv(env_var)
        if not token:
            raise ValueError(
                f"Pinata JWT token is required. Pass jwt_token or set {env_var}."
            )
        self.api_base    = api_base.rstrip("/")
        self.upload_base = upload_base.rstrip("/")
        self.network     = network
        self._headers    = {"Authorization": f"Bearer {token}"}

    # ── Upload (v3) ────────────────────────────────────────────────────────────

    def upload_clip(
        self,
        file_path: str | Path,
        *,
        name: str | None = None,
        keyvalues: dict[str, str] | None = None,
        timeout_s: int = 120,
    ) -> PinataUploadResult:
        """Upload a clip to Pinata IPFS with optional keyvalues metadata."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")

        payload = {
            "network": self.network,
            "name":    name or path.name,
        }
        if keyvalues:
            payload["keyvalues"] = json.dumps(keyvalues)

        with path.open("rb") as fh:
            response = requests.post(
                f"{self.upload_base}/v3/files",
                headers=self._headers,
                data=payload,
                files={"file": (path.name, fh, "video/mp4")},
                timeout=timeout_s,
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Pinata upload failed ({response.status_code}): {response.text}"
            )

        data = response.json()["data"]
        return PinataUploadResult(
            ipfs_cid=data["cid"],
            size_bytes=int(data.get("size", 0)),
            timestamp=str(data.get("created_at", "")),
            raw_response=data,
        )

