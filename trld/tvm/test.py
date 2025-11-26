from typing import Dict, List, cast
from ..platform.common import json_encode
from ..jsonld.base import JsonMap, JsonObject
from ..jsonld.keys import CONTEXT, GRAPH, ID
from ..jsonld.expansion import expand
from ..jsonld.flattening import flatten
from ..jsonld.compaction import compact
from ..jsonld.extras.index import make_index
from .mapmaker import make_target_map, leads_to
from .mapper import map_to


DEBUG = False


context = {
    "@context": {
        "ex": "http://example.org/ns#",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "bibo": "http://purl.org/ontology/bibo/",
        "dc": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "schema": "http://schema.org/",
        "bf": "http://id.loc.gov/ontologies/bibframe/",
        "lcrel": "http://id.loc.gov/vocabulary/relators/",
        "edtf": "http://id.loc.gov/datatypes/edtf/"
    }
}


def test_make_target_map() -> None:
    vocab = {
        "@graph": [
            {
                "@id": "foaf:Document",
                "rdfs:subClassOf": {"@id": "rdfs:Resource"}
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {"@id": "rdfs:label"}
            }
        ]
    }
    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}
    expect = {
        "http://xmlns.com/foaf/0.1/Document": [
            "http://www.w3.org/2000/01/rdf-schema#Resource"
        ],
        "http://purl.org/dc/terms/title": [
            "http://www.w3.org/2000/01/rdf-schema#label"
        ],
        "http://www.w3.org/2000/01/rdf-schema#Resource": "http://www.w3.org/2000/01/rdf-schema#Resource",
        "http://www.w3.org/2000/01/rdf-schema#label": "http://www.w3.org/2000/01/rdf-schema#label",
    }
    flat_vocab = _flat_graph(context, vocab)
    target_map: Dict = make_target_map(flat_vocab, {CONTEXT: target})
    assert_json_equals(target_map, expect)


def test_make_target_map_from_target_terms() -> None:
    vocab = {
        "@graph": [
            {
                "@id": "rdfs:Resource",
                "@type": "rdfs:Class"
            },
            {
                "@id": "rdfs:label",
                "@type": "rdf:Property"
            },
            {
                "@id": "ex:other",
                "@type": "rdf:Property"
            }
        ]
    }
    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}
    expect = {
        "http://www.w3.org/2000/01/rdf-schema#Resource": "http://www.w3.org/2000/01/rdf-schema#Resource",
        "http://www.w3.org/2000/01/rdf-schema#label": "http://www.w3.org/2000/01/rdf-schema#label",
    }
    flat_vocab = _flat_graph(context, vocab)
    target_map: Dict = make_target_map(flat_vocab, {CONTEXT: target})
    assert_json_equals(target_map, expect)


def test_cope_with_circular_references():
    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}

    assuming = {
        "@graph": [
            {
                "@id": "owl:Thing",
                "rdfs:subClassOf": {"@id": "skos:Concept"}
            },
            {
                "@id": "skos:Concept",
                "rdfs:subClassOf": {"@id": "owl:Thing"}
            }
        ]
    }

    _to_target_map(target, assuming)

    print_ok()


def test_reducing_foaf_to_rdfs():
    given = {
        "@id": "",
        "@type": "foaf:Document",
        "dc:title": "A"
    }

    expect = {
        "@id": "",
        "@type": "rdfs:Resource",
        "rdfs:label": "A"
    }

    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}

    assuming = {
        "@graph": [
            {
                "@id": "foaf:Document",
                "rdfs:subClassOf": {"@id": "rdfs:Resource"}
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {"@id": "rdfs:label"}
            }
        ]
    }

    check(given, target, expect, assuming)


