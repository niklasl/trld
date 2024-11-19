from typing import Dict, Iterator, List, Optional, Set, Tuple, Union, cast

from ..jsonld.keys import CONTEXT, GRAPH, ID, LIST, TYPE, VOCAB


def as_list(obj: object) -> List:
    return [] if obj is None else obj if isinstance(obj, List) else [obj]


def one_or_more(items: List[object]) -> Union[List[object], object]:
    return items[0] if len(items) == 1 else items


# mapmaker

CTX = {
    CONTEXT: {
        "owl": "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
    }
}
BROADER = ['rdfs:subClassOf', 'skos:broader', 'skos:broadMatch', 'owl:intersectionOf']
NARROWER = ['skos:narrower', 'skos:narrowMatch']


def make_fold_target_map(tbox: Dict[str, Dict], target: Dict) -> Tuple[Dict, Dict]:
    matchpattern_orderedprop_tree: Dict[str, Dict] = {}

    transitivebases: Dict[str, Set[str]] = {}

    target_vocab = target[VOCAB]

    for obj in tbox[GRAPH]:
        target_classes: List[str] = []
        for o in cast(List[Dict], [obj] + as_list(obj.get('owl:equivalentClass', []))):
            if ID in o and o[ID].startswith(target_vocab):
                target_classes.append(o[ID])

        current_tree: Dict = matchpattern_orderedprop_tree

        rule: Optional[Dict] = None
        intersections: Optional[Dict] = obj.get('owl:intersectionOf')

        if intersections is None and ID in obj and obj.get(TYPE) == 'owl:Restriction':
            intersections = {LIST: [obj]}

        if isinstance(intersections, Dict) and LIST in intersections:
            for o in intersections[LIST]:
                if 'owl:onProperty' in o:
                    prop = o['owl:onProperty'][ID]
                    by_pred: Dict = current_tree.setdefault('matchByPredicate', {})
                    valuematch: Dict = by_pred.setdefault(prop, {})
                    if 'owl:hasValue' not in o:
                        continue
                    value = o['owl:hasValue']
                    rule = {}
                    if ID in value:
                        by_id: Dict = valuematch.setdefault('byId', {})
                        by_id[value[ID]] = rule

                    current_tree = rule
                elif ID in o:
                    by_type: Dict = current_tree.setdefault('matchByType', {})
                    subtree: Dict = by_type.setdefault(o[ID], {})
                    current_tree = subtree

            if rule is not None and target_classes:
                rule['targetClass'] = (
                    target_classes[0] if len(target_classes) == 1 else target_classes
                )

        if ID in obj:
            for key in BROADER:
                if key in obj:
                    value = obj[key]
                    if isinstance(value, Dict) and LIST in value:
                        value = value[LIST]
                    for supclass in as_list(value):
                        if ID in supclass:
                            bases = transitivebases.setdefault(obj[ID], set())
                            bases.add(supclass[ID])

            for key in NARROWER:
                if key in obj:
                    value = obj[key]
                    if isinstance(value, Dict) and LIST in value:
                        value = value[LIST]
                    for subclass in as_list(value):
                        if ID in subclass:
                            bases = transitivebases.setdefault(subclass[ID], set())
                            bases.add(obj[ID])

    return matchpattern_orderedprop_tree, transitivebases


def make_tbox_equivalency_map(tbox: Dict[str, Dict]) -> Dict[str, Dict]:
    tbox_map: Dict[str, Dict] = {}
    for term in tbox[GRAPH]:
        if ID in term:
            term_id = cast(str, term[ID])
            if term_id in tbox_map:
                given: Dict = tbox_map[term_id]
                term.update(given)
            tbox_map[term_id] = term
        elif 'owl:equivalentClass' in term:
            bnode_id = f'_:b{id(term)}'
            term[ID] = bnode_id
            tbox_map[bnode_id] = term
            equiv: Dict = term['owl:equivalentClass']
            if ID in equiv:
                dfn: Dict = tbox_map.setdefault(equiv[ID], {ID: equiv[ID]})
                equivs = dfn.setdefault('owl:equivalentClass', [])
                equivs.append({ID: bnode_id})

    return tbox_map


# mapper


def match_struct_type(
    matchpattern_orderedprop_tree: Dict[str, Dict],
    transitivebases: Dict[str, Set[str]],
    obj: Dict[str, object],
) -> List[Tuple[str, List[Tuple[str, object]]]]:
    current_tree: Dict[str, Dict] = matchpattern_orderedprop_tree
    if TYPE not in obj:
        return []

    typetree: Optional[Dict[str, Dict]] = None
    for objtype in as_list(obj[TYPE]):
        typetree = cast(
            Dict[str, Dict], matchpattern_orderedprop_tree['matchByType'].get(objtype)
        )
        if typetree:
            break

    if typetree is None:
        return []

    results: List = []

    matched_predicate_values: List[Tuple[str, object]] = []

    # TODO: recursive, match, ordered lexically by prop...
    proptree: Optional[Dict] = typetree

    while proptree:
        # TODO: incomplete rule?
        if 'matchByPredicate' not in proptree:
            return results

        all_failed = True

        for targetrule, prop_value in _find_matches_by_predicate(
            transitivebases, proptree, obj
        ):
            all_failed = False

            # matches
            matched_predicate_values.append(prop_value)

            # leaf match
            if 'targetClass' in targetrule:
                foldedtype: str = targetrule['targetClass']
                results.append((foldedtype, matched_predicate_values))
                proptree = None
            else:
                proptree = targetrule

        if all_failed:
            return results

    return results


