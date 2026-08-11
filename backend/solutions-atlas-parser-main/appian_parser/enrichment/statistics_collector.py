"""Statistics collector for objects and bundles."""

from collections import defaultdict
from typing import List, Dict, Any


class StatisticsCollector:
    """Collects comprehensive statistics about objects and bundles."""
    
    def __init__(self, parsed_objects: List):
        """Initialize collector with parsed objects."""
        self.objects = {obj.uuid: obj for obj in parsed_objects}
    
    def collect_object_stats(self, obj_uuid: str, dependencies: List) -> Dict[str, Any]:
        """Collect statistics for a single object."""
        obj = self.objects.get(obj_uuid)
        if not obj:
            return {}
        
        # Count dependencies
        dep_count = sum(1 for d in dependencies if d.source_uuid == obj_uuid)
        dependent_count = sum(1 for d in dependencies if d.target_uuid == obj_uuid)
        
        stats = {
            'dependency_count': dep_count,
            'dependent_count': dependent_count,
        }
        
        # Add type-specific stats
        if obj.object_type == 'Process Model':
            stats['node_count'] = len(obj.data.get('nodes', []))
            stats['complexity_score'] = obj.data.get('complexity_score')
        
        return stats
    
    def collect_bundle_stats(self, bundle_objects: List, dependencies: List) -> Dict[str, Any]:
        """Collect statistics for a bundle."""
        stats = {
            'total_objects': len(bundle_objects),
            'object_counts': defaultdict(int),
            'total_nodes': 0,
            'total_edges': 0,
            'integration_count': 0,
            'subprocess_count': 0,
            'user_task_count': 0,
        }
        
        for obj in bundle_objects:
            stats['object_counts'][obj.object_type] += 1
            
            if obj.object_type == 'Process Model':
                nodes = obj.data.get('nodes', [])
                flows = obj.data.get('flows', [])
                stats['total_nodes'] += len(nodes)
                stats['total_edges'] += len(flows)
                
                # Count specific node types
                for node in nodes:
                    node_type = node.get('type', '')
                    if node_type in ['USER_INPUT_TASK', 'APPROVAL_TASK']:
                        stats['user_task_count'] += 1
                    elif node_type == 'SUBPROCESS':
                        stats['subprocess_count'] += 1
                    elif node_type == 'INTEGRATION':
                        stats['integration_count'] += 1
            
            elif obj.object_type == 'Integration':
                stats['integration_count'] += 1
        
        stats['object_counts'] = dict(stats['object_counts'])
        return stats
