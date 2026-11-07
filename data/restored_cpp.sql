-- ==========================================================
-- Database Backup Utility (C++ Edition)
-- Engine: SQLite
-- Database: ./data/sample.db
-- Backup Type: full
-- ==========================================================

PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

-- Table structure for table 'users'
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT);
INSERT INTO users (id, name, email) VALUES (1, 'Alice Smith', 'alice@example.com');
INSERT INTO users (id, name, email) VALUES (2, 'Bob Jones', 'bob@example.com');

-- Table structure for table 'orders'
CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL);
INSERT INTO orders (order_id, user_id, amount) VALUES (101, 1, 99.50);
INSERT INTO orders (order_id, user_id, amount) VALUES (102, 2, 149.99);

COMMIT;
