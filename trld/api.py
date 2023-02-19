import io
import json
import sys
from typing import Any, Dict, Optional

from .mimetypes import SUFFIX_MIME_TYPE_MAP
from .platform.common import json_encode
from .platform.io import Input, Output

TURTLE_OR_TRIG = {SUFFIX_MIME_TYPE_MAP[s] for s in ['trig', 'ttl']}
NT_OR_NQ = {SUFFIX_MIME_TYPE_MAP[s] for s in ['nt', 'nq']}


def text_input(text: str, fmt: str = 'trig') -> Input:
    return Input(io.StringIO(text), _to_headers(fmt))


def _to_headers(fmt: Optional[str]) -> Dict:
    headers = {}
    accept = SUFFIX_MIME_TYPE_MAP.get(fmt, fmt) if fmt else None
    if accept:
        headers['Accept'] = accept
    return headers


def parse_rdf(source: Any, fmt: Optional[str] = None) -> Any:
    headers = _to_headers(fmt)

    inp = (
        source
        if isinstance(source, Input)
        else Input(None if source == '-' else source, headers)
    )

    if inp.content_type in TURTLE_OR_TRIG:
        from .trig import parser as trig

        return trig.parse(inp)

    if inp.content_type in NT_OR_NQ:
        from .nq import parser as nq

        return nq.parse(inp)

    return inp.load_json()


def serialize_rdf(result, fmt, out=None):
    if fmt is None or fmt == 'jsonld':
        print(json_encode(result, pretty=True))
        return

    out = Output(out or sys.stdout)
    if fmt in {'trig', 'ttl', 'turtle', 'turtle-union'}:
        from .trig import serializer as trig

        if fmt == 'trig':
            trig.serialize(result, out)
        else:
            trig.serialize_turtle(result, out, union=fmt == 'turtle-union')
    else:
        from .jsonld.rdf import to_rdf_dataset

        dataset = to_rdf_dataset(result)
        if fmt == 'nq':
            from .nq import serializer as nq

            nq.serialize(dataset, out)
        else:
            print(json.dumps(dataset, indent=2, default=lambda o: o.__dict__))
