from typing import Optional, Tuple, Dict, List, Union, cast
from ..base import ID, GRAPH, REVERSE, JsonMap, as_list


def make_index(graph: List[JsonMap], add_reverses=True) -> Dict[str, JsonMap]:
    index: Dict[str, JsonMap] = {}

    for item in graph:
        id: Optional[str] = cast(Optional[str], item.get(ID))
        if isinstance(id, str):
            index[id] = item

    if add_reverses:
        _index_reverses(index)

    return index


def _index_reverses(index: Dict[str, JsonMap]):
    for item in index.values():
        if ID not in item:
            continue
        for link in item.keys():
            refs: List = as_list(item[link])
            for ref in refs:
                if not isinstance(ref, Dict):
                    continue
                linked: object = index.get(cast(str, ref.get(ID)))
                if not isinstance(linked, Dict):
                    continue
                revmap: Dict = linked.setdefault(REVERSE, {})
                revs: List[Dict] = revmap.setdefault(link, [])
                if not any(rev[ID] == item[ID] for rev in revs):
                    revs.append({ID: item[ID]})
