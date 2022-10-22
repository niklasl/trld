import argparse
import json
import sys
from typing import Any

from .platform.common import json_encode
from .platform.io import Input, Output
from .jsonld.compaction import compact
from .jsonld.expansion import expand
from .jsonld.flattening import flatten
from .mimetypes import SUFFIX_MIME_TYPE_MAP


TURTLE_OR_TRIG = {SUFFIX_MIME_TYPE_MAP[s] for s in ['trig', 'ttl']}
NT_OR_NQ = {SUFFIX_MIME_TYPE_MAP[s] for s in ['nt', 'nq']}


def printerr(msg):
    print(msg, file=sys.stderr)


def parse_rdf(source, fmt):
    headers = {}
    accept = SUFFIX_MIME_TYPE_MAP.get(fmt, fmt)
    if accept:
        headers['Accept'] = accept

    inp = Input(None if source == '-' else source, headers)

    if inp.content_type in TURTLE_OR_TRIG:
        from .trig import parser as trig
        return trig.parse(inp)

    if inp.content_type in NT_OR_NQ:
        from .nq import parser as nq
        return nq.parse(inp)

    return inp.load_json()


def serialize_rdf(result, fmt):
    if fmt is None or fmt == 'jsonld':
        print(json_encode(result, pretty=True))
        return

    out = Output(sys.stdout)
    if fmt in {'trig', 'ttl', 'turtle', 'turtle-union'}:
        from .trig import serializer as trig
        if fmt == 'trig':
            trig.serialize(result, out)
        else:
            trig.serialize_turtle(result, out, union=fmt == 'turtle-union')
    else:
        from .jsonld.rdf import to_rdf_dataset
        dataset = to_rdf_dataset(result)
        if fmt == 'nq':
            from .nq import serializer as nq
            nq.serialize(dataset, out)
        else:
            print(json.dumps(dataset, indent=2,
                             default=lambda o: o.__dict__))


def process_source(source, context_ref, args, ordered=True):
    base_iri = (
        args.base if args.base
        else f'file:///dev/stdin' if source == '-'
        else f'file://{source}' if '://' not in source
        else source
    )

    try:
        data = parse_rdf(source, args.input_format)

        if args.expand_context:
            expand_context = (
                None if args.expand_context == True else args.expand_context
            )
            result: Any = expand(data, base_iri, expand_context, ordered=ordered)
        else:
            result = data

        if args.flatten or args.output_format in {'nq', True}:
            result = flatten(result, ordered=ordered)

        if context_ref:
            result = compact(context_ref, result, base_iri, ordered=ordered)

        serialize_rdf(result, args.output_format)

    except Exception as e:
        printerr(f"Error in file '{source}'")
        import traceback
        traceback.print_exc()


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', metavar='SOURCE', nargs='*')
    argparser.add_argument('-c', '--context', help='Use to compact expanded JSON-LD')
    argparser.add_argument('-e', '--expand-context', const=True, nargs='?',
                        help='Use to expand plain JSON to JSON-LD')
    argparser.add_argument('-b', '--base',
                        help='Set the base IRI (default is current source)')
    argparser.add_argument('-f', '--flatten', action='store_true')
    argparser.add_argument('-i', '--input-format', help='Set RDF input format')
    argparser.add_argument('-o', '--output-format', help='Set RDF output format')

    args = argparser.parse_args()

    context_ref = args.context

    sources = args.source or ['-']

    for source in sources:
        if len(sources) > 1:
            printerr(f"Parsing file: '{source}'")

        process_source(source, context_ref, args)


if __name__ == '__main__':
    main()
