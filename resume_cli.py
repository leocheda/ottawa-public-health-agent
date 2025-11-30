"""
Simple persistent CLI that reuses the DatabaseSessionService-backed session.

Defaults to the provided session/user IDs so you can drop and reconnect while
keeping the same conversation state.
"""

import asyncio
import os

from google.genai import types

from ottawa_public_health_agent.agent import (
    APP_NAME,
    DEFAULT_SESSION_ID,
    MODEL_NAME,
    USER_ID,
    runner,
    session_service,
)


SESSION_ID = os.getenv("SESSION_ID", DEFAULT_SESSION_ID)
ACTIVE_USER_ID = os.getenv("USER_ID", USER_ID)


async def ensure_session(session_name: str):
    """Create or load a session with a stable ID."""
    try:
        return await session_service.create_session(
            app_name=APP_NAME, user_id=ACTIVE_USER_ID, session_id=session_name
        )
    except Exception:
        return await session_service.get_session(
            app_name=APP_NAME, user_id=ACTIVE_USER_ID, session_id=session_name
        )


async def main():
    session = await ensure_session(SESSION_ID)
    print(f"Resuming session '{session.id}' for user '{ACTIVE_USER_ID}' (app '{APP_NAME}')")
    print("Type 'exit' or Ctrl+C to quit.\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if user_input.lower() in {"exit", "quit"}:
            print("Exiting.")
            return
        if not user_input:
            continue

        content = types.Content(role="user", parts=[types.Part(text=user_input)])
        async for event in runner.run_async(
            user_id=ACTIVE_USER_ID, session_id=session.id, new_message=content
        ):
            if event.content and event.content.parts and event.content.parts[0].text:
                print(f"{MODEL_NAME}> {event.content.parts[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
