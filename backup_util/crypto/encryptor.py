import base64
import hashlib
import os
from typing import BinaryIO, Optional, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from backup_util.constants import CHUNK_SIZE
from backup_util.exceptions import BackupUtilityError


class BackupEncryptor:
    """Provides AES-256 encryption and decryption for backup files using PBKDF2 key derivation."""

    SALT_SIZE = 16

    @classmethod
    def generate_key_from_passphrase(cls, passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return key

    @classmethod
    def encrypt_file(cls, src_path: str, dest_path: str, passphrase: str) -> None:
        """Encrypts a file with AES-256 Fernet, embedding the random salt in the header."""
        salt = os.urandom(cls.SALT_SIZE)
        key = cls.generate_key_from_passphrase(passphrase, salt)
        fernet = Fernet(key)

        with open(src_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(b"BACKUP_ENC_V1")
            dst.write(salt)
            data = src.read()
            encrypted = fernet.encrypt(data)
            dst.write(encrypted)

    @classmethod
    def decrypt_file(cls, src_path: str, dest_path: str, passphrase: str) -> None:
        """Decrypts an encrypted backup file."""
        with open(src_path, "rb") as src:
            magic = src.read(13)
            if magic != b"BACKUP_ENC_V1":
                raise BackupUtilityError("File is not encrypted with Backup Utility V1 encryption.")
            salt = src.read(cls.SALT_SIZE)
            encrypted = src.read()

        key = cls.generate_key_from_passphrase(passphrase, salt)
        fernet = Fernet(key)
        try:
            decrypted = fernet.decrypt(encrypted)
        except Exception as e:
            raise BackupUtilityError("Failed to decrypt backup. Invalid password/key or corrupted file.") from e

        with open(dest_path, "wb") as dst:
            dst.write(decrypted)
