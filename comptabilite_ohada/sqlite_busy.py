"""Bounded retries for SQLite writers; never retry a caller-owned transaction."""

from functools import wraps
import sqlite3
import time

from django.db import connection, OperationalError


class AccountingBusy(OperationalError):
    pass


def retry_sqlite_busy(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        deadline = time.monotonic() + 1
        caller_transaction = connection.in_atomic_block
        while True:
            try:
                return operation(*args, **kwargs)
            except OperationalError as exc:
                code = getattr(exc.__cause__, "sqlite_errorcode", 0)
                if connection.vendor != "sqlite" or (code & 255) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                # The atomic block in operation has already rolled back. A
                # host-owned transaction cannot be safely restarted here.
                if caller_transaction or time.monotonic() >= deadline:
                    raise AccountingBusy("Le moteur comptable est occupé ; rejouez la requête.") from exc
                time.sleep(0.02)
    return wrapped
