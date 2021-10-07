from typing import List, Dict, Set, Iterable, Iterator, Union, Optional, NamedTuple, cast
from ..common import dump_canonical_json, parse_json
from .base import *
from .context import InvalidBaseDirectionError
from .expansion import InvalidLanguageTaggedStringError
from .flattening import BNodes, NodeMap, make_node_map
from ..rdfterms import (
    RDF_TYPE,
    RDF_VALUE,
    RDF_LIST,
    RDF_FIRST,
    RDF_REST,
    RDF_NIL,
    RDF_DIRECTION,
    RDF_LANGUAGE,
    RDF_JSON,
    RDF_LANGSTRING,
    XSD_BOOLEAN,
    XSD_DOUBLE,
    XSD_INTEGER,
    XSD_STRING,
    I18N,
)


MAX_INT: float = pow(10, 21)

COMPOUND_LITERAL: str = 'compound-literal'
I18N_DATATYPE: str = 'i18n-datatype'

USAGES: str = 'usages'


# TODO: global flag or add to processor
processing_mode: str = JSONLD11


class RdfLiteral(NamedTuple):
    value: str
    datatype: Optional[str] = None
    language: Optional[str] = None


RdfObject = Union[str, RdfLiteral]


class RdfTriple(NamedTuple):
    s: str
    p: str
    o: RdfObject


class RdfGraph:
    name: Optional[str]
    triples: List[RdfTriple]

    def __init__(self, name: Optional[str] = None):
        self.name = name
        self.triples = []

    def add(self, triple: RdfTriple):
        self.triples.append(triple)


class RdfDataset:
    default_graph: RdfGraph
    named_graphs: Dict[str, RdfGraph]

    def __init__(self):
        self.default_graph = RdfGraph()
        self.named_graphs = {}

    def add(self, graph: RdfGraph):
        if graph.name:
            self.named_graphs[graph.name] = graph
        else:
            self.default_graph = graph

    def __iter__(self) -> Iterator[RdfGraph]:
        yield self.default_graph
        yield from self.named_graphs.values()


class _Usage(NamedTuple):
    node: JsonMap
    property: str
    value: JsonMap


def to_rdf_dataset(data: JsonObject,
        rdf_direction: Optional[str] = None) -> RdfDataset:
    bnodes: BNodes = BNodes()
    dataset: RdfDataset = RdfDataset()
    node_map: NodeMap = {DEFAULT: {}}
    make_node_map(bnodes, data, node_map)

    jsonld_to_rdf_dataset(node_map, dataset, bnodes, rdf_direction)

    return dataset


def jsonld_to_rdf_dataset(node_map: NodeMap, dataset: RdfDataset,
                   bnodes: BNodes, rdf_direction: Optional[str] = None):
    # 1)
    for graph_name in cast(List[str], sorted(node_map.keys())):
        graph: Dict = node_map[graph_name]
        # 1.1)
        if not (is_iri(graph_name) or is_blank(graph_name) or graph_name == DEFAULT):
            continue
        # 1.2)
        triples: RdfGraph
        if graph_name == DEFAULT:
            triples = dataset.default_graph
        else:
            triples = RdfGraph(graph_name)
            dataset.add(triples)
        # 1.3)
        for subject in cast(Iterable[str], sorted(graph.keys())):
            node: JsonMap = graph[subject]
            # 1.3.1)
            if not is_iri_or_blank(subject):
                continue
            # 1.3.2)
            for property in cast(Iterable[str], sorted(node.keys())):
                # TODO: isn't this always a list if this is properly expanded
                # and flattened (as this algoritm implicitly expects..)?
                values: List[object] = as_list(node[property])
                # 1.3.2.1)
                if property == TYPE:
                    for type in values:
                        triples.add(RdfTriple(subject, RDF_TYPE, cast(str, type)))
                # 1.3.2.2)
                elif property in KEYWORDS:
                    continue
                # 1.3.2.3)
                elif is_blank(property): # TODO: and not options.produce_generalized_rdf
                    continue
                # 1.3.2.4)
                elif not is_iri_or_blank(property):
                    continue
                # 1.3.2.5)
                else:
                    for item in values:
                        assert isinstance(item, Dict)
                        # 1.3.2.5.1)
                        list_triples: List[RdfTriple] = []
                        # 1.3.2.5.2)
                        rdf_object: RdfObject = cast(RdfObject,
                                object_to_rdf_data(item, list_triples, bnodes, rdf_direction))
                        list_triples.append(RdfTriple(subject, property, rdf_object))
                        # 1.3.2.5.3)
                        for triple in list_triples:
                            triples.add(triple)


