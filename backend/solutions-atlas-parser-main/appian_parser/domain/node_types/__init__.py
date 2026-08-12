"""
Node Type Registry for Process Model Nodes.

This module provides a centralized registry for mapping Appian process model
node type identifiers (local-id) to human-readable names and categories.

The registry is used by the ProcessModelParser to enhance extracted node
data with human-readable type names and category classifications.

Example:
    >>> from domain.node_types import NODE_TYPE_REGISTRY, NodeCategory
    >>> from domain.node_types import get_node_type_info
    >>>
    >>> # Get info for a known node type
    >>> info = get_node_type_info('core.0')
    >>> print(info.name)  # "Start Event"
    >>> print(info.category)  # NodeCategory.CORE
    >>>
    >>> # Get info for an unknown node type (falls back to inference)
    >>> info = get_node_type_info('custom.plugin.node')
    >>> print(info.name)  # "custom.plugin.node"
    >>> print(info.category)  # NodeCategory.PLUGIN

Module Contents:
    NodeCategory: Enum of node categories (Core, Gateway, Smart Service, etc.)
    NodeTypeInfo: Immutable dataclass containing node type metadata
    NODE_TYPE_REGISTRY: Dictionary mapping local-id to NodeTypeInfo
    get_node_type_info: Function to get NodeTypeInfo with fallback inference
    infer_category_from_local_id: Function to infer category from local-id pattern
"""

from appian_parser.domain.node_types.categories import NodeCategory
from appian_parser.domain.node_types.registry import (
    NODE_TYPE_REGISTRY,
    NodeTypeInfo,
    get_node_type_info,
    infer_category_from_local_id,
)

__all__ = [
    'NodeCategory',
    'NODE_TYPE_REGISTRY',
    'NodeTypeInfo',
    'get_node_type_info',
    'infer_category_from_local_id',
]
