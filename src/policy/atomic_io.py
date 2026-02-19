from __future__ import annotations
import os
import tempfile


def atomic_write_text(
    path: str, data: str, encoding: str = "utf-8"
) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=d)
    try:
        with os.fdopen(
            fd, "w", encoding=encoding, newline="\n"
        ) as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