def test_remap_datatypes():
    given = {
        "@id": "",
        "dc:issued": {"@type": "2021", "@type": "xsd:year"}
    }

    expect = {
        "@id": "",
        "dc:issued": {"@type": "2021", "@type": "edtf:EDTF-level0"}
    }

    target = {
        "dc": "http://purl.org/dc/terms/",
        "edtf": "http://id.loc.gov/datatypes/edtf/"
    }

    assuming = {
        "@graph": [
            {
                "@id": "xsd:year",
                "rdfs:subClassOf": [
                    {"@id": "edtf:EDTF-level0"}
                ]
            }
        ]
    }

    check(given, target, expect, assuming)


def test_structured_values_and_shorthand_properties():
    given = {
        "@id": "/instance/a",
        "bf:identifiedBy": {
            "@type": "bf:Isbn",
            "rdf:value": "12-3456-789-0"
        }
    }

    target = {"@vocab": "http://schema.org/"}

    expect = {
        "@id": "/instance/a",
        "schema:isbn": "12-3456-789-0"
    }

    assuming = {
        "@graph": [
            {
                "@id": "schema:isbn",
                "owl:propertyChainAxiom": {
                    "@list": [
                        {
                            "rdfs:subPropertyOf": {"@id": "bf:identifiedBy"},
                            "rdfs:range": {"@id": "bf:Isbn"}
                        },
                        {"@id": "rdf:value"}
                    ]
                }
            }
        ]
    }

    check(given, target, expect, assuming)


def test_qualified_relations_as_reifications():
    given = {
        "@id": "/work",
        "bf:contribution": {
            "bf:agent": {"@id": "/person/a"},
            "bf:role": {"@id": "lcrel:ill"}
        }
    }

    target = {"@vocab": "http://purl.org/dc/terms/"}

    expect = {
        "@id": "/work",
        "dc:contributor": {"@id": "/person/a"}
    }

    assuming = {
        "@graph": [
            {
                "@id": "bf:Contribution",
                "rdfs:subClassOf": [
                    {"@id": "rdf:Statement"},
                    #{
                    #    "owl:onProperty": {"@id": "rdf:predicate"},
                    #    "owl:hasValue": {"@id": "dc:contributor"}
                    #}
                ]
            },
            {
                "@id": "bf:contribution",
                "rdfs:range": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {
                    "owl:inverseOf": {"@id": "rdf:subject"}
                }
            },
            {
                "@id": "bf:role",
                "rdfs:domain": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {"@id": "rdf:predicate"}
            },
            {
                "@id": "bf:agent",
                "rdfs:domain": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {"@id": "rdf:object"}
            },
            {
                "@id": "lcrel:ill",
                "rdfs:subPropertyOf": {"@id": "dc:contributor"}
            }
        ]
    }

    check(given, target, expect, assuming)


def test_inferred_qualified_relations_as_reifications():
    given = {
        "@id": "/work",
        "bf:contribution": {
            "bf:agent": {"@id": "/person/a"},
            "bf:role": {"@id": "lcrel:ill"}
        }
    }

    target = {"@vocab": "http://purl.org/dc/terms/"}

    expect = {
        "@id": "/work",
        "dc:contributor": {"@id": "/person/a"}
    }

    assuming = {
        "@graph": [
            {
                "@id": "ex:QualifiedEvent",
                "rdfs:subClassOf": [
                    {"@id": "rdf:Statement"}
                ]
            },
            {
                "@id": "ex:subject",
                "rdfs:subPropertyOf": {"@id": "rdf:subject"}
            },
            {
                "@id": "ex:role",
                "rdfs:subPropertyOf": {"@id": "rdf:predicate"}
            },
            {
                "@id": "ex:object",
                "rdfs:subPropertyOf": {"@id": "rdf:object"}
            },

            {
                "@id": "ex:hasStatement",
                "rdfs:subPropertyOf": {
                    "owl:inverseOf": {"@id": "ex:subject"}
                }
            },

            {
                "@id": "bf:Contribution",
                "rdfs:subClassOf": [
                    {"@id": "ex:QualifiedEvent"}
                ]
            },
            {
                "@id": "bf:contribution",
                "rdfs:range": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {"@id": "ex:hasStatement"}
            },
            {
                "@id": "bf:role",
                "rdfs:domain": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {"@id": "ex:role"}
            },
            {
                "@id": "bf:agent",
                "rdfs:domain": {"@id": "bf:Contribution"},
                "rdfs:subPropertyOf": {"@id": "ex:object"}
            },
            {
                "@id": "lcrel:ill",
                "rdfs:subPropertyOf": {"@id": "dc:contributor"}
            }
        ]
    }

    check(given, target, expect, assuming)


