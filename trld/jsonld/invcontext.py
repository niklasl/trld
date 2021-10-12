from .base import *
from .context import Context, Term


def get_inverse_context(active_context: Context) -> Dict:
    if active_context._inverse_context is None:
        active_context._inverse_context = create_inverse_context(active_context)
    return active_context._inverse_context


def create_inverse_context(active_context: Context) -> JsonMap:
    # 1)
    result: JsonMap = {}

    # 2)
    default_language: str = active_context.default_language if active_context.default_language else NONE

    # 3)
    term_keys: List[Optional[str]] = list(active_context.terms.keys())
    term_keys.sort(key=lambda s: (len(cast(str, s)) if s is not None else 0, s))
    for term_key in term_keys:
        assert isinstance(term_key, str) # TODO: Optional just to allow .get(Optional) ...
        term_dfn: Optional[Term] = active_context.terms[term_key]
        # 3.1)
        if term_dfn is None:
            continue
        # 3.2)
        container: str = NONE
        if len(term_dfn.container) > 0:
            container = ''.join(sorted(term_dfn.container))
        # 3.3)
        iri: str = term_dfn.iri
        # 3.4)
        if iri not in result:
            result[iri] = {}
        # 3.5)
        container_map: JsonMap = cast(JsonMap, result[iri])
        # 3.6)
        if container not in container_map:
            container_map[container] = {LANGUAGE: {}, TYPE: {}, ANY: {NONE: term_key}}
        # 3.7)
        typelanguage_map: JsonMap = cast(JsonMap, container_map[container])
        # 3.8)
        type_map: JsonMap = cast(JsonMap, typelanguage_map[TYPE])
        # 3.9)
        language_map: JsonMap = cast(JsonMap, typelanguage_map[LANGUAGE])
        lang_dir: str
        # 3.10)
        if term_dfn.is_reverse_property:
            # 3.10.1)
            if REVERSE not in type_map:
                type_map[REVERSE] = term_key
        # 3.11)
        elif term_dfn.type_mapping == NONE:
            # 3.11.1)
            if ANY not in language_map:
                language_map[ANY] = term_key
            # 3.11.2)
            if ANY not in type_map:
                type_map[ANY] = term_key
        # 3.12)
        elif term_dfn.type_mapping is not None:
            # 3.12.1)
            if term_dfn.type_mapping not in type_map:
                type_map[term_dfn.type_mapping] = term_key
        # 3.13)
        elif term_dfn.language is not None and term_dfn.direction is not None:
            # 3.13.1 + # 3.13.5)
            lang_dir = NULL
            # 3.13.2)
            if term_dfn.language is not NULL and term_dfn.direction is not NULL:
                lang_dir = f'{term_dfn.language}_{term_dfn.direction}'
            # 3.13.3)
            elif term_dfn.language is not NULL:
                lang_dir = term_dfn.language
            # 3.13.4)
            elif term_dfn.direction is not NULL:
                lang_dir = term_dfn.direction
            # 3.13.6)
            if lang_dir not in language_map:
                language_map[lang_dir] = term_key
        # 3.14)
        elif term_dfn.language is not None:
            # 3.14.1)
            language: str = term_dfn.language
            # 3.14.2)
            if language not in language_map:
                language_map[language] = term_key
        # 3.15)
        elif term_dfn.direction is not None:
            # 3.15.1)
            direction: str = term_dfn.direction
            if direction == NULL:
                direction = NONE
            else:
                direction = f'_{direction}'
            # 3.15.2)
            if direction not in language_map:
                language_map[direction] = term_key
        # 3.16)
        elif active_context.default_base_direction:
            # 3.16.1)
            lang_dir = f'{active_context.default_language}_{active_context.default_base_direction}'
            # 3.16.2)
            if lang_dir not in language_map:
                language_map[lang_dir] = term_key
            # 3.16.3)
            if NONE not in language_map:
                language_map[NONE] = term_key
            # 3.16.4)
            if NONE not in type_map:
                type_map[NONE] = term_key
        # 3.17)
        else:
            # 3.17.1)
            if active_context.default_language  is not None and active_context.default_language not in language_map:
                language_map[active_context.default_language] = term_key
            # 3.17.2)
            if NONE not in language_map:
                language_map[NONE] = term_key
            # 3.17.3)
            if NONE not in type_map:
                type_map[NONE] = term_key

    # 4)
    return result

