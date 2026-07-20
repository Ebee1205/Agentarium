"""
 Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

 The copyright of this software belongs to Ebee1205(wavicle).
 All rights reserved.
"""

# main.py
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import traceback
import asyncio
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.app_context import AppContext
from src.common.responses import build_error_response

from src.service.chatbot.chat_sample import router as chatbot_router

class AppFactory:
    """애플리케이션 팩토리 클래스"""
    
    @staticmethod
    def create_app() -> FastAPI:
        """FastAPI 애플리케이션 생성 및 설정"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            ctx = None
            try:
                ctx = app.state.ctx
                await AppFactory._startup(app)
                yield
            except asyncio.CancelledError:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.warning("     - Application interrupted by user (CancelledError)")
                else:
                    print("     Application interrupted by user (CancelledError)")
                raise  # shutdown 호출을 위해 재전파 필요
            except Exception as e:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.error(f"     - Unexpected error during startup: {e}")
                else:
                    print(f"     Unexpected error during startup: {e}")
                traceback.print_exc()
                raise
            finally:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.info("     - Starting graceful shutdown")
                else:
                    print("     Starting graceful shutdown")
                await AppFactory._shutdown(app)

        
        app = FastAPI(lifespan=lifespan)
        
        # 컨텍스트 초기화
        ctx = AppContext()
        app.state.ctx = ctx
        
        # 설정 로드
        ctx.load_config("src/conf/atm_web_server.local.cfg.json")
        ctx.load_json_map("event_map", "src/conf/atm-event-map.cfg.json")

        # CORS 설정
        AppFactory._setup_cors(app, ctx)

        # 예외 핸들러 등록
        AppFactory._register_exception_handlers(app)
        
        # 라우터 등록
        AppFactory._register_routes(app)
        
        return app
    
    @staticmethod
    def _setup_cors(app: FastAPI, ctx: AppContext) -> None:
        """CORS 미들웨어 설정"""
        cors_config = ctx.cfg.http_config
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.allow_origins,
            allow_credentials=cors_config.allow_credentials,
            allow_methods=cors_config.allow_methods,
            allow_headers=cors_config.allow_headers,
        )
        print(f"CORS configuration complete: {cors_config.allow_origins}")

    @staticmethod
    def _register_exception_handlers(app: FastAPI) -> None:
        """FastAPI 공식 가이드 기반 전역 예외 핸들러 등록"""

        @app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(request: Request, exc: StarletteHTTPException):
            # 401, 404 등 HTTP 기반 예외 발생 시 호출됨
            return JSONResponse(
                status_code=exc.status_code,
                content=build_error_response(exc.status_code),
            )

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            ctx = getattr(request.app.state, "ctx", None)
            if ctx and getattr(ctx, "log", None):
                ctx.log.warning(f"Request validation failed: {exc.errors()}")

            # 유효성 검사 실패는 보통 400 Bad Request로 처리
            # 필요 시 exc.errors()를 data 인자로 넘겨 상세 에러를 포함할 수 있음
            return JSONResponse(
                status_code=400,
                content=build_error_response(400, data={"detail": exc.errors()}),
            )

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(request: Request, exc: Exception):
            ctx = getattr(request.app.state, "ctx", None)
            if ctx and getattr(ctx, "log", None):
                ctx.log.error(f"Unhandled exception: {str(exc)}")

            # 예상치 못한 모든 서버 에러는 500 처리
            return JSONResponse(
                status_code=500,
                content=build_error_response(500),
            )
    
    @staticmethod
    def _register_routes(app: FastAPI) -> None:
        """라우터 등록"""
        routers = [
            basic_router,
            files_router,
            auth_router,
            tag_router,
            session_router,
            chatbot_router
        ]
        for router in routers:
            app.include_router(router)
    
    @staticmethod
    async def _startup(app: FastAPI) -> None:
        """애플리케이션 시작 시 초기화"""
        try:
            print("     - Initializing application...")
            ctx = app.state.ctx

            # 초기화 후 연결 설정
            await AppFactory._initialize_managers(ctx)
            await AppFactory._initialize_handlers(ctx)
            await AppFactory._setup_connections(ctx)
            
            ctx.log.info("     == Initialization complete")

        except Exception as e:
            if hasattr(app.state, 'ctx') and hasattr(app.state.ctx, 'log'):
                app.state.ctx.log.error(f"     -- Initialization error: {str(e)}")
            else:
                print(f"     -- Initialization error: {str(e)}")
            traceback.print_exc()
            raise
        
    @staticmethod
    async def _initialize_managers(ctx: AppContext) -> None:
        """매니저 초기화"""
        print("     - Initializing managers...")   
        ctx._init_logger()
        AppFactory._test_logging(ctx.log)
        
        ctx._init_system_manager()

    @staticmethod
    async def _initialize_handlers(ctx: AppContext) -> None:
        """핸들러 초기화"""    
        ctx.log.info("     - Initializing handlers...")

        # ctx._init_db()  # 테이블 미존재 시 자동으로 스키마·시드 초기화 실행
        # ctx._init_mongodb()
        
        ctx._init_websocket()
        ctx._init_rmq()
        ctx._init_redis()

        # ctx._init_redis()
        # ctx._init_redis_consumer()

    @staticmethod
    async def _setup_connections(ctx: AppContext) -> None:
        """외부 서비스 연결 설정"""
        # RabbitMQ 연결
        await ctx.rmq_handler.connect()
        await ctx.rmq_handler.consume_multi()

        # Redis 연결
        if ctx.redis_handler:
            await ctx.redis_handler.connect()

        # # Redis 연결
        # await ctx.redis_handler.connect()
        # await ctx.redis_consumer.init_group()
        
        # ctx.redis_consumer_task = asyncio.create_task(ctx.redis_consumer.consume())
        # await asyncio.sleep(0)  # 태스크가 시작되도록 제어권 양보   

    
    @staticmethod
    async def _shutdown(app: FastAPI) -> None:
        """애플리케이션 종료 시 정리"""
        ctx = app.state.ctx

        if hasattr(ctx, 'log') and ctx.log:
            ctx.log.info("     -- Shutting down application")

        # Redis 종료
        if hasattr(ctx, "redis_consumer") and ctx.redis_consumer:
            try:
                await ctx.redis_consumer.stop()
                ctx.log.info("     -- RedisStreamConsumer stopped")
            except Exception as e:
                ctx.log.warning(f"     - RedisStreamConsumer stop failed: {e}")
        if ctx.redis_handler:
            try:
                await ctx.redis_handler.disconnect()
                ctx.log.info("     -- Redis handler closed")
            except Exception as e:
                ctx.log.warning(f"     - Redis close failed: {e}")

        # WebSocket 종료
        if ctx.ws_handler:
            try:
                await ctx.ws_handler.disconnect_all()
                ctx.log.info("     -- WebSocket handler closed")
            except Exception as e:
                ctx.log.warning(f"     - WebSocket close failed: {e}")
        
        # RabbitMQ 종료
        if ctx.rmq_handler:
            try:
                await ctx.rmq_handler.disconnect()
                ctx.log.info("     -- RabbitMQ handler closed")
            except Exception as e:
                ctx.log.warning(f"     - RabbitMQ close failed: {e}")
        
        # # MongoDB 종료
        # if ctx.mongo_handler:
        #     try:
        #         ctx.mongo_handler.close_connection()
        #         ctx.log.info("     -- MongoDB handler closed")
        #     except Exception as e:
        #         ctx.log.warning(f"     - MongoDB close failed: {e}")
        
        # 모니터링 종료
        if ctx.system_monitor:
            try:
                ctx.system_monitor.stop()
                ctx.log.info("     -- system monitor stopped")
            except Exception as e:
                ctx.log.warning(f"     - system monitor stop failed: {e}")

    @staticmethod
    def _test_logging(logger) -> None:
        """로깅 테스트"""
        logger.info("===FILE LOG TEST START===")
        logger.debug("   -test debug level")
        logger.info("   -test info level")
        logger.warning("   -test warn level")
        logger.error("   -test error level")
        logger.info("===FILE LOG TEST END===")

# 애플리케이션 인스턴스 생성
app = AppFactory.create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.atm_web_server:app", host="0.0.0.0", port=9571, reload=True)