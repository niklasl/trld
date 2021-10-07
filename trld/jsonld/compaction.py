from typing import Optional, Dict, List, Set, Union, cast
from ..common import warning
from .base import *
from .context import Context, Term, InvalidNestValueError
from .invcontext import get_inverse_context


PRESERVE: str = '@preserve'


class IRIConfusedWithPrefixError(JsonLdError):
    pass


def compact(context: object, doc_data: JsonObject,
        base_iri: Optional[str] = None,
        compact_arrays = True,
        ordered = False) -> JsonObject:
    active_context: Context
    if isinstance(context, Context):
        active_context = context
    else:
        context_url: Optional[str] = context if isinstance(context, str) else None
        if isinstance(context, Dict):
            context = context.get(CONTEXT)
        active_context = Context(base_iri).get_context(cast(object, context), context_url)

    result: JsonObject = compaction(active_context, None, doc_data, compact_arrays, ordered)
    if isinstance(result, List):
        if len(result) == 0:
            result = {}
        else:
            result = {iri_compaction(active_context, GRAPH): result}
    return result


def compaction(
        active_context: Context,
        active_property: Optional[str],
        element: JsonObject,
        compact_arrays = False,
        ordered = False
        ) -> JsonObject:
    # 1)
    type_scoped_context: Context = active_context
    result: Union[Dict, List]
    result_map: JsonMap
    result_list: JsonList

    active_term: Optional[Term] = active_context.terms.get(active_property)
    active_container_mapping: List = active_term.container if active_term else []
    compacted_item: JsonObject

    # 2)
    if element is None or is_scalar(element):
        return element

    # 3)
    if isinstance(element, List):
        # 3.1)
        result = result_list = []
        # 3.2)
        for item in element:
            # 3.2.1)
            compacted_item = compaction(
                    active_context, active_property, item, compact_arrays, ordered)
            # 3.2.2)
            if compacted_item is not None:
                result.append(compacted_item)
        # 3.3)
        if (len(result_list) == 0 or len(result_list) > 1
                or not compact_arrays or active_property in {GRAPH, SET}
                or LIST in active_container_mapping or SET in active_container_mapping):
            return result_list
        # 3.4)
        else:
            return result_list[0]

    # 4)
    assert isinstance(element, Dict)

    # 5)
    if not active_context._propagate and active_context.previous_context:
        if VALUE not in element:
            if ID not in element or len(element) != 1:
                active_context = active_context.previous_context

    # 6)
    if active_term and active_term.has_local_context:
        active_context = active_term.get_local_context(active_context)

    # 7)
    if VALUE in element or ID in element:
        value_result: JsonObject = value_compaction(active_context, active_term, element)
        if is_scalar(value_result) or active_term and (active_term.type_mapping == JSON):
            return value_result

    # 8)
    if isinstance(element, Dict) and LIST in element and LIST in active_container_mapping:
        return compaction(active_context, active_property, element[LIST], compact_arrays, ordered)

    # 9)
    inside_reverse: bool = active_property == REVERSE

    # 10)
    result = result_map = {}

    # 11)
    # TODO: [5f594ac8] spec improvement; keep this and reuse in step 12.2)
    compacted_types: List[str] = []
    current_active_context: Context = active_context
    if TYPE in element:
        for expanded_type in as_list(element[TYPE]):
            compacted_types.append(
                    iri_compaction(type_scoped_context, cast(str, expanded_type)))
        for ctype in sorted(compacted_types):
            # 11.1)
            typeterm: Optional[Term] = type_scoped_context.terms.get(ctype)
            if typeterm and typeterm.has_local_context:
                active_context = typeterm.get_local_context(current_active_context, False)

    # 12)
    for expanded_property, expanded_value in cast(Dict[str, JsonObject], element).items():
        compacted_value: Optional[str] = None
        # TODO: [5f594ad1] spec improvement; do this once
        alias: str = iri_compaction(active_context, expanded_property, expanded_value)
        alias_term: Optional[Term] = active_context.terms.get(alias)
        alias_container_mapping: List = alias_term.container if alias_term else []
        as_array: bool

        # 12.1)
        if expanded_property == ID:
            # 12.1.1)
            if isinstance(expanded_value, str):
                compacted_value = shorten_iri(active_context, expanded_value)
            # 12.1.2)
            # (see 5f594ad1)
            # 12.1.3)
            result_map[alias] = cast(JsonObject, compacted_value)
            continue

        # 12.2)
        elif expanded_property == TYPE:
            # 12.2.1)
            # TODO: spec improvement (see 5f594ac8)
            # 12.2.2)
                # 12.2.2.1)
                # 12.2.2.2)
                    # 12.2.2.2.1)
                    # 12.2.2.2.2)
            # 12.2.3)
            # (see 5f594ad1)
            # 12.2.4)
            as_array = (active_context._processing_mode == JSONLD11
                        and SET in alias_container_mapping) or not compact_arrays
            # 12.2.5)
            # TODO: spec problem; says to pick first if isinstance(expanded_value, str),
            # but len is 1 is what works...
            add_value(result_map, alias,
                    compacted_types[0] if len(compacted_types) == 1 else compacted_types,
                    as_array)
            # 12.2.6)
            continue

        # 12.3)
        elif expanded_property == REVERSE:
            # 12.3.1)
            compacted_map: JsonMap = cast(JsonMap, compaction(
                    active_context, REVERSE, expanded_value, compact_arrays, ordered))
            # 12.3.2)
            for prop in cast(List[str], list(compacted_map.keys())):
                value: JsonObject = compacted_map[prop]
                prop_term: Optional[Term] = active_context.terms.get(prop)
                # 12.3.2.1)
                if prop_term and prop_term.is_reverse_property:
                    # 12.3.2.1.1)
                    as_array = (active_context._processing_mode == JSONLD11
                                and SET in prop_term.container) or not compact_arrays
                    # 12.3.2.1.2)
                    add_value(result_map, prop, value, as_array)
                    # 12.3.2.1.3)
                    compacted_map.pop(prop)
            # 12.3.3)
            if len(compacted_map) > 0:
                # 12.3.3.1)
                rev_alias: str = iri_compaction(active_context, REVERSE)
                # 12.3.3.2)
                result_map[rev_alias] = compacted_map
            # 12.3.4)
            continue

        # 12.4)
        elif expanded_property == PRESERVE:
            # 12.4.1)
            # 12.4.2)
            if expanded_value != []:
                result_map[PRESERVE] = compaction(active_context, active_property, expanded_value,
                        compact_arrays, ordered)

        # 12.5)
        elif expanded_property == INDEX and INDEX in active_container_mapping:
            continue

        # 12.6)
        elif expanded_property in {DIRECTION, INDEX, LANGUAGE, VALUE}:
            # 12.6.1)
            # 12.6.2)
            result_map[alias] = expanded_value
            continue

        item_active_property: str
        item_active_term: Optional[Term]
        nest_result: JsonMap
        # 12.7)
        if expanded_value == []:
            # 12.7.1)
            item_active_property = iri_compaction(active_context, expanded_property, expanded_value, vocab=True, reverse=inside_reverse)
            item_active_term = active_context.terms.get(item_active_property)
            # 12.7.2 - 12.7.3)
            nest_result = _get_nest_result(active_context, item_active_term, result_map)
            # 12.7.4)
            add_value_as_list(nest_result, item_active_property, [])

        # 12.8)
        expanded_value = as_list(expanded_value)
        assert isinstance(expanded_value, List)

        for expanded_item in expanded_value:
            # 12.8.1)
            item_active_property = iri_compaction(active_context, expanded_property, expanded_item, vocab=True, reverse=inside_reverse)
            item_active_term = active_context.terms.get(item_active_property)
            # 12.8.2 - 12.8.3)
            nest_result = _get_nest_result(active_context, item_active_term, result_map)
            # 12.8.4)
            container: List[str]
            if item_active_term and item_active_term.container is not None:
                container = item_active_term.container
            else:
                container = []
            # 12.8.5)
            as_array = (SET in container
                        or item_active_property in {GRAPH, LIST}
                       ) or not compact_arrays
            # 12.8.6)
            item_to_compact: JsonObject = expanded_item
            item_is_list_object: bool = False
            item_is_graph_object: bool = False
            if isinstance(expanded_item, Dict):
                if LIST in expanded_item:
                    item_to_compact = expanded_item[LIST]
                    item_is_list_object = True
                if is_graph_object(expanded_item):
                    item_to_compact = expanded_item[GRAPH]
                    item_is_graph_object = True

            compacted_item = compaction(
                    active_context, item_active_property, item_to_compact, compact_arrays, ordered)

            # 12.8.7)
            if item_is_list_object:
                assert isinstance(expanded_item, Dict) # TODO: follows indirectly from if test
                #assert isinstance(compacted_item, Dict)
                # 12.8.7.1)
                if not isinstance(compacted_item, List):
                    compacted_item = [compacted_item]
                # 12.8.7.2)
                if LIST not in container:
                    # 12.8.7.2.1)
                    compacted_item = {iri_compaction(active_context, LIST): compacted_item}
                    assert isinstance(compacted_item, Dict) # TODO: redundant, for transpile
                    # 12.8.7.2.2)
                    if INDEX in expanded_item:
                        compacted_item[iri_compaction(active_context, INDEX)] = expanded_item[INDEX]
                    # 12.8.7.2.3)
                    add_value(nest_result, item_active_property, compacted_item, as_array)
                    # TODO: spec problem; does not continue here (thus adding twice!)
                    continue
                # 12.8.7.3)
                elif active_property:
                    nest_result[active_property] = compacted_item

            # 12.8.8)
            map_object: JsonMap
            map_key: Optional[str] = None
            if item_is_graph_object:
                assert isinstance(expanded_item, Dict) # TODO: follows indirectly from if test
                # 12.8.8.1)
                if GRAPH in container and ID in container:
                    # 12.8.8.1.1)
                    map_object = cast(JsonMap, nest_result.setdefault(item_active_property, {}))
                    # 12.8.8.1.2)
                    id_or_none: str = cast(str, expanded_item[ID]) if ID in expanded_item else NONE
                    map_key = iri_compaction(active_context, id_or_none, None, vocab=ID not in expanded_item)
                    # 12.8.8.1.3)
                    add_value(map_object, map_key, compacted_item, as_array)
                # 12.8.8.2)
                elif GRAPH in container and INDEX in container and is_simple_graph_object(expanded_item):
                    # 12.8.8.2.1)
                    map_object = cast(JsonMap, nest_result.setdefault(item_active_property, {}))
                    # 12.8.8.2.2)
                    index_or_none: str = cast(str, expanded_item[INDEX]) if INDEX in expanded_item else NONE
                    map_key = iri_compaction(active_context, index_or_none)
                    # 12.8.8.2.3)
                    add_value(map_object, map_key, compacted_item, as_array)
                # 12.8.8.3)
                elif GRAPH in container and is_simple_graph_object(expanded_item):
                    # 12.8.8.3.1)
                    if isinstance(compacted_item, List) and len(compacted_item) > 1:
                        compacted_item = {iri_compaction(active_context, INCLUDED): compacted_item}
                    # 12.8.8.3.2)
                    add_value(nest_result, item_active_property, compacted_item, as_array)
                # 12.8.8.4)
                else:
                    # 12.8.8.4.1)
                    compacted_item = {iri_compaction(active_context, GRAPH): compacted_item}
                    assert isinstance(compacted_item, Dict)
                    # 12.8.8.4.2)
                    if ID in expanded_item:
                        compacted_item[iri_compaction(active_context, ID)] = shorten_iri(active_context, cast(str, expanded_item[ID]))
                    # 12.8.8.4.3)
                    if INDEX in expanded_item:
                        compacted_item[iri_compaction(active_context, INDEX)] = iri_compaction(active_context, cast(str, expanded_item[INDEX]))
                    # 12.8.8.4.4)
                    add_value(nest_result, item_active_property, compacted_item, as_array)

            # 12.8.9)
            elif (LANGUAGE in container
                  or INDEX in container
                  or ID in container
                  or TYPE in container) and GRAPH not in container:
                assert isinstance(expanded_item, Dict)
                # 12.8.9.1)
                map_object = cast(JsonMap, nest_result.setdefault(item_active_property, {}))
                # 12.8.9.2)
                container_kw: str = cast(str, LANGUAGE if LANGUAGE in container else
                                              INDEX if INDEX in container else
                                              ID if ID in container else
                                              TYPE if TYPE in container else None)
                container_key: str = iri_compaction(active_context, container_kw)
                # 12.8.9.3)
                index_key: str = item_active_term.index if item_active_term and item_active_term.index is not None else INDEX
                # 12.8.9.4)
                if LANGUAGE in container and VALUE in expanded_item:
                    # TODO: spec problem; doesn't mention if compacted_item is scalar
                    if isinstance(compacted_item, Dict):
                        compacted_item = compacted_item[VALUE]
                    map_key = cast(str, expanded_item.get(LANGUAGE))
                # 12.8.9.5)
                elif INDEX in container and index_key == INDEX:
                    # TODO: spec problem? This step is not in the spec!
                    if isinstance(compacted_item, Dict) and VALUE in compacted_item and len(compacted_item) == 1:
                        compacted_item = compacted_item[VALUE]
                    map_key = cast(str, expanded_item.get(INDEX))
                # 12.8.9.6)
                elif INDEX in container and index_key != INDEX:
                    # 12.8.9.6.1)
                    container_key = iri_compaction(active_context, index_key)
                    # 12.8.9.6.2)
                    # 12.8.9.6.3)
                    if isinstance(compacted_item, Dict) and container_key in compacted_item:
                        map_key = _get_map_key_and_deplete_container_key(compacted_item, container_key, as_array)
                # 12.8.9.7)
                elif ID in container:
                    assert isinstance(compacted_item, Dict) # TOOD: check?
                    map_key = cast(Optional[str], compacted_item.pop(container_key, None))
                # 12.8.9.8)
                elif TYPE in container:
                    # 12.8.9.8.1)
                    # 12.8.9.8.2)
                    # 12.8.9.8.3)
                    assert isinstance(compacted_item, Dict) # TOOD: check?
                    if container_key in compacted_item:
                        map_key = _get_map_key_and_deplete_container_key(compacted_item, container_key, as_array)
                    # 12.8.9.8.4)
                    if len(compacted_item) == 1:
                        for key, idval in cast(Dict[str, object], compacted_item).items():
                            if active_context.expand_vocab_iri(key) == ID:
                                compacted_item = compaction(
                                        active_context, item_active_property, {ID: idval})
                # 12.8.9.9)
                if map_key is None:
                    map_key = iri_compaction(active_context, NONE)
                # 12.8.9.10)
                add_value(map_object, map_key, compacted_item, as_array)

            # 12.8.10)
            else:
                add_value(nest_result, item_active_property, compacted_item, as_array)

    # 13)
    return result


