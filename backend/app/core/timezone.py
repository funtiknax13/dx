from zoneinfo import ZoneInfo

# The community is Cheboksary-only — every event/group time is a Cheboksary
# wall-clock time, and every viewer must see that same number regardless of
# their own browser's timezone. Russia hasn't observed DST since 2014, so
# this is a fixed UTC+3, but ZoneInfo keeps it correct if that ever changes
# rather than hardcoding the offset.
EVENT_TZ = ZoneInfo("Europe/Moscow")
