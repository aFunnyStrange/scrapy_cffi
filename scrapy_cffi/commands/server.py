"""Run the optional local or distributed crawler monitoring console."""


def run(host: str = "127.0.0.1", port: int = 6800) -> None:
    """Start the optional FastAPI crawler monitoring process."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "The monitoring server is optional. "
            "Install it with: pip install 'scrapy_cffi[server]' "
            "(fastapi>=0.115, uvicorn>=0.30)"
        ) from exc

    from ..monitoring import create_monitor_app

    uvicorn.run(create_monitor_app(), host=host, port=port)


__all__ = ["run"]
