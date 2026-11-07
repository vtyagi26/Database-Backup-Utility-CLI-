#pragma once

#include "Constants.hpp"
#include "Exceptions.hpp"
#include <string>
#include <vector>
#include <fstream>
#include <memory>
#include <algorithm>

namespace dbbackup {

class ICompressor {
public:
    virtual ~ICompressor() = default;
    virtual void compressFile(const std::string& srcPath, const std::string& dstPath, size_t& outUncompressedBytes, size_t& outCompressedBytes) = 0;
    virtual void decompressFile(const std::string& srcPath, const std::string& dstPath, size_t& outUncompressedBytes) = 0;
    virtual std::string getExtension() const = 0;
};

// Stream-based Run-Length & Header compression engine for zero-dependency modern C++
class StreamingCompressor : public ICompressor {
public:
    explicit StreamingCompressor(CompressionType type = CompressionType::GZIP)
        : type_(type) {}

    std::string getExtension() const override {
        switch (type_) {
            case CompressionType::GZIP:  return ".gz";
            case CompressionType::ZSTD:  return ".zst";
            case CompressionType::BZIP2: return ".bz2";
            default:                     return "";
        }
    }

    void compressFile(const std::string& srcPath, const std::string& dstPath, size_t& outUncompressed, size_t& outCompressed) override {
        std::ifstream src(srcPath, std::ios::binary);
        if (!src.is_open()) {
            throw CompressionException("Could not open source file for compression: " + srcPath);
        }

        std::ofstream dst(dstPath, std::ios::binary);
        if (!dst.is_open()) {
            throw CompressionException("Could not open destination file for compression: " + dstPath);
        }

        // Write compression container header
        std::string header = "CMPR_V1_" + toString(type_) + "\n";
        dst.write(header.data(), header.size());

        outUncompressed = 0;
        outCompressed = header.size();

        std::vector<uint8_t> inBuf(64 * 1024);
        while (src.good()) {
            src.read(reinterpret_cast<char*>(inBuf.data()), inBuf.size());
            std::streamsize bytes = src.gcount();
            if (bytes <= 0) break;
            outUncompressed += bytes;

            // Simple fast byte-run streaming encoding
            for (std::streamsize i = 0; i < bytes; ) {
                uint8_t byte = inBuf[i];
                uint8_t count = 1;
                while (i + count < bytes && inBuf[i + count] == byte && count < 255) {
                    count++;
                }

                if (count >= 4 || byte == 0xFF) {
                    // Marker for run
                    dst.put(static_cast<char>(0xFF));
                    dst.put(static_cast<char>(count));
                    dst.put(static_cast<char>(byte));
                    outCompressed += 3;
                } else {
                    for (uint8_t c = 0; c < count; ++c) {
                        dst.put(static_cast<char>(byte));
                        outCompressed += 1;
                    }
                }
                i += count;
            }
        }
    }

    void decompressFile(const std::string& srcPath, const std::string& dstPath, size_t& outUncompressed) override {
        std::ifstream src(srcPath, std::ios::binary);
        if (!src.is_open()) {
            throw CompressionException("Could not open compressed archive: " + srcPath);
        }

        std::string header;
        std::getline(src, header);
        if (header.find("CMPR_V1") == std::string::npos) {
            // Raw stream passthrough if uncompressed
            src.clear();
            src.seekg(0);
        }

        std::ofstream dst(dstPath, std::ios::binary);
        if (!dst.is_open()) {
            throw CompressionException("Could not open destination file for decompression: " + dstPath);
        }

        outUncompressed = 0;
        char ch;
        while (src.get(ch)) {
            uint8_t byte = static_cast<uint8_t>(ch);
            if (byte == 0xFF) {
                char countChar, valChar;
                if (src.get(countChar) && src.get(valChar)) {
                    uint8_t count = static_cast<uint8_t>(countChar);
                    for (uint8_t c = 0; c < count; ++c) {
                        dst.put(valChar);
                        outUncompressed++;
                    }
                }
            } else {
                dst.put(ch);
                outUncompressed++;
            }
        }
    }

    static CompressionType detectCompression(const std::string& path) {
        std::string lower = path;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        if (lower.size() >= 3 && lower.substr(lower.size() - 3) == ".gz") return CompressionType::GZIP;
        if (lower.size() >= 4 && lower.substr(lower.size() - 4) == ".zst") return CompressionType::ZSTD;
        if (lower.size() >= 4 && lower.substr(lower.size() - 4) == ".bz2") return CompressionType::BZIP2;
        return CompressionType::NONE;
    }

private:
    CompressionType type_;
};

} // namespace dbbackup

