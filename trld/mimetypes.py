from typing import Optional, Set

SUFFIX_MIME_TYPE_MAP = {
    'trig': 'application/trig',
    'ttl': 'text/turtle',
    'jsonld': 'application/ld+json',
    'xml': 'application/rdf+xml',
    'rdf': 'application/rdf+xml',
    'rdfs': 'application/rdf+xml',
    'owl': 'application/rdf+xml',
    'nq': 'application/n-quads',
    'nt': 'application/n-triples',
    'html': 'text/html',
}

JSONLD_MIME_TYPE = SUFFIX_MIME_TYPE_MAP['jsonld']
JSON_MIME_TYPES: Set[str] = {JSONLD_MIME_TYPE, 'application/json'}

def guess_mime_type(ref: str) -> Optional[str]:
    """
    >>> guess_mime_type('path/to/some.dir/file.jsonld')
    'application/ld+json'
    """
    i: int = ref.rfind('.')
    if i == -1:
        return None
    suffix: str = ref[i + 1 :]
    return SUFFIX_MIME_TYPE_MAP.get(suffix)


def get_first_mime_type(accepts):
    """
    >>> get_first_mime_type("text/html, application/xhtml+xml, application/xml;q=0.9, image/webp, */*;q=0.8")
    'text/html'
    >>> get_first_mime_type("application/xml;q=0.9, image/webp, */*;q=0.8")
    'application/xml'
    """
    return accepts.split(',', 1)[0].split(';', 1)[0].strip()
