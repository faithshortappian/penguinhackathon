"""Data models for enriched Appian objects."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class TypedEdge:
    """A typed edge in a process model flow graph."""
    
    from_node: str
    to_node: str
    edge_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'from': self.from_node,
            'to': self.to_node,
            'type': self.edge_type,
            'metadata': self.metadata,
        }


@dataclass
class CriticalPaths:
    """Critical paths through a process model."""
    
    longest_path: List[str] = field(default_factory=list)
    most_nodes_path: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'longest_path': self.longest_path,
            'most_nodes_path': self.most_nodes_path,
        }


@dataclass
class EnrichedFlow:
    """Enriched flow graph for a process model."""
    
    nodes: List[Dict[str, Any]]
    edges: List[TypedEdge]
    critical_paths: CriticalPaths
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'nodes': self.nodes,
            'edges': [e.to_dict() for e in self.edges],
            'critical_paths': self.critical_paths.to_dict(),
        }


@dataclass
class BundleStatistics:
    """Statistics for a bundle."""
    
    total_objects: int = 0
    object_counts: Dict[str, int] = field(default_factory=dict)
    total_nodes: int = 0
    total_edges: int = 0
    integration_count: int = 0
    subprocess_count: int = 0
    user_task_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.__dict__.copy()


@dataclass
class ObjectStatistics:
    """Statistics for an individual object."""
    
    dependency_count: int = 0
    dependent_count: int = 0
    complexity_score: Optional[float] = None
    node_count: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EnrichedBundle:
    """Enriched bundle with metadata and statistics."""
    
    bundle_id: str
    tags: List[str] = field(default_factory=list)
    statistics: BundleStatistics = field(default_factory=BundleStatistics)
    enriched_flow: Optional[EnrichedFlow] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'bundle_id': self.bundle_id,
            'tags': self.tags,
            'statistics': self.statistics.to_dict(),
        }
        if self.enriched_flow is not None:
            result['enriched_flow'] = self.enriched_flow.to_dict()
        return result


@dataclass
class ObjectEnrichment:
    """Enrichment data for an individual object."""
    
    uuid: str
    dependency_depth: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    statistics: ObjectStatistics = field(default_factory=ObjectStatistics)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'uuid': self.uuid,
            'tags': self.tags,
            'statistics': self.statistics.to_dict(),
        }
        if self.dependency_depth is not None:
            result['dependency_depth'] = self.dependency_depth
        return result
