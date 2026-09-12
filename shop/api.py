import html
import logging
import os
from pathlib import Path
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shop import store
from shop.models import Conversation, Question, Submission

app = FastAPI(title="Shopping assistant")
logger = logging.getLogger("uvicorn.error")
COOKIE = "shop_session"
STATIC = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def token(request: Request) -> str:
    value = request.cookies.get(COOKIE)
    if not value:
        raise HTTPException(401, "Start an anonymous session first")
    return value


@app.middleware("http")
async def request_metadata(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info("request_id=%s method=%s status=%s", request_id, request.method, response.status_code)
    return response


@app.exception_handler(store.NotFound)
async def not_found(request: Request, error: store.NotFound) -> JSONResponse:
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.get("/health")
def health() -> dict[str, str]:
    with store.connect() as db:
        db.execute("SELECT 1")
    return {"status": "ok"}


@app.exception_handler(store.Conflict)
async def conflict(request: Request, error: store.Conflict) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=409)


@app.post("/api/session")
def session(request: Request, response: Response) -> dict[str, str]:
    value = store.ensure_session(request.cookies.get(COOKIE))
    response.set_cookie(COOKIE, value, max_age=30 * 24 * 60 * 60, httponly=True,
                        samesite="strict", secure=os.environ.get("COOKIE_SECURE") == "true")
    return {"status": "ready"}


@app.post("/api/conversations", status_code=201)
def create_conversation(request: Request) -> dict[str, UUID]:
    return {"id": store.create_conversation(token(request))}


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: UUID, request: Request) -> Conversation:
    return store.get_conversation(conversation_id, token(request))


@app.post("/api/conversations/{conversation_id}/questions", status_code=202)
def submit(conversation_id: UUID, submission: Submission, request: Request) -> Question:
    return store.submit(conversation_id, token(request), submission)


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product(product_id: str) -> str:
    facts = store.get_product(product_id)
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>" + html.escape(facts.name) + "</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'><main>"
            f"<h1>{html.escape(facts.name)}</h1><p>{html.escape(facts.description)}</p>"
            f"<p>{html.escape(facts.department)} / {html.escape(facts.category)}</p>"
            f"<p>USD {facts.price_cents / 100:.2f} · {facts.stock} in stock</p>"
            f"<p>Rating: {facts.rating_average}/5 ({facts.rating_count} ratings)</p>"
            f"<p>Dimensions: {facts.length_cm:g} × {facts.width_cm:g} × {facts.height_cm:g} cm</p>"
            f"<p>Product weight: {facts.weight_kg:g} kg (excluding packaging)</p>"
            "<a href='/'>Back to assistant</a></main></html>")
