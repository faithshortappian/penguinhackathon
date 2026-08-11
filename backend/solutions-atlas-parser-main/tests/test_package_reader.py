"""Tests for PackageReader."""

import os
import pytest

from appian_parser.package_reader import PackageReader, PackageReadError


class TestPackageReader:
    """Tests for ZIP package reading."""

    def setup_method(self):
        self.reader = PackageReader()

    def test_read_valid_zip(self, sample_zip):
        contents = self.reader.read(sample_zip)
        try:
            assert len(contents.xml_files) == 4
            assert contents.zip_filename == "test_package.zip"
            assert contents.total_files >= 4
            assert os.path.isdir(contents.temp_dir)
        finally:
            self.reader.cleanup(contents.temp_dir)

    def test_read_discovers_xml_files(self, sample_zip):
        contents = self.reader.read(sample_zip)
        try:
            extensions = {os.path.splitext(f)[1] for f in contents.xml_files}
            assert extensions == {'.xml'}
        finally:
            self.reader.cleanup(contents.temp_dir)

    def test_cleanup_removes_temp_dir(self, sample_zip):
        contents = self.reader.read(sample_zip)
        temp_dir = contents.temp_dir
        assert os.path.exists(temp_dir)
        self.reader.cleanup(temp_dir)
        assert not os.path.exists(temp_dir)

    def test_cleanup_nonexistent_dir(self):
        """Cleanup should not raise for nonexistent directory."""
        self.reader.cleanup("/nonexistent/path/12345")

    def test_read_invalid_zip(self, tmp_path):
        bad_file = tmp_path / "bad.zip"
        bad_file.write_text("not a zip")
        with pytest.raises(PackageReadError):
            self.reader.read(str(bad_file))

    def test_skips_excluded_folders(self, tmp_path):
        """Verify that tempoReport/processModelFolder/groupType folders are skipped."""
        import zipfile
        zip_path = tmp_path / "skip_test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("good/test.xml", "<root/>")
            zf.writestr("tempoReport/skip.xml", "<root/>")
            zf.writestr("processModelFolder/skip.xml", "<root/>")
        contents = self.reader.read(str(zip_path))
        try:
            assert len(contents.xml_files) == 1
            assert any("good" in f for f in contents.xml_files)
        finally:
            self.reader.cleanup(contents.temp_dir)
