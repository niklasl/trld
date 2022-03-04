from typing import Optional, Dict, List, Set, Union, cast


Scalar = Union[str, int, float, bool]
JsonObject = Union[Dict, List, Scalar]
JsonMap = Dict[str, JsonObject]
JsonOptMap = Dict[str, Optional[JsonObject]]
JsonList = List[JsonObject]
JsonOptList = List[Optional[JsonObject]]


# From <https://tools.ietf.org/html/rfc3986#section-2.2>
PREFIX_DELIMS: Set[str] = {':', '/', '?', '#', '[', ']', '@'}

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

# TODO: see 5f6117d4
NULLS: Set[Optional[str]] = {None, NULL}
NOTHING: Set[Optional[str]] = {None, NULL, NONE}

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


class JsonLdError(Exception):
    pass


def is_iri(value: Optional[str]) -> bool:
    return value is not None and ':' in value and is_iri_ref(value)


def is_iri_ref(value: Optional[str]) -> bool:
    ... # TODO: check legal chars
    return value is not None and ' ' not in value and not is_blank(value)


def is_blank(value: str) -> bool:
    ...
    return value.startswith('_:')


def has_keyword_form(s: str) -> bool:
    return s.startswith('@') and s[1:].isalpha()


def is_lang_tag(value: Optional[str]) -> bool:
    ... # TODO: according to section 2.2.9 of [BCP47]
    return value is not None and value[0].isalpha() and  ' ' not in value


# TODO: spec errata: spec def excludes null but links to whatwg which includes it
def is_scalar(o: object) -> bool:
    return isinstance(o, (str, int, float, bool))


def is_graph_object(o: JsonMap) -> bool:
    if GRAPH in o:
        if ID in o:
            if INDEX in o:
                return len(o) == 3
            return len(o) == 2
        if INDEX in o:
            return len(o) == 2
        return len(o) == 1
    return False


def is_simple_graph_object(o: JsonMap) -> bool:
    if GRAPH in o:
        return len(o) == 2 if INDEX in o else len(o) == 1
    return False


def add_value_as_list(map: Dict, key: str, value: object):
    add_value(map, key, value, True)


def add_value(map: Dict, key: str, value: object, aslist=False):
    # TODO: rework this according to spec..
    existing: object = map.get(key)
    if aslist and key not in map:
        map[key] = as_list(value)
    #elif isinstance(existing, List):
    #    map.pop(key)
    #    for v in existing:
    #        add_value(map, key, v, aslist)
    elif key not in map:
        map[key] = value
    else:
        if not isinstance(existing, List):
            map[key] = [existing]
        if isinstance(value, List):
            map[key] += value
        else:
            assert isinstance(map, Dict) # TODO: just for transpile
            values: object = map[key]
            assert isinstance(values, List) # TODO: just for transpile
            assert isinstance(value, object) # TODO: just for transpile
            values.append(value)


def as_list(obj: object) -> List:
    return obj if isinstance(obj, List) else [obj]


def relativise_iri(base: str, iri: str) -> str:
    if iri.startswith(base + '#'):
        return iri[len(base):]
    if '?' in iri and iri.startswith(base):
        return iri[len(base):]
    if not base.endswith('/'):
        last: int = base.rfind('/')
        base = base[0:last + 1]
    if iri.startswith(base):
        return iri[len(base):]

    parentbase: str = base[:base.rfind('/')]
    leaf: str = iri[iri.rfind('/') + 1:]
    relativeto: List[str] = []
    while '/' in parentbase and not parentbase.endswith(':/'):
        if iri.startswith(parentbase):
            relativeto.append(leaf)
            return '/'.join(relativeto)
        relativeto.append('..')
        parentbase = parentbase[:parentbase.rfind('/')]

    return iri


def node_equals(a: JsonObject, b: JsonObject) -> bool:
    if is_scalar(a):
        return type(a) == type(b) and a == b
    if isinstance(a, List):
        if not isinstance(b, List):
            return False
        # TODO: transpile or live with C-style code...
        #return all(node_equals(it, b[i]) for i, it in enumerate(a))
        i: int = 0
        for ai in a:
            if not node_equals(ai, b[i]):
                return False
            i += 1
        return True
    elif isinstance(a, Dict):
        if not isinstance(b, Dict):
            return False
        return all(k in b and node_equals(a[k], b[k]) for k in a.keys())
    else:
        return False
