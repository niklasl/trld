from typing import Callable
import hashlib
import json
import re
import sys
import uuid
from itertools import permutations
from urllib.parse import urljoin, urlparse

ESC_BACKSLASH_RE = re.compile(r'(\\\\)')
LITERAL_CODEPOINT_RE = re.compile(r'\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8}')


def hash_hexdigest(algorithm: str, data: str) -> str:
    return hashlib.new(algorithm, data.encode('utf-8')).hexdigest()


def escape_codepoints(s: str, needs_esc: Callable[[int], bool]) -> str:
    return ''.join(fr"\u{ord(c):04X}" if needs_esc(ord(c)) else c for c in s)


def decode_escapes(s: str) -> str:
    parts = ESC_BACKSLASH_RE.split(s)
    return ''.join('\\' if p == '\\\\' else _decode_part_escapes(p) for p in parts)


def _decode_part_escapes(s: str) -> str:
    s = decode_unicode_escapes(s)
    s = s.replace(r'\"', '"')
    s = s.replace(r"\'", "'")
    s = s.replace(r'\b', '\b')
    s = s.replace(r'\t', '\t')
    s = s.replace(r'\n', '\n')
    s = s.replace(r'\f', '\f')
    s = s.replace(r'\r', '\r')
    return s


def decode_unicode_escapes(s: str) -> str:
    return LITERAL_CODEPOINT_RE.sub(lambda m: chr(int(m.group(0)[2:], 16)), s)


def json_decode(s: str) -> object:
    return json.loads(s)


def json_encode(o: object, pretty=False, sort_keys=False) -> str:
    indent = 2 if pretty else None
    ensure_ascii = not pretty
    return json.dumps(o, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)


def json_encode_canonical(o: object) -> str:
    return json.dumps(o, indent=None, separators=(',', ':'), sort_keys=True)


def resolve_iri(base: str, relative: str) -> str:
    if '//' in relative:
        url = urlparse(relative)
        urlpath: str = url.path
        if url.params:
            urlpath += f';{url.params}'
        if url.query:
            urlpath += f'?{url.query}'
        return urljoin(base, urljoin(relative, urlpath))

    return urljoin(base, relative)


def uuid4() -> str:
    return str(uuid.uuid4())


def warning(msg: str):
    print(msg, file=sys.stderr)
