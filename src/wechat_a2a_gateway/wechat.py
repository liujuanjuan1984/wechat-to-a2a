from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class WeChatMessage:
    to_user: str
    from_user: str
    create_time: int
    msg_type: str
    content: str
    msg_id: str | None = None


def verify_signature(*, token: str, timestamp: str, nonce: str, signature: str) -> bool:
    expected = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()
    return expected == signature


def parse_message_xml(payload: bytes) -> WeChatMessage:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"invalid WeChat XML: {exc}") from exc

    def text(tag: str, *, required: bool = True) -> str | None:
        node = root.find(tag)
        value = node.text if node is not None else None
        if required and not value:
            raise ValueError(f"missing WeChat XML field: {tag}")
        return value

    create_time_raw = text("CreateTime")
    assert create_time_raw is not None
    try:
        create_time = int(create_time_raw)
    except ValueError as exc:
        raise ValueError("invalid WeChat XML field: CreateTime") from exc

    return WeChatMessage(
        to_user=text("ToUserName") or "",
        from_user=text("FromUserName") or "",
        create_time=create_time,
        msg_type=text("MsgType") or "",
        content=text("Content", required=False) or "",
        msg_id=text("MsgId", required=False),
    )


def render_text_reply(*, to_user: str, from_user: str, content: str) -> str:
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content>{escape(content)}</Content>"
        "</xml>"
    )
