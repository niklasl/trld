import json
import sys
import traceback
from pathlib import Path
from io import StringIO

from .. import common

_load_json = common.load_json
def load_local_json(url):
    # TODO: hack to resolve import URL against file base.
    # Instead, "install" a LoadDocumentCallback with this hack!
    url = url.replace(TESTS_URL, SUITE_FILE_DIR)
    return _load_json(url)
common.load_json = load_local_json

from ..common import Input, Output
from .base import *
from . import context
from .expansion import expand
from .compaction import compact
from .flattening import flatten
from .rdf import RdfDataset, to_jsonld, to_rdf_dataset
from ..nq import parser as nq_parser, serializer as nq_serializer


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

        expectdoc_path = tc.get('expect')
        if expectdoc_path:
            assert 'jld:PositiveEvaluationTest' in tc[TYPE]
            expectdoc_path = suitedir / expectdoc_path
        elif 'jld:PositiveSyntaxTest' in tc[TYPE]:
            pass # NOTE: only input; just test conversion!
        else:
            assert 'jld:NegativeEvaluationTest' in tc[TYPE], f'Odd type: {tc[TYPE]!r}'

        context.DEFAULT_PROCESSING_MODE = options.get('processingMode', JSONLD11)

        base_uri = str(indoc_path).replace(str(suitedir), TESTS_URL)
        base_uri = options.get('base', base_uri)

        compact_arrays = options.get('compactArrays', True)

        expand_context = options.get('expandContext')
        if expand_context:
            expand_context = str(suitedir / expand_context)

        expected_error = tc.get('expectErrorCode')

        context_path = tc.get('context')

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

            in_data = None
            expect_data = None
            context_data = None

            if context_path:
                context_path = suitedir / context_path
                with context_path.open() as f:
                    context_data = json.load(f)

            if 'jld:FromRDFTest' in tc[TYPE]:
                with indoc_path.open() as f:
                    inp = Input(f)
                    in_data = RdfDataset()
                    nq_parser.parse(in_data, inp)
                    ordered = True
                    rdf_direction = options.get('rdfDirection')
                    use_native_types = options.get('useNativeTypes', False)
                    use_rdf_type = options.get('useRdfType', False)
                    out_data = to_jsonld(in_data, ordered,
                            rdf_direction, use_native_types, use_rdf_type)

            if in_data is None:
                with indoc_path.open() as f:
                    in_data = json.load(f)


            if 'jld:ToRDFTest' in tc[TYPE]:
                sb = StringIO()
                out = Output(sb)
                in_data = expand(in_data,
                        base_uri,
                        expand_context=expand_context,
                        ordered=True)
                rdf_direction = options.get('rdfDirection')
                dataset = to_rdf_dataset(in_data, rdf_direction)
                nq_serializer.serialize(dataset, out)
                out_data = sb.getvalue()
                out_data = '\n'.join(sorted(out_data.splitlines()))
                if expectdoc_path:
                    with expectdoc_path.open() as f:
                        expect_data = f.read()
                    expect_data = '\n'.join(sorted(expect_data.splitlines()))

            if expect_data is None and expectdoc_path:
                with expectdoc_path.open() as f:
                    expect_data = json.load(f)

            if 'jld:ExpandTest' in tc[TYPE] or 'jld:FlattenTest' in tc[TYPE]:
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

            out_shape = datarepr(out_data)
            expect_shape = datarepr(expect_data) if expect_data else out_shape
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


def datarepr(data):
    if isinstance(data, str):
        return data
    return json.dumps(data, sort_keys=True, indent=2)


if __name__ == '__main__':
    args = sys.argv[1:]
    ok = True
    for arg in args:
        if not run_testsuite(arg):
            ok = False
    if not ok:
        sys.exit(1)
