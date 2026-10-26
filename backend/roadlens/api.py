"""FastAPI entry point, served on loopback by the project launch scripts."""

import asyncio
import hashlib
import uuid
from time import perf_counter
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import __version__
from .capture import SourceError, VideoSource
from .calibration_api import calibration_routes
from .phase3_api import phase3_routes
from .profiling import ResponseProfiler
from .schemas import SessionSnapshot, StartRequest
from .session import SessionConflict, SessionManager
from .validation_api import validation_routes
from .field_api import field_routes
from .field_store import FieldStore
from .camera_api import camera_routes
from .annotation_api import annotation_routes
from .traffic_api import traffic_routes
from .traffic_overlay import traffic_overlay_routes


MAX_UPLOAD_BYTES = 256 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
LOCAL_ORIGINS = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 4173, 8000)}


def create_app(manager: SessionManager | None = None, max_upload_bytes: int = MAX_UPLOAD_BYTES) -> FastAPI:
    manager = manager or SessionManager()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(manager.stop)
        if hasattr(manager, "annotations"):
            await asyncio.to_thread(manager.annotations.close)

    app = FastAPI(title="RoadLens Radar", version=__version__, lifespan=lifespan)
    app.state.manager = manager
    app.include_router(calibration_routes(manager))
    response_profiler = ResponseProfiler()
    app.include_router(validation_routes())
    app.include_router(phase3_routes(manager, response_profiler))
    manager.field_store = getattr(manager, "field_store", None) or FieldStore(manager.calibrations.directory.parent / "field_sessions")
    app.include_router(annotation_routes(manager))
    app.include_router(field_routes(manager.field_store, observation_provider=manager.field_observation,
                                   tracking_provider=manager.annotations.metrics, annotation_delete=manager.annotations.delete))
    app.include_router(camera_routes(manager))
    app.include_router(traffic_routes(manager, field_store=manager.field_store, annotation_provider=manager.annotations.get))
    app.include_router(traffic_overlay_routes(manager))

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        host = urlsplit("//" + request.headers.get("host", "")).hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse({"detail": "RoadLens accepts requests to localhost only."}, status_code=403)
        origin = request.headers.get("origin")
        if (origin and origin not in LOCAL_ORIGINS) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-origin access to the local camera API is blocked."}, status_code=403)
        if request.url.path == "/api/videos":
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_upload_bytes + 2 * 1024 * 1024:
                return JSONResponse({"detail": "Video exceeds the 256 MB upload limit."}, status_code=413)
        if request.url.path.startswith("/api/validation/"):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > 4 * 1024 * 1024:
                return JSONResponse({"detail": "Validation requests are limited to 4 MiB; file imports are limited to 2 MiB."}, status_code=413)
        started = perf_counter()
        response = await call_next(request)
        response_ms = (perf_counter() - started) * 1000
        route = request.scope.get("route")
        if route is not None:
            response_profiler.record(f"{request.method} {route.path}", response_ms)
        response.headers["X-RoadLens-Response-Ms"] = f"{response_ms:.3f}"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(SessionConflict)
    async def session_conflict(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(SourceError)
    async def source_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(ValueError)
    async def invalid_configuration(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing_profile(request, error):
        return JSONResponse({"detail": str(error.args[0])}, status_code=404)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "model": manager.model_status()}

    @app.get("/api/cameras")
    def cameras():
        return {"cameras": manager.cameras()}

    @app.get("/api/field-sources")
    def field_sources():
        return {"sources": manager.field_sources()}

    @app.post("/api/videos")
    async def upload_video(file: UploadFile = File(...)):
        filename = (file.filename or "video").replace("\\", "/").rsplit("/", 1)[-1]
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in VIDEO_EXTENSIONS:
            await file.close()
            raise HTTPException(400, "Choose an MP4, AVI, MOV, MKV, WebM, or M4V video.")
        manager.upload_dir.mkdir(parents=True, exist_ok=True)
        path = manager.upload_dir / (uuid.uuid4().hex + extension)
        source = None
        try:
            size = 0
            digest = hashlib.sha256()
            with path.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(413, "Video exceeds the 256 MB upload limit.")
                    output.write(chunk)
                    digest.update(chunk)
            if not size:
                raise HTTPException(400, "The uploaded video is empty.")
            source = await asyncio.to_thread(VideoSource, path, filename)
            first_frame = await asyncio.to_thread(source.read)
            if first_frame is None:
                raise SourceError("The selected video contains no decodable frames.")
            label = "".join(character for character in filename if character.isprintable())[:120]
            video_id = manager.register_video(path, label, "video:" + digest.hexdigest())
            metadata = {"video_id": video_id, "name": label, "filename": label, "width": source.width, "height": source.height, "reported_fps": source.reported_fps}
            if manager.video_file(video_id).resolve() != path.resolve():
                source.close()
                source = None
                path.unlink()
            return metadata
        except Exception:
            if source is not None:
                source.close()
                source = None
            path.unlink(missing_ok=True)
            raise
        finally:
            if source is not None:
                source.close()
            await file.close()

    @app.get("/api/session", response_model=SessionSnapshot)
    def session():
        return manager.snapshot()

    @app.post("/api/sessions/start", response_model=SessionSnapshot)
    def start(request: StartRequest):
        return manager.start(request)

    @app.post("/api/sessions/pause", response_model=SessionSnapshot)
    def pause():
        return manager.pause()

    @app.post("/api/sessions/resume", response_model=SessionSnapshot)
    def resume():
        return manager.resume()

    @app.post("/api/sessions/stop", response_model=SessionSnapshot)
    def stop():
        return manager.stop()

    @app.post("/api/sessions/reset", response_model=SessionSnapshot)
    def reset():
        return manager.reset()

    @app.get("/api/frame")
    def frame(session: str | None = None):
        if session is not None and session != manager.snapshot().session_id:
            raise HTTPException(404, "This session is no longer active.")
        jpeg = manager.frame()
        if jpeg is None:
            raise HTTPException(404, "No processed frame is available yet.")
        return Response(jpeg, media_type="image/jpeg")

    @app.get("/api/stream")
    async def stream(request: Request, session: str | None = None):
        if session is not None and session != manager.snapshot().session_id:
            raise HTTPException(404, "This session is no longer active.")

        async def frames():
            version = -1
            while not await request.is_disconnected():
                next_version, jpeg, state, current_session = await asyncio.to_thread(manager.wait_for_frame, version, session)
                if session is not None and session != current_session:
                    break
                if jpeg is not None and next_version != version:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
                version = next_version
                if state in {"idle", "stopped", "completed", "error"}:
                    break
            yield b"--frame--\r\n"

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    return app


app = create_app()