def _get_map_key_and_deplete_container_key(
        compacted_item: JsonMap,
        container_key: str,
        as_array: bool) -> Optional[str]:
    container_key_values: List[str] = as_list(compacted_item[container_key])

    key_value: JsonObject = container_key_values.pop(0)
    if not isinstance(key_value, str):
        return None
    map_key: str = key_value

    if compacted_item[container_key] is not container_key_values:
        for remaining in list(container_key_values):
            add_value(compacted_item, container_key, remaining)

    if len(container_key_values) == 1 and not as_array:
        compacted_item[container_key] = container_key_values[0]
    elif len(container_key_values) == 0:
        del compacted_item[container_key]

    return map_key


def _get_nest_result(active_context: Context,
        item_active_term: Optional[Term],
        result_map: JsonMap) -> JsonMap:
    # TODO: spec redundancy, steps are the same...
    # 12.7.2 = 12.8.2)
    nest_result: JsonMap
    if item_active_term and item_active_term.nest_value is not None:
        # 12.7.2.1 = 12.8.2.1)
        if item_active_term.nest_value != NEST \
                and active_context.expand_vocab_iri(item_active_term.nest_value) != NEST:
            raise InvalidNestValueError(item_active_term.nest_value)
        # 12.7.2.2 = 12.8.2.2)
        if item_active_term.nest_value not in result_map:
            result_map[item_active_term.nest_value] = {}
        # 12.7.2.3 = 12.8.2.3)
        return cast(JsonMap, result_map[item_active_term.nest_value])
    # 12.7.3 = 12.8.3)
    else:
        return result_map


