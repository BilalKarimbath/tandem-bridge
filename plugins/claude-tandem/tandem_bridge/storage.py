"""Exclusive publication on filesystems supporting atomic hard links."""
import os
from pathlib import Path
import tempfile


def publish_text(path, text):
    """Publish complete UTF-8 content once; never downgrade to partial creation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise
        except OSError as exc:
            # Preserve type, errno, winerror and filenames on the original error.
            detail = f'{exc.strerror}; atomic hard-link publication failed; no fallback or destination write performed'
            exc.strerror = detail
            exc.args = (exc.errno, detail, *exc.args[2:])
            raise
    finally:
        os.unlink(temporary)
