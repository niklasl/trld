import re
from typing import (ClassVar, Dict, Iterable, List, Optional, Set, Tuple,
                    Union, cast)

from ..builtins import Char
from ..jsonld.base import PREFIX_DELIMS
from ..jsonld.keys import (BASE, CONTEXT, DIRECTION, GRAPH, ID, LANGUAGE, LIST,
                           PREFIX, TYPE, VALUE, VERSION, VOCAB)
from ..jsonld.keys import ANNOTATION, REIFIES, TRIPLE
from ..jsonld.keys import ANNOTATED_TYPE_KEY
from ..platform.common import json_encode
from ..platform.io import Input
from ..rdfterms import RDF_TYPE, XSD, XSD_BOOLEAN, XSD_DOUBLE, XSD_INTEGER


XSD_DECIMAL: str = f'{XSD}decimal'

AT_KEYWORDS = {PREFIX, BASE, VERSION}

RQ_PREFIX = 'prefix'
RQ_BASE = 'base'
RQ_VERSION = 'version'
RQ_GRAPH = 'graph'

RQ_KEYWORDS = {RQ_PREFIX, RQ_BASE, RQ_GRAPH, RQ_VERSION}

ESC_CHARS = {
    't': '\t',
    'b': '\b',
    'n': '\n',
    'r': '\r',
    'f': '\f',
    '"': '"',
    "'": "'",
    '\\': '\\'
}

RESERVED_CHARS = {'~', '.', '-', '!',
                  '$', '&', "'", '(',
                  ')', '*', '+', ',',
                  ';', '=', '/', '?',
                  '#', '@', '%', '_'}

NUMBER_LEAD_CHARS = re.compile(r'[+-.0-9]')

LITERAL_QUOTE_CHARS = {'"', "'"}

LANGDIR_SEP = '--'
LANG_DIRS = {'ltr', 'rtl'}

SYMBOL = '@symbol'
EOF = ''

EXP = {'E', 'e'}

StateResult = Tuple['ParserState', object]


# NOTE: Turn this into a stateful setting if this is to be used at runtime.
_use_native_types = True


def set_use_native_types(use: bool) -> None:
    global _use_native_types
    _use_native_types = use


def get_use_native_types() -> bool:
    return _use_native_types



PENDING_OPEN_BRACE = 1
PENDING_OPEN_ANGLE = 2
PENDING_CLOSING_ANGLE = 3
PENDING_OPEN_BRACKET = 4


class NotationError(Exception):
    pass


class ParserError(Exception):

    error: NotationError
    lno: int
    cno: int

    def __init__(self, error: NotationError, lno: int, cno: int):
        super().__init__(str(error))
        self.error = error
        self.lno = lno
        self.cno = cno

    def __str__(self) -> str:
        return (f'Notation error at line {self.lno}, column {self.cno}:'
                f' {self.error}')


class ParserState:

    parent: 'ParserState'
    context: Dict[str, object]

    def consume(self, c: Char, prev_value) -> StateResult:
        raise NotImplementedError(f"Unexpected {c!r} for {self}")


class BaseParserState(ParserState):

    def __init__(self, parent: Optional[ParserState]):
        super().__init__()
        self.parent = parent if parent is not None else ParserState()
        self.context = self.parent.context if isinstance(self.parent, BaseParserState) else {}
        self.init()

    def init(self):
        pass

    def symbol(self, value: Dict[str, str]) -> str:
        if SYMBOL in value:
            sym = value[SYMBOL]
            if sym in self.context:  # FIXME: not enough for vocab refs?
                sym = cast(str, self.context[VOCAB]) + sym
            return sym

        if ID not in value:
            raise NotationError(f'Unexpected symbol: {value!r}')

        return value[ID]


class ConsumeWs(BaseParserState):

    MATCH: ClassVar[re.Pattern] = re.compile(r'\s')

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: Char, prev_value) -> StateResult:
        if self.accept(c):
            return self, None
        else:
            return self.parent.consume(c, prev_value)


class ConsumeComment(BaseParserState):

    def consume(self, c: Char, prev_value) -> StateResult:
        if c == '\n':
            return self.parent, None
        else:
            return self, None


