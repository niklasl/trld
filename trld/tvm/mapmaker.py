from typing import NamedTuple, Optional, Tuple, Dict, List, Set, Union, cast

from collections import OrderedDict

from ..jsonld.base import CONTEXT, GRAPH, ID, LIST, REVERSE, TYPE, VOCAB, as_list, JsonMap
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
OWL_allValuesFrom: str = f'{OWL}allValuesFrom'

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

    vocab_index: Dict[str, JsonMap] = make_index(graph)

    target_map: Dict[str, object] = {}

    for obj in graph:
        id: Optional[str] = cast(Optional[str], obj[ID])

        _process_class_relations(obj, vocab_index, target_dfn, target_map)

        _process_property_relations(obj, vocab_index, target_dfn, target_map)

        _process_reified_forms(obj, vocab_index, target_map)

    identity_map: Dict[str, str] = {}

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
                identity_map[it] = it
            break

    target_map.update(identity_map)

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
        else:
            _extend_candidates(candidates, candidate, rels)

    _process_property_chain(obj, target, target_map, candidate_prop, baseprops)


def _process_property_chain(obj: Dict,
                             target: Dict[str, object],
                             target_map: Dict,
                             candidate_prop: Optional[str],
                             baseprops: List[Tuple[int, str]]) -> bool:
    if OWL_propertyChainAxiom not in obj:
        return False

    prop_chain: List[Dict] = cast(List[Dict], obj[OWL_propertyChainAxiom])
    source_property: Optional[str] = None

    lst: List[Dict] = prop_chain[0][LIST]
    lead: Dict = lst[0]
    # TODO: assert(len(lst) == 2) or use rest as path to value...
    if lead:
        source_property = lead.get(ID)

    value_from: str = lst[1][ID]
    rtype: Optional[str] = None

    # TODO: don't rely solely on anonymous subPropertyOf
    if source_property is None or source_property.startswith('_:'):
        try:
            ranges: List[Dict] = lead[RDFS_range]
            rtype = ranges[0][ID]
        except:
            pass
        superprops: List[Dict] = lead[RDFS_subPropertyOf]
        source_property = superprops[0][ID]

    match: Optional[Dict] = {TYPE: rtype} if rtype else None
    # TODO: also match OWL_Restriction using OWL_onProperty PLUS
    # OWL_hasValue OR OWL_allValuesFrom

    if source_property:
        if (source_property != candidate_prop and
            not _get_target_priority(target, source_property)):
            for prio, baseprop in baseprops:
                rule: Dict = _rule_from(baseprop, None, value_from, match)
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
            _add_rule(target_map, prop_id, _rule_from(None, property_from, value_from, None))


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

    if VOCAB in target and id.startswith(cast(str, target[VOCAB])):
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
