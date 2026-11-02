import bz2
import gzip
import hashlib
import io
import lzma
import os
import zipfile
from pathlib import Path
from typing import BinaryIO, Callable, Optional, Tuple

from backup_util.constants import CHUNK_SIZE, CompressionType
from backup_util.exceptions import CompressionError

# Check zstandard support
try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False


class Compressor:
    """Handles streaming compression and decompression for backup streams and files."""

    EXTENSION_MAP = {
        CompressionType.NONE: "",
        CompressionType.GZIP: ".gz",
        CompressionType.BZIP2: ".bz2",
        CompressionType.ZSTD: ".zst",
        CompressionType.XZ: ".xz",
        CompressionType.ZIP: ".zip",
    }

    @classmethod
    def get_extension(cls, comp_type: CompressionType) -> str:
        return cls.EXTENSION_MAP.get(comp_type, "")

    @classmethod
    def detect_compression(cls, filepath: str) -> CompressionType:
        """Detect compression type from file extension."""
        lower = filepath.lower()
        if lower.endswith(".gz"):
            return CompressionType.GZIP
        if lower.endswith(".bz2"):
            return CompressionType.BZIP2
        if lower.endswith(".zst"):
            return CompressionType.ZSTD
        if lower.endswith(".xz"):
            return CompressionType.XZ
        if lower.endswith(".zip"):
            return CompressionType.ZIP
        return CompressionType.NONE

    @classmethod
    def compress_stream(
        cls,
        input_stream: BinaryIO,
        output_stream: BinaryIO,
        algorithm: CompressionType = CompressionType.GZIP,
        level: int = 6,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Tuple[int, int, str]:
        """
        Compresses data from input_stream to output_stream in chunks.
        Computes SHA-256 hash of the uncompressed data.
        Returns: (uncompressed_bytes, compressed_bytes, sha256_hex)
        """
        sha256 = hashlib.sha256()
        uncompressed_bytes = 0
        initial_out_pos = output_stream.tell() if output_stream.seekable() else 0

        try:
            if algorithm == CompressionType.NONE:
                while True:
                    chunk = input_stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sha256.update(chunk)
                    uncompressed_bytes += len(chunk)
                    output_stream.write(chunk)
                    if progress_callback:
                        progress_callback(len(chunk))

            elif algorithm == CompressionType.GZIP:
                with gzip.GzipFile(fileobj=output_stream, mode="wb", compresslevel=level) as gz:
                    while True:
                        chunk = input_stream.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        gz.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.BZIP2:
                with bz2.BZ2File(output_stream, mode="wb", compresslevel=level) as bz:
                    while True:
                        chunk = input_stream.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        bz.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.XZ:
                with lzma.LZMAFile(output_stream, mode="wb", preset=level) as xzf:
                    while True:
                        chunk = input_stream.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        xzf.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.ZSTD:
                if not HAS_ZSTD:
                    raise CompressionError("zstandard package is required for ZSTD compression.")
                cctx = zstd.ZstdCompressor(level=level)
                with cctx.stream_writer(output_stream, closefd=False) as writer:
                    while True:
                        chunk = input_stream.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        writer.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.ZIP:
                with zipfile.ZipFile(output_stream, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                    with zf.open("backup_data", mode="w") as zentry:
                        while True:
                            chunk = input_stream.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            sha256.update(chunk)
                            uncompressed_bytes += len(chunk)
                            zentry.write(chunk)
                            if progress_callback:
                                progress_callback(len(chunk))
            else:
                raise CompressionError(f"Unsupported compression algorithm: {algorithm}")

        except Exception as e:
            if isinstance(e, CompressionError):
                raise
            raise CompressionError(f"Failed to compress data with {algorithm}: {e}") from e

        final_out_pos = output_stream.tell() if output_stream.seekable() else uncompressed_bytes
        compressed_bytes = max(0, final_out_pos - initial_out_pos)
        return uncompressed_bytes, compressed_bytes, sha256.hexdigest()

    @classmethod
    def compress_file(
        cls,
        src_path: str,
        dest_path: str,
        algorithm: CompressionType = CompressionType.GZIP,
        level: int = 6,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Tuple[int, int, str]:
        """Compress a local file to dest_path."""
        with open(src_path, "rb") as src, open(dest_path, "wb") as dst:
            return cls.compress_stream(src, dst, algorithm, level, progress_callback)

    @classmethod
    def decompress_stream(
        cls,
        input_stream: BinaryIO,
        output_stream: BinaryIO,
        algorithm: CompressionType = CompressionType.GZIP,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Tuple[int, str]:
        """
        Decompresses data from input_stream into output_stream in chunks.
        Computes SHA-256 hash of the restored uncompressed data.
        Returns: (uncompressed_bytes, sha256_hex)
        """
        sha256 = hashlib.sha256()
        uncompressed_bytes = 0

        try:
            if algorithm == CompressionType.NONE:
                while True:
                    chunk = input_stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sha256.update(chunk)
                    uncompressed_bytes += len(chunk)
                    output_stream.write(chunk)
                    if progress_callback:
                        progress_callback(len(chunk))

            elif algorithm == CompressionType.GZIP:
                with gzip.GzipFile(fileobj=input_stream, mode="rb") as gz:
                    while True:
                        chunk = gz.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        output_stream.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.BZIP2:
                with bz2.BZ2File(input_stream, mode="rb") as bz:
                    while True:
                        chunk = bz.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        output_stream.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.XZ:
                with lzma.LZMAFile(input_stream, mode="rb") as xzf:
                    while True:
                        chunk = xzf.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        output_stream.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.ZSTD:
                if not HAS_ZSTD:
                    raise CompressionError("zstandard package is required for ZSTD decompression.")
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(input_stream) as reader:
                    while True:
                        chunk = reader.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        uncompressed_bytes += len(chunk)
                        output_stream.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))

            elif algorithm == CompressionType.ZIP:
                with zipfile.ZipFile(input_stream, mode="r") as zf:
                    namelist = zf.namelist()
                    if not namelist:
                        raise CompressionError("Zip archive is empty.")
                    with zf.open(namelist[0], mode="r") as zentry:
                        while True:
                            chunk = zentry.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            sha256.update(chunk)
                            uncompressed_bytes += len(chunk)
                            output_stream.write(chunk)
                            if progress_callback:
                                progress_callback(len(chunk))
            else:
                raise CompressionError(f"Unsupported decompression algorithm: {algorithm}")

        except Exception as e:
            if isinstance(e, CompressionError):
                raise
            raise CompressionError(f"Failed to decompress data: {e}") from e

        return uncompressed_bytes, sha256.hexdigest()

    @classmethod
    def decompress_file(
        cls,
        src_path: str,
        dest_path: str,
        algorithm: Optional[CompressionType] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Tuple[int, str]:
        """Decompress a local file to dest_path."""
        if algorithm is None:
            algorithm = cls.detect_compression(src_path)

        with open(src_path, "rb") as src, open(dest_path, "wb") as dst:
            return cls.decompress_stream(src, dst, algorithm, progress_callback)
