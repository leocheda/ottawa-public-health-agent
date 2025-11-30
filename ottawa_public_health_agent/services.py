from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.cli.service_registry import get_service_registry


def sqlite_aiosqlite_factory(uri: str, **kwargs):
    # DatabaseSessionService expects db_url positional arg
    return DatabaseSessionService(db_url=uri, **kwargs)


get_service_registry().register_session_service(
    "sqlite+aiosqlite", sqlite_aiosqlite_factory
)
