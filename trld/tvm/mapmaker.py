from typing import NamedTuple, Optional, Tuple, Dict, List, Set, Union, cast

from collections import OrderedDict

from ..jsonld.keys import CONTEXT, GRAPH, ID, LIST, REVERSE, TYPE, VOCAB
from ..jsonld.base import as_list, JsonMap
from ..jsonld.flattening import flatten
from ..jsonld.extras.index import make_index


RDF: str = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDF_Property: str = f'{RDF}Property'
RDF_Statement: str = f'{RDF}Statement'
RDF_subject: str = f'{RDF}subject'
RDF_predicate: str = f'{RDF}predicate'
RDF_object: str = f'{RDF}object'

RDFS: str = 'http://www.w3.org/2000/01/rdf-schema#'
RDFS_Class: str = f'{RDFS}Class'
RDFS_subClassOf: str = f'{RDFS}subClassOf'
RDFS_subPropertyOf: str = f'{RDFS}subPropertyOf'
RDFS_domain: str = f'{RDFS}domain'
RDFS_range: str = f'{RDFS}range'

OWL: str = 'http://www.w3.org/2002/07/owl#'
OWL_Class: str = f'{OWL}Class'
OWL_Datatype: str = f'{OWL}Datatype'
OWL_ObjectProperty: str = f'{OWL}ObjectProperty'
OWL_DatatypeProperty: str = f'{OWL}DatatypeProperty'
OWL_Restriction: str = f'{OWL}Restriction'
OWL_equivalentClass: str = f'{OWL}equivalentClass'
OWL_equivalentProperty: str = f'{OWL}equivalentProperty'
OWL_inverseOf: str = f'{OWL}inverseOf'
OWL_propertyChainAxiom: str = f'{OWL}propertyChainAxiom'
OWL_onProperty: str = f'{OWL}onProperty'
OWL_hasValue: str = f'{OWL}hasValue'
OWL_hasSelf: str = f'{OWL}hasSelf'
OWL_someValuesFrom: str = f'{OWL}someValuesFrom'

SKOS: str = 'http://www.w3.org/2004/02/skos/core#'
SKOS_broadMatch: str = f'{SKOS}broadMatch'
SKOS_closeMatch: str = f'{SKOS}closeMatch'
SKOS_exactMatch: str = f'{SKOS}exactMatch'
SKOS_narrowMatch: str = f'{SKOS}narrowMatch'
SKOS_mappingRelation: str = f'{SKOS}mappingRelation'

SYMMETRIC: Set[str] = {
  OWL_equivalentClass,
  OWL_equivalentProperty,
  SKOS_closeMatch,
  SKOS_exactMatch,
}


Candidates = List[Tuple[Optional[str], Dict]]


class BaseRelation(NamedTuple):
    rel: Optional[str]
    base: str
    priority: int = -1


def make_target_map(vocab: object, target: object) -> Dict:
    target_dfn: Dict[str, object] = OrderedDict()
    if isinstance(target, str):
        target_dfn[VOCAB] = target
    else:
        if isinstance(target, Dict):
            target = target[CONTEXT]
        for dfn in as_list(target):
            target_dfn.update(cast(Dict, dfn))

    graph: List[JsonMap] = vocab if isinstance(vocab, List) else cast(List, cast(Dict, vocab)[GRAPH])

    graph = flatten(graph)

    vocab_index: Dict[str, JsonMap] = make_index(graph)

    target_map: Dict[str, object] = {}

    identity_set: Set[str] = set()

    for obj in graph:
        id: Optional[str] = cast(Optional[str], obj[ID]) if ID in obj else None

        _process_class_relations(obj, vocab_index, target_dfn, target_map)

        _process_property_relations(obj, vocab_index, target_dfn, target_map)

        _process_reified_forms(obj, vocab_index, target_map)

        if id and id not in target_map:
            if _get_target_priority(target_dfn, id) > 0:
                identity_set.add(id)

    for key, rule in target_map.items():
        rules: List[Tuple[int, Union[Dict, str]]] = sorted(as_list(rule),
                key=lambda it: (
                        cast(int, cast(Tuple, it)[0]),
                        cast(Tuple, it)[1].get('match') is not None
                        if isinstance(cast(Tuple, it)[1], Dict) else False
                    ),
                reverse=True)
        target_map[key] = [it for priority, it in rules] # keep all

        # Add identity mappings to keep target terms in source:
        for priority, it in rules:
            if isinstance(it, str):
                identity_set.add(it)
            break

    for it in identity_set:
        if it in target_map:
            target_map[it] = as_list(target_map[it]) + [it]
        else:
            target_map[it] = it

    return target_map


