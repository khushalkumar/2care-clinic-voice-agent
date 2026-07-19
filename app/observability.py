import json
import logging

LOGGER = logging.getLogger("voice_agent.http")


def log_http_request(
    *, request_id: str, method: str, path: str, status_code: int, duration_ms: float
) -> None:
    LOGGER.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
            separators=(",", ":"),
        )
    )
