from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from open_mechanic.web.schemas import ConnectRequest, DiagnosisRequest
from open_mechanic.web.service import DashboardService

STATIC_DIR = Path(__file__).with_name("static")


def _safe_static_file(path: str) -> Path | None:
    static_root = STATIC_DIR.resolve()
    requested = (static_root / path).resolve()
    try:
        requested.relative_to(static_root)
    except ValueError:
        return None
    return requested if requested.is_file() else None


def create_app(*, offline: bool = False, service: DashboardService | None = None) -> FastAPI:
    app = FastAPI(title="open-mechanic web dashboard")
    dashboard = service or DashboardService(offline=offline)

    @app.get("/api/status")
    def status() -> object:
        return dashboard.get_status()

    @app.post("/api/connect")
    def connect(request: ConnectRequest) -> object:
        return dashboard.connect(request)

    @app.post("/api/disconnect")
    def disconnect() -> object:
        return dashboard.disconnect()

    @app.get("/api/sensors")
    def sensors() -> object:
        return dashboard.get_sensors()

    @app.get("/api/dtcs")
    def dtcs() -> object:
        return dashboard.get_dtcs()

    @app.post("/api/diagnose")
    def diagnose(request: DiagnosisRequest) -> object:
        return dashboard.diagnose(request)

    @app.get("/api/reports")
    def reports() -> object:
        return dashboard.list_reports()

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown_api(path: str) -> object:
        raise HTTPException(status_code=404, detail="API route not found.")

    index_path = STATIC_DIR / "index.html"
    assets_path = STATIC_DIR / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    if index_path.exists():

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(index_path)

        @app.get("/{path:path}")
        def frontend(path: str) -> FileResponse:
            requested = _safe_static_file(path)
            if requested is not None:
                return FileResponse(requested)
            return FileResponse(index_path)

    else:

        @app.get("/")
        def missing_frontend() -> object:
            raise HTTPException(
                status_code=503,
                detail="React dashboard has not been built. Run npm --prefix frontend run build.",
            )

    return app
