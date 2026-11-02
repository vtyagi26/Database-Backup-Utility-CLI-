class BackupUtilityError(Exception):
    """Base exception for all Backup Utility errors."""
    def __init__(self, message: str, details: str = None, suggestion: str = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.suggestion = suggestion

    def __str__(self) -> str:
        parts = [self.message]
        if self.details:
            parts.append(f"\nDetails: {self.details}")
        if self.suggestion:
            parts.append(f"\nTip/Suggestion: {self.suggestion}")
        return "\n".join(parts)


class ConnectionFailedError(BackupUtilityError):
    """Raised when connecting to a database fails."""
    pass


class EngineNotFoundError(BackupUtilityError):
    """Raised when neither native tool nor driver engine is available."""
    pass


class BackupExecutionError(BackupUtilityError):
    """Raised when a backup operation fails."""
    pass


class RestoreExecutionError(BackupUtilityError):
    """Raised when a restore operation fails."""
    pass


class CompressionError(BackupUtilityError):
    """Raised when compression or decompression fails."""
    pass


class StorageError(BackupUtilityError):
    """Raised when storing or retrieving a backup fails."""
    pass


class ConfigurationError(BackupUtilityError):
    """Raised when configuration or CLI parameters are invalid."""
    pass


class IntegrityError(BackupUtilityError):
    """Raised when checksum verification fails."""
    pass
