"""Shared fixtures for validation tests against real Appian packages."""

import json
import os
import shutil
import pytest

from appian_parser.cli import dump_package
from appian_parser.domain.models import DumpOptions

TEST_FILES = "test_files/source_selection_v1"
FULL_V28 = f"{TEST_FILES}/SourceSelectionv2.8.0 - FULL.zip"
LEGACY_OUTPUT = "/tmp/v3_validation_legacy"


@pytest.fixture(scope="session")
def legacy_output():
    """Parse v2.8.0 in legacy mode once for all validation tests."""
    if not os.path.isfile(FULL_V28):
        pytest.skip("Test package not available")
    if os.path.isdir(LEGACY_OUTPUT):
        shutil.rmtree(LEGACY_OUTPUT)
    result = dump_package(FULL_V28, LEGACY_OUTPUT, DumpOptions(pretty=True))
    assert result.objects_parsed > 0, "Parse produced 0 objects"
    return LEGACY_OUTPUT


def load_json(path):
    with open(path) as f:
        return json.load(f)
