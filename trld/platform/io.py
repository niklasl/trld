import json
import sys
from http.client import HTTPResponse
from io import StringIO, TextIOWrapper
from typing import Dict, Iterator, List, NamedTuple, Optional, Set, TextIO, Union
from urllib.request import Request, urlopen

from ..builtins import Char
from ..jsonld.keys import JSONLD_CONTEXT_RELATION
from ..jsonld.base import JsonLdError, JsonObject
from ..mimetypes import (JSONLD_MIME_TYPE, SUFFIX_MIME_TYPE_MAP, get_first_mime_type,
                         guess_mime_type)

ACCEPT_HEADER = 'Accept'

ACCEPTS = ", ".join(
    mt + (f';q=0.{10 - i}' if i > 0 else '')
    for i, mt in enumerate(SUFFIX_MIME_TYPE_MAP.values())
)


class Input:
    document_url: Optional[str]
    content_type: Optional[str]
    profile: Optional[str]
    context_url: Optional[str]

    _stream: TextIO

    def __init__(
        self, source: Union[str, TextIO, None] = None, headers: Optional[Dict] = None
    ):
        self.document_url = None
        self.content_type = None
        self.profile = None
        self.context_url = None

        if isinstance(source, str):
            self._stream = self._open_stream(source, headers)
        elif source is None:
            self._stream = sys.stdin
        else:
            self._stream = source

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
        if source.startswith(('http:', 'https:')):
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
        # The profile *parameter* of the content type:
        for param, value in res.headers.get_params():
            if param == 'profile':
                self.profile = value

        return TextIOWrapper(res)

    def load_json(self) -> JsonObject:
        if self._stream == sys.stdin:
            return json.load(self._stream)
        else:
            with self._stream as fp:
                return json.load(fp)

    def read(self) -> str:
        return self._stream.read()

    def lines(self) -> Iterator[str]:
        return self._stream

    def characters(self) -> Iterator[Char]:
        return (c for l in self._stream for c in l)

    def close(self):
        if self._stream is not sys.stdin:
            self._stream.close()

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