def test_property_chains_for_events():
    given = {
        "@id": "/instance/a",
        "bf:provisionActivity": {
            "@type": "bf:Publication",
            "bf:agent": {"@id": "/org/a"},
            "bf:date": "2017"
        }
    }

    target = {"@vocab": "http://schema.org/"}

    expect = {
        "@id": "/instance/a",
        "schema:publisher": {"@id": "/org/a"},
        "schema:datePublished": "2017"
    }

    assuming = {
        "@graph": [
            {
                "@id": "schema:datePublished",
                "rdfs:subPropertyOf": {"@id": "dcterms:issued"},
                "owl:propertyChainAxiom": {
                    "@list": [
                        {
                            "rdfs:subPropertyOf": {"@id": "bf:provisionActivity"},
                            "rdfs:range": {"@id": "bf:Publication"}
                        },
                        {"@id": "bf:date"}
                    ]
                }
            },
            {
                "@id": "dcterms:publisher",
                "owl:equivalentProperty": {"@id": "schema:publisher"},
                "owl:propertyChainAxiom": {
                    "@list": [
                        {
                            "rdfs:subPropertyOf": {"@id": "bf:provisionActivity"},
                            "rdfs:range": {"@id": "bf:Publication"}
                        },
                        {"@id": "bf:agent"}
                    ]
                }
            }
        ]
    }

    check(given, target, expect, assuming)


def test_add_to_existing_key():
    given = {
        "@id": "",
        "dc:title": "Title",
        "foaf:name": "Name",
        "rdfs:label": "Label"
    }

    expect = {
        "@id": "",
        "rdfs:label": ["Title", "Name", "Label"]
    }

    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}

    assuming = {
        "@graph": [
            {
                "@id": "foaf:name",
                "rdfs:subPropertyOf": {"@id": "rdfs:label"}
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {"@id": "rdfs:label"}
            }
        ]
    }

    check(given, target, expect, assuming)


def test_only_add_most_specific() -> None:
    given = {
        "@id": "",
        "bf:identifiedBy": {
            "rdf:value": "0000000000"
        }
    }

    expect = {
        "@id": "",
        "bibo:identifier": "0000000000"
    }

    target: List = [
        {"bibo": "http://purl.org/ontology/bibo/"},
        {"dc": "http://purl.org/dc/terms/"},
        {"rdfs": "http://www.w3.org/2000/01/rdf-schema#"}
    ]

    assuming = {
        "@graph": [
            {
                "@id": "bibo:identifier",
                "rdfs:subPropertyOf": [{"@id": "dc:identifier"}, {"@id": "rdfs:label"}],
                "owl:propertyChainAxiom": {
                    "@list": [
                        {"@id": "bf:identifiedBy"},
                        {"@id": "rdf:value"}
                    ]
                }
            }
        ]
    }

    check(given, target, expect, assuming)


