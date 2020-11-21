from typing import Optional
from ..jsonld.base import is_blank
from ..jsonld.rdf import RdfDataset, RdfGraph, RdfTriple, RdfLiteral, XSD_STRING


def serialize(dataset: RdfDataset, writeln):
    for graph in dataset:
        write_graph(graph, writeln)


def write_graph(graph: RdfGraph, writeln):
    for triple in graph.triples:
        if triple.s is None or triple.p is None or triple.o is None:
            continue
        writeln(repr_quad(triple, graph.name))


def repr_quad(triple: RdfTriple, graph_name: Optional[str]) -> str:
    s: str = repr_term(triple.s)
    p: str = repr_term(triple.p)
    o: str = repr_term(triple.o)
    spo: str = f'{s} {p} {o}'
    quad: str = f'{spo} {repr_term(graph_name)}' if graph_name else spo
    return f'{quad} .'


def repr_term(t: object) -> str:
    if isinstance(t, str):
        if is_blank(t):
            return t
        else:
            return f'<{t}>'
    else:
        assert isinstance(t, RdfLiteral)
        v: str = t.value
        v = v.replace('\\', r'\\')
        v = v.replace('"', r'\"')
        v = f'"{v}"'
        if t.language:
            return f'{v}@{t.language}'
        elif t.datatype and t.datatype != XSD_STRING:
            dt: str = repr_term(t.datatype)
            return f'{v}^^{dt}'
        else:
            return v
