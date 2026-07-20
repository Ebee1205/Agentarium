"""
 Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

 The copyright of this software belongs to Ebee1205(wavicle).
 All rights reserved.
"""

from __future__ import annotations

import asyncio
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.app_context import AppContext
from src.common.responses import build_error_response

from src.service.terrarium.terrarium_router import router as terrarium_router


class AppFactory:
    """ATM FastAPI 애플리케이션 팩토리."""

    @staticmethod
    def create_app() -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            ctx = app.state.ctx
            try:
                await AppFactory._startup(app)
                yield
            except asyncio.CancelledError:
                AppFactory._log(ctx, "warning", "Application interrupted by user")
                raise
            except Exception as exc:
                AppFactory._log(ctx, "error", f"Unexpected startup error: {exc}")
                traceback.print_exc()
                raise
            finally:
                await AppFactory._shutdown(app)

        app = FastAPI(
            title="ATM - Agent Terrarium",
            version="0.1.0",
            lifespan=lifespan,
        )
        ctx = AppContext()
        app.state.ctx = ctx

        ctx.load_config("src/conf/atm_web_server.local.cfg.json")
        ctx.load_json_map("event_map", "src/conf/atm-event-map.cfg.json")

        AppFactory._setup_cors(app, ctx)
        AppFactory._register_exception_handlers(app)
        AppFactory._register_routes(app)
        return app

    @staticmethod
    def _setup_cors(app: FastAPI, ctx: AppContext) -> None:
        cors = ctx.cfg.http_config
        if cors is None:
            return
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors.allow_origins,
            allow_credentials=cors.allow_credentials,
            allow_methods=cors.allow_methods,
            allow_headers=cors.allow_headers,
        )

    @staticmethod
    def _register_exception_handlers(app: FastAPI) -> None:
        @app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(
            request: Request,
            exc: StarletteHTTPException,
        ):
            return JSONResponse(
                status_code=exc.status_code,
                content=build_error_response(
                    exc.status_code,
                    data={"detail": exc.detail},
                ),
            )

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(
            request: Request,
            exc: RequestValidationError,
        ):
            AppFactory._log(
                getattr(request.app.state, "ctx", None),
                "warning",
                f"Request validation failed: {exc.errors()}",
            )
            return JSONResponse(
                status_code=400,
                content=build_error_response(
                    400,
                    data={"detail": exc.errors()},
                ),
            )

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(request: Request, exc: Exception):
            AppFactory._log(
                getattr(request.app.state, "ctx", None),
                "error",
                f"Unhandled exception: {exc}",
            )
            return JSONResponse(
                status_code=500,
                content=build_error_response(500),
            )

    @staticmethod
    def _register_routes(app: FastAPI) -> None:
        app.include_router(terrarium_router)

        @app.get("/health")
        async def health(request: Request):
            ctx = request.app.state.ctx
            return {
                "status": "ok",
                "project": ctx.cfg.project_name,
                "terrarium": ctx.simulation_manager is not None,
                "llm_provider": (
                    ctx.llm_manager.provider_name if ctx.llm_manager else None
                ),
            }

    @staticmethod
    async def _startup(app: FastAPI) -> None:
        ctx = app.state.ctx
        ctx._init_logger()
        ctx._init_system_manager()
        ctx._init_websocket()

        # 외부 인프라는 설정이 있을 때만 초기화합니다.
        if ctx.cfg.rmq is not None:
            ctx._init_rmq()
        if ctx.cfg.redis is not None:
            ctx._init_redis()
        if ctx.cfg.db is not None:
            ctx._init_db()

        ctx._init_llms()
        ctx._init_terrarium_managers()
        await AppFactory._setup_connections(ctx)

        terrarium_cfg = ctx.cfg.terrarium
        if terrarium_cfg.enabled:
            state = await ctx.simulation_manager.ensure(
                terrarium_cfg.default_simulation_id
            )
            if terrarium_cfg.auto_start:
                await ctx.simulation_manager.start(state.simulation_id)

        AppFactory._log(ctx, "info", "ATM initialization complete")

    @staticmethod
    async def _setup_connections(ctx: AppContext) -> None:
        if ctx.rmq_handler is not None:
            await ctx.rmq_handler.connect()
            await ctx.rmq_handler.consume_multi()
        if ctx.redis_handler is not None:
            await ctx.redis_handler.connect()

    @staticmethod
    async def _shutdown(app: FastAPI) -> None:
        ctx = app.state.ctx
        AppFactory._log(ctx, "info", "Starting graceful shutdown")

        if ctx.simulation_manager is not None:
            await ctx.simulation_manager.close()
        if ctx.llm_manager is not None:
            try:
                await ctx.llm_manager.close()
            except Exception as exc:
                AppFactory._log(ctx, "warning", f"LLM close failed: {exc}")
        if ctx.redis_consumer is not None:
            try:
                await ctx.redis_consumer.stop()
            except Exception as exc:
                AppFactory._log(ctx, "warning", f"Redis consumer stop failed: {exc}")
        if ctx.redis_handler is not None:
            try:
                await ctx.redis_handler.disconnect()
            except Exception as exc:
                AppFactory._log(ctx, "warning", f"Redis close failed: {exc}")
        if ctx.ws_handler is not None:
            try:
                await ctx.ws_handler.disconnect_all()
            except Exception as exc:
                AppFactory._log(ctx, "warning", f"WebSocket close failed: {exc}")
        if ctx.rmq_handler is not None:
            try:
                await ctx.rmq_handler.disconnect()
            except Exception as exc:
                AppFactory._log(ctx, "warning", f"RabbitMQ close failed: {exc}")
        if ctx.system_monitor is not None:
            ctx.system_monitor.stop()

    @staticmethod
    def _log(ctx, level: str, message: str) -> None:
        logger = getattr(ctx, "log", None) if ctx is not None else None
        method = getattr(logger, level, None)
        if not callable(method):
            print(message)
            return
        try:
            method(message)
        except TypeError:
            method("ATM", message)


app = AppFactory.create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.atm_web_server:app", host="0.0.0.0", port=9571, reload=True)
