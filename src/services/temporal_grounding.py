from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
import re


class TemporalGrounding:
    """
    Conservative temporal grounding service for Synapse expectations.
    
    Rule Set:
    1. Grounding MUST respect explicitly passed `now` and IANA `timezone_str`.
    2. Explicit supported expressions ("today", "tonight", "tomorrow", "tomorrow morning", 
       named weekdays, "by 5pm Friday") are converted to expected windows / hard deadlines in UTC.
    3. Unresolved relational phrases ("after the Miami trip", "when Ashley gets back") 
       MUST remain ungrounded (None, None, None) while preserving `raw_temporal_phrase`.
    """

    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    def ground_expression(
        self,
        raw_phrase: Optional[str],
        now: datetime,
        timezone_str: str = "UTC",
    ) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        """
        Grounds a temporal expression string against reference `now` + `timezone_str`.

        Returns:
            Tuple of (expected_window_start, expected_window_end, hard_deadline_at) in UTC.
        """
        if not raw_phrase or not raw_phrase.strip():
            return None, None, None

        phrase = raw_phrase.strip().lower()

        # Resolve local timezone
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            return None, None, None

        # Normalize reference now to local timezone
        if now.tzinfo is None:
            local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        else:
            local_now = now.astimezone(tz)

        local_today = local_now.date()

        if phrase == "now":
            start = local_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            return start, start + timedelta(hours=2), None

        if phrase in ("later", "later today"):
            start_local = local_now + timedelta(hours=1)
            end_local = datetime.combine(local_today, time(23, 59, 59), tzinfo=tz)
            if start_local >= end_local:
                start_local = local_now
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        if phrase in ("this week", "for a few days", "for a few days"):
            days = (6 - local_today.weekday()) if phrase == "this week" else 3
            end_date = local_today + timedelta(days=max(1, days))
            start_local = datetime.combine(local_today, time(0, 0), tzinfo=tz)
            end_local = datetime.combine(end_date, time(23, 59, 59), tzinfo=tz)
            return (start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None), end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None), None)

        if phrase == "next week":
            start_date = local_today + timedelta(days=(7 - local_today.weekday()))
            end_date = start_date + timedelta(days=6)
            return (
                datetime.combine(start_date, time(0, 0), tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                datetime.combine(end_date, time(23, 59, 59), tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        if phrase.startswith("until "):
            phrase = phrase[6:]

        # 1. Unresolved relational phrases -> return (None, None, None)
        if any(rel in phrase for rel in ["after ", "when ", "once ", "until ", "as soon as"]):
            # Check if it has a groundable phrase embedded like "after 5pm Friday" vs "after Miami trip"
            if not re.search(r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(:\d{2})?\s*(am|pm))\b", phrase):
                return None, None, None

        # 2. Hard deadline phrases: e.g. "by 5pm friday", "by 5pm today", "by 5pm"
        by_time_match = re.search(r"by\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)(?:\s+(on\s+)?(\w+))?", phrase)
        if by_time_match:
            hour = int(by_time_match.group(1))
            minute = int(by_time_match.group(2)) if by_time_match.group(2) else 0
            ampm = by_time_match.group(3)
            day_spec = by_time_match.group(5)

            if not day_spec and local_now.time() > time(hour % 12 + (12 if ampm == "pm" else 0), minute):
                return None, None, None

            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0

            target_date = local_today
            if day_spec:
                day_spec = day_spec.lower()
                if day_spec == "tomorrow":
                    target_date = local_today + timedelta(days=1)
                elif day_spec in self.WEEKDAYS:
                    target_weekday = self.WEEKDAYS[day_spec]
                    days_ahead = (target_weekday - local_today.weekday()) % 7
                    if days_ahead == 0 and local_now.time() > time(hour, minute):
                        days_ahead = 7
                    target_date = local_today + timedelta(days=days_ahead)

            deadline_local = datetime.combine(target_date, time(hour, minute), tzinfo=tz)
            deadline_utc = deadline_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            window_start_local = datetime.combine(target_date, time(0, 0), tzinfo=tz)
            window_start_utc = window_start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            return window_start_utc, deadline_utc, deadline_utc

        # 3. Today & Tonight
        if phrase == "today":
            start_local = datetime.combine(local_today, time(0, 0, 0), tzinfo=tz)
            end_local = datetime.combine(local_today, time(23, 59, 59), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        if phrase in ("tonight", "this evening"):
            start_local = datetime.combine(local_today, time(18, 0, 0), tzinfo=tz)
            end_local = datetime.combine(local_today, time(23, 59, 59), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        # 4. Tomorrow variations
        if phrase == "tomorrow":
            tomorrow_date = local_today + timedelta(days=1)
            start_local = datetime.combine(tomorrow_date, time(0, 0, 0), tzinfo=tz)
            end_local = datetime.combine(tomorrow_date, time(23, 59, 59), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        # "tomorrow morning at 9" / "tomorrow at 9am" - daypart + explicit clock time
        daypart_time_match = re.search(
            r"\b(tomorrow|today)\s+(?:morning\s+)?at\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b",
            phrase, re.IGNORECASE)
        if daypart_time_match:
            day_word, hour_s, minute_s, ampm = daypart_time_match.groups()
            hour = int(hour_s) % 12 + (12 if ampm == "pm" else 0)
            minute = int(minute_s) if minute_s else 0
            target_date = local_today + (timedelta(days=1) if day_word == "tomorrow" else timedelta(0))
            start_local = datetime.combine(target_date, time(hour, minute), tzinfo=tz)
            end_local = datetime.combine(target_date, time(min(hour + 3, 23), 59), tzinfo=tz)
            return (start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                    end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                    end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None))

        if phrase == "tomorrow morning":
            tomorrow_date = local_today + timedelta(days=1)
            start_local = datetime.combine(tomorrow_date, time(6, 0, 0), tzinfo=tz)
            end_local = datetime.combine(tomorrow_date, time(12, 0, 0), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        if phrase == "tomorrow afternoon":
            tomorrow_date = local_today + timedelta(days=1)
            start_local = datetime.combine(tomorrow_date, time(12, 0, 0), tzinfo=tz)
            end_local = datetime.combine(tomorrow_date, time(17, 0, 0), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        if phrase == "tomorrow evening":
            tomorrow_date = local_today + timedelta(days=1)
            start_local = datetime.combine(tomorrow_date, time(17, 0, 0), tzinfo=tz)
            end_local = datetime.combine(tomorrow_date, time(23, 59, 59), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        # 5. Named Weekdays: e.g. "friday", "this friday", "next friday"
        weekday_match = re.search(r"\b(this\s+|next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", phrase)
        if weekday_match:
            modifier = weekday_match.group(1).strip() if weekday_match.group(1) else ""
            target_day_name = weekday_match.group(2)
            target_weekday = self.WEEKDAYS[target_day_name]

            days_ahead = (target_weekday - local_today.weekday()) % 7
            if days_ahead == 0 and modifier != "this":
                days_ahead = 7
            if modifier == "next" and days_ahead < 7:
                days_ahead += 7

            target_date = local_today + timedelta(days=days_ahead)
            start_local = datetime.combine(target_date, time(0, 0, 0), tzinfo=tz)
            end_local = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)
            return (
                start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                None,
            )

        # Default fallback for ungroundable phrases
        return None, None, None
