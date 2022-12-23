from typing import List, NamedTuple, Optional, Protocol, Union

from ..mimetypes import JSON_MIME_TYPES, JSONLD_MIME_TYPE
from ..platform.io import Input, _is_http_url
from .base import JsonLdError

REQUEST_HEADERS = {'Accept': f'{JSONLD_MIME_TYPE}, application/json;q=0.9'}


class RemoteDocument(NamedTuple):
    document_url: Optional[str]
    content_type: Optional[str]
    context_url: Optional[str]
    profile: Optional[str]
    document: object


class LoadDocumentOptions(NamedTuple):
    profile: str
    request_profile: Union[str, List[str]]


class LoadingDocumentNotAllowedError(JsonLdError):
    pass


class LoadDocumentCallback(Protocol):
    def __call__(self, url: str, options: Optional[LoadDocumentOptions] = None) -> RemoteDocument:
        ...


_custom_document_loader: Optional[LoadDocumentCallback] = None


def set_document_loader(loader: LoadDocumentCallback):
    global _custom_document_loader
    _custom_document_loader = loader


def get_document_loader(start_url: Optional[str] = None) -> LoadDocumentCallback:
    if _custom_document_loader is not None:
        return _custom_document_loader

    if start_url is not None and _is_http_url(start_url):
        if start_url.startswith('https:'):
            return https_document_loader
        return http_document_loader

    return any_document_loader


def any_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> RemoteDocument:
    return load_any_document(url)


def http_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> RemoteDocument:
    if not _is_http_url(url):
        raise LoadingDocumentNotAllowedError(f"Not allowed to load non-HTTP URL: {url}")
    return load_any_document(url)


def https_document_loader(url: str, options: Optional[LoadDocumentOptions] = None) -> RemoteDocument:
    if not url.startswith('https:'):
        raise LoadingDocumentNotAllowedError(f"Not allowed to load non-HTTPS URL: {url}")
    return load_any_document(url)


def load_any_document(url: str) -> RemoteDocument:
    document: object
    with Input(url, REQUEST_HEADERS) as inp:
        if inp.content_type in JSON_MIME_TYPES:
            document = inp.load_json()
        else:
            document = inp.read()

    return RemoteDocument(inp.document_url, inp.content_type, inp.context_url, inp.profile, document)