def _process_class_relations(obj: Dict, vocab_index: Dict, target: Dict[str, object], target_map: Dict):
    rels: List[str] = [OWL_equivalentClass, RDFS_subClassOf]

    # TODO: rework this even more like process_property_relations
    base_rels: List[BaseRelation] = []

    id: Optional[str] = cast(Optional[str], obj.get(ID))

    id_target_prio: int = 0
    if id is not None:
        id_target_prio = _get_target_priority(target, id)
        if id_target_prio:
            base_rels.append(BaseRelation(None, id, id_target_prio))

    candidates: Candidates = _collect_candidates(obj, rels)

    seen_candidates: Set[str] = set()

    while candidates:
        crel, candidate = candidates.pop(0)
        if ID not in candidate:
            continue

        candidate_id: str = candidate[ID]

        match: Optional[Dict] = _class_to_match_node(candidate_id, vocab_index)
        if id and crel == OWL_equivalentClass and match and TYPE not in match:
            if 'valueMatches' in match:
                source_id: str = match['property']
                rule = {
                    'property': TYPE,
                    'useValue': id,
                    'match': match
                }
                _add_rule(target_map, source_id, rule, id_target_prio)
                continue

        candidate = cast(Dict, vocab_index.get(candidate_id, candidate))

        target_prio: int = _get_target_priority(target, candidate_id)
        if target_prio:
            base_rels.append(BaseRelation(crel, candidate_id, target_prio))
        elif crel in SYMMETRIC and id_target_prio:
            assert id is not None
            _add_rule(target_map, candidate_id, id, id_target_prio)
        elif candidate_id not in seen_candidates:
            _extend_candidates(candidates, candidate, rels)

        seen_candidates.add(candidate_id)

    if id is not None and not id_target_prio:
        base_rels = [it for it in base_rels if it.base != id]

        if len(base_rels) > 0:
            base_classes: List[str] = []
            for baserel in base_rels:
                class_dfn: Optional[Dict] = cast(Optional[Dict], vocab_index.get(baserel.base))
                if class_dfn is None:
                    class_dfn = {ID: baserel.base}
                base_classes.append(cast(str, class_dfn[ID]))
                break
                #if baserel.rel == OWL_equivalentClass:
                #    _add_rule(target_map, baserel.base, id)
            _add_rule(target_map, id, base_classes)


def _process_property_relations(obj: Dict, vocab_index: Dict, target: Dict[str, object], target_map: Dict):
    rels: List[str] = [OWL_equivalentProperty, RDFS_subPropertyOf]

    if ID not in obj: # TODO: OK?
        return

    id: str = obj[ID]
    id_target_prio: int = _get_target_priority(target, id)
    property: Optional[str] = id if id_target_prio else None
    prop_prio: int = id_target_prio

    # TODO: OK to add identity-mapping?
    if property:
        _add_rule(target_map, id, property, id_target_prio)

    candidates: Candidates = _collect_candidates(obj, rels)

    baseprops: List[Tuple[int, str]] = []
    if id_target_prio:
        baseprops.append((id_target_prio, id))

    candidate_prop: Optional[str] = None

    seen_candidates: Set[str] = set()

    while candidates:
        crel, candidate = candidates.pop(0)
        if ID not in candidate:
            continue

        candidate_id: str = candidate[ID]
        candidate = cast(Dict, vocab_index.get(candidate_id, candidate))

        target_prio: int = _get_target_priority(target, candidate_id)
        if not id_target_prio and target_prio:
            baseprops.append((target_prio, candidate_id))
            _add_rule(target_map, id, candidate_id, target_prio)
            candidate_prop = candidate_id
            prop_prio = target_prio
            #break
        elif crel in SYMMETRIC and not target_prio and id_target_prio:
            _add_rule(target_map, candidate_id, id, id_target_prio)
            candidate_prop = candidate_id
            prop_prio = target_prio
            #break
        elif candidate_id not in seen_candidates:
            _extend_candidates(candidates, candidate, rels)

        seen_candidates.add(candidate_id)

    _process_property_chain(obj, vocab_index, target, target_map, candidate_prop, baseprops)


