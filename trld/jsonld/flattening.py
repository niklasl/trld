from typing import Optional, Dict, List, Set, Union, cast
from ..common import warning
from .base import *


NodeMap = Dict[str, JsonMap]


class ConflictingIndexesError(JsonLdError): pass


class BNodes:
    i: int
    id_map: Dict[str, str]

    def __init__(self):
        self.i = 0
        self.id_map = {}

    def make_bnode_id(self, identifier: Optional[str] = None) -> str:
        if identifier in self.id_map:
            return self.id_map[identifier]
        bnode_id: str = f'_:b{str(self.i)}'
        self.i += 1
        if identifier is not None:
            self.id_map[identifier] = bnode_id
        return bnode_id


def flatten(element: JsonObject, ordered=False, bnodes: Optional[BNodes] = None) -> JsonObject:
    if bnodes is None:
        bnodes = BNodes()

    # 1)
    node_map: NodeMap = {DEFAULT: {}}
    # 2)
    make_node_map(bnodes, element, node_map)
    # 3)
    default_graph: Dict = node_map[DEFAULT]
    # 4)
    graph_names: List[str] = list(node_map.keys())
    if ordered:
        graph_names.sort()
    for graph_name in graph_names:
        if graph_name == DEFAULT:
            continue
        graph: JsonMap = cast(JsonMap, node_map[graph_name])
        # 4.1)
        if graph_name not in default_graph:
            default_graph[graph_name] = {ID: graph_name}
        # 4.2)
        entry: JsonMap = cast(JsonMap, default_graph[graph_name])
        # 4.3)
        entry_graph: List[JsonMap] = []
        entry[GRAPH] = entry_graph 
        # 4.4)
        node_ids: List[str] = list(graph.keys())
        if ordered:
            node_ids.sort()
        for node_id in node_ids:
            node: JsonMap = cast(JsonMap, graph[node_id])
            if len(node) > 1 or ID not in node:
                entry_graph.append(node)
    # 5)
    flattened: List[JsonMap] = []
    # 6)
    top_node_ids: List[str] = list(default_graph.keys())
    if ordered:
        top_node_ids.sort()
    for node_id in top_node_ids:
        top_node: JsonMap = cast(JsonMap, default_graph[node_id])
        if len(top_node) > 1 or ID not in top_node:
            flattened.append(top_node)
    # 7)
    return flattened


