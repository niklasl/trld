from typing import Dict

from ..keys import (BASE, CONTAINER, CONTEXT, DIRECTION, ID, INDEX, LANGUAGE,
                    NEST, PROTECTED, REVERSE, TYPE, VOCAB)
from ..context import Context, get_context
from ..compaction import iri_compaction


def to_simple_context(context: Context) -> Dict:
    ctx_data: Dict[str, str] = {}

    if context.base_iri:
        ctx_data[BASE] = context.base_iri

    if context.vocabulary_mapping:
        ctx_data[VOCAB] = context.vocabulary_mapping

    for key, term in context.terms.items():
        if term.is_prefix and isinstance(key, str):
            ctx_data[key] = term.iri

    return ctx_data


def to_context_data(context: Context) -> Dict:
    ctx_data: Dict[str, object] = {}

    if context.base_iri:
        ctx_data[BASE] = context.base_iri

    if context.vocabulary_mapping:
        ctx_data[VOCAB] = context.vocabulary_mapping

    for key, term in context.terms.items():
        if not isinstance(key, str):
            continue

        if term.is_prefix:
            ctx_data[key] = term.iri

    simple_context = get_context({CONTEXT: ctx_data})

    for key, term in context.terms.items():
        if not isinstance(key, str):
            continue

        if term.is_prefix:
            continue

        term_data: Dict[str, object] = {}

        if term.iri is not None:
            curie = iri_compaction(simple_context, term.iri)
            term_data[REVERSE if term.is_reverse_property else ID] = curie

        for keyword, value in [
            (TYPE, term.type_mapping),
            (LANGUAGE, term.language),
            (CONTAINER, term.container),
            (BASE, term.base_url),
            (INDEX, term.index),
            (NEST, term.nest_value),
            (PROTECTED, term.is_protected),
            (DIRECTION, term.direction),
        ]:
            if value:
                v = value[0] if isinstance(value, list) and len(value) == 1 else value
                term_data[keyword] = v

        if term.has_local_context:
            term_data[CONTEXT] = term._local_context

        if len(term_data) == 1:
            ctx_data[key] = term_data[ID]
        else:
            if term_data.get(ID) == key:
                del term_data[ID]
            if len(term_data) > 0:
                ctx_data[key] = term_data

    return ctx_data


if __name__ == '__main__':

    import json
    import sys

    for ref in sys.argv[1:]:

        ctx = get_context(ref)
        ctx_data = to_context_data(ctx)

        json.dump(ctx_data, sys.stdout, indent=2)
