from typing import Optional

SUFFIX_MIME_TYPE_MAP = {
    'ttl': 'text/turtle',
    'trig': 'application/trig',
    'jsonld': 'application/ld+json',
    'xml': 'application/rdf+xml',
    'rdf': 'application/rdf+xml',
    'rdfs': 'application/rdf+xml',
    'owl': 'application/rdf+xml',
    'html': 'text/html',
}


def guess_mime_type(ref: str) -> Optional[str]:
    """
    >>> guess_mime_type('path/to/some.dir/file.jsonld')
    'application/ld+json'
    """
    i: int = ref.rfind('.')
    if i == -1:
        return None
    suffix: str = ref[i + 1:]
    return SUFFIX_MIME_TYPE_MAP.get(suffix)
