-- Show all tables in the database
SELECT name FROM sqlite_master WHERE type='table';
-- Show all columns in a table
PRAGMA table_info(table_name);
-- Show all indexes in the database
SELECT name FROM sqlite_master WHERE type='index';
-- Show all views in the database
SELECT name FROM sqlite_master WHERE type='view';
-- Show all triggers in the database
SELECT name FROM sqlite_master WHERE type='trigger';
-- Show all columns in all tables
SELECT m.name AS table_name, p.name AS column_name
FROM sqlite_master AS m
JOIN pragma_table_info(m.name) AS p
WHERE m.type = 'table'
ORDER BY m.name, p.cid;