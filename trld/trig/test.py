from typing import Iterator, List, Dict, Union, NamedTuple, cast
from pathlib import Path
from ..common import Input, dump_canonical_json
from ..jsonld.base import CONTEXT, GRAPH, ID, TYPE, LIST
from ..jsonld.expansion import expand
from ..jsonld.compaction import compact
from ..jsonld.flattening import flatten
from ..jsonld.rdf import to_rdf_dataset, to_jsonld
from ..nq import parser as nq_parser

from . import parser

##
# Official test suite located at: https://www.w3.org/2013/TrigTests/TESTS.tar.gz


class TestCase(NamedTuple):
    ttype: str
    taction: str
    tresult: str


def read_manifest(manifest_path) -> Iterator[TestCase]:
    data = cast(Dict, parser.parse(Input(str(manifest_path))))
    index = {node[ID]: node for node in data[GRAPH] if ID in node}

    testentries = cast(List[Dict], index['']['mf:entries'][LIST])
    for testentry in testentries:
        tnode = index[testentry[ID]]
        ttype = tnode['rdf:type'][ID] if 'rdf:type' in tnode else tnode[TYPE]
        taction = tnode['mf:action'][ID]
        tresult = tnode['mf:result'][ID] if 'mf:result' in tnode else None
        yield TestCase(ttype, taction, tresult)


def run_tests(test_suite_dir: Union[str, Path]):
    test_suite_dir = Path(test_suite_dir)

    i = 0
    failed = 0
    passed = 0

    manifest = read_manifest(test_suite_dir / 'manifest.ttl')

    for ttype, taction, tresult in manifest:
        i += 1
        trig_path = test_suite_dir / taction
        negative = ttype == 'rdft:TestTrigNegativeSyntax'
        inp = Input(str(trig_path))
        try:
            result = cast(Dict, parser.parse(inp))
            assert result is not None
        except Exception as e:
            if negative:
                passed += 1
            else:
                print(f'FAILED on {trig_path} (a {ttype}):', e)
                failed += 1
        else:
            if negative:
                print(f'SHOULD FAIL on {trig_path} (a {ttype})')
                failed += 1
            elif tresult:
                nq_path = test_suite_dir / tresult
                try:
                    expected = nq_parser.parse(Input(str(nq_path)))
                except Exception:
                    print(f'Error parsing NQuads {nq_path}')
                    raise

                base_uri = 'http://www.w3.org/2013/TriGTests/'
                context = result[CONTEXT]
                resultrepr = datarepr(result, context, f'{base_uri}{trig_path.name}')
                expectedrepr = datarepr(expected, context, f'{base_uri}{nq_path.name}')

                if resultrepr != expectedrepr:
                    print(f'FAILED COMPARISON for {trig_path} ({ttype}). Got:\n',
                          f'{resultrepr}\n',
                          f'Expected from {nq_path}:\n', f'{expectedrepr}', sep='\t')
                    print()
                    failed += 1
                else:
                    passed += 1
            else:
                passed += 1

    print(f'Ran {i} tests. Passed {passed}, failed {failed}')


def datarepr(data, context, base_uri) -> str:
    data = expand(data, base_uri)
    data = flatten(data)
    dataset = to_rdf_dataset(data)
    data = to_jsonld(dataset)
    data = compact(context, data, '', ordered=True)
    return dump_canonical_json(data)


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]

    test_suite_dir = args.pop(0) if args else 'cache/trig-tests'

    run_tests(test_suite_dir)
