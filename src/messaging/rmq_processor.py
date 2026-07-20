from src.messaging.event_dispatcher_utils import dispatch_event

async def processor(ctx, msg, queue_name: str = "unknown"):
    event = msg.get("hd", {}).get("event")  
    return await dispatch_event(
        ctx,
        event=event,
        source_type="rmq",
        queue_name=queue_name,
        msg=msg
    )
