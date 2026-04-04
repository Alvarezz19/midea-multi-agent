from __future__ import annotations

from typing import Any, TextIO
import sys


def _stream_encoding(stream: TextIO | None) -> str | None:
    if stream is None:
        return None
    return getattr(stream, "encoding", None)


def safe_console_text(value: Any, stream: TextIO | None = None) -> str:
    text = value if isinstance(value, str) else str(value)
    encoding = _stream_encoding(stream or sys.stdout)
    if not encoding:
        return text

    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def safe_print(
    *args: Any,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    stream = file or sys.stdout
    sanitized = [safe_console_text(arg, stream=stream) for arg in args]
    print(*sanitized, sep=sep, end=end, file=stream, flush=flush)
