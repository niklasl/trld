from typing import Dict

from ..base import BASE, VOCAB
from ..context import Context, get_context


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
