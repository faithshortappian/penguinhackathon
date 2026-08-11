"""Package reader for Appian zip files."""
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from typing import List


class PackageReadError(Exception):
    """Error reading package."""
    pass


@dataclass
class PackageContents:
    """Package contents."""
    temp_dir: str
    xml_files: List[str]
    zip_filename: str
    total_files: int
    properties_files: List[str]


class PackageReader:
    """Reads Appian package files."""
    
    def __init__(self):
        self.skip_folders = {'tempoReport', 'processModelFolder', 'groupType'}
    
    def read(self, zip_path: str) -> PackageContents:
        """Read package contents, handling nested ZIPs (Appian export format)."""
        try:
            temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                zip_file.extractall(temp_dir)

            # Extract nested ZIPs (Appian packages are outer ZIP → inner ZIP)
            self._extract_nested_zips(temp_dir)

            xml_files = []
            properties_files = []
            total_files = 0

            for root, dirs, files in os.walk(temp_dir):
                dirs[:] = [d for d in dirs if d not in self.skip_folders]
                for file in files:
                    total_files += 1
                    if file.endswith(('.xml', '.xsd')):
                        xml_files.append(os.path.join(root, file))
                    elif file.endswith('.properties'):
                        properties_files.append(os.path.join(root, file))

            return PackageContents(
                temp_dir=temp_dir,
                xml_files=xml_files,
                zip_filename=os.path.basename(zip_path),
                total_files=total_files,
                properties_files=properties_files,
            )
        except Exception as e:
            raise PackageReadError(f"Failed to read package: {e}")

    def _extract_nested_zips(self, temp_dir: str) -> None:
        """Find and extract nested ZIP files (skip AdminConsole ZIPs)."""
        for root, _dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith('.zip') and 'AdminConsole' not in file:
                    nested_path = os.path.join(root, file)
                    try:
                        with zipfile.ZipFile(nested_path, 'r') as zf:
                            zf.extractall(root)
                        os.remove(nested_path)
                    except zipfile.BadZipFile:
                        pass
    
    def cleanup(self, temp_dir: str):
        """Clean up temporary directory."""
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)