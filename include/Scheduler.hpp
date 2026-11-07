#pragma once

#include "Logger.hpp"
#include <string>
#include <functional>

#ifdef _WIN32
  #include <windows.h>
  #define SLEEP_SECONDS(s) Sleep((s) * 1000)
#else
  #include <unistd.h>
  #define SLEEP_SECONDS(s) sleep(s)
#endif

namespace dbbackup {

class Scheduler {
public:
    static void runDaemon(int intervalMinutes, std::function<void()> backupCallback, int maxIterations = 0) {
        Logger::info("Starting backup daemon (Interval: " + std::to_string(intervalMinutes) + " minute(s)). Press Ctrl+C to stop.");
        
        int count = 0;
        while (true) {
            count++;
            Logger::info("Executing scheduled backup run #" + std::to_string(count) + "...");
            try {
                backupCallback();
            } catch (const std::exception& e) {
                Logger::error(std::string("Scheduled backup iteration failed: ") + e.what());
            }

            if (maxIterations > 0 && count >= maxIterations) {
                Logger::info("Reached requested max scheduled iterations. Stopping daemon.");
                break;
            }

            Logger::info("Sleeping for " + std::to_string(intervalMinutes) + " minute(s)...");
            SLEEP_SECONDS(intervalMinutes * 60);
        }
    }

    static std::string generateCron(const std::string& profile, const std::string& cronExpr = "0 2 * * *") {
        return "# Database Backup Utility Cron Job\n" + cronExpr + " db-backup backup -p " + profile + " >> /var/log/db_backup.log 2>&1\n";
    }

    static std::string generateWindowsTask(const std::string& profile, const std::string& timeStr = "02:00") {
        return "schtasks /create /tn \"DBBackup_" + profile + "\" /tr \"db-backup.exe backup -p " + profile + "\" /sc daily /st " + timeStr + " /ru SYSTEM\n";
    }
};

} // namespace dbbackup
