from typing import List, Dict, Set, Optional, Iterable, Union, Tuple, ClassVar, cast
import re
from ..builtins import Char
from ..common import Input, dump_json
from ..jsonld.base import (
        VALUE, TYPE, LANGUAGE,
        ID, LIST, GRAPH,
        CONTEXT, VOCAB, BASE,
        PREFIX, PREFIX_DELIMS)
from ..rdfterms import RDF_TYPE, XSD, XSD_DOUBLE, XSD_INTEGER


ANNOTATION = '@annotation' # TODO: move to base (also from serializer)

XSD_DECIMAL: str = f'{XSD}decimal'

AT_KEYWORDS = {PREFIX, BASE}

RQ_PREFIX = 'prefix'
RQ_BASE = 'base'
RQ_GRAPH = 'graph'

RQ_KEYWORDS = {RQ_PREFIX, RQ_BASE, RQ_GRAPH}

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

TURTLE_INT_CHARS = re.compile(r'[+-.0-9]')

LITERAL_QUOTE_CHARS = {'"', "'"}

SYMBOL = '@symbol'
EOF = ''

StateResult = Tuple['ParserState', object]


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

    def consume(self, c: str, prev_value) -> StateResult:
        raise NotImplementedError


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
            if sym in self.context:
                sym = cast(str, self.context[VOCAB]) + sym
            return sym
        return value[ID]


class ConsumeWs(BaseParserState):

    MATCH: ClassVar[re.Pattern] = re.compile(r'\s')

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: str, prev_value) -> StateResult:
        if self.accept(c):
            return self, None
        else:
            return self.parent.consume(c, prev_value)


class ConsumeComment(BaseParserState):

    def consume(self, c: str, prev_value) -> StateResult:
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

    def backtrack(self, prev_c: str, c: str, value) -> StateResult:
        state, value = self.parent.consume(prev_c, value)
        return state.consume(c, value)


class ReadIRI(ReadTerm):

    MATCH: ClassVar[re.Pattern] = re.compile(r'\S') # TODO: specify better

    def init(self):
        self.escape_chars = {}

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: str, prev_value) -> StateResult:
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

    def consume(self, c: str, prev_value) -> StateResult:
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

        value: Union[str, bool, Dict] = self.pop()
        assert isinstance(value, str)

        last_dot = False
        if not just_escaped and value.endswith('.'):
            value = value[:-1]
            last_dot = True

        if value in {'true', 'false'}:
            value = cast(bool, value == 'true')
        elif value == 'a':
            value = TYPE
        elif value not in AT_KEYWORDS:
            lowered = value.lower()
            if lowered in RQ_KEYWORDS:
                value = lowered
            else:
                if value != '':
                    if ':' not in value:
                        raise NotationError(f'Expected PNname, got {value!r}')
                    elif value[0] == ':':
                        value = value[1:]
                value = cast(Dict, {SYMBOL: value})

        assert isinstance(value, object)

        if last_dot:
            return self.backtrack('.', c, value)

        return self.parent.consume(c, value)


