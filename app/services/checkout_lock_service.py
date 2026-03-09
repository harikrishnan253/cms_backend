from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app import models


@dataclass
class LockResult:
    ok: bool
    code: str
    file: models.File | None
    owner_id: int | None
    owner_username: str | None
    lock_changed: bool


@dataclass
class LockAvailabilityResult:
    available: bool
    locked_by_other: bool
    owner_id: int | None
    owner_username: str | None


class CheckoutLockService:
    def _owner_username(self, file_record: models.File) -> str | None:
        if file_record.checked_out_by:
            return file_record.checked_out_by.username
        return None

    def checkout_file(
        self,
        file_record: models.File,
        user_id: int,
        timestamp: datetime,
    ) -> LockResult:
        owner_username = self._owner_username(file_record)
        was_locked_by_owner = bool(
            file_record.is_checked_out and file_record.checked_out_by_id == user_id
        )
        if file_record.is_checked_out and file_record.checked_out_by_id != user_id:
            return LockResult(
                ok=False,
                code="LOCKED_BY_OTHER",
                file=file_record,
                owner_id=file_record.checked_out_by_id,
                owner_username=owner_username,
                lock_changed=False,
            )

        file_record.is_checked_out = True
        file_record.checked_out_by_id = user_id
        file_record.checked_out_at = timestamp
        return LockResult(
            ok=True,
            code="ALREADY_LOCKED_BY_OWNER" if was_locked_by_owner else "SUCCESS",
            file=file_record,
            owner_id=file_record.checked_out_by_id,
            owner_username=owner_username,
            lock_changed=True,
        )

    def cancel_checkout(
        self,
        file_record: models.File,
        user_id: int,
    ) -> LockResult:
        return self.release_lock_if_owner(file_record, user_id, clear_timestamp=False)

    def assert_lock_available(
        self,
        file_record: models.File,
        user_id: int,
    ) -> LockAvailabilityResult:
        owner_username = self._owner_username(file_record)
        locked_by_other = bool(
            file_record.is_checked_out and file_record.checked_out_by_id != user_id
        )
        return LockAvailabilityResult(
            available=not locked_by_other,
            locked_by_other=locked_by_other,
            owner_id=file_record.checked_out_by_id,
            owner_username=owner_username,
        )

    def acquire_processing_lock(
        self,
        file_record: models.File,
        user_id: int,
        timestamp: datetime,
    ) -> LockResult:
        owner_username = self._owner_username(file_record)
        if file_record.is_checked_out:
            if file_record.checked_out_by_id != user_id:
                return LockResult(
                    ok=False,
                    code="LOCKED_BY_OTHER",
                    file=file_record,
                    owner_id=file_record.checked_out_by_id,
                    owner_username=owner_username,
                    lock_changed=False,
                )
            return LockResult(
                ok=True,
                code="ALREADY_LOCKED_BY_OWNER",
                file=file_record,
                owner_id=file_record.checked_out_by_id,
                owner_username=owner_username,
                lock_changed=False,
            )

        file_record.is_checked_out = True
        file_record.checked_out_by_id = user_id
        file_record.checked_out_at = timestamp
        return LockResult(
            ok=True,
            code="SUCCESS",
            file=file_record,
            owner_id=file_record.checked_out_by_id,
            owner_username=owner_username,
            lock_changed=True,
        )

    def release_lock(
        self,
        file_record: models.File,
        clear_timestamp: bool = False,
    ) -> LockResult:
        owner_username = self._owner_username(file_record)
        file_record.is_checked_out = False
        file_record.checked_out_by_id = None
        if clear_timestamp:
            file_record.checked_out_at = None

        return LockResult(
            ok=True,
            code="UNLOCKED",
            file=file_record,
            owner_id=None,
            owner_username=owner_username,
            lock_changed=True,
        )

    def release_lock_if_owner(
        self,
        file_record: models.File,
        user_id: int,
        clear_timestamp: bool = False,
    ) -> LockResult:
        owner_username = self._owner_username(file_record)
        if not file_record.is_checked_out or file_record.checked_out_by_id != user_id:
            return LockResult(
                ok=True,
                code="NO_OP",
                file=file_record,
                owner_id=file_record.checked_out_by_id,
                owner_username=owner_username,
                lock_changed=False,
            )

        return self.release_lock(file_record, clear_timestamp=clear_timestamp)

    def finalize_overwrite_lock_state(self, file_record: models.File) -> LockResult:
        return self.release_lock(file_record, clear_timestamp=False)
