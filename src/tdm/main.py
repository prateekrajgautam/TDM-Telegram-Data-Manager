from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.jobs import start_workers, requeue_pending
from app.logger import setup_logging, get_logger
from app.routers import auth, dialogs, jobs, settings as settings_router
from app.telegram_client import manager as tg_manager

BASE_DIR = Path(__file__).resolve().parent
setup_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    log.info("Starting Telegram Data Manager v%s", settings.app_version)
    init_db()
    restored = await tg_manager.restore_active_session()
    log.info("Session restored on startup: %s", restored)
    start_workers()
    requeue_pending()
    yield


app = FastAPI(title="Telegram Data Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(auth.router)
app.include_router(dialogs.router)
app.include_router(jobs.router)
app.include_router(settings_router.router)


@app.get("/")
async def index(request: Request):
    if not tg_manager.is_logged_in():
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dialogs")
async def dialogs_page(request: Request):
    if not tg_manager.is_logged_in():
        return RedirectResponse("/login")
    return templates.TemplateResponse("dialogs.html", {"request": request})


@app.get("/jobs")
async def jobs_page(request: Request):
    return templates.TemplateResponse("jobs.html", {"request": request})


@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


def run():
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
