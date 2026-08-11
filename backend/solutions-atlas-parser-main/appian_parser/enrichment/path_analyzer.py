"""Critical path analyzer for process models."""

from collections import defaultdict, deque
from typing import List, Dict, Any, Tuple
from appian_parser.domain.enriched_models import CriticalPaths


class CriticalPathAnalyzer:
    """Analyzes process models to find critical paths."""
    
    def __init__(self, process_model_data: Dict[str, Any]):
        """Initialize analyzer with process model data."""
        self.nodes = process_model_data.get('nodes', [])
        self.flows = process_model_data.get('flows', [])
        self.node_map = {node['id']: node for node in self.nodes}
        self.graph = self._build_graph()
    
    def analyze(self) -> CriticalPaths:
        """Find critical paths through the process model."""
        longest = self._find_longest_path()
        most_nodes = self._find_most_nodes_path()
        
        return CriticalPaths(
            longest_path=longest,
            most_nodes_path=most_nodes
        )
    
    def _build_graph(self) -> Dict[str, List[Tuple[str, int]]]:
        """Build adjacency list with edge weights."""
        graph = defaultdict(list)
        
        for flow in self.flows:
            weight = self._estimate_edge_weight(flow)
            graph[flow['from']].append((flow['to'], weight))
        
        return graph
    
    def _estimate_edge_weight(self, flow: Dict[str, Any]) -> int:
        """Estimate edge weight based on target node type."""
        target_id = flow['to']
        target = self.node_map.get(target_id, {})
        target_type = target.get('type', '')
        
        weights = {
            'USER_INPUT_TASK': 10,
            'APPROVAL_TASK': 10,
            'INTEGRATION': 5,
            'SMART_SERVICE': 5,
            'SUBPROCESS': 8,
            'SCRIPT_TASK': 2,
        }
        
        return weights.get(target_type, 1)
    
    def _find_longest_path(self) -> List[str]:
        """Find longest path by weight using topological sort + DP."""
        start_nodes = [n['id'] for n in self.nodes if n.get('type') == 'START_EVENT']
        end_nodes = [n['id'] for n in self.nodes if n.get('type') == 'END_EVENT']
        
        if not start_nodes or not end_nodes:
            return []
        
        # Topological sort
        topo_order = self._topological_sort()
        if not topo_order:
            return []
        
        # DP for longest path
        distances = {node['id']: float('-inf') for node in self.nodes}
        predecessors = {}
        
        for start in start_nodes:
            distances[start] = 0
        
        for node_id in topo_order:
            if distances[node_id] == float('-inf'):
                continue
            
            for neighbor, weight in self.graph[node_id]:
                new_dist = distances[node_id] + weight
                if new_dist > distances[neighbor]:
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = node_id
        
        # Find best end node
        best_end = max(end_nodes, key=lambda n: distances[n])
        
        # Reconstruct path
        return self._reconstruct_path(predecessors, best_end)
    
    def _find_most_nodes_path(self) -> List[str]:
        """Find path that traverses most nodes using DFS."""
        start_nodes = [n['id'] for n in self.nodes if n.get('type') == 'START_EVENT']
        end_nodes = set(n['id'] for n in self.nodes if n.get('type') == 'END_EVENT')
        
        if not start_nodes or not end_nodes:
            return []
        
        max_path = []
        
        def dfs(current: str, path: List[str], visited: set):
            nonlocal max_path
            
            if current in end_nodes:
                if len(path) > len(max_path):
                    max_path = path.copy()
                return
            
            for neighbor, _ in self.graph[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    path.append(neighbor)
                    dfs(neighbor, path, visited)
                    path.pop()
                    visited.remove(neighbor)
        
        for start in start_nodes:
            visited = {start}
            dfs(start, [start], visited)
        
        return max_path
    
    def _topological_sort(self) -> List[str]:
        """Topological sort using Kahn's algorithm."""
        in_degree = defaultdict(int)
        
        for node in self.nodes:
            if node['id'] not in in_degree:
                in_degree[node['id']] = 0
        
        for node_id, neighbors in self.graph.items():
            for neighbor, _ in neighbors:
                in_degree[neighbor] += 1
        
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        topo_order = []
        
        while queue:
            current = queue.popleft()
            topo_order.append(current)
            
            for neighbor, _ in self.graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return topo_order
    
    def _reconstruct_path(self, predecessors: Dict[str, str], end: str) -> List[str]:
        """Reconstruct path from predecessors."""
        path = []
        current = end
        
        while current in predecessors:
            path.append(self.node_map[current].get('name', current))
            current = predecessors[current]
        
        path.append(self.node_map[current].get('name', current))
        path.reverse()
        
        return path