class ReadTerm(BaseParserState):

    ESCAPE_CHAR: ClassVar[str] = '\\'

    collected: List[Char]
    escape_chars: Dict[Char, Char]
    escape_next: bool
    unicode_chars: List[Char]
    unicode_escapes_left: int

    def __init__(self, parent: Optional[ParserState]):
        super().__init__(parent)
        self.collected = []
        self.escape_next = False
        self.unicode_chars = []
        self.unicode_escapes_left = 0

    def collect(self, c: Char):
        self.collected.append(c)

    def pop(self) -> str:
        value = ''.join(self.collected)
        self.collected = []
        return value

    def handle_escape(self, c: Char) -> bool:
        if self.unicode_escapes_left:
            self.unicode_chars.append(c)
            if self.unicode_escapes_left == 1:
                hex_seq = ''.join(self.unicode_chars)
                try:
                    c = chr(int(hex_seq, 16))
                except ValueError:
                    raise NotationError(f'Invalid unicode escape: {hex_seq}')
                self.unicode_chars = []
                self.unicode_escapes_left = 0
            else:
                self.unicode_escapes_left -= 1
                return True

        elif self.escape_next:
            if c == 'u':
                self.unicode_escapes_left = 4
                return True
            elif c == 'U':
                self.unicode_escapes_left = 8
                return True
            elif c in self.escape_chars:
                c = self.escape_chars[c]
            else:
                raise NotationError(f'Invalid escape char: {c!r}')

        if self.escape_next:
            self.escape_next = False
            self.collect(c)
            return True

        if c == self.ESCAPE_CHAR:
            self.escape_next = True
            return True

        return False

    def backtrack(self, prev_c: Char, c: Char, value) -> StateResult:
        state, value = self.parent.consume(prev_c, value)
        return state.consume(c, value)


class ReadIRI(ReadTerm):

    MATCH: ClassVar[re.Pattern] = re.compile(r'\S') # TODO: specify better

    def init(self):
        self.escape_chars = {}

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: Char, prev_value) -> StateResult:
        if c == '>':
            value = self.pop()
            return self.parent, {ID: value}
        elif self.handle_escape(c):
            return self, None
        else:
            if not self.accept(c):
                raise NotationError(f'Invalid URI character: {c!r}')
            self.collect(c)
            return self, None


class ReadSymbol(ReadTerm):

    MATCH: ClassVar[re.Pattern] = re.compile(r"[^\]\[{}^<>\"\s~!$&'()*,;=/?#]")

    just_escaped: bool

    def init(self):
        self.escape_chars = {c: c for c in RESERVED_CHARS}
        self.just_escaped = False

    def accept(self, c: Char) -> bool:
        if self.MATCH.match(c) is None:
            return False
        if c == ':' and len(self.collected) > 1 and (self.collected[0] == '_' and
                                                     self.collected[1] == ':'):
            return False
        return True

    def consume(self, c: Char, prev_value) -> StateResult:
        if len(self.collected) == 0 and c == '<':
            return ReadIRI(self.parent), None
        elif len(self.collected) == 0 and NUMBER_LEAD_CHARS.match(c) is not None:
            return ReadNumber(self.parent).consume(c, None)
        elif self.handle_escape(c):
            self.just_escaped = True
            return self, None

        just_escaped = self.just_escaped
        self.just_escaped = False

        if self.accept(c):
            self.collect(c)
            return self, None

        v: str = self.pop()
        last_dot = False
        if not just_escaped and v.endswith('.'):
            v = v[:-1]
            last_dot = True

        value: Union[str, bool, Dict] = v

        if v in {'true', 'false'}:
            if _use_native_types:
                value = cast(bool, v == 'true')
            else:
                value = {VALUE: v, TYPE: XSD_BOOLEAN}
        elif v == 'a':
            value = TYPE
        elif v not in AT_KEYWORDS:
            lowered = v.lower()
            if lowered in RQ_KEYWORDS:
                value = lowered
            else:
                if v != '':
                    if ':' not in v:
                        raise NotationError(f'Expected PNname, got {v!r}')
                    elif v[0] == ':':
                        v = v[1:]
                value = cast(Dict, {SYMBOL: v})

        if last_dot:
            return self.backtrack('.', c, value)

        return self.parent.consume(c, value)


