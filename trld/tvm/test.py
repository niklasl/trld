import json
from ..jsonld.expansion import expand
from ..jsonld.compaction import compact
from .mapmaker import make_target_map
from .mapper import map_to


DEBUG = False


context = {
    "@context": {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "dc": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "schema": "http://schema.org/",
        "bf": "http://id.loc.gov/ontologies/bibframe/",
        "lcrel": "http://id.loc.gov/vocabulary/relators/"
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

    check(given, expect, target, assuming)


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

    check(given, expect, target, assuming)


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

    check(given, expect, target, assuming)


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

    check(given, expect, target, assuming)


def check(given, expect, target, assuming):
    vocab = expand(dict(context, **assuming), "")
    target_map = make_target_map(expand(vocab, ""), {"@context": target})
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
