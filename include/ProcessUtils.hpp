#pragma once

#include "Exceptions.hpp"
#include <string>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <iostream>

#ifdef _WIN32
  extern "C" FILE* _popen(const char*, const char*);
  extern "C" int _pclose(FILE*);
  #define POPEN _popen
  #define PCLOSE _pclose
#else
  #include <stdio.h>
  #define POPEN popen
  #define PCLOSE pclose
#endif

namespace dbbackup {

struct PipeDeleter {
    void operator()(FILE* f) const {
        if (f) PCLOSE(f);
    }
};

class SubprocessPipe {
public:
    SubprocessPipe(const std::string& command, const std::string& mode = "r")
        : pipe_(POPEN(command.c_str(), mode.c_str())) {
        if (!pipe_) {
            throw EngineException("Failed to spawn subprocess: " + command);
        }
    }

    FILE* get() const { return pipe_.get(); }

    std::string readAll() {
        std::string result;
        char buffer[4096];
        while (fgets(buffer, sizeof(buffer), pipe_.get()) != nullptr) {
            result += buffer;
        }
        return result;
    }

    static bool isCommandAvailable(const std::string& cmd) {
#ifdef _WIN32
        std::string checkCmd = "where " + cmd + " >nul 2>&1";
#else
        std::string checkCmd = "command -v " + cmd + " >/dev/null 2>&1";
#endif
        int res = std::system(checkCmd.c_str());
        return (res == 0);
    }

private:
    std::unique_ptr<FILE, PipeDeleter> pipe_;
};

} // namespace dbbackup
