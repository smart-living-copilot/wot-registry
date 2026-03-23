from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Protocol

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from wot_registry.content_store.cleanup import (
    ContentStoreCleanupState,
    start_content_store_cleanup,
    stop_content_store_cleanup,
)
from wot_registry.config import Settings
from wot_registry.bootstrap import BackendBootstrapService
from wot_registry.search import ThingSearchService, set_active_search_service
from wot_registry.stream_runtime import StreamConsumerState
from wot_registry.thing_events import (
    ThingEventOutboxPublisherState,
    ThingEventOutboxPublisherWorker,
    ValkeyThingEventStreamPublisher,
)


class BackgroundTaskState(Protocol):
    task: asyncio.Task[None] | None


def initialize_app_state(
    app: FastAPI,
    *,
    settings: Settings,
    session_factory: sessionmaker,
) -> None:
    app.state.session_factory = session_factory
    app.state.event_publisher = ValkeyThingEventStreamPublisher(
        settings.REDIS_URL,
        settings.THING_EVENTS_STREAM,
    )
    app.state.thing_event_outbox_state = ThingEventOutboxPublisherState()
    app.state.thing_event_outbox_stop_event = asyncio.Event()
    app.state.thing_event_outbox_publisher = None

    app.state.search_indexer_consumer_state = StreamConsumerState()
    app.state.search_indexer_stop_event = asyncio.Event()
    app.state.search_indexer_consumer = None
    app.state.search_service = None
    app.state.content_store_cleanup_state = ContentStoreCleanupState()
    app.state.content_store_cleanup_stop_event = asyncio.Event()


def bootstrap_persistent_state(
    *,
    session_factory: sessionmaker,
    settings: Settings,
) -> None:
    session = session_factory()
    try:
        BackendBootstrapService(session).bootstrap(settings)
    finally:
        session.close()


def _start_background_task(
    *,
    state: BackgroundTaskState,
    stop_event: asyncio.Event,
    runner: Callable[[asyncio.Event], Awaitable[None]],
) -> None:
    state.task = asyncio.create_task(runner(stop_event))


async def _stop_background_task(
    *,
    state: BackgroundTaskState,
    stop_event: asyncio.Event,
) -> None:
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


def start_thing_event_outbox(
    app: FastAPI,
    *,
    session_factory: sessionmaker,
) -> None:
    publisher = ThingEventOutboxPublisherWorker(
        session_factory=session_factory,
        publisher_getter=lambda: app.state.event_publisher,
        state=app.state.thing_event_outbox_state,
    )
    app.state.thing_event_outbox_publisher = publisher
    _start_background_task(
        state=app.state.thing_event_outbox_state,
        stop_event=app.state.thing_event_outbox_stop_event,
        runner=publisher.run_forever,
    )


async def stop_thing_event_outbox(app: FastAPI) -> None:
    await _stop_background_task(
        state=app.state.thing_event_outbox_state,
        stop_event=app.state.thing_event_outbox_stop_event,
    )


async def start_search_indexer(app: FastAPI, *, settings: Settings) -> None:
    from wot_registry.search_indexer.consumer import SearchIndexerStreamConsumer

    consumer = SearchIndexerStreamConsumer(
        settings=settings,
        state=app.state.search_indexer_consumer_state,
    )
    app.state.search_indexer_consumer = consumer
    await consumer.start()
    _start_background_task(
        state=app.state.search_indexer_consumer_state,
        stop_event=app.state.search_indexer_stop_event,
        runner=consumer.run_forever,
    )


async def stop_search_indexer(app: FastAPI) -> None:
    await _stop_background_task(
        state=app.state.search_indexer_consumer_state,
        stop_event=app.state.search_indexer_stop_event,
    )

    consumer = app.state.search_indexer_consumer
    if consumer is not None:
        await consumer.close()
        app.state.search_indexer_consumer = None


def start_search_service(app: FastAPI, *, settings: Settings) -> None:
    service = ThingSearchService(settings)
    app.state.search_service = service
    set_active_search_service(service)


async def stop_search_service(app: FastAPI) -> None:
    search_service = app.state.search_service
    if search_service is not None:
        set_active_search_service(None)
        await search_service.close()
        app.state.search_service = None
        return

    set_active_search_service(None)


async def start_backend_runtime(
    app: FastAPI,
    *,
    settings: Settings,
    session_factory: sessionmaker,
) -> None:
    settings.validate_search_settings()
    settings.validate_runtime_security_settings()
    initialize_app_state(app, settings=settings, session_factory=session_factory)
    bootstrap_persistent_state(session_factory=session_factory, settings=settings)

    try:
        start_content_store_cleanup(app, settings=settings)
        start_thing_event_outbox(app, session_factory=session_factory)
        await start_search_indexer(app, settings=settings)
        start_search_service(app, settings=settings)
    except Exception:
        await shutdown_backend_runtime(app)
        raise


async def shutdown_backend_runtime(app: FastAPI) -> None:
    await stop_content_store_cleanup(app)
    await stop_search_service(app)
    await stop_thing_event_outbox(app)
    await stop_search_indexer(app)
    app.state.event_publisher.close()
