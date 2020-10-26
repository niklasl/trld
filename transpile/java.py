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
        ast.Eq: '({0} == null && ((Object) {1}) == null || {0} != null && {0}.equals({1}))',
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
        if node.level == 1:
            for name in node.names:
                if node.module is None:
                    continue
                assert name.asname is None
                name = Casing.camelize(name.name)
                if name == '*' or name[0].islower():
                    self.outln('import static ', self.package, '.', Casing.upper_camelize(node.module), '.', name, self.end_stmt)
                else:
                    self.outln('import ', self.package, '.', name, self.end_stmt)

    def map_isinstance(self, vrepr: str, classname: str):
        return f'{vrepr} instanceof {classname}'

    def map_for(self, container, ctype, part, parttype):
        if 'Map' in ctype:
            entry = part.replace(", ", "_")
            typedentry = f'Map.Entry<{parttype}> {entry}'
            parttypes = parttype.split(', ')
            parts = part.split(', ')
            stmts = [f'{parttypes[0]} {parts[0]} = {entry}.getKey()',
                     f'{parttypes[1]} {parts[1]} = {entry}.getValue()']
            nametypes = [(parts[0], parttypes[0]), (parts[1], parttypes[1])]
        else:
            typedentry = f'{parttype} {part}'
            stmts = []
            nametypes = [(part, parttype)]

        return f'for ({typedentry} : {self._cast(container)})', stmts, nametypes

    def map_attr(self, owner, attr, callargs=None):
        ownertype = self.gettype(owner) or ('Object', False)

        castowner = self._cast(owner, parens=True)

        if attr == 'join':# and ownertype[0] == 'String':
            return f'String.join({owner}, {callargs[0]})'

        elif attr == 'get' and 'Map' in ownertype[0] and len(callargs) == 2:
            return f'{self._cast(owner, parens=True)}.getOrDefault({callargs[0]}, {callargs[1]})'

        elif not callargs:
            if attr == 'sort' and 'List' in ownertype[0]:
                    return f'Collections.sort({owner})'

            if attr == 'copy' and 'Map' in ownertype[0]:
                    return f'new HashMap({owner})'

        if attr == 'items':# and 'Map' in ownertype[0]:
            member = 'entrySet'
        elif attr == 'keys':# and 'Map' in ownertype[0]:
            member = 'keySet'
        elif attr == 'update' and 'Map' in ownertype[0]:
            member = 'putAll'
        elif attr == 'pop':
            if 'Map' in ownertype[0] and len(callargs) == 2 and callargs[1] == 'null':
                callargs.pop(1)
            member = 'remove'
        elif attr == 'setdefault' and 'Map' in ownertype[0]:
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
                sizelength = 'size' if 'List' in ownertype[0] else 'length'
                key = f"{owner}.{sizelength}() {key.replace('-', '- ')}"
            if ownertype[0] == 'String':
                return f'{owner}.substring({key}, {key} + 1)'

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
            return f'{owner}.addAll({value})'
        return None

    def map_setitem(self, owner, key, value):
        assert self.gettype(owner)[0].startswith('Map')
        method = 'put' # if ismap else 'add'
        value = self._cast(value)
        return f'{self._cast(owner, parens=True)}.{method}({key}, {value})'

    def map_op_setitem(self, owner, key, op, value):
        value = self._cast(value)
        if isinstance(op, ast.Add):
            if self.gettype(owner)[0].startswith('Map'):
                return f'((List) {owner}.get({key})).addAll({value})'
        return None

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
            return f'trld.jsonld.Common.mapOf({data})'
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
        elt = self.repr_expr(gen.elt)
        item = self.repr_expr(g.target)
        iter = self.repr_expr(g.iter)

        view = ''
        ntype_narrowed = self.gettype(iter)
        if ntype_narrowed and 'Map' in ntype_narrowed[0]:
            view = '.keySet()'

        iter = self._cast(iter, parens=True)

        return f'{iter}{view}.stream().{method}({item} -> {elt})'

    def map_len(self, item: str) -> str:
        itemcast = self._cast(item, parens=True)
        itemtypeinfo = self.gettype(item)
        itemtype = itemtypeinfo[0] if itemtypeinfo else None
        return f"{itemcast}.{'length' if itemtype == 'String' else 'size'}()"


if __name__ == '__main__':
    JavaTranspiler().main()
