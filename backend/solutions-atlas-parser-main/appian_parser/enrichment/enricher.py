"""Main orchestrator for data enrichment."""

from typing import List, Dict, Any
from appian_parser.enrichment.graph_enricher import GraphEnricher
from appian_parser.enrichment.depth_calculator import DependencyDepthCalculator
from appian_parser.enrichment.path_analyzer import CriticalPathAnalyzer
from appian_parser.enrichment.tag_classifier import TagClassifier
from appian_parser.enrichment.statistics_collector import StatisticsCollector
from appian_parser.domain.enriched_models import (
    EnrichedBundle,
    EnrichedFlow,
    ObjectEnrichment,
    BundleStatistics,
    ObjectStatistics,
)


class Enricher:
    """Main orchestrator for enriching parsed Appian objects."""
    
    def __init__(self):
        """Initialize the enricher."""
        self.graph_enricher = GraphEnricher()
        self.tag_classifier = TagClassifier()
    
    def enrich_all(
        self,
        parsed_objects: List,
        dependencies: List,
    ) -> Dict[str, Any]:
        """Enrich all parsed objects and dependencies.
        
        Args:
            parsed_objects: List of ParsedObject instances
            dependencies: List of Dependency instances
            
        Returns:
            Dictionary containing all enrichment data
        """
        # Calculate dependency depths
        depth_calc = DependencyDepthCalculator(parsed_objects, dependencies)
        depths = depth_calc.calculate_depths()
        
        # Collect statistics
        stats_collector = StatisticsCollector(parsed_objects)
        
        # Enrich objects
        object_enrichments = []
        for obj in parsed_objects:
            obj_stats = stats_collector.collect_object_stats(obj.uuid, dependencies)
            tags = self.tag_classifier.classify_object(obj)
            
            enrichment = ObjectEnrichment(
                uuid=obj.uuid,
                dependency_depth=depths.get(obj.uuid),
                tags=tags,
                statistics=ObjectStatistics(**obj_stats)
            )
            object_enrichments.append(enrichment)
        
        return {
            'object_enrichments': [e.to_dict() for e in object_enrichments],
            'depths': depths,
        }
    
    def enrich_bundle(
        self,
        bundle_objects: List,
        dependencies: List,
    ) -> EnrichedBundle:
        """Enrich a single bundle.
        
        Args:
            bundle_objects: List of objects in the bundle
            dependencies: List of dependencies
            
        Returns:
            EnrichedBundle instance
        """
        # Collect statistics
        stats_collector = StatisticsCollector(bundle_objects)
        bundle_stats = stats_collector.collect_bundle_stats(bundle_objects, dependencies)
        
        # Classify bundle
        tags = self.tag_classifier.classify_bundle(bundle_objects, bundle_stats)
        
        # Find process model for flow enrichment
        enriched_flow = None
        for obj in bundle_objects:
            if obj.object_type == 'Process Model':
                # Enrich edges
                typed_edges = self.graph_enricher.enrich_edges(obj.data)
                
                # Analyze critical paths
                path_analyzer = CriticalPathAnalyzer(obj.data)
                critical_paths = path_analyzer.analyze()
                
                enriched_flow = EnrichedFlow(
                    nodes=obj.data.get('nodes', []),
                    edges=typed_edges,
                    critical_paths=critical_paths
                )
                break
        
        return EnrichedBundle(
            bundle_id=bundle_objects[0].uuid if bundle_objects else 'unknown',
            tags=tags,
            statistics=BundleStatistics(**bundle_stats),
            enriched_flow=enriched_flow
        )
