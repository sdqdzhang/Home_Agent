from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from shared.server_center.crypto import (
    decrypt_payload_b64,
    encrypt_payload_b64,
    is_encrypted_payload,
    load_public_key_from_pem,
    public_key_to_pem,
)


def _ascii_wire_id(preferred: str | None, module_name: str) -> str:
    """HTTP header values must be ASCII; never put Chinese module names in headers."""
    if preferred and preferred.isascii() and preferred.strip():
        return preferred.strip()
    digest = hashlib.sha1(module_name.encode("utf-8")).hexdigest()[:12]
    return f"mod_{digest}"


class ServerCenterClient:
    """与 Server Center 通信：统一混合加密，所有模块复用。"""

    def __init__(
        self,
        base_url: str,
        module_name: str,
        private_key: RSAPrivateKey,
        public_key: RSAPublicKey,
        *,
        id_prefix: str | None = None,
        wire_encrypt: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.module_name = module_name
        self.id_prefix = _ascii_wire_id(id_prefix, module_name)
        self.private_key = private_key
        self.public_key = public_key
        self.wire_encrypt = wire_encrypt
        self._server_public_key: RSAPublicKey | None = None

    @property
    def client_id(self) -> str:
        """业务侧模块名（可含中文），用于消息 name / 注册别名。"""
        return self.module_name

    @property
    def wire_client_id(self) -> str:
        """线缆加密用 ASCII id（HTTP Header / 响应加密查找）。"""
        return self.id_prefix

    def _client_headers(self) -> dict[str, str]:
        return {"X-Client-Id": self.wire_client_id}

    async def ping(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def ensure_registered(self, *extra_client_ids: str) -> None:
        await self._fetch_server_public_key()
        # 中文 module_name 仅进 JSON body 注册；Header 只用 ASCII wire_client_id
        ids: list[str] = []
        for cid in (self.wire_client_id, self.client_id, *extra_client_ids):
            if cid and cid not in ids:
                ids.append(cid)
        async with httpx.AsyncClient(timeout=30.0) as client:
            for cid in ids:
                resp = await client.post(
                    f"{self.base_url}/api/v1/clients/register",
                    json={
                        "client_id": cid,
                        "public_key": public_key_to_pem(self.public_key),
                    },
                )
                resp.raise_for_status()

    async def _fetch_server_public_key(self) -> RSAPublicKey:
        if self._server_public_key is not None:
            return self._server_public_key
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/v1/keys/public")
            resp.raise_for_status()
            self._server_public_key = load_public_key_from_pem(resp.json()["public_key"])
            return self._server_public_key

    def _decode_response_body(self, body: dict[str, Any]) -> dict[str, Any]:
        if is_encrypted_payload(body):
            plain = decrypt_payload_b64(body, self.private_key)
            return json.loads(plain.decode("utf-8"))
        if self.wire_encrypt:
            raise ValueError("Server returned plaintext while LA_WIRE_ENCRYPT is enabled")
        return body

    def _build_inbound_payload(
        self,
        *,
        msg_type: str,
        message: dict[str, Any],
        target: str,
        msg_id: str | None,
    ) -> dict[str, Any]:
        return {
            "id": msg_id or f"{self.id_prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "name": self.module_name,
            "target": target,
            "msg_type": msg_type,
            "message": message,
            "timestamp": int(time.time()),
        }

    async def _post_encrypted(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float = 120.0,
        method: str = "POST",
    ) -> dict[str, Any]:
        server_key = await self._fetch_server_public_key()
        plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted_body = encrypt_payload_b64(plaintext, server_key)
        chunk_count = 1
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{self.base_url}{path}"
            headers = self._client_headers()
            if method.upper() == "PATCH":
                resp = await client.patch(url, json=encrypted_body, headers=headers)
            else:
                resp = await client.post(url, json=encrypted_body, headers=headers)
            resp.raise_for_status()
            result = self._decode_response_body(resp.json())
            result["_encrypted_chunks"] = chunk_count
            result["_plaintext_bytes"] = len(plaintext)
            return result

    async def send_message(
        self,
        *,
        msg_type: str,
        message: dict[str, Any],
        target: str = "user_ui",
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._build_inbound_payload(
            msg_type=msg_type,
            message=message,
            target=target,
            msg_id=msg_id,
        )
        result = await self._post_encrypted("/api/v1/messages", payload)
        result["_outbound_id"] = payload["id"]
        return result

    @staticmethod
    def message_id_from_response(response: dict[str, Any], fallback: str = "") -> str:
        """Server Center 返回 { ok, message: { id, ... } }，取出消息 id。"""
        message = response.get("message")
        if isinstance(message, dict) and message.get("id"):
            return str(message["id"])
        outbound = response.get("_outbound_id")
        if outbound:
            return str(outbound)
        if response.get("id"):
            return str(response["id"])
        return fallback

    async def fetch_messages(
        self,
        *,
        target: str | None = None,
        name: str | None = None,
        status: str | None = None,
        msg_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """拉取消息列表（可按 target/name 过滤）。默认用本客户端公钥加密返回。"""
        params: dict[str, Any] = {
            "encrypted_for": self.wire_client_id,
            "limit": limit,
        }
        if target:
            params["target"] = target
        if name:
            params["name"] = name
        if status:
            params["status"] = status
        if msg_type:
            params["msg_type"] = msg_type

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/messages",
                params=params,
                headers=self._client_headers(),
            )
            resp.raise_for_status()
            body = resp.json()
            if is_encrypted_payload(body):
                plain = decrypt_payload_b64(body, self.private_key)
                return json.loads(plain.decode("utf-8")).get("messages", [])
            if self.wire_encrypt:
                raise ValueError("Server returned plaintext message list while wire encrypt is on")
            return body.get("messages", [])

    async def fetch_encrypted_messages(
        self,
        *,
        status: str | None = None,
        msg_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """兼容旧接口：按本模块 name 过滤（多为出站消息）。"""
        return await self.fetch_messages(
            name=self.module_name,
            status=status,
            msg_type=msg_type,
            limit=limit,
        )

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        params = {"encrypted_for": self.wire_client_id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/messages/{message_id}",
                params=params,
                headers=self._client_headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            body = resp.json()
            if is_encrypted_payload(body):
                plain = decrypt_payload_b64(body, self.private_key)
                data = json.loads(plain.decode("utf-8"))
                return data if isinstance(data, dict) else None
            if self.wire_encrypt:
                raise ValueError("Server returned plaintext message while wire encrypt is on")
            return body if isinstance(body, dict) else None

    async def respond(
        self,
        ref_id: str,
        *,
        msg_type: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "ref_id": ref_id,
            "msg_type": msg_type,
            "message": message,
            "timestamp": int(time.time()),
        }
        return await self._post_encrypted(f"/api/v1/messages/{ref_id}/respond", payload)

    async def update_message(
        self,
        message_id: str,
        *,
        message: dict[str, Any] | None = None,
        status: str | None = None,
        timestamp: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if message is not None:
            payload["message"] = message
        if status is not None:
            payload["status"] = status
        if timestamp is not None:
            payload["timestamp"] = int(timestamp)
        return await self._post_encrypted(f"/api/v1/messages/{message_id}", payload, method="PATCH")
