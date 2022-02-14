from typing import Callable, Dict, List, NamedTuple, Optional, Union, cast
import re

from ..common import Output, uuid4
from ..jsonld.base import (BASE, CONTEXT, GRAPH, ID, INDEX, LANGUAGE, LIST,
                           REVERSE, TYPE, VALUE, VOCAB)

StrObject = Dict[str, object]
StrOrObject = Union[str, StrObject]

ANNOTATION = '@annotation'

WORD_START = re.compile(r'^\w*$')
PNAME_LOCAL_ESC = re.compile(r"([~!$&'()*+,;=/?#@%]|^[.-]|[.-]$)")


class Settings(NamedTuple):
    indent_chars: str = '  '
    upcase_keywords: bool = False
    use_graph_keyword: bool = True
    space_before_semicolon: bool = True
    predicate_repeat_new_line: bool = True
    bracket_start_new_line: bool = False
    bracket_end_new_line: bool = False
    list_item_new_line: bool = True
    prologue_end_line: int = 1
    separator_lines: int = 1


class KeyAliases(NamedTuple):
    id: str = ID
    value: str = VALUE
    type: str = TYPE
    lang: str = LANGUAGE
    graph: str = GRAPH
    list_: str = LIST
    reverse: str = REVERSE
    index_: str = INDEX
    annotation: str = ANNOTATION


def serialize(
    data: StrObject,
    out: Output = None,
    context: Optional[Dict] = None,
    base_iri: Optional[str] = None,
    settings: Settings = None,
):
    out = out if out is not None else Output()
    settings = settings if settings is not None else Settings()
    state = SerializerState(out, settings, context, base_iri)
    state.serialize(data)


