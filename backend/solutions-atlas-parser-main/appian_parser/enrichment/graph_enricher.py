"""Graph enricher for typed edges in process models."""

from typing import List, Dict, Any
from appian_parser.enrichment.edge_types import EdgeType, EdgeMetadata
from appian_parser.domain.enriched_models import TypedEdge


class GraphEnricher:
    """Enriches process model flow graphs with typed edges."""
    
    def __init__(self):
        """Initialize the graph enricher."""
        self.node_map: Dict[str, Dict[str, Any]] = {}
    
    def enrich_edges(self, process_model_data: Dict[str, Any]) -> List[TypedEdge]:
        """Enrich edges with types based on node analysis.
        
        Args:
            process_model_data: Parsed process model data
            
        Returns:
            List of TypedEdge objects
        """
        nodes = process_model_data.get('nodes', [])
        flows = process_model_data.get('flows', [])
        
        # Build node lookup
        self.node_map = {node['id']: node for node in nodes}
        
        typed_edges = []
        for flow in flows:
            edge_type, metadata = self._determine_edge_type(flow)
            typed_edges.append(TypedEdge(
                from_node=flow['from'],
                to_node=flow['to'],
                edge_type=edge_type.value,
                metadata=metadata.to_dict()
            ))
        
        return typed_edges
    
    def _determine_edge_type(self, flow: Dict[str, Any]) -> tuple[EdgeType, EdgeMetadata]:
        """Determine edge type based on source and target nodes."""
        source = self.node_map.get(flow['from'], {})
        target = self.node_map.get(flow['to'], {})
        
        source_type = source.get('type', '')
        target_type = target.get('type', '')
        
        # End event
        if target_type == 'END_EVENT':
            return EdgeType.END_EVENT, EdgeMetadata()
        
        # Gateway branches
        if source_type in ['XOR_GATEWAY', 'OR_GATEWAY']:
            return EdgeType.CONDITIONAL, EdgeMetadata(
                gateway_type=source_type,
                condition=flow.get('condition')
            )
        
        if source_type == 'AND_GATEWAY':
            return EdgeType.PARALLEL, EdgeMetadata(gateway_type='AND')
        
        # Subprocess call
        if target_type == 'SUBPROCESS':
            return EdgeType.SUBPROCESS_CALL, EdgeMetadata(
                target_process=target.get('subprocess_uuid')
            )
        
        # User tasks
        if target_type == 'USER_INPUT_TASK':
            if self._is_approval_task(target):
                return EdgeType.APPROVAL_TASK, EdgeMetadata()
            return EdgeType.USER_INPUT_TASK, EdgeMetadata(
                form_uuid=target.get('form_uuid')
            )
        
        # Service tasks
        if target_type in ['INTEGRATION', 'SMART_SERVICE']:
            return self._classify_service_task(target)
        
        # Exception flow
        if flow.get('is_exception', False):
            return EdgeType.EXCEPTION_FLOW, EdgeMetadata()
        
        # Default: sequence
        return EdgeType.SEQUENCE, EdgeMetadata()
    
    def _is_approval_task(self, node: Dict[str, Any]) -> bool:
        """Detect if user task is an approval."""
        name = node.get('name', '').lower()
        return any(kw in name for kw in ['approve', 'review', 'accept', 'reject'])
    
    def _classify_service_task(self, node: Dict[str, Any]) -> tuple[EdgeType, EdgeMetadata]:
        """Classify service task into specific types."""
        expression = str(node.get('expression', ''))
        
        # Integration call
        if node.get('type') == 'INTEGRATION':
            return EdgeType.INTEGRATION_CALL, EdgeMetadata(
                integration_name=node.get('integration_name')
            )
        
        # Write operation
        if 'a!writeToDataStoreEntity' in expression or 'a!writeRecords' in expression:
            return EdgeType.WRITE_TO_RECORD, EdgeMetadata()
        
        # Query operation
        if 'a!queryEntity' in expression or 'a!queryRecordType' in expression:
            return EdgeType.QUERY_RECORD, EdgeMetadata()
        
        return EdgeType.SEQUENCE, EdgeMetadata()