def test_sort_target_rules() -> None:
    vocab = {
        "@graph": [
            {
                "@id": "schema:identifier",
                #"rdfs:subPropertyOf": {"@id": "dc:identifier"},
                "owl:propertyChainAxiom": {
                    "@list": [
                        {"@id": "bf:identifiedBy"},
                        {"@id": "rdf:value"}
                    ]
                }
            },
            {
                "@id": "schema:isbn",
                "owl:propertyChainAxiom": {
                    "@list": [
                        {
                            "rdfs:subPropertyOf": {"@id": "bf:identifiedBy"},
                            "rdfs:range": {"@id": "bf:Isbn"}
                        },
                        {"@id": "rdf:value"}
                    ]
                }
            }
        ]
    }
    target: List = [
        {"@vocab": "http://schema.org/"},
        #{"@vocab": "http://purl.org/dc/terms/"}
    ]
    expect = {
        "http://id.loc.gov/ontologies/bibframe/identifiedBy": [
            {
                "match": {
                    "@type": "http://id.loc.gov/ontologies/bibframe/Isbn"
                },
                "property": "http://schema.org/isbn",
                "propertyFrom": None,
                "valueFrom": "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            },
            {
                "match": None,
                "property": "http://schema.org/identifier",
                "propertyFrom": None,
                "valueFrom": "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            }
        ],
        "http://schema.org/identifier": "http://schema.org/identifier",
        "http://schema.org/isbn": "http://schema.org/isbn"
    }

    flat_vocab = _flat_graph(context, vocab)
    target_map: Dict = make_target_map(flat_vocab, {CONTEXT: target})

    assert_json_equals(target_map, expect)



def test_keep_target_terms():
    given = {
        "@id": "",
        "@type": "rdfs:Resource",
        "rdfs:label": "A"
    }

    expect = given

    target = {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}

    assuming = {
        "@graph": [
            {
                "@id": "foaf:Document",
                "rdfs:subClassOf": {"@id": "rdfs:Resource"}
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {"@id": "rdfs:label"}
            }
        ]
    }

    check(given, target, expect, assuming)


def test_leads_to() -> None:
    r0 = {ID: "urn:x-test:0"}
    r1 = {ID: "urn:x-test:1"}
    r2 = {ID: "urn:x-test:2"}
    rel = "urn:x-test:rel"
    graph: List = [
        r0,
        dict(r1, **{rel: [r0]}),
        dict(r2, **{rel: [r1]})
    ]
    index: Dict = make_index(graph)
    assert leads_to(r0, index, rel, r0[ID])
    assert leads_to(r1, index, rel, r0[ID])
    assert leads_to(r2, index, rel, r0[ID])
    print_ok()


def check(given: Dict, target: JsonObject, expect: Dict, assuming: Dict) -> None:
    drop_unmapped = False
    target_map = _to_target_map(target, assuming)
    if DEBUG:
        print(_jsonstr(target_map))
    indata: JsonObject = expand(dict(context, **given), "")
    outdata: JsonObject = map_to(target_map, indata, drop_unmapped)
    outdata = compact(context, outdata)
    assert_json_equals(outdata, expect)


def assert_json_equals(given, expected) -> None:
    gvn = _jsonstr(given)
    exp = _jsonstr(expected)
    assert_equals(gvn, exp)


def assert_equals(given: str, expected: str) -> None:
    assert given == expected, f'Expected:\n{expected}\nGot:\n{given}'
    print_ok()


def print_ok() -> None:
    print('OK', end='')


def _flat_graph(context: Dict, graph: Dict) -> List:
    data = dict(context)
    data.update(graph)
    return flatten(expand(data, ""))


def _to_target_map(target: JsonObject, assuming: Dict) -> Dict:
    vocab = _flat_graph(context, assuming)
    return make_target_map(expand(vocab, ""), {CONTEXT: target})


def _jsonstr(data) -> str:
    return json_encode(data, pretty=True, sort_keys=True)


if __name__ == '__main__':
    from sys import argv

    args = []
    for arg in argv[1:]:
        if arg == '-d':
            DEBUG = True
        else:
            args.append(arg)

    for k, v in dict(globals()).items():
        if k.startswith('test_') and hasattr(v, '__call__'):
            if args and not any(k.endswith(arg) for arg in args):
                continue

            print(f'Running {k}:', end=' ')
            try:
                v()
            except AssertionError as e:
                print(str(e))
            else:
                print()
