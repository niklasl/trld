import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from . import context
from .docloader import any_document_loader, set_document_loader
from .keys import BASE, CONTEXT, GRAPH, ID, JSONLD10, JSONLD11
from .testbase import TESTS_URL, TestCase


def run_testsuite(suitefile: Path) -> tuple[list, int, int, int]:
    eprint(f'Running test suite: {suitefile}')

    suitedir = suitefile.parent
    with suitefile.open() as fp:
        testsuite = json.load(fp)

    suite_file_dir = _find_suite_file_dir(suitedir)

    def local_testsuite_loader(url, options=None):
        return any_document_loader(url.replace(TESTS_URL, suite_file_dir))

    set_document_loader(local_testsuite_loader)

    manifest_base = ""
    for ctx in testsuite[CONTEXT]:
        if BASE in ctx:
            manifest_base = ctx[BASE]

    results: list[dict] = []

    runs, oks, fails, errors = 0, 0, 0, 0

    for tc_data in testsuite['sequence']:

        tc = TestCase(str(suitedir), tc_data)

        tc_id = manifest_base + tc_data[ID]
        # one of passed, failed, cantTell, inapplicable, untested
        outcome = {"@id": "earl:cantTell"}
        tstamp = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
        result = {
            "@type": "earl:Assertion",
            "earl:assertedBy": {"@id": "https://neverspace.net/id#self"},
            "earl:subject": {"@id": "https://github.com/niklasl/trld"},
            "earl:test": {"@id": tc_id},
            "earl:result": {
                "@type": "earl:TestResult",
                "earl:outcome": outcome,
                "date": tstamp,
            },
            "earl:mode": {"@id": "earl:automatic"},
        }
        results.append(result)

        if tc.options.get('specVersion') == JSONLD10:
            outcome[ID] = "earl:untested"
            continue

        runs += 1
        eprint(f"Running TC {tc.testid} - {tc.name}:", end=' ')

        context.DEFAULT_PROCESSING_MODE = tc.options.get('processingMode', JSONLD11)  # type: ignore

        try:
            out_data, expect_data = tc.run()
        except Exception as e:
            if tc.expected_error:
                errorname = tc.expected_error.translate({ord(c): None for c in ' -@'})
                if errorname.lower() + 'error' == type(e).__name__.lower():
                    outcome[ID] = "earl:passed"
                    oks += 1
                    eprint(f'(Got expected error: {tc.expected_error}): OK')
                else:
                    outcome[ID] = "earl:failed"
                    fails += 1
                    report_failure(tc, expect_data)
                    eprint('>', end=' ')
                    traceback.print_exc(-3)
                    eprint()
            else:
                outcome[ID] = "earl:failed"
                errors += 1
                eprint(f"ERROR in file '{tc.indoc_path}'")
                eprint('>', end=' ')
                traceback.print_exc(-3)
                eprint()
        else:
            out_shape = datarepr(out_data)
            expect_shape = datarepr(expect_data) if expect_data else out_shape

            if out_shape != expect_shape:
                outcome[ID] = "earl:failed"
                fails += 1
                report_failure(tc, expect_shape)
                eprint(f'  Got: {out_shape}')
            else:
                outcome[ID] = "earl:passed"
                oks += 1
                eprint('OK')

    eprint()
    eprint(f'Ran {runs} test cases. Passed: {oks}. Failed: {fails}. Errors: {errors}.')

    return results, oks, fails, errors


def _find_suite_file_dir(suitedir):
    while suitedir.parent.name and suitedir.name != 'tests':
        suitedir = suitedir.parent
    return str(suitedir)


def report_failure(tc, expect_data):
    eprint('FAIL')
    eprint(f"  With base: '{tc.base_uri}'")
    eprint(f"  From file: '{tc.indoc_path}'")
    if tc.context_path:
        eprint(f"  Using context: '{tc.context_path}'")
    if tc.expectdoc_path:
        eprint(f"  Expecting: '{tc.expectdoc_path}'")
    if expect_data:
        eprint(f'  Expected: {expect_data}')
    if tc.expected_error:
        eprint(f'Expected error: {tc.expected_error}')


def datarepr(data):
    if isinstance(data, str):
        return '\n'.join(sorted(data.splitlines()))
    return json.dumps(data, sort_keys=True, indent=2)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def save_report(report_base: dict, reports_dir: Path, results: list):
    with reports_dir.open('w') as f:
        report = report_base.copy()
        graph = report[GRAPH]
        assert isinstance(graph, list)
        graph += results
        json.dump(report, f, indent=2, ensure_ascii=False)


def main():
    import argparse

    argp = argparse.ArgumentParser()
    argp.add_argument('test_manifests', metavar='TEST_MANIFEST', nargs='*')
    argp.add_argument('-r', '--reports-dir')
    args = argp.parse_args()

    reports_dir = Path(args.reports_dir) if args.reports_dir else None
    report_base = {}
    if reports_dir is not None:
        pkg_root = Path(__file__).parent.parent.parent
        with (pkg_root / 'test' / 'report-base.jsonld').open() as f:
            report_base = json.load(f)

    ok = True
    for suitefilepath in args.test_manifests:
        suitefile = Path(suitefilepath)
        results, oks, fails, errors = run_testsuite(suitefile)
        if fails > 0 or errors > 0:
            ok = False

        if reports_dir is not None:
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_name = suitefile.name.replace('-manifest', '-report')
            save_report(report_base, reports_dir / report_name, results)

    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