class ReadNumber(ReadTerm):

    whole: Optional[str]
    dot: Char
    exp: bool

    def init(self):
        self.whole = None
        self.dot = ''
        self.exp = False

    def consume(self, c: Char, prev_value) -> StateResult:
        exp = c in EXP
        if exp:
            self.exp = True
        if self.whole is None and c == '.':
            self.whole = self.pop()
            self.dot = c
            return self, None
        elif self.whole is None and exp:
            self.whole = self.pop()
            self.collect(c)
            return self, None
        elif c.isdecimal() or (self.whole is None and
                                len(self.collected) == 0 and
                                NUMBER_LEAD_CHARS.match(c) is not None) or (
                            self.whole is not None and c in EXP) or (
                                len(self.collected) > 0
                                and self.collected[-1] in EXP
                                and NUMBER_LEAD_CHARS.match(c) is not None):
            self.collect(c)
            return self, None
        else:
            number: object
            if self.whole is not None and len(self.collected) == 0:
                if self.whole == '':
                    return self.parent.consume(c, prev_value)
                number = int(self.whole)
                return self.backtrack('.', c, number)

            try:
                number = self.to_number()
            except ValueError as e:
                raise NotationError(f'Invalid number character, got {e}')

            return self.parent.consume(c, number)

    def to_number(self) -> Union[int, float, Dict]:
        value = self.pop()
        if self.whole:
            value = f'{self.whole}{self.dot}{value}'
            number: float = float(value)
            if not _use_native_types or number.is_integer():
                return {VALUE: value, TYPE: XSD_DOUBLE if self.exp else XSD_DECIMAL}
            return number
        else:
            if not _use_native_types or (len(value) > 1 and value[0] == '+'):
                return {VALUE: value, TYPE: XSD_INTEGER}
            return int(value)


class ReadLiteral(ReadTerm):

    value: Optional[str]
    quotechar: str
    multiline: int
    prev_dt_start: int

    def __init__(self, parent: ParserState, quotechar: str):
        super().__init__(parent)
        self.quotechar = quotechar
        self.escape_chars = ESC_CHARS

    def init(self):
        self.prev_dt_start = 0
        self.value = None
        self.multiline = 0

    def consume(self, c: Char, prev_value) -> StateResult:
        if self.value == '' and c == self.quotechar:
            self.multiline = 1
            self.value = None
            return self, None
        elif self.value is not None:
            if self.prev_dt_start > 0:
                self.no_after_literal('Datatype', prev_value)
                if c == '^':
                    if self.prev_dt_start != 1:
                        raise NotationError(f"Expected '^' got {c!r}")
                    self.prev_dt_start = 2
                    return self, None
                else:
                    if self.prev_dt_start != 2:
                        raise NotationError(f"Expected '^' got {c!r}")
                    self.prev_dt_start = 0
                    return ReadSymbol(self).consume(c, None)

            if c == '^':
                self.no_after_literal('Datatype', prev_value)
                self.prev_dt_start = 1
                return self, None

            if c == '@':
                self.no_after_literal('Language', prev_value)
                state = ReadLanguage(self)
                return ReadLanguage(self), None

            value = {VALUE: self.value}
            if prev_value is not None:
                if isinstance(prev_value, Dict) and LANGUAGE in prev_value:
                    value.update(prev_value)
                else:
                    if not isinstance(prev_value, Dict):
                        raise NotationError(f"Expected datatype IRI, got {prev_value!r}")
                    assert self.prev_dt_start == 0
                    dtype = self.symbol(prev_value)
                    if dtype == '':
                        raise NotationError(f'Literal datatype must not be empty')
                    value[TYPE] = dtype

            return self.parent.consume(c, value)

        if self.handle_escape(c):
            self._collect_quotechars()
            return self, None

        if c == self.quotechar:
            if self.multiline == 0 or self.multiline == 3:
                self.multiline = 0
                self.value = self.pop()
            elif self.multiline > 0:
                self.multiline += 1

            return self, None

        self._collect_quotechars()
        self.collect(c)

        return self, None

    def _collect_quotechars(self):
        if self.multiline > 1:
            for i in range(self.multiline - 1):
                self.collect(self.quotechar)
            self.multiline = 1

    def no_after_literal(self, kind, prev_value):
        if prev_value is not None:
            raise NotationError(f'{kind} not allowed after {prev_value!r}')


