from typing import Optional, Dict, List, Set, Union, cast

from ..jsonld.extras.index import make_index
from ..jsonld.keys import CONTEXT, GRAPH, ID, TYPE, VOCAB
from ..jsonld.base import as_list, JsonMap


ListOrJsonMap = Union[List, Dict[str, object]]


def map_to(target_map: Dict, indata: ListOrJsonMap, drop_unmapped=False) -> ListOrJsonMap:
    result: ListOrJsonMap = {} if isinstance(indata, Dict) else []

    data_index: Dict[str, JsonMap] = make_index(as_list(indata))

    _modify(data_index, target_map, indata, result, drop_unmapped)

    return result


def _modify(data_index: Dict, target_map: Dict, ino: ListOrJsonMap, outo: Union[Dict, List], drop_unmapped: bool):
    if isinstance(ino, Dict):
        for k, v in cast(Dict[str, object], ino).items(): # TODO: cast just for transpile
            _modify_pair(data_index, target_map, k, v, outo, drop_unmapped)
    elif isinstance(ino, List):
        i: int = 0
        for v in ino:
            _modify_pair(data_index, target_map, i, v, outo, drop_unmapped)
            i += 1


def _modify_pair(data_index: Dict, target_map: Dict, k: Union[str, int], v: object, outo: Union[Dict, List], drop_unmapped: bool):
    mapo: Dict[Union[str, int], Union[List, Dict, str]] = _map(data_index, target_map, k, v, drop_unmapped)

    for mapk, mapv in mapo.items():
        outv: Union[List, Dict]
        if isinstance(mapv, List):
            outv = []
            _modify(data_index, target_map, mapv, outv, drop_unmapped)
            mapv = outv
        elif isinstance(mapv, Dict):
            outv = {}
            _modify(data_index, target_map, mapv, outv, drop_unmapped)
            mapv = outv

        if isinstance(outo, Dict):
            if mapk in outo:
                values: List = as_list(outo[mapk])
                values += as_list(mapv)
                mapv = values

            outo[mapk] = mapv
        else:
            outo.append(mapv)


def _map(data_index: Dict, target_map: Dict, key: Union[str, int], value, drop_unmapped=False) -> Dict:
    somerule: object = target_map.get(key)

    if drop_unmapped and somerule is None and isinstance(key, str) and key[0] != '@':
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
                if property_from in first:
                    property_from_object: Optional[List[Dict]] = first[property_from]
                    if property_from_object:
                        property = property_from_object[0][ID]

            if property in target_map:
                property = as_list(target_map[property])[0]

            outvalue: List[object] = []
            # TODO: if match + use base_map

            value_from: Optional[str] = rule.get('valueFrom')
            match: Optional[Dict[str, object]] = rule.get('match')
            if value_from or match:
                for v in objectvalues:
                    assert isinstance(v, Dict)

                    got_match = False
                    if match is None:
                        got_match = True
                    elif TYPE in match:
                        vo: Dict = v
                        if TYPE in v:
                            vo = v
                        elif ID in v and v[ID] in data_index:
                            v = data_index[v[ID]]

                        for t in cast(List, vo.get(TYPE, [])):
                            if t == match[TYPE]:
                                got_match = True
                                break
                    elif 'valueMatches' in match:
                        valmatch = cast(Dict[str, Dict], match['valueMatches'])
                        vmatches = False
                        for mk, mv in valmatch.items():
                            for vm in as_list(v[mk]):
                                if vm == mv:
                                    got_match = True
                                break

                    if match is None or got_match:
                        if value_from is not None:
                            vv: object = v.get(value_from)
                            if isinstance(vv, List):
                                for m in vv:
                                    outvalue.append(m)
                            else:
                                outvalue.append(vv)
                        elif 'useValue' in rule:
                            outvalue.append(rule['useValue'])
                        else:
                            outvalue.append(v)
            else:
                outvalue = value

            mappedvalue: List[object] = []
            for v in outvalue:
                if isinstance(v, str):
                    v = target_map.get(v, v)
                mappedvalue += as_list(v)

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
