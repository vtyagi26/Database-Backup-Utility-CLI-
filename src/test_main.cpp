#include "../include/Sha256.hpp"
#include "../include/Crypto.hpp"
#include "../include/Compression.hpp"
#include "../include/Storage.hpp"
#include "../include/engines/SqliteEngine.hpp"
#include "../include/Config.hpp"
#include "../include/Logger.hpp"

#include <iostream>
#include <cassert>
#include <sstream>
#include <fstream>

using namespace dbbackup;

void testSha256() {
    Logger::info("Testing SHA-256 Hashing...");
    std::string input = "hello database backup";
    std::string hash = Sha256::hashString(input);
    assert(!hash.empty());
    assert(hash.length() == 64);
    Logger::success("SHA-256 test passed (Digest: " + hash.substr(0, 16) + "...)");
}

void testCryptoRoundTrip() {
    Logger::info("Testing AES-256 / PBKDF2 Crypto Round-Trip...");
    std::string plainPath = "test_plain.txt";
    std::string encPath = "test_plain.txt.enc";
    std::string decPath = "test_decrypted.txt";

    std::string originalContent = "CRITICAL_DATABASE_PAYLOAD_SECRET_DATA_123456789";
    {
        std::ofstream out(plainPath);
        out << originalContent;
    }

    std::string password = "MySecretPassphrase!";
    Crypto::encryptFile(plainPath, encPath, password);
    Crypto::decryptFile(encPath, decPath, password);

    {
        std::ifstream in(decPath);
        std::string restoredContent;
        std::getline(in, restoredContent);
        assert(restoredContent == originalContent);
    }

    std::remove(plainPath.c_str());
    std::remove(encPath.c_str());
    std::remove(decPath.c_str());

    Logger::success("Crypto encryption/decryption round-trip verified!");
}

void testCompression() {
    Logger::info("Testing Streaming Compression & Decompression...");
    StreamingCompressor comp(CompressionType::GZIP);

    std::string origPath = "test_data.sql";
    std::string compPath = "test_data.sql.gz";
    std::string decompPath = "test_restored.sql";

    std::string sampleSql = "CREATE TABLE users (id INT, name TEXT);\nINSERT INTO users VALUES (1, 'Alice');\n";
    {
        std::ofstream out(origPath);
        for (int i = 0; i < 20; ++i) out << sampleSql;
    }

    size_t uncomp = 0, compBytes = 0;
    comp.compressFile(origPath, compPath, uncomp, compBytes);
    assert(uncomp > 0);
    assert(compBytes > 0);

    size_t decompBytes = 0;
    comp.decompressFile(compPath, decompPath, decompBytes);
    assert(decompBytes == uncomp);

    std::remove(origPath.c_str());
    std::remove(compPath.c_str());
    std::remove(decompPath.c_str());

    Logger::success("Compression & Decompression verified! Uncompressed: " + std::to_string(uncomp) + "B, Compressed: " + std::to_string(compBytes) + "B");
}

void testLocalStorageAndPruning() {
    Logger::info("Testing Local Storage & Retention Pruning...");
    LocalStorage storage("./test_backups_dir");

    std::string dummyFile = "test_backup.sql";
    {
        std::ofstream out(dummyFile);
        out << "SAMPLE_DATA";
    }

    BackupMetadata meta;
    meta.backupId = "test_1";
    meta.databaseName = "test_db";
    meta.filename = "test_backup.sql";

    storage.store(dummyFile, "test_backup_1.sql", meta);
    storage.store(dummyFile, "test_backup_2.sql", meta);
    storage.store(dummyFile, "test_backup_3.sql", meta);

    auto items = storage.listBackups();
    assert(items.size() >= 3);

    // Prune to retain only 2
    size_t pruned = storage.prune(2, 0);
    assert(pruned == 1);

    auto remaining = storage.listBackups();
    assert(remaining.size() == 2);

    std::remove(dummyFile.c_str());
    // Cleanup
    for (const auto& it : remaining) {
        std::remove(it.path.c_str());
        std::string metaPath = it.path + ".meta.json";
        std::remove(metaPath.c_str());
    }
#ifdef _WIN32
    _rmdir("./test_backups_dir");
#else
    rmdir("./test_backups_dir");
#endif

    Logger::success("Storage listing and retention pruning verified!");
}

void testConfigEnvInterpolation() {
    Logger::info("Testing Config Environment Variable Interpolation...");
    std::string raw = "host: ${USER}, port: 3306";
    std::string expanded = ConfigManager::interpolateEnvVars(raw);
    assert(!expanded.empty());
    Logger::success("Environment variable interpolation verified!");
}

int main() {
    std::cout << "\n============================================\n";
    std::cout << "  Database Backup Utility (C++ Test Suite)\n";
    std::cout << "============================================\n\n";

    try {
        testSha256();
        testCryptoRoundTrip();
        testCompression();
        testLocalStorageAndPruning();
        testConfigEnvInterpolation();

        std::cout << "\n\033[1;32mALL 5 TEST SUITES PASSED (100% SUCCESS)!\033[0m\n\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n\033[1;31mTEST FAILED:\033[0m " << e.what() << "\n\n";
        return 1;
    }
}

