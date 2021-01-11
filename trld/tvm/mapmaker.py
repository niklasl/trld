from typing import NamedTuple, Optional, Tuple, Dict, List, Set, Union, cast

from collections import OrderedDict
from ..common import sorted

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
            target = target['@context']
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

    for key, rule in target_map.items():
        rules: List[Tuple[int, Union[Dict, str]]] = sorted(as_list(rule),
                key=lambda it: cast(int, cast(Tuple, it)[0]), reverse=True)
                #key=lambda it: it[0], reverse=True)
        target_map[key] = [it for priority, it in rules] # keep all

    return target_map


def _process_class_relations(obj: Dict, vocab_index: Dict, target: Dict[str, object], target_map: Dict):
    rels: List[str] = [OWL_equivalentClass, RDFS_subClassOf]

    # TODO: rework this even more like process_property_relations
    base_rels: List[BaseRelation] = []

    id: Optional[str] = cast(Optional[str], obj.get(ID))

    id_targeted: int = 0
    if id is not None:
        id_targeted = _is_targeted(target, id)
        if id_targeted:
            base_rels.append(BaseRelation(None, id, id_targeted))

    candidates: Candidates = _collect_candidates(obj, rels)

    while candidates:
        crel, candidate = candidates.pop(0)
        if ID not in candidate:
            continue
        candidate_id: str = candidate[ID]
        candidate = cast(Dict, vocab_index.get(candidate_id, candidate))

        targeted: int = _is_targeted(target, candidate_id)
        if targeted:
            base_rels.append(BaseRelation(crel, candidate_id, targeted))
        elif crel in SYMMETRIC and id_targeted:
            assert id is not None
            _add_rule(target_map, candidate_id, id, id_targeted)
        else:
            _extend_candidates(candidates, candidate, rels)

    if id is not None and not id_targeted:
        # TODO: transpile filter comprehensions!
        #base_rels = [it for it in base_rels if it.base != id]
        filtered_base_rels: List[BaseRelation] = []
        for it in base_rels:
            if it.base != id:
                filtered_base_rels.append(it)
        base_rels = filtered_base_rels

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
    id_targeted: int = _is_targeted(target, id)
    property: Optional[str] = id if id_targeted else None
    prop_prio: int = id_targeted

    # TODO: OK to add identity-mapping?
    if property:
        _add_rule(target_map, id, property, id_targeted)

    candidates: Candidates = _collect_candidates(obj, rels)

    baseprops: List[Tuple[int, str]] = []
    if id_targeted:
        baseprops.append((id_targeted, id))

    while candidates:
        crel, candidate = candidates.pop(0)
        if ID not in candidate:
            continue
        candidate_id: str = candidate[ID]
        candidate = cast(Dict, vocab_index.get(candidate_id, candidate))

        targeted: int = _is_targeted(target, candidate_id)
        if not id_targeted and targeted:
            baseprops.append((targeted, candidate_id))
            _add_rule(target_map, id, candidate_id, targeted)
            property = candidate_id
            prop_prio = targeted
            #break
        elif crel in SYMMETRIC and not targeted and id_targeted:
            _add_rule(target_map, candidate_id, id, id_targeted)
            property = candidate_id
            prop_prio = targeted
            #break
        else:
            _extend_candidates(candidates, candidate, rels)

    if OWL_propertyChainAxiom in obj:
        prop_chain: List[Dict] = cast(List[Dict], obj[OWL_propertyChainAxiom])
        source_property: Optional[str] = None

        lst: List[Dict] = prop_chain[0][LIST]
        lead: Dict = lst[0]
        # TODO: assert(len(lst) == 2) or use rest as path to value...
        if lead:
            source_property = lead.get(ID)

        value_from: str = lst[1][ID]
        rtype: Optional[str] = None
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
            if (property is not None and property != source_property and
                not _is_targeted(target, source_property)):
                for prio, prop in baseprops:
                    rule: Dict = _rule_from(prop, None, value_from, match)
                    _add_rule(target_map, source_property, rule, prio)


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
        inverse_of_subject: bool = False
        invs: List[Dict] = cast(List[Dict], obj.get(OWL_inverseOf))

        if invs is not None:
            inverse_of_subject = any(p.get(ID) == RDF_subject for p in invs)
        else:
            supers: List[Dict] = cast(List[Dict], obj.get(RDFS_subPropertyOf))
            if supers is not None:
                inverse_of_subject = any(OWL_inverseOf in sup and
                                         any(p.get(ID) == RDF_subject
                                             for p in cast(List[Dict], sup[OWL_inverseOf]))
                                         for sup in supers)

        if inverse_of_subject:
            ranges: List[Dict] = as_list(obj[RDFS_range])
            property_from: Optional[str] = None
            value_from: Optional[str] = None
            for range in ranges:
                range_node: Optional[Dict] = vocab_index.get(range[ID])
                if range_node is None:
                    continue
                reverses: Optional[Dict] = cast(Dict, range_node.get(REVERSE))
                in_domain_of: List[Dict] = cast(List[Dict], reverses.get(RDFS_domain, [])) if reverses is not None else []
                for prop in in_domain_of:
                    propdata: Optional[Dict] = cast(Dict, vocab_index.get(prop[ID]))
                    super_props: List[Dict] = cast(List, propdata.get(RDFS_subPropertyOf, [])) if propdata is not None else []
                    if any(sprop[ID] == RDF_predicate for sprop in super_props):
                        property_from = prop[ID]
                    elif any(sprop[ID] == RDF_object for sprop in super_props):
                        value_from = prop[ID]

            id: str = obj[ID]
            if property_from and value_from and isinstance(id, str):
                _add_rule(target_map, id, _rule_from(None, property_from, value_from, None))


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


# TODO: rename to _get_target_priority
def _is_targeted(target: Dict[str, object], id: str) -> int:
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
