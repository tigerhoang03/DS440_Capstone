import json
import orjson
from typing import Iterable
from redis.asyncio import Redis
from ..config import settings
from ..models.schema import NormalizedItem

def _dumps(obj) -> str:
    return orjson.dumps(obj).decode("utf-8")

def _loads(s: str):
    return json.loads(s)

async def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)

async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(settings.REDIS_STREAM, settings.REDIS_CONSUMER_GROUP, id="0-0", mkstream=True)
    except Exception as e:
        # group exists
        if "BUSYGROUP" not in str(e):
            raise

async def publish_items(redis: Redis, items: Iterable[NormalizedItem]) -> int:
    n = 0
    for item in items:
        payload = _dumps(item.model_dump())
        await redis.xadd(settings.REDIS_STREAM, {"payload": payload}, maxlen=100000, approximate=True)
        n += 1
    return n

async def read_batch(redis: Redis, count: int = 100, block_ms: int = 2000):
    await ensure_group(redis)
    res = await redis.xreadgroup(
        groupname=settings.REDIS_CONSUMER_GROUP,
        consumername=settings.REDIS_CONSUMER_NAME,
        streams={settings.REDIS_STREAM: ">"},
        count=count,
        block=block_ms,
    )
    # res: [(stream, [(id, {payload:..}), ...])]
    out = []
    for _, msgs in res:
        for msg_id, fields in msgs:
            out.append((msg_id, fields.get("payload")))
    return out

async def ack(redis: Redis, msg_ids: list[str]) -> None:
    if msg_ids:
        await redis.xack(settings.REDIS_STREAM, settings.REDIS_CONSUMER_GROUP, *msg_ids)
