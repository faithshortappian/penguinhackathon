"""Integration test for the full CLI pipeline."""

import json
import os

import pytest

from appian_parser.cli import dump_package
from appian_parser.domain.models import DumpOptions


class TestCLIPipeline:
    """End-to-end tests for the dump pipeline."""

    def test_dump_produces_v3_structure(self, sample_zip, tmp_path):
        """Verify v3 output has objects/, code/, bundles/ (flat), graph.json, orphans_index.json."""
        output_dir = str(tmp_path / "output")
        result = dump_package(sample_zip, output_dir, DumpOptions())

        assert result.objects_parsed > 0
        assert os.path.isfile(os.path.join(output_dir, 'app_overview.json'))
        assert os.path.isfile(os.path.join(output_dir, 'search_index.json'))
        assert os.path.isfile(os.path.join(output_dir, 'graph.json'))
        assert os.path.isfile(os.path.join(output_dir, 'orphans_index.json'))
        assert os.path.isdir(os.path.join(output_dir, 'objects'))
        assert os.path.isdir(os.path.join(output_dir, 'code'))
        assert os.path.isdir(os.path.join(output_dir, 'bundles'))

        # Object files have type_specific
        obj_files = os.listdir(os.path.join(output_dir, 'objects'))
        if obj_files:
            sample = json.load(open(os.path.join(output_dir, 'objects', obj_files[0])))
            assert 'type_specific' in sample
            assert 'uuid' in sample
            assert 'calls' in sample
            assert 'called_by' in sample
            # Legacy mode: no version_history
            assert 'version_history' not in sample

    def test_dump_produces_app_overview(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        options = DumpOptions(pretty=True)
        result = dump_package(sample_zip, output_dir, options)

        assert result.objects_parsed > 0
        assert result.errors_count == 0
        assert os.path.isfile(os.path.join(output_dir, 'app_overview.json'))

    def test_dump_app_overview_structure(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        dump_package(sample_zip, output_dir, DumpOptions())

        with open(os.path.join(output_dir, 'app_overview.json')) as f:
            overview = json.load(f)

        assert '_metadata' in overview
        assert 'package_info' in overview
        assert 'object_counts' in overview
        assert 'coverage' in overview
        assert overview['package_info']['total_parsed_objects'] > 0

    def test_dump_produces_search_index(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        dump_package(sample_zip, output_dir, DumpOptions())

        path = os.path.join(output_dir, 'search_index.json')
        assert os.path.isfile(path)
        with open(path) as f:
            index = json.load(f)
        assert len(index) > 0

    def test_dump_produces_object_files(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        dump_package(sample_zip, output_dir, DumpOptions(include_dependencies=True))

        objects_dir = os.path.join(output_dir, 'objects')
        # Object files exist if dependencies were found
        if os.path.isdir(objects_dir):
            files = os.listdir(objects_dir)
            assert len(files) > 0

    def test_dump_no_deps_option(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        dump_package(sample_zip, output_dir, DumpOptions(include_dependencies=False))

        # Objects dir always exists in v3 (object files are independent of deps)
        assert os.path.isdir(os.path.join(output_dir, 'objects'))
        # But graph should be empty and no bundles
        graph = json.load(open(os.path.join(output_dir, 'graph.json')))
        assert graph['_metadata']['edge_count'] == 0
        assert not os.listdir(os.path.join(output_dir, 'bundles'))

    def test_dump_no_errors_file_when_clean(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        result = dump_package(sample_zip, output_dir, DumpOptions())

        if result.errors_count == 0:
            assert not os.path.isfile(os.path.join(output_dir, 'errors.json'))

    def test_dump_result_fields(self, sample_zip, tmp_path):
        output_dir = str(tmp_path / "output")
        result = dump_package(sample_zip, output_dir, DumpOptions())

        assert result.total_files > 0
        assert result.objects_parsed > 0
        assert result.output_dir == output_dir
