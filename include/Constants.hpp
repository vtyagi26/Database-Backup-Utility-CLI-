#pragma once

#include <string>
#include <algorithm>

namespace dbbackup {

constexpr size_t CHUNK_SIZE = 64 * 1024; // 64 KB streaming buffer

enum class DatabaseType {
    SQLITE,
    MYSQL,
    POSTGRES,
    MONGODB,
    UNKNOWN
};

enum class CompressionType {
    NONE,
    GZIP,
    ZSTD,
    BZIP2
};

enum class StorageType {
    LOCAL,
    S3,
    GCS,
    AZURE
};

enum class BackupType {
    FULL,
    INCREMENTAL,
    DIFFERENTIAL
};

enum class BackupStatus {
    PENDING,
    RUNNING,
    COMPLETED,
    FAILED
};

inline std::string toString(DatabaseType type) {
    switch (type) {
        case DatabaseType::SQLITE:   return "sqlite";
        case DatabaseType::MYSQL:    return "mysql";
        case DatabaseType::POSTGRES: return "postgres";
        case DatabaseType::MONGODB:  return "mongodb";
        default:                     return "unknown";
    }
}

inline DatabaseType parseDatabaseType(const std::string& str) {
    std::string lower = str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower == "sqlite" || lower == "sqlite3") return DatabaseType::SQLITE;
    if (lower == "mysql" || lower == "mariadb") return DatabaseType::MYSQL;
    if (lower == "postgres" || lower == "postgresql" || lower == "pg") return DatabaseType::POSTGRES;
    if (lower == "mongo" || lower == "mongodb") return DatabaseType::MONGODB;
    return DatabaseType::UNKNOWN;
}

inline std::string toString(CompressionType comp) {
    switch (comp) {
        case CompressionType::GZIP:  return "gzip";
        case CompressionType::ZSTD:  return "zstd";
        case CompressionType::BZIP2: return "bzip2";
        default:                     return "none";
    }
}

inline CompressionType parseCompressionType(const std::string& str) {
    std::string lower = str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower == "gzip" || lower == "gz") return CompressionType::GZIP;
    if (lower == "zstd" || lower == "zst") return CompressionType::ZSTD;
    if (lower == "bzip2" || lower == "bz2") return CompressionType::BZIP2;
    return CompressionType::NONE;
}

inline std::string toString(StorageType st) {
    switch (st) {
        case StorageType::LOCAL: return "local";
        case StorageType::S3:    return "s3";
        case StorageType::GCS:   return "gcs";
        case StorageType::AZURE: return "azure";
        default:                 return "local";
    }
}

inline StorageType parseStorageType(const std::string& str) {
    std::string lower = str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower == "s3") return StorageType::S3;
    if (lower == "gcs") return StorageType::GCS;
    if (lower == "azure") return StorageType::AZURE;
    return StorageType::LOCAL;
}

inline std::string toString(BackupType bt) {
    switch (bt) {
        case BackupType::FULL:         return "full";
        case BackupType::INCREMENTAL:  return "incremental";
        case BackupType::DIFFERENTIAL: return "differential";
        default:                       return "full";
    }
}

inline BackupType parseBackupType(const std::string& str) {
    std::string lower = str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower == "incremental") return BackupType::INCREMENTAL;
    if (lower == "differential") return BackupType::DIFFERENTIAL;
    return BackupType::FULL;
}

} // namespace dbbackup

