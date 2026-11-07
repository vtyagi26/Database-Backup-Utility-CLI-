#pragma once

#include "Models.hpp"
#include "Constants.hpp"
#include "Exceptions.hpp"
#include "Logger.hpp"
#include "DatabaseEngine.hpp"
#include "engines/SqliteEngine.hpp"
#include "engines/MysqlEngine.hpp"
#include "engines/PostgresEngine.hpp"
#include "Storage.hpp"
#include "Compression.hpp"
#include "Crypto.hpp"
#include "Sha256.hpp"

#include <memory>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

namespace dbbackup {

class BackupManager {
public:
    BackupManager(const DatabaseConfig& dbCfg, const StorageConfig& storageCfg, const BackupOptions& options)
        : dbConfig_(dbCfg), storageConfig_(storageCfg), options_(options) {
        engine_ = createEngine(dbConfig_);
        storage_ = createStorage(storageConfig_);
        compressor_ = std::make_unique<StreamingCompressor>(options_.compression);
    }

    bool testConnection(std::string& outDetails) {
        return engine_->testConnection(outDetails);
    }

    BackupMetadata runBackup() {
        auto startTime = std::chrono::steady_clock::now();
        std::string timestampStr = getCurrentTimestampString();
        std::string cleanName = sanitizeDbName(dbConfig_.database);
        std::string backupId = cleanName + "_" + toString(options_.backupType) + "_" + timestampStr;

        Logger::info("Starting backup operation [" + backupId + "] for " + toString(dbConfig_.dbType) + "...");

        // 1. Pre-flight check
        std::string connDetails;
        if (!engine_->testConnection(connDetails)) {
            throw ConnectionException("Pre-flight connection test failed: " + connDetails);
        }
        Logger::info("Pre-flight check passed: " + connDetails);

        // Ensure backups directory exists
        MKDIR(storageConfig_.localPath.c_str());

        // Staging raw path
        std::string stagingRaw = storageConfig_.localPath + "/" + backupId + ".sql";
        std::string stagingCompressed = stagingRaw + compressor_->getExtension();
        std::string finalStaging = stagingCompressed;

        // 2. Dump from database engine
        Logger::info("Dumping database schema and records...");
        std::vector<std::string> backedUpTables;
        {
            std::ofstream rawOut(stagingRaw, std::ios::binary);
            if (!rawOut.is_open()) {
                throw BackupException("Failed to open staging dump file: " + stagingRaw);
            }
            engine_->backup(rawOut, options_, backedUpTables);
        }

        // 3. Streaming Compression
        size_t uncompressedBytes = 0;
        size_t compressedBytes = 0;
        Logger::info("Compressing payload using " + toString(options_.compression) + "...");
        compressor_->compressFile(stagingRaw, stagingCompressed, uncompressedBytes, compressedBytes);

        // Remove raw dump
        std::remove(stagingRaw.c_str());

        // 4. Optional Encryption
        bool isEncrypted = false;
        if (options_.encrypt && !options_.encryptionKey.empty()) {
            Logger::info("Encrypting backup payload using AES-256 (PBKDF2 key derivation)...");
            std::string stagingEncrypted = stagingCompressed + ".enc";
            Crypto::encryptFile(stagingCompressed, stagingEncrypted, options_.encryptionKey);
            std::remove(stagingCompressed.c_str());
            finalStaging = stagingEncrypted;
            isEncrypted = true;
        }

        // 5. Compute SHA-256 Checksum
        std::string checksum = Sha256::hashFile(finalStaging);
        Logger::info("Calculated SHA-256 Checksum: " + checksum);

        // 6. Build Metadata
        auto endTime = std::chrono::steady_clock::now();
        double durationSec = std::chrono::duration<double>(endTime - startTime).count();

        std::string destFileName = finalStaging.substr(finalStaging.find_last_of("/\\") + 1);

        BackupMetadata meta;
        meta.backupId = backupId;
        meta.dbType = toString(dbConfig_.dbType);
        meta.databaseName = cleanName;
        meta.filename = destFileName;
        meta.backupType = toString(options_.backupType);
        meta.uncompressedSizeBytes = uncompressedBytes;
        meta.compressedSizeBytes = compressedBytes;
        meta.checksumSha256 = checksum;
        meta.timestamp = timestampStr;
        meta.durationSeconds = durationSec;
        meta.isEncrypted = isEncrypted;
        meta.compressionAlgorithm = toString(options_.compression);
        meta.tables = backedUpTables;

        // 7. Store to Storage Backend
        Logger::info("Storing archive to " + toString(storageConfig_.storageType) + " storage...");
        std::string finalLocation = storage_->store(finalStaging, destFileName, meta);

        // 8. Retention Pruning
        if (options_.retentionCount > 0 || options_.retentionDays > 0) {
            size_t pruned = storage_->prune(options_.retentionCount, options_.retentionDays);
            if (pruned > 0) {
                Logger::info("Pruned " + std::to_string(pruned) + " older backup archives matching retention policy.");
            }
        }

        Logger::success("Backup operation completed successfully in " + std::to_string(durationSec) + "s!");
        return meta;
    }

