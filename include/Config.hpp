#pragma once

#include "Models.hpp"
#include "Exceptions.hpp"
#include <string>
#include <unordered_map>
#include <fstream>
#include <sstream>
#include <cstdlib>

namespace dbbackup {

struct ProfileConfig {
    DatabaseConfig db;
    StorageConfig storage;
    BackupOptions options;
};

class ConfigManager {
public:
    static std::string interpolateEnvVars(const std::string& input) {
        std::string result = input;
        size_t startPos = 0;
        while ((startPos = result.find("${", startPos)) != std::string::npos) {
            size_t endPos = result.find("}", startPos);
            if (endPos != std::string::npos) {
                std::string varName = result.substr(startPos + 2, endPos - startPos - 2);
                const char* envVal = std::getenv(varName.c_str());
                std::string replacement = envVal ? envVal : "";
                result.replace(startPos, endPos - startPos + 1, replacement);
                startPos += replacement.length();
            } else {
                break;
            }
        }
        return result;
    }

    static ProfileConfig getDefaultProfile() {
        ProfileConfig profile;
        profile.db.dbType = DatabaseType::SQLITE;
        profile.db.database = "./data/sample.db";
        profile.storage.storageType = StorageType::LOCAL;
        profile.storage.localPath = "./backups";
        profile.options.backupType = BackupType::FULL;
        profile.options.compression = CompressionType::GZIP;
        return profile;
    }

    static std::unordered_map<std::string, ProfileConfig> loadProfiles(const std::string& configPath) {
        std::unordered_map<std::string, ProfileConfig> profiles;
        // Seed standard default profiles
        profiles["local_sqlite"] = getDefaultProfile();

        ProfileConfig mysqlProf;
        mysqlProf.db.dbType = DatabaseType::MYSQL;
        mysqlProf.db.host = "localhost";
        mysqlProf.db.port = 3306;
        mysqlProf.db.username = "root";
        mysqlProf.db.database = "production_db";
        mysqlProf.storage.storageType = StorageType::LOCAL;
        mysqlProf.storage.localPath = "./backups/mysql";
        profiles["production_mysql"] = mysqlProf;

        ProfileConfig pgProf;
        pgProf.db.dbType = DatabaseType::POSTGRES;
        pgProf.db.host = "localhost";
        pgProf.db.port = 5432;
        pgProf.db.username = "postgres";
        pgProf.db.database = "analytics_db";
        pgProf.storage.storageType = StorageType::LOCAL;
        pgProf.storage.localPath = "./backups/postgres";
        profiles["analytics_postgres"] = pgProf;

        return profiles;
    }
};

} // namespace dbbackup

