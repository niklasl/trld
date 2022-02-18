from typing import Dict, List, Tuple, Optional, cast

from ..common import Input, Output, load_json
from .base import *
from . import context
from .expansion import expand
from .compaction import compact
from .flattening import flatten
from .rdf import RdfDataset, to_jsonld, to_rdf_dataset
#from ..nq import parser as nq_parser, serializer as nq_serializer
from ..nq.parser import load
from ..nq.serializer import serialize


TESTS_URL: str = 'https://w3c.github.io/json-ld-api/tests'


class TestCase:

    testtype: List[str]
    testid: str
    name: str
    options: Dict[str, object]
    indoc_path: str
    base_uri: str

    compact_arrays: bool
    expected_error: Optional[str]
    expectdoc_path: Optional[str]
    expand_context: Optional[str]
    context_path: Optional[str]
    compact_context: object

    def __init__(self, suitedir: str, tc_data: Dict):
        self.testtype = tc_data[TYPE]
        self.testid = cast(str, tc_data[ID]).replace('#t', '')
        self.name = tc_data['name']

        self.options = cast(Dict, tc_data.get(u'option', {}))

        self.indoc_path = f"{suitedir}/{tc_data['input']}"

        base_uri: str = self.indoc_path.replace(suitedir, TESTS_URL)
        self.base_uri = cast(str, self.options.get('base', base_uri))

        self.compact_arrays = cast(bool, self.options.get('compactArrays', True))

        self.expected_error = tc_data.get('expectErrorCode')

        self.expectdoc_path = None
        expectdoc_path: Optional[str] = tc_data.get('expect')
        if expectdoc_path:
            self.expectdoc_path = f'{suitedir}/{expectdoc_path}'

        self.expand_context = None
        expand_context: Optional[str] = cast(Optional[str], self.options.get('expandContext'))
        if expand_context:
            self.expand_context = f'{suitedir}/{expand_context}'

        self.context_path = None
        self.compact_context = None
        context_path: str = cast(str, tc_data.get('context'))
        if context_path:
            self.context_path = f'{suitedir}/{context_path}'
            self.compact_context = load_json(str(self.context_path))

    def run(self) -> Tuple[object, object]:
        out_data: object = None
        if 'jld:FromRDFTest' in self.testtype:
            out_data = self.run_from_rdf_test()

        elif 'jld:ToRDFTest' in self.testtype:
            out_data = self.run_to_rdf_test()

        elif 'jld:ExpandTest' in self.testtype \
                or 'jld:CompactTest' in self.testtype \
                or 'jld:FlattenTest' in self.testtype:
            in_data: object = load_json(self.indoc_path)
            out_data = expand(cast(JsonObject, in_data), self.base_uri,
                    expand_context=self.expand_context, ordered=True)

        if 'jld:FlattenTest' in self.testtype:
            out_data = flatten(cast(JsonObject, out_data), ordered=True)

        if self.compact_context:
            out_data = compact(self.compact_context, cast(JsonObject, out_data),
                    self.base_uri,
                    compact_arrays=self.compact_arrays, ordered=True)

        return out_data, self._load_expect_data()

    def run_from_rdf_test(self) -> object:
        in_data: RdfDataset = RdfDataset()
        with Input(self.indoc_path) as inp:
            load(in_data, inp)
        ordered: bool = True
        rdf_direction: Optional[str] = cast(Optional[str], self.options.get('rdfDirection'))
        use_native_types: bool = cast(bool, self.options.get('useNativeTypes', False))
        use_rdf_type: bool = cast(bool, self.options.get('useRdfType', False))
        return to_jsonld(in_data, ordered,
                rdf_direction, use_native_types, use_rdf_type)

    def run_to_rdf_test(self) -> object:
        out: Output = Output()
        in_data: JsonObject = cast(JsonObject, load_json(self.indoc_path))
        in_data = expand(in_data, self.base_uri,
                expand_context=self.expand_context, ordered=True)
        #in_data = flatten(cast(JsonObject, in_data), ordered=True)
        rdf_direction: Optional[str] = cast(Optional[str], self.options.get('rdfDirection'))
        dataset: RdfDataset = to_rdf_dataset(in_data, rdf_direction)
        serialize(dataset, out)
        return out.get_value()

    def _load_expect_data(self) -> Optional[object]:
        if self.expectdoc_path:
            assert 'jld:PositiveEvaluationTest' in self.testtype
            if self.expectdoc_path.endswith('.nq'):
                with Input(self.expectdoc_path) as inp:
                    return inp.read()
            else:
                expect_data: object = load_json(self.expectdoc_path)
                if self.context_path and isinstance(expect_data, Dict):
                    expect_data.pop(CONTEXT, None)
                return expect_data
        elif 'jld:PositiveSyntaxTest' in self.testtype:
            pass # NOTE: only input; just test conversion!
        else:
            assert 'jld:NegativeEvaluationTest' in self.testtype
        return None
