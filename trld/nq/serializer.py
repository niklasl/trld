from typing import Optional
from ..platform.io import Output
from ..jsonld.base import is_blank
from ..jsonld.rdf import RdfDataset, RdfGraph, RdfLiteral, RdfObject, RdfTriple
from ..rdfterms import XSD_STRING


def serialize(dataset: RdfDataset, out: Output):
    for graph_name, graph in dataset:
        write_graph(graph_name, graph, out)


def write_graph(graph_name: Optional[str], graph: RdfGraph, out: Output):
    for triple in graph:
        if triple.subject is None or triple.predicate is None or triple.object is None:
            continue
        out.writeln(repr_quad(triple, graph_name))


def repr_quad(triple: RdfTriple, graph_name: Optional[str]) -> str:
    s: str = repr_term(triple.subject)
    p: str = repr_term(triple.predicate)
    o: str = repr_term(triple.object)
    spo: str = f'{s} {p} {o}'
    quad: str = f'{spo} {repr_term(graph_name)}' if graph_name else spo
    return f'{quad} .'


def repr_term(t: RdfObject) -> str:
    # NOTE: according to <https://www.w3.org/TR/rdf-canon/#canonical-quads>
    if isinstance(t, str):
        if is_blank(t):
            return t
        else:
            return f'<{t}>'
    else:
        assert isinstance(t, RdfLiteral)
        v: str = t.value
        # Characters BS (backspace, code point U+0008), HT (horizontal tab,
        # code point U+0009), LF (line feed, code point U+000A), FF (form feed,
        # code point U+000C), CR (carriage return, code point U+000D), "
        # (quotation mark, code point U+0022), and \ (backslash, code point
        # U+005C) MUST be encoded using ECHAR.
        v = v.replace('\\', r'\\')
        v = v.replace('"', r'\"')
        v = v.replace('\b', r'\b')
        v = v.replace('\t', r'\t')
        v = v.replace('\n', r'\n')
        v = v.replace('\f', r'\f')
        v = v.replace('\r', r'\r')

        # Characters in the range from U+0000 to U+0007, VT (vertical tab, code
        # point U+000B), characters in the range from U+000E to U+001F, DEL
        # (delete, code point U+007F), and characters not matching the Char
        # production from [XML11] MUST be represented by UCHAR using a
        # lowercase \u with 4 HEXes.
        v = ''.join(fr"\u{ord(c):04X}" if _needs_unicode_esc(c) else c for c in v)

        # All characters not required to be represented by ECHAR or UCHAR MUST
        # be represented by their native [UNICODE] representation.
        v = f'"{v}"'
        if t.language is not None:
            return f'{v}@{t.language}'
        elif t.datatype is not None and t.datatype != XSD_STRING:
            dt: str = repr_term(t.datatype)
            return f'{v}^^{dt}'
        else:
            return v


def _needs_unicode_esc(c: str) -> bool:
    cp = ord(c)
    return (
        (0x00 < cp <= 0x07)
        or cp == 0x0B
        or (0x0E < cp <= 0x1F)
        or cp == 0x7F
        or not (
            # Char from <https://www.w3.org/TR/xml11/#charsets>
            (0x01 < cp <= 0xD7FF)
            or (0xE000 < cp <= 0xFFFD)
            or (0x10000 < cp <= 0x10FFFF)
        )
    )
