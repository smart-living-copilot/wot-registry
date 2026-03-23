from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from wot_registry.content_store.store import cleanup_expired_entries, ensure_directories
from wot_registry.config import Settings


@dataclass
class ContentStoreCleanupState:
    task: asyncio.Task[None] | None = None


def start_content_store_cleanup(app, *, settings: Settings) -> None:
    base = Path(settings.CONTENT_STORE_DIR).resolve()
    ensure_directories(base)
    state = app.state.content_store_cleanup_state
    stop_event = app.state.content_store_cleanup_stop_event
    stop_event.clear()

    async def runner(stop_signal: asyncio.Event) -> None:
        while not stop_signal.is_set():
            await asyncio.to_thread(cleanup_expired_entries, base)
            try:
                await asyncio.wait_for(
                    stop_signal.wait(),
                    timeout=settings.CONTENT_STORE_CLEANUP_INTERVAL_SECONDS,
                )
            except TimeoutError:
                continue

    state.task = asyncio.create_task(runner(stop_event))


async def stop_content_store_cleanup(app) -> None:
    state = app.state.content_store_cleanup_state
    stop_event = app.state.content_store_cleanup_stop_event
    stop_event.set()
    task = state.task
    if task is None:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        state.task = None