def object_to_rdf_data(item: JsonMap, list_triples: List, bnodes: BNodes,
        rdf_direction: Optional[str] = None) -> Optional[RdfObject]:
    # 1)
    if ID in item and not is_iri_or_blank(cast(str, item[ID])):
        return None
    # 2)
    if ID in item:
        return cast(str, item[ID])
    # 3)
    if LIST in item:
        return list_to_rdf_list(cast(List, item[LIST]), list_triples, bnodes, rdf_direction)
    # 4)
    assert VALUE in item
    value: JsonObject = item[VALUE]
    # 5)
    datatype: Optional[str] = cast(Optional[str], item.get(TYPE))
    # 6)
    if datatype is not None and not is_iri(datatype) and not datatype == JSON:
        return None
    # 7)
    if LANGUAGE in item and not is_lang_tag(cast(str, item[LANGUAGE])):
        return None
    # 8)
    if datatype == JSON:
        value = dump_canonical_json(value)
        datatype = RDF_JSON
    # 9)
    if isinstance(value, bool):
        value = 'true' if value else 'false'
        if datatype is None:
            datatype = XSD_BOOLEAN
    # 10)
    elif isinstance(value, (int, float)) and ((cast(float, value) % 1 > 0 or cast(float, value) >= MAX_INT) or datatype == XSD_DOUBLE):
        value = str(value) # TODO: to_canonical_double(value)
        if datatype is None:
            datatype = XSD_DOUBLE
    # 11)
    elif isinstance(value, (int, float)):
        value = str(value) # TODO: to_canonical_integer(value)
        if datatype is None:
            datatype = XSD_INTEGER
    # 12)
    elif datatype is None:
        datatype = RDF_LANGSTRING if LANGUAGE in item else XSD_STRING
    # 13)
    assert isinstance(value, str)
    literal: Optional[RdfObject] = None
    if DIRECTION in item and rdf_direction is not None:
        # 13.1)
        language: str = cast(str, item.get(LANGUAGE, ''))
        language = language.lower()
        # 13.2)
        if rdf_direction == I18N_DATATYPE:
            datatype = f'{I18N}{language}_{item[DIRECTION]}'
            literal = RdfLiteral(value, datatype)
        # 13.3)
        elif rdf_direction == COMPOUND_LITERAL:
            # 13.3.1)
            nodeid: str = bnodes.make_bnode_id()
            literal = nodeid
            # 13.3.2)
            # TODO: spec errata? says to use item[VALUE] (not to use the stringified value)
            list_triples.append(RdfTriple(nodeid, RDF_VALUE, RdfLiteral(value)))
            # 13.3.3)
            if LANGUAGE in item:
                list_triples.append(RdfTriple(nodeid, RDF_LANGUAGE, RdfLiteral(cast(str, item[LANGUAGE]))))
            # 13.3.4)
            list_triples.append(RdfTriple(nodeid, RDF_DIRECTION, RdfLiteral(cast(str, item[DIRECTION]))))
    # 14)
    else:
        literal = RdfLiteral(value, datatype, cast(Optional[str], item.get(LANGUAGE)))
    # 15)
    return literal