def maybe_iri_compaction(active_context: Context,
        iri: Optional[str],
        value: Optional[JsonObject] = None,
        vocab = True,
        reverse = False
        ) -> Optional[str]:
    # 1)
    if iri is None:
        return None
    return iri_compaction(active_context, iri, value, vocab, reverse)


# TODO: spec improvement: allow this to keep IRI:s as is with a flag (also much simpler)!
# Case: To make convenient JSON with preserved input IRIs (or even expanded full IRIs!).
def shorten_iri(active_context: Context, iri: str) -> str:
    return iri_compaction(active_context, iri, None, vocab=False)


def iri_compaction(active_context: Context, iri: str,
        value: Optional[JsonObject] = None,
        vocab = True,
        reverse = False
        ) -> str:
    # 3)
    inverse_context: Dict = get_inverse_context(active_context)

    # 4)
    if vocab and iri in inverse_context:
        # 4.1 + 4.1.2))
        default_language: str = active_context.default_language if active_context.default_language else NONE
        if active_context.default_base_direction is not None:
            # 4.1.1)
            default_language = f'{default_language}_{active_context.default_base_direction}'

        # 4.2)
        if isinstance(value, Dict) and PRESERVE in value:
            values: List = as_list(value[PRESERVE]) # TODO: as_list not needed?
            value = values[0]

        # 4.3)
        containers: List[str] = []

        # 4.4)
        type_or_language: str = LANGUAGE
        type_or_language_value: str = NULL

        # 4.5)
        if isinstance(value, Dict) and INDEX in value and GRAPH not in value:
            containers.append(INDEX)
            containers.append(f'{INDEX}{SET}')

        # 4.6)
        if reverse:
            type_or_language = TYPE
            type_or_language_value = REVERSE
            containers.append(SET)
        # 4.7)
        elif isinstance(value, Dict) and LIST in value:
            # 4.7.1)
            if INDEX not in value:
                containers.append(LIST)
            # 4.7.2)
            valuelist: List[JsonMap] = cast(List[JsonMap], value[LIST])
            # 4.7.3)
            common_type: Optional[str] = None
            common_language: Optional[str] = None
            if len(valuelist) == 0:
                common_language = default_language
            # 4.7.4)
            for item in valuelist:
                # TODO: always expect isinstance(item. Dict)?
                # 4.7.4.1)
                item_language: str = NONE
                item_type: str = NONE
                # 4.7.4.2)
                if isinstance(item, Dict) and VALUE in item:
                    # 4.7.4.2.1)
                    if DIRECTION in item:
                        item_language = f"{cast(str, item.get(LANGUAGE, ''))}_{item[DIRECTION]}"
                    # 4.7.4.2.2)
                    elif LANGUAGE in item:
                        item_language = cast(str, item[LANGUAGE])
                    # 4.7.4.2.3)
                    elif TYPE in item:
                        item_type = cast(str, item[TYPE])
                    # 4.7.4.2.4)
                    else:
                        item_language = NULL
                # 4.7.4.3)
                else:
                    item_type = ID
                # 4.7.4.4)
                if common_language is None:
                    common_language = item_language
                # 4.7.4.5)
                elif item_language != common_language and isinstance(item, Dict) and VALUE in item:
                    common_language = NONE
                # 4.7.4.6)
                if common_type is None:
                    common_type = item_type
                # 4.7.4.7)
                elif item_type != common_type:
                    common_type = NONE
                # 4.7.4.8)
                if common_language == NONE and common_type == NONE:
                    break
            # 4.7.5)
            if common_language is None:
                common_language = NONE
            # 4.7.6)
            if common_type is None:
                common_type = NONE
            # 4.7.7)
            if common_type != NONE:
                type_or_language = TYPE
                type_or_language_value = common_type
            # 4.7.8)
            else:
                type_or_language_value = common_language
        # 4.8)
        elif isinstance(value, Dict) and GRAPH in value:
            # 4.8.1)
            if INDEX in value:
                containers.append(f'{GRAPH}{INDEX}')
                containers.append(f'{GRAPH}{INDEX}{SET}')
            # 4.8.2)
            if ID in value:
                containers.append(f'{GRAPH}{ID}')
                containers.append(f'{GRAPH}{ID}{SET}')
            # 4.8.3)
            containers.append(GRAPH)
            containers.append(f'{GRAPH}{SET}')
            containers.append(SET)
            # 4.8.4)
            if INDEX not in value:
                containers.append(f'{GRAPH}{INDEX}')
                containers.append(f'{GRAPH}{INDEX}{SET}')
            # 4.8.5)
            if ID not in value:
                containers.append(f'{GRAPH}{ID}')
                containers.append(f'{GRAPH}{ID}{SET}')
            # 4.8.6)
            containers.append(INDEX)
            containers.append(f'{INDEX}{SET}')
            # 4.8.7)
            type_or_language = TYPE
            type_or_language_value = ID
        # 4.9)
        else:
            # 4.9.1)
            if isinstance(value, Dict) and VALUE in value:
                # 4.9.1.1)
                if DIRECTION in value and INDEX not in value:
                    type_or_language_value = f"{cast(str, value.get(LANGUAGE, ''))}_{value[DIRECTION]}"
                    containers.append(LANGUAGE)
                    containers.append(f'{LANGUAGE}{SET}')
                # 4.9.1.2)
                elif LANGUAGE in value and INDEX not in value:
                    type_or_language_value = cast(str, value[LANGUAGE])
                    containers.append(LANGUAGE)
                    containers.append(f'{LANGUAGE}{SET}')
                # 4.9.1.3)
                elif TYPE in value:
                    type_or_language_value = cast(str, value[TYPE])
                    type_or_language = TYPE
            # 4.9.2)
            else:
                type_or_language = TYPE
                type_or_language_value = ID
                containers.append(ID)
                containers.append(f'{ID}{SET}')
                containers.append(TYPE)
                containers.append(f'{SET}{TYPE}')
            # 4.9.3)
            containers.append(SET)

        # 4.10)
        containers.append(NONE)
        # 4.11)
        if active_context._processing_mode != JSONLD10:
            if not isinstance(value, Dict) or INDEX not in value:
                containers.append(INDEX)
                containers.append(f'{INDEX}{SET}')
        # 4.12)
        if active_context._processing_mode != JSONLD10:
            if isinstance(value, Dict) and len(value) == 1 and VALUE in value:
                containers.append(LANGUAGE)
                containers.append(f'{LANGUAGE}{SET}')
        # 4.13)
        if type_or_language_value is None:
            type_or_language_value = NULL
        # 4.14)
        preferred_values: List[str] = []
        # 4.15)
        if type_or_language_value == REVERSE:
            preferred_values.append(REVERSE)
        # 4.16)
        if type_or_language_value in {ID, REVERSE} and isinstance(value, Dict) and ID in value:
            # 4.16.1)
            compact_id: str = iri_compaction(active_context, cast(str, value[ID]))
            id_term: Optional[Term] = active_context.terms.get(compact_id)
            if id_term and id_term.iri == value[ID]:
                preferred_values.append(VOCAB)
                preferred_values.append(ID)
                preferred_values.append(NONE)
            # 4.16.2)
            else:
                preferred_values.append(ID)
                preferred_values.append(VOCAB)
                preferred_values.append(NONE)
        # 4.17)
        else:
            preferred_values.append(type_or_language_value)
            preferred_values.append(NONE)
            if isinstance(value, Dict) and LIST in value:
                listvalue: List = cast(List, value[LIST])
                if len(listvalue) == 0:
                    type_or_language = ANY
        # 4.18)
        preferred_values.append(ANY)
        # 4.19)
        for pv in cast(List[str], list(preferred_values)):
            idx: int = pv.find('_')
            if idx > -1:
                preferred_values.append(pv[idx:])
        # 4.20)
        term_key: Optional[str] = term_selection(active_context, iri, containers, type_or_language, preferred_values)
        # 4.21)
        if term_key is not None:
            return term_key

    # 5)
    if vocab and active_context.vocabulary_mapping is not None:
        # 5.1)
        if iri.startswith(active_context.vocabulary_mapping):
            suffix: str = iri[len(active_context.vocabulary_mapping):]
            if len(suffix) > 0 and suffix not in active_context.terms:
                return suffix

    # 6)
    compact_iri: Optional[str] = None

    # 7)
    for key, term_dfn in active_context.terms.items():
        # 7.1)
        if term_dfn.iri is None or term_dfn.iri == iri or not iri.startswith(term_dfn.iri) or not term_dfn.is_prefix:
            continue
        # 7.2)
        candidate: str = f'{key}:{iri[len(term_dfn.iri):]}'
        # 7.3)
        if compact_iri is None or len(candidate) <= len(compact_iri) and candidate < compact_iri:
            if candidate not in active_context.terms or active_context.terms[candidate].iri == iri and value is None:
                compact_iri = candidate

    # 8)
    if compact_iri is not None:
        return compact_iri

    # 9)
    colonx: int = iri.find(':')
    if colonx > -1 and '//' not in iri:
        term: Optional[Term] = active_context.terms.get(iri[0:colonx])
        if term and term.is_prefix:
            raise IRIConfusedWithPrefixError(str(iri))

    # 10)
    if not vocab:
        iri = relativise_iri(active_context.base_iri, iri)

    # 11)
    return iri


