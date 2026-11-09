"""Shared helpers for CRUD routers."""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException, status
from pydantic import BaseModel


def apply_partial_update(obj, update: BaseModel, non_nullable: Iterable[str] = ()) -> dict:
    """
    Apply only the fields the client actually sent (exclude_unset), so that
    an explicit null can clear a nullable field while omitted fields stay
    untouched. Explicit null on a non-nullable field → 422.
    """
    changes = update.model_dump(exclude_unset=True, by_alias=False)
    blocked = [k for k in non_nullable if k in changes and changes[k] is None]
    if blocked:
        raise HTTPException(422, f"Fields cannot be null: {', '.join(blocked)}")
    for key, value in changes.items():
        setattr(obj, key, value)
    return changes
