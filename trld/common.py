import json
import sys
from typing import Iterator, Optional
from os.path import expanduser
from urllib.parse import urlparse, urljoin
from urllib.request import urlopen


Char = str


class Input:
    def __init__(self, source=None):
        self._source = source or sys.stdin

    def get_header(self, header: str) -> Optional[str]:
        raise NotImplementedError

    def lines(self) -> Iterator[str]:
        return self._source

    def characters(self) -> Iterator[Char]:
        return (c for l in self._source for c in l)

    def close(self):
        if self._source is not sys.stdin:
            self._source.close()


class Output:
    def __init__(self, dest=None):
        self._dest = dest or sys.stdout

    def write(self, s: str):
        print(s, file=self._dest, end='')

    def writeln(self, s: str):
        print(s, file=self._dest)

    def close(self):
        if self._source is not sys.stdout:
            self._source.close()


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
        urlpath = url.path
        if url.params:
            urlpath += f';{url.params}'
        if url.query:
            urlpath += f'?{url.query}'
        return urljoin(base, urljoin(relative, urlpath))
    return urljoin(base, relative)


def warning(msg: str):
    print(msg, file=sys.stderr)
