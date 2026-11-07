cmake_minimum_required(VERSION 3.10)
project(DatabaseBackupUtility LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

# Main CLI Executable
add_executable(db-backup src/main.cpp)

# Test Suite Executable
add_executable(db-backup-test src/test_main.cpp)

if(MSVC)
    target_compile_options(db-backup PRIVATE /W4)
    target_compile_options(db-backup-test PRIVATE /W4)
else()
    target_compile_options(db-backup PRIVATE -Wall -Wextra -O2)
    target_compile_options(db-backup-test PRIVATE -Wall -Wextra -O2)
endif()

