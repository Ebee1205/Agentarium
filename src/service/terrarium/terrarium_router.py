from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket

from src.common.responses import ResponseStatus
from src.common.ws_responses import (
    MessageSender,
    build_ws_error_response,
    build_ws_success_response,
)
from src.service.terrarium.terrarium_schema import (
    CreateSimulationRequest,
    ObserverInterventionRequest,
    model_to_dict,
)

router = APIRouter(tags=["terrarium"])


def _manager_from(target: Any):
    ctx = getattr(target.app.state, "ctx", None)
    if ctx is None or getattr(ctx, "simulation_manager", None) is None:
        raise RuntimeError("Terrarium managers are not initialized")
    return ctx, ctx.simulation_manager


@router.post("/api/v1/terrarium")
async def create_terrarium(request: Request, body: CreateSimulationRequest):
    _, manager = _manager_from(request)
    try:
        state = await manager.create(body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"data": model_to_dict(state)}


@router.get("/api/v1/terrarium/{simulation_id}")
async def get_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    try:
        return {"data": manager.snapshot(simulation_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/terrarium/{simulation_id}/start")
async def start_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    state = await manager.start(simulation_id)
    return {"data": model_to_dict(state)}


@router.post("/api/v1/terrarium/{simulation_id}/pause")
async def pause_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    try:
        state = await manager.pause(simulation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"data": model_to_dict(state)}


@router.post("/api/v1/terrarium/{simulation_id}/resume")
async def resume_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    state = await manager.start(simulation_id, resumed=True)
    return {"data": model_to_dict(state)}


@router.post("/api/v1/terrarium/{simulation_id}/stop")
async def stop_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    try:
        state = await manager.stop(simulation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"data": model_to_dict(state)}


@router.post("/api/v1/terrarium/{simulation_id}/tick")
async def tick_terrarium(request: Request, simulation_id: str):
    _, manager = _manager_from(request)
    state = await manager.run_tick(simulation_id)
    return {"data": model_to_dict(state)}


@router.get("/api/v1/terrarium/{simulation_id}/events")
async def get_events(
    request: Request,
    simulation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
):
    ctx, manager = _manager_from(request)
    try:
        manager.get(simulation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"data": ctx.event_manager.list_events(simulation_id, limit=limit)}


@router.get("/api/v1/terrarium/{simulation_id}/timeline")
async def get_timeline(
    request: Request,
    simulation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
):
    ctx, manager = _manager_from(request)
    try:
        manager.get(simulation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"data": ctx.timeline_service.list_items(simulation_id, limit=limit)}


@router.post("/api/v1/terrarium/{simulation_id}/interventions")
async def intervene_terrarium(
    request: Request,
    simulation_id: str,
    body: ObserverInterventionRequest,
):
    _, manager = _manager_from(request)
    await manager.intervene(
        simulation_id,
        summary=body.summary,
        data=body.data,
    )
    return {"data": {"accepted": True}}


async def terrarium_ws_processor(ctx, websocket: WebSocket, message: dict) -> dict:
    header = message.get("hd", {})
    body = message.get("bd", {})
    data = body.get("data", {}) if isinstance(body, dict) else {}
    event_type = str(header.get("type", "")).upper()
    simulation_id = header.get("sid") or getattr(websocket, "_sid", None)
    request_mid = header.get("mid")

    if event_type == "PING":
        return build_ws_success_response(
            event_type="PONG",
            sid=simulation_id,
            sender=MessageSender.AUTO,
            data={"request_mid": request_mid},
        )

    manager = ctx.simulation_manager
    try:
        if event_type == "SIMULATION_START":
            state = await manager.start(simulation_id)
        elif event_type == "SIMULATION_PAUSE":
            state = await manager.pause(simulation_id)
        elif event_type == "SIMULATION_RESUME":
            state = await manager.start(simulation_id, resumed=True)
        elif event_type == "SIMULATION_STOP":
            state = await manager.stop(simulation_id)
        elif event_type == "RUN_TICK":
            state = await manager.run_tick(simulation_id)
        elif event_type == "GET_STATE":
            state = await manager.ensure(simulation_id)
        elif event_type == "OBSERVER_INTERVENTION":
            summary = data.get("summary") if isinstance(data, dict) else None
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError("bd.data.summary is required")
            await manager.intervene(
                simulation_id,
                summary=summary.strip(),
                data=data.get("data", {}),
            )
            state = manager.get(simulation_id)
        else:
            return build_ws_error_response(
                event_type="TERRARIUM_ERROR",
                sid=simulation_id,
                sender=MessageSender.AUTO,
                status=ResponseStatus.BAD_REQUEST,
                data={
                    "reason": f"Unsupported event type: {event_type}",
                    "request_mid": request_mid,
                },
            )
    except (KeyError, ValueError) as exc:
        return build_ws_error_response(
            event_type="TERRARIUM_ERROR",
            sid=simulation_id,
            sender=MessageSender.AUTO,
            status=ResponseStatus.BAD_REQUEST,
            data={"reason": str(exc), "request_mid": request_mid},
        )

    return build_ws_success_response(
        event_type="SIMULATION_STATE",
        sid=simulation_id,
        sender=MessageSender.AUTO,
        data={
            "simulation": model_to_dict(state),
            "request_mid": request_mid,
        },
    )


@router.websocket("/ws/terrarium/{simulation_id}")
async def terrarium_websocket(websocket: WebSocket, simulation_id: str) -> None:
    ctx = getattr(websocket.app.state, "ctx", None)
    if ctx is None or getattr(ctx, "ws_handler", None) is None:
        await websocket.close(code=1011, reason="AppContext is not initialized")
        return

    handler = ctx.ws_handler
    try:
        connection_id = await handler.init(websocket, sid=simulation_id)
        state = await ctx.simulation_manager.ensure(simulation_id)
        connected = build_ws_success_response(
            event_type="SESSION_CONNECTED",
            sid=simulation_id,
            sender=MessageSender.AUTO,
            data={
                "connection_id": connection_id,
                "simulation": model_to_dict(state),
                "recent_events": ctx.event_manager.list_events(
                    simulation_id,
                    limit=20,
                ),
                "recent_timeline": ctx.timeline_service.list_items(
                    simulation_id,
                    limit=20,
                ),
            },
        )
        if not await handler.send_to_connection(websocket, connected):
            return
        await handler.process(websocket, terrarium_ws_processor)
    except Exception as exc:
        logger = getattr(ctx, "log", None)
        if logger:
            try:
                logger.error(f"[ATM] websocket router error: {exc}")
            except TypeError:
                logger.error("ATM", f"websocket router error: {exc}")
        await handler.destroy(websocket, close=True, code=1011)
