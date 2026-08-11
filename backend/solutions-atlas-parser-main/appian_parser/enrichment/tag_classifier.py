"""Rule-based tag classifier for bundles and objects."""

from typing import List, Dict, Any


class TagClassifier:
    """Classifies bundles and objects with deterministic tags."""
    
    def __init__(self):
        """Initialize the tag classifier."""
        pass
    
    def classify_bundle(self, bundle_objects: List, statistics: Dict[str, Any]) -> List[str]:
        """Apply classification rules to a bundle.
        
        Args:
            bundle_objects: List of objects in the bundle
            statistics: Bundle statistics
            
        Returns:
            List of classification tags
        """
        tags = []
        
        # Architecture tags
        if self._has_record_types(bundle_objects):
            tags.append('record_driven')
        
        if statistics.get('integration_count', 0) >= 3:
            tags.append('integration_heavy')
        
        if statistics.get('subprocess_count', 0) >= 3:
            tags.append('subprocess_heavy')
        
        if statistics.get('user_task_count', 0) >= 5:
            tags.append('form_heavy')
        
        # Workflow tags
        if self._has_gateways(bundle_objects, ['XOR_GATEWAY', 'OR_GATEWAY']):
            tags.append('conditional_workflow')
        
        if self._has_gateways(bundle_objects, ['AND_GATEWAY']):
            tags.append('parallel_workflow')
        
        if self._has_approval_tasks(bundle_objects):
            tags.append('approval_workflow')
        
        # Data operation tags
        write_count = self._count_operations(bundle_objects, ['a!writeToDataStoreEntity', 'a!writeRecords'])
        query_count = self._count_operations(bundle_objects, ['a!queryEntity', 'a!queryRecordType'])
        
        if write_count == 0 and query_count > 0:
            tags.append('read_only')
        
        if write_count >= 5:
            tags.append('write_heavy')
        
        if query_count >= 5:
            tags.append('query_heavy')
        
        # Complexity tags
        total_nodes = statistics.get('total_nodes', 0)
        if total_nodes < 10:
            tags.append('simple')
        elif total_nodes <= 30:
            tags.append('moderate')
        else:
            tags.append('complex')
        
        # Integration type tags
        if statistics.get('integration_count', 0) > 0:
            tags.append('has_integrations')
        
        return tags
    
    def classify_object(self, obj: Any) -> List[str]:
        """Classify an individual object.
        
        Args:
            obj: ParsedObject instance
            
        Returns:
            List of classification tags
        """
        tags = []
        
        if obj.object_type == 'Interface':
            expression = str(obj.data.get('expression', ''))
            
            # UI pattern detection
            chart_count = expression.count('a!chartField') + expression.count('a!pieChartField')
            grid_count = expression.count('a!gridField')
            form_count = expression.count('a!formLayout')
            write_count = expression.count('a!writeToDataStoreEntity') + expression.count('a!writeRecords')
            
            if chart_count >= 2 and write_count == 0:
                tags.append('dashboard')
            
            if form_count > 0 and write_count > 0:
                tags.append('form_interface')
            
            if grid_count > 0 and write_count == 0:
                tags.append('report')
        
        return tags
    
    def _has_record_types(self, objects: List) -> bool:
        """Check if any object references record types."""
        for obj in objects:
            if 'recordType' in str(obj.data):
                return True
        return False
    
    def _has_gateways(self, objects: List, gateway_types: List[str]) -> bool:
        """Check if process models have specific gateway types."""
        for obj in objects:
            if obj.object_type == 'Process Model':
                nodes = obj.data.get('nodes', [])
                for node in nodes:
                    if node.get('type') in gateway_types:
                        return True
        return False
    
    def _has_approval_tasks(self, objects: List) -> bool:
        """Check if process models have approval tasks."""
        for obj in objects:
            if obj.object_type == 'Process Model':
                nodes = obj.data.get('nodes', [])
                for node in nodes:
                    if node.get('type') == 'APPROVAL_TASK':
                        return True
                    name = node.get('name', '').lower()
                    if any(kw in name for kw in ['approve', 'review', 'accept', 'reject']):
                        return True
        return False
    
    def _count_operations(self, objects: List, operation_patterns: List[str]) -> int:
        """Count specific operations across all objects."""
        count = 0
        for obj in objects:
            data_str = str(obj.data)
            for pattern in operation_patterns:
                count += data_str.count(pattern)
        return count
