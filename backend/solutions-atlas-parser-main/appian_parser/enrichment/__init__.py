"""
Data enrichment layer for parsed Appian objects.

This module provides deterministic enrichment of parsed Appian objects,
adding structured metadata without any inference or guessing.
"""

from appian_parser.enrichment.enricher import Enricher
from appian_parser.enrichment.edge_types import EdgeType, EdgeMetadata
from appian_parser.domain.enriched_models import (
    EnrichedBundle,
    EnrichedFlow,
    TypedEdge,
    ObjectEnrichment,
    BundleStatistics,
    ObjectStatistics,
    CriticalPaths,
)

__all__ = [
    'Enricher',
    'EdgeType',
    'EdgeMetadata',
    'EnrichedBundle',
    'EnrichedFlow',
    'TypedEdge',
    'ObjectEnrichment',
    'BundleStatistics',
    'ObjectStatistics',
    'CriticalPaths',
]

__version__ = '0.1.0'
