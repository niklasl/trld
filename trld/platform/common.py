import json
import sys
import uuid
from urllib.parse import urljoin, urlparse


def json_decode(s: str) -> object:
    return json.loads(s)


def json_encode(o: object, pretty=False) -> str:
    return json.dumps(o, indent=2 if pretty else None, ensure_ascii=not pretty)


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
