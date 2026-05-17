import hashlib
import json
import sys
import uuid
from itertools import permutations
from urllib.parse import urljoin, urlparse


def hash_hexdigest(algorithm: str, data: str) -> str:
    return hashlib.new(algorithm, data.encode('utf-8')).hexdigest()


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
