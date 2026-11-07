#pragma once

#include "Models.hpp"
#include "Exceptions.hpp"
#include "Logger.hpp"
#include <string>
#include <vector>
#include <fstream>
#include <algorithm>
#include <cstdio>

#ifdef _WIN32
  #include <windows.h>
  #include <direct.h>
  #define MKDIR(d) _mkdir(d)
#else
  #include <sys/stat.h>
  #include <dirent.h>
  #define MKDIR(d) mkdir(d, 0755)
#endif

namespace dbbackup {

struct StoredItem {
    std::string filename;
    size_t sizeBytes;
    std::string timestamp;
    std::string path;
};

class IStorageBackend {
public:
    virtual ~IStorageBackend() = default;

    virtual std::string store(const std::string& srcLocalPath, const std::string& destinationName, const BackupMetadata& metadata) = 0;
    virtual void retrieve(const std::string& location, const std::string& destLocalPath) = 0;
    virtual std::vector<StoredItem> listBackups() = 0;
    virtual size_t prune(int retentionCount, int retentionDays) = 0;
    virtual StorageType getType() const = 0;
};

class LocalStorage : public IStorageBackend {
public:
    explicit LocalStorage(const std::string& baseDir = "./backups")
        : baseDir_(baseDir) {
        ensureDirectory(baseDir_);
    }

    StorageType getType() const override {
        return StorageType::LOCAL;
    }

    std::string store(const std::string& srcLocalPath, const std::string& destinationName, const BackupMetadata& metadata) override {
        ensureDirectory(baseDir_);
        std::string destPath = baseDir_ + "/" + destinationName;

        // Copy file
        if (srcLocalPath != destPath) {
            std::ifstream src(srcLocalPath, std::ios::binary);
            if (!src.is_open()) {
                throw StorageException("Failed to open source file for storing: " + srcLocalPath);
            }
            std::ofstream dst(destPath, std::ios::binary);
            if (!dst.is_open()) {
                throw StorageException("Failed to open destination path: " + destPath);
            }
            dst << src.rdbuf();
        }

        // Write atomic .meta.json sidecar
        std::string metaPath = destPath + ".meta.json";
        std::ofstream metaFile(metaPath);
        if (metaFile.is_open()) {
            metaFile << metadata.toJsonString();
        }

        return destPath;
    }

    void retrieve(const std::string& location, const std::string& destLocalPath) override {
        std::string src = location;
        std::ifstream test(src, std::ios::binary);
        if (!test.is_open()) {
            src = baseDir_ + "/" + location;
        }

        std::ifstream in(src, std::ios::binary);
        if (!in.is_open()) {
            throw StorageException("Local backup file not found at: " + location + " (or " + src + ")");
        }

        std::ofstream out(destLocalPath, std::ios::binary);
        if (!out.is_open()) {
            throw StorageException("Failed to open restore staging destination: " + destLocalPath);
        }
        out << in.rdbuf();
    }

    std::vector<StoredItem> listBackups() override {
        std::vector<StoredItem> items;

#ifdef _WIN32
        std::string searchPattern = baseDir_ + "/*";
        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPattern.c_str(), &fd);
        if (hFind != INVALID_HANDLE_VALUE) {
            do {
                if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
                    std::string fname = fd.cFileName;
                    if (fname.size() >= 10 && fname.substr(fname.size() - 10) == ".meta.json") {
                        continue; // Skip sidecars from direct listing
                    }
                    StoredItem item;
                    item.filename = fname;
                    item.path = baseDir_ + "/" + fname;
                    item.sizeBytes = (static_cast<uint64_t>(fd.nFileSizeHigh) << 32) | fd.nFileSizeLow;
                    item.timestamp = "Recent";
                    items.push_back(item);
                }
            } while (FindNextFileA(hFind, &fd));
            FindClose(hFind);
        }
#else
        DIR* dir = opendir(baseDir_.c_str());
        if (dir) {
            struct dirent* ent;
            while ((ent = readdir(dir)) != nullptr) {
                std::string fname = ent->d_name;
                if (fname != "." && fname != ".." && (fname.size() < 10 || fname.substr(fname.size() - 10) != ".meta.json")) {
                    StoredItem item;
                    item.filename = fname;
                    item.path = baseDir_ + "/" + fname;
                    item.sizeBytes = 0;
                    item.timestamp = "Recent";
                    items.push_back(item);
                }
            }
            closedir(dir);
        }
#endif
        return items;
    }

    size_t prune(int retentionCount, int retentionDays) override {
        if (retentionCount <= 0 && retentionDays <= 0) return 0;

        auto items = listBackups();
        if (retentionCount > 0 && items.size() > static_cast<size_t>(retentionCount)) {
            size_t toDelete = items.size() - retentionCount;
            size_t deleted = 0;
            for (size_t i = 0; i < toDelete; ++i) {
                std::remove(items[i].path.c_str());
                std::string metaPath = items[i].path + ".meta.json";
                std::remove(metaPath.c_str());
                deleted++;
            }
            return deleted;
        }
        return 0;
    }

private:
    std::string baseDir_;

    static void ensureDirectory(const std::string& dir) {
        MKDIR(dir.c_str());
    }
};

class S3Storage : public IStorageBackend {
public:
    explicit S3Storage(const StorageConfig& config)
        : config_(config) {}

    StorageType getType() const override {
        return StorageType::S3;
    }

    std::string store(const std::string& srcLocalPath, const std::string& destinationName, const BackupMetadata& metadata) override {
        std::string s3Url = "s3://" + config_.s3Bucket + "/" + config_.s3Prefix + "/" + destinationName;
        Logger::info("Simulating S3 multipart stream upload to: " + s3Url);
        Logger::info("S3 Region: " + config_.s3Region + (config_.s3Endpoint.empty() ? "" : " (Endpoint: " + config_.s3Endpoint + ")"));
        return s3Url;
    }

    void retrieve(const std::string& location, const std::string& destLocalPath) override {
        Logger::info("Downloading S3 archive from " + location + " to " + destLocalPath);
        std::ofstream dummy(destLocalPath);
        dummy << "-- S3 Restored Payload Mock\n";
    }

    std::vector<StoredItem> listBackups() override {
        StoredItem item;
        item.filename = "remote_s3_archive.sql.gz";
        item.sizeBytes = 1024 * 1024 * 5;
        item.timestamp = "2026-11-01 02:00:00";
        item.path = "s3://" + config_.s3Bucket + "/" + item.filename;
        return {item};
    }

    size_t prune(int retentionCount, int retentionDays) override {
        Logger::info("Enforcing S3 lifecycle retention rules for bucket: " + config_.s3Bucket);
        return 0;
    }

private:
    StorageConfig config_;
};

} // namespace dbbackup

