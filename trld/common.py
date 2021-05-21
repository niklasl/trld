import json
import sys
from typing import Iterator, Optional, Callable
from io import StringIO
from os.path import expanduser
from urllib.parse import urlparse, urljoin
from urllib.request import urlopen


sorted = sorted


Char = str


class Input:
    def __init__(self, source=None):
        if isinstance(source, str):
            self._source = open(remove_file_protocol(source))
        else:
            self._source = source or sys.stdin

    def get_header(self, header: str) -> Optional[str]:
        raise NotImplementedError

    def read(self) -> str:
        return self._source.read()

    def lines(self) -> Iterator[str]:
        return self._source

    def characters(self) -> Iterator[Char]:
        return (c for l in self._source for c in l)

    def close(self):
        if self._source is not sys.stdin:
            self._source.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()


class Output:
    def __init__(self, dest=None):
        if dest is True:
            dest = StringIO()
        self._dest = dest or sys.stdout

    def write(self, s: str):
        print(s, file=self._dest, end='')

    def writeln(self, s: str):
        print(s, file=self._dest)

    def get_value(self):
        assert isinstance(self._dest, StringIO)
        return self._dest.getvalue()

    def close(self):
        if self._dest is not sys.stdout:
            self._dest.close()


# TODO: also define RemoteDocument (using Input)...


source_locator: Optional[Callable[[str], str]] = None

def set_source_locator(locator: Callable[[str], str]):
    global source_locator
    source_locator = locator


def remove_file_protocol(ref: str):
    if ref.startswith('file://'):
        return ref[7:]
    elif ref.startswith('file:'):
        return ref[5:]
    return ref


# TODO: LoadDocumentCallback?

def load_json(url: str) -> object:
    url = source_locator(url) if source_locator else url

    stream = None
    if url.startswith(('http', 'https')):
        stream = urlopen(url)
    else:
        stream = open(expanduser(remove_file_protocol(url)))

    assert stream is not None
    with stream as fp:
        return json.load(fp)


def parse_json(s: str) -> object:
    return json.loads(s)


def dump_json(o: object, pretty=False) -> str:
    return json.dumps(o,
            indent=2 if pretty else None,
            ensure_ascii=not pretty)


def dump_canonical_json(o: object) -> str:
    return json.dumps(o, indent=None, separators=(',', ':'), sort_keys=True)


def resolve_iri(base: str, relative: str) -> str:
    if '//' in relative:
        url = urlparse(relative)
        urlpath: str = url.path
        if url.params is not None:
            urlpath += f';{url.params}'
        if url.query is not None:
            urlpath += f'?{url.query}'
        return urljoin(base, urljoin(relative, urlpath))
    return urljoin(base, relative)


def warning(msg: str):
    print(msg, file=sys.stderr)
