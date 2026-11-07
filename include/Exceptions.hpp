#pragma once

#include <stdexcept>
#include <string>

namespace dbbackup {

class BackupException : public std::runtime_error {
public:
    explicit BackupException(const std::string& message)
        : std::runtime_error(message) {}
};

class ConnectionException : public BackupException {
public:
    explicit ConnectionException(const std::string& message)
        : BackupException("Database Connection Error: " + message) {}
};

class EngineException : public BackupException {
public:
    explicit EngineException(const std::string& message)
        : BackupException("Engine Execution Error: " + message) {}
};

class StorageException : public BackupException {
public:
    explicit StorageException(const std::string& message)
        : BackupException("Storage Error: " + message) {}
};

class CryptoException : public BackupException {
public:
    explicit CryptoException(const std::string& message)
        : BackupException("Cryptography Error: " + message) {}
};

class CompressionException : public BackupException {
public:
    explicit CompressionException(const std::string& message)
        : BackupException("Compression Error: " + message) {}
};

class ConfigException : public BackupException {
public:
    explicit ConfigException(const std::string& message)
        : BackupException("Configuration Error: " + message) {}
};

} // namespace dbbackup

