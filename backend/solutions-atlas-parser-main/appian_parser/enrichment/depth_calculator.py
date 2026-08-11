"""Dependency depth calculator using BFS."""

from collections import deque, defaultdict
from typing import List, Dict, Set


class DependencyDepthCalculator:
    """Calculates dependency depth for all objects from entry points."""
    
    def __init__(self, parsed_objects: List, dependencies: List):
        """Initialize calculator with parsed objects and dependencies.
        
        Args:
            parsed_objects: List of ParsedObject instances
            dependencies: List of Dependency instances
        """
        self.objects = {obj.uuid: obj for obj in parsed_objects}
        self.dependency_graph = self._build_dependency_graph(dependencies)
        self.entry_points = self._identify_entry_points(dependencies)
    
    def calculate_depths(self) -> Dict[str, int]:
        """Calculate depth for all objects using BFS.
        
        Returns:
            Dictionary mapping object UUID to depth
        """
        depths = {}
        
        for entry_point in self.entry_points:
            entry_depths = self._bfs_depth(entry_point)
            
            # Keep minimum depth for each object
            for obj_id, depth in entry_depths.items():
                if obj_id not in depths or depth < depths[obj_id]:
                    depths[obj_id] = depth
        
        return depths
    
    def _build_dependency_graph(self, dependencies: List) -> Dict[str, List[str]]:
        """Build adjacency list of object dependencies."""
        graph = defaultdict(list)
        
        for dep in dependencies:
            graph[dep.source_uuid].append(dep.target_uuid)
        
        return graph
    
    def _identify_entry_points(self, dependencies: List) -> List[str]:
        """Identify entry point objects (interfaces, top-level process models)."""
        entry_points = []
        
        # Find all objects that are called
        called_objects: Set[str] = set()
        for dep in dependencies:
            called_objects.add(dep.target_uuid)
        
        # Entry points are interfaces and process models not called by others
        for obj in self.objects.values():
            if obj.object_type == 'Interface':
                entry_points.append(obj.uuid)
            elif obj.object_type == 'Process Model' and obj.uuid not in called_objects:
                entry_points.append(obj.uuid)
        
        return entry_points
    
    def _bfs_depth(self, start_node: str) -> Dict[str, int]:
        """BFS to calculate depth from start node."""
        depths = {start_node: 0}
        queue = deque([start_node])
        
        while queue:
            current = queue.popleft()
            current_depth = depths[current]
            
            for neighbor in self.dependency_graph.get(current, []):
                if neighbor not in depths:
                    depths[neighbor] = current_depth + 1
                    queue.append(neighbor)
        
        return depths
