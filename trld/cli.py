import argparse
import json
import os
import sys

from .platform.common import json_encode
from .jsonld.base import CONTEXT
from .jsonld.compaction import compact
from .jsonld.docloader import set_document_loader, any_document_loader
from .jsonld.expansion import expand
from .jsonld.flattening import flatten
from .api import parse_rdf, serialize_rdf


set_document_loader(any_document_loader)


def printerr(msg):
    print(msg, file=sys.stderr)


def process_source(source, args, ordered=True):
    context_ref = args.context

    base_iri = (
        args.base if args.base
        else f'file://{os.getcwd()}/' if source == '-'
        else f'file://{source}' if '://' not in source
        else source
    )

    try:
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

        if context_ref:
            if context_ref is True:
                context_ref = data
            elif isinstance(context_ref, str):
                context_ref = _absolutize(context_ref)

            result = compact(context_ref, result, base_iri, ordered=ordered)

            if isinstance(context_ref, dict) and CONTEXT in context_ref:
                result[CONTEXT] = context_ref[CONTEXT]

        serialize_rdf(result, args.output_format)

    except Exception as e:
        printerr(f"Error in file '{source}'")
        import traceback
        traceback.print_exc()


def _absolutize(context_ref: str) -> str:
    if '://' not in context_ref and os.path.exists(context_ref):
        return os.path.abspath(context_ref)
    else:
        return context_ref


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', metavar='SOURCE', nargs='*')
    argparser.add_argument('-c', '--context', help='Use to compact expanded JSON-LD', const=True, nargs='?')
    argparser.add_argument('-e', '--expand-context', const=True, nargs='?',
                        help='Use to expand plain JSON to JSON-LD')
    argparser.add_argument('-b', '--base',
                        help='Set the base IRI (default is current source)')
    argparser.add_argument('-f', '--flatten', action='store_true')
    argparser.add_argument('-i', '--input-format', help='Set RDF input format')
    argparser.add_argument('-o', '--output-format', help='Set RDF output format')

    args = argparser.parse_args()

    sources = args.source or ['-']

    for source in sources:
        if len(sources) > 1:
            printerr(f"Parsing file: '{source}'")

        process_source(source, args)


if __name__ == '__main__':
    main()
