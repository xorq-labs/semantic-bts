from semantic_bts.api import __all__ as _api_all  # noqa: F401


__all__ = _api_all


def __getattr__(name: str):
    import semantic_bts.api as _api

    try:
        return getattr(_api, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
