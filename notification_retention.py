"""Read-notification retention; never remove unread notifications or parcel history."""
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic


def purge_read_notifications(connection, timestamp):
    cutoff = (datetime.fromisoformat(timestamp) - timedelta(hours=2)).isoformat(timespec='seconds')
    return connection.execute(
        'DELETE FROM ops_notifications WHERE read_at IS NOT NULL AND read_at < ?',
        (cutoff,),
    ).rowcount


def install_notification_retention(app, conn, now):
    """Sweep at startup and automatically during API activity (at most once/minute).

    An idle process needs no timer: the notification endpoint also sweeps before
    returning data, so expired rows are never displayed on the next visit.
    """
    from flask import request
    lock = Lock()
    last_sweep = [float('-inf')]
    with conn() as c:
        c.execute('CREATE INDEX IF NOT EXISTS ops_notice_read_at ON ops_notifications(read_at) WHERE read_at IS NOT NULL')
        purge_read_notifications(c, now())

    @app.before_request
    def expire_read_notifications():
        if not request.path.startswith('/api/') or monotonic() - last_sweep[0] < 60:
            return
        if not lock.acquire(blocking=False):
            return
        try:
            if monotonic() - last_sweep[0] >= 60:
                with conn() as c:
                    purge_read_notifications(c, now())
                last_sweep[0] = monotonic()
        finally:
            lock.release()
