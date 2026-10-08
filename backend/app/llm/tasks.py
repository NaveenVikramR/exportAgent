from enum import StrEnum


class Tier(StrEnum):
    NANO = "nano"
    SUPER = "super"
    ULTRA = "ultra"


class TaskType(StrEnum):
    CLASSIFY = "classify"
    EXTRACT = "extract"
    # one field re-extracted after a Python validation check failed on Nano's answer
    EXTRACT_ESCALATION = "extract_escalation"
    CHANGE_DETECTION = "change_detection"
    DRAFT_REPLY = "draft_reply"
    DRAFT_INTERNAL_NOTE = "draft_internal_note"
    RISK_REASONING = "risk_reasoning"
    PLANNING = "planning"


# The routing table: high-volume structured work on Nano, writing and escalated
# re-extraction on Super, reasoning and planning on Ultra. Overridable per task from the environment.
DEFAULT_TASK_TIERS: dict[TaskType, Tier] = {
    TaskType.CLASSIFY: Tier.NANO,
    TaskType.EXTRACT: Tier.NANO,
    TaskType.EXTRACT_ESCALATION: Tier.SUPER,
    TaskType.CHANGE_DETECTION: Tier.NANO,
    TaskType.DRAFT_REPLY: Tier.SUPER,
    TaskType.DRAFT_INTERNAL_NOTE: Tier.SUPER,
    TaskType.RISK_REASONING: Tier.ULTRA,
    TaskType.PLANNING: Tier.ULTRA,
}