class ReadLanguage(ReadTerm):

    MATCH: ClassVar[re.Pattern] = re.compile(r'[A-Za-z0-9-]') # TODO: only allow numbers in subtag

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: Char, prev_value) -> StateResult:
        if self.accept(c):
            self.collect(c)
            return self, None
        else:
            if len(self.collected) == 0:
                raise NotationError(f'Language tags must not be empty')
            lang = self.pop()
            langdir: Optional[str] = None
            dirdash: int = lang.find(LANGDIR_SEP)
            if dirdash > -1:
                langdir = lang[dirdash+2:]
                lang = lang[:dirdash]
                if len(langdir) == 0:
                    raise NotationError(f'Language direction must not be empty')
                if langdir not in LANG_DIRS:
                    raise NotationError(f'Language direction must be ltr or rtl')
            self.collected = []
            langdata = {LANGUAGE: lang}
            if langdir is not None:
                langdata[DIRECTION] = langdir
            return self.parent.consume(c, langdata)


class ReadCompound(BaseParserState):

    ws: ConsumeWs
    comment: ConsumeComment
    pending: int

    def __init__(self, parent: Optional[ParserState]):
        super().__init__(parent)
        self.pending = 0
        self.ws = ConsumeWs(self)
        self.comment = ConsumeComment(self)

    def read_space(self, c: Char) -> Optional[StateResult]:
        if self.ws.accept(c):
            return self.ws, None
        elif c == '#':
            return self.comment, None
        else:
            return None

    def take_predicate(self, value: object) -> str:
        if value == TYPE:
            return TYPE
        else:
            if not isinstance(value, Dict):
                raise NotationError(f'Unexpected predicate: {value!r}')
            return self.symbol(value)

    def node_with_id(self, value: Dict) -> Dict:
        if SYMBOL in value:
            node_id: str = value[SYMBOL]
            if ':' not in node_id and VOCAB in self.context:
                node_id = cast(str, self.context[VOCAB]) + node_id
            value = {ID: node_id}
        return value

    def compact_value(self, value: object) -> object:
        if isinstance(value, Dict):
            if VALUE in value:
                if len(value) == 1:
                    return value[VALUE]
            else:
                return self.node_with_id(value)
        return value


class ReadDecl(ReadCompound):

    final_dot: bool
    completed: bool

    def __init__(self, parent: 'ReadNodes', final_dot: bool):
        super().__init__(parent)
        self.final_dot = final_dot
        self.completed = False

    def consume(self, c: Char, prev_value) -> StateResult:
        if isinstance(prev_value, Dict):
            if not self.more_parts(prev_value):
                self.completed = True
                if not self.final_dot:
                    self.declare()
                    return self.parent.consume(c, None)

        readspace = self.read_space(c)
        if readspace:
            return readspace

        if c == '.':
            self.declare()
            return self.parent, None
        elif self.completed and self.final_dot:
            raise NotationError(f'Expected a final dot')

        return self.expected_value_reader(c)

    def expected_value_reader(self, c: Char) -> StateResult:
        return ReadSymbol(self).consume(c, None)

    def more_parts(self, value: Dict) -> bool:
        raise NotImplementedError

    def declare(self):
        raise NotImplementedError


class ReadPrefix(ReadDecl):

    pfx: Optional[str]
    ns: Optional[str]

    def init(self):
        self.pfx = None
        self.ns = None

    def more_parts(self, value: Dict) -> bool:
        if self.pfx is None:
            if SYMBOL not in value:
                raise NotationError(f'Invalid prefix {value!r}')

            pfx = cast(str, value[SYMBOL])
            if pfx != '':
                if pfx.endswith(':'):
                    pfx = pfx[:-1]
                else:
                    raise NotationError(f'Invalid prefix {pfx!r}')
            self.pfx = pfx
            return True

        if self.ns is None:
            self.ns = value[ID]

        return False

    def declare(self) -> None:
        if self.ns is None:
            raise NotationError(f'Missing namespace for prefix {self.pfx}')

        ns: Union[str, Dict[str, object]] = self.ns
        if self.pfx != '' and self.ns != '' and not self.ns[-1] in PREFIX_DELIMS:
            ns = {ID: self.ns, PREFIX: True}
        key: str = self.pfx if self.pfx is not None and self.pfx != '' else VOCAB
        self.parent.context[key] = ns


