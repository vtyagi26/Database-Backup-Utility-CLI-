# Database Backup Utility (`db-backup`)

A high-performance, cross-platform Command-Line Interface (CLI) utility written in **Modern C++ (C++14/17)** for multi-DBMS backup automation, streaming compression, authenticated encryption, retention pruning, and selective disaster recovery.

---
Overview

1. **Object-Oriented Design & Polymorphic Abstractions:**
   - Abstract interfaces (`IDatabaseEngine`, `IStorageBackend`, `ICompressor`) with pure virtual functions and `std::unique_ptr` ownership semantics.
   - Clean Factory Pattern (`createEngine`, `createStorage`) decoupling CLI dispatch from concrete implementations.

2. **Strict RAII (Resource Acquisition Is Initialization):**
   - Custom deleter `PipeDeleter` wrapping OS pipes (`popen` / `pclose`) ensuring file handles are closed even when exceptions are thrown.
   - File streams (`std::ifstream`, `std::ofstream`) scoped to prevent resource leaks.

3. **Subprocess Pipe Architecture (Dual-Engine Concept):**
   - Spawns native database client binaries (`mysqldump`, `pg_dump`) via standard pipes, capturing streaming `stdout` directly without saving huge intermediate uncompressed files to disk.
   - Seamlessly falls back to pure C++ generation if host tools are not installed.

4. **Cryptographic Envelope Security & Integrity:**
   - Custom pure C++ **SHA-256** implementation calculating cryptographic digests on-the-fly.
   - **Authenticated Encryption** format: 13-byte magic header (`BACKUP_ENC_V1`), unique 16-byte random salt, PBKDF2 key stretching, and stream cipher.

5. **Bounded-Memory Streaming Pipeline ($O(1)$ RAM):**
   - Streams byte buffers in fixed 64KB chunks (`CHUNK_SIZE`), keeping memory usage strictly bounded regardless of database size.

6. **Zero External Dependency Build:**
   - Compiles cleanly on Windows (MinGW / MSVC) and Linux/macOS with standard `g++` or `clang++`. No heavy SDKs or multi-gigabyte build trees required.

---

## 📐 Architecture

```text
                     CLI Command (main.cpp)
                               │
                               ▼
                       [BackupManager]
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
[IDatabaseEngine]      [ICompressor]         [IStorageBackend]
   ├── SqliteEngine       ├── StreamingGzip     ├── LocalStorage
   ├── MysqlEngine        └── NoopCompressor    └── S3Storage
   └── PostgresEngine                                │
         │                                           ▼
         ▼                                  [.meta.json Manifest]
[SubprocessPipe]
(mysqldump / pg_dump)
```

---

## 🚀 How to Build

### Windows (1-Click Compilation):
```cmd
cd cpp
build.bat
```
This compiles `bin\db-backup.exe` and `bin\db-backup-test.exe`, and runs the test suite automatically.

### Linux / macOS:
```bash
cd cpp
make
make test
```

### CMake (CLion / Visual Studio / VS Code):
```bash
cd cpp
mkdir build && cd build
cmake ..
cmake --build .
```

---

## ⚡ CLI Usage Examples

### 1. Pre-Flight Connection Test
```bash
db-backup test -p local_sqlite
```

### 2. Standard Backup (with Gzip compression)
```bash
db-backup backup -p local_sqlite
```

### 3. Encrypted Backup (AES-256)
```bash
db-backup backup -p local_sqlite --encrypt --encryption-key "YourPassphrase123"
```

### 4. Listing Stored Backups
```bash
db-backup list
```

### 5. Restoring a Database
```bash
# Standard restore
db-backup restore -y sample_full_20261107_123459.sql.gz -d ./data/restored.db

# Restoring an encrypted backup
db-backup restore -y sample_full_20261107_123601.sql.gz.enc --encryption-key "YourPassphrase123" -d ./data/restored.db
```

### 6. Retention Pruning (Keep latest 3)
```bash
db-backup prune --retention-count 3
```

### 7. Task Scheduler Generation
```bash
# Generate Windows Task Scheduler command
db-backup schedule generate-task -p local_sqlite --time 03:00

# Generate Linux Crontab line
db-backup schedule generate-cron -p local_sqlite
```

---

## 🧪 Running the C++ Test Suite
```bash
./bin/db-backup-test
```
Verifies:
- SHA-256 cryptographic hashing
- AES-256 encryption/decryption round-trip
- Streaming compression & decompression
- Local storage listing and retention pruning
- Environment variable configuration interpolation

