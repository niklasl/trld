# TODO: Improve transpile to remove redundant redundancies:
# - Most cast calls (especially "upcasts" to JsonObject)
# - Some `if ...: if ....:` could be just `and` with paren grouping

from typing import Optional, Dict, List, Set, Union, cast
from .base import *
from .common import warning
from .context import Context, Term, InvalidBaseDirectionError, InvalidNestValueError


# framing keywords
DEFAULT: str = '@default'
EMBED: str = '@embed'
EXPLICIT: str = '@explicit'
OMIT_DEFAULT: str = '@omit_default'
REQUIRES_ALL: str = '@requires_all'
FRAMING_KEYWORDS: Set[str] = {DEFAULT, EMBED, EXPLICIT, OMIT_DEFAULT, REQUIRES_ALL}


class InvalidReversePropertyMapError(JsonLdError): pass

class CollidingKeywordsError(JsonLdError): pass

class InvalidIdValueError(JsonLdError): pass

class InvalidTypeValueError(JsonLdError): pass

class InvalidIncludedValueError(JsonLdError): pass

class InvalidValueObjectError(JsonLdError): pass

class InvalidValueObjectValueError(JsonLdError): pass

class InvalidTypedValueError(JsonLdError): pass

class InvalidSetOrListObjectError(JsonLdError): pass

class InvalidLanguageTaggedValueError(JsonLdError): pass

class InvalidLanguageTaggedStringError(JsonLdError): pass

class InvalidIndexValueError(JsonLdError): pass

class InvalidReverseValueError(JsonLdError): pass

class InvalidReversePropertyValueError(JsonLdError): pass

class InvalidLanguageMapValueError(JsonLdError): pass


def expand(doc_data: JsonObject,
           base_iri: str,
           expand_context: str = None,
           ordered = False) -> List:
    ctx: Context = Context(base_iri)
    if expand_context is not None:
        ctx = ctx.get_context(expand_context, expand_context)
    result: Optional[JsonObject] = expansion(ctx, None, doc_data, base_iri,
                                             False, ordered)
    if result is None:
        return []
    if isinstance(result, Dict) and GRAPH in result and len(result) == 1:
        result = result[GRAPH]
    return as_list(result)


