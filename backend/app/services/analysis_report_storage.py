"""Private immutable report bodies; metadata and authorization remain in PostgreSQL."""
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path


def report_root():
    root = Path(os.getenv('REPORT_EXPORT_DIR', str(Path(__file__).resolve().parents[3] / 'reports'))).resolve() / 'analyses'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def report_path(key):
    if not re.fullmatch(r'[0-9a-f]{32}\.txt', key):
        raise OSError('Invalid report key')
    path = report_root() / key
    if path.is_symlink():
        raise OSError('Report symlinks are not allowed')
    return path


def write_report(content):
    data = content.encode('utf-8')
    key = uuid.uuid4().hex + '.txt'
    root = report_root()
    fd, temporary = tempfile.mkstemp(prefix='.report-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, report_path(key))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return key, hashlib.sha256(data).hexdigest()


def read_report(key, checksum):
    with report_path(key).open('rb') as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
        raise OSError('Report integrity check failed')
    return data.decode('utf-8')
