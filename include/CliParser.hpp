#pragma once

#include "Models.hpp"
#include "Constants.hpp"
#include <string>
#include <vector>
#include <unordered_map>
#include <iostream>

namespace dbbackup {

struct ParsedArgs {
    std::string command = "help";
    std::string subcommand = "";
    std::string profile = "";
    std::string dbTypeStr = "";
    std::string host = "";
    int port = 0;
    std::string username = "";
    std::string password = "";
    std::string database = "";
    std::string uri = "";
    std::string compressionStr = "";
    std::string storageStr = "";
    std::string localPath = "";
    std::string s3Bucket = "";
    std::string s3Prefix = "";
    std::string s3Region = "";
    std::string s3Endpoint = "";
    bool encrypt = false;
    std::string encryptionKey = "";
    std::vector<std::string> tables;
    int retentionCount = 0;
    int retentionDays = 0;
    std::string backupFile = "";
    bool skipConfirm = false;
    bool verbose = false;
    int minutes = 0;
    std::string timeStr = "";
};

class CliParser {
public:
    static ParsedArgs parse(int argc, char* argv[]) {
        ParsedArgs args;
        if (argc < 2) {
            args.command = "help";
            return args;
        }

        std::string first = argv[1];
        if (first == "--help" || first == "-h") {
            args.command = "help";
            return args;
        }
        if (first == "--version") {
            args.command = "version";
            return args;
        }

        args.command = first;

        int idx = 2;
        // Check for subcommands (e.g. schedule run, config list)
        if (args.command == "schedule" || args.command == "config") {
            if (idx < argc && argv[idx][0] != '-') {
                args.subcommand = argv[idx];
                idx++;
            }
        }

        for (; idx < argc; ++idx) {
            std::string opt = argv[idx];
            if (opt == "-h" || opt == "--host") {
                if (idx + 1 < argc) args.host = argv[++idx];
            } else if (opt == "-P" || opt == "--port") {
                if (idx + 1 < argc) args.port = std::stoi(argv[++idx]);
            } else if (opt == "-u" || opt == "--username") {
                if (idx + 1 < argc) args.username = argv[++idx];
            } else if (opt == "-w" || opt == "--password") {
                if (idx + 1 < argc) args.password = argv[++idx];
            } else if (opt == "-d" || opt == "--database" || opt == "--db") {
                if (idx + 1 < argc) args.database = argv[++idx];
            } else if (opt == "-t" || opt == "--type") {
                if (idx + 1 < argc) args.dbTypeStr = argv[++idx];
            } else if (opt == "-p" || opt == "--profile") {
                if (idx + 1 < argc) args.profile = argv[++idx];
            } else if (opt == "--compression") {
                if (idx + 1 < argc) args.compressionStr = argv[++idx];
            } else if (opt == "--storage") {
                if (idx + 1 < argc) args.storageStr = argv[++idx];
            } else if (opt == "--local-path") {
                if (idx + 1 < argc) args.localPath = argv[++idx];
            } else if (opt == "--s3-bucket") {
                if (idx + 1 < argc) args.s3Bucket = argv[++idx];
            } else if (opt == "--s3-prefix") {
                if (idx + 1 < argc) args.s3Prefix = argv[++idx];
            } else if (opt == "--s3-region") {
                if (idx + 1 < argc) args.s3Region = argv[++idx];
            } else if (opt == "--s3-endpoint") {
                if (idx + 1 < argc) args.s3Endpoint = argv[++idx];
            } else if (opt == "--encrypt") {
                args.encrypt = true;
            } else if (opt == "--encryption-key") {
                if (idx + 1 < argc) args.encryptionKey = argv[++idx];
            } else if (opt == "--table") {
                if (idx + 1 < argc) args.tables.push_back(argv[++idx]);
            } else if (opt == "-y" || opt == "--yes") {
                args.skipConfirm = true;
            } else if (opt == "-v" || opt == "--verbose") {
                args.verbose = true;
            } else if (opt == "--retention-count") {
                if (idx + 1 < argc) args.retentionCount = std::stoi(argv[++idx]);
            } else if (opt == "--retention-days") {
                if (idx + 1 < argc) args.retentionDays = std::stoi(argv[++idx]);
            } else if (opt == "--minutes") {
                if (idx + 1 < argc) args.minutes = std::stoi(argv[++idx]);
            } else if (opt == "--time") {
                if (idx + 1 < argc) args.timeStr = argv[++idx];
            } else if (opt[0] != '-') {
                // Positional argument (e.g. restore file)
                args.backupFile = opt;
            }
        }

        return args;
    }

    static void printHelp() {
        std::cout << "\033[1;36mDatabase Backup Utility (C++ Edition)\033[0m\n";
        std::cout << "Version: 1.0.0 (Modern C++ Architecture)\n\n";
        std::cout << "\033[1mUsage:\033[0m db-backup <command> [subcommand] [options] [args]\n\n";
        std::cout << "\033[1mCommands:\033[0m\n";
        std::cout << "  test                     Validate database connectivity & diagnostics\n";
        std::cout << "  backup                   Execute full/incremental database backup\n";
        std::cout << "  restore <file>           Restore database from backup archive\n";
        std::cout << "  list                     List stored backup archives and metadata\n";
        std::cout << "  prune                    Clean up backups matching retention policy\n";
        std::cout << "  schedule <run|generate>  Background scheduler daemon & cron generators\n";
        std::cout << "  config <list|init>       Profile & configuration management\n\n";
        std::cout << "\033[1mOptions:\033[0m\n";
        std::cout << "  -p, --profile <name>     Select profile from backup_config.yaml\n";
        std::cout << "  -t, --type <db_type>     DBMS type: sqlite, mysql, postgres, mongodb\n";
        std::cout << "  -d, --database <db>      Target database name or SQLite file path\n";
        std::cout << "  -h, --host <host>        Database server host (default: localhost)\n";
        std::cout << "  -P, --port <port>        Database server port (e.g. 3306, 5432)\n";
        std::cout << "  -u, --username <user>    Database username\n";
        std::cout << "  -w, --password <pass>    Database password\n";
        std::cout << "      --compression <type> Compression format: gzip, zstd, bzip2, none\n";
        std::cout << "      --storage <type>     Storage backend: local, s3\n";
        std::cout << "      --local-path <path>  Local backup destination (default: ./backups)\n";
        std::cout << "      --encrypt            Encrypt backup with AES-256 Fernet envelope\n";
        std::cout << "      --encryption-key <k> Passphrase for AES-256 encryption\n";
        std::cout << "      --table <name>       Selective backup or restore of specific table\n";
        std::cout << "  -y, --yes                Skip interactive overwrite confirmation prompts\n";
        std::cout << "  -v, --verbose            Enable verbose debug logs\n";
    }
};

} // namespace dbbackup

