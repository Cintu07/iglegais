"""iglegais: memory that answers why, not just what."""

__all__ = ["MemoryGraph", "LocalMemoryGraph", "HelixMemoryGraph"]
__version__ = "0.4.0"


def __getattr__(name: str):
    # lazy so the console entry points stay fast and helix stays optional.
    # default backend is the zero-dependency local sqlite store.
    if name in ("MemoryGraph", "LocalMemoryGraph"):
        from .local import LocalMemoryGraph

        return LocalMemoryGraph
    if name == "HelixMemoryGraph":
        from .mg import MemoryGraph

        return MemoryGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
