import hashlib
import logging
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

from typing import Optional

class ArchiveExtractor:
    """Universal extractor for various archive formats."""
    
    SUPPORTED_EXTENSIONS = {".zip", ".rar", ".tar", ".gz", ".tgz"}
    
    @classmethod
    def is_supported(cls, path: Path) -> bool:
        ext = path.suffix.lower()
        if ext in cls.SUPPORTED_EXTENSIONS:
            return True
        if path.name.lower().endswith(".tar.gz"):
            return True
        return False

    @classmethod
    def extract(cls, fpath: Path, workspace: Path) -> Optional[Path]:
        """Extract archive to a cache directory and return the cache path."""
        if not cls.is_supported(fpath):
            return None
            
        ext = fpath.suffix.lower()
        
        # Use md5 to ensure unique cache directory per file state
        hash_str = hashlib.md5(f"{fpath.resolve()}_{fpath.stat().st_mtime}".encode()).hexdigest()
        cache_dir = workspace / ".omx" / "cache" / "extracted" / hash_str
        
        if cache_dir.exists():
            return cache_dir
            
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if ext == ".zip":
                with zipfile.ZipFile(fpath, 'r') as zf:
                    zf.extractall(cache_dir)
            elif ext in (".tar", ".gz", ".tgz") or fpath.name.lower().endswith(".tar.gz"):
                with tarfile.open(fpath) as tf:
                    tf.extractall(cache_dir)
            elif ext == ".rar":
                # Use bsdtar for rar files (standard on macOS and many Linux distros)
                res = subprocess.run(["bsdtar", "-xf", str(fpath), "-C", str(cache_dir)], capture_output=True)
                if res.returncode != 0:
                    log.warning(f"bsdtar extract returned {res.returncode}: {res.stderr.decode()}")
                    # Continue anyway to scan partially extracted files
        except Exception as e:
            log.error(f"Failed to extract archive {fpath}: {e}")
            shutil.rmtree(cache_dir, ignore_errors=True)
            return None
            
        return cache_dir
