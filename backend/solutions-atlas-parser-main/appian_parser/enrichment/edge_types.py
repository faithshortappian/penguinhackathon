"""Edge type definitions for process model flows."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class EdgeType(Enum):
    """Types of edges in process model flow graphs."""
    
    SEQUENCE = "sequence"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    SUBPROCESS_CALL = "subprocess_call"
    USER_INPUT_TASK = "user_input_task"
    APPROVAL_TASK = "approval_task"
    INTEGRATION_CALL = "integration_call"
    WRITE_TO_RECORD = "write_to_record"
    QUERY_RECORD = "query_record"
    EXCEPTION_FLOW = "exception_flow"
    END_EVENT = "end_event"


@dataclass(frozen=True)
class EdgeMetadata:
    """Additional metadata for typed edges."""
    
    condition: Optional[str] = None
    gateway_type: Optional[str] = None
    target_process: Optional[str] = None
    integration_name: Optional[str] = None
    record_type: Optional[str] = None
    form_uuid: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}