def expansion(active_context: Context,
        active_property: Optional[str],
        element: Optional[JsonObject],
        base_url: str,
        frame_expansion = False,
        ordered = False,
        from_map = False,
        # additional flags:
        warn_on_keywordlike_terms = False,
        warn_on_empty_keys = False,
        warn_on_bnode_properties = False,
        ) -> Optional[JsonObject]:
    # 1)
    if element is None:
        return None

    # 2)
    if active_property == '@default':
        frame_expansion = False

    property_scoped_context: Optional[Context] = None

    # 3)
    if active_property in active_context.terms and \
            active_context.terms[active_property].has_local_context:
        property_scoped_context = active_context.terms[active_property].get_local_context(active_context)

    # 4)
    if not isinstance(element, (Dict, List)):
        # 4.1)
        if active_property is None or active_property == GRAPH:
            return None
        # 4.2)
        if property_scoped_context is not None:
            active_context = property_scoped_context
        # 4.3)
        return value_expansion(active_context, active_property, element)

    # 5)
    if isinstance(element, List):
        # 5.1)
        results: List = []
        # 5.2)
        for item in element:
            # 5.2.1)
            expanded_item: Optional[JsonObject] = expansion(active_context, active_property, item, base_url, frame_expansion, from_map)
            # 5.2.2)
            active_term: Optional[Term] = active_context.terms.get(active_property)
            if active_term is not None and LIST in active_term.container and isinstance(expanded_item, List):
                expanded_item = {LIST: expanded_item}

            # 5.2.3)
            if isinstance(expanded_item, List):
                results += expanded_item
            elif expanded_item is not None:
                results.append(expanded_item)

        # 5.3)
        return results

    # 6)
    assert isinstance(element, Dict)

    # 7)
    # TODO: differs from spec (see spec problem 5f496df9)
    if not active_context._propagate and active_context.previous_context:
        # TODO: to make effectively final for closure generated by transpile
        active_context2: Context = active_context 
        if ((not from_map)
            and (not any(k in active_context2.terms and active_context2.terms[k].iri == VALUE for k in element))
            and (not (len(element) == 1 and any(active_context2.expand_iri(cast(str, k)) == ID for k in element)))):
            active_context = active_context.previous_context

    # 8)
    if property_scoped_context is not None:
        active_context = property_scoped_context

    # 9)
    if CONTEXT in element:
        active_context = active_context.get_context(element[CONTEXT], base_url)

    # 10)
    type_scoped_context: Context = active_context

    # 11)
    values: Optional[List[str]] = None
    keys: List[str] = list(element.keys())
    keys.sort()
    for key in keys:
        if type_scoped_context.expand_iri(key) == TYPE:
            # 11.1)
            values = list(as_list(element[key]))
            values.sort()
            # 11.2)
            for value in values:
                term: Optional[Term] = type_scoped_context.terms.get(value)
                if isinstance(value, str) and term and term.has_local_context:
                    active_context = term.get_local_context(type_scoped_context, False)

    # 12)
    result: Dict = {}
    nests: Dict = {}
    input_type: Optional[str] = values[-1] if values else None
    if input_type is not None and isinstance(input_type, str):
        # TODO: or expand immediately above?
        input_type = active_context.expand_iri(input_type)


    # 13) + 14)
    _expand_element(
            active_context, type_scoped_context, active_property, element, result, nests, input_type,
            base_url, frame_expansion, ordered, from_map,
            warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties)

    # 15)
    if VALUE in result:
        resultval: JsonObject = result[VALUE]
        # 15.1)
        if any(k not in VALUE_KEYWORDS for k in result.keys()) \
           or TYPE in result and (LANGUAGE in result or DIRECTION in result):
            raise InvalidValueObjectError
        # 15.2)
        if TYPE in result and result[TYPE] == JSON:
            pass # VALUE entry may contain any value
        # 15.3)
        elif resultval is None or resultval == []:
            return None
        # 15.4)
        elif not isinstance(resultval, str) and LANGUAGE in result:
            raise InvalidLanguageTaggedValueError
        # 15.5)
        # TODO: simpler but doesn't transpile.java
        #elif TYPE in result and not all(is_iri(t) for t in result[TYPE]):
        elif TYPE in result and not all(is_iri(cast(str, t)) for t in as_list(result[TYPE])):
            raise InvalidTypedValueError(str(result[TYPE]))

    # 16)
    elif TYPE in result and not isinstance(result[TYPE], List):
        result[TYPE] = [result[TYPE]]

    # 17)
    elif SET in result or LIST in result:
        # 17.1)
        if len(result) > 1:
            if len(result) > 2 or INDEX not in result:
                raise InvalidSetOrListObjectError(str(result))
        # 17.2)
        if SET in result:
            # TODO: spec says "set result to", but the remaining steps are only
            # applicable when result is still a Dict...
            #result =
            return result[SET]

    # 18)
    if len(result) == 1 and LANGUAGE in result:
        return None

    # 19)
    if active_property is None or active_property == GRAPH:
        # 19.1)
        # TODO: spec errata: step says "or contains only the entries @value or list@"
        # By dropping "only", TC 0046 passes.
        # Thus removed from paren after `or`: `len(result) == 1 and `
        if (isinstance(result, Dict) and len(result) == 0) or ((VALUE in result or LIST in result)):
            return None
        # 19.2)
        elif not frame_expansion and len(result) == 1 and ID in result:
            return None

    # 20)
    return result