class ReadNumber(ReadTerm):

    EXP = {'E', 'e'}

    whole: Optional[str]
    dot: Char
    exp: bool

    def init(self):
        self.whole = None
        self.dot = ''
        self.exp = False

    def consume(self, c: str, prev_value) -> StateResult:
        exp = c in self.EXP
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
                            self.whole is not None and c in self.EXP) or (
                                len(self.collected) > 0
                                and self.collected[-1] in self.EXP
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
            if number.is_integer():
                return {VALUE: value, TYPE: XSD_DOUBLE if self.exp else XSD_DECIMAL}
            return number
        else:
            if len(value) > 1 and TURTLE_INT_CHARS.match(value[0]) is not None:
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

    def consume(self, c: str, prev_value) -> StateResult:
        if self.value == '' and c == self.quotechar:
            self.multiline = 1
            self.value = None
            return self, None
        elif self.value is not None:
            if self.prev_dt_start:
                self.no_after_literal('Datatype', prev_value)
                if c == '^':
                    assert self.prev_dt_start == 1
                    self.prev_dt_start = 2
                    return self, None
                else:
                    assert self.prev_dt_start == 2
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
            if prev_value:
                if isinstance(prev_value, Dict) and LANGUAGE in prev_value:
                    value.update(prev_value)
                else:
                    assert isinstance(prev_value, Dict)
                    value[TYPE] = self.symbol(prev_value)

            return self.parent.consume(c, value)

        if self.handle_escape(c):
            return self, None

        if c == self.quotechar:
            if self.multiline == 0 or self.multiline == 3:
                self.multiline = 0
                self.value = self.pop()
            elif self.multiline > 0:
                self.multiline += 1
            return self, None

        if self.multiline > 1:
            for i in range(self.multiline - 1):
                self.collect(self.quotechar)
            self.multiline = 1

        self.collect(c)
        return self, None

    def no_after_literal(self, kind, prev_value):
        if prev_value is not None:
            raise NotationError(f'{kind} not allowed after {prev_value!r}')


class ReadLanguage(ReadTerm):

    MATCH: ClassVar[re.Pattern] = re.compile(r'[A-Za-z0-9-]') # TODO: only allow numbers in subtag

    def accept(self, c: Char) -> bool:
        return self.MATCH.match(c) is not None

    def consume(self, c: str, prev_value) -> StateResult:
        if self.accept(c):
            self.collect(c)
            return self, None
        else:
            value = self.pop()
            self.collected = []
            return self.parent.consume(c, {LANGUAGE: value})


class ReadCompound(BaseParserState):

    ws: ConsumeWs
    comment: ConsumeComment

    def __init__(self, parent: Optional[ParserState]):
        super().__init__(parent)
        self.ws = ConsumeWs(self)
        self.comment = ConsumeComment(self)

    def read_space(self, c: Char) -> Optional[StateResult]:
        if self.ws.accept(c):
            return self.ws, None
        elif c == '#':
            return self.comment, None
        else:
            return None

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

    def consume(self, c: str, prev_value) -> StateResult:
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

    def declare(self):
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


class ReadNode(ReadCompound):

    node: Optional[Dict]
    p: Optional[str]
    last_value: Optional[object]
    open_brace: bool = False

    def fill_node(self, value):
        if self.p is None:
            if value == TYPE:
                self.p = TYPE
            else:
                if not isinstance(value, Dict):
                    raise NotationError(f'Unexpected predicate: {value!r}')
                self.p = self.symbol(value)
        elif self.last_value is None:
            if self.p == TYPE:
                assert isinstance(value, Dict)
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
            last_value = self.last_value
            if self.p == TYPE:
                last_value = {TYPE: last_value}
            elif not isinstance(last_value, Dict):
                last_value = {VALUE: last_value}
            last_value[ANNOTATION] = value[ANNOTATION]
            if isinstance(self.node[self.p], List):
                l: List = self.node[self.p]
                l[-1] = last_value
            else:
                self.node[self.p] = last_value
        else:
            raise NotationError(f'Unexpected: {value!r}')

    def consume_node_char(self, c: str) -> StateResult:
        readspace = self.read_space(c)
        if readspace:
            return readspace

        if c == '{':
            self.open_brace = True
            return self, None
        elif c == '|':
            assert self.open_brace
            self.open_brace = False
            return ReadAnnotation(self), None
        elif c == '[':
            return ReadBNode(self), None
        elif c == '(':
            return ReadCollection(self), None
        elif c == ';':
            self.p = None
            self.last_value = None
            return self, None
        elif c == ',':
            self.last_value = None
            return self, None
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

    def consume(self, c: str, prev_value) -> StateResult:
        if prev_value is not None:
            self.fill_node(prev_value)

        if c == EOF:
            raise NotationError(f'Unexpected {c!r} in bnode.')
        elif c == ']':
            return self.parent, self.node
        else:
            return self.consume_node_char(c)


class ReadAnnotation(ReadBNode): # TODO: Factor out ReadNodeBase

    end_started: bool = False

    def consume(self, c: str, prev_value) -> StateResult:
        if prev_value is not None:
            self.fill_node(prev_value)

        if c == EOF:
            raise NotationError(f'Unexpected {c!r} in annotation.')
        elif not self.open_brace and c == '|':
            self.end_started = True
            return self, None
        elif c == '}':
            assert self.end_started
            self.end_started = False
            return self.parent, {ANNOTATION: self.node}
        else:
            return self.consume_node_char(c)


class ReadCollection(ReadCompound):

    nodes: List[object]

    def init(self):
        self.reset()

    def reset(self):
        self.nodes = []

    def consume(self, c: str, prev_value) -> StateResult:
        if prev_value is not None:
            self.nodes.append(self.compact_value(prev_value))

        readspace = self.read_space(c)
        if readspace:
            return readspace
        elif c == EOF:
            raise NotationError(f'Unexpected EOF in collection.')
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

    def consume(self, c: str, prev_value) -> StateResult:
        if prev_value is not None:
            if isinstance(prev_value, str):
                final_dot = False
                if prev_value in AT_KEYWORDS:
                    prev_value = prev_value[1:]
                    final_dot = True
                if prev_value == RQ_PREFIX:
                    return ReadPrefix(self, final_dot).consume(c, None)
                elif prev_value == RQ_BASE:
                    return ReadBase(self, final_dot).consume(c, None)
                elif prev_value == RQ_GRAPH:
                    self.expect_graph = True
                    return self, None

            if self.node is None:
                assert isinstance(prev_value, Dict)
                self.node = self.node_with_id(prev_value)
            else:
                if self.p is None and self.expect_graph and self.node is not None:
                    raise NotationError('Expected graph notation to follow, '
                                        f'got {prev_value!r}')
                self.fill_node(prev_value)

        if c == EOF:
            result = {CONTEXT: self.context, GRAPH: self.nodes}
            return self.parent, result
        elif c == '.' and (self.p is None or self.last_value is not None):
            self.next_node()
            return self, None
        else:
            if self.open_brace:
                if c != '|':
                    self.open_brace = False
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

    def consume(self, c: str, prev_value) -> StateResult:
        if isinstance(prev_value, str) and prev_value != TYPE:
            raise NotationError(f'Directive not allowed in graph: {prev_value!r}')

        readnodes = cast(ReadNodes, self.parent)

        if self.expect_graph or self.open_brace and c != '|':
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
            raise ParserError(e, lno, cno)

        cno += 1

        assert next_state is not None
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
        print(dump_json(result, pretty=True))
