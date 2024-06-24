from collections import OrderedDict
from typing import Optional

from ..keys import GRAPH, ID
from ..base import JsonObject
from ..star import ANNOTATION


def frameblanks(doc: JsonObject) -> JsonObject:
    data = doc
    if isinstance(data, dict):
        if GRAPH in data:
            data = data[GRAPH]
    items = data if isinstance(data, list) else [data] if data is not None else []

    index: dict[str, tuple[dict, list[dict]]] = OrderedDict()

    graphs = []

    for item in items:
        assert isinstance(item, dict)
        if GRAPH in item:
            graphs.append(item)
        else:
            visit_node(index, item, None)

    items = graphs

    for id, (node, refs) in index.items():
        if node is None:
            continue

        if id.startswith('_:'):
            if len(refs) == 1:
                refs[0].update(node)
                del refs[0][ID]
                continue

        items.append(node)

    if isinstance(doc, list):
        return items
    else:
        assert isinstance(doc, dict)
        if GRAPH not in doc:
            assert len(items) < 2
            return items[0] if items else items
        else:
            doc[GRAPH] = items

    return doc


def visit_node(index: dict, node: dict, parent: Optional[dict]):
    id = node.get(ID)
    if id is not None:
        full_node: dict | None
        refs: list[dict]
        if id in index:
            full_node, refs = index[id]
        else:
            full_node = None
            refs = []

        isref = len(node) == (2 if ANNOTATION in node else 1)
        if isref:
            assert parent, f"Unexpected orphaned ref: {node}"
            refs.append(node)
        else:
            full_node = node

        index[id] = full_node, refs

    for value in node.values():
        if isinstance(value, list):
            for v in value:
                if isinstance(v, dict):
                    visit_node(index, v, node)
        elif isinstance(value, dict):
            visit_node(index, value, node)
