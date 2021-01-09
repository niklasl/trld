from pathlib import Path
from io import StringIO

from .. import common
from ..common import Input, Output
from .base import *
from . import context
from .expansion import expand
from .compaction import compact
from .flattening import flatten
from .rdf import RdfDataset, to_jsonld, to_rdf_dataset
#from ..nq import parser as nq_parser, serializer as nq_serializer
from ..nq.parser import parse
from ..nq.serializer import serialize


TESTS_URL = 'https://w3c.github.io/json-ld-api/tests'


class TestCase:

    def __init__(self, suitedir: Path, tc_data: Dict):
        self.testtype = tc_data[TYPE]
        self.testid = tc_data[ID].replace('#t', '')
        self.name = tc_data['name']

        options = tc_data.get(u'option') or {}
        self.options = options

        self.indoc_path = suitedir / tc_data['input']

        base_uri = str(self.indoc_path).replace(str(suitedir), TESTS_URL)
        self.base_uri = options.get('base', base_uri)

        self.compact_arrays = options.get('compactArrays', True)

        self.expected_error = tc_data.get('expectErrorCode')

        self.expectdoc_path = None
        expectdoc_path = tc_data.get('expect')
        if expectdoc_path:
            self.expectdoc_path = suitedir / expectdoc_path

        self.expand_context = None
        expand_context = options.get('expandContext')
        if expand_context:
            self.expand_context = str(suitedir / expand_context)

        self.context_path = None
        self.compact_context = None
        context_path = tc_data.get('context')
        if context_path:
            self.context_path = suitedir / context_path
            self.compact_context = common.load_json(str(self.context_path))

    def run(self):
        if 'jld:FromRDFTest' in self.testtype:
            out_data = self.run_from_rdf_test()

        elif 'jld:ToRDFTest' in self.testtype:
            out_data = self.run_to_rdf_test()

        elif 'jld:ExpandTest' in self.testtype \
                or 'jld:CompactTest' in self.testtype \
                or 'jld:FlattenTest' in self.testtype:
            in_data = common.load_json(str(self.indoc_path))
            out_data = expand(in_data, self.base_uri,
                    expand_context=self.expand_context, ordered=True)

        if 'jld:FlattenTest' in self.testtype:
            out_data = flatten(out_data, ordered=True)

        if self.compact_context:
            out_data = compact(self.compact_context, out_data, self.base_uri,
                    compact_arrays=self.compact_arrays, ordered=True)

        return out_data, self._load_expect_data()

    def run_from_rdf_test(self):
        in_data = RdfDataset()
        with self.indoc_path.open() as f:
            inp = Input(f)
            parse(in_data, inp)
        ordered = True
        rdf_direction = self.options.get('rdfDirection')
        use_native_types = self.options.get('useNativeTypes', False)
        use_rdf_type = self.options.get('useRdfType', False)
        return to_jsonld(in_data, ordered,
                rdf_direction, use_native_types, use_rdf_type)

    def run_to_rdf_test(self):
        sb = StringIO()
        out = Output(sb)
        in_data = common.load_json(str(self.indoc_path))
        in_data = expand(in_data, self.base_uri,
                expand_context=self.expand_context, ordered=True)
        rdf_direction = self.options.get('rdfDirection')
        dataset = to_rdf_dataset(in_data, rdf_direction)
        serialize(dataset, out)
        return sb.getvalue()

    def _load_expect_data(self):
        if self.expectdoc_path:
            assert 'jld:PositiveEvaluationTest' in self.testtype
            if self.expectdoc_path.suffix == '.nq':
                with self.expectdoc_path.open() as f:
                    return f.read()
            else:
                expect_data = common.load_json(str(self.expectdoc_path))
                if self.context_path and isinstance(expect_data, dict):
                    expect_data.pop(CONTEXT, None)
                return expect_data
        elif 'jld:PositiveSyntaxTest' in self.testtype:
            pass # NOTE: only input; just test conversion!
        else:
            assert 'jld:NegativeEvaluationTest' in self.testtype
