# handler/websocket_handler.py

from uuid import uuid4

import orjson
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


class WebSocketHandler:
    """
    WebSocket 연결의 init -> process -> destroy 라이프사이클을 관리합니다.

    - init: 연결 승인 및 세션 등록
    - process: 메시지 수신/처리/응답
    - destroy: 연결 및 세션 정보 정리

    같은 sid에 여러 WebSocket 연결을 허용합니다. 연결이 끊어진 뒤 같은 sid로
    다시 접속하면 새 WebSocket 객체가 해당 세션에 다시 등록됩니다.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.log = ctx.log
        self.active_connections: list[WebSocket] = []
        self.session_map: dict[str, list[WebSocket]] = {}

    # ------------------------------------------------------------------
    # lifecycle: init
    # ------------------------------------------------------------------
    async def init(self, websocket: WebSocket, sid: str | None = None) -> str:
        """WebSocket 연결을 승인하고 활성 연결 및 세션에 등록합니다."""
        if getattr(websocket, "_ws_registered", False):
            return getattr(websocket, "_connection_id")

        await websocket.accept()

        connection_id = uuid4().hex
        setattr(websocket, "_sid", sid)
        setattr(websocket, "_connection_id", connection_id)
        setattr(websocket, "_ws_registered", True)

        self.active_connections.append(websocket)

        if sid:
            connections = self.session_map.setdefault(sid, [])
            connections.append(websocket)
            self.log.info(
                "WS",
                (
                    f"- Connection initialized: sid={sid}, "
                    f"connection_id={connection_id}, client={websocket.client}, "
                    f"session_connections={len(connections)}"
                ),
            )
        else:
            self.log.info(
                "WS",
                (
                    f"- Connection initialized: connection_id={connection_id}, "
                    f"client={websocket.client}"
                ),
            )

        return connection_id

    async def connect(self, websocket: WebSocket, id: str | None = None) -> str:
        """기존 호출부 호환용 init 별칭입니다."""
        return await self.init(websocket, sid=id)

    # ------------------------------------------------------------------
    # lifecycle: process
    # ------------------------------------------------------------------
    async def process(self, websocket: WebSocket, processor) -> None:
        """
        연결이 유지되는 동안 메시지를 처리합니다.

        WebSocketDisconnect, 수신 예외, 서버 종료 등 어떤 경로로 빠져나가더라도
        finally에서 destroy를 호출하여 등록 정보를 정리합니다.
        """
        try:
            while self._is_registered(websocket):
                try:
                    raw_message = await websocket.receive_text()
                except WebSocketDisconnect as exc:
                    self.log.info(
                        "WS",
                        (
                            f"- Client disconnected: sid={getattr(websocket, '_sid', None)}, "
                            f"connection_id={getattr(websocket, '_connection_id', None)}, "
                            f"code={exc.code}"
                        ),
                    )
                    break

                try:
                    message = orjson.loads(raw_message)
                    if not isinstance(message, dict):
                        raise ValueError("WebSocket message must be a JSON object")

                    self.log.debug("WS", f">> Received message: {message}")
                    sid = self._normalize_message(websocket, message)

                    try:
                        response = await processor(self.ctx, websocket, message)
                    except Exception as exc:
                        self.log.error("WS", f"- Handler error: {exc}")
                        response = {
                            "status": "error",
                            "message": str(exc),
                        }

                    # processor가 직접 응답을 보낸 경우 None을 반환합니다.
                    if response is None:
                        continue

                    if sid:
                        await self.broadcast_to_session(sid, response)
                    else:
                        await self.send_to_connection(websocket, response)

                    self.log.debug("WS", f"<< Send response: {response}")

                except (orjson.JSONDecodeError, ValueError) as exc:
                    self.log.warning("WS", f"- Invalid message: {exc}")
                    await self.send_to_connection(
                        websocket,
                        {
                            "status": "error",
                            "errMsg": str(exc),
                        },
                    )

                except Exception as exc:
                    self.log.error("WS", f"- Message processing error: {exc}")
                    sent = await self.send_to_connection(
                        websocket,
                        {
                            "status": "error",
                            "errMsg": str(exc),
                        },
                    )
                    if not sent:
                        break

        except Exception as exc:
            self.log.error("WS", f"- Unexpected connection error: {exc}")

        finally:
            await self.destroy(websocket)

    async def receive_and_respond(self, websocket: WebSocket, processor) -> None:
        """기존 호출부 호환용 process 별칭입니다."""
        await self.process(websocket, processor)

    # ------------------------------------------------------------------
    # lifecycle: destroy
    # ------------------------------------------------------------------
    async def destroy(
        self,
        websocket: WebSocket,
        *,
        close: bool = False,
        code: int = 1000,
    ) -> None:
        """WebSocket을 필요 시 닫고 모든 내부 등록 정보를 제거합니다."""
        if close and websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=code)
            except Exception as exc:
                self.log.warning(
                    "WS",
                    f"- Failed to close connection {websocket.client}: {exc}",
                )

        self._unregister(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """기존 동기 호출부 호환용 정리 메서드입니다."""
        self._unregister(websocket)

    async def disconnect_all(self) -> None:
        """서버 종료 시 모든 연결을 destroy합니다."""
        self.log.info("WS", "- Destroying all websocket connections...")

        for websocket in list(self.active_connections):
            await self.destroy(websocket, close=True, code=1001)

    # ------------------------------------------------------------------
    # send
    # ------------------------------------------------------------------
    async def send_to_connection(self, websocket: WebSocket, message: dict) -> bool:
        """단일 WebSocket으로 전송하고 실패한 연결은 즉시 정리합니다."""
        if not self._is_sendable(websocket):
            await self.destroy(websocket)
            return False

        try:
            await websocket.send_json(message)
            return True
        except Exception as exc:
            self.log.warning(
                "WS",
                (
                    f"- Send failed: sid={getattr(websocket, '_sid', None)}, "
                    f"connection_id={getattr(websocket, '_connection_id', None)}, "
                    f"error={exc}"
                ),
            )
            await self.destroy(websocket)
            return False

    async def broadcast_to_session(
        self,
        sid: str,
        message: dict,
        exclude_sender: WebSocket | None = None,
    ) -> int:
        """
        같은 sid의 현재 활성 연결에 메시지를 전송합니다.

        연결이 이미 끊어진 클라이언트는 전송 실패 시 destroy됩니다.
        Redis 백업이나 재전송 큐는 사용하지 않습니다.

        :return: 전송에 성공한 연결 수
        """
        connections = list(self.session_map.get(sid, []))
        if not connections:
            self.log.warning("WS", f"- No active connection for sid={sid}")
            return 0

        sent_count = 0
        for websocket in connections:
            if exclude_sender is websocket:
                continue

            if await self.send_to_connection(websocket, message):
                sent_count += 1

        return sent_count

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _normalize_message(self, websocket: WebSocket, message: dict) -> str | None:
        header = message.get("hd")
        if not isinstance(header, dict):
            header = {}

        sid = header.get("sid") or getattr(websocket, "_sid", None)
        role = header.get("role", "user")

        header["asker"] = role
        if sid:
            header["sid"] = sid
            message.setdefault("sid", sid)

        message["hd"] = header
        return sid

    def _is_registered(self, websocket: WebSocket) -> bool:
        return bool(getattr(websocket, "_ws_registered", False))

    def _is_sendable(self, websocket: WebSocket) -> bool:
        return (
            self._is_registered(websocket)
            and websocket.application_state == WebSocketState.CONNECTED
            and websocket.client_state == WebSocketState.CONNECTED
        )

    def _unregister(self, websocket: WebSocket) -> None:
        """여러 번 호출되어도 안전한 idempotent 정리 함수입니다."""
        if not getattr(websocket, "_ws_registered", False):
            return

        setattr(websocket, "_ws_registered", False)

        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        sid = getattr(websocket, "_sid", None)
        connection_id = getattr(websocket, "_connection_id", None)

        if sid:
            connections = self.session_map.get(sid)
            if connections and websocket in connections:
                connections.remove(websocket)

            if connections is not None and not connections:
                self.session_map.pop(sid, None)
                self.log.info("WS", f"- Session removed: sid={sid}")

        self.log.info(
            "WS",
            (
                f"- Connection destroyed: sid={sid}, "
                f"connection_id={connection_id}, client={websocket.client}"
            ),
        )