def _process_property_chain(
    obj: Dict,
    vocab_index: Dict,
    target: Dict[str, object],
    target_map: Dict,
    candidate_prop: Optional[str],
    baseprops: List[Tuple[int, str]]
) -> bool:
    if OWL_propertyChainAxiom not in obj:
        return False

    prop_chain_node: List[Dict] = cast(List[Dict], obj[OWL_propertyChainAxiom])
    source_property: Optional[str] = None

    prop_chain: List[Dict] = prop_chain_node[0][LIST]
    if len(prop_chain) == 0:
        return False

    first: Dict = prop_chain[0]
    if len(prop_chain) <= 1:
        return False

    if ID in first:
        id_key: str = first[ID]
        if id_key in vocab_index:
            first = vocab_index[id_key]

    second_id: str = prop_chain[1][ID]

    source_property = first.get(ID)

    rtype: Optional[str] = None
    value_from: Optional[str] = None
    property_from: Optional[str] = None

    rolified: Optional[JsonMap] = None

    # TODO: These are very brittle heuristics; for starters, any chain part may
    # be a rolified.
    step_desc: Optional[Dict] = vocab_index.get(second_id)
    if step_desc is not None and REVERSE in step_desc:
        reverses: Dict[str, List] = step_desc[REVERSE]
        if OWL_onProperty in reverses:
            for propref in cast(List[Dict], reverses[OWL_onProperty]):
                assert isinstance(propref, Dict)
                if ID in propref and propref[ID] in vocab_index:
                    onprop: Dict = vocab_index[propref[ID]]
                    if OWL_hasSelf in onprop:
                        rolified = onprop
                        break

    if rolified is not None:
        if OWL_equivalentClass in rolified:
            for equiv in cast(List[Dict], rolified[OWL_equivalentClass]):  # or RDFS_subClassOf...
                rtype = equiv[ID]
                break
        elif REVERSE in rolified:
            reverses = cast(Dict, rolified[REVERSE])
            if OWL_equivalentClass in reverses:
                for equiv in cast(List[Dict], reverses[OWL_equivalentClass]):  # or RDFS_subClassOf...
                    rtype = equiv[ID]
                    break

        if rtype is not None:
            if source_property and not source_property.startswith('_:'):
                property_from = source_property

            # TODO: Should get from last regular (non-rolified) property component,
            # and if followed by rolified, use to match value type.
            if len(prop_chain) == 3:
                value_property: Dict = prop_chain[2]
                value_prop_id: str = value_property[ID]
                if not value_prop_id.startswith('_:'):
                    value_from = value_prop_id

    # TODO: Deprecate this blank subPropertyOf pattern in favour of the rolified form.
    # TODO: don't rely solely on anonymous subPropertyOf
    elif source_property is None or source_property.startswith('_:'):
        try:
            ranges: List[Dict] = first[RDFS_range]
            rtype = ranges[0][ID]
        except:
            pass
        superprops: List[Dict] = first[RDFS_subPropertyOf]
        source_property = superprops[0][ID]
        value_from = second_id
    else:
        value_from = second_id

    match: Optional[Dict] = _class_to_match_node(rtype, vocab_index)

    if source_property and (value_from or property_from):
        if source_property != candidate_prop:
            for prio, baseprop in baseprops:
                rule: Dict = _rule_from(baseprop, property_from, value_from, match)
                if _get_target_priority(target, source_property) < prio:
                    # TODO: only if rule is "explicit enough" (has a 'propertyFrom' or 'match' term)?
                    _add_rule(target_map, source_property, rule, prio)

            return True

    # TODO: also check vocab_index[source_property][REVERSE][RDFS_subPropertyOf]

    return False


def _collect_candidates(obj: Dict, rels: List[str]) -> Candidates:
    candidates: Candidates = []
    for rel in rels:
        refs: object = obj.get(rel)
        if isinstance(refs, List):
            candidates += cast(Candidates, [(rel, ref) for ref in refs])
    return candidates


def _extend_candidates(candidates: Candidates, candidate: Dict, rels: List[str]):
    for rel in rels:
        superrefs: Optional[List[Dict]] = cast(Optional[List[Dict]], candidate.get(rel))
        if superrefs is not None:
            for sup in superrefs:
                if ID in sup:
                    candidates.append((None, sup))


def _class_to_match_node(rtype: Optional[str], vocab_index: Dict[str, JsonMap]) -> Optional[Dict]:
    if rtype is None:
        return None

    if rtype.startswith('_:') and rtype in vocab_index:
        restr = vocab_index[rtype]

        if isinstance(restr, Dict):
            if OWL_onProperty in restr:
                onprop = cast(List[Dict], restr[OWL_onProperty])
                match = {'property': onprop[0].get(ID)}

                valmatch: Union[str, Dict, None] = None
                match_kind: Optional[str] = None
                if OWL_someValuesFrom in restr:
                    somevaluesfrom = cast(List[Dict], restr[OWL_someValuesFrom])
                    for somefrom in somevaluesfrom:
                        assert isinstance(somefrom, Dict)
                        if ID in somefrom:
                            match_kind = 'valueMatches'
                            valmatch = _class_to_match_node(
                                cast(str, somefrom[ID]), vocab_index
                            )
                            break
                elif OWL_hasValue in restr:
                    hasvalue = cast(List[Dict], restr[OWL_hasValue])
                    for hasval in hasvalue:
                        match_kind = 'valueMatches'
                        valmatch = hasval
                        break

                if match_kind:
                    match[match_kind] = valmatch

                return match

    return {TYPE: rtype}


