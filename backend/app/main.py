from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.ws_input import router as ws_input_router
from app.core.config import settings
from app.db.database import init_db

app = FastAPI(title="RetroHost")

init_db()

app.include_router(api_router)
app.include_router(ws_input_router)

if settings.FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(settings.FRONTEND_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(settings.FRONTEND_DIR / "index.html"))
