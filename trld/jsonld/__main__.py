from typing import Any
import json
import sys
import argparse

from ..common import any_document_loader, dump_json
from .expansion import expand
from .compaction import compact
from .flattening import flatten


def err(msg): print(msg, file=sys.stderr)

argparser = argparse.ArgumentParser()
argparser.add_argument('source', nargs='*')
argparser.add_argument('-c', '--context', help='Use to compact expanded JSON-LD')
argparser.add_argument('-e', '--expand-context', help='Use to expand plain JSON to JSON-LD')
argparser.add_argument('-b', '--base', help='Set the base IRI (default is current source)')
argparser.add_argument('-f', '--flatten', action='store_true')

args = argparser.parse_args()

context_url = args.context

doc_paths = args.source or ['-']

for doc_path in doc_paths:
    if len(doc_paths) > 1:
        err(f"Parsing file: '{doc_path}'")

    if doc_path == '-':
        doc_path = '/dev/stdin'
        data = json.load(sys.stdin)
    else:
        data = any_document_loader(doc_path).load_json()

    ordered = True
    base_iri = args.base if args.base else f'file://{doc_path}'

    try:
        result: Any = expand(data, base_iri, args.expand_context, ordered=ordered)
        if args.flatten:
            result = flatten(result, ordered=ordered)
        if context_url:
            result = compact(context_url, result, base_iri, ordered=ordered)

        print(dump_json(result, pretty=True))
    except Exception as e:
        err(f"Error in file '{doc_path}'")
        import traceback
        traceback.print_exc()
