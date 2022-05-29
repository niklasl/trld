import argparse
import json
import sys
from typing import Any

from .common import Input, Output, dump_json, load_json
from .jsonld.compaction import compact
from .jsonld.expansion import expand
from .jsonld.flattening import flatten
from .mimetypes import SUFFIX_MIME_TYPE_MAP


def eprint(msg):
    print(msg, file=sys.stderr)


def parse_rdf(source, fmt):
    headers = {}
    accept = SUFFIX_MIME_TYPE_MAP.get(fmt)
    if accept:
        headers['Accept'] = accept

    inp = Input(None if source == '-' else source, headers)

    # TODO: Use inp.content_type (which uses guess_mime_type)?
    # So instead of using suffixes or "names" below, check mime-type (accept).
    if fmt is None and isinstance(source, str):
        fmt = source.rsplit('.', 1)[-1]

    if fmt in {'trig', 'ttl', 'turtle'}:
        from .trig import parser as trig
        return trig.parse(inp)

    if fmt in {'nq', 'nt'}:
        from .nq import parser as nq
        return nq.parse(inp)

    return load_json(inp)


def serialize_rdf(result, fmt):
    if fmt is None or fmt == 'jsonld':
        print(dump_json(result, pretty=True))
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


def process_source(source, context_data, args, ordered=True):
    base_iri = (
        args.base if args.base
        else f'file:///dev/stdin' if source == '-'
        else f'file://{source}'
    )

    try:
        data = parse_rdf(source, args.input)

        if args.expand_context:
            expand_context = (
                None if args.expand_context == True else args.expand_context
            )
            result: Any = expand(data, base_iri, expand_context, ordered=ordered)
        else:
            result = data

        if args.flatten or args.output in {'nq', True}:
            result = flatten(result, ordered=ordered)
        if context_data:
            result = compact(context_data, result, base_iri, ordered=ordered)

        serialize_rdf(result, args.output)

    except Exception as e:
        eprint(f"Error in file '{source}'")
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

    context_data = None
    if args.context:
        context_data = load_json(args.context)

    sources = args.source or ['-']

    for source in sources:
        if len(sources) > 1:
            eprint(f"Parsing file: '{source}'")

        process_source(source, context_data, args)


if __name__ == '__main__':
    main()