class SerializerState:
    settings: Settings
    out: Output
    parent: Optional['SerializerState']
    context: StrObject
    base_iri: Optional[str]
    prefixes: Dict[str, str]
    aliases: KeyAliases
    bnode_skolem_base: Optional[str] = None
    prefix_keyword: str
    base_keyword: str
    graph_keyword: Optional[str] = None
    unique_bnode_suffix: str
    bnode_counter: int

    def __init__(
            self,
            out: Output,
            settings: Settings,
            context: Optional[Dict],
            base_iri: Optional[str] = None,
            parent: 'SerializerState' = None,
    ):
        self.out = out if out is not None else cast(SerializerState, parent).out
        self.init_context(context)
        self.base_iri = base_iri
        self.parent = parent
        self.settings = parent.settings if parent is not None else settings
        self.prefix_keyword = self._kw('prefix')
        self.base_keyword = self._kw('base')
        if self.settings.use_graph_keyword:
            self.graph_keyword = self._kw('graph')
        self.unique_bnode_suffix = ''
        self.bnode_counter = 0

    def _kw(self, s: str) -> str:
        return s.upper() if self.settings.upcase_keywords else s

    def init_context(self, context: Optional[StrObject]):
        self.aliases = KeyAliases()
        if context is None:
            self.context = {}
        else:
            for key in self.context.keys():
                raise Exception('context already initialized')
        ctx: StrObject = {}
        # TODO: merge arrays, deref uri:s ...
        if isinstance(context, List):
            for item in context:
                ctx.update(cast(StrObject, item))
        elif isinstance(context, Dict):
                ctx.update(context)
        self.context = ctx
        self.prefixes = collect_prefixes(context)

    def serialize(self, data: Dict):
        ctx: object = data.get(CONTEXT)
        if isinstance(ctx, Dict):
            self.init_context(cast(StrObject, ctx))
        self.prelude(self.prefixes)
        graph: object = data if isinstance(data, List) else data.get(GRAPH)
        if graph:
            for node in as_list(graph):
                self.object_to_turtle(cast(StrObject, node))
        else:
            self.object_to_turtle(data)

    def prelude(self, prefixes: Dict[str, str]):
        for k, v in prefixes.items():
            if k == BASE:
                self.write_base(v)
            else:
                self.writeln(f'{self.prefix_keyword} {k}: <{v}>')
        if self.base_iri:
            self.write_base(self.base_iri)
        if self.settings.prologue_end_line > 1:
            self.writeln()

    def write_base(self, iri: str):
        self.writeln(f'{self.base_keyword} <{iri}>')

    def is_list_container(self, term: str) -> bool:
        if self.context is not None:
            termdef: object = self.context.get(term)
            if isinstance(termdef, Dict):
                return termdef['@container'] == '@list'

        return False

    def is_lang_container(self, term: str) -> bool:
        if self.context is not None:
            termdef: object = self.context.get(term)
            if isinstance(termdef, Dict):
                return termdef['@container'] == '@language'

        return False

    def object_to_trig(self, iri: Optional[str], graph: object):
        self.writeln()
        if iri == None:
            self.writeln("{")
        else:
            if self.graph_keyword:
                    self.write(f'{self.graph_keyword} ')
            self.writeln(f'{self.ref_repr(iri)}:')
        for node in as_list(graph):
            self.object_to_turtle(cast(StrObject, node), 0, GRAPH)
        self.writeln()
        self.writeln("}")

    def object_to_turtle(
            self,
            obj: object,
            depth: int = 0,
            via_key: Optional[str] = None,
    ) -> List[StrObject]:
        if depth > 0 and isinstance(obj, Dict) and CONTEXT in obj:
            # TODO: use SerializerState(node[CONTEXT], None, None, state)
            raise Exception('Nested context not supported yet')

        if via_key and self.is_lang_container(via_key) and isinstance(obj, Dict):
            first = True
            for lang, value in cast(StrObject, obj).items():
                if not first:
                    self.write(' , ')
                self.to_literal(
                 { self.aliases.value: value, self.aliases.lang: lang },
                    via_key)
                first = False
            return []

        if not isinstance(obj, Dict) or self.aliases.value in obj:
            self.to_literal(cast(object, obj), via_key)
            return []

        explicit_list: bool = self.aliases.list_ in obj

        if via_key and self.is_list_container(via_key):
            obj = { self.aliases.list_: obj }

        s = cast(Optional[str], obj.get(self.aliases.id))

        is_list: bool = self.aliases.list_ in obj
        started_list: bool = is_list

        is_bracketed: bool = is_list or via_key == self.aliases.annotation

        if self.aliases.graph in obj:
            if CONTEXT in obj:
                self.prelude(collect_prefixes(cast(StrObject, obj[CONTEXT])))
            self.object_to_trig(s, obj[self.aliases.graph])
            return []

        if explicit_list:
            self.write('( ')

        in_graph_add: int = 1 if via_key == GRAPH else 0

        if s is not None and self.has_keys(obj, 2):
            if depth == 0:
                self.writeln()
            if in_graph_add > 0:
                self.write(self.get_indent(0))
            self.write(self.ref_repr(s))
        elif depth > 0:
            if not is_bracketed:
                depth += 1
                self.write("[")
        else:
            return []

        indent = self.get_indent(depth + in_graph_add)

        nested_depth: int = depth + 1 + in_graph_add

        top_objects: List[StrObject] = []

        first = True
        ended_list = False

        for key, vo in cast(StrObject, obj).items():
            term = self.term_for(key)

            rev_key: Optional[str] = self.rev_key_for(key) if term == None else None
            if term is None and rev_key is None:
                continue

            if term == self.aliases.id or term == "@context":
                continue

            if term == self.aliases.index_:
                continue

            if term == self.aliases.annotation:
                continue

            vs: List = vo if isinstance(vo, List) else [vo] if vo is not None else []
            vs = cast(List, [x for x in vs if x is not None])

            if len(vs) == 0: # TODO: and not @list
                continue

            in_list: bool = is_list or self.is_list_container(key)

            rev_container: Optional[StrObject] = None
            if term == self.aliases.reverse:
                rev_container = cast(Optional[StrObject], obj[key])
            elif rev_key:
                rev_container = { rev_key: obj[key] }

            if rev_container:
                for revkey, rvo in rev_container.items():
                    vs = rvo if isinstance(rvo, List) else [rvo] if rvo is not None else []
                    for x in vs:
                        top_objects.append(
                            self.make_top_object(s, revkey, cast(StrObject, x))
                        )
            else:
                use_indent = indent
                if first:
                    use_indent = ' '
                    first = False
                else:
                    if started_list and not in_list and not ended_list:
                        ended_list = True
                        self.write(" )")
                    self.writeln(" ;")

                assert isinstance(term, str)

                if term == self.aliases.type:
                    term = "a"

                if term != '@list':
                    term = self.to_valid_term(term)
                    self.write(use_indent + term + " ")

                for i in range(len(vs)):
                    v: object = vs[i]

                    if in_list:
                        if not started_list:
                            self.write("(")
                            started_list = True
                        self.write(" ")
                    elif i > 0:
                        if self.settings.predicate_repeat_new_line:
                            self.writeln(' ,')
                            self.write(self.get_indent(nested_depth))
                        else:
                            self.write(' , ')

                    if self.bnode_skolem_base and isinstance(v, Dict) and self.aliases.id not in v:
                        s = self.gen_skolem_id()
                        v[self.aliases.id] = s

                    if term == "a":
                        t = self.repr_type(cast(StrOrObject, v))
                        self.write(t)
                    elif v and isinstance(v, Dict) and self.aliases.id in v:
                        top_objects.append(v)
                        self.write(self.ref_repr(v[self.aliases.id]))
                    elif v is not None:
                        objects = self.object_to_turtle(v, nested_depth, key)
                        for it in objects:
                            top_objects.append(it)

                    self.output_annotation(v, depth)

        if explicit_list or (not is_list and started_list) and not ended_list:
            self.write(" )")

        if depth == 0:
            if not first:
                self.writeln(" .")
            #self.writeln()
            for it in top_objects:
                self.object_to_turtle(it, depth, via_key)
            return []
        else:
            indent = self.get_indent(nested_depth - (1 + in_graph_add))
            if self.settings.bracket_end_new_line:
                self.writeln()
                self.write(indent)
            else:
                self.write(' ')
            if not is_bracketed:
                # NOTE: hack for e.g. BlazeGraph
                #if not self.has_keys(obj) and self.settings.mark_empty_bnode:
                #    self.writeln(f'a {self.settings.empty_marker}')
                #    self.write(indent)
                self.write("]")
            return top_objects

    def output_annotation(self, v: object, depth: int):
        if isinstance(v, Dict) and self.aliases.annotation in v:
            annotation: StrObject = v[self.aliases.annotation]
            self.write(':|')
            self.object_to_turtle(annotation, depth + 2, self.aliases.annotation)
            self.write('|}')

    def to_literal(
        self,
        obj: object,
        via_key: Optional[str] = None,
        write: Callable = None, # [[str], None]
    ):
        if write is None:
            write = lambda s: self._write(s)
        value = obj
        lang: Optional[object] = self.context.get("@language")
        datatype: Optional[str] = None
        if isinstance(obj, Dict):
            value = obj.get(self.aliases.value)
            datatype = cast(str, obj.get(self.aliases.type))
            lang = obj.get(self.aliases.lang)
        else:
            kdef: Optional[StrObject] = None
            if via_key is not None and via_key in self.context:
                kdef = cast(StrObject, self.context[via_key])
            coerce_to: Optional[str] = None
            if isinstance(kdef, Dict) and "@type" in kdef:
                coerce_to = cast(str, kdef["@type"])
            if coerce_to == "@vocab":
                next = False
                for v in as_list(value):
                    if next:
                        write(' , ')
                    else:
                        next = True
                    write(self.ref_repr(v, True) if isinstance(v, str) else str(v))
                return
            elif coerce_to == "@id":
                next = False
                for v in as_list(value):
                    if next:
                        write(' , ')
                    else:
                        next = True
                    write(self.ref_repr(v))
                return
            elif coerce_to:
                datatype = coerce_to
            else:
                if isinstance(kdef, Dict) and "@language" in kdef:
                    lang = kdef["@language"]

        next = False
        for v in as_list(value):
            if next:
                write(' , ')
            else:
                next = True

            if isinstance(v, str):
                escaped = v.replace('\\', '\\\\')
                quote = '"'
                if escaped.find('\n') > -1:
                    quote = '"""'
                    if escaped.endswith('"'):
                        escaped = f'{escaped[0 : len(escaped) - 1]}\\"'
                else:
                    escaped = escaped.replace('"', '\\"')
                write(quote)
                write(escaped)
                write(quote)
                if datatype:
                    write("^^" + self.to_valid_term(cast(str, self.term_for(datatype))))
                elif isinstance(lang, str):
                    write(f"@{lang}")
            else: # boolean or number
                write(str(v))

    def term_for(self, key: str) -> Optional[str]:
        if key.startswith("@"):
            return key
        elif key.find(":") > -1 or \
                             key.find('/') > -1 or \
                             key.find('#') > -1:
            return key
        elif key in self.context:
            kdef = self.context[key]
            if kdef is None:
                return None
            term = None
            if isinstance(kdef, Dict):
                term = kdef.get("@id", key)
            else:
                term = kdef
            if term is None:
                return None
            assert isinstance(term, str)
            ci: int = term.find(":")
            return f":{term}" if ci == -1 else term
        else:
            return ":" + key

    def rev_key_for(self, key: str) -> Optional[str]:
        kdef = self.context[key]
        if isinstance(kdef, Dict) and "@reverse" in kdef:
            return cast(str, kdef["@reverse"])
        return None

    def make_top_object(self, s: Optional[str], rev_key: str, it: Dict) -> StrObject:
        node = dict(it)
        # TODO: probe object to find an id:d top object...
        if self.aliases.id not in node:
            node[self.aliases.id] = f'_:bnode-{self.bnode_counter}'
            self.bnode_counter += 1
        node[rev_key] = { self.aliases.id: s }
        return node

    def repr_type(self, t: StrOrObject) -> str:
        tstr: str = t if isinstance(t, str) else cast(str, cast(Dict, t)['@type']) # assuming annotation form
        return self.to_valid_term(cast(str, self.term_for(tstr)))

    def ref_repr(self, refobj: Optional[StrOrObject], use_vocab = False) -> str:
        if refobj is None:
            return '[]'

        if isinstance(refobj, Dict) and self.aliases.id in refobj:
            return self.repr_triple(refobj)

        ref = cast(str, refobj)

        c_i: int = ref.find(':')
        if c_i > -1:
            pfx = ref[0 : c_i]
            if pfx == "_":
                node_id: str = ref + self.unique_bnode_suffix
                if self.bnode_skolem_base:
                    ref = self.bnode_skolem_base + node_id[2 :]
                else:
                    return self.to_valid_term(node_id)
            elif pfx in self.context:
                local = ref[c_i + 1 :]
                return f'{pfx}:{self.escape_pname_local(local)}'
        elif use_vocab and ref.find("/") == -1:
            return ":" + ref

        if VOCAB in self.context and ref.startswith(cast(str, self.context[VOCAB])):
            return ":" + ref[len(cast(str, self.context[VOCAB])) :]

        ref = self.clean_value(ref)

        c_i = ref.find(':')
        if c_i > -1:
            pfx = ref[0 : c_i]
            rest = ref[c_i :]
            if pfx in self.context:
                return ref
            # non-std: check if ref is "most likely" a pname
            if len(self.context) > 0 and \
                    rest.find(':') == -1 and \
                    WORD_START.match(rest) is not None and \
                    WORD_START.match(pfx) is not None:
                return ref

        return f'<{ref}>'

    def repr_triple(self, ref: StrObject) -> str:
        s: str = self.ref_repr(cast(str, ref[self.aliases.id]))

        p: str = ''
        obj: StrOrObject = ''
        for k in ref.keys():
            if k == self.aliases.id:
                continue
            if p is not None:
                raise Exception('Quoted triples cannot contain multiple statements')

            p = self.term_for(k)
            obj = cast(StrObject, ref[k])

        o: str
        if p == self.aliases.type:
            p = "a"
            o = self.repr_type(obj)
        else:
            if isinstance(obj, List):
                raise Exception('Quoted triples must have one single object')
            if self.is_lang_container(p) and isinstance(obj, Dict):
                raise Exception('Language containers not yet supported in quoted triples')
            if isinstance(obj, Dict) and self.aliases.list_ in obj:
                raise Exception('Quoted triples cannot contain Lists')

            if not isinstance(obj, Dict) or self.aliases.value in obj:
                l: List[str] = []
                self.to_literal(obj, p, lambda x: l.append(cast(str, x)))
                o = ''.join(l)
            else:
                o = self.ref_repr(obj)

        return f'<< {s} {p} {o} >>'

    def to_valid_term(self, term: str) -> str:
        term = self.clean_value(term)
        c_i: int = term.find(':')
        pfx: Optional[str] = term[0 : c_i] if c_i > -1 else None
        if (
                not (pfx in self.context) and
                # non-std: fake pnames even when missing prefixes!
                (term.find('/') > -1 or
                 term.find('#') > -1 or
                 pfx is not None and term.rfind(':') > len(pfx))
        ):
            return f'<{term}>'
        if pfx is not None:
            local = term[c_i + 1 :]
            return f'{pfx}:{self.escape_pname_local(local)}'
        return self.escape_pname_local(term)

    def has_keys(self, obj: StrObject, at_least: int = 1) -> bool:
        seen = 0
        for k in obj.keys():
            if k != self.aliases.annotation:
                seen += 1
                if seen == at_least:
                    return True
        return False

    def clean_value(self, v: str) -> str:
        return v

    def escape_pname_local(self, pnlocal: str) -> str:
        # From: https://www.w3.org/TR/turtle/#grammar-production-PN_LOCAL_ESC
        # Note that '.-' are OK within, but need escaping at start/end.
        # And '_' *may* be escaped but is OK everywhere in PN_LOCAL.
        return PNAME_LOCAL_ESC.sub(r'\\\1', pnlocal)

    def gen_skolem_id(self) -> Optional[str]:
        if self.bnode_skolem_base is None:
            return None
        return self.bnode_skolem_base + uuid4()

    def get_indent(self, depth: int) -> str:
        chunks: List[str] = []
        i = -1
        while i < depth:
            i += 1
            chunks.append(self.settings.indent_chars)
        return ''.join(chunks)

    def write(self, s: str):
        self.out.write(s if s is not None else '')

    def writeln(self, s: Optional[str] = None):
        self.out.write((s if s is not None else '') + '\n')

    # TODO: for transpile (refactor to avoid passing a write function above)
    def _write(self, s) -> Optional[str]:
        self.write(cast(str, s))
        return None


def collect_prefixes(context: Optional[Dict]) -> Dict[str, str]:
    if not isinstance(context, Dict):
        return {}

    prefixes = {}
    for key, value in cast(StrObject, context).items():
        # TODO: verify JSON-LD 1.1 prefix rules
        if isinstance(value, str) and value[-1] in {'#', '/', ':'}:
            prefixes['' if key == VOCAB else key] = value
        elif isinstance(value, Dict) and value.get('@prefix') == True:
            prefixes[key] = value[ID]

    return prefixes


def as_list(value) -> List:
    return value if isinstance(value, List) else [value]