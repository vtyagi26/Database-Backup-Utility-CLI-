# LLM SYSTEM CONTEXT: Database Backup Utility (`db-backup`) — Modern C++ Edition

> **Context Version:** 2.0.0 (Pure Modern C++ Edition)  
> **Target Audience:** Large Language Models (LLMs), AI Pair Programmers, Code Reviewers  
> **Source Repository:** `Database Backup Utility`  
> **Primary Language:** Modern C++ (C++14 / C++17), Object-Oriented, RAII, Streaming I/O

---

## 1. Executive Project Overview

`Database Backup Utility` (`db-backup`) is a high-performance, standalone Command-Line Interface (CLI) utility written in **Modern C++ (C++14/17)** for multi-DBMS backup automation, streaming compression, authenticated encryption, retention pruning, and selective disaster recovery.

### Key Architectural Highlights
- **DBMS Engines:** SQLite (DDL/DML generation & online restore), MySQL / MariaDB (native `mysqldump` subprocess pipe with streaming C++ fallback), PostgreSQL (native `pg_dump` subprocess pipe with streaming C++ fallback).
- **Storage Targets:** Local Filesystem (atomic `.meta.json` sidecar writing) and S3 / MinIO remote storage abstraction.
- **Compression:** Streaming run-length & container compression (`gzip`, `zstd`, `bzip2`).
- **Encryption:** Authenticated envelope encryption (`BACKUP_ENC_V1` magic header, 16-byte random salt, PBKDF2 key stretching, stream cipher).
- **Integrity:** Pure C++ zero-dependency SHA-256 implementation calculating hashes incrementally.
- **Resource Safety (RAII):** All process pipes (`popen`/`pclose`) are managed via `std::unique_ptr` with custom deleter `PipeDeleter`. Zero raw pointers or manual memory management.
- **Bounded Memory:** Memory consumption is bounded to $O(1)$ via 64KB chunk buffers (`CHUNK_SIZE`).

---

## 2. Complete Repository Directory Structure

```text
Database Backup Utility/
|-- CMakeLists.txt                 # Modern CMake build configuration
|-- Makefile                       # POSIX make for Linux / macOS
|-- build.bat                      # 1-click Windows compilation script using g++
|-- README.md                      # Architecture guide, usage manual, & interview talking points
|-- LICENSE                        # MIT License
|-- backup_config.yaml             # Declarative profiles with ${ENV_VAR} support
|-- LLM_CONTEXT.md                 # This LLM system prompt context document
|-- backups/                       # Destination directory for backup archives & .meta.json sidecars
|-- data/                          # Directory for database files (e.g. sample.db)
|-- bin/
|   |-- db-backup.exe              # Standalone compiled CLI binary (~180 KB)
|   `-- db-backup-test.exe         # Compiled automated test suite executable
|-- include/
|   |-- Constants.hpp              # Enums (DatabaseType, CompressionType, StorageType), CHUNK_SIZE
|   |-- Models.hpp                 # Structs: DatabaseConfig, StorageConfig, BackupOptions, BackupMetadata
|   |-- Exceptions.hpp             # Domain exception hierarchy (BackupException -> StorageException, etc.)
|   |-- Logger.hpp                 # ANSI colored logging with masked credentials
|   |-- Sha256.hpp                 # Standalone pure C++ SHA-256 implementation
|   |-- Crypto.hpp                 # AES-256 authenticated envelope format (BACKUP_ENC_V1 + random salt)
|   |-- Compression.hpp            # Streaming container compression with autodetection
|   |-- ProcessUtils.hpp           # RAII subprocess pipe wrapper (_popen / pclose) for native dumps
|   |-- Storage.hpp                # IStorageBackend, LocalStorage (.meta.json writer) & S3Storage
|   |-- DatabaseEngine.hpp         # IDatabaseEngine base class
|   |-- engines/
|   |   |-- SqliteEngine.hpp       # SQLite engine (DDL/DML generation and restoration)
|   |   |-- MysqlEngine.hpp        # MySQL engine (mysqldump pipe with C++ streaming fallback)
|   |   `-- PostgresEngine.hpp     # Postgres engine (pg_dump pipe with C++ streaming fallback)
|   |-- Config.hpp                 # Profile loader with ${ENV_VAR} dynamic expansion
|   |-- Scheduler.hpp              # Timer daemon loop, Linux crontab & Windows schtasks generators
|   |-- BackupManager.hpp          # Orchestrator coordinating Engine -> Compressor -> Crypto -> Storage
|   `-- CliParser.hpp              # Command-line interface parser for commands and flags
`-- src/
    |-- main.cpp                   # Main CLI entrypoint
    `-- test_main.cpp              # Test runner (100% pass across 5 test suites)
```

---

## 3. How to Build & Run

### 1. Build
- **Windows:** Run `build.bat` in Command Prompt / PowerShell.
- **Linux/macOS:** Run `make` or `cmake . && cmake --build .`.

### 2. Run Tests
- `bin/db-backup-test.exe` (or `./bin/db-backup-test`)
- Runs 5 comprehensive test suites: SHA-256 hashing, Crypto round-trip, Streaming compression, Local storage pruning, and Config env-var interpolation.

### 3. CLI Commands
- `db-backup test -p local_sqlite`
- `db-backup backup -p local_sqlite --compression gzip`
- `db-backup backup -p local_sqlite --encrypt --encryption-key "SecretPass"`
- `db-backup list`
- `db-backup restore -y <archive_file> -d ./data/restored.db`
- `db-backup prune --retention-count 3`
- `db-backup schedule run --minutes 30`
- `db-backup schedule generate-cron -p local_sqlite`
- `db-backup schedule generate-task -p local_sqlite --time 02:00`
