from typing import Set, Optional

BASE: str = '@base'
CONTAINER: str = '@container'
CONTEXT: str = '@context'
DIRECTION: str = '@direction'
GRAPH: str = '@graph'
ID: str = '@id'
IMPORT: str = '@import'
INCLUDED: str = '@included'
INDEX: str = '@index'
JSON: str = '@json'
LANGUAGE: str = '@language'
LIST: str = '@list'
NEST: str = '@nest'
NONE: str = '@none'
PREFIX: str = '@prefix'
PROPAGATE: str = '@propagate'
PROTECTED: str = '@protected'
REVERSE: str = '@reverse'
SET: str = '@set'
TYPE: str = '@type'
VALUE: str = '@value'
VERSION: str = '@version'
VOCAB: str = '@vocab'

# TODO: not "really" (public) keywords...?
ANY: str = '@any'
NULL: str = '@null'
DEFAULT: str = '@default'

KEYWORDS: Set[str] = {
    BASE,
    CONTAINER,
    CONTEXT,
    DIRECTION,
    GRAPH,
    ID,
    IMPORT,
    INCLUDED,
    INDEX,
    JSON,
    LANGUAGE,
    LIST,
    NEST,
    NONE,
    PREFIX,
    PROPAGATE,
    PROTECTED,
    REVERSE,
    SET,
    TYPE,
    VALUE,
    VERSION,
    VOCAB
}

CONTEXT_KEYWORDS: Set[str] = {
    VERSION,
    IMPORT,
    BASE,
    VOCAB,
    LANGUAGE,
    DIRECTION,
    PROPAGATE,
    PROTECTED
}

VALUE_KEYWORDS: Set[str] = {
    DIRECTION, INDEX, LANGUAGE, TYPE, VALUE
}

CONTAINER_KEYWORDS: Set[str] = {GRAPH, ID, INDEX, LANGUAGE, LIST, SET, TYPE}

DIRECTIONS: Set[str] = {'rtl', 'ltr'}

JSONLD10: str = 'json-ld-1.0'
JSONLD11: str = 'json-ld-1.1'

JSONLD_CONTEXT_RELATION: str = 'http://www.w3.org/ns/json-ld#context'

# TODO: see 5f6117d4
NULLS: Set[Optional[str]] = {None, NULL}
NOTHING: Set[Optional[str]] = {None, NULL, NONE}
