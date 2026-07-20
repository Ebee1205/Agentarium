"""
 Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

 The copyright of this software belongs to Ebee1205(wavicle).
 All rights reserved.
"""

# app_context.py
import orjson

from pydantic import BaseModel, Field
from typing import Any, Optional

from src.modules import logger

from src.modules.system_monitor import SystemMonitor
from src.infra.websocket.websocket_handler import WebSocketHandler
from src.infra.database.db_handler import DBHandler
from src.infra.rabbitmq.rabbitmq_handler import RabbitMQHandler
from src.infra.redis.redis_handler import RedisHandler
from src.infra.redis_stream.redis_stream_consumer import RedisStreamConsumer

from src.llm.llm_manager import LLMManager
# from src.llm.rag_manager import RAGManager

class LoggerConfig(BaseModel):
    level: str
    path: str
    suffix: str
    max_bytes: int
    max_files: str
    rotation: str
    use_console: bool

class HTTPConfig(BaseModel):
    allow_origins: list[str]
    allow_methods: list[str]
    allow_headers: list[str]
    allow_credentials: bool
    
class DBConfig(BaseModel):
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    password: Optional[str] = None
    database: Optional[str] = None
    charset: Optional[str] = "utf8mb4"
    autocommit: Optional[bool] = True

class MongoDBConfig(BaseModel):
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    password: Optional[str] = None
    database: Optional[str] = None
    
class RMQConfig(BaseModel):
    host: Optional[str]
    port: Optional[int]
    user: Optional[str]
    password: Optional[str]
    queues: Optional[list[dict]]

class RedisConfig(BaseModel):
    host: Optional[str]
    port: Optional[int]
    db: Optional[int]
    password: Optional[str] = None

class RedisConsumerConfig(BaseModel):
    stream_key: Optional[str]
    group_name: Optional[str]
    consumer_name: Optional[str]

class R2Config(BaseModel):
    account_id: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    bucket_name: Optional[str] = None
    region: Optional[str] = "auto"
    endpoint_url: Optional[str] = None
    public_base_url: Optional[str] = None
    image_prefix: Optional[str] = "images"
    upload_url_expire_seconds: Optional[int] = 900


