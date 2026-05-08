from __future__ import annotations

import hashlib

import pytest

from wechat_a2a_gateway.wechat import parse_message_xml, render_text_reply, verify_signature


def _signature(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()


def test_verify_signature_accepts_valid_wechat_signature() -> None:
    token = "secret"
    timestamp = "123"
    nonce = "abc"
    assert verify_signature(
        token=token,
        timestamp=timestamp,
        nonce=nonce,
        signature=_signature(token, timestamp, nonce),
    )


def test_parse_text_message_xml() -> None:
    msg = parse_message_xml(
        b"""
        <xml>
          <ToUserName><![CDATA[gh_x]]></ToUserName>
          <FromUserName><![CDATA[user-1]]></FromUserName>
          <CreateTime>123</CreateTime>
          <MsgType><![CDATA[text]]></MsgType>
          <Content><![CDATA[hello]]></Content>
          <MsgId>42</MsgId>
        </xml>
        """
    )

    assert msg.to_user == "gh_x"
    assert msg.from_user == "user-1"
    assert msg.msg_type == "text"
    assert msg.content == "hello"
    assert msg.msg_id == "42"


def test_render_text_reply_escapes_content() -> None:
    xml = render_text_reply(to_user="user", from_user="gh", content="a < b")
    assert "<ToUserName><![CDATA[user]]></ToUserName>" in xml
    assert "<FromUserName><![CDATA[gh]]></FromUserName>" in xml
    assert "<Content>a &lt; b</Content>" in xml


def test_parse_message_xml_rejects_invalid_xml() -> None:
    with pytest.raises(ValueError, match="invalid WeChat XML"):
        parse_message_xml(b"<xml>")
