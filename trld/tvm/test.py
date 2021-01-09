import json
from .mapmaker import make_target_map
from .mapper import map_to


indata = {
    "@graph": [
        {
            "@id": "",
            "@type": ["http://xmlns.com/foaf/0.1/Document"],
            "http://purl.org/dc/terms/title": [{"@value": "A"}]
        }
    ]
}
vocab: dict = {
    "@graph": [
        {
            "@id": "http://xmlns.com/foaf/0.1/Document",
            "http://www.w3.org/2000/01/rdf-schema#subClassOf": [
            {"@id": "http://www.w3.org/2000/01/rdf-schema#Resource"}
            ]
        },
        {
            "@id": "http://purl.org/dc/terms/title",
            "http://www.w3.org/2000/01/rdf-schema#subPropertyOf": [
            {"@id": "http://www.w3.org/2000/01/rdf-schema#label"}
            ]
        }
    ]
}
target = {"@context": {"@vocab": "http://www.w3.org/2000/01/rdf-schema#"}}

tgm = make_target_map(vocab, target)
print(json.dumps(tgm, indent=2))
outdata = map_to(tgm, indata)
print(json.dumps(outdata, indent=2))
