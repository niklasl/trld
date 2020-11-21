from typing import List, Optional, Iterable
from ..jsonld.rdf import RdfDataset, RdfGraph, RdfTriple, RdfLiteral, RdfObject


READ_STMT: int = 0
READ_IRI: int = 1
READ_BNODE_ID: int = 2
READ_STRING: int = 3
READ_LITERAL_END: int = 4
READ_DATATYPE_START: int = 5
READ_DATATYPE_NEXT: int = 6
READ_DATATYPE_IRI: int = 7
READ_LANGUAGE: int = 8
READ_COMMENT: int = 9
ESCAPE_NEXT: int = 10

ESCAPE_CHAR: str = '\\'


def parse(dataset: RdfDataset, stream: Iterable[str]):
    state: int = READ_STMT
    prev_state: int = -1
    chars: List[str] = []
    literal: Optional[str] = None
    datatype: Optional[str] = None
    language: Optional[str] = None
    terms: List[RdfObject] = []

    for c in stream:
        if c == ESCAPE_CHAR:
            prev_state = state
            state = ESCAPE_NEXT
            continue

        if state == ESCAPE_NEXT:
            state = prev_state
        elif state == READ_STMT:
            if c.isspace():
                continue
            elif c == '<':
                state = READ_IRI
                continue
            elif c == '_':
                state = READ_BNODE_ID
            elif c == '"':
                state = READ_STRING
                continue
            elif c == '.':
                if literal:
                    terms.append(RdfLiteral(literal, datatype, language))
                    literal = datatype = language = None
                handle_statement(dataset, terms)
                terms = []
                continue
            elif c == '#':
                state = READ_COMMENT
                continue
        elif state == READ_IRI or state == READ_DATATYPE_IRI:
            if c == '>':
                s: str = ''.join(chars)
                if state == READ_IRI:
                    terms.append(s)
                else:
                    datatype = s
                chars = []
                state = READ_STMT
                continue
        elif state == READ_BNODE_ID:
            if c.isspace():
                terms.append(''.join(chars))
                chars = []
                state = READ_STMT
                continue
        elif state == READ_STRING:
            if c == '"':
                literal = ''.join(chars)
                chars = []
                state = READ_LITERAL_END
                continue
        elif state == READ_LITERAL_END:
            if c == '@':
                state = READ_LANGUAGE
                continue
            elif c == '^':
                state = READ_DATATYPE_START
                continue
            elif c.isspace():
                if literal:
                    terms.append(RdfLiteral(literal, datatype, language))
                    literal = datatype = language = None
                state = READ_STMT
                continue
        elif state == READ_LANGUAGE:
            if c.isspace():
                language = ''.join(chars)
                chars = []
                state = READ_STMT
                continue
        elif state == READ_DATATYPE_START:
            if c == '^':
                state = READ_DATATYPE_NEXT
                continue
            else:
                raise Exception(f'Bad READ_DATATYPE_START char: {c}')
        elif state == READ_DATATYPE_NEXT:
            if c == '<':
                state = READ_DATATYPE_IRI
                continue
            else:
                raise Exception(f'Bad READ_DATATYPE_NEXT char: {c}')
        elif state == READ_COMMENT:
            if c == '\n':
                state = READ_STMT
            continue

        chars.append(c)

    if len(chars) != 0 or len(terms) != 0:
        raise Exception(f'Trailing data: chars={"".join(chars)}, terms={repr(terms)}')


def handle_statement(dataset: RdfDataset, terms):
    if len(terms) < 3 or len(terms) > 4:
        raise Exception(f'Invalid NQuads statement {str(terms)}')

    s = terms[0]
    p = terms[1]
    o = terms[2]
    g = terms[3] if len(terms) == 4 else None

    graph: RdfGraph
    if g is None:
        graph = dataset.default_graph
        if graph is None:
            graph = dataset.default_graph = RdfGraph()
    else:
        if g not in dataset.named_graphs:
            dataset.named_graphs[g] = RdfGraph(g)
        graph = dataset.named_graphs[g]

    graph.add(RdfTriple(s, p, o))


if __name__ == '__main__':
    from ..jsonld.rdf import to_jsonld
    import json
    import sys

    seq = (c for line in sys.stdin for c in line)
    dataset = RdfDataset()
    parse(dataset, seq)
    result = to_jsonld(dataset)
    print(json.dumps(result, indent=2))