class ReadBase(ReadDecl):

    base: Optional[str]

    def init(self):
        self.base = None

    def more_parts(self, value: Dict) -> bool:
        if self.base is None:
            self.base = value[ID]
        return False

    def declare(self):
        self.parent.context[BASE] = self.base


class ReadVersion(ReadDecl):

    version: Optional[str]

    def init(self):
        self.version = None

    def more_parts(self, value: Dict) -> bool:
        if VALUE not in value:
            raise NotationError(f'Invalid version {value!r}')

        if self.version is None:
            trig_version: str = value[VALUE]
            # TODO: check allowed versions; remap RDF ver to JSON-LD ver!
            self.version = trig_version

        return False

    def expected_value_reader(self, c: Char) -> StateResult:
        if c in LITERAL_QUOTE_CHARS:
            return ReadLiteral(self, c), None
        else:
            raise NotationError(f'Invalid version start {c!r}')

    def declare(self):
        self.parent.context[VERSION] = self.version


class ReadNode(ReadCompound):

    node: Optional[Dict]
    p: Optional[str]
    last_value: Optional[object]

    def fill_node(self, value: object):
        assert self.node is not None

        if self.p is None:
            self.p = self.take_predicate(value)
        elif self.last_value is None:
            if self.p == TYPE:
                if not isinstance(value, Dict) or SYMBOL not in value and ID not in value:
                    self.p = RDF_TYPE
                else:
                    value = cast(str, self.symbol(value))

            value = self.compact_value(value)

            given: Optional[object] = self.node.get(self.p)
            if given is not None:
                values: List = given if isinstance(given, List) else [given]
                values.append(value)
                self.node[self.p] = values
            else:
                self.node[self.p] = value
            self.last_value = value
        elif isinstance(value, Dict) and ANNOTATION in value:
            # NOTE/TODO?: value is only the annotation itself (stacked after); correct?
            last_value = self.last_value
            if self.p == TYPE:
                last_value = {ANNOTATED_TYPE_KEY: last_value}
            elif not isinstance(last_value, Dict):
                last_value = {VALUE: last_value}

            _add_annots_from(last_value, value)

            o: object = self.node[self.p]
            l: Optional[List] = None
            if isinstance(o, List):
                l = o
                o = o[-1]

            if VALUE in last_value and isinstance(o, Dict) and ANNOTATION in o:
                _add_annots_from(o, last_value)
                last_value[ANNOTATION] = o[ANNOTATION]

            # TODO: annotation already added and must be replaced by the real value?
            if l is not None:
                l[-1] = last_value
            else:
                self.node[self.p] = last_value
        else:
            raise NotationError(f'Unexpected: {value!r}')

    def consume_node_char(self, c: Char) -> StateResult:
        if self.pending == PENDING_OPEN_ANGLE:
            self.pending = 0
            if c == '<':
                return ReadTripleOrReifier(self), None
            else:
                return ReadIRI(self).consume(c, None)
        else:
            readspace = self.read_space(c)
            if readspace:
                return readspace

        if c == '<':
            self.pending = PENDING_OPEN_ANGLE
            return self, None
        elif c == '{':
            self.pending = PENDING_OPEN_BRACE
            return self, None
        elif c == '|':
            if self.pending != PENDING_OPEN_BRACE:
                raise NotationError(f'Unexpected: {c!r}')
            assert self.last_value is not None
            self.pending = 0
            return ReadAnnotation(self), None
        elif c == '[':
            return ReadBNode(self), None
        elif c == '(':
            return ReadCollection(self), None
        elif c == '~':
            if self.last_value is None:
                raise NotationError(f'Unexpected: {c!r}')
            return ReadAnnotationNameOrAnnotation(self), None
        elif c == ';':
            if self.node is None:
                raise NotationError(f'Unexpected: {c!r}')
            self.check_complete()
            self.p = None
            self.last_value = None
            return self, None
        elif c == ',':
            self.last_value = None
            return self, None
        elif c in LITERAL_QUOTE_CHARS:
            return ReadLiteral(self, c), None
        else:
            assert self.pending == 0
            return ReadSymbol(self).consume(c, None)

    def check_complete(self) -> None:
        if self.p is not None and self.last_value is None:
            raise NotationError(f'Missing triple object')


