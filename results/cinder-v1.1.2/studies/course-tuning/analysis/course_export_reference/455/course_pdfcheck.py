"""Minimal one-page PDF validation shim for frozen course figure exporters."""
from __future__ import annotations
import re
from pathlib import Path
class PdfReader:
    def __init__(self,path,strict=True):
        data=Path(path).read_bytes()
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]:
            raise ValueError('invalid PDF framing')
        n=len(re.findall(rb'/Type\s*/Page(?!s)\b',data))
        if n < 1: raise ValueError('no PDF pages found')
        self.pages=[object() for _ in range(n)]
