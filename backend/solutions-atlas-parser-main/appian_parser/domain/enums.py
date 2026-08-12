"""Domain enums for the appian parser."""
from enum import Enum


class DependencyTypeEnum(Enum):
    """Dependency types."""
    CALLS = "CALLS"
    USES_CONSTANT = "USES_CONSTANT"
    USES_CDT = "USES_CDT"
    USES_RECORD_TYPE = "USES_RECORD_TYPE"
    USES_INTEGRATION = "USES_INTEGRATION"
    USES_CONNECTED_SYSTEM = "USES_CONNECTED_SYSTEM"
    USES_GROUP = "USES_GROUP"
    USES_SITE = "USES_SITE"