def _add_annots_from(target: Dict, source: Dict):
    if ANNOTATION in target:
        annot_obj: object = target[ANNOTATION]
        annots: List
        if not isinstance(annot_obj, List):
            annots = [annot_obj]
            target[ANNOTATION] = annots
        else:
            annots = annot_obj

        source_annot: object = source[ANNOTATION]
        if isinstance(source_annot, List):
            if annots[-1] is not source_annot[-1]:
                annots += source_annot
        else:
            if annots[-1] is not source_annot:
                annots.append(source_annot)
    else:
        target[ANNOTATION] = source[ANNOTATION]


class ReadTripleOrReifier(ReadNode):

    waiting_for_name: bool
    name: Optional[str]
    pending: int

    def init(self):
        self.reset()
        self.pending = 0

    def reset(self):
        self.waiting_for_name = False
        self.name = None
        self.node = {}
        self.p = None
        self.last_value = None

    def consume(self, c: Char, prev_value) -> StateResult:
        if c == '(' and self.pending == 0:
            return ReadTriple(self), None

        new_node = False
        if isinstance(prev_value, Dict):
            if self.waiting_for_name:
                self.name = self.symbol(prev_value)
                return self, None

            if self.p is None:
                assert self.node is not None
                if len(self.node) == 0:
                    if len(prev_value) > 0:
                        if TRIPLE in prev_value:
                            self.node.update(prev_value)
                        else:
                            self.node[ID] = self.symbol(prev_value)
                        new_node = True

            if not new_node:
                self.fill_node(prev_value)

        if c == EOF:
            raise NotationError(f'Unexpected {c!r} in bnode.')
        elif c == '>':
            if self.pending == PENDING_CLOSING_ANGLE:
                self.pending = 0

                if isinstance(self.node, dict) and TRIPLE in self.node:
                    return self.parent, self.node

                if (
                    not isinstance(self.node, Dict)
                    or ID not in self.node
                    or len(self.node) != 2
                    or not self._is_reifiable(self.node)
                ):
                    raise NotationError(f'Malformed reifier: {self.node}')

                reifier: dict = {}
                if self.name is not None:
                    reifier[ID] = self.name
                reifier[REIFIES] = self.node

                return self.parent, reifier

            elif self.pending == PENDING_OPEN_ANGLE:
                self.pending = 0
                return ReadIRI(self).consume(c, None)
            else:
                self.pending = PENDING_CLOSING_ANGLE
                return self, None

        elif c == '~':
            assert not self.waiting_for_name
            self.waiting_for_name = True
            return self, None
        elif self.waiting_for_name:
            return ReadSymbol(self), None
        else:
            return self.consume_node_char(c)

    def _is_reifiable(self, node: Dict[str, object]) -> bool:
        for k, v in node.items():
            if k == ID:
                continue
            elif isinstance(v, Dict):
                if VALUE not in v and (
                    (LIST in v and len(cast(List, v[LIST])) != 0)
                    or (LIST not in v and ID not in v and len(v) != 0)
                ):
                    return False
            elif isinstance(v, List):
                return False

        return True



