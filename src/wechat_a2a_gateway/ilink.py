from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
import struct
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

import httpx

from .gateway import GatewayReply, WeChatA2AGateway
from .wechat import WeChatMessage

logger = logging.getLogger(__name__)

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

ITEM_TEXT = 1
ITEM_VOICE = 3
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

LONG_POLL_TIMEOUT_SECONDS = 35.0
API_TIMEOUT_SECONDS = 15.0
QR_TIMEOUT_SECONDS = 35.0
SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2


@dataclass(frozen=True, slots=True)
class ILinkCredentials:
    account_id: str
    token: str
    base_url: str = ILINK_BASE_URL
    user_id: str = ""


@dataclass(frozen=True, slots=True)
class ILinkInboundMessage:
    account_id: str
    chat_id: str
    sender_id: str
    text: str
    message_id: str | None
    context_token: str | None
    raw: dict[str, Any]


class ILinkStateStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def save_credentials(self, credentials: ILinkCredentials) -> None:
        self._write_json(
            self._account_path(credentials.account_id),
            {
                "account_id": credentials.account_id,
                "token": credentials.token,
                "base_url": credentials.base_url,
                "user_id": credentials.user_id,
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def load_credentials(self, account_id: str) -> ILinkCredentials | None:
        path = self._account_path(account_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        token = _optional_str(data.get("token"))
        if not token:
            return None
        return ILinkCredentials(
            account_id=account_id,
            token=token,
            base_url=_optional_str(data.get("base_url")) or ILINK_BASE_URL,
            user_id=_optional_str(data.get("user_id")) or "",
        )

    def single_saved_account_id(self) -> str | None:
        account_files = [
            path
            for path in self._root.glob("*.json")
            if not path.name.endswith((".sync.json", ".context-tokens.json"))
        ]
        if len(account_files) != 1:
            return None
        return account_files[0].stem

    def load_sync_buf(self, account_id: str) -> str:
        path = self._sync_path(account_id)
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        return _optional_str(data.get("get_updates_buf")) or ""

    def save_sync_buf(self, account_id: str, sync_buf: str) -> None:
        self._write_json(self._sync_path(account_id), {"get_updates_buf": sync_buf})

    def get_context_token(self, account_id: str, chat_id: str) -> str | None:
        return self._load_context_tokens(account_id).get(chat_id)

    def set_context_token(self, account_id: str, chat_id: str, context_token: str) -> None:
        tokens = self._load_context_tokens(account_id)
        tokens[chat_id] = context_token
        self._write_json(self._context_tokens_path(account_id), tokens)

    def clear_context_token(self, account_id: str, chat_id: str) -> None:
        tokens = self._load_context_tokens(account_id)
        tokens.pop(chat_id, None)
        self._write_json(self._context_tokens_path(account_id), tokens)

    def _load_context_tokens(self, account_id: str) -> dict[str, str]:
        path = self._context_tokens_path(account_id)
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(key): value for key, value in data.items() if isinstance(value, str)}

    def _account_path(self, account_id: str) -> Path:
        return self._root / f"{account_id}.json"

    def _sync_path(self, account_id: str) -> Path:
        return self._root / f"{account_id}.sync.json"

    def _context_tokens_path(self, account_id: str) -> Path:
        return self._root / f"{account_id}.context-tokens.json"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass


class ILinkClient:
    def __init__(
        self,
        *,
        base_url: str = ILINK_BASE_URL,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = client

    async def get_bot_qrcode(self, *, bot_type: str = "3") -> dict[str, Any]:
        return await self._get(
            endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_seconds=QR_TIMEOUT_SECONDS,
        )

    async def get_qrcode_status(self, *, qrcode: str) -> dict[str, Any]:
        return await self._get(
            endpoint=f"{EP_GET_QR_STATUS}?qrcode={qrcode}",
            timeout_seconds=QR_TIMEOUT_SECONDS,
        )

    async def get_updates(self, *, sync_buf: str) -> dict[str, Any]:
        try:
            return await self._post(
                endpoint=EP_GET_UPDATES,
                payload={"get_updates_buf": sync_buf},
                timeout_seconds=LONG_POLL_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}

    async def send_text(
        self,
        *,
        to_user_id: str,
        text: str,
        context_token: str | None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("iLink text message must not be empty")
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id or f"wechat-to-a2a-{uuid.uuid4().hex}",
            "message_type": MSG_TYPE_BOT,
            "message_state": MSG_STATE_FINISH,
            "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
        }
        if context_token:
            message["context_token"] = context_token
        return await self._post(
            endpoint=EP_SEND_MESSAGE,
            payload={"msg": message},
            timeout_seconds=API_TIMEOUT_SECONDS,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            return

    async def _get(self, *, endpoint: str, timeout_seconds: float) -> dict[str, Any]:
        async def request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(
                f"{self._base_url}/{endpoint}",
                headers=_ilink_get_headers(),
                timeout=timeout_seconds,
            )

        return await self._request(request)

    async def _post(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        body = _json_dumps({**payload, "base_info": {"channel_version": CHANNEL_VERSION}})

        async def request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                f"{self._base_url}/{endpoint}",
                content=body,
                headers=_ilink_post_headers(self._token, body),
                timeout=timeout_seconds,
            )

        return await self._request(request)

    async def _request(
        self,
        request: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]],
    ) -> dict[str, Any]:
        if self._client is not None:
            response = await request(self._client)
        else:
            async with httpx.AsyncClient(trust_env=True) as client:
                response = await request(client)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"unexpected iLink response: {data!r}")
        return data


class ILinkGatewayRunner:
    def __init__(
        self,
        *,
        account_id: str,
        ilink_client: ILinkClient,
        gateway: WeChatA2AGateway,
        state_store: ILinkStateStore,
        poll_interval_seconds: float = 1.0,
        send_chunk_delay_seconds: float = 1.5,
    ) -> None:
        self._account_id = account_id
        self._ilink_client = ilink_client
        self._gateway = gateway
        self._state_store = state_store
        self._poll_interval_seconds = poll_interval_seconds
        self._send_chunk_delay_seconds = send_chunk_delay_seconds
        self._seen_message_ids: set[str] = set()

    async def run_forever(self) -> None:  # pragma: no cover
        sync_buf = self._state_store.load_sync_buf(self._account_id)
        while True:
            response = await self._ilink_client.get_updates(sync_buf=sync_buf)
            ret = response.get("ret", 0)
            errcode = response.get("errcode", 0)
            if ret not in (0, None) or errcode not in (0, None):
                logger.warning("iLink getupdates failed ret=%s errcode=%s", ret, errcode)
                await asyncio.sleep(self._poll_interval_seconds)
                continue

            new_sync_buf = _optional_str(response.get("get_updates_buf"))
            if new_sync_buf:
                sync_buf = new_sync_buf
                self._state_store.save_sync_buf(self._account_id, sync_buf)

            for raw_message in response.get("msgs") or []:
                if isinstance(raw_message, dict):
                    await self.handle_raw_message(raw_message)
            await asyncio.sleep(self._poll_interval_seconds)

    async def handle_raw_message(self, raw_message: dict[str, Any]) -> GatewayReply | None:
        inbound = parse_ilink_message(raw_message, account_id=self._account_id)
        if inbound is None:
            return None
        if inbound.message_id and inbound.message_id in self._seen_message_ids:
            return None
        if inbound.message_id:
            self._seen_message_ids.add(inbound.message_id)
        if inbound.context_token:
            self._state_store.set_context_token(
                self._account_id,
                inbound.chat_id,
                inbound.context_token,
            )

        reply = await self._gateway.handle_message(
            WeChatMessage(
                to_user=self._account_id,
                from_user=inbound.chat_id,
                create_time=int(time.time()),
                msg_type="text",
                content=inbound.text,
                msg_id=inbound.message_id,
                gateway="ilink",
            )
        )
        await self._send_reply(inbound.chat_id, reply)
        return reply

    async def _send_reply(self, chat_id: str, reply: GatewayReply) -> None:
        chunks = reply.chunks or [reply.text]
        context_token = self._state_store.get_context_token(self._account_id, chat_id)
        for index, chunk in enumerate(chunks):
            response = await self._ilink_client.send_text(
                to_user_id=chat_id,
                text=chunk,
                context_token=context_token,
            )
            ret = response.get("ret", 0)
            errcode = response.get("errcode", 0)
            if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
                self._state_store.clear_context_token(self._account_id, chat_id)
                await self._ilink_client.send_text(
                    to_user_id=chat_id,
                    text=chunk,
                    context_token=None,
                )
            elif ret == RATE_LIMIT_ERRCODE or errcode == RATE_LIMIT_ERRCODE:
                raise RuntimeError(f"iLink sendmessage rate limited: {response!r}")
            elif ret not in (0, None) or errcode not in (0, None):
                raise RuntimeError(f"iLink sendmessage failed: {response!r}")
            if index < len(chunks) - 1 and self._send_chunk_delay_seconds > 0:
                await asyncio.sleep(self._send_chunk_delay_seconds)


async def run_qr_login(
    *,
    state_store: ILinkStateStore,
    bot_type: str = "3",
    timeout_seconds: int = 480,
) -> ILinkCredentials | None:  # pragma: no cover
    client = ILinkClient()
    qr_response = await client.get_bot_qrcode(bot_type=bot_type)
    qrcode = _optional_str(qr_response.get("qrcode"))
    qrcode_url = _optional_str(qr_response.get("qrcode_img_content")) or qrcode
    if not qrcode:
        raise RuntimeError(f"iLink QR response missing qrcode: {qr_response!r}")

    print("\n请使用微信扫描以下二维码：")
    print(qrcode_url)
    try:
        qrcode_lib = import_module("qrcode")

        qr = qrcode_lib.QRCode()
        qr.add_data(qrcode_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as exc:
        print(f"终端二维码渲染失败：{exc}")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status_response = await client.get_qrcode_status(qrcode=qrcode)
        status = _optional_str(status_response.get("status")) or "wait"
        if status == "wait":
            print(".", end="", flush=True)
        elif status == "scaned":
            print("\n已扫码，请在微信里确认...")
        elif status == "confirmed":
            credentials = ILinkCredentials(
                account_id=_required_str(status_response, "ilink_bot_id"),
                token=_required_str(status_response, "bot_token"),
                base_url=_optional_str(status_response.get("baseurl")) or ILINK_BASE_URL,
                user_id=_optional_str(status_response.get("ilink_user_id")) or "",
            )
            state_store.save_credentials(credentials)
            print(f"\niLink 登录成功，account_id={credentials.account_id}")
            return credentials
        elif status == "expired":
            print("\n二维码已过期，请重新运行登录命令。")
            return None
        await asyncio.sleep(1)
    print("\niLink 登录超时。")
    return None


def parse_ilink_message(
    raw_message: dict[str, Any],
    *,
    account_id: str,
) -> ILinkInboundMessage | None:
    sender_id = _optional_str(raw_message.get("from_user_id")) or ""
    if not sender_id or sender_id == account_id:
        return None
    text = extract_ilink_text(raw_message.get("item_list") or [])
    if not text:
        return None
    chat_id = _optional_str(raw_message.get("room_id")) or sender_id
    return ILinkInboundMessage(
        account_id=account_id,
        chat_id=chat_id,
        sender_id=sender_id,
        text=text,
        message_id=_optional_str(raw_message.get("message_id")),
        context_token=_optional_str(raw_message.get("context_token")),
        raw=raw_message,
    )


def extract_ilink_text(item_list: object) -> str:
    if not isinstance(item_list, list):
        return ""
    for item in item_list:
        if not isinstance(item, dict):
            continue
        if item.get("type") == ITEM_TEXT:
            return str((item.get("text_item") or {}).get("text") or "").strip()
    for item in item_list:
        if not isinstance(item, dict):
            continue
        if item.get("type") == ITEM_VOICE:
            return str((item.get("voice_item") or {}).get("text") or "").strip()
    return ""


def default_ilink_state_dir() -> Path:
    return Path.home() / ".wechat-to-a2a" / "ilink"


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _ilink_get_headers() -> dict[str, str]:
    return {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }


def _ilink_post_headers(token: str | None, body: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _required_str(data: dict[str, Any], key: str) -> str:
    value = _optional_str(data.get(key))
    if not value:
        raise RuntimeError(f"iLink response missing {key}: {data!r}")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
