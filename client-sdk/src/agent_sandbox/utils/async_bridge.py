"""Async/sync bridging utilities.

Provides run_sync() for calling async functions from sync context,
and make_sync for generating sync method variants.
"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = get_logger("utils.async_bridge")

T = TypeVar("T")

# Shared thread pool for sync bridging
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sandbox-sync")


def _has_running_loop() -> bool:
    """Check if there's a running event loop in the current thread."""
    try:
        loop = asyncio.get_running_loop()
        return loop is not None
    except RuntimeError:
        return False


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from synchronous code.

    Handles the common case where an event loop may already be running
    (e.g., in Jupyter notebooks) by falling back to a thread pool.

    Args:
        coro: The coroutine to execute.

    Returns:
        The coroutine's return value.

    Raises:
        Whatever the coroutine raises.
    """
    if _has_running_loop():
        # Already in an async context (e.g., Jupyter) — run in a separate thread
        logger.debug("Detected running event loop, using thread pool for sync execution")
        future = _executor.submit(asyncio.run, coro)
        return future.result()
    else:
        return asyncio.run(coro)


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
