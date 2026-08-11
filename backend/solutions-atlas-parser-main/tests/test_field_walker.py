"""Tests for the shared field walker utility."""

import pytest

from appian_parser.domain.field_walker import walk_field_paths, apply_to_field_paths


class TestWalkFieldPaths:
    """Tests for walk_field_paths (read-only collection)."""

    def test_simple_key(self):
        data = {'sail_code': 'a!formLayout()'}
        assert walk_field_paths(data, 'sail_code') == ['a!formLayout()']

    def test_nested_key(self):
        data = {'config': {'url': 'https://example.com'}}
        assert walk_field_paths(data, 'config.url') == ['https://example.com']

    def test_list_iteration(self):
        data = {'nodes': [{'name': 'A'}, {'name': 'B'}]}
        assert walk_field_paths(data, 'nodes[].name') == ['A', 'B']

    def test_nested_list_iteration(self):
        data = {
            'nodes': [
                {'conditions': [{'expr': 'x > 1'}, {'expr': 'x < 10'}]},
                {'conditions': [{'expr': 'y = 0'}]},
            ]
        }
        result = walk_field_paths(data, 'nodes[].conditions[].expr')
        assert result == ['x > 1', 'x < 10', 'y = 0']

    def test_missing_key_returns_empty(self):
        assert walk_field_paths({}, 'missing') == []
        assert walk_field_paths({'a': 1}, 'b') == []

    def test_none_data_returns_empty(self):
        assert walk_field_paths(None, 'key') == []

    def test_non_string_values_skipped(self):
        data = {'items': [1, 'hello', None, 'world']}
        assert walk_field_paths(data, 'items[]') == ['hello', 'world']

    def test_mixed_path(self):
        data = {
            'nodes': [
                {'subprocess_config': {'input_mappings': [{'expression': 'expr1'}]}},
            ]
        }
        result = walk_field_paths(data, 'nodes[].subprocess_config.input_mappings[].expression')
        assert result == ['expr1']


class TestApplyToFieldPaths:
    """Tests for apply_to_field_paths (in-place mutation)."""

    def test_simple_key_mutation(self):
        data = {'sail_code': 'original'}
        apply_to_field_paths(data, 'sail_code', str.upper)
        assert data['sail_code'] == 'ORIGINAL'

    def test_list_mutation(self):
        data = {'items': [{'value': 'a'}, {'value': 'b'}]}
        apply_to_field_paths(data, 'items[].value', str.upper)
        assert data['items'][0]['value'] == 'A'
        assert data['items'][1]['value'] == 'B'

    def test_missing_key_no_error(self):
        data = {'other': 'value'}
        apply_to_field_paths(data, 'missing.path', str.upper)
        assert data == {'other': 'value'}

    def test_non_string_not_mutated(self):
        data = {'value': 42}
        apply_to_field_paths(data, 'value', str.upper)
        assert data['value'] == 42  # Unchanged
