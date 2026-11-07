#pragma once

#include <iostream>
#include <string>
#include <vector>
#include <iomanip>

namespace dbbackup {

class Logger {
public:
    static void setVerbose(bool v) {
        verboseRef() = v;
    }

    static bool isVerbose() {
        return verboseRef();
    }

    static void info(const std::string& msg) {
        std::cout << "\033[1;34m[INFO]\033[0m " << msg << std::endl;
    }

    static void success(const std::string& msg) {
        std::cout << "\033[1;32m[SUCCESS]\033[0m " << msg << std::endl;
    }

    static void warn(const std::string& msg) {
        std::cout << "\033[1;33m[WARN]\033[0m " << msg << std::endl;
    }

    static void error(const std::string& msg) {
        std::cerr << "\033[1;31m[ERROR]\033[0m " << msg << std::endl;
    }

    static void debug(const std::string& msg) {
        if (isVerbose()) {
            std::cout << "\033[1;36m[DEBUG]\033[0m " << msg << std::endl;
        }
    }

    static void printHeader(const std::string& title) {
        std::cout << "\n\033[1;35m=== " << title << " ===\033[0m\n";
    }

    static void printKeyValue(const std::string& key, const std::string& val, int width = 22) {
        std::cout << "  " << std::left << std::setw(width) << ("\033[1m" + key + "\033[0m:") << " " << val << "\n";
    }

private:
    static bool& verboseRef() {
        static bool v = false;
        return v;
    }
};

} // namespace dbbackup
