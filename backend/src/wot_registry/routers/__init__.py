from collections.abc import Iterator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_db_session)]


def decode_thing_id(thing_id: str) -> str:
    return unquote(thing_id)
