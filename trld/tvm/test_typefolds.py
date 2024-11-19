import json
from pathlib import Path

from ..api import parse_rdf, text_input
from ..jsonld.keys import GRAPH, ID, TYPE, VOCAB
from .typefolds import make_fold_target_map, make_tbox_equivalency_map
from .typefolds import fold_type, unfold_type
from .test import assert_json_equals

tbox = """
gf:Newspaper skos:broader gf:Periodical .

[] owl:equivalentClass sdo:Periodical ;
    owl:intersectionOf (
            bf:Serial
            [ a owl:Restriction ;
                owl:onProperty bf:genreForm ;
                owl:hasValue gf:Periodical ]
        ) .

[] owl:equivalentClass sdo:PublicationIssue ;
    owl:intersectionOf (
            bf:Text
            [ a owl:Restriction ;
                owl:onProperty bf:genreForm ;
                owl:hasValue gf:Periodical ]
        ) .
"""

expected_matchpattern_orderedprop_tree = {
    'matchByType': {
        'bf:Serial': {
            'matchByPredicate': {
                'bf:genreForm': {
                    'byId': {'gf:Periodical': {'targetClass': 'sdo:Periodical'}}
                }
            }
        },
        "bf:Text": {
            "matchByPredicate": {
                "bf:genreForm": {
                    "byId": {"gf:Periodical": {"targetClass": "sdo:PublicationIssue"}}
                }
            }
        },
    }
}


def test_make_fold_target_map():
    assuming = parse_rdf(text_input(tbox))
    target = {"@vocab": "sdo:"}

    matchpattern_orderedprop_tree, transitivebases = make_fold_target_map(
        assuming, target
    )

    print("test_make_fold_target_map:")
    assert_json_equals(
        matchpattern_orderedprop_tree, expected_matchpattern_orderedprop_tree
    )
    print()


def test_typefolds():
    dataset = _load("test-typefolds.trig")
    tbox = None
    aboxes = {}

    target = {"@vocab": "sdo:"}

    for graph in dataset[GRAPH]:
        if graph[ID] == 'tbox':
            tbox = graph
        else:
            name, leaf = graph[ID].rsplit('/', 1)
            aboxes.setdefault(name, {})[leaf] = graph

    matchpattern_orderedprop_tree, transitivebases = make_fold_target_map(
        tbox, target
    )
    #print(json.dumps(matchpattern_orderedprop_tree, indent=2))

    tbox_map = make_tbox_equivalency_map(tbox)

    for name, boxmap in aboxes.items():
        print("Test", name)
        given = boxmap['exp']
        expect = boxmap['cmp']

        folded = [
            fold_type(
                matchpattern_orderedprop_tree, transitivebases, target[VOCAB], obj, True
            )
            for obj in given[GRAPH]
        ]

        assert_json_equals(folded, expect[GRAPH])
        print()

        unfolded = [
            unfold_type(tbox_map, transitivebases, target[VOCAB], obj)
            for obj in folded
        ]

        try:
            assert_json_equals(unfolded, given[GRAPH])
        except AssertionError as e:
            print("Failed unfold:")
            print(e)

        print()



def _load(pth):
    data = parse_rdf(str((Path(__file__).parent / pth).absolute()))
    #return expand(data, None)
    return data


if __name__ == '__main__':
    test_make_fold_target_map()
    test_typefolds()
