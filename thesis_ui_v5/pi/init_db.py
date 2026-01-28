from db import init_db, DB_PATH

if __name__ == "__main__":
    init_db()
    print(f"✅ Database initialized at: {DB_PATH}")