def _expand_element(active_context: Context,
        type_scoped_context: Context,
        active_property: Optional[str],
        element: JsonOptMap,
        result: JsonOptMap,
        nests: JsonMap,
        input_type: Optional[str],
        base_url: str,
        frame_expansion = False,
        ordered = False,
        from_map = False,
        # additional flags:
        warn_on_keywordlike_terms = False,
        warn_on_empty_keys = False,
        warn_on_bnode_properties = False,
        ):
    # 13)
    keys: List[str] = list(element.keys())
    if ordered:
        keys.sort()
    for key in keys:
        value: Optional[JsonObject] = element[key]
        expanded_value: Optional[JsonObject] = None
        expanded_map: JsonOptMap
        expanded_list: JsonOptList
        reverse_map: JsonMap

        # 13.1)
        if key == CONTEXT:
            continue
        # 13.2)
        expanded_property: Optional[str] = active_context.expand_vocab_iri(key)
        # 13.3)
        if expanded_property is None or (':' not in expanded_property and expanded_property not in KEYWORDS):
            continue
        # 13.4)
        if expanded_property in KEYWORDS:
            # 13.4.1)
            if active_property == REVERSE:
                raise InvalidReversePropertyMapError
            # 13.4.2)
            if expanded_property in result and expanded_property not in {INCLUDED, TYPE}:
                pass # FIXME: expansion TC in06 fails with this on ID! Due to nested recusion?
                # TODO: spec problem; just allow ID too?
                #raise CollidingKeywordsError(expanded_property)

            # 13.4.3)
            if expanded_property == ID:
                # 13.4.3.1)
                if not isinstance(value, str) or (frame_expansion and
                        (value == {} or isinstance(value, List))):
                    raise InvalidIdValueError
                # 13.4.3.2)
                if frame_expansion:
                    expanded_value = expanded_list = []
                    for v in expanded_list:
                        expanded_list.append(
                            active_context.expand_doc_relative_iri(v)
                            if isinstance(v, str) else v)
                else:
                    expanded_value = active_context.expand_doc_relative_iri(value)

            # 13.4.4)
            elif expanded_property == TYPE:
                # 13.4.4.1)
                if not isinstance(value, (str, List)) and not (
                        frame_expansion and (value == {} or
                            (isinstance(value, Dict) and
                             is_iri(cast(str, value.get(DEFAULT)))))): # type: ignore
                    raise InvalidTypeValueError
                # 13.4.4.2)
                if isinstance(value, Dict) and value == {}:
                    expanded_value = expanded_map = value
                # 13.4.4.3)
                elif isinstance(value, Dict) and DEFAULT in value:
                    expanded_map = {DEFAULT: type_scoped_context.expand_doc_relative_vocab_iri(cast(str, value[DEFAULT]))}
                # 13.4.4.4)
                else:
                    expanded_value = expanded_list = []
                    for v in as_list(cast(JsonObject, value)):
                        expanded_list.append(type_scoped_context.expand_doc_relative_vocab_iri(cast(str, v)))
                    # TODO: spec errata: be more explicit about collapsing singe-item list
                    if len(expanded_list) == 1:
                        expanded_value = expanded_list[0]
                # 13.4.4.5)
                if TYPE in result:
                    expanded_value = as_list(result[TYPE]) + as_list(expanded_value)
                # TODO: will result be set further below?
                #else:
                #    result[TYPE] = expanded_value

            # 13.4.5)
            elif expanded_property == GRAPH:
                expanded_value = as_list(expansion(active_context,
                    GRAPH, value,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties))

            # 13.4.6)
            elif expanded_property == INCLUDED:
                # 13.4.6.1)
                if active_context._processing_mode == JSONLD10:
                    continue
                # 13.4.6.2)
                expanded_value = expanded_list = as_list(expansion(active_context,
                    None, value,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties))
                # 13.4.6.3)
                if any(not isinstance(v, Dict) for v in expanded_list):
                    raise InvalidIncludedValueError
                # 13.4.6.4)
                if INCLUDED in result:
                    expanded_value = as_list(result[INCLUDED]) + expanded_list

            # 13.4.7)
            elif expanded_property == VALUE:
                # 13.4.7.1)
                if input_type == JSON:
                    if active_context._processing_mode == JSONLD10:
                        raise InvalidValueObjectValueError
                    expanded_value = value
                # 13.4.7.2)
                elif (not is_scalar(value) and value is not None) and not \
                    (frame_expansion and (value == {} or
                        (isinstance(value, List) and
                         all(is_scalar(v) for v in value)))):
                    raise InvalidValueObjectValueError(f'Unexpected value {value}')
                # 13.4.7.3)
                else:
                    expanded_value = cast(JsonObject, value)
                    if frame_expansion:
                        expanded_value = as_list(expanded_value)
                # 13.4.7.4)
                if expanded_value is None:
                    result[VALUE] = None
                    continue

            # 13.4.8)
            elif expanded_property == LANGUAGE:
                # 13.4.8.1)
                if not isinstance(value, str):
                    raise InvalidLanguageTaggedStringError
                # 13.4.8.2)
                expanded_value = value
                if not is_lang_tag(value):
                    warning(f'Language tag {value} is not well-formed')
                if frame_expansion:
                    expanded_value = as_list(expanded_value)

            # 13.4.9)
            elif expanded_property == DIRECTION:
                # 13.4.9.1)
                if active_context._processing_mode == JSONLD10:
                    continue
                # 13.4.9.2)
                if value not in DIRECTIONS or frame_expansion and (value != {} or isinstance(value, List) and not all(isinstance(v, str) for v in value)):
                    raise InvalidBaseDirectionError
                # 13.4.9.3)
                expanded_value = value
                if frame_expansion:
                    expanded_value = as_list(expanded_value)

            # 13.4.10)
            elif expanded_property == INDEX:
                # 13.4.10.1)
                if not isinstance(value, str):
                    raise InvalidIndexValueError
                # 13.4.10.2)
                expanded_value = value

            # 13.4.11)
            elif expanded_property == LIST:
                # 13.4.11.1)
                if active_property is None or active_property == GRAPH:
                    continue
                # 13.4.11.2)
                expanded_value = as_list(expansion(active_context,
                    active_property, value,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties))

            # 13.4.12)
            elif expanded_property == SET:
                expanded_value = expansion(active_context,
                        active_property, value,
                        base_url, frame_expansion, ordered, from_map,
                        warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties)

            # 13.4.13)
            elif expanded_property == REVERSE:
                # 13.4.13.1)
                if not isinstance(value, Dict):
                    raise InvalidReverseValueError
                # 13.4.13.2)
                # TODO:[5f4f785a] algorithm uses expanded_value regardless of
                # type, but declaring local, specifically typed variables are
                # simpler to transcribe. (We probably want to factor out the
                # steps instead though, to reduce and isolate scopes (and smoke
                # out complexity).)
                expanded_map = cast(JsonOptMap, expansion(active_context,
                    REVERSE, value,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties))

                # 13.4.13.3)
                if REVERSE in expanded_map:
                    # 13.4.13.3.1)
                    entry: JsonMap = cast(JsonMap, expanded_map[REVERSE])
                    for prop, item in entry.items():
                        add_value_as_list(result, prop, item)

                # 13.4.13.4)
                if any(k != REVERSE for k in expanded_map.keys()):
                    # 13.4.13.4.1)
                    reverse_map = cast(JsonMap, result.setdefault(REVERSE, {}))
                    # 13.4.13.4.2)
                    for prop, items in expanded_map.items():
                        # 13.4.13.4.2.1)
                        for item in cast(List[JsonMap], items):
                            # 13.4.13.4.2.1.1)
                            if isinstance(item, Dict) and (VALUE in item or LIST in item):
                                raise InvalidReversePropertyValueError
                            # 13.4.13.4.2.1.2)
                            add_value_as_list(reverse_map, prop, item)

                # 13.4.13.5)
                continue

            # 13.4.14)
            elif expanded_property == NEST:
                nests.setdefault(key, [])
                continue

            # 13.4.15)
            if frame_expansion and expanded_property in FRAMING_KEYWORDS:
                expanded_value = expansion(active_context,
                        active_property, value,
                        base_url, frame_expansion, ordered, from_map,
                        warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties)

            # 13.4.16)
            if not (expanded_value is None and expanded_property == VALUE and input_type != JSON):
                result[expanded_property] = expanded_value

            # 13.4.17)
            continue

        # 13.5)
        key_term: Optional[Term] = active_context.terms.get(key)
        container_mapping: List = key_term.container if key_term else []

        # 13.6)
        if key_term and key_term.type_mapping == JSON:
            expanded_value = {VALUE: value, TYPE: JSON}

        # 13.7)
        elif LANGUAGE in container_mapping and isinstance(value, Dict):
            # 13.7.1)
            expanded_value = expanded_list = []
            # 13.7.2)
            direction: Optional[str] = active_context.default_base_direction
            # 13.7.3)
            if key_term and key_term.direction is not None:
                direction = key_term.direction
            # 13.7.4)
            languages: List[str] = list(value.keys())
            if ordered:
                languages.sort()
            for lang in languages:
                # 13.7.4.1)
                langvalues: List[str] = as_list(value[lang])
                # 13.7.4.2)
                for item in langvalues:
                    # 13.7.4.2.1)
                    if item is None:
                        continue
                    # 13.7.4.2.2)
                    if not isinstance(item, str):
                        raise InvalidLanguageMapValueError
                    # 13.7.4.2.3)
                    o: Dict[str, str] = {VALUE: item, LANGUAGE: lang}
                    # TODO: spec errata: s/If item/If language/
                    if lang not in NULLS and not is_lang_tag(lang):
                        warning(f'Language tag {value} is not well-formed')
                    # 13.7.4.2.4)
                    if lang in NULLS or active_context.expand_iri(lang) == NONE:
                        del o[LANGUAGE]
                    # 13.7.4.2.5)
                    if direction not in NULLS: # TODO: marked from None
                        o[DIRECTION] = cast(str, direction)
                    # 13.7.4.2.6)
                    expanded_list.append(o)

        # 13.8)
        elif any(k in container_mapping for k in [INDEX, TYPE, ID]) and isinstance(value, Dict):
            # 13.8.1)
            expanded_value = expanded_list = []
            # 13.8.2)
            index_key: str = INDEX
            if key_term and key_term.index is not None:
                index_key = key_term.index

            # 13.8.3)
            indexes: List[str] = list(value.keys())
            if ordered:
                indexes.sort()
            for index in indexes:
                # 13.8.3.1)
                map_context: Context
                if (ID in container_mapping or TYPE in container_mapping) and \
                        active_context.previous_context:
                    map_context = active_context.previous_context
                else:
                    map_context = active_context

                # 13.8.3.2)
                index_term: Optional[Term] = active_context.terms.get(index)
                if TYPE in container_mapping and index_term and index_term.has_local_context:
                    map_context = index_term.get_local_context(map_context)
                # 13.8.3.3)
                else:
                    map_context = active_context

                # 13.8.3.4)
                expanded_index: str = cast(str, active_context.expand_vocab_iri(index))
                # 13.8.3.5)
                index_values: List[JsonMap] = as_list(value[index])
                # 13.8.3.6)
                index_values = cast(List[JsonMap], expansion(map_context,
                    key, index_values,
                    base_url, frame_expansion, ordered, True,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties))
                # 13.8.3.7)
                for item in index_values:
                    # 13.8.3.7.1)
                    if GRAPH in container_mapping and (not isinstance(item, Dict) or GRAPH not in item):
                        item = {GRAPH: as_list(item)}
                    # 13.8.3.7.2)
                    if INDEX in container_mapping and index_key != INDEX and expanded_index != NONE:
                        # 13.8.3.7.2.1)
                        reexpanded_index: JsonObject = value_expansion(
                                active_context, index_key, index)
                        # 13.8.3.7.2.2)
                        expanded_index_key: str = cast(str, active_context.expand_vocab_iri(index_key))
                        # 13.8.3.7.2.3)
                        index_property_values: List = [reexpanded_index]
                        if expanded_index_key in item:
                            index_property_values += as_list(item[expanded_index_key])
                        # 13.8.3.7.2.4)
                        item[expanded_index_key] = index_property_values
                        # 13.8.3.7.2.5)
                        if isinstance(value, Dict) and VALUE in value and len(value) > 1:
                            raise InvalidValueObjectError
                    # 13.8.3.7.3)
                    elif INDEX in container_mapping and INDEX not in item and expanded_index != NONE:
                        item[INDEX] = index
                    # 13.8.3.7.4)
                    elif ID in container_mapping and ID not in item and expanded_index != NONE:
                        # TODO: spec errata: different from step 13.8.3.4?
                        expanded_index = cast(str, active_context.expand_doc_relative_iri(index))
                        item[ID] = expanded_index
                    # 13.8.3.7.5)
                    elif TYPE in container_mapping and expanded_index != NONE:
                        types: List[str] = [expanded_index]
                        if TYPE in item:
                            types += as_list(item[TYPE])
                        item[TYPE] = types
                    # 13.8.3.7.6)
                    expanded_list.append(item)

        # 13.9)
        else:
            expanded_value = expansion(active_context,
                    key, value,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties)

        # 13.10)
        if expanded_value is None:
            continue

        # 13.11)
        if LIST in container_mapping:
            if not isinstance(expanded_value, Dict) or LIST not in expanded_value:
                expanded_value = {LIST: as_list(cast(JsonObject, expanded_value))}

        # 13.12)
        if GRAPH in container_mapping and ID not in container_mapping and INDEX not in container_mapping:
            new_expanded: List = []
            for ev in as_list(expanded_value):
                # 13.12.1)
                new_expanded.append({GRAPH: as_list(ev)})
            expanded_value = new_expanded

        # 13.13)
        if key_term and key_term.is_reverse_property:
            # 13.13.1)
            # 13.13.2)
            reverse_map = cast(JsonMap, result.setdefault(REVERSE, {}))
            # 13.13.3)
            if not isinstance(expanded_value, List):
                expanded_value = [expanded_value]
            # 13.13.4)
            for item in expanded_value:
                # 13.13.4.1)
                if isinstance(item, Dict) and (VALUE in item or LIST in item):
                    raise InvalidReversePropertyValueError
                # 13.13.4.2)
                rev_entry: List = cast(List, reverse_map.setdefault(expanded_property, []))
                # 13.13.4.3)
                add_value_as_list(reverse_map, expanded_property, item)

        # 13.14)
        else:
            add_value_as_list(result, expanded_property, expanded_value)

    # 14)
    nesting_keys: List[str] = list(nests.keys())
    if ordered:
        nesting_keys.sort()
    for nesting_key in nesting_keys:
        # 14.1)
        nested_values: List[JsonObject] = as_list(element[nesting_key]) if nesting_key in element else []
        # 14.2)
        for nested_value in nested_values:
            # 14.2.1)
            if not isinstance(nested_value, Dict) or any(active_context.expand_iri(cast(str, k)) == VALUE for k in nested_value.keys()):
                raise InvalidNestValueError
            # 14.2.2)
            # TODO:
            _expand_element(
                    active_context, type_scoped_context, active_property, nested_value, result, nests, input_type,
                    base_url, frame_expansion, ordered, from_map,
                    warn_on_keywordlike_terms, warn_on_empty_keys, warn_on_bnode_properties)


