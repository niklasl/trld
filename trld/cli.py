import argparse
import json
import os
import sys

from .platform.common import json_encode
from .jsonld.keys import CONTAINER, CONTEXT, TYPE
from .jsonld.compaction import compact
from .jsonld.context import get_context
from .jsonld.docloader import set_document_loader, any_document_loader
from .jsonld.expansion import expand
from .jsonld.extras.contexts import to_simple_context
from .jsonld.flattening import flatten
from .api import parse_rdf, serialize_rdf


set_document_loader(any_document_loader)


def printerr(msg):
    print(msg, file=sys.stderr)


def process_source(source, args, ordered=True):
    source_is_data = isinstance(source, (dict, list))

    context_ref = args.context

    base_iri = (
        args.base if args.base
        else f'file://{os.getcwd()}/' if source_is_data or source == '-'
        else f'file://{source}' if '://' not in source
        else source
    )

    try:
        if source_is_data:
            data = source
        else:
            data = parse_rdf(source, args.input_format)

        if args.expand_context:
            expand_context = (
                None if args.expand_context == True else args.expand_context
            )
            result = expand(data, base_iri, expand_context, ordered=ordered)
        else:
            result = data

        if args.flatten or args.output_format in {'nq', True}:
            result = flatten(result, ordered=ordered)

        context = None

        if context_ref:
            if context_ref is True:
                context_ref = data
            elif isinstance(context_ref, str):
                context_ref = _absolutize(context_ref)

            context = get_context(context_ref)
            result = compact(context, result, base_iri, ordered=ordered)

            if isinstance(context_ref, dict) and CONTEXT in context_ref:
                result[CONTEXT] = context_ref[CONTEXT]

        if args.embed_blanks:
            from .jsonld.extras.frameblanks import frameblanks  # type: ignore[import]

            result = frameblanks(result)

        serialize_rdf(result, args.output_format, None, context)

    except Exception as e:
        printerr(f"Error in file '{source}'")
        import traceback
        traceback.print_exc()


def process_linestream(args, stream):
    container_context = {}

    if args.context:
        context = get_context(_absolutize(args.context))

        # Hack to get compact terms but supress prefix declarations in trig output.
        container_context[CONTEXT] = {
            key: {CONTAINER: term.container, TYPE: term.type_mapping}
            for key, term in context.terms.items()
        }

        ctx = to_simple_context(context)
        # Print prefix declarations
        process_source({CONTEXT: ctx}, args)

    for l in stream:
        process_source(json.loads(l) | container_context, args)


def _absolutize(context_ref: str) -> str:
    if '://' not in context_ref and os.path.exists(context_ref):
        return os.path.abspath(context_ref)
    else:
        return context_ref


def make_argsparser():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', metavar='SOURCE', nargs='*')
    argparser.add_argument('-c', '--context', help='Use to compact expanded JSON-LD', const=True, nargs='?')
    argparser.add_argument('-e', '--expand-context', const=True, nargs='?',
                        help='Use to expand plain JSON to JSON-LD')
    argparser.add_argument('-b', '--base',
                        help='Set the base IRI (default is current source)')
    argparser.add_argument('-f', '--flatten', action='store_true')
    argparser.add_argument('-B', '--embed-blanks', action='store_true')
    argparser.add_argument('-i', '--input-format', help='Set RDF input format')
    argparser.add_argument('-o', '--output-format', help='Set RDF output format')

    return argparser


def main():
    args = make_argsparser().parse_args()

    sources = args.source or ['-']

    if args.input_format in ('ndjson', 'jsonl'):
        process_linestream(args, sys.stdin)
    else:
        for source in sources:
            if len(sources) > 1:
                printerr(f"Parsing file: '{source}'")
            process_source(source, args)


if __name__ == '__main__':
    main()
