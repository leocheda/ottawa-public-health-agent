import asyncio
import os
import sys
from google.genai import types

# Ensure the project root is in sys.path
sys.path.append(os.getcwd())

from ottawa_public_health_agent.agent import runner, session_service, USER_ID

# --- Monkey Patch Start ---
# Fix for ADK bug where compaction is deserialized as dict instead of object
try:
    from google.adk.flows.llm_flows import contents

    original_process = contents._process_compaction_events

    def patched_process_compaction_events(events):
        for event in events:
            if (
                event.actions
                and event.actions.compaction
                and isinstance(event.actions.compaction, dict)
            ):

                class CompactionWrapper:
                    def __init__(self, d):
                        self._d = d

                    def __getattr__(self, name):
                        return self._d.get(name)

                event.actions.compaction = CompactionWrapper(event.actions.compaction)
        return original_process(events)

    contents._process_compaction_events = patched_process_compaction_events
    print("DEBUG: Applied monkey patch for _process_compaction_events")
except Exception as e:
    print(f"DEBUG: Failed to apply monkey patch: {e}")
# --- Monkey Patch End ---


async def run_session(runner_instance, user_queries, session_name):
    print(f"\n ### Session: {session_name}")
    if isinstance(user_queries, str):
        user_queries = [user_queries]

    # Get or create session
    print(f"DEBUG: Calling get_session for {session_name}")
    try:
        session = await session_service.get_session(
            app_name=runner_instance.app_name, user_id=USER_ID, session_id=session_name
        )
        print(f"DEBUG: get_session returned: {session}")
    except Exception as e:
        print(f"get_session raised exception: {e}")
        session = None

    if session is None:
        print(f"DEBUG: Calling create_session for {session_name}")
        try:
            session = await session_service.create_session(
                app_name=runner_instance.app_name,
                user_id=USER_ID,
                session_id=session_name,
            )
            print(f"DEBUG: create_session returned: {session}")
        except Exception as create_e:
            print(f"create_session failed with error: {create_e}")
            import traceback

            traceback.print_exc()
            session = None

    print(f"DEBUG: Session object final: {session}")
    if session is None:
        return

    for query_text in user_queries:
        print(f"\nUser > {query_text}")
        query = types.Content(role="user", parts=[types.Part(text=query_text)])
        async for event in runner_instance.run_async(
            user_id=USER_ID, session_id=session.id, new_message=query
        ):
            if event.content and event.content.parts:
                text = event.content.parts[0].text
                if text and text != "None":
                    print(f"Model > {text}")


async def main():
    session_id = "compaction_demo"

    # Clear previous session if exists to ensure clean test
    try:
        # We can't easily delete a session via the service interface,
        # but we can just use a new session ID if needed.
        # For now, let's assume "compaction_demo" is fresh or we append to it.
        # Ideally we might want to delete the DB file or use a unique ID.
        pass
    except:
        pass

    print("--- Starting Compaction Test ---")

    # Turn 1
    await run_session(
        runner,
        "What is the latest news about AI in healthcare?",
        session_id,
    )

    # Turn 2
    await run_session(
        runner,
        "Are there any new developments in drug discovery?",
        session_id,
    )

    # Turn 3 - Compaction should trigger after this turn!
    await run_session(
        runner,
        "Tell me more about the second development you found.",
        session_id,
    )

    # Turn 4
    await run_session(
        runner,
        "Who are the main companies involved in that?",
        session_id,
    )

    print("\n--- Verifying Compaction ---")

    # Get the final session state
    final_session = await session_service.get_session(
        app_name=runner.app_name,
        user_id=USER_ID,
        session_id=session_id,
    )

    print("--- Searching for Compaction Summary Event ---")
    found_summary = False
    for event in final_session.events:
        # Compaction events have a 'compaction' attribute or are of a specific type.
        # The user's snippet checks: if event.actions and event.actions.compaction:
        # Let's verify the structure of the event object.
        # Based on ADK, it might be in event.actions.

        if event.actions and event.actions.compaction:
            print("\n✅ SUCCESS! Found the Compaction Event:")
            print(f"  Author: {event.author}")

            compaction_data = event.actions.compaction
            summary = None
            if hasattr(compaction_data, "summary"):
                summary = compaction_data.summary
            elif isinstance(compaction_data, dict):
                summary = compaction_data.get("summary")

            if summary:
                print(f"  Compaction Summary: {summary}")
            else:
                print(
                    "  Compaction Event found (Summary content is empty or not accessible)"
                )

            found_summary = True
            break

    if not found_summary:
        print(
            "\n❌ No compaction event found. Try increasing the number of turns in the demo."
        )
        # Debug: print all events to see what's there
        # for e in final_session.events:
        #     print(e)


if __name__ == "__main__":
    asyncio.run(main())