def list_to_rdf_list(l: List[JsonMap], list_triples: List, bnodes: BNodes,
        rdf_direction: Optional[str] = None) -> str:
    # 1)
    if len(l) == 0:
        return RDF_NIL
    # 2)
    # NOTE: made this a little different from spec...
    # 3)
    subject: str = bnodes.make_bnode_id()
    first: str = subject
    i: int = 0
    for item in l:
        # 3.1)
        embedded_triples: List = []
        # 3.2)
        obj: Optional[RdfObject] = object_to_rdf_data(item, embedded_triples, bnodes, rdf_direction)
        # 3.3)
        if obj is not None:
            list_triples.append(RdfTriple(subject, RDF_FIRST, obj))
        # 3.4)
        i += 1
        next_subject: str = bnodes.make_bnode_id() if i < len(l) else RDF_NIL
        list_triples.append(RdfTriple(subject, RDF_REST, next_subject))
        subject = next_subject
        # 3.5)
        list_triples += embedded_triples
    # 4)
    return first if i > 0 else RDF_NIL


def to_jsonld(dataset: RdfDataset,
        ordered=False,
        rdf_direction: Optional[str] = None,
        use_native_types=False,
        use_rdf_type=False) -> List[JsonMap]:
    # 1)
    default_graph: Dict[str, JsonMap] = {}
    # 2)
    graph_map: Dict[str, Dict[str, JsonMap]] = {DEFAULT: default_graph}
    # 3)
    referenced_once: Dict[str, Union[_Usage, bool]] = {}
    # 4)
    compound_literal_subjects: Dict[str, Set[str]] = {}

    # 5)
    for graph in dataset:
        # 5.1)
        name: str = DEFAULT if graph.name is None else graph.name
        # 5.2)
        graph_map.setdefault(name, {})
        # 5.3)
        compound_literal_subjects.setdefault(name, set())
        # 5.4)
        if name != DEFAULT:
            default_graph.setdefault(name, {ID: name})
        # 5.5)
        node_map: Dict[str, JsonMap] = cast(Dict[str, JsonMap], graph_map[name])
        # 5.6)
        compounds: Set[str] = compound_literal_subjects[name]

        # 5.7)
        for triple in graph.triples:
            # 5.7.1)
            if triple.s not in node_map:
                node_map[triple.s] = {ID: triple.s}
            # 5.7.2)
            node: JsonMap = node_map[triple.s]
            # 5.7.3)
            if rdf_direction == COMPOUND_LITERAL and triple.p == RDF_DIRECTION:
                compounds.add(triple.s)
            # 5.7.4)
            if isinstance(triple.o, str) and triple.o not in node_map:
                node_map[triple.o] = {ID: triple.o}
            # 5.7.5)
            if triple.p == RDF_TYPE and not use_rdf_type and isinstance(triple.o, str):
                types: List = cast(List, node.setdefault(TYPE, []))
                if not any(t == triple.o for t in types):
                    types.append(triple.o)
                continue
            # 5.7.6)
            value: JsonMap = to_jsonld_object(triple.o, rdf_direction, use_native_types)
            # 5.7.7)
            values: List[JsonObject] = cast(List, node.setdefault(triple.p, []))
            # 5.7.8)
            # TODO: spec errata; continue instead, to avoid duplicates in 5.7.9
            # (see fromRdf/0022)
            if any(node_equals(v, value) for v in values):
                continue
            values.append(value)
            # 5.7.9)
            if triple.o == RDF_NIL:
                # 5.7.9.1)
                obj: JsonMap = node_map[cast(str, triple.o)]
                obj_usages: List = cast(List, obj.setdefault(USAGES, []))
                # 5.7.9.2)
                obj_usages.append(_Usage(node, triple.p, value))
            # 5.7.10)
            elif triple.o in referenced_once:
                referenced_once[cast(str, triple.o)] = False
            # 5.7.11)
            elif isinstance(triple.o, str) and is_blank(triple.o):
                # 5.7.11.1)
                usage: _Usage = _Usage(node, triple.p, value)
                referenced_once[triple.o] = usage
                # TODO: spec seems to have an overeager copy/paste error
                # ("and values to the usages array") from just above.

    # 6)
    for name, graph_object in graph_map.items():
        # 6.1)
        if name in compound_literal_subjects:
            # TODO: handle getitem in transpile
            graph_compounds: Set[str] = compound_literal_subjects[name]
            for cl in graph_compounds:
                # 6.1.1)
                cl_entry: object = referenced_once.get(cl)
                if not isinstance(cl_entry, _Usage):
                    continue
                # 6.1.2)
                c_node: JsonMap = cl_entry.node
                # 6.1.3)
                c_property: str = cl_entry.property
                # 6.1.4)
                # TODO: spec errata? not used...
                #c_value: JsonObject = cl_entry.value
                # 6.1.5)
                cl_node: JsonMap = cast(JsonMap, graph_object.pop(cl))
                # 6.1.6)
                for cl_ref in cast(List, c_node[c_property]):
                    assert isinstance(cl_ref, Dict)
                    if not cl_ref[ID] == cl:
                        continue
                    # 6.1.6.1)
                    del cl_ref[ID]
                    # 6.1.6.2)
                    cl_ref[VALUE] = cast(Dict, cast(List, cl_node[RDF_VALUE])[0])[VALUE]
                    # 6.1.6.3)
                    if RDF_LANGUAGE in cl_node:
                        cl_ref[LANGUAGE] = cast(Dict, cast(List, cl_node[RDF_LANGUAGE])[0])[VALUE]
                        if not is_lang_tag(cast(str, cl_ref[LANGUAGE])):
                            raise InvalidLanguageTaggedStringError(str(cl_ref[LANGUAGE]))
                    # 6.1.6.4)
                    if RDF_DIRECTION in cl_node:
                        cl_ref[DIRECTION] = cast(Dict, cast(List, cl_node[RDF_DIRECTION])[0])[VALUE]
                        if not cl_ref[DIRECTION] in DIRECTIONS:
                            raise InvalidBaseDirectionError(str(cl_ref[DIRECTION]))
        # 6.2)
        if RDF_NIL not in graph_object:
            continue
        # 6.3)
        nil: JsonMap = cast(JsonMap, graph_object[RDF_NIL])
        # 6.4)
        if USAGES not in nil:
            continue
        for usage in cast(List[_Usage], nil[USAGES]):
            # 6.4.1)
            unode: JsonMap = usage.node
            uproperty: str = usage.property
            head: JsonMap = usage.value
            # 6.4.2)
            list_values: List = []
            list_nodes: List = []
            # 6.4.3)
            while uproperty == RDF_REST and is_well_formed_list(unode):
                # 6.4.3.3)
                node_usage: Union[_Usage, bool] = referenced_once[cast(str, unode[ID])]
                if not isinstance(node_usage, _Usage):
                    break
                # 6.4.3.1)
                list_values.append(cast(List, unode[RDF_FIRST])[0])
                # 6.4.3.2)
                list_nodes.append(unode[ID])
                # 6.4.3.4)
                unode = node_usage.node
                uproperty = node_usage.property
                head = node_usage.value
                # 6.4.3.5)
                if is_iri(cast(str, unode[ID])):
                    break
            # 6.4.4)
            del head[ID]
            # 6.4.5)
            list_values.reverse()
            # 6.4.6)
            head[LIST] = list_values
            # 6.4.7)
            for node_id in list_nodes:
                del graph_object[node_id]

    # 7)
    result: List[JsonMap] = []
    # 8)
    subjects: List[str] = list(default_graph.keys())
    if ordered:
        subjects.sort()
    for subject in subjects:
        s_node: JsonMap = cast(JsonMap, default_graph[subject])
        # 8.1)
        if subject in graph_map:
            subject_graph: Dict[str, JsonMap] = graph_map[subject]
            # 8.1.1)
            named_graphs: List = []
            s_node[GRAPH] = named_graphs
            # 8.1.2)
            graph_names: List = list(subject_graph.keys())
            if ordered:
                graph_names.sort()
            for graph_name in graph_names:
                named: JsonMap = cast(JsonMap, subject_graph[graph_name])
                if USAGES in named:
                    del named[USAGES]
                if not len(named) == 1 and ID in named:
                    named_graphs.append(named)
        # 8.2)
        if USAGES in s_node:
            del s_node[USAGES]
        if not len(s_node) == 1 and ID in s_node:
            result.append(s_node)
    # 9)
    return result


