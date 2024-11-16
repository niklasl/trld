import json
import os

from ..jsonld.keys import CONTEXT, VOCAB
from ..jsonld.expansion import expand
from ..jsonld.compaction import compact
from ..api import parse_rdf, serialize_rdf

from .mapmaker import make_target_map
from .mapper import map_to


def run(args):
    vocab_refs = args.vocab
    targetref = args.target_profile
    drop_unmapped = args.drop
    sources = args.source
    context_ref = args.context

    if os.path.isfile(targetref):
        with open(targetref) as f:
            target = json.load(f)
    else:
        target = {"@context": {"@vocab": targetref}}

    def _get_target_map():
        vocab_data = []
        for vocab_id in vocab_refs:
            vocab = parse_rdf(vocab_id)
            vocab_data += expand(vocab, vocab_id, context_ref)
        return make_target_map(vocab_data, target)

    if not sources:
        target_map = _get_target_map()
        print(json.dumps(target_map, indent=2))
    else:
        results = []

        for source in sources:
            indata = parse_rdf(source, args.input_format)

            ctx = None
            if not vocab_refs and VOCAB in ctx:
                ctx = indata[CONTEXT]
                vocabref = ctx[VOCAB]
                vocab_refs = vocabref if isinstance(vocabref, list) else [vocabref]

            indata = expand(indata, source, context_ref)

            target_map = _get_target_map()

            outdata = map_to(target_map, indata, drop_unmapped)

            results += outdata

        result = compact(target, results) # type: ignore
        if isinstance(result, dict):
            result[CONTEXT] = target[CONTEXT]

        serialize_rdf(result, args.output_format)


if __name__ == '__main__':
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', metavar='SOURCE', nargs='*')
    argparser.add_argument('-b', '--base', help='Set the base IRI (default is current source)')
    argparser.add_argument('-c', '--context', help='Used to expand and compact given data')
    argparser.add_argument('-v', '--vocab', help="Source vocabulary (figure out from source if not given)", nargs='+')
    argparser.add_argument('-t', '--target-profile')
    argparser.add_argument('-d', '--drop', action='store_true', help="Drop unmapped terms")
    argparser.add_argument('-i', '--input-format', help='Set RDF input format')
    argparser.add_argument('-o', '--output-format', help='Set RDF output format')
    argparser.add_argument('-B', '--embed-blanks', action='store_true')

    args = argparser.parse_args()

    run(args)
