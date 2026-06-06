import os
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from ._logging import configure_logging
from ._metrics import install_metrics
from ._routes import register_routes


def _package_version() -> str:
    """Single source of truth is the package metadata (pyproject)."""
    try:
        return version("ch-converter")
    except PackageNotFoundError:
        return "0.0.0"


# Must run before FastAPI/Instrumentator so all log records use our format.
configure_logging()

app = FastAPI(title="ES -> ClickHouse Schema Converter", version=_package_version())
install_metrics(app)
register_routes(app)


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
