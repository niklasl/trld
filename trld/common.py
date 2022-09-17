import json
import sys
import uuid
from http.client import HTTPResponse
from io import StringIO, TextIOWrapper
from typing import (Dict, Iterator, List, NamedTuple, Optional, Protocol, Set,
                    TextIO, Union)
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .builtins import Char
from .jsonld.base import JSONLD_CONTEXT_RELATION, JsonLdError, JsonObject
from .mimetypes import (ACCEPTS, JSON_MIME_TYPES, JSONLD_MIME_TYPE,
                        get_first_mime_type, guess_mime_type)

ACCEPT_HEADER = 'Accept'


class Input:
    document_url: Optional[str]
    content_type: Optional[str]
    context_url: Optional[str]
    profile: Optional[str]

    _source: TextIO

    def __init__(
        self, source: Union[str, TextIO, None] = None, headers: Optional[Dict] = None
    ):
        self.document_url = None
        self.content_type = None
        self.context_url = None
        self.profile = None

        if isinstance(source, str):
            self._source = self._open_stream(source, headers)
        elif source is None:
            self._source = sys.stdin
        else:
            self._source = source

        if (
            self.content_type is None
            and headers is not None
            and ACCEPT_HEADER in headers
        ):
            accepts = headers[ACCEPT_HEADER]
            first_accept = get_first_mime_type(accepts)
            if first_accept == accepts:
                self.content_type = first_accept

    def _open_stream(self, source: str, headers: Optional[Dict] = None) -> TextIO:
        self.document_url = source
        if is_http_url(source):
            return self._open_request(source, headers)
        else:
            self.content_type = guess_mime_type(source)
            return open(_remove_file_protocol(source))

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
            return self.load_json()
        else:
            return self.read()

    def load_json(self) -> JsonObject:
        if self._source == sys.stdin:
            return json.load(self._source)
        else:
            with self._source as fp:
                return json.load(fp)

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


class LoadDocumentOptions(NamedTuple):
    profile: str
    request_profile: Union[str, List[str]]


class LoadingDocumentNotAllowedError(JsonLdError):
    pass


class LoadDocumentCallback(Protocol):
    def __call__(self, url: str, options: Optional[LoadDocumentOptions] = None) -> Input:
        ...


def any_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> Input:
    return Input(url)


def http_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> Input:
    if not is_http_url(url):
        raise LoadingDocumentNotAllowedError(f"Not allowed to load non-HTTP URL: {url}")
    return Input(url)


def https_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> Input:
    if not url.startswith('https:'):
        raise LoadingDocumentNotAllowedError(f"Not allowed to load non-HTTPS URL: {url}")
    return Input(url)


_custom_document_loader: Optional[LoadDocumentCallback] = None


def set_document_loader(loader: LoadDocumentCallback):
    global _custom_document_loader
    _custom_document_loader = loader


def get_document_loader(start_url: Optional[str] = None) -> LoadDocumentCallback:
    if _custom_document_loader is not None:
        return _custom_document_loader

    if start_url is not None and is_http_url(start_url):
        if start_url.startswith('https:'):
            return https_document_loader
        return http_document_loader

    return any_document_loader


def parse_json(s: str) -> object:
    return json.loads(s)


def dump_json(o: object, pretty=False) -> str:
    return json.dumps(o, indent=2 if pretty else None, ensure_ascii=not pretty)


def dump_canonical_json(o: object) -> str:
    return json.dumps(o, indent=None, separators=(',', ':'), sort_keys=True)


def is_http_url(url: str) -> bool:
    return url.startswith(('http:', 'https:'))


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
