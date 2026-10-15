from typing import Dict, Iterator, List, Optional, Set, Tuple, cast

from ...rdfterms import RDF_TYPE, RDF_REIFIES
from ..keys import GRAPH, ID, VALUE, TYPE, LANGUAGE, DIRECTION, LIST
from ..base import JsonMap, JsonObject
from ..keys import ANNOTATION, REIFIES, TRIPLE
from .transforms import IndexType, Transformer, run_transforms

Triple = Tuple[str, str, str, str]

Reifiers = Dict[Triple, List[Dict]]


def reduce_rdf_terms(doc: JsonObject) -> JsonObject:
    keyworsforms = KeywordForms()
    return run_transforms(doc, [keyworsforms])


class KeywordForms(Transformer):
    """
    Takes an expanded *and* flattened json-ld document structure, and replaces
    low-level RDF predicates (rdf:type and rdf:reifies) and triple terms with
    native JSON-LD keywords (@type, @annotation, @reifies).
    """

    reifiers: Reifiers

    def reset(self):
        self.reifiers = {}

    def visit_node(self, index: IndexType, node: JsonMap, parent: Optional[Dict]):
        super().visit_node(index, node, parent)
        for key in list(node.keys()):
            o: object = node[key]
            values: List = [] if o is None else o if isinstance(o, List) else [o]
            lowlevel_key = False
            lowlevel_remainder: List = []
            for value in values:
                if isinstance(value, Dict):
                    if key == RDF_TYPE:
                        lowlevel_key = True
                        if ID in value and len(value) == 1:
                            cast(List, node.setdefault(TYPE, [])).append(value[ID])
                        else:
                            lowlevel_remainder.append(value)
                    elif key == RDF_REIFIES:
                        lowlevel_key = True
                        if TRIPLE in value:
                            cast(List, node.setdefault(REIFIES, [])).append(value[TRIPLE])
                            triple = _to_triple_key(value[TRIPLE])
                            self.reifiers.setdefault(triple, []).append(node)
                        else:
                            lowlevel_remainder.append(value)
                    elif key == REIFIES:
                        triple = _to_triple_key(value)
                        self.reifiers.setdefault(triple, []).append(node)
                    else:
                        self.visit_node(index, value, node)

            if len(lowlevel_remainder) > 0:
                node[key] = lowlevel_remainder
            elif lowlevel_key:
                del node[key]

    def transform(self, index: IndexType, node: JsonMap, refs: List[Dict]) -> bool:
        if ID not in node:
            return True

        s = cast(str, node[ID])

        for key, value in list(node.items()):
            if not isinstance(value, List):
                value = [value]
            for v in value:
                triple = (s, key) + _to_triple_value(v)
                if triple in self.reifiers:
                    for reifier in self.reifiers[triple]:
                        if REIFIES in reifier:
                            triples = reifier[REIFIES]
                            if not isinstance(triples, List):
                                triples = [triples]
                            triples = [
                                t for t in triples if _to_triple_key(t) != triple
                            ]
                            annotation: Dict
                            if len(triples) == 0:
                                del reifier[REIFIES]
                                annotation = {ID: reifier[ID]}
                            else:
                                annotation = {ID: reifier[ID]}
                                reifier[REIFIES] = (
                                    triples[0] if len(triples) == 1 else triples
                                )

                            if not isinstance(v, Dict):
                                v = {VALUE: v}

                            annots: List
                            if ANNOTATION in v:
                                a = v[ANNOTATION]
                                annots = a if isinstance(a, List) else [annots]
                            else:
                                annots = []
                            annots.append(annotation)
                            v[ANNOTATION] = annots

        return True


def _to_triple_key(node: JsonMap) -> Triple:
    s: str
    p: str
    o: object

    for key, value in node.items():

        if key == ID:
            assert isinstance(value, str)
            s = value
        else:
            p = key
            assert isinstance(value, List) and len(value) == 1
            o = value[0]

    t, v = _to_triple_value(o)

    return (s, p, t, v)


def _to_triple_value(o: object) -> Tuple[str, str]:
    s: str
    t: str = ''
    v: str
    if isinstance(o, str):
        v = o
    elif isinstance(o, Dict):
        if ID in o:
            t = ID
            v = o[ID]
        elif TRIPLE in o:
            return TRIPLE, '\t'.join(_to_triple_value(o[TRIPLE]))
        elif LIST in o:
            t = LIST
            v = f"_:list-id-{id(o)}"
        else:
            v = o[VALUE]
            if TYPE in o:
                v = o[VALUE]
            elif LANGUAGE in o:
                t = o[LANGUAGE]
                if DIRECTION in o:
                    t += '--' + o[DIRECTION]
    else:
        t = type(o).__name__
        v = str(o)

    return (t, v)
