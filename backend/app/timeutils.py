from datetime import datetime, timezone


def agora_utc() -> datetime:
    """SQLModel 0.0.46+ exige datetime timezone-aware (rejeita datetime.utcnow())."""
    return datetime.now(timezone.utc)