def value_expansion(active_context: Context, active_property: str, value: Scalar) -> JsonObject:
    # 1)
    active_term: Optional[Term] = active_context.terms.get(active_property)
    if active_term and active_term.type_mapping == ID and isinstance(value, str):
        return {ID: active_context.expand_doc_relative_iri(value)}

    # 2)
    if active_term and active_term.type_mapping == VOCAB and isinstance(value, str):
        return {ID: active_context.expand_doc_relative_vocab_iri(value)}

    # 3)
    result: Dict[str, Optional[JsonObject]] = {VALUE: value}

    # 4)
    if active_term and active_term.type_mapping not in {ID, VOCAB, NONE, None}:
        result[TYPE] = active_term.type_mapping
    # 5)
    elif isinstance(value, str):
        # 5.1)
        language: Optional[str] = active_context.default_language
        if active_term and active_term.language is not None:
            # TODO: see 5f6117d4
            language = None if active_term.language in NOTHING else active_term.language
        # 5.2)
        direction: Optional[str] = active_context.default_base_direction
        if active_term and active_term.direction is not None:
            # TODO: see previous about Term step 22 (this corresponds to step 23)
            direction = None if active_term.direction in NOTHING else active_term.direction
        # 5.3)
        if language is not None:
            result[LANGUAGE] = language
        # 5.4)
        if direction is not None:
            result[DIRECTION] = direction

    # 6)
    return result
