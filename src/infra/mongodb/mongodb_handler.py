# handler/mongodb_handler.py

import pymongo
from pymongo import MongoClient

class MongoDBHandler:
    def __init__(self, config: dict):
        self._config = config
        self.client = None
        self.db = None

    def init_connection(self):
        """MongoDB 연결 초기화"""
        if self.client:
            return

        # 설정에서 값 추출 (기본값 처리 포함)
        host = self._config.get("host", "localhost")
        port = self._config.get("port", 27017)
        user = self._config.get("user")
        password = self._config.get("password")
        database = self._config.get("database")
        
        # MongoClient 생성 (Thread-safe 하므로 단일 인스턴스 사용)
        self.client = MongoClient(
            host=host,
            port=port,
            username=user,
            password=password,
            # 필요한 경우 추가 옵션 설정 (예: connectTimeoutMS 등)
        )

        if database:
            self.db = self.client[database]

    def get_connection(self):
        """MongoClient 객체 반환"""
        if not self.client:
            self.init_connection()
        return self.client
    
    def get_db(self):
        """Database 객체 반환"""
        if self.db is None:
            self.init_connection()
        return self.db

    def close_connection(self):
        """커넥션 종료"""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None
