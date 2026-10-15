import re
from typing import Iterable, NamedTuple, Set, Union, cast

from ..platform.common import decode_escapes, decode_unicode_escapes
from ..platform.io import Input
from ..rdfterms import RDF_DIRLANGSTRING, RDF_LANGSTRING, XSD_STRING
from ..jsonld.rdf import (
        RdfDataset, RdfGraph, RdfTriple, RdfLiteral, RdfObject, to_jsonld)

LTR = 'ltr'
RTL = 'rtl'
DIRECTIONS: Set = {LTR, RTL}

IRI_OR_BNODE_RE = re.compile(r'^\s*(?:<([^<> \t]+)>|(_:[\w.-]+))\s*')
EMPTY_LINE_RE = re.compile(r'^\s*(?:#.*)?$')
VERSION_RE = re.compile(r'^\s*VERSION\s*')
DOT_TRAIL_RE = re.compile(r'^\s*\.\s*#?.*')
LITERAL_LEXICAL_RE = re.compile(r'''^"((?:[^"\\]|\\[tbnrf\\"']|\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8})*)"''')
LITERAL_TYPE_LANG_RE = re.compile(r'(?i)^\^\^<([^<> \t]+)>|@([a-z0-9]+(?:-[a-z0-9]+)*)(?:--(ltr|rtl))?')
TRIPLE_TERM_START = '<<('
TRIPLE_TERM_END_RE = re.compile(r'^\s*\)>>')

ALLOWED_VERSIONS = {'1.1', '1.2-basic', '1.2'}


class ResultItem(NamedTuple):
    cno: int
    triple: RdfTriple
    graph: str | None
    trail: str


class ParsedLiteral(NamedTuple):
    literal: RdfLiteral
    trail: str
    cno: int


class ParserError(Exception):
    msg: str
    lno: int
    cno: int

    def __init__(self, msg: str, lno: int, cno: int):
        self.msg = msg
        self.lno = lno
        self.cno = cno

    def __str__(self) -> str:
        return (f'Syntax error at line {self.lno}, column {self.cno}: {self.msg}')


def parse(inp: Input, use_native_types=True) -> object:
    dataset = RdfDataset()
    load(dataset, inp)
    return to_jsonld(dataset, use_native_types=use_native_types)


def load(dataset: RdfDataset, inp: Input) -> None:
    lno = 0
    for line in cast(Iterable[str], inp.lines()):
        lno += 1

        m: re.Match | None = EMPTY_LINE_RE.match(line)
        if m is not None:
            continue

        version = _read_version_declaration(line, lno)
        if version is not None:
            continue

        item = _read_triple_and_graph(line, lno)
        cno = item.cno
        triple = item.triple
        g = item.graph
        trail = item.trail

        if DOT_TRAIL_RE.match(trail) is None:
            raise ParserError(f"Invalid trailing syntax {trail!r}", lno, cno)

        graph: RdfGraph | None
        if g is None:
            graph = dataset.default_graph
            if graph is None:
                graph = RdfGraph()
                dataset.default_graph = graph
        else:
            graph = dataset.named_graphs.get(g)
            if graph is None:
                graph = RdfGraph()
                dataset.named_graphs[g] = graph

        graph.add(triple)


def _read_version_declaration(line: str, lno: int) -> str | None:
    m: re.Match | None = VERSION_RE.match(line)
    if m is None:
        return None

    c_offset: int = m.end()
    chunk = line[c_offset:]
    cno: int = c_offset
    m = LITERAL_LEXICAL_RE.match(chunk)
    if m is None:
        raise ParserError(f"Invalid VERSION directive {chunk!r}", lno, cno)

    lexical: str = m.group(1)
    version: str = decode_escapes(lexical)
    if version not in ALLOWED_VERSIONS:
            raise ParserError(f"Invalid VERSION value {version!r}", lno, cno)

    return version


