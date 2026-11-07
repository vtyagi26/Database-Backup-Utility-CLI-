#pragma once

#include "Constants.hpp"
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>

namespace dbbackup {

struct DatabaseConfig {
    DatabaseType dbType = DatabaseType::SQLITE;
    std::string host = "localhost";
    int port = 0;
    std::string username = "";
    std::string password = "";
    std::string database = "";
    std::string uri = "";

    std::string getMaskedPassword() const {
        return password.empty() ? "" : "********";
    }

    std::string getDisplayDescription() const {
        std::ostringstream ss;
        ss << toString(dbType) << "://";
        if (!username.empty()) ss << username << "@";
        ss << host;
        if (port > 0) ss << ":" << port;
        ss << "/" << database;
        return ss.str();
    }
};

struct StorageConfig {
    StorageType storageType = StorageType::LOCAL;
    std::string localPath = "./backups";
    std::string s3Bucket = "";
    std::string s3Prefix = "db-backups";
    std::string s3Region = "us-east-1";
    std::string s3Endpoint = "";
};

struct BackupOptions {
    BackupType backupType = BackupType::FULL;
    CompressionType compression = CompressionType::GZIP;
    int compressionLevel = 6;
    bool encrypt = false;
    std::string encryptionKey = "";
    std::vector<std::string> tables;
    int retentionCount = 0;
    int retentionDays = 0;
};

struct BackupMetadata {
    std::string backupId = "";
    std::string dbType = "";
    std::string databaseName = "";
    std::string filename = "";
    std::string backupType = "full";
    size_t uncompressedSizeBytes = 0;
    size_t compressedSizeBytes = 0;
    std::string checksumSha256 = "";
    std::string timestamp = "";
    double durationSeconds = 0.0;
    bool isEncrypted = false;
    std::string compressionAlgorithm = "none";
    std::vector<std::string> tables;

    std::string toJsonString() const {
        std::ostringstream ss;
        ss << "{\n";
        ss << "  \"backup_id\": \"" << backupId << "\",\n";
        ss << "  \"db_type\": \"" << dbType << "\",\n";
        ss << "  \"database\": \"" << databaseName << "\",\n";
        ss << "  \"filename\": \"" << filename << "\",\n";
        ss << "  \"backup_type\": \"" << backupType << "\",\n";
        ss << "  \"uncompressed_bytes\": " << uncompressedSizeBytes << ",\n";
        ss << "  \"compressed_bytes\": " << compressedSizeBytes << ",\n";
        ss << "  \"checksum_sha256\": \"" << checksumSha256 << "\",\n";
        ss << "  \"timestamp\": \"" << timestamp << "\",\n";
        ss << "  \"duration_sec\": " << std::fixed << std::setprecision(2) << durationSeconds << ",\n";
        ss << "  \"is_encrypted\": " << (isEncrypted ? "true" : "false") << ",\n";
        ss << "  \"compression\": \"" << compressionAlgorithm << "\",\n";
        ss << "  \"tables\": [";
        for (size_t i = 0; i < tables.size(); ++i) {
            ss << "\"" << tables[i] << "\"";
            if (i + 1 < tables.size()) ss << ", ";
        }
        ss << "]\n";
        ss << "}\n";
        return ss.str();
    }
};

} // namespace dbbackup
