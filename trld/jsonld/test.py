import json
import sys
import traceback
from pathlib import Path

from ..common import Input, set_document_loader
from .base import JSONLD10, JSONLD11
from . import context
from .testbase import TestCase, TESTS_URL


realprint = print
def print(*args, **kwargs):
    realprint(*args, file=sys.stderr, **kwargs)


def _find_suite_file_dir(suitedir):
    while suitedir.parent.name and suitedir.name != 'tests':
        suitedir = suitedir.parent
    return str(suitedir)


def run_testsuite(suitefilepath: str) -> bool:
    suitefile = Path(suitefilepath)
    print(f'Running test suite: {suitefile}')
    suitedir = suitefile.parent
    with suitefile.open() as fp:
        testsuite = json.load(fp)

    suite_file_dir = _find_suite_file_dir(suitedir)
    set_document_loader(lambda url: Input(url.replace(TESTS_URL, suite_file_dir)))

    runs, oks, fails, errors = 0, 0, 0, 0

    for tc_data in testsuite['sequence']:
        tc = TestCase(str(suitedir), tc_data)
        if tc.options.get('specVersion') == JSONLD10:
            continue

        runs += 1
        print(f"Running TC {tc.testid} - {tc.name}:", end=' ')

        context.DEFAULT_PROCESSING_MODE = tc.options.get('processingMode', JSONLD11) # type: ignore

        try:
            out_data, expect_data = tc.run()
        except Exception as e:
            if tc.expected_error:
                if tc.expected_error.translate({ord(c): None for c in ' -@'}).lower() + 'error' == type(e).__name__.lower():
                    oks += 1
                    print(f'(Got expected error: {tc.expected_error}): OK')
                else:
                    fails += 1
                    report_failure(tc, expect_data)
                    print('>', end=' ')
                    traceback.print_exc(-3)
                    print()
            else:
                errors += 1
                print(f"ERROR in file '{tc.indoc_path}'")
                print('>', end=' ')
                traceback.print_exc(-3)
                print()
        else:
            out_shape = datarepr(out_data)
            expect_shape = datarepr(expect_data) if expect_data else out_shape

            if out_shape != expect_shape:
                fails += 1
                report_failure(tc, expect_shape)
                print(f'  Got: {out_shape}')
            else:
                oks += 1
                print('OK')

    print()
    print(f'Ran {runs} test cases. Passed: {oks}. Failed: {fails}. Errors: {errors}.')

    return not fails and not errors


def datarepr(data):
    if isinstance(data, str):
        return '\n'.join(sorted(data.splitlines()))
    return json.dumps(data, sort_keys=True, indent=2)


def report_failure(tc, expect_data):
    print('FAIL')
    print(f"  With base: '{tc.base_uri}'")
    print(f"  From file: '{tc.indoc_path}'")
    if tc.context_path:
        print(f"  Using context: '{tc.context_path}'")
    if tc.expectdoc_path:
        print(f"  Expecting: '{tc.expectdoc_path}'")
    if expect_data:
        print(f'  Expected: {expect_data}')
    if tc.expected_error:
        print(f'Expected error: {tc.expected_error}')


if __name__ == '__main__':
    args = sys.argv[1:]
    ok = True
    for arg in args:
        if not run_testsuite(arg):
            ok = False
    if not ok:
        sys.exit(1)