def _process_reified_forms(obj: Dict, vocab_index: Dict, target_map: Dict[str, object]):
    prop = _trace_inverse_of_subject(obj, vocab_index)

    if prop is not None:
        ranges: List[Dict] = []

        prop_id: str = obj[ID]

        if RDFS_range in obj:
            ranges += as_list(obj[RDFS_range])
        if prop is not obj and RDFS_range in prop:
            ranges += as_list(prop[RDFS_range])

        property_from: Optional[str] = None
        value_from: Optional[str] = None

        for range in ranges:
            range_node: Optional[Dict] = vocab_index.get(range[ID])
            if range_node is None:
                continue
            reverses: Optional[Dict] = cast(Dict, range_node.get(REVERSE))
            in_domain_of: List[Dict] = cast(List[Dict], reverses.get(RDFS_domain, [])) if reverses is not None else []
            for domain_prop in in_domain_of:
                if leads_to(domain_prop, vocab_index, RDFS_subPropertyOf, RDF_predicate):
                    property_from = domain_prop[ID]
                elif leads_to(domain_prop, vocab_index, RDFS_subPropertyOf, RDF_object):
                    value_from = domain_prop[ID]

        if property_from and value_from and isinstance(prop_id, str):
            ## TODO: needs target prio at runtime from property_from...
            target_prio: int = 4096  # _get_target_priority(target, candidate_id)
            rule = _rule_from(None, property_from, value_from, None)
            _add_rule(target_map, prop_id, rule, target_prio)


def _trace_inverse_of_subject(obj: Dict, vocab_index: Dict) -> Optional[Dict]:
    invs = cast(Optional[List[Dict]], obj.get(OWL_inverseOf))

    if invs is not None:
        for p in invs:
            if leads_to(p, vocab_index, RDFS_subPropertyOf, RDF_subject):
                return p

    supers = cast(Optional[List[Dict]], obj.get(RDFS_subPropertyOf))
    if supers is None:
        return None

    for supref in supers:
        sup = cast(Dict, vocab_index.get(supref[ID], supref) if ID in supref else supref)
        if _trace_inverse_of_subject(sup, vocab_index):
            return sup

    return None


def _add_rule(target_map: Dict[str, object],
              source_id: str,
              rule: Union[str, List, Dict],
              priority=0):
    if source_id == rule:
        return

    rule_priority: object = [(priority, it) for it in rule] if isinstance(rule, List) else [(priority, rule)]

    rules: List = cast(List, target_map.get(source_id))
    if rules is None:
        target_map[source_id] = rule_priority
    else:
        if not isinstance(rules, List):
            rules = [rules]
            target_map[source_id] = rules
        if isinstance(rule_priority, List):
            rules += rule_priority
        else:
            rules.append(rule_priority)


def _rule_from(property: Optional[str],
               property_from: Optional[str],
               value_from: Optional[str],
               match: Optional[Dict[str, str]]) -> Dict:
    return {
        'property': property,
        'propertyFrom': property_from,
        'valueFrom': value_from,
        'match': match
    }


def _get_target_priority(target: Dict[str, object], id: str) -> int:
    top_prio: int = len(target)

    prio: int = top_prio * 3
    for v in target.values():
        if id == v:
            return prio
        prio -= 1

    vocab: Optional[object] = target.get(VOCAB)
    if isinstance(vocab, str) and id.startswith(vocab):
        return top_prio * 2

    prio = top_prio
    for v in target.values():
        if isinstance(v, str) and id.startswith(cast(str, v)):
            return prio
        prio -= 1

    return 0


def leads_to(s: Dict, vocab_index: Dict, rel: str, o) -> bool:
    if s.get(ID) == o:
        return True

    data: Optional[Dict] = cast(Dict, vocab_index.get(s[ID], s) if ID in s else s)
    xs: List[Dict] = cast(List, data.get(rel, [])) if data is not None else []

    for x in xs:
        if x.get(ID) == o or leads_to(x, vocab_index, rel, o):
            return True

    return False
