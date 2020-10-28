import json
import sys
import traceback
from pathlib import Path

from . import common

_load_json = common.load_json
def load_local_json(url):
    # TODO: hack to resolve import URL against file base.
    # Instead, "install" a LoadDocumentCallback with this hack!
    url = url.replace(TESTS_URL, SUITE_FILE_DIR)
    return _load_json(url)
common.load_json = load_local_json

from .base import *
from . import context
from .expansion import expand
from .compaction import compact
from .flattening import flatten


TESTS_URL = 'https://w3c.github.io/json-ld-api/tests'

def _set_suite_file_dir(suitedir):
    global SUITE_FILE_DIR
    while suitedir.parent.name and suitedir.name != 'tests':
        suitedir = suitedir.parent
    SUITE_FILE_DIR = str(suitedir)


realprint = print
def print(*args, **kwargs):
    realprint(*args, file=sys.stderr, **kwargs)


def run_testsuite(suitefilepath):
    suitefile = Path(suitefilepath)
    print(f'Running test suite: {suitefile}')
    suitedir = suitefile.parent
    with suitefile.open() as fp:
        testsuite = json.load(fp)

    _set_suite_file_dir(suitedir)

    runs, oks, fails, errors = 0, 0, 0, 0

    for tc in testsuite['sequence']:
        testid = tc[ID].replace('#t', '')

        options = tc.get(u'option') or {}
        if options.get('specVersion') == JSONLD10:
            continue

        runs += 1

        print(f"Running TC {testid} - {tc['name']}:", end=' ')


        indoc_path = suitedir / tc['input']
        with indoc_path.open() as f:
            in_data = json.load(f)

        expectdoc_path = tc.get('expect')
        expect_data = None
        if expectdoc_path:
            assert 'jld:PositiveEvaluationTest' in tc[TYPE]
            expectdoc_path = suitedir / expectdoc_path
            with expectdoc_path.open() as f:
                expect_data = json.load(f)
        else:
            assert 'jld:NegativeEvaluationTest' in tc[TYPE]

        expected_error = tc.get('expectErrorCode')

        context_path = tc.get('context')
        context_data = None
        if context_path:
            context_path = suitedir / context_path
            with context_path.open() as f:
                context_data = json.load(f)

        context.DEFAULT_PROCESSING_MODE = options.get('processingMode', JSONLD11)

        base_uri = str(indoc_path).replace(str(suitedir), TESTS_URL)
        base_uri = options.get('base', base_uri)

        def handle_fail():
            nonlocal fails
            fails += 1
            print('FAIL')
            print(f"  With base: '{base_uri}'")
            print(f"  From file: '{indoc_path}'")
            if context_path:
                print(f"  Using context: '{context_path}'")
            if expectdoc_path:
                print(f"  Expecting: '{expectdoc_path}'")
            if expect_data:
                print(f'  Expected: {expect_shape}')
            if expected_error:
                print(f'Expected error: {expected_error}')

        try:
            compact_arrays = options.get('compactArrays', True)

            if 'jld:ExpandTest' in tc[TYPE] or 'jld:FlattenTest' in tc[TYPE]:
                expand_context = options.get('expandContext')
                if expand_context:
                    expand_context = str(suitedir / expand_context)

                out_data = expand(in_data,
                        base_uri,
                        expand_context=expand_context,
                        ordered=True)
            elif 'jld:CompactTest' in tc[TYPE]:
                out_data = expand(in_data, base_uri, ordered=True)

            if 'jld:FlattenTest' in tc[TYPE]:
                out_data = flatten(out_data, ordered=True)

            if context_data:
                out_data = compact(context_data, out_data, base_uri,
                        compact_arrays=compact_arrays, ordered=True)

                if isinstance(expect_data, dict):
                    expect_data.pop(CONTEXT, None)

            out_shape = jsonrepr(out_data)
            expect_shape = jsonrepr(expect_data)
            if out_shape != expect_shape:
                handle_fail()
                print(f'  Got: {out_shape}')
            else:
                oks += 1
                print('OK')
        except Exception as e:
            if expected_error:
                if expected_error.translate({ord(c): None for c in ' -@'}).lower() + 'error' == type(e).__name__.lower():
                    oks += 1
                    print(f'(Got expected error: {expected_error}): OK')
                else:
                    handle_fail()
                    print('>', end=' ')
                    traceback.print_exc(-3)
                    print()
            else:
                errors += 1
                print(f"ERROR in file '{indoc_path}'")
                print('>', end=' ')
                traceback.print_exc(-3)
                print()

    print()
    print(f'Ran {runs} test cases. Passed: {oks}. Failed: {fails}. Errors: {errors}.')

    return not fails and not errors


def jsonrepr(data):
    return json.dumps(data, sort_keys=True, indent=2)


if __name__ == '__main__':
    args = sys.argv[1:]
    ok = True
    for arg in args:
        if not run_testsuite(arg):
            ok = False
    if not ok:
        sys.exit(1)
