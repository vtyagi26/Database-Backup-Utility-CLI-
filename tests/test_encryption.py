import os
import tempfile
import pytest

from backup_util.crypto.encryptor import BackupEncryptor
from backup_util.exceptions import BackupUtilityError


def test_encryption_decryption_success():
    payload = b"Top secret database backup data 987654321!"
    passphrase = "UltraSecurePassword123#$"

    with tempfile.NamedTemporaryFile(delete=False) as raw, \
         tempfile.NamedTemporaryFile(delete=False) as enc, \
         tempfile.NamedTemporaryFile(delete=False) as dec:
        raw_p = raw.name
        enc_p = enc.name
        dec_p = dec.name

    try:
        with open(raw_p, "wb") as f:
            f.write(payload)

        BackupEncryptor.encrypt_file(raw_p, enc_p, passphrase)
        assert os.path.getsize(enc_p) > len(payload)

        BackupEncryptor.decrypt_file(enc_p, dec_p, passphrase)
        with open(dec_p, "rb") as f:
            assert f.read() == payload
    finally:
        for p in [raw_p, enc_p, dec_p]:
            if os.path.exists(p):
                os.unlink(p)


def test_encryption_decryption_wrong_key():
    payload = b"Sample backup data"
    with tempfile.NamedTemporaryFile(delete=False) as raw, \
         tempfile.NamedTemporaryFile(delete=False) as enc, \
         tempfile.NamedTemporaryFile(delete=False) as dec:
        raw_p = raw.name
        enc_p = enc.name
        dec_p = dec.name

    try:
        with open(raw_p, "wb") as f:
            f.write(payload)

        BackupEncryptor.encrypt_file(raw_p, enc_p, "CorrectPassphrase")
        with pytest.raises(BackupUtilityError):
            BackupEncryptor.decrypt_file(enc_p, dec_p, "WrongPassphrase")
    finally:
        for p in [raw_p, enc_p, dec_p]:
            if os.path.exists(p):
                os.unlink(p)
