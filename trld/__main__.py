from typing import Any
import json
import sys
import argparse

from .common import load_json, dump_json, Output
from .jsonld.expansion import expand
from .jsonld.compaction import compact
from .jsonld.flattening import flatten


def err(msg): print(msg, file=sys.stderr)


def serialize_rdf(result, fmt):
    out = Output(sys.stdout)
    if fmt in {'trig', 'turtle', 'turtle-union'}:
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


argparser = argparse.ArgumentParser()
argparser.add_argument('source', nargs='*')
argparser.add_argument('-c', '--context', help='Use to compact expanded JSON-LD')
argparser.add_argument('-e', '--expand-context', const=True, nargs='?', help='Use to expand plain JSON to JSON-LD')
argparser.add_argument('-b', '--base', help='Set the base IRI (default is current source)')
argparser.add_argument('-f', '--flatten', action='store_true')
argparser.add_argument('-o', '--output', help='Set RDF output format')
argparser.add_argument('-i', '--input', nargs='?', help='Set RDF input format')

args = argparser.parse_args()

context_data = None
if args.context:
    context_data = load_json(args.context)

doc_paths = args.source or ['-']

for doc_path in doc_paths:
    if len(doc_paths) > 1:
        err(f"Parsing file: '{doc_path}'")

    if doc_path == '-':
        doc_path = '/dev/stdin'
        data = json.load(sys.stdin)
    else:
        data = load_json(doc_path)

    ordered = True
    base_iri = args.base if args.base else f'file://{doc_path}'

    try:
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

        if args.output:
            serialize_rdf(result, args.output)
        else:
            print(dump_json(result, pretty=True))

    except Exception as e:
        err(f"Error in file '{doc_path}'")
        import traceback
        traceback.print_exc()
