from enum import Enum

class State(Enum):
    QUEUED = "queued"
    CONNECTING = "connecting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Priority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2

class ErrorClass(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AUTH = "auth"
    RANGE_MISMATCH = "range_mismatch"
    THROTTLE = "throttle"
    UNKNOWN = "unknown"

def classify_error(error_msg):
    e = error_msg.lower()
    if any(x in e for x in ['403', 'forbidden', 'unauthorized']):
        return ErrorClass.AUTH
    if any(x in e for x in ['404', 'not found', '410', 'gone']):
        return ErrorClass.PERMANENT
    if any(x in e for x in ['416', 'range', 'requested range']):
        return ErrorClass.RANGE_MISMATCH
    if any(x in e for x in ['429', 'too many', 'throttl', 'rate limit']):
        return ErrorClass.THROTTLE
    if any(x in e for x in ['timeout', 'timed out', 'connection reset',
                              'connection refused', 'network', 'eof',
                              'socket', 'broken pipe']):
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN

def should_retry(err_class):
    return err_class in (ErrorClass.TRANSIENT, ErrorClass.THROTTLE, ErrorClass.UNKNOWN)
