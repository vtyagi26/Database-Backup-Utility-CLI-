CXX ?= g++
CXXFLAGS ?= -std=c++14 -O2 -Wall -Wextra -Iinclude

all: bin/db-backup bin/db-backup-test

bin/db-backup: src/main.cpp
	@mkdir -p bin backups
	$(CXX) $(CXXFLAGS) src/main.cpp -o bin/db-backup

bin/db-backup-test: src/test_main.cpp
	@mkdir -p bin backups
	$(CXX) $(CXXFLAGS) src/test_main.cpp -o bin/db-backup-test

test: bin/db-backup-test
	./bin/db-backup-test

clean:
	rm -rf bin backups/temp_*

.PHONY: all test clean