class ReadTriple(ReadCompound):

    node: Optional[Dict]
    p: Optional[str]
    last_value: Optional[object]

    def init(self):
        self.reset()

    def reset(self):
        self.node = None
        self.p = None
        self.last_value = None
        self.pending = 0

    def consume(self, c: Char, prev_value) -> StateResult:
        if self.pending == PENDING_OPEN_BRACKET:
            if c != ']':
                raise NotationError(f'Unexpected character {c!r} in triple.')
            return self, {}

        if isinstance(prev_value, Dict):
            if self.node is None:
                self.node = self.node_with_id(prev_value)
            elif self.p is None:
                self.p = self.take_predicate(prev_value)
                return self, None

        if prev_value is not None:
            self.last_value = prev_value

        readspace = self.read_space(c)
        if readspace:
            return readspace

        # FIXME: duplicated ReadCollection logic (why negative checks down here)?
        elif c == EOF:
            raise NotationError(f'Unexpected EOF in triple.')
        elif c == ';':
            raise NotationError(f'Unexpected ";" in triple.')
        elif c == '(':
            raise NotationError(f'Unexpected "(" in triple.')
        elif c == '[':
            self.pending = PENDING_OPEN_BRACKET
            return self, None
        if c == ')':
            assert self.node is not None
            assert self.p is not None
            self.node[self.p] = self.compact_value(self.last_value)
            return self.parent, {TRIPLE: self.node}
        elif c in LITERAL_QUOTE_CHARS:
            return ReadLiteral(self, c), None
        else:
            return ReadSymbol(self).consume(c, None)


class ReadBNode(ReadNode):

    def init(self):
        self.reset()

    def reset(self):
        self.node = {}
        self.p = None
        self.last_value = None

    def consume(self, c: Char, prev_value) -> StateResult:
        if prev_value is not None:
            self.fill_node(prev_value)

        if c == EOF:
            raise NotationError(f'Unexpected {c!r} in bnode.')
        elif c == ']':
            self.check_complete()
            return self.parent, self.node
        else:
            return self.consume_node_char(c)


class ReadAnnotation(ReadBNode): # TODO: Factor out ReadNodeBase

    end_started: bool = False
    name: Optional[str]

    def __init__(self, parent: Optional[ParserState], name: Optional[str] = None):
        super().__init__(parent)
        self.name = name

    def consume(self, c: Char, prev_value) -> StateResult:
        if prev_value is not None:
            self.fill_node(prev_value)

        if c == EOF:
            raise NotationError(f'Unexpected {c!r} in annotation.')
        elif not self.pending == PENDING_OPEN_BRACE and c == '|':
            self.end_started = True
            return self, None
        elif c == '}':
            if not self.end_started:
                raise NotationError(f'Unexpected: {c!r}')
            self.end_started = False
            self.check_complete()
            if self.name is not None and isinstance(self.node, dict):
                self.node = {ID: self.name, **self.node}
            annot = {ANNOTATION: self.node}
            return self.parent, annot
        else:
            if self.end_started:
                raise NotationError(f'Unexpected: {c!r}')

            return self.consume_node_char(c)


class ReadAnnotationNameOrAnnotation(ReadCompound):

    name: Optional[str]

    def init(self):
        self.name = None

    def consume(self, c: Char, prev_value) -> StateResult:
        if isinstance(prev_value, dict):
            self.name = self.symbol(prev_value)

        if self.pending != PENDING_OPEN_ANGLE:
            readspace = self.read_space(c)
            if readspace:
                return readspace

        if c == '{':
            self.pending = PENDING_OPEN_BRACE
            return self, None
        elif c == '|':
            assert self.pending == PENDING_OPEN_BRACE
            self.pending = 0
            readannot = ReadAnnotation(self.parent, self.name)
            return readannot, None
        elif c == '~':
            return self.parent.consume(c, {ANNOTATION: {ID: self.name}})
        elif self.name is not None:
            assert isinstance(self.parent, ReadNode)
            self.parent.fill_node({ANNOTATION: {ID: self.name}})
            return self.parent.consume(c, prev_value)
        else:
            assert self.pending == 0
            return ReadSymbol(self).consume(c, None)


class ReadCollection(ReadCompound):

    nodes: List[object]

    def init(self):
        self.reset()

    def reset(self):
        self.nodes = []

    def consume(self, c: Char, prev_value) -> StateResult:
        if prev_value is not None:
            self.nodes.append(self.compact_value(prev_value))

        readspace = self.read_space(c)
        if readspace:
            return readspace
        elif c == EOF:
            raise NotationError(f'Unexpected EOF in collection.')
        elif c == ';':
            raise NotationError(f'Unexpected ";" in collection.')
        elif c == '[':
            return ReadBNode(self), None
        elif c == '(':
            return ReadCollection(self), None
        elif c == ')':
            return self.parent, {LIST: self.nodes}
        elif c in LITERAL_QUOTE_CHARS:
            return ReadLiteral(self, c), None
        else:
            return ReadSymbol(self).consume(c, None)


