import argparse
import re
from ..common import load_json, dump_json
from . import CONTEXT, GRAPH, ID, TYPE,  make_diff, make_changeset, make_annotated


def load_as_graph(docpath, embed_instance=False):
    data = load_json(docpath)

    if GRAPH not in data:
        data = {GRAPH: [data]}

    if ID not in data:
        data[ID] = docpath.rsplit('.', 1)[0]

    if embed_instance:
        # Move local work into instance as a bnode:
        if len(data[GRAPH]) > 2 and 'instanceOf' in data[GRAPH][1]:
            ref_id = data[GRAPH][1]['instanceOf'].get(ID)
            if ref_id == data[GRAPH][2].get(ID):
                data[GRAPH][1]['instanceOf'] = data[GRAPH].pop(2)
                data[GRAPH][1]['instanceOf'].pop(ID)

    return data


argparser = argparse.ArgumentParser()
argparser.add_argument('first_version')
argparser.add_argument('version', nargs='+')
argparser.add_argument('-c', '--changeset', action='store_true')
argparser.add_argument('-a', '--annotated', action='store_true')
argparser.add_argument('-C', '--no-context', action='store_true')
argparser.add_argument('-i', '--embed-instance', action='store_true')

args = argparser.parse_args()

assert not args.changeset or not args.annotated

graphs = [load_as_graph(docpath, args.embed_instance)
            for docpath in [args.first_version] + args.version]

if args.annotated:
    diffresult = make_annotated(graphs)
    records = []
    for g in graphs:
        record = g[GRAPH][0]
        modified = record.get('modified')
        agent = record.get('descriptionLastModifier')
        if modified:
            version = {ID: g[ID], TYPE: 'Record', 'modified': modified, 'agent': agent}
            records.append(version)

    if records:
        diffresult[GRAPH] = records + diffresult[GRAPH]


elif len(graphs) == 2 and not args.changeset:
    diffresult = make_diff(graphs[0], graphs[1])
else:
    diffresult = make_changeset(graphs)

if args.no_context and CONTEXT in diffresult:
    diffresult.pop(CONTEXT)

s = dump_json(diffresult, pretty=True)
s = re.sub(r'{\s+(\S+: "[^"]*")\s+}', r'{\1}', s)
print(s)