def _find_matches_by_predicate(
    transitivebases: Dict[str, Set[str]], proptree: Dict, obj: Dict
) -> Iterator[Tuple[Dict, Tuple[str, object]]]:
    if 'matchByPredicate' not in proptree:
        return

    by_predicate_map: Dict[str, Dict] = proptree['matchByPredicate']
    for prop, by_id_node in by_predicate_map.items():
        # TODO: incomplete rule?
        if 'byId' not in by_id_node:
            continue

        value: Optional[object] = obj.get(prop)
        if not value:
            continue

        targetmatch = _find_rule_by_id(transitivebases, by_id_node['byId'], value)

        if targetmatch is None:
            continue

        matchid: str
        targetrule: Dict
        matchid, targetrule = targetmatch

        yield targetrule, (prop, {ID: matchid})


def _find_rule_by_id(
    transitivebases: Dict[str, Set[str]], by_id: Dict[str, Dict], value: object
) -> Optional[Tuple[str, Dict]]:
    for matchid, candidate_rule in by_id.items():
        for vo in as_list(value):
            if isinstance(vo, Dict) and ID in vo:
                if matches(transitivebases, vo[ID], matchid):
                    return matchid, candidate_rule

    return None


def matches(
    transitivebases: Dict[str, Set[str]], checkedtypeid: str, soughttypeid: str
) -> bool:
    if checkedtypeid == soughttypeid:
        return True
    if (
        checkedtypeid in transitivebases
        and soughttypeid in transitivebases[checkedtypeid]
    ):
        return True
    else:
        return False


def fold_type(
    matchpattern_orderedprop_tree: Dict,
    transitivebases: Dict[str, Set[str]],
    target_vocab: str,
    obj: Dict,
    drop_matched=False,
) -> Dict:
    results = match_struct_type(matchpattern_orderedprop_tree, transitivebases, obj)

    if TYPE not in obj:
        return obj

    objtypes: List[str] = as_list(obj[TYPE])

    out_obj = obj.copy()
    new_types = []

    for matched in results:
        newtype: str = matched[0]
        matched_predicate_values: List[Tuple[str, object]] = matched[1]
        # newtype, matched_predicate_values = matched
        keeptypes = [
            t
            for t in objtypes
            if t.startswith(target_vocab) and not matches(transitivebases, newtype, t)
        ]
        new_types += keeptypes + as_list(newtype)

        if drop_matched:
            for objtype in objtypes:
                if objtype not in transitivebases:
                    continue
                for basetype in transitivebases[objtype]:
                    for targetrule, prop_value in _find_matches_by_predicate(
                        transitivebases, matchpattern_orderedprop_tree, obj
                    ):
                        matched_predicate_values.append(prop_value)

            for k, v in matched_predicate_values:
                if k not in out_obj:
                    continue

                v_ids = set([x[ID] for x in as_list(v) if ID in x])
                out_vs = [
                    x for x in as_list(out_obj[k]) if ID not in x or x[ID] not in v_ids
                ]
                if not out_vs:
                    out_obj.pop(k)
                else:
                    out_obj[k] = one_or_more(out_vs)

    if new_types:
        # FIXME: reduce to most specific
        out_obj[TYPE] = one_or_more(list(set(new_types)))
        return out_obj

    return obj


def get_intersections(
    tbox_map: Dict, typedfn: Dict, visited: Optional[Set[str]] = None
) -> Iterator[Dict]:
    if visited is None:
        visited = set()

    if ID in typedfn:
        type_id = cast(str, typedfn[ID])
        if type_id in visited:
            return
        visited.add(type_id)

        yield typedfn

    if 'owl:onProperty' in typedfn:
        yield typedfn

    if 'owl:intersectionOf' in typedfn:
        for item in typedfn['owl:intersectionOf'][LIST]:
            item = _get_mapped(tbox_map, item)
            yield from get_intersections(tbox_map, item, visited)

    if 'owl:equivalentClass' in typedfn:
        for equiv in as_list(typedfn['owl:equivalentClass']):
            equiv = _get_mapped(tbox_map, equiv)
            yield from get_intersections(tbox_map, equiv, visited)

    if 'rdfs:subClassOf' in typedfn:
        for baseclass in as_list(typedfn['rdfs:subClassOf']):
            baseclass = _get_mapped(tbox_map, baseclass)
            yield from get_intersections(tbox_map, baseclass, visited)


def _get_mapped(obj_map: Dict[str, Dict], obj: Dict) -> Dict:
    if ID in obj:
        obj_id = cast(str, obj[ID])
        if obj_id in obj_map:
            obj = obj_map[obj_id]

    return obj


def unfold_type(
    tbox_map: Dict[str, Dict],
    transitivebases: Dict[str, Set[str]],
    target_vocab: str,
    obj: Dict,
    drop_matched=False,
) -> Dict:
    out_obj = obj.copy()
    for objtype in as_list(obj[TYPE]):
        typedfn = tbox_map.get(objtype)
        if not isinstance(typedfn, Dict):
            continue

        # TODO: precompute target type + intersection set (it + baseclasses)
        for intersect in get_intersections(tbox_map, typedfn):
            if 'owl:onProperty' in intersect and 'owl:hasValue' in intersect:
                prop = intersect['owl:onProperty'][ID]
                value = intersect['owl:hasValue']
                if prop in out_obj:
                    values = as_list(out_obj[prop])
                    if not any(x == value for x in values):
                        values.append(value)
                    out_obj[prop] = one_or_more(values)
                else:
                    out_obj[prop] = value
            elif ID in intersect:
                it_id = intersect[ID]
                if it_id != objtype and not it_id.startswith('_:'):
                    out_obj[TYPE] = it_id

    return out_obj
