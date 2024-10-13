from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, cast

from ..keys import GRAPH, ID
from ..base import JsonObject
from ..star import ANNOTATION

IndexType = Dict[str, Tuple[Optional[Dict], List[Dict]]]


def frameblanks(doc: JsonObject) -> JsonObject:
    data = doc
    if isinstance(data, Dict):
        if GRAPH in data:
            data = data[GRAPH]
    items: List = data if isinstance(data, List) else [data] if data is not None else []

    index: IndexType = OrderedDict()

    graphs = []

    for item in items:
        assert isinstance(item, Dict)
        if GRAPH in item:
            graphs.append(item)
        else:
            visit_node(index, item, None)

    items = graphs

    node_id: str
    for node_id, node_and_refs in index.items():
        node: Optional[Dict]
        refs: List[Dict]
        (node, refs) = node_and_refs
        if node is None:
            continue

        if node_id.startswith('_:'):
            if len(refs) == 1:
                ref = refs[0]
                ref.update(node)
                del ref[ID]
                continue

        items.append(node)

    if isinstance(doc, List):
        return items
    else:
        assert isinstance(doc, Dict)
        if GRAPH not in doc:
            assert len(items) < 2
            return items[0] if items else items
        else:
            doc[GRAPH] = items

    return doc


def visit_node(index: IndexType, node: Dict[str, object], parent: Optional[Dict]):
    if ID in node:
        node_id = cast(str, node[ID])
        full_node: Optional[Dict]
        refs: List[Dict]
        if node_id in index:
            full_node, refs = index[node_id]
        else:
            full_node = None
            refs = []

        isref = len(node) == (2 if ANNOTATION in node else 1)
        if isref:
            assert parent, f"Unexpected orphaned ref: {node}"
            refs.append(node)
        else:
            full_node = node

        if isinstance(full_node, Dict):
            index[node_id] = full_node, refs

    for value in node.values():
        if isinstance(value, List):
            for v in value:
                if isinstance(v, Dict):
                    visit_node(index, v, node)
        elif isinstance(value, Dict):
            visit_node(index, value, node)
