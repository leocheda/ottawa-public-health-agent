import asyncio
import sqlite3
import os
import sys

# Ensure the project root is in sys.path
sys.path.append(os.getcwd())

from ottawa_public_health_agent.agent import runner, run_session


async def main():
    print("--- Test Run 1: Verifying Persistence ---")
    await run_session(
        runner,
        [
            "Hi, I am Sam! What is the capital of the United States?",
            "Hello! What is my name?",
        ],
        "test-db-session-01",
    )

    print("\n--- Test Run 2: Resuming a Conversation ---")
    # We are simulating a restart by just using the same session ID.
    # The agent instance is the same in memory, but the session data is fetched from DB.
    # To truly verify persistence, we rely on the fact that DatabaseSessionService fetches from DB.
    await run_session(
        runner,
        ["What is the capital of India?", "Hello! What is my name?"],
        "test-db-session-01",
    )

    print("\n--- Test Run 3: Isolation Test ---")
    await run_session(runner, ["Hello! What is my name?"], "test-db-session-02")

    print("\n--- Database Inspection ---")
    check_data_in_db()


def check_data_in_db():
    db_path = "my_agent_data.db"
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return

    try:
        with sqlite3.connect(db_path) as connection:
            cursor = connection.cursor()
            result = cursor.execute(
                "select app_name, session_id, author, content from events"
            )
            columns = [description[0] for description in result.description]
            print(f"Columns: {columns}")
            rows = result.fetchall()
            print(f"Total rows: {len(rows)}")
            for i, each in enumerate(rows):
                print(f"Row {i}: {each}")
    except Exception as e:
        print(f"Error reading database: {e}")


if __name__ == "__main__":
    asyncio.run(main())
