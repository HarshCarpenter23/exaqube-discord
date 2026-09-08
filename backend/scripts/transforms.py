"""Pure CSV-row transforms for the loader.

Kept free of any database or app imports so the coercion and column mapping can
be unit-tested on their own (see tests), and so the bug-prone part of the load
— matching CSV columns and coercing types — is isolated and easy to read.
"""

from __future__ import annotations

from datetime import date, datetime

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def clean(value: str | None) -> str | None:
    """Empty / whitespace-only strings become None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def to_bool(value: str | None) -> bool | None:
    v = clean(value)
    if v is None:
        return None
    return v.lower() in ("true", "1", "t", "yes")


def to_int(value: str | None) -> int | None:
    v = clean(value)
    if v is None:
        return None
    # A few numeric fields arrive as floats (e.g. "3600.0"); handle both.
    return int(float(v))


def to_ts(value: str | None) -> datetime | None:
    v = clean(value)
    return datetime.strptime(v, TS_FORMAT) if v else None


def to_date(value: str | None) -> date | None:
    v = clean(value)
    return datetime.strptime(v, "%Y-%m-%d").date() if v else None


# --- per-table row builders (CSV dict -> column dict) -----------------------

def server_row(r: dict) -> dict:
    return {
        "server_id": r["server_id"],
        "server_name": r["server_name"],
        "owner_id": clean(r.get("owner_id")),
        "creation_date": to_ts(r.get("creation_date")),
        "region": clean(r.get("region")),
        "verification_level": to_int(r.get("verification_level")),
        "premium_tier": to_int(r.get("premium_tier")),
        "premium_subscription_count": to_int(r.get("premium_subscription_count")),
        "approximate_member_count": to_int(r.get("approximate_member_count")),
        "approximate_presence_count": to_int(r.get("approximate_presence_count")),
    }


def channel_row(r: dict) -> dict:
    return {
        "channel_id": r["channel_id"],
        "server_id": r["server_id"],
        "channel_name": clean(r.get("channel_name")),
        "channel_type": clean(r.get("channel_type")),
        "topic": clean(r.get("topic")),
        "nsfw": to_bool(r.get("nsfw")),
        "rate_limit_per_user": to_int(r.get("rate_limit_per_user")),
        "position": to_int(r.get("position")),
    }


def member_row(r: dict) -> dict:
    return {
        "server_id": r["server_id"],
        "user_id": r["user_id"],
        "username": clean(r.get("username")),
        "display_name": clean(r.get("display_name")),
        "discriminator": clean(r.get("discriminator")),
        "is_bot": to_bool(r.get("is_bot")) or False,
        "join_date": to_ts(r.get("join_date")),
        "last_active": to_ts(r.get("last_active")),
        "roles": clean(r.get("roles")),
        "messages_sent": to_int(r.get("messages_sent")),
        "voice_minutes": to_int(r.get("voice_minutes")),
        "is_owner": to_bool(r.get("is_owner")),
    }


def message_row(r: dict) -> dict:
    return {
        "message_id": r["message_id"],
        "server_id": r["server_id"],
        "channel_id": r["channel_id"],
        "user_id": r["user_id"],
        "ts": to_ts(r.get("timestamp")),
        "content": r.get("content"),
        "has_attachment": to_bool(r.get("has_attachment")),
        "has_embed": to_bool(r.get("has_embed")),
        "reaction_count": to_int(r.get("reaction_count")),
        "is_pinned": to_bool(r.get("is_pinned")),
        "length": to_int(r.get("length")),
    }


def daily_stat_row(r: dict) -> dict:
    return {
        "server_id": r["server_id"],
        "day": to_date(r.get("date")),
        "total_messages": to_int(r.get("total_messages")),
        "new_members": to_int(r.get("new_members")),
        "active_members": to_int(r.get("active_members")),
        "total_members": to_int(r.get("total_members")),
        "day_of_week": to_int(r.get("day_of_week")),
        "is_weekend": to_bool(r.get("is_weekend")),
    }


def channel_daily_stat_row(r: dict) -> dict:
    return {
        "channel_id": r["channel_id"],
        "server_id": r["server_id"],
        "day": to_date(r.get("date")),
        "message_count": to_int(r.get("message_count")),
        "active_users": to_int(r.get("active_users")),
    }
