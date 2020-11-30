import ast
from typing import Union
from contextlib import contextmanager
from pathlib import Path
from .base import Transpiler, Casing, under_camelize


class JavaTranspiler(Transpiler):

    class_based = True
    has_static = True
    typing = True
    union_surrogate = 'Object'
    optional_type_form = '/*@Nullable*/ {0}'
    public = 'public '
    constant = 'final '
    protected = 'protected '

    begin_block = ' {'
    end_block = '}'
    end_stmt = ';'

    this = 'this'
    none = 'null'

    types = {
        'object': 'Object',
        'Exception': 'RuntimeException',
        'bool': 'Boolean',
        'str': 'String',
        'int': 'Integer',
        'float': 'Double',
        'list': 'ArrayList',
        'List': 'List',
        'dict': 'HashMap',
        'Dict': 'Map',
        'set': 'HashSet',
        'Set': 'Set',
        'Iterable': 'Iterable',
    }

    constants = {
        None: 'null',
        True: 'true',
        False: 'false',
    }

    operators =  {
        ast.And: '&&',
        ast.Or: '||',
        ast.Is: '==',
        ast.IsNot: '!=',
        ast.Eq: '({0} == null && ((Object) {1}) == null || {0} != null && ({0}).equals({1}))',
        ast.NotEq: '!{0}.equals({1})',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>=',
    }

    indent = '  '

    strcmp = '{0}.compareTo({1})'
    list_concat = 'Stream.concat({left}.stream(), {right}.stream()).collect(Collectors.toList())'

    function_map = {
        'str': '{0}.toString()',
        'pow': 'Math.pow({0}, {1})',
        'type': '{0}.getClass()',
        'id': '{0}.hashCode()',
        'print': 'System.out.println({0})',
    }

    @contextmanager
    def on_file(self, srcpath: Path):
        # TODO: Change back to just staticname + 'Common'?
        self.staticname = Casing.upper_camelize(srcpath.with_suffix('').parts[-1])
        self.package = str(srcpath.parent.with_suffix('')).replace('/', '.')
        self.filename = (Path(self.outdir) /
                self.package.replace('.', '/') /
                self.staticname).with_suffix('.java')
        self.outln(f'package {self.package};')
        self.outln()
        self.stmt('//import javax.annotation.Nullable')
        self.stmt('import java.util.*')
        self.stmt('import java.util.stream.Stream')
        self.stmt('import java.util.stream.Collectors')
        self.stmt('import java.io.*')
        self.outln()
        yield

    def handle_import(self, node: ast.ImportFrom):
        # TODO: also node.level >= 2 (e.g. `from ..base import *`)
        if node.level == 1:
            for impname in node.names:
                if node.module is None:
                    continue
                assert impname.asname is None
                name = Casing.camelize(impname.name)
                if name[0].isupper():
                    continue # FIXME: just assumes class in same package;
                    # we need to write public classes as separate files.
                if name == '*' or name[0].islower():
                    self.outln('import static ', self.package, '.', Casing.upper_camelize(node.module), '.', name, self.end_stmt)
                else:
                    self.outln('import ', self.package, '.', name, self.end_stmt)

    def map_isinstance(self, vrepr: str, classname: str):
        return f'{vrepr} instanceof {classname}'

    def map_for(self, container, ctype, part, parttype):
        if self._is_map(ctype):
            entry = part.replace(", ", "_")
            typedentry = f'Map.Entry<{parttype}> {entry}'
            parttypes = parttype.split(', ', 1)
            parts = part.split(', ', 1)
            stmts = [f'{parttypes[0]} {parts[0]} = {entry}.getKey()',
                     f'{parttypes[1]} {parts[1]} = {entry}.getValue()']
            nametypes = [(parts[0], parttypes[0]), (parts[1], parttypes[1])]
        else:
            typedentry = f'{parttype} {part}'
            stmts = []
            nametypes = [(part, parttype)]

        return f'for ({typedentry} : {self._cast(container)})', stmts, nametypes

    # TODO:
    #def map_name(self, name, callargs=None): ...

    def map_attr(self, owner, attr, callargs=None):
        ownertype = self.gettype(owner) or ('Object', False)

        castowner = self._cast(owner, parens=True)

        if attr == 'join':# and ownertype[0] == 'String':
            return f'String.join({owner}, {callargs[0]})'

        elif attr == 'get' and self._is_map(ownertype[0]) and len(callargs) == 2:
            return f'{self._cast(owner, parens=True)}.getOrDefault({callargs[0]}, {callargs[1]})'

        elif not callargs:
            if attr == 'sort' and self._is_list(ownertype[0]):
                    return f'Collections.sort({owner})'

            if attr == 'reverse' and self._is_list(ownertype[0]):
                    return f'Collections.reverse({owner})'

            if attr == 'copy' and self._is_map(ownertype[0]):
                    return f'new HashMap({owner})'

        if attr == 'items':# and self._is_map(ownertype[0]):
            member = 'entrySet'
        elif attr == 'keys':# and self._is_map(ownertype[0]):
            member = 'keySet'
        elif attr == 'update' and self._is_map(ownertype[0]):
            member = 'putAll'
        elif attr == 'pop':
            if self._is_map(ownertype[0]) and len(callargs) == 2 and callargs[1] == 'null':
                callargs.pop(1)
            member = 'remove'
        elif attr == 'setdefault' and self._is_map(ownertype[0]):
            self._pre_stmts = [
                f'if (!{castowner}.containsKey({callargs[0]})) '
                f'{castowner}.put({callargs[0]}, {callargs.pop(1)})'
            ]
            member = 'get'
        elif attr == 'append':
            if self.typing and 'List' not in ownertype[0] and not castowner.startswith('('):
                castowner = f'((List) {castowner})'
            member = 'add'
        elif attr == 'isalpha':# and ownertype[0] == 'String':
            member = 'matches'
            callargs.append(r'"^\\w+$"')
        elif attr == 'isnumeric':# and ownertype[0] == 'String':
            member = 'matches'
            callargs.append(r'"^\\d+$"')
        elif ownertype and ownertype[0] == 'String':
            member = {
                'startswith': 'startsWith',
                'endswith': 'endsWith',
                'index': 'indexOf',
                'rindex': 'lastIndexOf',
                'find': 'indexOf',
                'rfind': 'lastIndexOf',
                'upper': 'toUpperCase',
                'lower': 'toLowerCase',
            }.get(attr, attr)
        else:
            member = under_camelize(attr, self.protected == '_')

        obj = f'{castowner}.{member}'

        if callargs is not None:
            return f"{obj}({', '.join(callargs)})"

        return obj

    def map_getitem(self, owner, key):
        ownertype = self.gettype(owner)
        if ownertype:
            if key.startswith('-'):
                sizelength = 'size' if self._is_list(ownertype[0]) else 'length'
                key = f"{owner}.{sizelength}() {key.replace('-', '- ')}"
            if ownertype[0] == 'String':
                return f'{self._cast(owner, parens=True)}.substring({key}, {key} + 1)'

        return f'{self._cast(owner, parens=True)}.get({key})'

    def map_getslice(self, owner, lower, upper=None):
        if lower == 'null':
            lower = '0'
        if upper:
            if upper != '-1':
                return f'{owner}.substring({lower}, {upper})'
        return f'{owner}.substring({lower})'

    def map_op_assign(self, owner, op, value):
        value = self._cast(value)
        if isinstance(op, ast.Add):
            ownertype = self.gettype(owner)
            if ownertype[0] == 'Integer':
                return f'{owner} += {value}'
            return f'{owner}.addAll({value})'
        return None

    def map_setitem(self, owner, key, value):
        assert self.gettype(owner)[0].startswith('Map')
        method = 'put' # if ismap else 'add'
        key = self._cast(key)
        value = self._cast(value)
        return f'{self._cast(owner, parens=True)}.{method}({key}, {value})'

    def map_op_setitem(self, owner, key, op, value):
        value = self._cast(value)
        if isinstance(op, ast.Add):
            if self.gettype(owner)[0].startswith('Map'):
                return f'((List) {owner}.get({key})).addAll({value})'
        return None

    def map_delitem(self, owner, key):
        assert self.gettype(owner)[0].startswith('Map')
        return f'{self._cast(owner, parens=True)}.remove({key})'

    def map_in(self, container, contained, negated=False):
        contains = 'containsKey' if self.gettype(container) and self.gettype(container)[0].startswith('Map') else 'contains'
        castcontainer = self._cast(container, parens=True)
        result = f'{castcontainer}.{contains}({contained})'
        if negated:
            return f'!{result}'
        return result

    def map_list(self, expr: Union[ast.List, ast.Set]):
        elems = ', '.join(self.repr_expr(el) for el in expr.elts)

        def is_string(el):
            if isinstance(el, ast.Str):
                return True
            if isinstance(el, ast.Name):
                eltype = self.gettype(self.repr_expr(el))
                if eltype:
                    return eltype[0] == 'String'
            return False

        eltype = 'String' if all(is_string(el) for el in expr.elts) else 'Object'
        if elems:
            return f'new ArrayList(Arrays.asList(new {eltype}[] {{{elems}}}))'
        else:
            return 'new ArrayList<>()'

    def map_dict(self, expr: ast.Dict):
        data = ', '.join(
                f'{self.repr_expr(k)}, {self.repr_expr(expr.values[i])}'
                for i, k in enumerate(expr.keys))
        if data:
            # TODO: decide whether to require imports of these base utils
            return f'trld.Common.mapOf({data})'
        return f'new HashMap<>()'

    def map_set(self, expr: ast.Set):
        return f'new HashSet({self.map_list(expr)})'

    def map_joined_str(self, expr: ast.JoinedStr):
        return super().map_joined_str(expr)

    def map_any(self, gen: ast.GeneratorExp):
        return self._map_generator(gen, 'anyMatch')

    def map_all(self, gen: ast.GeneratorExp):
        return self._map_generator(gen, 'allMatch')

    def _map_generator(self, gen, method):
        g = gen.generators[0]
        item = self.repr_expr(g.target)
        iter = self.repr_expr(g.iter)

        view = ''
        ntypeinfo = self.gettype(iter)
        if ntypeinfo and self._is_map(ntypeinfo[0]):
            view = '.keySet()'

        itemtype = None
        if ntypeinfo and ntypeinfo[0].endswith('>'):
            itemtype = ntypeinfo[0].split('<', 1)[-1][:-1].split(',')[0]

        self.new_scope()
        if itemtype:
            self.addtype(item, itemtype)
        elt = self.repr_expr(gen.elt)
        self.exit_scope()

        iter = self._cast(iter, parens=True )

        return f'{iter}{view}.stream().{method}({item} -> {elt})'

    def map_len(self, item: str) -> str:
        itemcast = self._cast(item, parens=True)
        itemtypeinfo = self.gettype(item)
        itemtype = itemtypeinfo[0] if itemtypeinfo else None
        return f"{itemcast}.{'length' if itemtype == 'String' else 'size'}()"

    def _is_map(self, typerepr: str) -> bool:
        return typerepr.split('<', 1)[0] in {'Map', 'HashMap'}

    def _is_list(self, typerepr: str) -> bool:
        return typerepr.split('<', 1)[0] in {'List', 'ArrayList'}

    def declare_iterator(self, iter_type):
        iter_name = 'iter'
        self._in_iterator = (iter_name, iter_type)
        return 'iterator', [
            f'List<{iter_type}> {iter_name} = new ArrayList()'
        ]

    def add_to_iterator(self, expr) -> str:
        return f'{self._in_iterator[0]}.add({self.repr_expr(expr)})'

    def add_all_to_iterator(self, expr) -> str:
        return f'{self._in_iterator[0]}.addAll({self.repr_expr(expr)})'

    def exit_iterator(self, node):
        self.stmt(f'return {self._in_iterator[0]}.iterator()')


if __name__ == '__main__':
    JavaTranspiler().main()