def make_node_map(bnodes: BNodes,
        element,
        node_map: NodeMap,
        active_graph: str = DEFAULT,
        active_subject: Optional[Union[str, JsonMap]] = None,
        active_property: Optional[str] = None,
        list_map: Optional[Dict[str, JsonObject]] = None):
    # 1)
    if isinstance(element, List):
        for item in element:
            # 1.1)
            make_node_map(bnodes, item, node_map, active_graph, active_subject,
                          active_property, list_map)
        return

    # 2)
    assert isinstance(element, Dict)
    # TODO: spec problem; seems to expect node_map[active_graph] to already be
    # set?
    graph: JsonMap = node_map.setdefault(active_graph, {})
    subject_node: Optional[JsonMap] = None
    if isinstance(active_subject, str):
        subject_node = cast(JsonMap, graph.get(active_subject))

    # 3)
    if TYPE in element:
        etype: object = element[TYPE]
        mapped_types: List = []
        for item in cast(List[str], as_list(etype)):
            # 3.1)
            if is_blank(item):
                item = bnodes.make_bnode_id(item)
            mapped_types.append(item)
        element[TYPE] = mapped_types if isinstance(etype, List) else mapped_types[0]

    # 4)
    if VALUE in element:
        assert subject_node is not None
        assert isinstance(active_property, str)
        # 4.1)
        if list_map is None:
            # 4.1.1)
            if active_property not in subject_node:
                subject_node[active_property] = [element]
            # 4.1.2)
            else:
                elements: List[JsonObject] = cast(List[JsonObject], subject_node[active_property])
                if not any(node_equals(element, el) for el in elements):
                    elements.append(element)
        # 4.2)
        else:
            cast(JsonList, list_map[LIST]).append(element)

    # 5)
    elif LIST in element:
        assert subject_node is not None
        assert isinstance(active_property, str)
        # 5.1)
        result: JsonMap = {LIST: []}
        # 5.2)
        make_node_map(bnodes, element[LIST], node_map, active_graph,
                      active_subject, active_property, result)
        # 5.3)
        if list_map is None:
            cast(JsonList, subject_node[active_property]).append(result)
        # 5.4)
        else:
            cast(JsonList, list_map[LIST]).append(result)

    # 6)
    else:
        # 6.1)
        eid: str
        if ID in element:
            eid = cast(str, element.pop(ID))
            if eid is None or is_blank(eid):
                eid = bnodes.make_bnode_id(eid)
        # 6.2)
        else:
            eid = bnodes.make_bnode_id(None)
        # 6.3)
        if eid not in graph:
            graph[eid] = {ID: eid}
        # 6.4)
        node: JsonMap = cast(JsonMap, graph[eid])
        # 6.5)
        if isinstance(active_subject, Dict): # reverse property relationship
            assert isinstance(active_property, str)
            # 6.5.1)
            if active_property not in node:
                node[active_property] = [active_subject]
            # 6.5.2)
            else:
                subjects: List[JsonMap] = cast(List[JsonMap] , node[active_property])
                if not any(node_equals(active_subject, subj) for subj in subjects):
                    subjects.append(active_subject)

        # 6.6)
        elif active_property is not None:
            assert subject_node is not None
            # 6.6.1)
            reference: JsonMap = {ID: eid}
            # 6.6.2)
            if list_map is None:
                # 6.6.2.1)
                if active_property not in subject_node:
                    subject_node[active_property] = [reference]
                # 6.6.2.2)
                objects: List[JsonMap] = cast(List[JsonMap], subject_node[active_property])
                if reference not in objects:
                    objects.append(reference)
            # 6.6.3)
            else:
                cast(JsonList, list_map[LIST]).append(reference)

        # 6.7)
        if TYPE in element:
            # TODO: spec problem; seems to expect node[TYPE] to already be set?
            ntypes: List = cast(List, node.setdefault(TYPE, []))
            for ntype in as_list(element[TYPE]):
                if ntype not in ntypes:
                    ntypes.append(ntype)
            del element[TYPE]

        # 6.8)
        if INDEX in element:
            if INDEX in node and node[INDEX] != element[INDEX]:
                raise ConflictingIndexesError(str(node[INDEX]))
            node[INDEX] = element.pop(INDEX)

        # 6.9)
        if REVERSE in element:
            # 6.9.1)
            referenced_node: JsonMap = {ID: eid}
            # 6.9.2)
            reverse_map: JsonMap = cast(JsonMap, element[REVERSE])
            # 6.9.3)
            for property, values in reverse_map.items():
                # 6.9.3.1)
                for value in cast(List, values):
                    # 6.9.3.1.1)
                    make_node_map(bnodes, value, node_map, active_graph,
                                  referenced_node, property)
            # 6.9.4)
            del element[REVERSE]

        # 6.10)
        if GRAPH in element:
            make_node_map(bnodes, element[GRAPH], node_map, eid)
            del element[GRAPH]

        # 6.11)
        if INCLUDED in element:
            make_node_map(bnodes, element[INCLUDED], node_map, active_graph)
            del element[INCLUDED]

        # 6.12)
        properties: List[str] = list(element.keys())
        properties.sort()
        for property in properties:
            evalue: JsonObject = element[property]
            # 6.12.1)
            if is_blank(property):
                property = bnodes.make_bnode_id(property)
            # 6.12.2)
            if property not in node:
                node[property] = []
            # 6.12.3)
            make_node_map(bnodes, evalue, node_map, active_graph, eid, property)


def merge_node_maps(node_maps: Dict[str, NodeMap]):
    # 1)
    result: JsonMap = {}
    # 2)
    for graph_name, node_map in node_maps.items():
        for node_id, node in node_map.items():
            # 2.1)
            merged_node: JsonMap = cast(JsonMap,
                    result.setdefault(node_id, {ID: node_id}))
            # 2.2)
            for property, values in node.items():
                # 2.2.1)
                if property != TYPE and property in KEYWORDS:
                    merged_node[property] = values
                # 2.2.2)
                else:
                    # TODO: recursive merge_node_maps...?
                    existing: List = cast(List,
                            merged_node.setdefault(property, []))
                    existing += cast(List, values)
    # 3)
    return result
