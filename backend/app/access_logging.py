"""Keep successful high-volume tile requests out of the console access log."""
import logging


class SuccessfulTileAccessFilter(logging.Filter):
    def filter(self, record):
        if record.name != "uvicorn.access" or not isinstance(record.args, tuple) or len(record.args) != 5:
            return True
        _, method, path, _, status = record.args
        return not (method == "GET" and str(path).split("?", 1)[0].startswith("/api/tiles/")
                    and str(status) in {"200", "304"})


def configure_tile_access_logging():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, SuccessfulTileAccessFilter) for item in logger.filters):
        logger.addFilter(SuccessfulTileAccessFilter())
