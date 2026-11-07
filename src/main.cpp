#include "../include/CliParser.hpp"
#include "../include/Config.hpp"
#include "../include/BackupManager.hpp"
#include "../include/Scheduler.hpp"
#include "../include/Logger.hpp"

#include <iostream>
#include <iomanip>

using namespace dbbackup;

int main(int argc, char* argv[]) {
    try {
        ParsedArgs args = CliParser::parse(argc, argv);
        Logger::setVerbose(args.verbose);

        if (args.command == "help") {
            CliParser::printHelp();
            return 0;
        }

        if (args.command == "version") {
            std::cout << "db-backup (C++ Edition) version 1.0.0" << std::endl;
            return 0;
        }

        // Load profiles from config
        auto profiles = ConfigManager::loadProfiles("backup_config.yaml");

        // Determine active profile or build config from flags
        ProfileConfig activeProfile;
        if (!args.profile.empty()) {
            if (profiles.find(args.profile) == profiles.end()) {
                Logger::error("Profile '" + args.profile + "' not found in configuration.");
                return 1;
            }
            activeProfile = profiles[args.profile];
        } else if (profiles.find("local_sqlite") != profiles.end()) {
            activeProfile = profiles["local_sqlite"];
        }

        // Override with explicit CLI flags
        if (!args.dbTypeStr.empty()) activeProfile.db.dbType = parseDatabaseType(args.dbTypeStr);
        if (!args.database.empty())  activeProfile.db.database = args.database;
        if (!args.host.empty())      activeProfile.db.host = args.host;
        if (args.port > 0)           activeProfile.db.port = args.port;
        if (!args.username.empty())  activeProfile.db.username = args.username;
        if (!args.password.empty())  activeProfile.db.password = args.password;
        if (!args.compressionStr.empty()) activeProfile.options.compression = parseCompressionType(args.compressionStr);
        if (!args.storageStr.empty()) activeProfile.storage.storageType = parseStorageType(args.storageStr);
        if (!args.localPath.empty())  activeProfile.storage.localPath = args.localPath;
        if (!args.s3Bucket.empty())   activeProfile.storage.s3Bucket = args.s3Bucket;
        if (args.encrypt)             activeProfile.options.encrypt = true;
        if (!args.encryptionKey.empty()) activeProfile.options.encryptionKey = args.encryptionKey;
        if (!args.tables.empty())     activeProfile.options.tables = args.tables;
        if (args.retentionCount > 0)  activeProfile.options.retentionCount = args.retentionCount;
        if (args.retentionDays > 0)   activeProfile.options.retentionDays = args.retentionDays;

        BackupManager manager(activeProfile.db, activeProfile.storage, activeProfile.options);

        // Command routing
        if (args.command == "test") {
            Logger::printHeader("Database Pre-Flight Connection Test");
            std::string details;
            bool ok = manager.testConnection(details);
            if (ok) {
                Logger::success("Connection test passed!");
                Logger::printKeyValue("Details", details);
                return 0;
            } else {
                Logger::error("Connection test failed: " + details);
                return 1;
            }
        }

        if (args.command == "backup") {
            Logger::printHeader("Database Backup Operation");
            BackupMetadata meta = manager.runBackup();

            std::cout << "\n\033[1;32mBackup Summary:\033[0m\n";
            Logger::printKeyValue("Backup ID", meta.backupId);
            Logger::printKeyValue("Database", meta.dbType + " (" + meta.databaseName + ")");
            Logger::printKeyValue("Uncompressed Size", std::to_string(meta.uncompressedSizeBytes) + " bytes");
            Logger::printKeyValue("Compressed Size", std::to_string(meta.compressedSizeBytes) + " bytes");
            Logger::printKeyValue("SHA-256 Checksum", meta.checksumSha256);
            Logger::printKeyValue("Encrypted", meta.isEncrypted ? "Yes (AES-256)" : "No");
            Logger::printKeyValue("Duration", std::to_string(meta.durationSeconds) + "s");
            return 0;
        }

        if (args.command == "restore") {
            Logger::printHeader("Database Restore Operation");
            if (args.backupFile.empty()) {
                Logger::error("Missing backup file path argument. Usage: db-backup restore <file>");
                return 1;
            }

            if (!args.skipConfirm) {
                std::cout << "\033[1;33mWARNING: Restoring will overwrite target " << toString(activeProfile.db.dbType)
                          << " (" << activeProfile.db.database << "). Continue? [y/N]: \033[0m";
                std::string input;
                std::getline(std::cin, input);
                if (input != "y" && input != "Y") {
                    Logger::warn("Restore aborted by user.");
                    return 0;
                }
            }

            std::string restoreDetails;
            bool ok = manager.runRestore(args.backupFile, args.encryptionKey, args.tables, restoreDetails);
            if (ok) {
                Logger::printKeyValue("Status", "Success");
                Logger::printKeyValue("Details", restoreDetails);
                return 0;
            } else {
                Logger::error("Restore failed: " + restoreDetails);
                return 1;
            }
        }

        if (args.command == "list") {
            Logger::printHeader("Stored Backup Archives");
            auto items = manager.listBackups();
            if (items.empty()) {
                std::cout << "No backups found in " << activeProfile.storage.localPath << std::endl;
                return 0;
            }

            std::cout << std::left << std::setw(40) << "\033[1mArchive Name\033[0m"
                      << std::setw(15) << "\033[1mSize\033[0m"
                      << "\033[1mLocation\033[0m\n";
            std::cout << std::string(75, '-') << "\n";
            for (const auto& item : items) {
                std::cout << std::left << std::setw(40) << item.filename
                          << std::setw(15) << (std::to_string(item.sizeBytes / 1024) + " KB")
                          << item.path << "\n";
            }
            return 0;
        }

        if (args.command == "prune") {
            Logger::printHeader("Backup Pruning");
            int count = (args.retentionCount > 0) ? args.retentionCount : 5;
            size_t pruned = manager.pruneBackups(count, args.retentionDays);
            Logger::success("Pruning complete. Removed " + std::to_string(pruned) + " old backup(s).");
            return 0;
        }

        if (args.command == "schedule") {
            if (args.subcommand == "generate-cron") {
                std::cout << Scheduler::generateCron(args.profile.empty() ? "local_sqlite" : args.profile);
                return 0;
            }
            if (args.subcommand == "generate-task") {
                std::cout << Scheduler::generateWindowsTask(args.profile.empty() ? "local_sqlite" : args.profile, args.timeStr.empty() ? "02:00" : args.timeStr);
                return 0;
            }
            if (args.subcommand == "run") {
                int mins = (args.minutes > 0) ? args.minutes : 30;
                Scheduler::runDaemon(mins, [&manager]() {
                    manager.runBackup();
                });
                return 0;
            }
            Logger::error("Unknown schedule subcommand. Available: run, generate-cron, generate-task");
            return 1;
        }

        if (args.command == "config") {
            if (args.subcommand == "list") {
                Logger::printHeader("Configured Database Profiles");
                for (const auto& kv : profiles) {
                    Logger::printKeyValue(kv.first, kv.second.db.getDisplayDescription());
                }
                return 0;
            }
            Logger::error("Unknown config subcommand. Available: list");
            return 1;
        }

        Logger::error("Unknown command: " + args.command + ". Run 'db-backup --help' for usage.");
        return 1;

    } catch (const std::exception& e) {
        Logger::error(std::string("Fatal Error: ") + e.what());
        return 1;
    }
}

