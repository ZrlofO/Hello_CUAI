from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from .models import MetadataItem, NormalizedMetadata, Provenance, UserConfirmedMetadata, UserConfirmationStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def update_item(metadata: NormalizedMetadata, item_id: str, changes: Dict[str, Any]) -> NormalizedMetadata:
    items = list(metadata.items)
    for index, item in enumerate(items):
        if item.item_id != item_id:
            continue
        if item.user_confirmation_status == UserConfirmationStatus.CONFIRMED:
            raise ValueError("Confirmed metadata cannot be silently overwritten")
        allowed = {"category", "sub_category", "normalized_value", "original_text", "source_page", "source_location"}
        payload = item.dict()
        payload.update({key: value for key, value in changes.items() if key in allowed})
        payload["provenance"] = Provenance.USER_CORRECTED
        payload["user_confirmation_status"] = UserConfirmationStatus.PENDING
        payload["updated_at"] = _now()
        items[index] = MetadataItem(**payload)
        return metadata.copy(update={"items": items})
    raise KeyError(f"Metadata item not found: {item_id}")


def delete_item(metadata: NormalizedMetadata, item_id: str) -> NormalizedMetadata:
    for item in metadata.items:
        if item.item_id == item_id and item.user_confirmation_status == UserConfirmationStatus.CONFIRMED:
            raise ValueError("Confirmed metadata cannot be silently deleted")
    remaining = [item for item in metadata.items if item.item_id != item_id]
    if len(remaining) == len(metadata.items):
        raise KeyError(f"Metadata item not found: {item_id}")
    return metadata.copy(update={"items": remaining})


def add_item(metadata: NormalizedMetadata, payload: Dict[str, Any]) -> NormalizedMetadata:
    item = MetadataItem(
        category=payload.get("category", "additional_information"),
        sub_category=payload.get("sub_category"),
        normalized_value=payload.get("normalized_value", ""),
        original_text=payload.get("original_text") or payload.get("normalized_value", ""),
        provenance=Provenance.USER_PROVIDED,
        extraction_confidence=1.0,
    )
    return metadata.copy(update={"items": [*metadata.items, item]})


def confirm_metadata(metadata: NormalizedMetadata, revision: int) -> UserConfirmedMetadata:
    confirmed_items = [
        item.copy(update={"user_confirmation_status": UserConfirmationStatus.CONFIRMED, "updated_at": _now()})
        for item in metadata.items
    ]
    return UserConfirmedMetadata(
        items=confirmed_items,
        preferences=metadata.preferences,
        warnings=metadata.warnings,
        extraction_confidence=metadata.extraction_confidence,
        confirmed_at=_now(),
        revision=revision,
    )
