#pragma once

#include "Models.hpp"
#include <string>
#include <vector>
#include <ostream>
#include <istream>
#include <memory>

namespace dbbackup {

class IDatabaseEngine {
public:
    virtual ~IDatabaseEngine() = default;

    virtual bool testConnection(std::string& outDetails) = 0;
    virtual std::vector<std::string> listTables() = 0;
    virtual bool backup(std::ostream& outputStream, const BackupOptions& options, std::vector<std::string>& outTables) = 0;
    virtual bool restore(std::istream& inputStream, const BackupOptions& options, std::string& outDetails) = 0;
    virtual DatabaseType getType() const = 0;
};

} // namespace dbbackup

