import argparse
from ..common import load_json, dump_json
from . import *


def name_graph(data, iri):
    if GRAPH in data and ID not in data:
        data[ID] = iri


argparser = argparse.ArgumentParser()
argparser.add_argument('version_a')
argparser.add_argument('version_b')
argparser.add_argument('-C', '--no-context', action='store_true')
argparser.add_argument('-i', '--embed-instance', action='store_true')

args = argparser.parse_args()

a_data = load_json(args.version_a)
b_data = load_json(args.version_b)

name_graph(a_data, args.version_a)
name_graph(b_data, args.version_b)

if args.embed_instance:
    # Move local work into instance as a bnode:
    if len(a_data[GRAPH]) > 2 and 'instanceOf' in a_data[GRAPH][1]:
        ref_id = a_data[GRAPH][1]['instanceOf'].get(ID)
        if ref_id == a_data[GRAPH][2].get(ID):
            a_data[GRAPH][1]['instanceOf'] = a_data[GRAPH].pop(2)
            a_data[GRAPH][1]['instanceOf'].pop(ID)

diffresult = diffld(a_data, b_data)

if args.no_context:
    diffresult.pop(CONTEXT)

s = dump_json(diffresult, pretty=True)
s = re.sub(r'{\s+(\S+: "[^"]*")\s+}', r'{\1}', s)
print(s)
