from io import StringIO
from textwrap import dedent

import trld.api

TESTS = [
    (
        {
            "@context": {
                "@vocab": "http://example.org/ns#",
                "termComponentList": {"@container": "@list"}
            },
            "@graph": [
                {
                    "@id": "http://example.org/text/1",
                    "@type": "Text",
                    "subject": [
                        {"@id": "https://example.org/Other"},
                        {
                            "@type": "ComplexSubject",
                            "termComponentList": [
                                {"@id": "https://example.org/Something"},
                                {"@id": "https://example.org/aspect"}
                            ]
                        },
                        {
                            "@type": "ComplexSubject",
                            "termComponentList": [
                                {"@type": "Topic", "prefLabel": "Education"},
                                {"@type": "TopicSubdivision", "prefLabel": "Research"}
                            ]
                        },
                        {
                            "@type": "ComplexSubject",
                            "termComponentList": [
                                {
                                    "@type": "ComplexSubject",
                                    "termComponentList": [
                                        {"@type": "Topic", "prefLabel": "Extra"},
                                        {"@type": "Topic", "prefLabel": "Extra"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        """
        prefix : <http://example.org/ns#>

        <http://example.org/text/1> a :Text ;
          :subject <https://example.org/Other> ,
            [ a :ComplexSubject ;
              :termComponentList ( <https://example.org/Something> <https://example.org/aspect> ) ] ,
            [ a :ComplexSubject ;
              :termComponentList ( [ a :Topic ;
                  :prefLabel "Education" ] [ a :TopicSubdivision ;
                  :prefLabel "Research" ] ) ] ,
            [ a :ComplexSubject ;
              :termComponentList ( [ a :ComplexSubject ;
                  :termComponentList ( [ a :Topic ;
                      :prefLabel "Extra" ] [ a :Topic ;
                      :prefLabel "Extra" ] ) ] ) ] .
        """
    )
]


def run_tests():
    for indata, expected in TESTS:
        out = StringIO()
        trld.api.serialize_rdf(indata, 'ttl', out)
        outdata = out.getvalue()
        expected = dedent(expected).strip() + '\n'

        assert outdata == expected


if __name__ == '__main__':
    run_tests()
