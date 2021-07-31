from typing import List, Dict, Iterable, NamedTuple, cast
import re

#from ..jsonld.base import CONTEXT, GRAPH, ID, TYPE
CONTEXT = '@context'
GRAPH = '@graph'
ID = '@id'
TYPE = '@type'


GEN_BNODE_PFX = '_:diffnode-'
CLEAN_BNODE = re.compile(r'[^A-Za-z0-9-_]')


class DiffResult(NamedTuple):
    in_both: List
    in_a: Dict
    in_b: Dict


def some_id(node: Dict, path: List[str]) -> str:
    if ID not in node:
        clean_path = [CLEAN_BNODE.sub('', s) for s in path]
        node[ID] = f"{GEN_BNODE_PFX}{'-'.join(clean_path)}"

    return cast(str, node[ID])


def diffld(a: Dict, b: Dict) -> Dict:
    a_id = cast(str, a.get(ID, '_:diffgraph-a'))
    b_id = cast(str, b.get(ID, '_:diffgraph-b'))

    result = DiffResult(a[GRAPH], {}, {})
    diff_nodes(result, a, b)

    return {
        CONTEXT: {
            "@vocab": "https://id.kb.se/vocab/",
            "nodemap": {"@id": "@graph", "@container": "@id"},
            "diffs": {"@id": "diffs", "@container": ["@graph", "@id", "@set"]}
        },
        "nodemap": to_nodemap(result.in_both),
        "diffs": {
            a_id: {
                "nodemap": to_nodemap(result.in_a.values())
            },
            b_id: {
                "nodemap": to_nodemap(result.in_b.values())
            }
        }
    }


def diff_nodes(result, a_node: object, b_node: object, path: List = None) -> bool:
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
                if not diff_nodes(result, a_child, b_child, i_path):
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
                equal = diff_nodes(result, a_val, b_val, path + [key])

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
