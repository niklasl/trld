from pathlib import Path
from typing import Union, List, Tuple, Optional, Callable
from contextlib import contextmanager
import ast
from .base import Transpiler
from .java import JavaTranspiler


# FIXME: not really rust stuff; just to get some code out to boot...
MAPSTARTS = ('Map', 'HashMap', 'Option<HashMap')


class RustTranspiler(JavaTranspiler):
    indent = ' ' * 4
    classdfn = 'impl '
    if_stmt = 'if (%s)'
    while_stmt = 'while (%s)'
    ctor = 'new'
    this = 'self'
    selfarg = '&self'
    has_static = False
    inherit_constructor = True
    public = 'pub '
    constant = 'const '
    protected = ''
    declaring = 'let mut '
    optional_type_form = None

    types = {
        'object': 'Object',
        'Exception': 'Err',
        'ValueError': 'NumberFormatErr', # TODO
        'NotImplementedError': 'Err',
        'Optional': 'Option',
        'bool': 'bool',
        'str': 'String',
        'Char': 'char',
        'int': 'int32',
        'float': 'f64',
        'list': 'Vec',
        'List': 'Vec',
        'dict': 'HashMap',
        'Dict': 'HashMap', # TODO: no common trais for Hash/BTree!
        'OrderedDict': 'BTreeMap',
        'set': 'HashSet',
        'Set': 'HashSet',
        'Iterable': 'Iterable',
        'Tuple': 'Tuple',
        're.Pattern': 'regex::Regex'
    }

    constants = {
        None: ('None', 'Option'),
        True: ('true', 'bool'),
        False: ('false', 'bool'),
    }

    operators = {
        ast.And: '&&',
        ast.Or: '||',
        ast.Is: '==',
        ast.IsNot: '!=',
        ast.Eq: '==',
        ast.NotEq: '!=',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>=',
    }

    def enter_block(self, scope, *parts, end=None, continued=False,
            stmts=[], nametypes=[], on_exit: Optional[Callable] = None):
        if 'class ' in parts[0]:
            l = list(parts)
            l[0] = l[0].replace('class ', 'impl ', 1)
            parts = tuple(l)
        super().enter_block(scope, *parts,
                            end=end, continued=continued, stmts=stmts, on_exit=on_exit)

    def to_var_name(self, name):
        return name

    def to_attribute_name(self, attr):
        return attr[1:] if attr.startswith('_') else attr

    def typed(self, name, typename=None):
        return f'{name}: {typename}' if typename and self.typing else name

    def funcdef(self, name: str, argdecls: List[Tuple], ret: Optional[str] = None):
        argrepr = ', '.join(
                arg[0] if arg[0] == self.selfarg else self.typed(arg[0], arg[2])
                for arg in argdecls)
        if not ret:
            return f'fn {name}({argrepr})'
        return f'fn {name}({argrepr}) -> {ret}'

    def overload(self, name, args, ret=None):
        return self.funcdef(f'{name}{len(args) - 1}', args, ret)

    def visit_ClassDef(self, node):
        Transpiler.visit_ClassDef(self, node)

    @contextmanager
    def enter_file(self, srcpath: Path):
        self._srcpath = srcpath
        fpath = '/'.join(srcpath.with_suffix('.rs').parts[1:])
        self.filename = Path(self.outdir) / fpath
        self.stmt(f"mod {self.filename.with_suffix('').name}")
        self.outln()
        yield

    def map_for(self, container, ctype, part, parttype):
        stmts = []
        if self._is_map(ctype) or parttype.startswith('Map.Entry'):
            entry = part.replace(", ", "_")

            if self._is_map(ctype):
                parttypes = parttype.split(', ', 1)
            else:
                parttypes = self.container_type(parttype).contained.split(', ', 1)

            if ', ' in part:
                parts = part.split(', ', 1)
                stmts = [f'{parttypes[0]} {parts[0]} = {entry}.getKey()',
                        f'{parttypes[1]} {parts[1]} = {entry}.getValue()']
                nametypes = [(parts[0], parttypes[0]), (parts[1], parttypes[1])]
            else:
                nametypes = [(part, parttypes[1])]
        else:
            nametypes = [(part, parttype)]

        return f'for {part} in {self._cast(container)}', stmts, nametypes

    def map_for_to(self, counter, ceiling):
        ct = [(counter, 'u32')]
        return f'for {counter} in 0..{ceiling}', [], ct

    def handle_import(self, node: ast.ImportFrom):
        if len(node.names) == 1 and node.names[0].name == '*' and self._modules:
            modpath = str((self._srcpath.parent / node.module).with_suffix(self._srcpath.suffix))
            names = ', '.join(name for name, ntype in self._modules[modpath].items()
                              if ntype and not name.startswith('__'))
        else:
            names = ', '.join(name.name # type: ignore
                    for name in node.names
                    if node.module is not None and name.name not in self._type_alias)
        rel = '.' * node.level
        modpath = str(node.module).replace('.', '::')
        self.outln(f'use {modpath}::{{ {names} }}', self.end_stmt)

    def repr_cast(self, type, expr) -> str:
        return expr

    def _cast(self, name, parens=False, lvaltype=None):
        return name

    def map_isinstance(self, vrepr: str, classname: str):
        # TODO: there is no instanceof, match on struct!
        return f'{vrepr} instanceof {classname}'

    def map_list(self, expr: Union[ast.List, ast.Set]):
        reprs_types = [self.repr_expr_and_type(el) for el in expr.elts]
        elems = ', '.join(r for r, t in reprs_types)

        eltype = None
        for r, t in reprs_types:
            if eltype and eltype != t:
                eltype = None
                break
            eltype = t
        eltype = eltype or 'Object'

        ltype = f'Vec<{eltype}>'
        return f'vec![{elems}]', ltype

    def map_tuple(self, expr):
        parts = [self.repr_expr(el) for el in expr.elts]
        return f"({', '.join(parts)})"

    def new_regexp(self, callargs) -> Tuple[str, str]:
        args = ', '.join(callargs)
        return f'regex::Regex.new({args}).unwrap()', 'regex::Regex'

    def map_op_assign(self, owner, op, value):
        value = self._cast(value)
        if isinstance(op, (ast.Add, ast.Sub)):
            plusminus = '+' if isinstance(op, ast.Add) else '-'
            ownertype = self.gettype(owner)
            if ownertype and ownertype[0] == 'Integer':
                return f'{owner} {plusminus}= {value}'
            return f'{owner}.addAll({value})'
        return None

    def map_setitem(self, owner, key, value):
        typeinfo = self.gettype(owner)
        if key.isdigit():
            method = 'add'
        elif key.startswith('-') and key[1:].isdigit():
            method = 'set'
            key = f'{owner}.size() - 1'
        else:
            if typeinfo:
                assert typeinfo[0].startswith(MAPSTARTS)
            method = 'put' # if ismap else 'add'

        key = self._cast(key)
        value = self._cast(value)
        return f'{self._cast(owner, parens=True)}.{method}({key}, {value})'

    def map_op_setitem(self, owner, key, op, value):
        value = self._cast(value)
        typeinfo = self.gettype(owner)
        if isinstance(op, ast.Add):
            if typeinfo and typeinfo[0].startswith(MAPSTARTS):
                return f'((List) {owner}.get({key})).addAll({value})'
        return None

    def map_delitem(self, owner, key):
        typeinfo = self.gettype(owner)
        if typeinfo:
            assert typeinfo[0].startswith(MAPSTARTS)
        return f'{self._cast(owner, parens=True)}.remove({key})'


if __name__ == '__main__':
    RustTranspiler().main()
