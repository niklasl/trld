from typing import Optional, Dict, List, Union, cast
from .base import CONTEXT, GRAPH, ID, TYPE, VOCAB
from .base import TargetMap, RuleFrom, as_array


ListOrJsonMap = Union[List, Dict[str, object]]


def map_to(mapping: TargetMap, indata, drop_unmapped=False) -> ListOrJsonMap:
    result: ListOrJsonMap = {} if isinstance(indata, Dict) else []
    _modify(mapping, indata, result)
    return result


def _modify(mapping: TargetMap, ino: ListOrJsonMap, outo: Union[Dict, List]):
    if isinstance(ino, Dict):
        for k, v in cast(Dict[str, object], ino).items(): # TODO: cast just for transpile
            _modify_pair(mapping, k, v, outo)
    elif isinstance(ino, List):
        i: int = 0
        for v in ino:
            _modify_pair(mapping, i, v, outo)
            i += 1


def _modify_pair(mapping: TargetMap, k: Union[str, int], v: object, outo: Union[Dict, List]):
    mapo: Dict[Union[str, int], Union[List, Dict, str]] = _map(mapping.target_map, k, v)

    for mapk, mapv in mapo.items():
        outv: Union[List, Dict]
        if isinstance(mapv, List):
            outv = []
            _modify(mapping, mapv, outv)
            mapv = outv
        elif isinstance(mapv, Dict):
            outv = {}
            _modify(mapping, mapv, outv)
            mapv = outv

        if isinstance(outo, Dict):
            outo[mapk] = mapv
        else:
            outo.append(mapv)


def _map(target_map: Dict, key: Union[str, int], value, drop_unmapped=False) -> Dict:
    somerule: object = target_map.get(key)

    if drop_unmapped and isinstance(key, str) and key[0] != '@' and somerule is None:
        return {}

    if isinstance(value, List):
        remapped: List[object] = []
        for v in value:
            item: object = target_map[v] if isinstance(v, str) and  v in target_map else v
            if isinstance(item, List):
                remapped += item
            else:
                remapped.append(item)
        value = remapped

    out: Dict = {}

    rules: List = as_array(somerule)
    for rule in rules:
        if isinstance(rule, str):
            out[rule] = value
            break

        if isinstance(rule, Dict):
            rule = RuleFrom(
                    cast(Optional[str], rule.get('property')),
                    cast(Optional[str], rule.get('property_from')),
                    cast(Optional[str], rule.get('value_from')),
                    cast(Optional[Dict[str, str]], rule.get('match')),
                )

        if isinstance(rule, RuleFrom):
            objectvalues: List[Dict] = value
            # TODO: support NamedTuple unpacking in transpile!
            #property, property_from, value_from, match = rule
            property: Optional[str] = rule.property
            # TODO: use both property and property_from if present
            if rule.property_from is not None:
                first: Dict = objectvalues[0]
                property_from: List[Dict] = first[rule.property_from]
                property = property_from[0][ID]

            if property in target_map:
                property = target_map[property]

            outvalue: List[object] = []
            # TODO: if match + use base_map

            if rule.value_from is not None:
                for v in objectvalues:
                    assert isinstance(v, Dict)
                    match: Optional[Dict] = rule.match
                    if match is None or TYPE in match and any(
                            t == match[TYPE] for t in cast(List, v[TYPE])):
                        vv: object = v.get(rule.value_from)
                        if isinstance(vv, List):
                            for m in vv:
                                outvalue.append(m)
                        else:
                            outvalue.append(vv)
            else:
                outvalue = value

            #outvalue = [target_map.get(v, v) for v in outvalue]
            mappedvalue: List[object] = []
            for v in outvalue:
                mappedvalue.append(target_map.get(v, v) if isinstance(v, str) else v)
            outvalue = mappedvalue

            if property is not None and outvalue:
                out[property] = outvalue
                break

    return out if len(rules) > 0 else {key: value}
