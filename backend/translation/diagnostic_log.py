"""Local diagnostic records with no keys, prompts or translation content."""
from datetime import datetime, timezone
import json
from pathlib import Path


def save_attempt(outcome, model, destination=None):
    path = Path(destination) if destination else Path(__file__).resolve().parents[2] / "experiments/runtime_logs/translation_attempts.jsonl"
    record = {"time_utc": datetime.now(timezone.utc).isoformat(), "phase": outcome.phase,
        "provider": outcome.provider, "model": model, "status": outcome.status,
        "error_code": outcome.error_code, "latency_ms": outcome.latency_ms, "diagnostic": outcome.diagnostic}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # Logging must not turn a successful provider response into a failure.
        pass
    return record
