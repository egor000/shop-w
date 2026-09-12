"""Hold the public ASGI acknowledgement after the real application commits."""
import asyncio

from shop.api import app as application


async def app(scope, receive, send):
    async def delayed_send(message):
        if scope["type"] == "http" and message["type"] == "http.response.start" and message["status"] == 202:
            await asyncio.Event().wait()
        await send(message)

    await application(scope, receive, delayed_send)
