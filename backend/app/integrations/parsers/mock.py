import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas.ai import Extraction, ScheduleProposal

from .base import ParseOutcome
from .privacy import redact, unsafe_instruction


def explicit_time(text: str, reference: datetime, timezone: str) -> datetime | None:
    zone = ZoneInfo(timezone)
    match = re.search(
        r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})(?::(?P<second>\d{2}))?(?P<offset>Z|[+-]\d{2}:\d{2})?", text
    )
    if match:
        suffix = match.group("offset") or ""
        value = datetime.fromisoformat(
            f"{match.group(1)}T{int(match.group(2)):02}:{match.group(3)}:{match.group('second') or '00'}"
            + suffix.replace("Z", "+00:00")
        )
        return value if value.tzinfo else value.replace(tzinfo=zone)
    relative = re.search(
        r"(明天|后天)(?:上午|下午|晚上)?\s*(\d{1,2}|[一二三四五六七八九十两]{1,3})(?::(\d{2})|点)", text
    )
    if relative:
        day = reference.astimezone(zone).date() + timedelta(days=1 if relative.group(1) == "明天" else 2)
        digits = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "十一": 11,
            "十二": 12,
        }
        hour = int(relative.group(2)) if relative.group(2).isdigit() else digits.get(relative.group(2), -1)
        if ("下午" in relative.group(0) or "晚上" in relative.group(0)) and 1 <= hour < 12:
            hour += 12
        return datetime(day.year, day.month, day.day, hour, int(relative.group(3) or 0), tzinfo=zone)
    return None


class MockParser:
    provider = "mock"

    async def parse(self, text: str, reference_time: datetime, timezone: str) -> ParseOutcome:
        text = redact(text).strip()
        if unsafe_instruction(text):
            return ParseOutcome(
                Extraction(intent="unknown", ambiguities=["UNSAFE_INSTRUCTION"], should_confirm=True),
                error_code="UNSAFE_INSTRUCTION",
            )
        creating = re.fullmatch(r"(?:新增|添加)([^，,\s]{1,20})[，,\s]*(?:应聘|申请)([^，,\s]{2,40})", text)
        if creating:
            return ParseOutcome(
                Extraction(
                    intent="create_application",
                    candidate_name=creating.group(1),
                    position_name=creating.group(2),
                    source_spans={"candidate_name": creating.group(1), "position_name": creating.group(2)},
                )
            )
        code = re.search(r"(?<![A-Za-z0-9_])(A[A-Z0-9_-]{3,39})(?![A-Za-z0-9_])", text, re.I)
        name = None if code else re.match(r"([^，,\s]{1,20}?)(?:一面|初试|二面|复试|安排|进入)", text)
        proposal = Extraction(
            intent="unknown",
            application_code=code.group(1).upper() if code else None,
            candidate_name=name.group(1) if name else None,
        )
        if code:
            proposal.source_spans["application_code"] = code.group(1)
        result = re.search(r"(一面|初试|二面|复试)(未通过|不通过|通过|过了)", text)
        scheduling = bool(
            re.search(
                r"(?:安排|预约).{0,30}(?:一面|初试|二面|复试)|(?:一面|初试|二面|复试).{0,20}(?:时间|安排)",
                text,
            )
        )
        # A compound result + next-round appointment is represented explicitly.
        has_schedule = scheduling or (
            result is not None
            and bool(re.search(r"(?:明天|后天|\d{4}-\d{2}-\d{2}|周[一二三四五六日天]).*(?:二面|复试)", text))
        )
        try:
            when = explicit_time(text, reference_time, timezone) if has_schedule else None
        except (ValueError, KeyError):
            return ParseOutcome(
                Extraction(
                    intent="schedule_interview",
                    application_code=proposal.application_code,
                    should_confirm=True,
                    ambiguities=["INVALID_TIME"],
                ),
                error_code="INVALID_TIME",
            )
        interviewer_match = re.search(
            r"面试官[：:\s]*([^，,\s]{1,20})|[，,\s]([^，,\s]{1,20})(?:主持|面试)$", text
        )
        interviewer = next((v for v in interviewer_match.groups() if v), None) if interviewer_match else None
        if result:
            proposal.intent = "record_result"
            proposal.interview_round = 1 if result.group(1) in {"一面", "初试"} else 2
            proposal.interview_result = "failed" if result.group(2) in {"未通过", "不通过"} else "passed"
            if has_schedule:
                proposal.next_interview = ScheduleProposal(
                    round=proposal.interview_round + 1, scheduled_at=when, interviewer=interviewer
                )
        elif has_schedule:
            proposal.intent = "schedule_interview"
            proposal.interview_round = 2 if re.search(r"二面|复试", text) else 1
            proposal.scheduled_at = when
            proposal.interviewer = interviewer
        else:
            stage = next(
                (
                    value
                    for phrase, value in [
                        ("进入筛选", "screening"),
                        ("进入一面", "interview_1"),
                        ("进入二面", "interview_2"),
                        ("进入Offer", "offer"),
                        ("录用", "hired"),
                        ("淘汰", "rejected"),
                    ]
                    if phrase in text
                ),
                None,
            )
            if stage:
                from app.domain import Stage

                proposal.intent = "update_stage"
                proposal.stage = Stage(stage)
        if proposal.intent == "unknown":
            proposal.ambiguities.append("UNKNOWN_INTENT")
        if len(re.findall(r"(?:一面|初试|二面|复试)(?:未通过|不通过|通过|过了)", text)) > 1:
            proposal.ambiguities.append("MULTIPLE_RESULTS")
        if len(set(re.findall(r"(?<![A-Za-z0-9_])A[A-Z0-9_-]{3,39}(?![A-Za-z0-9_])", text, re.I))) > 1:
            proposal.ambiguities.append("MULTIPLE_APPLICATIONS")
        if has_schedule and when is None:
            proposal.missing_fields.append("scheduled_at")
        if has_schedule and interviewer is None:
            proposal.missing_fields.append("interviewer")
        if proposal.application_code is None:
            proposal.ambiguities.append("APPLICATION_ID_REQUIRED")
        proposal.should_confirm = bool(proposal.missing_fields or proposal.ambiguities)
        return ParseOutcome(proposal)
