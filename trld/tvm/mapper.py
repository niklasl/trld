from typing import Optional, Dict, List, Set, Union, cast
from ..jsonld.base import CONTEXT, GRAPH, ID, TYPE, VOCAB, as_list


ListOrJsonMap = Union[List, Dict[str, object]]


def map_to(target_map: Dict, indata, drop_unmapped=False) -> ListOrJsonMap:
    result: ListOrJsonMap = {} if isinstance(indata, Dict) else []
    _modify(target_map, indata, result, drop_unmapped)
    return result


def _modify(target_map: Dict, ino: ListOrJsonMap, outo: Union[Dict, List], drop_unmapped: bool):
    if isinstance(ino, Dict):
        for k, v in cast(Dict[str, object], ino).items(): # TODO: cast just for transpile
            _modify_pair(target_map, k, v, outo, drop_unmapped)
    elif isinstance(ino, List):
        i: int = 0
        for v in ino:
            _modify_pair(target_map, i, v, outo, drop_unmapped)
            i += 1


def _modify_pair(target_map: Dict, k: Union[str, int], v: object, outo: Union[Dict, List], drop_unmapped: bool):
    mapo: Dict[Union[str, int], Union[List, Dict, str]] = _map(target_map, k, v, drop_unmapped)

    for mapk, mapv in mapo.items():
        outv: Union[List, Dict]
        if isinstance(mapv, List):
            outv = []
            _modify(target_map, mapv, outv, drop_unmapped)
            mapv = outv
        elif isinstance(mapv, Dict):
            outv = {}
            _modify(target_map, mapv, outv, drop_unmapped)
            mapv = outv

        if isinstance(outo, Dict):
            if mapk in outo:
                values: List = as_list(outo[mapk])
                values += as_list(mapv)
                mapv = values

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

    if somerule is None:
        return {key: value}

    out: Dict = {}

    mapped_keypaths: Set[str] = set()

    for rule in as_list(somerule):
        if isinstance(rule, str):
            out[rule] = value
            break

        if isinstance(rule, Dict):
            objectvalues: List[Dict] = value

            property: Optional[str] = rule.get('property')
            property_from: Optional[str] = rule.get('propertyFrom')

            # TODO: use both property and property_from if present
            if property_from is not None:
                first: Dict = objectvalues[0]
                property_from_object: List[Dict] = first[property_from]
                property = property_from_object[0][ID]

            if property in target_map:
                property = as_list(target_map[property])[0]

            outvalue: List[object] = []
            # TODO: if match + use base_map

            value_from: Optional[str] = rule.get('valueFrom')
            if value_from is not None:
                for v in objectvalues:
                    assert isinstance(v, Dict)
                    match: Optional[Dict[str, str]] = rule.get('match')
                    if match is None or TYPE in match and any(
                            t == match[TYPE] for t in cast(List, v[TYPE])):
                        vv: object = v.get(value_from)
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
                if value_from is not None:
                    mapped_key = f'{key} {value_from}'

                    # Skipping rule if earlier rule used the same source parts
                    if mapped_key in mapped_keypaths:
                        continue

                    mapped_keypaths.add(mapped_key)

                out[property] = outvalue
                # TODO: Using all rules since they may be complementary.
                # Might need to combine those into one rule instead.
                #break

    return out
