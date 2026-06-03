import logging

from fastapi import FastAPI, HTTPException

from ._schemas import ConvertRequest, ConvertResponse
from .conversion import convert_index

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    @app.post("/convert", response_model=ConvertResponse)
    def convert(request: ConvertRequest) -> ConvertResponse:
        try:
            artifacts = convert_index(request.index_name, request.mapping, request.config)
        except Exception as exc:
            logger.exception("conversion failed for index '%s'", request.index_name)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ConvertResponse.from_artifacts(artifacts)

    @app.post("/convert/bulk", response_model=list[ConvertResponse])
    def convert_bulk(requests: list[ConvertRequest]) -> list[ConvertResponse]:
        """Convert many indices in one call.

        Returns results positionally; a failure in one index is isolated to its
        slot (reported via ``error``) and never fails the rest of the batch.
        """
        results: list[ConvertResponse] = []
        for request in requests:
            try:
                artifacts = convert_index(request.index_name, request.mapping, request.config)
                results.append(ConvertResponse.from_artifacts(artifacts))
            except Exception as exc:
                logger.exception("bulk: index '%s' failed", request.index_name)
                results.append(ConvertResponse.from_error(request.index_name, str(exc)))
        return results

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}
