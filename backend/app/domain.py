from enum import StrEnum


class Role(StrEnum):
    HR = "HR"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class Stage(StrEnum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW_1 = "interview_1"
    INTERVIEW_2 = "interview_2"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SyncState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    MOCK_SYNCED = "mock_synced"
    SYNCED = "synced"
    FAILED = "failed"
    DEAD = "dead"
    SUPERSEDED = "superseded"


class Outcome(StrEnum):
    PENDING = "pending"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


TERMINAL_STAGES = {Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN}
FORWARD_STAGES = {
    Stage.APPLIED: {Stage.SCREENING},
    Stage.SCREENING: {Stage.INTERVIEW_1},
    Stage.INTERVIEW_1: {Stage.INTERVIEW_2},
    Stage.INTERVIEW_2: {Stage.OFFER},
    Stage.OFFER: {Stage.HIRED},
}


def transition_requires_confirmation(current: Stage, target: Stage) -> bool:
    return current != target and current in TERMINAL_STAGES


def transition_allowed(current: Stage, target: Stage) -> bool:
    if current == target:
        return True
    if current in TERMINAL_STAGES:
        return False
    return target in FORWARD_STAGES.get(current, set()) or target in {Stage.REJECTED, Stage.WITHDRAWN}
