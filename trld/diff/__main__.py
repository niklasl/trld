import argparse
import re

from ..common import dump_json, load_json
from ..jsonld.base import CONTEXT, GRAPH, ID
from . import Differ, DiffKeys

if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument('version', nargs='+')
    argparser.add_argument('-b', '--blame', action='store_true')
    argparser.add_argument('-C', '--no-context', action='store_true')
    argparser.add_argument('--version-type')
    argparser.add_argument('--version-prev')
    argparser.add_argument('--version-next')
    argparser.add_argument('--version-latest')
    args = argparser.parse_args()

    def load_as_named_graph(docpath):
        data = load_json(docpath)
        if GRAPH not in data:
            data = {GRAPH: [data]}
        if ID not in data:
            data[ID] = docpath.rsplit('.', 1)[0]
        return data

    graphs = [load_as_named_graph(docpath) for docpath in args.version]

    differ = Differ(
        args.blame,
        DiffKeys(
            v_type=args.version_type,
            v_prev=args.version_prev,
            v_next=args.version_next,
            v_latest=args.version_latest,
        ),
    )

    diffgraph = differ.diff(graphs)

    if args.no_context and CONTEXT in diffgraph:
        diffgraph.pop(CONTEXT)

    s = dump_json(diffgraph, pretty=True)
    s = re.sub(r'{\s+(\S+: "[^"]*")\s+}', r'{\1}', s)
    print(s)