def _read_triple_and_graph(line: str, lno: int) -> ResultItem:
    names: list[str] = []
    chunk = line
    count = 0
    cno = 1

    c_offset: int
    trail: str

    m: re.Match | None

    while chunk != "":
        m = IRI_OR_BNODE_RE.match(chunk)
        if m is None:
            break

        name: str = m.group(1) if m.group(1) is not None else m.group(2)
        names.append(decode_unicode_escapes(name))

        c_offset = m.end()
        chunk = chunk[c_offset:]
        cno += c_offset

        count = len(names)

        if count > 4:
            raise ParserError(f"Too many terms {chunk!r}", lno, cno)

    if count < 2:
        raise ParserError(f"Too few terms {chunk!r}", lno, cno)

    s = _iri_or_bnode(names[0])
    p = names[1]

    o: Union[str, RdfLiteral, RdfTriple]
    g: str | None = None

    if count > 2:
        o = _iri_or_bnode(names[2])
        if count > 3:
            g = _iri_or_bnode(names[3])

        trail = chunk
    elif chunk.startswith('"'):
        lit_res = _read_literal(chunk, lno, cno)
        o = lit_res.literal
        trail = lit_res.trail
        cno = lit_res.cno

    elif chunk.startswith(TRIPLE_TERM_START):
        c_offset = len(TRIPLE_TERM_START)
        cno += c_offset
        item: ResultItem = _read_triple_and_graph(chunk[c_offset:], lno)
        cno += item.cno
        g = item.graph
        trail = item.trail
        if not isinstance(item.triple, RdfTriple):
            raise ParserError(f"Error in triple term {chunk!r}", lno, cno)

        o = item.triple

        m = TRIPLE_TERM_END_RE.match(trail)
        if m is None:
            raise ParserError(f"Incomplete triple term {chunk!r}", lno, cno)

        c_offset = m.end()
        trail = trail[c_offset:]
        cno += c_offset
    else:
        raise ParserError(f"Invalid term {chunk!r}", lno, cno)

    m = IRI_OR_BNODE_RE.match(trail)
    if m is not None:
        g_name: str = m.group(1) if m.group(1) is not None else m.group(2)
        g = _iri_or_bnode(decode_unicode_escapes(g_name))
        c_offset = m.end()
        trail = trail[c_offset:]
        cno += c_offset

    triple = RdfTriple(s, p, o)

    return ResultItem(cno, triple, g, trail)


def _iri_or_bnode(s: str) -> str:
    return s


def _read_literal(chunk: str, lno: int, cno: int) -> ParsedLiteral:
    m: re.Match |None = LITERAL_LEXICAL_RE.match(chunk)
    if m is None:
        raise ParserError(f"Invalid literal {chunk!r}", lno, cno)

    lexical: str = m.group(1)
    lexical = decode_escapes(lexical)
    c_offset: int = m.end()
    chunk = chunk[c_offset:]
    cno += c_offset

    m = LITERAL_TYPE_LANG_RE.match(chunk)
    o: RdfLiteral
    trail: str
    if m is None:
        o = RdfLiteral(lexical, XSD_STRING)
        trail = chunk
    else:
        c_offset = m.end()
        trail = chunk[c_offset:]
        cno += c_offset

        datatype: str | None = m.group(1)
        language: str | None = m.group(2)
        if language is None:
            if datatype is None:
                raise ParserError(f"Incomplete literal {chunk!r}", lno, cno)

            o = RdfLiteral(lexical, decode_unicode_escapes(datatype))
        else:
            language = language.lower()
            direction: str | None = m.group(3)
            assert datatype is None
            datatype = RDF_LANGSTRING if direction is None else RDF_DIRLANGSTRING
            if direction is not None:
                direction = direction.lower()
                if direction not in DIRECTIONS:
                    raise ParserError(
                        f"Invalid literal direction {direction!r}", lno, cno
                    )
            o = RdfLiteral(lexical, datatype, language, direction)

    return ParsedLiteral(o, trail, cno)
