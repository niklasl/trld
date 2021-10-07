import ast
from typing import List, Tuple, Optional, Union, IO
from contextlib import contextmanager
from pathlib import Path
from .base import camelize, upper_camelize, under_camelize
from .cstyle import CStyleTranspiler


class JavaTranspiler(CStyleTranspiler):
    has_static = True
    typing = True
    inherit_constructor = False
    union_surrogate = 'Object'
    optional_type_form = '/*@Nullable*/ {0}'
    static_annotation_form = '/*@Static*/ {0}'
    public = 'public '
    constant = 'final '
    protected = 'protected '

    types = {
        'object': 'Object',
        'Exception': 'RuntimeException',
        'ValueError': 'NumberFormatException',
        'NotImplementedError': 'RuntimeException',
        'bool': 'Boolean',
        'str': 'String',
        'Char': 'String', #'Character',
        'int': 'Integer',
        'float': 'Double',
        'list': 'ArrayList',
        'List': 'List',
        'dict': 'HashMap',
        'Dict': 'Map',
        'OrderedDict': 'LinkedHashMap',
        'set': 'HashSet',
        'Set': 'Set',
        'Iterable': 'Iterable',
        'Tuple': 'Map.Entry',
        're.Pattern': 'Pattern'
    }

    constants = {
        None: ('null', 'Object'),
        True: ('true', 'Boolean'),
        False: ('false', 'Boolean'),
    }

    operators = {
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

    strcmp = '{0}.compareTo({1})'
    list_concat = 'Stream.concat({left}.stream(), {right}.stream()).collect(Collectors.toList())'

    function_map = {
        'str': '{0}.toString()',
        'int': ('Integer.valueOf({0})', 'Integer.valueOf({0}, {1}).intValue()'),
        'chr': 'Character.toString(((char) {0}))',
        'pow': 'Math.pow({0}, {1})',
        'type': '{0}.getClass()',
        'id': '{0}.hashCode()',
        'print': 'System.out.println({0})',
        'sorted': ('Builtins.sorted({0})', 'Builtins.sorted({0}, {1})', 'Builtins.sorted({0}, {1}, {2})'),
    }

    _current_imports: List[str]
    _prev_outfile: Optional[IO]

    @contextmanager
    def enter_file(self, srcpath: Path):
        # TODO: Change back to just staticname + 'Common'?
        self.staticname = upper_camelize(srcpath.with_suffix('').parts[-1])
        self.package = str(srcpath.parent.with_suffix('')).replace('/', '.')
        self.filename = (Path(self.outdir) /
                self.package.replace('.', '/') /
                self.staticname).with_suffix('.java')
        self._current_imports = []
        self._output_prelude()
        yield

    def visit_ClassDef(self, node):
        classname = self.map_name(node.name)
        currclass = self.filename.with_suffix('').name
        classfilepath = self.filename.parent / f'{classname}.java'

        if classfilepath == self.filename:
            super().visit_ClassDef(node)
            return

        self._prev_outfile = self.outfile
        self.outfile = classfilepath.open('w')
        print('Class file:', classfilepath)
        self._output_prelude()
        for impstr in self._current_imports:
            self.stmt(impstr)
        self.stmt(f'import static {self.package}.{currclass}.*')
        self.outln()
        super().visit_ClassDef(node)
        self.outfile.close()
        self.outfile = self._prev_outfile

    def _output_prelude(self):
        self.outln(f'package {self.package};')
        self.outln()
        self.stmt('//import javax.annotation.Nullable')
        self.stmt('import java.util.*')
        self.stmt('import java.util.regex.Pattern')
        self.stmt('import java.util.stream.Stream')
        self.stmt('import java.util.stream.Collectors')
        self.stmt('import java.io.*')
        self.stmt('import static java.util.AbstractMap.SimpleEntry')
        self.outln()
        self.stmt('import trld.Builtins')
        self.outln()

    def handle_import(self, node: ast.ImportFrom):
        for impname in node.names:
            if node.module is None:
                continue

            package = self.package.rsplit('.', node.level - 1)[0:1]
            modparts = node.module.split('.')
            package += modparts

            assert impname.asname is None
            name = camelize(impname.name)
            if name in self._type_alias:
                continue

            if name == '*' or name[0].islower() or \
                    all(c == '_' or c.isupper() or c.isdecimal() for c in name):
                importing = 'import static'
                namepath = package + [name]
                namepath[-2] = upper_camelize(namepath[-2])
            else:
                importing = 'import'
                if len(package) > 1: # collapse namespace a bit
                    package = package[:-1]
                namepath = package + [name]

            impstr = f"{importing} {'.'.join(namepath)}"
            self._current_imports.append(impstr)
            self.stmt(impstr)

    def cleantype(self, typename: Optional[str]) -> Optional[str]:
        if typename is None:
            return None
        typename = typename.replace('/*@Nullable*/ ', '')
        typename = typename.replace('/*@Static*/ ', '')
        return typename

    def typed(self, name, typename=None):
        return f'{typename} {name}' if typename else name

    def funcdef(self, name: str, argdecls: List[Tuple], ret: Optional[str] = None):
        argrepr = ', '.join(self.typed(arg[0], arg[2]) for arg in argdecls)

        if ret == '':
            return f'{name}({argrepr})'

        return f"{ret or 'void'} {name}({argrepr})"

    def map_isinstance(self, vrepr: str, classname: str):
        return f'{vrepr} instanceof {classname}'

    def map_assert(self, expr, failmsg):
        stmt = f'assert {expr}'
        if failmsg and failmsg != self.none:
            stmt += f' : {failmsg}'
        return stmt

    def map_for(self, container, ctype, part, parttype):
        stmts = []
        if self._is_map(ctype) or parttype.startswith('Map.Entry'):
            entry = part.replace(", ", "_")

            if self._is_map(ctype):
                typedentry = f'Map.Entry<{parttype}> {entry}'
                parttypes = parttype.split(', ', 1)
            else:
                typedentry = f'{parttype} {entry}'
                parttypes = self.container_type(parttype).contained.split(', ', 1)

            if ', ' in part:
                parts = part.split(', ', 1)
                stmts = [f'{parttypes[0]} {parts[0]} = {entry}.getKey()',
                        f'{parttypes[1]} {parts[1]} = {entry}.getValue()']
                nametypes = [(parts[0], parttypes[0]), (parts[1], parttypes[1])]
            else:
                typedentry = f'{parttypes[1]} {part}'
                nametypes = [(part, parttypes[1])]
        else:
            typedentry = f'{parttype} {part}'
            nametypes = [(part, parttype)]

        return f'for ({typedentry} : {self._cast(container)})', stmts, nametypes

    def map_for_to(self, counter, ceiling):
        ct = [(counter, 'int')]
        return f'for (int {counter} = 0; {counter} < {ceiling}; {counter}++)', [], ct

    def handle_with(self, expr, var):
        vartype = expr.split('(', 1)[0].replace('new ', '')
        self.enter_block(None, f'try ({vartype} {var} = {expr})', nametypes=[(var, vartype)])

    # TODO:
    #def map_name(self, name, callargs=None): ...

    def map_attr(self, owner, attr, callargs=None):
        ownertypeinfo = self.gettype(owner)
        ownertype = ownertypeinfo[0] if ownertypeinfo else 'Object'
        ownertype = self.cleantype(ownertype)

        castowner = self._cast(owner, parens=True)

        if attr == 'join':# and ownertype == 'String':
            return f'String.join({owner}, {callargs[0]})', 'String'

        elif attr == 'get' and self._is_map(ownertype) and len(callargs) == 2:
            return f'{self._cast(owner, parens=True)}.getOrDefault({callargs[0]}, {callargs[1]})'

        elif not callargs:
            if attr == 'sort' and self._is_list(ownertype):
                    return f'Collections.sort({owner})'

            if attr == 'reverse' and self._is_list(ownertype):
                    return f'Collections.reverse({owner})'

            if attr == 'copy' and self._is_map(ownertype):
                    return f'new HashMap({owner})'

        member = under_camelize(attr, self.protected == '_')
        rtype = None

        if attr == 'items':# and self._is_map(ownertype):
            member = 'entrySet'
        elif attr == 'keys':# and self._is_map(ownertype):
            member = 'keySet'
        elif attr == 'update' and self._is_map(ownertype):
            member = 'putAll'
        elif attr == 'pop':
            if self._is_map(ownertype):
                if len(callargs) == 2 and callargs[1] == 'null':
                    callargs.pop(1)
                member = 'remove'
            elif self._is_list(ownertype):
                member = 'remove'
        elif attr == 'setdefault' and self._is_map(ownertype):
            self._pre_stmts = [
                f'if (!{castowner}.containsKey({callargs[0]})) '
                f'{castowner}.put({callargs[0]}, {callargs.pop(1)})'
            ]
            member = 'get'
        elif attr == 'append':
            if self.typing and 'List' not in ownertype and not castowner.startswith('('):
                castowner = f'((List) {castowner})'
            member = 'add'
        elif attr == 'isalpha':# and ownertype == 'String':
            member = 'matches'
            callargs.append(r'"^\\w+$"')
        elif attr == 'isdecimal':# and ownertype == 'String':
            member = 'matches'
            callargs.append(r'"^\\d+$"')
        elif attr == 'isspace':# and ownertype == 'String':
            member = 'matches'
            callargs.append(r'"^\\s+$"')
        elif ownertype and ownertype == 'Pattern' and attr == 'match':
            v = callargs.pop()
            assert not callargs
            return f'({castowner}.matcher({v}).matches() ? {v} : null)'
        elif ownertype and ownertype == 'String':
            check = {
                'startswith': 'startsWith',
                'endswith': 'endsWith',
            }.get(attr)
            # TODO: would be less brittle not to hack up the tuple repr
            # (which might contain checks for ',')...
            if check and callargs[0].startswith('new SimpleEntry('):
                alts = ' || '.join(f'{castowner}.{check}({arg})' for arg in
                                   callargs[0][16:-1].split(', '))
                return f'({alts})'

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
            rtype = 'String'
        elif ownertype and ownertype == 'Double' and attr == 'is_integer':
            assert not callargs
            return f'({castowner} % 1 == 0)'

        if attr == '__init__':
            classdfn = self._within[-2].node
            assert isinstance(classdfn, ast.ClassDef) and owner == 'super()'
            obj = 'super'
        else:
            if owner == 'super()':
                castowner = 'super'
            obj = f'{castowner}.{member}'

        if callargs is not None:
            return f"{obj}({', '.join(callargs)})", rtype

        return obj, rtype

    def map_getitem(self, owner, key):
        ownertype = self.gettype(owner)

        # TODO: hack relying on an already cast owner
        if '(Map.Entry)' in owner or ownertype and ownertype[0].startswith('Map.Entry'):
            getter = 'getKey' if key == '0' else 'getValue'
            return f'{self._cast(owner, parens=True)}.{getter}()'

        if ownertype:
            key = self._get_upper_key(key, owner, ownertype)
            if ownertype[0] == 'String':
                return f'{self._cast(owner, parens=True)}.substring({key}, {key} + 1)'

        return f'{self._cast(owner, parens=True)}.get({key})'

    def map_getslice(self, owner, lower, upper=None):
        if lower == 'null':
            lower = '0'
        if upper:
            upper = self._get_upper_key(upper, owner)
            return f'{owner}.substring({lower}, {upper})'
        return f'{owner}.substring({lower})'

    def _get_upper_key(self, key, owner, ownertype=None):
        ownertype = ownertype or self.gettype(owner)
        if ownertype and key.startswith('-'):
            sizelength = 'size' if self._is_list(ownertype[0]) else 'length'
            return f"{self._cast(owner, parens=True)}.{sizelength}() {key.replace('-', '- ')}"
        return key

    def map_op_assign(self, owner, op, value):
        value = self._cast(value)
        if isinstance(op, (ast.Add, ast.Sub)):
            plusminus = '+' if isinstance(op, ast.Add) else '-'
            ownertype = self.gettype(owner)
            if ownertype[0] == 'Integer':
                return f'{owner} {plusminus}= {value}'
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
        reprs_types = [self.repr_expr_and_type(el) for el in expr.elts]
        elems = ', '.join(r for r, t in reprs_types)

        eltype = None
        for r, t in reprs_types:
            if eltype and eltype != t:
                eltype = None
                break
            eltype = t
        eltype = eltype or 'Object'

        ltype = f"List<{eltype}>"
        if elems:
            if '<' in eltype:
                arr = f'new Object[] {{{elems}}}'
            else:
                arr = f'new {eltype}[] {{({eltype}) {elems}}}'
            return f'new ArrayList<>(Arrays.asList({arr}))', ltype
        else:
            return 'new ArrayList<>()', ltype

    def map_dict(self, expr: ast.Dict):
        typed_kvs = [(self.repr_expr_and_type(k),
                      self.repr_expr_and_type(expr.values[i]))
                     for i, k in enumerate(expr.keys)]
        data = ', '.join(f'{k}, {v}' for (k, kt), (v, vt) in typed_kvs)

        if not data:
            return f'new HashMap<>()', 'Map'

        ktype, vtype = None, None
        for (k, kt), (v, vt) in typed_kvs:
            if ktype and ktype != kt:
                ktype = None
                break
            ktype = kt
            if vtype and vtype != vt:
                vtype = None
                break
            vtype = vt
        ktype = ktype or 'Object'
        vtype = vtype or 'Object'

        mtype = f'Map<{ktype}, {vtype}>'

        return f'trld.Builtins.mapOf({data})', mtype

    def map_set(self, expr: ast.Set):
        l, ltype = self.map_list(expr)
        return f'new HashSet({l})', ltype.replace('List', 'Set', 1)

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
        if ntypeinfo:
            containertype = self.container_type(ntypeinfo[0])
            if containertype:
                itemtype = containertype.contained.split(',')[0]

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
        #return (self.container_type(typerepr) or typerepr).endswith(('Map', 'HashMap'))
        return typerepr.split('<', 1)[0] in {'Map', 'HashMap'}

    def _is_list(self, typerepr: str) -> bool:
        #return (self.container_type(typerepr) or typerepr).endswith(('List', 'ArrayList'))
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

    def map_tuple(self, expr):
        parts = [self.repr_expr(el) for el in expr.elts]
        return f"new SimpleEntry({', '.join(parts)})"

    def unpack_tuple(self, expr, assignedto=None):
        parts = [self.repr_expr(el) for el in expr.elts]
        thetuple = '_'.join(parts)

        ttype = self.types['Tuple']
        p0type = 'Object'
        p1type = 'Object'

        if any(s in assignedto for s in ['.get(', '.remove(']): # assuming "get from collection" method
            ttype_narrowed = self.gettype(assignedto.split('.', 1)[0])
            if ttype_narrowed:
                ttype = ttype_narrowed[0]
                if ttype and '<' in ttype:
                    ttype = ttype.split('<', 1)[1][:-1]
        else:
            objpath = assignedto.split('(', 1)[0]
            ttype_narrowed = self.gettype(objpath)
            if ttype_narrowed:
                ttype = ttype_narrowed[0]

        containertype = self.container_type(ttype)
        if containertype:
            p0type, p1type = containertype.contained.split(', ')

        if not self.gettype(parts[0]):
            self.addtype(parts[0], p0type)
        else:
            p0type = None

        if not self.gettype(parts[1]):
            self.addtype(parts[1], p1type)
        else:
            p1type = None

        self._post_stmts = [
            f'{self.typed(parts[0], p0type)} = {thetuple}.getKey()',
            f'{self.typed(parts[1], p1type)} = {thetuple}.getValue()'
        ]

        return self.typed(thetuple, ttype), None # TODO: hack the spaghetti

    def map_listcomp(self, comp):
        r = self.repr_expr
        mapto = r(comp.elt)

        assert len(comp.generators) == 1
        gen = comp.generators[0]

        if isinstance(gen.target, ast.Tuple):
            parts = [r(el) for el in gen.target.elts]
            args = '_'.join(parts)
            mapto = mapto.replace(parts[0], f'{args}.getKey()')
            mapto = mapto.replace(parts[1], f'{args}.getValue()')
        else:
            args = r(gen.target)

        iter = self._cast(r(gen.iter), parens=True)

        if gen.ifs:
            assert len(gen.ifs) == 1
            optfilter = f'.filter(({args}) -> {r(gen.ifs[0])})'
        else:
            optfilter = ''

        mapcall = '' if args == mapto else f'.map(({args}) -> {mapto})'

        return f'{iter}.stream(){optfilter}{mapcall}.collect(Collectors.toList())'

    def map_dictcomp(self, comp):
        r = self.repr_expr

        assert len(comp.generators) == 1
        gen = comp.generators[0]

        iter = self._cast(r(gen.iter), parens=True)
        args = r(gen.target)

        if gen.ifs:
            assert len(gen.ifs) == 1
            optfilter = f'.filter(({args}) -> {r(gen.ifs[0])})'
        else:
            optfilter = ''

        gkey = self.map_lambda([args], r(comp.key))
        gval = self.map_lambda([args], r(comp.value))

        return f'{iter}.stream(){optfilter}.collect(Collectors.toMap({gkey}, {gval}))'

    def map_lambda(self, args, body):
        # TODO: hardcoded for the simplest case, else just ignoring
        if ',' not in body:
            return f"({', '.join(args)}) -> {body}"
        return self.none

    def new_regexp(self, callargs) -> Tuple[str, str]:
        args = ', '.join(callargs)
        return f'Pattern.compile({args})', 'Pattern'


if __name__ == '__main__':
    JavaTranspiler().main()
