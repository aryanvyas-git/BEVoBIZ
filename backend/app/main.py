import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import auth, dashboard, nlq, products, sales

logger = logging.getLogger(__name__)

app = FastAPI(title="BEVoBIZ API")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all so a genuinely unexpected error still returns
    clean JSON — never a stack trace or Starlette's default plain-text
    response — with the real exception logged server-side. FastAPI's own
    handlers for HTTPException and validation errors take precedence over
    this; it only ever fires for something nothing else already handled.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(sales.router)
app.include_router(dashboard.router)
app.include_router(nlq.router)


@app.get("/health")
def health():
    return {"status": "ok"}
