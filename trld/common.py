import json
import sys
import uuid
from http.client import HTTPResponse
from io import StringIO, TextIOWrapper
from typing import Callable, Dict, Iterator, Optional, Set, TextIO, Union
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .builtins import Char
from .jsonld.base import JSONLD_CONTEXT_RELATION
from .mimetypes import SUFFIX_MIME_TYPE_MAP, guess_mime_type

JSONLD_MIME_TYPE = SUFFIX_MIME_TYPE_MAP['jsonld']
JSON_MIME_TYPES: Set[str] = {JSONLD_MIME_TYPE, 'application/json'}

ACCEPT_HEADER = 'Accept'

ACCEPTS = ", ".join(
    mt + (f';q=0.{10 - i}' if i > 0 else '')
    for i, mt in enumerate(SUFFIX_MIME_TYPE_MAP.values())
)


class Input:
    document_url: Optional[str]
    content_type: Optional[str]
    context_url: Optional[str]
    profile: Optional[str]

    def __init__(
        self, source: Union[str, TextIO, None] = None, headers: Optional[Dict] = None
    ):
        stream: TextIO
        if isinstance(source, str):
            self.document_url = source
            if source.startswith(('http', 'https')):
                stream = self._open_request(source, headers)
            else:
                stream = open(_remove_file_protocol(source))
                self.content_type = guess_mime_type(source)
        elif source is None:
            stream = sys.stdin
        else:
            stream = source

        self._source = stream

    def _open_request(self, source: str, headers: Optional[Dict] = None) -> TextIO:
        req = Request(source)

        if headers is None or ACCEPT_HEADER not in headers:
            req.add_header(ACCEPT_HEADER, ACCEPTS)
        if headers is not None:
            for h, hv in headers.items():
                req.add_header(h, hv)

        res = urlopen(req)

        self.content_type = res.headers.get_content_type()
        self.context_url = _get_link_header(
            res, rel=JSONLD_CONTEXT_RELATION, type=JSONLD_MIME_TYPE
        )
        self.profile = _get_link_header(res, rel='profile')

        return TextIOWrapper(res)

    @property
    def document(self) -> object:
        if self.content_type in JSON_MIME_TYPES:
            return load_json(self)
        else:
            return self.read()

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
    def __init__(self, dest: Optional[TextIO] = None):
        if dest is None:
            dest = StringIO()
        self._dest = dest

    def write(self, s: str):
        print(s, file=self._dest, end='')

    def writeln(self, s: str):
        print(s, file=self._dest)

    def get_captured(self):
        return self._dest

    def get_value(self):
        assert isinstance(self._dest, StringIO)
        return self._dest.getvalue()


LoadDocumentCallback = Callable[[str], Input]


document_loader: Optional[LoadDocumentCallback] = None


def set_document_loader(loader: LoadDocumentCallback):
    global document_loader
    document_loader = loader


def load_json(source: Union[str, Input]) -> object:
    stream = None

    if not isinstance(source, Input):
        assert isinstance(source, str)
        source = document_loader(source) if document_loader else Input(source)

    if source._source == sys.stdin:
        return json.load(source._source)

    with source._source as fp:
        return json.load(fp)


def parse_json(s: str) -> object:
    return json.loads(s)


def dump_json(o: object, pretty=False) -> str:
    return json.dumps(o, indent=2 if pretty else None, ensure_ascii=not pretty)


def dump_canonical_json(o: object) -> str:
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


def _remove_file_protocol(ref: str):
    if ref.startswith('file://'):
        return ref[7:]
    elif ref.startswith('file:'):
        return ref[5:]
    return ref


def _get_link_header(
    response: HTTPResponse, rel: str, type: Optional[str] = None
) -> Optional[str]:
    links = response.headers.get_all('Link')
    if links is None:
        return None

    for link in links:
        href = link[link.find('<') : link.find('>')]
        if rel in link and (type is None or type in link):
            return href

    return None