    bool runRestore(const std::string& backupFile, const std::string& encryptionKey, const std::vector<std::string>& tables, std::string& outDetails) {
        Logger::info("Starting restore operation from: " + backupFile);

        std::string stagingTarget = storageConfig_.localPath + "/temp_restore_staged.bin";
        storage_->retrieve(backupFile, stagingTarget);

        std::string currentFile = stagingTarget;

        // 1. Decrypt if encrypted (.enc or contains magic header)
        bool isEncrypted = (backupFile.size() >= 4 && backupFile.substr(backupFile.size() - 4) == ".enc");
        if (isEncrypted) {
            if (encryptionKey.empty()) {
                throw CryptoException("Archive is encrypted (.enc) but no encryption key was provided (--encryption-key).");
            }
            Logger::info("Decrypting encrypted archive using passphrase...");
            std::string decrypted = storageConfig_.localPath + "/temp_decrypted.bin";
            Crypto::decryptFile(currentFile, decrypted, encryptionKey);
            std::remove(currentFile.c_str());
            currentFile = decrypted;
        }

        // 2. Decompress
        std::string uncompressed = storageConfig_.localPath + "/temp_uncompressed.sql";
        size_t uncompBytes = 0;
        Logger::info("Decompressing backup stream...");
        compressor_->decompressFile(currentFile, uncompressed, uncompBytes);
        std::remove(currentFile.c_str());

        // 3. Restore into target database engine
        Logger::info("Restoring payload into " + toString(dbConfig_.dbType) + " (" + dbConfig_.database + ")...");
        BackupOptions restoreOpts = options_;
        if (!tables.empty()) {
            restoreOpts.tables = tables;
        }

        std::ifstream sqlStream(uncompressed);
        bool ok = engine_->restore(sqlStream, restoreOpts, outDetails);
        sqlStream.close();
        std::remove(uncompressed.c_str());

        if (ok) {
            Logger::success("Database restore completed successfully!");
        }
        return ok;
    }

    std::vector<StoredItem> listBackups() {
        return storage_->listBackups();
    }

    size_t pruneBackups(int retentionCount, int retentionDays) {
        return storage_->prune(retentionCount, retentionDays);
    }

private:
    DatabaseConfig dbConfig_;
    StorageConfig storageConfig_;
    BackupOptions options_;

    std::unique_ptr<IDatabaseEngine> engine_;
    std::unique_ptr<IStorageBackend> storage_;
    std::unique_ptr<ICompressor> compressor_;

    static std::string sanitizeDbName(const std::string& dbPath) {
        size_t lastSlash = dbPath.find_last_of("/\\");
        std::string name = (lastSlash != std::string::npos) ? dbPath.substr(lastSlash + 1) : dbPath;
        size_t dot = name.find_last_of('.');
        if (dot != std::string::npos && dot > 0) {
            name = name.substr(0, dot);
        }
        return name.empty() ? "database" : name;
    }

    static std::unique_ptr<IDatabaseEngine> createEngine(const DatabaseConfig& cfg) {
        switch (cfg.dbType) {
            case DatabaseType::SQLITE:
                return std::make_unique<SqliteEngine>(cfg);
            case DatabaseType::MYSQL:
                return std::make_unique<MysqlEngine>(cfg);
            case DatabaseType::POSTGRES:
                return std::make_unique<PostgresEngine>(cfg);
            default:
                return std::make_unique<SqliteEngine>(cfg);
        }
    }

    static std::unique_ptr<IStorageBackend> createStorage(const StorageConfig& cfg) {
        switch (cfg.storageType) {
            case StorageType::S3:
                return std::make_unique<S3Storage>(cfg);
            case StorageType::LOCAL:
            default:
                return std::make_unique<LocalStorage>(cfg.localPath);
        }
    }

    static std::string getCurrentTimestampString() {
        auto now = std::time(nullptr);
        std::tm* tmNow = std::localtime(&now);
        char buf[64] = {0};
        if (tmNow) {
            std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", tmNow);
        } else {
            std::snprintf(buf, sizeof(buf), "backup");
        }
        return std::string(buf);
    }
};

} // namespace dbbackup