class ReadNodes(ReadNode):

    nodes: List[Dict]
    expect_graph: bool

    def init(self):
        self.nodes = []
        self.reset()

    def reset(self):
        self.node = None
        self.p = None
        self.last_value = None
        self.expect_graph = False

    def consume(self, c: Char, prev_value) -> StateResult:
        if prev_value is not None:
            if isinstance(prev_value, str):
                prev_str: str = prev_value
                final_dot = False
                if prev_str in AT_KEYWORDS:
                    prev_str = prev_str[1:]
                    final_dot = True

                if prev_str == RQ_PREFIX:
                    return ReadPrefix(self, final_dot).consume(c, None)
                elif prev_str == RQ_BASE:
                    return ReadBase(self, final_dot).consume(c, None)
                elif prev_str == RQ_VERSION:
                    return ReadVersion(self, final_dot).consume(c, None)
                elif prev_str == RQ_GRAPH:
                    self.expect_graph = True
                    return self, None

                prev_value = prev_str

            if self.node is None:
                if not isinstance(prev_value, Dict) or VALUE in prev_value:
                    raise NotationError(f'Unexpected node: {prev_value!r}.')

                self.node = self.node_with_id(prev_value)
            else:
                if self.p is None and self.expect_graph and self.node is not None:
                    raise NotationError('Expected graph notation to follow, '
                                        f'got {prev_value!r}')
                self.fill_node(prev_value)

        if c == EOF:
            result = {CONTEXT: self.context, GRAPH: self.nodes}
            return self.parent, result
        elif not self.pending and c == '.' and (self.p is None or self.last_value is not None):
            self.next_node()
            return self, None
        else:
            if self.pending == PENDING_OPEN_BRACE:
                if c != '|':
                    self.pending = 0
                    self.expect_graph = False
                    state = ReadGraph(self)
                    return state.consume(c, prev_value)
            return self.consume_node_char(c)

    def next_node(self):
        if self.node is None or (self.p is None and (
                                    (GRAPH not in self.node) and
                                    (ID in self.node and len(self.node) == 1))):
            raise NotationError(f'Incomplete triple for node: {self.node}')
        self.nodes.append(self.node)
        self.reset()


class ReadGraph(ReadNodes):

    def consume(self, c: Char, prev_value) -> StateResult:
        if isinstance(prev_value, str) and prev_value != TYPE:
            raise NotationError(f'Directive not allowed in graph: {prev_value!r}')

        readnodes = cast(ReadNodes, self.parent)

        if self.expect_graph or self.pending == PENDING_OPEN_BRACE and c != '|':
            raise NotationError('Nested graphs are not allowed in TriG')

        if c == '}':
            if self.node is not None:
                if self.p is not None and prev_value is not None:
                    self.fill_node(prev_value)
                self.next_node()
            if readnodes.node is None:
                readnodes.nodes += self.nodes
            else:
                readnodes.node[GRAPH] = self.nodes
                readnodes.next_node()
            return readnodes, None
        else:
            return super().consume(c, prev_value)


def parse(inp: Input) -> object:
    state: ParserState = ReadNodes(None)
    value: object = None

    lno = 1
    cno = 1
    for c in cast(Iterable[Char], inp.characters()):
        if c == '\n':
            lno += 1
            cno = 0

        next_state: ParserState
        try:
            next_state, value = state.consume(c, value)
        except NotationError as e:
            raise ParserError(e, lno, cno) from None

        cno += 1

        if next_state is None:
            raise NotationError(f'Unexpected')

        state = next_state

    endstate, result = state.consume(EOF, value)

    return result


if __name__ == '__main__':
    import sys

    inp = Input(sys.argv[1]) if len(sys.argv) > 1 else Input()
    try:
        result = parse(inp)
    except ParserError as e:
        print(e, file=sys.stderr)
    else:
        print(json_encode(result, pretty=True))
