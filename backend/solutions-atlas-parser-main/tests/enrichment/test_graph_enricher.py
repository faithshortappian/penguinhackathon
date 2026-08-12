"""Tests for GraphEnricher class."""

import pytest
from appian_parser.enrichment.graph_enricher import GraphEnricher
from appian_parser.enrichment.edge_types import EdgeType


class TestGraphEnricher:
    """Tests for GraphEnricher class."""
    
    def test_initialization(self):
        """Test GraphEnricher can be initialized."""
        enricher = GraphEnricher()
        assert enricher is not None
    
    def test_enrich_edges_basic(self):
        """Test basic edge enrichment."""
        enricher = GraphEnricher()
        pm_data = {
            'nodes': [
                {'id': 'n1', 'type': 'START_EVENT'},
                {'id': 'n2', 'type': 'USER_INPUT_TASK'},
                {'id': 'n3', 'type': 'END_EVENT'},
            ],
            'flows': [
                {'from': 'n1', 'to': 'n2'},
                {'from': 'n2', 'to': 'n3'},
            ]
        }
        
        edges = enricher.enrich_edges(pm_data)
        
        assert len(edges) == 2
        assert edges[0].edge_type == EdgeType.USER_INPUT_TASK.value
        assert edges[1].edge_type == EdgeType.END_EVENT.value
    
    def test_conditional_edge(self):
        """Test conditional edge detection."""
        enricher = GraphEnricher()
        pm_data = {
            'nodes': [
                {'id': 'n1', 'type': 'XOR_GATEWAY'},
                {'id': 'n2', 'type': 'USER_INPUT_TASK'},
            ],
            'flows': [
                {'from': 'n1', 'to': 'n2', 'condition': 'approved'},
            ]
        }
        
        edges = enricher.enrich_edges(pm_data)
        
        assert len(edges) == 1
        assert edges[0].edge_type == EdgeType.CONDITIONAL.value
        assert edges[0].metadata['gateway_type'] == 'XOR_GATEWAY'
        assert edges[0].metadata['condition'] == 'approved'
