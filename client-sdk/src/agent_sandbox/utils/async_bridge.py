"""Async/sync bridging utilities.

Provides run_sync() for calling async functions from sync context,
and make_sync for generating sync method variants.
"""

from __future__ import annotations

import asyncio
import atexit
import functools
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

T = TypeVar("T")


class _SyncRunner:
    """Own the event loop shared by synchronous SDK calls and their clients."""

    def __init__(self) -> None:
        ready: Future[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = Future()

        async def serve() -> None:
            stop = asyncio.Event()
            ready.set_result((asyncio.get_running_loop(), stop))
            await stop.wait()

        self.thread = threading.Thread(
            target=lambda: asyncio.run(serve()), name="sandbox-sync", daemon=True
        )
        self.thread.start()
        self.loop, self.stop = ready.result()
        atexit.register(self.close)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.stop.set)
        self.thread.join()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        if threading.current_thread() is self.thread:
            coro.close()
            raise RuntimeError(
                "A synchronous SDK callback cannot call another synchronous SDK method; "
                "use the asynchronous API for nested operations."
            )
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result()
        except BaseException:
            future.cancel()
            raise


_runner: _SyncRunner | None = None
_runner_lock = threading.Lock()


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on the shared synchronous SDK loop and wait for its result.

    Successive calls reuse the loop, including calls from notebook event loops.
    This blocks the calling thread. Clients used here must be opened and closed
    through their synchronous methods; do not move live async clients between loops.
    """
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = _SyncRunner()
    return _runner.run(coro)


def make_sync(
    async_method: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., T]:
    """Create a synchronous wrapper for an async method.

    Args:
        async_method: The async method to wrap.

    Returns:
        A synchronous function that calls the async method via run_sync().

    Example:
        class MyClass:
            async def do_thing(self) -> str:
                return "done"

            do_thing_sync = make_sync(do_thing)
    """

    @functools.wraps(async_method)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return run_sync(async_method(*args, **kwargs))

    # Mark as sync wrapper for introspection
    wrapper._is_sync_wrapper = True  # type: ignore[attr-defined]
    return wrapper


def make_classmethod_sync(
    async_method: Callable[..., Coroutine[Any, Any, T]],
) -> Any:
    """Synchronous wrapper for an async classmethod.

    ``staticmethod(make_sync(fn))`` does not inject ``cls``. A call such as
    ``Sandbox.connect_sync(sandbox_id)`` then binds the id to ``cls`` and
    raises ``TypeError``. This wrapper is a real classmethod, so subclasses
    keep their type, and it dispatches through ``getattr(cls, name)`` so an
    override of the async method is used.

    Example:
        class MyClass:
            @classmethod
            async def create(cls) -> MyClass:
                return cls()

            create_sync = make_classmethod_sync(create.__func__)
    """
    name = async_method.__name__

    @functools.wraps(async_method)
    def wrapper(cls: type[Any], *args: Any, **kwargs: Any) -> T:
        bound = getattr(cls, name)
        return run_sync(bound(*args, **kwargs))  # type: ignore[no-any-return]

    wrapper._is_sync_wrapper = True  # type: ignore[attr-defined]
    return classmethod(wrapper)
