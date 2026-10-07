from functools import wraps

from rest_framework.exceptions import Throttled

from ..sqlite_busy import AccountingBusy, retry_sqlite_busy


class AccountingServiceUnavailable(Throttled):
    """Transient storage contention, with Retry-After, rather than a server error."""

    status_code = 503
    default_detail = "Le moteur comptable est occupé ; rejouez la même requête."
    default_code = "accounting_busy"


def accounting_storage_operation(operation):
    retried = retry_sqlite_busy(operation)

    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return retried(*args, **kwargs)
        except AccountingBusy as exc:
            raise AccountingServiceUnavailable(wait=1) from exc
    return wrapped