def to_jsonld_object(value: RdfObject,
        rdf_direction: Optional[str],
        use_native_types: bool) -> JsonMap:
    # 1)
    if isinstance(value, str):
        return {ID: value}

    # 2)
    literal: RdfLiteral = value
    # 2.1)
    result: JsonMap = {}
    # 2.2)
    # TODO: spec errata? says: value
    converted_value: JsonObject = literal.value
    # 2.3)
    rtype: Optional[str] = None

    # 2.4)
    if use_native_types:
        if literal.datatype == XSD_STRING:
            converted_value = literal.value
        elif literal.datatype == XSD_BOOLEAN:
            if literal.value == 'true':
                converted_value = True
            elif literal.value == 'false':
                converted_value = False
            else:
                rtype = XSD_BOOLEAN
        elif literal.datatype == XSD_INTEGER and literal.value.isdecimal():
            converted_value = int(literal.value)
        elif literal.datatype == XSD_DOUBLE:# and all(c == '.' or c.isdecimal() for c in literal.value):
            try:
                converted_value = float(literal.value)
            except ValueError:
                pass
        # TODO: spec errata; only done in an otherwise below (thus fromRdf/0018 fails)
        elif literal.datatype != XSD_STRING:
            rtype = literal.datatype
    # 2.5)
    elif literal.datatype == RDF_JSON and processing_mode != JSONLD10:
        try:
            converted_value = cast(JsonObject, parse_json(literal.value))
        except:# json.decoder.JSONDecodeError
            pass
        rtype = JSON
    # 2.6)
    elif rdf_direction == I18N_DATATYPE and literal.datatype is not None and literal.datatype.startswith(I18N):
        # 2.6.1)
        converted_value = literal.value
        # 2.6.2)
        frag_id: str = literal.datatype[len(I18N):]
        i: int = frag_id.find('_')
        lang: str = frag_id
        direction: str = ''
        if i > -1:
            lang = frag_id[:i]
            direction = frag_id[i + 1:]
        if len(lang) > 0:
            result[LANGUAGE] = lang
        # 2.6.3)
        if len(direction) > 0:
            result[DIRECTION] = direction
    # 2.7)
    elif literal.language is not None:
        result[LANGUAGE] = literal.language
    # 2.8)
    elif literal.datatype and literal.datatype != XSD_STRING:
        rtype = literal.datatype

    # 2.9)
    result[VALUE] = converted_value
    # 2.10)
    if rtype:
        result[TYPE] = rtype

    # 2.11)
    return result


def is_iri_or_blank(iri: str) -> bool:
    return is_iri(iri) or is_blank(iri)


def is_well_formed_list(node: JsonMap) -> bool:
    return is_blank(cast(str, node[ID])) and \
            _has_list_with_one_item(node, RDF_FIRST) and \
            _has_list_with_one_item(node, RDF_REST) and \
            (len(node) == 3 or len(node) == 4 and TYPE in node and
                    as_list(node[TYPE])[0] == RDF_LIST)


def _has_list_with_one_item(node: JsonMap, p) -> bool:
    return p in node and isinstance(node[p], List) and len(cast(List, node[p])) == 1
