import asyncio
import json
from typing import Any, Protocol


class SqsClient(Protocol):
    def send_message(self, **kwargs: Any) -> dict[str, Any]: ...


class SqsPublisher:
    def __init__(self, client: SqsClient, *, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url

    async def publish(self, event_id: str, event_type: str, payload: dict[str, object]) -> None:
        body = json.dumps(
            {
                "schema_version": 1,
                "event_id": event_id,
                "event_type": event_type,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        await asyncio.to_thread(
            self._client.send_message, QueueUrl=self._queue_url, MessageBody=body
        )
