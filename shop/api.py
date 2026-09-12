import html
import logging
import os
from pathlib import Path
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shop import store, work_queue
from shop.models import Conversation, OperationalQuestion, Question, Submission
from shop.vector_store import search as vector_search

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


@app.get("/api/operations/questions/{question_id}")
def operations(question_id: UUID) -> OperationalQuestion:
    return store.get_operations(question_id)


@app.post("/api/conversations/{conversation_id}/questions", status_code=202)
def submit(conversation_id: UUID, submission: Submission, request: Request) -> Question:
    return store.submit(conversation_id, token(request), submission)


@app.post("/api/conversations/{conversation_id}/questions/{question_id}/cancel")
def cancel(conversation_id: UUID, question_id: UUID, request: Request) -> Question:
    session_token = token(request)
    store.get_question(conversation_id, question_id, session_token)
    work_queue.cancel(question_id)
    return store.get_question(conversation_id, question_id, session_token)


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product(product_id: str) -> str:
    facts = store.get_product(product_id)
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>" + html.escape(facts.name) + "</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'><main>"
            f"<h1>{html.escape(facts.name)}</h1><p>Brand: {html.escape(facts.brand)}</p><p>{html.escape(facts.description)}</p>"
            f"<p>{html.escape(facts.department)} / {html.escape(facts.category)}</p>"
            f"<p>USD {facts.price_cents / 100:.2f} · {facts.stock} in stock</p>"
            f"<p>Rating: {facts.rating_average}/5 ({facts.rating_count} ratings)</p>"
            f"<p>Dimensions: {facts.length_cm:g} × {facts.width_cm:g} × {facts.height_cm:g} cm</p>"
            f"<p>Product weight: {facts.weight_kg:g} kg (excluding packaging)</p>"
            "<a href='/'>Back to assistant</a></main></html>")


@app.get("/api/products/search")
def search_products(q: str, category: str | None = None, department: str | None = None) -> dict[str, object]:
    if not store.catalog_ready():
        raise HTTPException(503, "Catalog is not ready")
    try:
        release = store.product_search_release()
        ids = vector_search(q, release, score_threshold=0.0 if (category or department) else .4) if release else []
    except Exception:
        raise HTTPException(503, "Product search is temporarily unavailable") from None
    products = store.products_by_ids(ids)
    if category:
        products = [product for product in products if product.category == category]
    if department:
        products = [product for product in products if product.department == department]
    catalog_info = store.catalog_status()
    return {"products": [product.model_dump() | {"url": f"/products/{product.id}", "available": product.stock > 0} for product in products], "catalog_release": catalog_info["release"] if catalog_info else None}


@app.get("/api/catalog/readiness")
def catalog_readiness() -> dict[str, object]:
    return store.catalog_status() or {"status": "unready"}
