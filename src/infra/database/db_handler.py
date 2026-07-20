# db_handler.py

import pymysql
import threading
from pymysql import OperationalError, InterfaceError

class DBHandler:
    def __init__(self, app_context):
        self._app_context = app_context
        self._config = None
        self._local = threading.local()

        self._initialize()

    def _initialize(self):
        """AppContext의 설정으로 DB 연결 및 초기화 책임을 수행"""
        db_cfg = getattr(self._app_context.cfg, "db", None)
        if not db_cfg:
            return

        self._config = db_cfg.dict()
        self.init_connection()

        from src.infra.database.db_init import init_db_if_needed
        init_db_if_needed(self, self._app_context.log)

    def init_connection(self):
        """스레드 로컬에 DB 연결 초기화"""
        if not self._config:
            raise RuntimeError("DB config is not initialized")
        if not hasattr(self._local, "conn"):
            self._local.conn = pymysql.connect(**self._config)

    def _create_new_connection(self):
        """현재 스레드에 새 커넥션을 생성한다."""
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
            except Exception:
                pass
            del self._local.conn
        self._local.conn = pymysql.connect(**self._config)

    def _ensure_connection_alive(self):
        """유휴/끊김 커넥션을 감지하면 자동 재연결한다."""
        if not hasattr(self._local, "conn"):
            self._create_new_connection()
            return

        try:
            # MySQL wait_timeout 이후 끊긴 연결이면 reconnect=True로 복구
            self._local.conn.ping(reconnect=True)
        except (OperationalError, InterfaceError):
            self._create_new_connection()

    def get_connection(self):
        """현재 스레드의 커넥션 반환 (없으면 init)"""
        if not self._config:
            raise RuntimeError("DB config is not initialized")

        self._ensure_connection_alive()
        return self._local.conn

    def close_connection(self):
        """커넥션 종료 및 제거"""
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
            except Exception:
                pass
            del self._local.conn

