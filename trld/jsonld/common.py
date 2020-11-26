import json
import sys
from os.path import expanduser
from urllib.parse import urlparse, urljoin
from urllib.request import urlopen


sorted = sorted


def load_json(url: str) -> object:
    if url.startswith(('http', 'https')):
        stream = urlopen(url)
    else:
        if url.startswith('file://'):
            url = url[7:]
        stream = open(expanduser(url))
    with stream as fp:
        return json.load(fp)

    return None


def parse_json(s: str) -> object:
    return json.loads(s)


def dump_json(o: object, pretty=False) -> str:
    return json.dumps(o,
            indent=2 if pretty else None,
            ensure_ascii=not pretty)


def dump_canonical_json(o: object, pretty=False) -> str:
    return json.dumps(o, indent=None, separators=(',', ':'), sort_keys=True)


def resolve_iri(base: str, relative: str) -> str:
    if '//' in relative:
        url = urlparse(relative)
        return urljoin(base, urljoin(relative, url.path))
    return urljoin(base, relative)


def warning(msg: str):
    print(msg, file=sys.stderr)
