import os
import tempfile
import pytest

from backup_util.compression.compressor import Compressor
from backup_util.constants import CompressionType


@pytest.fixture
def sample_data():
    return b"Database Backup Utility test payload 1234567890 \n" * 1000


def test_compression_decompression_all_algorithms(sample_data):
    algorithms = [
        CompressionType.NONE,
        CompressionType.GZIP,
        CompressionType.BZIP2,
        CompressionType.XZ,
        CompressionType.ZIP,
    ]
    if hasattr(Compressor, "HAS_ZSTD"):
        algorithms.append(CompressionType.ZSTD)

    for algo in algorithms:
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as comp, \
             tempfile.NamedTemporaryFile(delete=False) as decomp:

            src_path = src.name
            comp_path = comp.name
            decomp_path = decomp.name

        try:
            with open(src_path, "wb") as f:
                f.write(sample_data)

            # Compress
            uncomp_size, comp_size, checksum = Compressor.compress_file(src_path, comp_path, algorithm=algo)
            assert uncomp_size == len(sample_data)
            if algo != CompressionType.NONE:
                assert comp_size < uncomp_size

            # Decompress
            restored_size, restored_checksum = Compressor.decompress_file(comp_path, decomp_path, algorithm=algo)
            assert restored_size == len(sample_data)
            assert restored_checksum == checksum

            with open(decomp_path, "rb") as f:
                restored_data = f.read()
            assert restored_data == sample_data

        finally:
            for p in [src_path, comp_path, decomp_path]:
                if os.path.exists(p):
                    os.unlink(p)
