"""Tests for Enricher class."""

import pytest
from appian_parser.enrichment import Enricher


class TestEnricher:
    """Tests for Enricher class."""
    
    def test_enricher_initialization(self):
        """Test Enricher can be initialized."""
        enricher = Enricher()
        assert enricher is not None
        assert enricher.graph_enricher is not None
        assert enricher.tag_classifier is not None
    
    def test_enrich_all(self, sample_parsed_object, sample_dependency):
        """Test enrich_all returns expected structure."""
        enricher = Enricher()
        result = enricher.enrich_all([sample_parsed_object], [sample_dependency])
        
        assert 'object_enrichments' in result
        assert 'depths' in result
        assert isinstance(result['object_enrichments'], list)
        assert isinstance(result['depths'], dict)
    
    def test_enrich_bundle(self, sample_process_model, sample_dependency):
        """Test enrich_bundle returns EnrichedBundle."""
        enricher = Enricher()
        bundle = enricher.enrich_bundle([sample_process_model], [sample_dependency])
        
        assert bundle is not None
        assert bundle.bundle_id == sample_process_model.uuid
        assert isinstance(bundle.tags, list)
        assert bundle.statistics is not None
