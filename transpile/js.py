from pathlib import Path
from typing import Union
from contextlib import contextmanager
import ast
from .base import Transpiler, Casing, camelize, under_camelize


class JsTranspiler(Transpiler):

    class_based = True
    ctor = 'constructor'
    has_static = False
    typing = False
    optional_type_form = '{0}'

    public = 'export ' # FIXME: top_level_export
    constant = 'const '
    declaring = 'let '
    protected = '_'

    this = 'this'
    none = 'null'

    func_defaults = '{key} = {value}'

    class_casing = Casing.UpperCamelCase
    constant_casing = Casing.UPPER_SNAKE_CASE
    method_casing = Casing.lowerCamelCase
    name_casing = Casing.lowerCamelCase

    begin_block = ' {'
    end_block = '}'
    control_parens = True
    end_stmt = ''#';'

    keywords = {
        'for': 'for',
        'if': 'if',
        'elif': 'else if',
        'else': 'else',
        'while': 'while',
        'return': 'return',
        'raise': 'throw',
        'catch': 'catch',
    }

    types = {
        'object': 'Object',
        'Exception': 'Error',
        'bool': 'Boolean',
        'str': 'String',
        'int': 'Number',
        'float': 'Number',
        'list': 'Array',
        'List': 'Array',
        'dict': 'Map',
        'Dict': 'Map',
        'OrderedDict': 'Object',
        'set': 'Set',
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
        ast.Is: '===',
        ast.IsNot: '!==',
        ast.Eq: '==',
        ast.NotEq: '!=',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>=',
    }

    notmissing = '!= null'

    list_concat = '{left}.concat({right})'

    function_map = {
        'str': '{0}.toString()',
        'type': 'typeof {0}',
        'id': '{0}',
        'print': 'console.log({0})',
    }

    method_map = {
        'Object': {
            'get(a)': '[{a}]',
            ' in ': '{0} in {1}',
            ' not in ': '!({0} in {1})',
            'setdefault(a, b)': '[{a}] || ([{a}] = {b})',
        },
        'Set': {
            ' in ': '{0}.has({1})',
            ' not in ': '!{0}.has({1})',
        },
    }

    indent = '  '

    @contextmanager
    def enter_file(self, srcpath: Path):
        self._srcpath = srcpath
        fpath = '/'.join(srcpath.with_suffix('.js').parts[1:])
        self.filename = Path(self.outdir) / fpath
        self.stmt("'use strict'" + self.end_stmt)
        self.outln()
        yield

    def handle_import(self, node: ast.ImportFrom):
        if len(node.names) == 1 and node.names[0].name == '*' and self._modules:
            modpath = str((self._srcpath.parent / node.module).with_suffix(self._srcpath.suffix))
            names = ', '.join(self._modules[modpath])
        else:
            names = ', '.join(camelize(name.name) # type: ignore
                    for name in node.names
                    if node.module is not None and name.name not in self._type_alias)
        rel = '.' * node.level
        relmodpath = str(node.module).replace('.', '/') + '.js'
        self.outln(f"import {{ {names} }} from '{rel}/{relmodpath}'", self.end_stmt)

    def map_isinstance(self, vrepr: str, classname: str):
        if classname in {'String', 'Number', 'Boolean'}:
            return f"typeof {vrepr} === '{classname.lower()}'"
        if classname == 'Map':
            return f"{vrepr} !== null && typeof {vrepr} === 'object' && !Array.isArray({vrepr})"
        if classname == 'Array':
            return f"Array.isArray({vrepr})"
        return f'{vrepr} instanceof {classname}'

    def visit_Assert(self, node):
        self.stmt(f'// {self.repr_expr(node.test)}')

    def map_for(self, container, ctype, part, parttype):
        if 'Map' in ctype or container.endswith('.entrySet()'):
            container = container.replace('.entrySet()', '')
            key, val = part.split(', ')
            ktype, vtype = parttype.split(', ', 1)
            stmts = [f'let {val} = {container}[{key}]']
            nametypes = [(key, ktype), (val, vtype)]
            return f'for (let {key} in {container})', stmts, nametypes
        else:
            if ',' in part:
                part = f'[{part}]'
            return f'for (let {part} of {container})', [], [(part, parttype)]

    def map_name(self, name, callargs=None):
        if name == 'list':
            if not callargs:
                return '[]'
            return f'[].concat({callargs[0]})'
        elif name == 'dict':
            if not callargs:
                return '{}'
            return f'Object.assign({{}}, {callargs[0]})'

        return super().map_name(name, callargs)

    def map_attr(self, owner, attr, callargs=None):
        ownertype = self.gettype(owner) or ('Object', False)

        castowner = self._cast(owner, parens=True)

        ismaplike = 'Map' in ownertype[0].split('<', 1)[0]

        if attr == 'join':# and ownertype[0] == 'String':
            return f'{callargs[0]}.join({owner})'

        if attr == 'get' and (ismaplike or ownertype[0] == 'Object'):
            if len(callargs) == 1:
                return f'{self._cast(owner, parens=True)}[{callargs[0]}]'
            elif len(callargs) == 2:
                return f'({self._cast(owner, parens=True)}[{callargs[0]}] || {callargs[1]})'

        if not callargs:
            if attr == 'copy' and ismaplike:
                return f'Object.assign({{}}, {owner})'

        if attr == 'setdefault':# and 'Object' in ownertype[0]:
            a = castowner
            b = callargs[0]
            return f'{a}[{b}] || ({a}[{b}] = {callargs.pop(1)})'

        if attr == 'isalpha':# and ownertype[0] == 'String':
            return f'!!({castowner}.match(/^\w+$/))'

        if attr == 'items' and ismaplike:
            member = 'entrySet'
        elif attr == 'keys' and (ismaplike or ownertype[0] == 'Object'):
            return f'Object.keys({castowner})'
        elif attr == 'values' and ismaplike:
            return f'Object.values({castowner})'
        elif attr == 'update' and ismaplike:
            return f'Object.assign({castowner}, {callargs[0]})'
        elif attr == 'append':
            member = 'push'
        elif attr == 'pop':
            if ismaplike:# and len(callargs) == 2 and callargs[1] == 'null':
                access = f'{castowner}[{callargs[0]}]'
                self._post_stmts = [f'delete {access}']
                return access
            elif callargs and callargs[0] == '0':
                callargs.pop()
                member = 'shift'
            else:
                member = 'pop'
        elif attr == 'remove' and 'Set' in ownertype[0]:
            member = 'delete'
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

    def map_compare(self, left, op, right):
        if right == '[]':
            return f'Array.isArray({left}) && {left}.length === 0'

        if right == 'null': # for null or undefined
            if isinstance(op, ast.Is):
                op = ast.Eq()
            elif isinstance(op, ast.IsNot):
                op = ast.NotEq()

        if isinstance(op, ast.Eq):
            if right == 'null':
                return f'{left} == null'
            ltypeinfo = self.gettype(left)
            if ltypeinfo and ltypeinfo[0].startswith('Object'):
                return f'global.JSON.stringify({left}) === global.JSON.stringify({right})'
            if ltypeinfo and ltypeinfo[0].startswith('Array'):
                return f'Array.isArray({right}) && {left}.toString() === {right}.toString()'
            if ltypeinfo and ltypeinfo[0].startswith('Set'):
                return f'((l, r) => l === r || l !== null && r !== null && l.size === r.size && !Array.from(l).find(it => !r.has(it)))({left}, {right})'
        return super().map_compare(left, op, right)

    def map_getitem(self, owner, key):
        ownertype = self.gettype(owner)
        if ownertype:
            if key.startswith('-'):
                key = f"{owner}.length {key.replace('-', '- ')}"
            if ownertype[0] == 'String':
                return f'{owner}.substring({key}, {key} + 1)'

        return f'{owner}[{key}]'

    def map_getslice(self, owner, lower, upper=None):
        if lower == 'null':
            lower = '0'
        if upper:
            if upper != '-1':
                return f'{owner}.substring({lower}, {upper})'
        return f'{owner}.substring({lower})'

    def map_op_assign(self, owner, op, value):
        ownertype = self.gettype(owner)

        if ownertype[0] == 'Number':
            if isinstance(op, ast.Add):
                return f'{owner} += {value}'
            elif isinstance(op, ast.Sub):
                return f'{owner} -= {value}'

        if isinstance(op, ast.Add):
            return f'Array.prototype.push.apply({owner}, {value})'

        return None

    def map_setitem(self, owner, key, value):
        return f'{owner}[{key}] = {value}'

    def map_op_setitem(self, owner, key, op, value):
        if isinstance(op, ast.Add):
            if self.gettype(owner)[0].startswith('Map'):
                return f'Array.prototype.push.apply({owner}[{key}], {value})'
        return None

    def map_delitem(self, owner, key):
        assert self.gettype(owner)[0].startswith('Map')
        return f'delete {owner}[{key}]'

    def map_in(self, container, contained, negated=False):
        containertypeinfo = self.gettype(container)
        # String or List
        result = f'{container}.indexOf({contained}) > -1'

        if containertypeinfo:
            containertype = containertypeinfo[0]
            if containertype.startswith('Union'):
                # FIXME: something slipped through!
                containertype = 'Map'
        elif 'new Set' in container:
            containertype = 'Set'
        else:
            containertype = None

        if containertype:
            if containertype.startswith(('Map', 'Object')):
                result = f'Object.hasOwnProperty.call({container}, {contained})'
            elif containertype.startswith('Set'):
                result = f'{container}.has({contained})'
        if negated:
            return f'!({result})'
        return result

    def map_list(self, expr: Union[ast.List, ast.Set]):
        elems = ', '.join(self.repr_expr(el) for el in expr.elts)
        return f'[{elems}]'

    def map_dict(self, expr: ast.Dict):
        data = ', '.join(
                f'[{self.repr_expr(k)}]: {self.repr_expr(expr.values[i])}'
                for i, k in enumerate(expr.keys))
        return f'{{{data}}}'

    def map_set(self, expr: ast.Set):
        return f'new Set({self.map_list(expr)})'

    def map_joined_str(self, expr: ast.JoinedStr):
        return super().map_joined_str(expr)

    def map_any(self, gen: ast.GeneratorExp):
        iter, item, elt = self._repr_generator(gen)
        return f'{iter}.find({item} => {elt})'

    def map_all(self, gen: ast.GeneratorExp):
        iter, item, elt = self._repr_generator(gen)
        return f'!{iter}.find({item} => !({elt}))'

    def _repr_generator(self, gen):
        g = gen.generators[0]
        item = self.repr_expr(g.target)
        iter = self.repr_expr(g.iter)

        ntypeinfo = self.gettype(iter)
        if ntypeinfo:
            if ntypeinfo[0].startswith('Map'):
                iter = f'Object.keys({iter})'
            elif ntypeinfo[0].startswith('Set'):
                iter = f'Array.from({iter})'

        itemtype = None
        if ntypeinfo and ntypeinfo[0].endswith('>'):
            itemtype = ntypeinfo[0].split('<', 1)[-1][:-1].split(',')[0]

        self.new_scope()
        if itemtype:
            self.addtype(item, itemtype)
        elt = self.repr_expr(gen.elt)
        self.exit_scope()

        return iter, item, elt

    def map_len(self, item: str) -> str:
        itype_narrowed = self.gettype(item)
        if itype_narrowed:
            if itype_narrowed[0].startswith('Set'):
                return f'{item}.size'
            elif itype_narrowed[0].startswith('Map'):
                return f'Object.keys({item}).length'
        return f'{item}.length'

    def declare_iterator(self, iter_type):
        return '*[Symbol.iterator]', []

    def add_to_iterator(self, expr) -> str:
        return f'yield {self.repr_expr(expr)}'

    def add_all_to_iterator(self, expr) -> str:
        return f'yield* {self.repr_expr(expr)}'

    def exit_iterator(self, node):
        pass

    def map_tuple(self, expr, assignedto=None):
        parts = [self.repr_expr(el) for el in expr.elts]
        return f"[{', '.join(parts)}]"

    def unpack_tuple(self, expr, assignedto=None):
        parts = [self.repr_expr(el) for el in expr.elts]
        ttype = None

        for sep in ('.', '['):
            if sep in assignedto: # assuming "get from collection" method
                ttype_narrowed = self.gettype(assignedto.split(sep, 1)[0])
                if ttype_narrowed:
                    ttype = ttype_narrowed[0].split('<', 1)[1][:-1]
                    break
        else:
            ttype_narrowed = self.gettype(assignedto)
            if ttype_narrowed:
                ttype = ttype_narrowed[0]

        print(ttype, assignedto.split('[', 1)[0])
        if ttype:
            p0type, p1type = ttype.split('<', 1)[1][:-1].split(', ')
            self.addtype(parts[0], p0type)
            self.addtype(parts[1], p1type)
        assert self.gettype(parts[0])
        trepr = f"[{', '.join(parts)}]"

        return trepr

    def map_listcomp(self, comp):
        r = self.repr_expr
        mapto = r(comp.elt)
        assert len(comp.generators) == 1
        gen = comp.generators[0]
        args = r(gen.target)
        iter = r(gen.iter)
        if gen.ifs:
            assert len(gen.ifs) == 1
            optfilter = f'.filter(({args}) => {r(gen.ifs[0])})'
        else:
            optfilter = ''
        mapcall = '' if args == mapto else f'.map(({args}) => {mapto})'
        return f'{iter}{optfilter}{mapcall}'

    def map_lambda(self, args, body):
        return f"({', '.join(args)}) => {body}"


if __name__ == '__main__':
    JsTranspiler().main()
