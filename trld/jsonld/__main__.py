from typing import Any
import json
import sys
import argparse
from .common import load_json
from .expansion import expand
from .compaction import compact
from .flattening import flatten


def err(msg): print(msg, file=sys.stderr)

argparser = argparse.ArgumentParser()
argparser.add_argument('source', nargs='+')
argparser.add_argument('-c', '--context')
argparser.add_argument('-b', '--base')
argparser.add_argument('-f', '--flatten', action='store_true')

args = argparser.parse_args()

context_data = None
if args.context:
    context_data = load_json(args.context)

for doc_path in args.source:
    if len(args.source) > 1:
        err(f"Parsing file: '{doc_path}'")
    if doc_path == '-':
        doc_path = '/dev/stdin'
        doc_data = json.load(sys.stdin)
    else:
        doc_data = load_json(doc_path)

    ordered = True
    base_iri = args.base if args.base else f'file://{doc_path}'

    try:
        result: Any = expand(doc_data, base_iri, ordered=ordered)
        if args.flatten:
            result = flatten(result, ordered=ordered)
        if context_data:
            result = compact(context_data, result, base_iri, ordered=ordered)


        print(json.dumps(result, indent=2))
    except Exception as e:
        err(f"Error in file '{doc_path}'")
        import traceback
        traceback.print_exc()
