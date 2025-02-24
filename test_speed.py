import sqlite3
import timeit
import os
import pandas as pd
from pymongo import MongoClient

# SQLite Setup
sqlite_db = "benchmark_test.db"
sqlite_conn = sqlite3.connect(sqlite_db)
sqlite_cursor = sqlite_conn.cursor()
sqlite_cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);")
sqlite_conn.commit()

# MongoDB Setup
mongo_client = MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["benchmark_db"]
mongo_collection = mongo_db["users"]

# Functions for Benchmarking
def sqlite_insert():
    sqlite_cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Test User", "test@example.com"))
    sqlite_conn.commit()

def mongo_insert():
    mongo_collection.insert_one({"name": "Test User", "email": "test@example.com"})

def sqlite_query():
    sqlite_cursor.execute("SELECT * FROM users WHERE email=?", ("test@example.com",))
    sqlite_cursor.fetchone()

def mongo_query():
    mongo_collection.find_one({"email": "test@example.com"})

# Measure Execution Time
sqlite_insert_time = timeit.timeit(sqlite_insert, number=1000)
mongo_insert_time = timeit.timeit(mongo_insert, number=1000)
sqlite_query_time = timeit.timeit(sqlite_query, number=1000)
mongo_query_time = timeit.timeit(mongo_query, number=1000)

# Print Results
benchmark_results = pd.DataFrame({
    "Database": ["SQLite", "MongoDB"],
    "Insert Time (ms)": [sqlite_insert_time, mongo_insert_time],
    "Query Time (ms)": [sqlite_query_time, mongo_query_time]
})

print(benchmark_results)

# Clean up test data
sqlite_cursor.execute("DROP TABLE users;")
mongo_db.drop_collection("users")
sqlite_conn.close()
mongo_client.close()
