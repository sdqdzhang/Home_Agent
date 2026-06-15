from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from app.server_client.crypto import decrypt_from_b64, encrypt_to_b64, public_key_to_pem


class ServerCenterClient:
    """与 Server Center 的 RSA 加密 HTTP 通信。"""

    def __init__(
        self,
        base_url: str,
        module_name: str,
        private_key: RSAPrivateKey,
        public_key: RSAPublicKey,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.module_name = module_name
        self.private_key = private_key
        self.public_key = public_key
        self._server_public_key: RSAPublicKey | None = None

    @property
    def client_id(self) -> str:
        return self.module_name

    async def ensure_registered(self) -> None:
        await self._fetch_server_public_key()
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{self.base_url}/api/v1/clients/register",
                json={
                    "client_id": self.client_id,
                    "public_key": public_key_to_pem(self.public_key),
                },
            )

    async def _fetch_server_public_key(self) -> RSAPublicKey:
        if self._server_public_key is not None:
            return self._server_public_key
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/v1/keys/public")
            resp.raise_for_status()
            from app.server_client.crypto import load_public_key_from_pem

            self._server_public_key = load_public_key_from_pem(resp.json()["public_key"])
            return self._server_public_key

    async def send_message(
        self,
        *,
        msg_type: str,
        message: dict[str, Any],
        target: str = "user_ui",
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        server_key = await self._fetch_server_public_key()
        payload = {
            "id": msg_id or f"crawler_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "name": self.module_name,
            "target": target,
            "msg_type": msg_type,
            "message": message,
            "timestamp": int(time.time()),
        }
        plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted = encrypt_to_b64(plaintext, server_key)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/messages",
                json={"encrypted": encrypted},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_encrypted_messages(
        self,
        *,
        status: str | None = None,
        msg_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "name": self.module_name,
            "encrypted_for": self.client_id,
            "limit": limit,
        }
        if status:
            params["status"] = status
        if msg_type:
            params["msg_type"] = msg_type

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/v1/messages", params=params)
            resp.raise_for_status()
            body = resp.json()
            encrypted = body.get("encrypted")
            if not encrypted:
                return body.get("messages", [])
            plain = decrypt_from_b64(encrypted, self.private_key)
            return json.loads(plain.decode("utf-8")).get("messages", [])

    async def respond(
        self,
        ref_id: str,
        *,
        msg_type: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        server_key = await self._fetch_server_public_key()
        payload = {
            "ref_id": ref_id,
            "msg_type": msg_type,
            "message": message,
            "timestamp": int(time.time()),
        }
        plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted = encrypt_to_b64(plaintext, server_key)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/messages/{ref_id}/respond",
                json={"encrypted": encrypted},
            )
            resp.raise_for_status()
            return resp.json()
