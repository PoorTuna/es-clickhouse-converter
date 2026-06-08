import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from ._logging import configure_logging
from ._metrics import install_metrics
from ._routes import register_routes
from .elasticsearch import SessionStore, register_es_routes

_SWEEP_INTERVAL_SECONDS = 60


def _package_version() -> str:
    """Single source of truth is the package metadata (pyproject)."""
    try:
        return version("ch-converter")
    except PackageNotFoundError:
        return "0.0.0"


async def _sweep_sessions(store: SessionStore) -> None:
    """Periodically reap idle cluster sessions until the app shuts down."""
    while True:
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
        await store.sweep()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    store: SessionStore = app.state.es_sessions
    sweeper = asyncio.create_task(_sweep_sessions(store))
    try:
        yield
    finally:
        sweeper.cancel()
        await store.close_all()


# Must run before FastAPI/Instrumentator so all log records use our format.
configure_logging()

app = FastAPI(
    title="ES -> ClickHouse Schema Converter", version=_package_version(), lifespan=_lifespan
)
app.state.es_sessions = SessionStore()
install_metrics(app)
register_routes(app)
register_es_routes(app, app.state.es_sessions)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "ch_converter.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        log_config=None,  # preserve our dictConfig; uvicorn.run() would overwrite it
    )


if __name__ == "__main__":
    main()
