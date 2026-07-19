import json
from typing import Any

from app.infrastructure.queue.sqs import SqsPublisher


class FakeSqsClient:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def send_message(self, **kwargs: Any) -> dict[str, str]:
        self.request = kwargs
        return {"MessageId": "message-1"}


async def test_sqs_message_contains_stable_event_envelope() -> None:
    client = FakeSqsClient()
    publisher = SqsPublisher(client, queue_url="https://sqs.example/jobs")

    await publisher.publish("event-1", "booking.confirmed", {"operation_id": "operation-1"})

    assert client.request is not None
    assert client.request["QueueUrl"] == "https://sqs.example/jobs"
    assert json.loads(client.request["MessageBody"]) == {
        "event_id": "event-1",
        "event_type": "booking.confirmed",
        "payload": {"operation_id": "operation-1"},
        "schema_version": 1,
    }
