from fastapi import APIRouter, Header, HTTPException, Query

from app.config import settings
from app.modules import MODULES, module_to_dict, resolve_module
from app.crypto.rsa import decrypt_payload_b64, public_key_to_pem
from app.models.message import ClientRegistration, EncryptedPayload, InboundMessage, MessageUpdateBody, ResponseBody
from app.services.message_service import message_service
from app.services.terminal_relay import terminal_relay

router = APIRouter(prefix="/api/v1")


def _encrypt_response_for_client(client_id: str | None, data: dict) -> dict:
    if not settings.wire_encrypt:
        return data
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="X-Client-Id required when SC_WIRE_ENCRYPT is enabled",
        )
    encrypted = message_service.encrypt_for_client(client_id, data)
    if encrypted is None:
        raise HTTPException(status_code=404, detail=f"Client not registered: {client_id}")
    return encrypted


@router.get("/modules")
def list_modules() -> dict:
    return {"modules": [module_to_dict(m) for m in MODULES]}


@router.get("/modules/{module_id}")
def get_module(module_id: str) -> dict:
    for module in MODULES:
        if module.id == module_id:
            return module_to_dict(module)
    raise HTTPException(status_code=404, detail=f"Module not found: {module_id}")


@router.get("/keys/public")
def get_public_key() -> dict[str, str]:
    from app.main import server_public_key

    return {"public_key": public_key_to_pem(server_public_key)}


@router.post("/messages/local")
async def post_message_local(msg: InboundMessage) -> dict:
    """Plaintext submit for the built-in web UI (same origin)."""
    try:
        data = await message_service.create_message(msg)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    mod = resolve_module(msg.name, msg.target)
    return {"ok": True, "message": data, "module": mod.id if mod else None}


@router.post("/messages")
async def post_message(
    body: EncryptedPayload,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    from app.main import server_private_key

    try:
        raw = decrypt_payload_b64(body.model_dump(exclude_none=True), server_private_key)
        msg = InboundMessage.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted message: {exc}") from exc

    try:
        data = await message_service.create_message(msg)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    mod = resolve_module(msg.name, msg.target)
    result = {"ok": True, "message": data, "module": mod.id if mod else None}
    return _encrypt_response_for_client(x_client_id or msg.name, result)


@router.get("/messages")
def list_messages(
    target: str | None = Query(None),
    name: str | None = Query(None),
    status: str | None = Query(None),
    msg_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    encrypted_for: str | None = Query(None, description="Client id to encrypt response for"),
) -> dict:
    items = message_service.list_messages(
        target=target,
        name=name,
        status=status,
        msg_type=msg_type,
        limit=limit,
    )
    if encrypted_for:
        encrypted = message_service.encrypt_for_client(encrypted_for, {"messages": items})
        if encrypted is None:
            raise HTTPException(status_code=404, detail=f"Client not registered: {encrypted_for}")
        return encrypted
    return {"messages": items}


@router.get("/messages/{message_id}")
def get_message(
    message_id: str,
    encrypted_for: str | None = Query(None),
) -> dict:
    data = message_service.get_message(message_id)
    if not data:
        raise HTTPException(status_code=404, detail="Message not found")
    if encrypted_for:
        encrypted = message_service.encrypt_for_client(encrypted_for, data)
        if encrypted is None:
            raise HTTPException(status_code=404, detail=f"Client not registered: {encrypted_for}")
        return encrypted
    return data


async def _handle_response(message_id: str, response: ResponseBody) -> dict:
    if response.ref_id != message_id:
        raise HTTPException(status_code=400, detail="ref_id does not match message_id")

    try:
        return {"ok": True, "message": await message_service.respond(response)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/messages/{message_id}/respond")
async def respond_message(
    message_id: str,
    body: EncryptedPayload,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    from app.main import server_private_key

    try:
        raw = decrypt_payload_b64(body.model_dump(exclude_none=True), server_private_key)
        response = ResponseBody.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted response: {exc}") from exc

    result = await _handle_response(message_id, response)
    return _encrypt_response_for_client(x_client_id, result)


@router.post("/messages/{message_id}/respond/local")
async def respond_message_local(message_id: str, body: ResponseBody) -> dict:
    """Plaintext respond endpoint for the built-in web UI (same origin)."""
    return await _handle_response(message_id, body)


async def _handle_update(message_id: str, body: MessageUpdateBody) -> dict:
    try:
        data = await message_service.update_message(
            message_id,
            message=body.message,
            status=body.status,
            timestamp=body.timestamp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "message": data}


@router.patch("/messages/{message_id}")
async def update_message(
    message_id: str,
    body: EncryptedPayload,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> dict:
    from app.main import server_private_key

    try:
        raw = decrypt_payload_b64(body.model_dump(exclude_none=True), server_private_key)
        update = MessageUpdateBody.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted update: {exc}") from exc
    result = await _handle_update(message_id, update)
    return _encrypt_response_for_client(x_client_id, result)


@router.patch("/messages/{message_id}/local")
async def update_message_local(message_id: str, body: MessageUpdateBody) -> dict:
    """Plaintext update for local agent / same-origin tooling."""
    return await _handle_update(message_id, body)


@router.get("/terminal/status")
def terminal_status() -> dict:
    from app.config import settings as sc_settings

    return {
        "enabled": sc_settings.terminal_enabled,
        "agent_connected": terminal_relay.agent_connected,
    }


@router.post("/clients/register")
def register_client(body: ClientRegistration) -> dict:
    return message_service.register_client(body.client_id, body.public_key)
