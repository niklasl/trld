import json
from pathlib import Path

from trld.c14n import canonicalize
from trld.jsonld.rdf import RdfDataset
from trld.nq.parser import load
from trld.nq.serializer import serialize
from trld.platform.io import Input, Output

repo_dir = Path(__file__).parent / '..'
tests_dir = repo_dir / 'cache' / 'rdf-canon' / 'tests'
manifest_file = tests_dir / 'manifest.jsonld'


def test_testcase(entry: dict) -> None:
    ds = RdfDataset()
    with open(tests_dir / entry['action']) as f:
        load(ds, Input(f))
    ds = canonicalize(ds, entry.get('hashAlgorithm'))
    out = Output()
    serialize(ds, out)
    result_lines = sorted(l for l in set(out.get_value().split('\n')) if l)

    with (tests_dir / entry['result']).open() as f:
        expected_lines = sorted(l.rstrip() for l in f)

    assert result_lines == expected_lines


def pytest_generate_tests(metafunc):
    with manifest_file.open() as f:
        manifest = json.load(f)

    if metafunc.function is test_testcase:
        entries = [
            entry
            for entry in manifest['entries']
            if entry["type"] == "rdfc:RDFC10EvalTest"
        ]
        ids = [entry['id'] for entry in entries]
        metafunc.parametrize('entry', entries, ids=ids)
