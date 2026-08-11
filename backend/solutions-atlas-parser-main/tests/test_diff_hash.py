"""Tests for DiffHashService."""

import pytest

from appian_parser.diff_hash import DiffHashService


class TestDiffHashService:
    """Tests for content hashing."""

    def test_generate_hash_returns_hex_string(self):
        result = DiffHashService.generate_hash({'key': 'value'})
        assert isinstance(result, str)
        assert len(result) == 128  # SHA-512 hex

    def test_same_data_same_hash(self):
        data = {'name': 'Test', 'value': 42}
        assert DiffHashService.generate_hash(data) == DiffHashService.generate_hash(data)

    def test_different_data_different_hash(self):
        h1 = DiffHashService.generate_hash({'name': 'A'})
        h2 = DiffHashService.generate_hash({'name': 'B'})
        assert h1 != h2

    def test_excludes_version_uuid(self):
        """version_uuid should not affect the hash."""
        h1 = DiffHashService.generate_hash({'name': 'Test', 'version_uuid': 'v1'})
        h2 = DiffHashService.generate_hash({'name': 'Test', 'version_uuid': 'v2'})
        assert h1 == h2

    def test_excludes_all_excluded_fields(self):
        base = {'name': 'Test'}
        for field in DiffHashService.EXCLUDED_FIELDS:
            with_field = {**base, field: 'some_value'}
            assert DiffHashService.generate_hash(base) == DiffHashService.generate_hash(with_field)

    def test_nested_data_hashed(self):
        data = {'outer': {'inner': 'value'}}
        result = DiffHashService.generate_hash(data)
        assert len(result) == 128

    def test_list_data_hashed(self):
        data = {'items': [1, 2, 3]}
        result = DiffHashService.generate_hash(data)
        assert len(result) == 128

    def test_order_independent_keys(self):
        """Dict keys are sorted, so order shouldn't matter."""
        h1 = DiffHashService.generate_hash({'a': 1, 'b': 2})
        h2 = DiffHashService.generate_hash({'b': 2, 'a': 1})
        assert h1 == h2