class LLMConfig(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None
    timeout_seconds: int = 120
    # 실제 키는 cfg에 저장하지 않고 이 이름의 환경변수에서 조회한다.
    api_key_env: Optional[str] = None


class RAGConfig(BaseModel):
    enabled: bool = True
    chunks_path: str = "reference/atm_chunks.json"
    index_path: str = "faiss_index_chunks"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: Optional[str] = "http://127.0.0.1:11434"


class AppConfig(BaseModel):
    # 상위 항목 직접 정의
    environment: str
    project_name: str
    api_v1_str: str
    host: str
    port: int
    secret_key: str
    access_token_expire_minutes: int

    # 구성 요소들
    mongodb: Optional[MongoDBConfig] = None
    logger: LoggerConfig
    http_config: Optional[HTTPConfig] = None

    rmq: Optional[RMQConfig] = None
    redis: Optional[RedisConfig] = None
    redis_consumer: Optional[RedisConsumerConfig] = None
    r2: Optional[R2Config] = None
    db: Optional[DBConfig] = None

    # 시스템 모니터링 관련 기본값 설정
    enable_monitoring: Optional[bool] = True
    monitoring_interval: Optional[int] = 10

    # 서비스 관련
    llm: Optional[LLMConfig] = None
    rag: RAGConfig = Field(default_factory=RAGConfig)


class AppContext:
    def __init__(self):
        self.cfg = {}
        self.log = None
        
        # 핸들러
        self.ws_handler = None
        self.redis_handler = None
        self.redis_consumer = None
        self.rmq_handler = None
        self.mongo_handler = None
        self.db_handler = None

        # 매니저
        self.system_monitor = None
        # self.rag_manager: Optional[RAGManager] = None
        self.llm_manager: Optional[LLMManager] = None

    def load_config(self, path: str) -> AppConfig:
        """JSON 파일을 로드하고 AppConfig 모델로 파싱"""
        print("+ start load cfg")

        with open(path, "rb") as f:
            raw = orjson.loads(f.read())

        print("- end load cfg")
        self.cfg = AppConfig(**raw)
        
    def load_json_map(self, name: str, path: str):
        """
        임의의 JSON 파일을 로드하여 ctx에 동적으로 등록
        예: ctx.load_json_map("event_map", "config/event_map.json")
            → self.event_map 로 저장됨
        """
        try:
            with open(path, "rb") as f:
                data = orjson.loads(f.read())

            setattr(self, name, data)
            print(f"> loaded JSON map '{name}' from {path}")
            return True
        except Exception as e:
            print(f"!! failed to load JSON map '{name}' from {path}: {e}")
            return False

    def load_token(self, path: str):
        """토큰 파일을 로드하여 cfg의 각 서비스 설정에 병합"""
        try:
            with open(path, "rb") as f:
                tokens = orjson.loads(f.read())

            if "r2" in tokens and self.cfg.r2:
                r2 = tokens["r2"]
                if "access_key_id" in r2:
                    self.cfg.r2.access_key_id = r2["access_key_id"]
                if "secret_access_key" in r2:
                    self.cfg.r2.secret_access_key = r2["secret_access_key"]

            print(f"> loaded token from {path}")
            return True
        except FileNotFoundError:
            print(f"!! token file not found: {path}")
            return False
        except Exception as e:
            print(f"!! failed to load token '{path}': {e}")
            return False

    def _init_logger(self):
        print("+ start init logger")

        log_level = self.cfg.logger.level 
        log_path = self.cfg.logger.path
        log_max_files = self.cfg.logger.max_files
        self.log = logger.setup_logger(log_level, log_path, log_max_files)

        self.log.debug("- end init logger")

    def _init_websocket(self):
        self.log.debug("+ start init websocket")

        self.ws_handler = WebSocketHandler(self)

        self.log.debug("- end init websocket")

    def _init_rmq(self):
        self.log.debug("+ start init RabbitMQ")

        self.rmq_handler = RabbitMQHandler(self)

        self.log.debug("- end init RabbitMQ")

    def _init_redis(self):
        self.log.debug("+ start init Redis")

        self.redis_handler = RedisHandler(self)

        self.log.debug("- end init Redis")
        
    def _init_redis_consumer(self):
        self.log.debug("+ start init RedisStreamConsumer")

        self.redis_consumer = RedisStreamConsumer(self)
        
        self.log.debug("- end init RedisStreamConsumer")
        
    def _init_db(self) -> None:
        """호환성 유지용 래퍼"""
        self.log.debug("+ start init DB")

        self.db_handler = DBHandler(self)

        self.log.debug("- end init DB")

    # def _init_mongodb(self):
    #     self.log.debug("+ start init MongoDB")
        
    #     if not self.cfg.mongodb:
    #         self.log.debug("- skip init MongoDB (no config)")
    #         return
            
    #     mongo_config = self.cfg.mongodb.dict()
    #     self.mongo_handler = MongoDBHandler(mongo_config)
    #     self.mongo_handler.init_connection()
        
    #     self.log.debug("- end init MongoDB")

    def _init_system_manager(self):
        self.log.debug("+ start init system manager")

        if self.cfg.enable_monitoring:
            interval = self.cfg.monitoring_interval
            self.system_monitor = SystemMonitor(self.log, interval)
            self.system_monitor.start()

        self.log.debug("- end init system manager")

    def _init_llms(self):
        if not self.cfg or not self.cfg.llm:
            self.log.warning("[LLM] llm config missing; skipping LLM init")
            return

        self.log.debug("+ start init LLMs")

        try:
            # LLMManager가 ctx.cfg.llm과 ctx.rag_manager를 직접 사용한다.
            self.llm_manager = LLMManager(ctx=self)
            self.log.info(
                f"[LLM] manager ready "
                f"(provider={self.cfg.llm.provider}, model={self.cfg.llm.model})"
            )
        except Exception as exc:
            self.log.error(f"[LLM] init failed: {exc}")
            raise

        self.log.debug("- end init LLMs")