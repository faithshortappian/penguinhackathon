"""Writer for enrichment output files."""

import json
import os
from typing import Dict, Any


class EnrichmentWriter:
    """Writes enrichment data to JSON files."""
    
    def __init__(self, output_dir: str, pretty: bool = True):
        """Initialize writer.
        
        Args:
            output_dir: Base output directory
            pretty: Whether to pretty-print JSON
        """
        self.output_dir = output_dir
        self.pretty = pretty
        self.enrichment_dir = os.path.join(output_dir, 'enrichment')
    
    def write_all(self, enriched_data: Dict[str, Any]) -> None:
        """Write all enrichment data to files.
        
        Args:
            enriched_data: Dictionary containing enrichment results
        """
        os.makedirs(self.enrichment_dir, exist_ok=True)
        
        # Write object depths
        if 'depths' in enriched_data:
            self._write_json('object_depths.json', enriched_data['depths'])
        
        # Write object enrichments
        if 'object_enrichments' in enriched_data:
            enrichments_by_uuid = {
                e['uuid']: e for e in enriched_data['object_enrichments']
            }
            self._write_json('object_enrichments.json', enrichments_by_uuid)
        
        # Write metadata
        metadata = {
            'total_objects': len(enriched_data.get('object_enrichments', [])),
            'objects_with_depth': len(enriched_data.get('depths', {})),
            'enrichment_version': '0.1.0'
        }
        self._write_json('metadata.json', metadata)
    
    def _write_json(self, filename: str, data: Any) -> None:
        """Write data to JSON file."""
        filepath = os.path.join(self.enrichment_dir, filename)
        with open(filepath, 'w') as f:
            if self.pretty:
                json.dump(data, f, indent=2, sort_keys=True)
            else:
                json.dump(data, f)
