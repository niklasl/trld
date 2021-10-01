import json
from ..jsonld.expansion import expand
from ..jsonld.compaction import compact
from .mapmaker import make_target_map
from .mapper import map_to


DEBUG = False

null = None


context = {
    "@context": {
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


def test_make_target_map():
    vocab = {
        "@graph": [
            {
                "@id": "foaf:Document",
                "rdfs:subClassOf": {
                    "@id": "rdfs:Resource"
                }
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {
                    "@id": "rdfs:label"
                }
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
        ]
    }
    vocab = expand(dict(context, **vocab), "")
    target_map = make_target_map(vocab, {"@context": target})
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

    print('OK', end='')


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
                "rdfs:subClassOf": {
                    "@id": "rdfs:Resource"
                }
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {
                    "@id": "rdfs:label"
                }
            }
        ]
    }

    check(**locals())


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

    check(**locals())


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

    check(**locals())


def test_qualified_relations_as_reifications():
    given = {
        "@id": "/work",
        "bf:contribution": {
            "bf:agent": {
                "@id": "/person/a"
            },
            "bf:role": {
                "@id": "lcrel:ill"
            }
        }
    }

    target = {"@vocab": "http://purl.org/dc/terms/"}

    expect = {
        "@id": "/work",
        "dc:contributor": {
            "@id": "/person/a"
        }
    }

    assuming = {
        "@graph": [
            {
                "@id": "bf:Contribution",
                "rdfs:subClassOf": [
                    {"@id": "rdf:Statement"},
                    {
                        "owl:onProperty": {"@id": "rdf:predicate"},
                        "owl:hasValue": {"@id": "dc:contributor"}
                    }
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

    check(**locals())


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

    check(**locals())


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
                "rdfs:subPropertyOf": {
                    "@id": "rdfs:label"
                }
            },
            {
                "@id": "dc:title",
                "rdfs:subPropertyOf": {
                    "@id": "rdfs:label"
                }
            }
        ]
    }

    check(**locals())


def test_only_add_most_specific():
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

    target = [
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

    check(**locals())


def test_sort_target_rules():
    vocab = {
        "@graph": [
            {
                "@id": "schema:identifier",
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
    target = {"@vocab": "http://schema.org/"}
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
                "match": null,
                "property": "http://schema.org/identifier",
                "propertyFrom": null,
                "valueFrom": "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            }
        ]
    }
    vocab = expand(dict(context, **vocab), "")
    target_map = make_target_map(vocab, {"@context": target})
    assert_json_equals(target_map, expect)


def check(given, target, expect, assuming):
    target_map = _to_target_map(target, assuming)
    if DEBUG:
        print(_jsonstr(target_map))
    indata = expand(dict(context, **given), "")
    outdata = map_to(target_map, indata)
    outdata = compact(context, outdata)
    assert_json_equals(outdata, expect)


def assert_json_equals(given, expect):
    g = _jsonstr(given)
    e = _jsonstr(expect)
    assert g == e, f'Expected:\n{e}\nGot:\n{g}'
    print('OK', end='')


def _to_target_map(target, assuming):
    vocab = expand(dict(context, **assuming), "")
    return make_target_map(expand(vocab, ""), {"@context": target})


def _jsonstr(data):
    return json.dumps(data, indent=2, sort_keys=True)


if __name__ == '__main__':
    from sys import argv

    DEBUG = '-d' in argv

    for k, v in dict(globals()).items():
        if k.startswith('test_') and hasattr(v, '__call__'):
            print(f'Running {k}:', end=' ')
            try:
                v()
            except AssertionError as e:
                print(str(e))
            else:
                print()
