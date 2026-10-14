from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, cast

from ..base import JsonMap, JsonObject
from ..keys import GRAPH, ID
from ..keys import ANNOTATION

IndexType = Dict[str, Tuple[Optional[Dict], List[Dict]]]


class Transformer:

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        pass

    def visit_node(self, index: IndexType, node: JsonMap, parent: Optional[Dict]):
        index_node(index, node, parent)

    def transform(self, index: IndexType, node: JsonMap, refs: List[Dict]) -> bool:
        return True


def run_transforms(doc: JsonObject, transforms: List[Transformer]) -> JsonObject:
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
            run_transforms(item, transforms)
        else:
            for transform in transforms:
                transform.visit_node(index, item, None)

    items = []

    node_id: str
    for node_id, node_and_refs in index.items():
        node: Optional[Dict]
        refs: List[Dict]
        (node, refs) = node_and_refs
        if node is None:
            continue

        keep_item = True
        for transform in transforms:
            if not transform.transform(index, node, refs):
                keep_item = False

        if keep_item:
            items.append(node)

    # filter empty nodes (e.g. skipping reifiers only used as annotations)
    items = [
        node for node in items
        if not (ID in node and len(node) == 1)
    ]

    items += graphs

    if isinstance(doc, List):
        return items
    else:
        assert isinstance(doc, Dict)
        if GRAPH not in doc:
            assert len(items) < 2
            return items[0] if items else items
        else:
            doc[GRAPH] = items

    for transform in transforms:
        transform.reset()

    return doc


def index_node(index, node, parent: Optional[Dict]) -> None:
    node_id: Optional[str] = None

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

        index[node_id] = full_node, refs
