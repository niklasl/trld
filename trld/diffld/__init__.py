from typing import Any, List, Dict, Iterable, NamedTuple, Optional, cast
import re

from ..common import dump_json, parse_json
from ..jsonld.base import CONTEXT, GRAPH, ID, TYPE, VALUE, LIST, SET
#CONTEXT = '@context'
#GRAPH = '@graph'
#ID = '@id'
#TYPE = '@type'
#VALUE = '@value'
#LIST = '@list'
#SET = '@set'
ANNOTATION = '@annotation'


GEN_BNODE_PFX = '_:diffnode-'
CLEAN_BNODE = re.compile(r'[^A-Za-z0-9-_]')

DIFF_CONTEXT = {
        "nodemap": {"@id": "@graph", "@container": "@id"},
        "diffs": {"@id": "diffs", "@container": ["@graph", "@id"]},
    }

CHANGESET_CONTEXT = dict(DIFF_CONTEXT, **{
    'diff': 'https://niklasl.github.io/diff-id/ns#',
})


class DiffResult(NamedTuple):
    in_both: List
    in_a: Dict
    in_b: Dict


def clone(o: object):
    return parse_json(dump_json(o))


def some_id(node: Dict, path: List[str]) -> str:
    if ID not in node:
        clean_path = [CLEAN_BNODE.sub('', s) for s in path]
        node[ID] = f"{GEN_BNODE_PFX}{'-'.join(clean_path)}"

    return cast(str, node[ID])


def make_changeset(graphs: List[Dict]) -> Dict:
    context = cast(Dict, graphs[0]).get(CONTEXT)
    seq: List[Dict] = []
    result = [
        {ID: "changeset", TYPE: 'diff:GraphChangeSet', 'diff:graphSequence': {LIST: seq}}
    ]

    def add_change(gid, added, itemmap, initial=None):
        changeid = gid + (';removed' if not added else ';added')
        seq.append({ID: changeid})
        result.append({
            ID: changeid,
            TYPE: 'diff:NegativeGraph' if not added else 'diff:Graph',
            GRAPH: (initial or []) + list(node
                for node in itemmap.values()
                if ID not in node or len(node) > 1),
        })

    for i, (a, b) in enumerate(zip(graphs[0:-1], graphs[1:])):
        diff = diff_graphs(a, b)

        if i == 0:
            add_change(a[ID], True, diff.in_a, diff.in_both)

        add_change(b[ID], True, diff.in_b)
        add_change(b[ID], False, diff.in_a)

    return {
        CONTEXT: context,
        GRAPH: result,
    }


def make_annotated(graphs: List[Dict]) -> Dict:
    context = cast(Dict, graphs[0]).get(CONTEXT)

    merged: Dict[str, object] = {}

    def annotate_values(annot, nodes):
        for node in nodes:
            if ID in node and len(node) == 1:
                continue

            mnode = merged.setdefault(node[ID], {})
            for key, value in node.items():
                if key == ID:
                    mnode[ID] = value
                    continue

                values = _aslist(mnode.get(key))
                for value in _aslist(value):
                    current = None

                    if not isinstance(value, Dict):
                        vkey = SET if key == TYPE else VALUE
                        for some in values:
                            if isinstance(some, Dict) and some.get(vkey) == value:
                                current = some

                        if current is None:
                            value = {vkey: value}
                            values.append(value)
                        else:
                            value = current
                    else:
                        if ID in value:
                            for some in values:
                                if isinstance(some, Dict) and some.get(ID) == value[ID]:
                                    current = some
                        if current is None:
                            value = dict(value)
                            values.append(value)
                        else:
                            value = current

                    existing_annot = value.setdefault(ANNOTATION, {})
                    # TODO: to avoid overwriting existing changes (due to bug below)
                    new_annot = dict(annot)
                    new_annot.update(existing_annot)
                    existing_annot.update(new_annot)
                    # TODO: fix regular diff of sets (shows as remove then re-add)
                    if existing_annot.get('removedIn') == existing_annot.get('addedIn'):
                        existing_annot.pop('removedIn', None)

                mnode[key] = values


    for i, (a, b) in enumerate(zip(graphs[0:-1], graphs[1:])):
        diff = diff_graphs(a, b)

        if i == 0:
            annotate_values({'addedIn': {ID: a[ID]}},
                            diff.in_both + list(diff.in_a.values()))

        annotate_values({'addedIn': {ID: b[ID]}}, diff.in_b.values())
        annotate_values({'removedIn': {ID: b[ID]}}, diff.in_a.values())

    nodes = list(v for k, v in merged.items() if not k.startswith(GEN_BNODE_PFX))
    turtlify(nodes, merged)

    return {
        CONTEXT: context,
        GRAPH: nodes,
    }


