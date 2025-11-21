from trld.jsonld.keys import ID, REVERSE
from trld.jsonld.extras.index import make_index

g1 = [
    {
        ID: "a",
        "references": {ID: "b"}
    },
    {
        ID: "b",
        "references": {ID: "a"}
    }
]


def test_g1_simple_index():
    idx = make_index(g1, add_reverses=False)

    assert idx == {
        "a": {
            ID: "a",
            "references": {ID: "b"}
        },
        "b": {
            ID: "b",
            "references": {ID: "a"}
        }
    }


def test_g1_index_with_reverses():
    idx = make_index(g1, add_reverses=True)

    assert idx == {
        "a": {
            ID: "a",
            "references": {ID: "b"},
            REVERSE: {"references": [{ID: "b"}]}
        },
        "b": {
            ID: "b",
            "references": {ID: "a"},
            REVERSE: {"references": [{ID: "a"}]}
        }
    }


def test_index_with_undescribed():
    g = [
        {
            ID: "a",
            "references": {ID: "c"}
        },
        {
            ID: "b",
            "references": {ID: "c"}
        }
    ]

    idx = make_index(g)

    assert idx == {
        "a": {
            ID: "a",
            "references": {ID: "c"}
        },
        "b": {
            ID: "b",
            "references": {ID: "c"}
        },
        "c": {
            ID: "c",
            REVERSE: {"references": [{ID: "a"}, {ID: "b"}]}
        }
    }
