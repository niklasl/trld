from io import StringIO
from typing import Dict, Union, cast
from pathlib import Path
from ..platform.io import Input, Output
from ..jsonld.keys import CONTEXT

from . import parser
from . import serializer
from .test import read_manifest, datarepr


def run_tests(test_suite_dir: Union[str, Path]):
    test_suite_dir = Path(test_suite_dir)

    i = 0
    failed = 0
    rtrippable = 0
    rtripped = 0

    manifest = read_manifest(test_suite_dir / 'manifest.ttl')

    for ttype, taction, tresult in manifest:
        i += 1
        trig_path = test_suite_dir / taction
        negative = ttype in ('rdft:TestTrigNegativeSyntax', 'rdft:TestTrigNegativeEval')
        if negative:
            continue

        inp = Input(str(trig_path))
        try:
            result = cast(Dict, parser.parse(inp))
            assert result is not None
        except Exception as e:
            print(f'FAILED on {trig_path} (a {ttype}):', e)
            failed += 1
        else:
            base_uri = 'http://www.w3.org/2013/TriGTests/'
            context = result[CONTEXT]
            resultrepr = datarepr(result, context, f'{base_uri}{trig_path.name}')

            rtrippable += 1
            out = Output()
            serializer.serialize(result, out)
            try:
                rtrip = cast(Dict, parser.parse(Input(StringIO(out.get_value()))))
            except Exception as e:
                print(f'ERROR on {trig_path} (a {ttype}): {e!r}')
                failed += 1
            else:
                rtripexpr = datarepr(rtrip, context, f'{base_uri}{trig_path.name}')
                if resultrepr == rtripexpr:
                    rtripped += 1
                else:
                    print('UNEQUAL:', resultrepr, '!=', rtripexpr)

    print(f'Examined {i} tests.',
          f'Round-tripped {rtrippable}, passed {rtripped}, failed {failed}')


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]

    test_suite_dir = args.pop(0) if args else 'cache/trig-tests'

    run_tests(test_suite_dir)
