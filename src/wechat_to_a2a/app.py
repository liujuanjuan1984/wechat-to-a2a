from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

from .a2a_client import A2AClient
from .conversation import ConversationStore
from .gateway import WeChatA2AGateway
from .settings import Settings
from .wechat import parse_message_xml, render_text_reply, verify_signature

logger = logging.getLogger(__name__)


def create_app(settings: Settings, gateway: WeChatA2AGateway | None = None) -> FastAPI:
    if not settings.wechat_token:
        raise RuntimeError("WECHAT_TO_A2A_WECHAT_TOKEN is required for official webhook mode")
    wechat_token = settings.wechat_token
    app = FastAPI(title="wechat-to-a2a", version="0.1.0")
    if gateway is None:
        client = A2AClient(
            agent_card_url=settings.upstream_a2a_card_endpoint,
            bearer_token=settings.upstream_a2a_bearer_token,
            timeout_seconds=settings.upstream_a2a_timeout_seconds,
        )
        gateway = WeChatA2AGateway(
            a2a_client=client,
            conversation_store=ConversationStore(settings.conversation_state_path),
            reply_max_chars=settings.wechat_reply_max_chars,
            split_multiline_messages=settings.wechat_split_multiline_messages,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/wechat", response_class=Response)
    async def verify_wechat_endpoint(
        signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
        echostr: str = Query(...),
    ) -> Response:
        if not verify_signature(
            token=wechat_token,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
        ):
            raise HTTPException(status_code=403, detail="invalid WeChat signature")
        return Response(content=echostr, media_type="text/plain")

    @app.post("/wechat", response_class=Response)
    async def handle_wechat_message(
        request: Request,
        signature: str = Query(...),
        timestamp: str = Query(...),
        nonce: str = Query(...),
    ) -> Response:
        if not verify_signature(
            token=wechat_token,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
        ):
            raise HTTPException(status_code=403, detail="invalid WeChat signature")

        payload = await request.body()
        message = parse_message_xml(payload)
        if message.msg_type != "text":
            reply = "Only text messages are supported right now."
            return _wechat_xml_response(
                to_user=message.from_user,
                from_user=message.to_user,
                content=reply,
            )

        try:
            gateway_reply = await gateway.handle_message(message)
        except httpx.HTTPError as exc:
            logger.warning("upstream A2A request failed: %s", exc)
            reply = "The upstream A2A agent is unavailable."
        except RuntimeError as exc:
            logger.warning("upstream A2A response failed: %s", exc)
            reply = "The upstream A2A agent returned an invalid response."
        except Exception as exc:
            logger.warning("upstream A2A handling failed: %s", exc)
            reply = "The upstream A2A agent is unavailable."
        else:
            reply = gateway_reply.text

        return _wechat_xml_response(
            to_user=message.from_user,
            from_user=message.to_user,
            content=reply,
        )

    return app


def _wechat_xml_response(*, to_user: str, from_user: str, content: str) -> Response:
    xml = render_text_reply(to_user=to_user, from_user=from_user, content=content)
    return Response(content=xml, media_type="application/xml")
