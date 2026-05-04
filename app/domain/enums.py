from enum import StrEnum


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class GitHubSourceType(StrEnum):
    RELEASES = "releases"
    FILE = "file"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class UpdateType(StrEnum):
    RELEASE = "release"
    FILE_CHANGE = "file_change"


class SummaryStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