def term_selection(active_context: Context,
        keyword_or_iri: str,
        containers: List[str],
        type_or_language: str,
        preferred_values: List[str]) -> Optional[str]:
    # 1)
    # 2)
    inverse_context: Dict = get_inverse_context(active_context)
    # 3)
    container_map: JsonMap = cast(JsonMap, inverse_context[keyword_or_iri])
    # 4)
    for container in containers:
        # 4.1)
        if container not in container_map:
            continue
        # 4.2)
        typelanguage_map: JsonMap = cast(JsonMap, container_map[container])
        # 4.3)
        value_map: Dict[str, str] = cast(Dict[str, str], typelanguage_map[type_or_language])
        # 4.4)
        for item in preferred_values:
            # 4.4.1)
            if item not in value_map:
                continue
            # 4.4.2)
            return value_map[item]
    # 5)
    return None


def value_compaction(
        active_context: Context,
        active_term: Optional[Term],
        value: JsonMap
        ) -> JsonObject:
    # 1)
    result: JsonObject = dict(value)
    # 2)
    # 3)
    inverse_context: Dict = get_inverse_context(active_context)
    # 4)
    language: Optional[str] = active_context.default_language
    if active_term and active_term.language is not None:
        language = active_term.language
    # 5)
    direction: Optional[str] = active_context.default_base_direction
    if active_term and active_term.direction is not None:
        direction = active_term.direction
    # 6)
    if ID in value and len(value) == 1 or len(value) == 2 and INDEX in value:
        # 6.1)
        if active_term and active_term.type_mapping == ID:
            result = shorten_iri(active_context, cast(str, value[ID]))
        # 6.2)
        elif active_term and active_term.type_mapping == VOCAB:
            result = iri_compaction(active_context, cast(str, value[ID]))
    # 7)
    elif active_term and TYPE in value and value[TYPE] == active_term.type_mapping:
        result = value[VALUE]
    # 8)
    elif (active_term and active_term.type_mapping == NONE) or TYPE in value and (active_term is None or value[TYPE] != active_term.type_mapping):
        # 8.1)
        if isinstance(result, Dict) and TYPE in result:
            # TODO: spec problem; if type value is an array...
            rtype: Union[str, List[str]] = result[TYPE]
            if isinstance(rtype, List):
                ctypes: List[str] = []
                for t in rtype:
                    ctypes.append(iri_compaction(active_context, cast(str, t)))
                result[TYPE] = ctypes
            else:
                result[TYPE] = iri_compaction(active_context, cast(str, rtype))
    # 9)
    elif VALUE in value and not isinstance(value[VALUE], str):
        # 9.1)
        if (INDEX in value and active_term and INDEX in active_term.container) or INDEX not in value:
            result = value[VALUE]
    # 10) # TODO: opague spec text.
    elif VALUE in value and (LANGUAGE in value and value[LANGUAGE] == language or language in NULLS and LANGUAGE not in value):
        if DIRECTION not in value or direction is not None and value[DIRECTION] == direction:
            # 10.1)
            if INDEX not in value or (active_term and INDEX in active_term.container):
                result = value[VALUE]
    # 11)
    if isinstance(result, Dict):
        compacted: Dict = {}
        for k, v in cast(JsonMap, result).items():
            compacted[iri_compaction(active_context, k, v)] = v
        result = compacted
    # 12)
    return result
