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
        if t.language is not None:
            return f'{v}@{t.language}'
        elif t.datatype is not None and t.datatype != XSD_STRING:
            dt: str = repr_term(t.datatype)
            return f'{v}^^{dt}'
        else:
            return v