def make_diff(a: Dict, b: Dict) -> Dict:
    a_id = cast(str, a.get(ID, '_:diffgraph-a'))
    b_id = cast(str, b.get(ID, '_:diffgraph-b'))

    diff = diff_graphs(a, b)

    given_context: Optional[object] = a.get(CONTEXT)
    assert given_context == b.get(CONTEXT)

    context: object = DIFF_CONTEXT
    if given_context:
        if not isinstance(given_context, List):
            given_context = [given_context]
        context = given_context + [DIFF_CONTEXT]

    return {
        CONTEXT: context,
        "nodemap": to_nodemap(diff.in_both),
        "diffs": {
            a_id: {
                "nodemap": to_nodemap(diff.in_a.values())
            },
            b_id: {
                "nodemap": to_nodemap(diff.in_b.values())
            }
        }
    }


def diff_graphs(a: Dict, b: Dict) -> DiffResult:
    # FIXME: fix mutation below!
    a = clone(a)
    b = clone(b)

    diff = DiffResult(a[GRAPH], {}, {})
    _diff_nodes(diff, a, b)

    return diff


def _diff_nodes(result, a_node: object, b_node: object, path: List = None) -> bool:
    path = [] if path is None else path + []
    equal = True

    if isinstance(a_node, List):
        if not isinstance(b_node, List):
            return False

        for i in range(max(len(a_node), len(b_node))):
            i_path = path + [str(i)]
            if i >= len(b_node):
                child = a_node[i]
                child_id = some_id(child, i_path)
                result.in_a.setdefault(child_id, child)
                a_node[i] = {ID: child_id}
            elif i >= len(a_node):
                child = b_node[i]
                child_id = some_id(child, i_path)
                result.in_b.setdefault(child_id, child)
                b_node[i] = {ID: child_id}
                # TODO: at least handle lists differently (no "schroedinger members")
                #if not is_list(context, path[-1]):
                a_node.append({ID: child_id})
                #else:
                #equal = False
            else:
                a_child = a_node[i]
                b_child = b_node[i]
                if not _diff_nodes(result, a_child, b_child, i_path):
                    equal = False

    elif isinstance(a_node, Dict):
        if not isinstance(b_node, Dict):
            return False

        a_node_diff_added = False
        b_node_diff_added = False

        a_nid = some_id(a_node, path)
        a_node_diff = cast(Dict, result.in_a.setdefault(a_nid, {ID: a_nid}))

        b_nid = some_id(b_node, path)
        b_node_diff = cast(Dict, result.in_b.setdefault(b_nid, {ID: b_nid}))

        # TODO: transpile this expression instead of the below manoeuvre
        #for key in sorted(set(a_node) | set(b_node)):
        node_keys = list(a_node.keys())
        node_keys += list(b_node.keys())
        node_keys.sort()
        prev_key = ''

        for key in node_keys:
            if key == prev_key: continue
            prev_key = key

            a_val: object
            b_val: object

            if key in a_node:
                a_val = a_node[key]
            else:
                equal = False

            if key in b_node:
                b_val = b_node[key]
            else:
                equal = False

            if equal:
                equal = _diff_nodes(result, a_val, b_val, path + [key])

            if not equal and key != ID and GRAPH not in a_node:
                if key in a_node:
                    a_node_diff[key] = a_node.pop(key)
                    a_node_diff_added = True
                if key in b_node:
                    b_node_diff[key] = b_node.pop(key)
                    b_node_diff_added = True

                equal = a_node.get(ID) == b_node.get(ID)

        if a_node_diff_added != b_node_diff_added and a_nid != b_nid:
            if not a_node_diff_added:
                result.in_a[b_nid] = {ID: a_nid}
                a_node_diff_added = True
            if not b_node_diff_added:
                result.in_b[a_nid] = {ID: b_nid}
                b_node_diff_added = True

        if not b_node_diff_added and a_nid.startswith(GEN_BNODE_PFX):
            if not a_node_diff_added:
                _reembed(a_node, result.in_a)
            equal = True

        if not a_node_diff_added and b_nid.startswith(GEN_BNODE_PFX):
            if not b_node_diff_added:
                _reembed(b_node, result.in_b)
            equal = True

    else:
        return a_node == b_node

    return equal


def _reembed(node: Dict, map: Dict):
    copy = cast(Dict, map.pop(node[ID]))
    node.update(copy)
    node.pop(ID)


def to_nodemap(nodes: Iterable[Dict]) -> Dict:
    # TODO: transpile dict comprehension doesn't infer types and methods properly
    #return {node.pop(ID): node for node in nodes if len(node) > 1}
    nodemap = {}
    for node in nodes:
        if len(node) > 1:
            nodemap[node.pop(ID)] = node

    return nodemap


def turtlify(o, nodemap):
    if isinstance(o, List):
        for x in o:
            turtlify(x, nodemap)

    if not isinstance(o, Dict):
        return

    for y in o.values():
        turtlify(y, nodemap)

    if ID in o and o[ID].startswith(GEN_BNODE_PFX):
        _reembed(o, nodemap)


def _aslist(o: object):
    return o if isinstance(o, List) else [] if o is None  else [o]
