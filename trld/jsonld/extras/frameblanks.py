from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, cast

from ..keys import GRAPH, ID
from ..base import JsonMap, JsonObject
from ..keys import ANNOTATION, REIFIES, TRIPLE
from .transforms import IndexType, Transformer, run_transforms


def frameblanks(doc: JsonObject) -> JsonObject:
    blanksframer = BlanksFramer()
    return run_transforms(doc, [blanksframer])


class BlanksFramer(Transformer):

    def visit_node(self, index: IndexType, node: JsonMap, parent: Optional[Dict]):
        super().visit_node(index, node, parent)
        for key, value in node.items():
            if isinstance(value, dict):
                if key == REIFIES:
                    continue
                if key == TRIPLE:
                    continue

            if isinstance(value, List):
                for v in value:
                    if isinstance(v, Dict):
                        self.visit_node(index, v, node)
            elif isinstance(value, Dict):
                self.visit_node(index, value, node)

    def transform(self, index: IndexType, node: JsonMap, refs: List[Dict]) -> bool:
        node_id = cast(Optional[str], node.get(ID))
        if node_id is not None and node_id.startswith('_:'):
            if len(refs) == 1:
                ref = refs[0]
                if REIFIES not in node or ref[ID] != node_id:
                    ref.update(node)
                    del ref[ID]
                    return False
            elif len(refs) == 0:
                del node[ID]

        return True
