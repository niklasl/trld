from typing import (Any, Dict, Iterable, List, NamedTuple, Optional, Tuple,
                    Union, cast)

from ..jsonld.base import (CONTEXT, DIRECTION, GRAPH, ID, LANGUAGE, LIST, SET,
                           TYPE, VALUE)
from ..jsonld.star import ANNOTATED_TYPE_KEY, ANNOTATION

LITERAL_ID_KEYS = [VALUE, TYPE, LANGUAGE, DIRECTION]

DictList = List[Dict]


class DiffKeys(NamedTuple):
    asserted: str = 'assertedIn'
    added: str = 'addedIn'
    removed: str = 'removedIn'
    v_type: Optional[str] = None
    v_prev: Optional[str] = None
    v_next: Optional[str] = None
    v_latest: Optional[str] = None

    def describe_versions(self, graphs: DictList) -> DictList:
        if not (self.v_type or self.v_prev or self.v_next or self.v_latest):
            return []

        versions: DictList = []
        prev: Optional[Dict] = None
        for g in graphs:
            version = {ID: g[ID]}
            if self.v_type:
                version[TYPE] = self.v_type
            if self.v_latest:
                version[self.v_latest] = {ID: graphs[-1][ID]}
            if prev:
                if self.v_prev:
                    version[self.v_prev] = {ID: prev[ID]}
                if self.v_next:
                    prev[self.v_next] = {ID: version[ID]}
            prev = version
            versions.append(version)

        return versions


class Differ:
    blame: bool
    annots: DictList
    keys: DiffKeys

    def __init__(self, blame=False, keys: DiffKeys = None):
        self.blame = blame
        self.annots = []
        self.keys = keys if keys is not None else DiffKeys()

    def diff(self, versions: DictList) -> Dict:
        diffgraph = self.make_annotated_union(versions)

        if self.blame:
            self._annotate_addedremoved(versions)

        diffgraph[GRAPH] = self.keys.describe_versions(versions) + cast(
            List, diffgraph[GRAPH]
        )

        return diffgraph

    def make_annotated_union(self, versions: DictList) -> Dict:
        merged: Dict[str, object] = {}

        context: object = cast(Dict, versions[0]).get(CONTEXT)
        merged[CONTEXT] = context

        copies: Dict[str, Dict] = {}

        for version in versions:
            nodes: DictList = version[GRAPH]
            self._copy_annotated(nodes, GRAPH, -1, merged, cast(str, version[ID]))

        return merged

    def _copy_annotated(
        self, data, key: str, pos: int, merged: Union[List, Dict], v_id: str
    ):
        if isinstance(data, List):
            assert isinstance(merged, Dict)
            copied: List = merged.setdefault(key, [])
            if not isinstance(copied, List):
                copied = [copied]
                merged[key] = copied

            for i, item in enumerate(data):
                self._copy_annotated(item, key, i, copied, v_id)

        elif isinstance(data, Dict):
            node: Dict[str, object] = data
            if VALUE in node:
                self._annotate_node(node, key, pos, merged, v_id, LITERAL_ID_KEYS)
            else:
                anode: Dict = self._annotate_node(node, key, pos, merged, v_id, [ID])
                for k, v in node.items():
                    if k == ID:
                        continue
                    self._copy_annotated(v, k, -1, anode, v_id)
        else:
            id_keys: List[str]
            if key == TYPE:
                data = {ANNOTATED_TYPE_KEY: data}
                id_keys = [ANNOTATED_TYPE_KEY]
            else:
                data = {VALUE: data}
                id_keys = LITERAL_ID_KEYS

            self._annotate_node(cast(Dict, data), key, pos, merged, v_id, id_keys)

    def _annotate_node(
        self,
        data: Dict,
        key: str,
        pos: int,
        merged: Union[List, Dict],
        v_id: str,
        id_key_spec: List[str],
    ) -> Dict:
        data_id = make_id_key(data, id_key_spec)
        node: Optional[Dict] = None
        if isinstance(merged, List):
            assert pos > -1
            for givennode in cast(DictList, merged):
                if data_id and make_id_key(givennode, id_key_spec) == data_id:
                    node = givennode
                    break
            if node is None:
                if (
                    len(merged) <= pos
                    or make_id_key(cast(Dict, merged[pos]), id_key_spec) != data_id
                ):
                    node = {}
                    for id_key in id_key_spec:
                        if id_key in data:
                            node[id_key] = data[id_key]
                    merged.append(node)
                else:
                    node = cast(Dict, merged[pos])
        else:
            assert isinstance(merged, Dict)
            given: object = merged.get(key)
            for givennode in aslist(given):
                if make_id_key(cast(Dict, givennode), id_key_spec) == data_id:
                    node = givennode
                    break

            if node is None:
                node = {}
                if data_id is not None:
                    for id_key in id_key_spec:
                        if id_key in data:
                            node[id_key] = data[id_key]

                if given:
                    if not isinstance(given, List):
                        given = [given]
                        merged[key] = given
                    given.append(node)
                else:
                    merged[key] = node

        if key != ID and key != GRAPH:
            self._link_assertion(node, v_id)

        return node

    def _link_assertion(self, node: Dict, link: str):
        #node.setdefault(f'_{key}', []).append(link)
        annot: Dict
        if ANNOTATION not in node:
            annot = {}
            node[ANNOTATION] = annot
            self.annots.append(annot)
        else:
            annot = node[ANNOTATION]

        key = self.keys.asserted
        links: DictList
        if key in annot:
            links = cast(DictList, cast(Dict, annot[key])[LIST])
        else:
            links = []
            annot[key] = {LIST: links}
        links.append({ID: link})

    def _annotate_addedremoved(self, graphs: DictList):
        nextindex: Dict[str, str] = {}

        prev_id: Optional[str] = None
        for g in graphs:
            current_id: str = g[ID]
            if prev_id:
                nextindex[prev_id] = current_id
            prev_id = current_id

        for annot in self.annots:
            versionlinks: DictList = cast(Dict, annot.pop(self.keys.asserted))[LIST]
            annot[self.keys.added] = {ID: versionlinks[0][ID]}
            if versionlinks:
                last = versionlinks[-1]
                if last[ID] != graphs[-1][ID]:
                    annot[self.keys.removed] = {ID: nextindex[last[ID]]}


def make_id_key(node: Dict, id_key_spec: List[str]) -> str:
    values = []
    for key in id_key_spec:
        if key in node:
            values.append(node[key])
    return "|".join([str(v) for v in values])


def aslist(o: object) -> List:
    return o if isinstance(o, List) else [] if o is None else [o]
