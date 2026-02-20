try:
    from numba import njit

    NUMBA_ENABLED = True

    def maybe_njit(*args, **kwargs):
        return njit(*args, **kwargs)

except ImportError:  # pragma: no cover - exercised when numba is installed
    NUMBA_ENABLED = False

    def maybe_njit(*args, **kwargs):
        def decorator(func):
            return func

        return decorator
