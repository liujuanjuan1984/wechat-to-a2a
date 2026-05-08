from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

from .a2a_client import A2AClient
from .settings import Settings
from .wechat import parse_message_xml, render_text_reply, verify_signature

logger = logging.getLogger(__name__)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="wechat-to-a2a", version="0.1.0")
    context_by_user: dict[str, str] = {}

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
            token=settings.wechat_token,
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
            token=settings.wechat_token,
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

        client = A2AClient(
            endpoint=settings.a2a_endpoint,
            bearer_token=settings.a2a_bearer_token,
            timeout_seconds=settings.a2a_timeout_seconds,
        )
        try:
            a2a_reply = await client.send_message(
                text=message.content,
                context_id=context_by_user.get(message.from_user),
            )
        except httpx.HTTPError as exc:
            logger.warning("upstream A2A request failed: %s", exc)
            reply = "The upstream A2A agent is unavailable."
        except RuntimeError as exc:
            logger.warning("upstream A2A response failed: %s", exc)
            reply = "The upstream A2A agent returned an invalid response."
        else:
            if a2a_reply.context_id:
                context_by_user[message.from_user] = a2a_reply.context_id
            reply = a2a_reply.text or "The upstream A2A agent returned no text."

        return _wechat_xml_response(
            to_user=message.from_user,
            from_user=message.to_user,
            content=reply,
        )

    return app


def _wechat_xml_response(*, to_user: str, from_user: str, content: str) -> Response:
    xml = render_text_reply(to_user=to_user, from_user=from_user, content=content)
    return Response(content=xml, media_type="application/xml")
