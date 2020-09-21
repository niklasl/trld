from typing import NamedTuple, Dict, List, Tuple, Union, Optional
import ast
from pathlib import Path
import sys


NAME_MAP = {
    'object': 'Object',
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

CONSTANT_MAP = {
    None: 'null',
    True: 'true',
    False: 'false',
}

OP_MAP =  {
    ast.Is: '==',
    ast.IsNot: '!=',
    ast.Lt: '<',
    ast.LtE: '<=',
    ast.Gt: '>',
    ast.GtE: '>=',
}

INDENT = '  '


class AssignCall(NamedTuple):
    owner: str
    method: str
    key: str


class Scope(NamedTuple):
    node: object
    typed: Dict[str, Tuple[str, bool]]


class Transpiler(ast.NodeVisitor):

    def __init__(self, outdir: str):
        super().__init__()
        self.outdir = outdir
        self.within: List[Scope] = []
        self._level = 0
        self.top: Dict[str, Tuple] = {}
        self.in_static = False
        self.staticname = 'Statics'
        self.statics: List[Tuple] = []
        self.classes: Dict[str, Dict[str, str]] = {}
        self._typing_names: Dict[str, str] = {}
        self._type_alias: Dict[str, str] = {}
        self._pre_stmts: Optional[List[str]] = None
        self._in_negation = False
        self._post_negation = None
        self.show_lineno = True

    def run(self, tree: ast.Module, src: str = None):
        if src:
            srcpath = Path(src)
            # TODO: Change back to just staticname + 'Common'?
            self.staticname = capital_camelize(srcpath.with_suffix('').parts[-1])
            self.package = str(srcpath.parent.with_suffix('')).replace('/', '.')
            self.filename = (Path(self.outdir) /
                    self.package.replace('.', '/') /
                    self.staticname).with_suffix('.java')
            print(f'Writing file: {self.filename}')
            self.filename.parent.mkdir(parents=True, exist_ok=True)
            self.outfile = self.filename.open('w')
            self.outln(f'package {self.package};')
            self.outln()

        self.stmt('//import javax.annotation.Nullable')
        self.stmt('import java.util.*')
        self.stmt('import java.util.stream.Stream')
        self.stmt('import java.util.stream.Collectors')
        self.stmt('import java.io.*')
        self.outln()
        self.visit(tree)
        self._staticout()
        if self.outfile:
            self.outfile.close()

    def _staticout(self, inclass=None):
        if inclass and inclass != self.staticname:
            return
        if self.statics:
            self.outln()
            if not inclass:
                self.outln('public class ' ,self.staticname, ' {')
            for args, kwargs in self.statics:
                self.outln(INDENT if args and not inclass else '', *args, **kwargs)
            if inclass:
                self.outln()
            else:
                self.outln('}')
            self.statics = []

    def outln(self, *parts, sep=None, end=None, continued=False, node=None):
        def out(*args, **kwargs):
            #if self.outfile:
            #    print(*args, **dict(kwargs, file=None))
            print(*args, **dict(kwargs, file=self.outfile))

        if self.in_static:
            out = lambda *args, **kwargs: self.statics.append((args, kwargs))
        if not parts:
            out()
        else:
            indent = '' if continued else INDENT * self._level
            lineno = self.note_lineno(node, eol=end is None)
            notes = (lineno,) if lineno else () 
            out(indent, *parts + notes, sep='', end=end)

    def stmt(self, *args, **kwargs):
        if self._pre_stmts:
            for pre_stmt in self._pre_stmts:
                self.outln(f'{pre_stmt};')
            self._pre_stmts = None
        self.outln(*args + (';',), **kwargs)

    def note_lineno(self, node, eol=True):
        if not self.show_lineno or not node or not isinstance(node, ast.AST):
            return None
        note = f'LINE: {node.lineno}'
        return f' // {note}' if eol else f'/* {note} */'

    def new_scope(self, node):
        scope = Scope(node, {})
        self.within.append(scope)
        return scope

    def enter_block(self, scope, *parts, end=None, continued=False, stmts=[], nametypes=[]):
        if not isinstance(scope, Scope):
            scope = self.new_scope(scope)

        self.outln(*parts + (' {',), node=scope.node, continued=continued)
        self._level += 1
        if 'class ' in parts[0]:
            self.classes[scope.node.name] = scope.typed
            self._staticout(inclass=parts[1])

        for argtype in nametypes:
            self.addtype(*argtype)

        for stmt in stmts:
            self.stmt(stmt)

        if isinstance(scope.node, list):
            for n in scope.node:
                self.visit(n)
        elif scope.node:
            self.generic_visit(scope.node)

        self.within.pop()
        self._level -= 1
        self.outln('}', end=end)

    def addtype(self, name: str, typename: str, narrowed=False):
        typename = typename.replace('/*@Nullable*/ ', '')
        if self.within:
            scope = self.within[-1]
            known = scope.typed.get(name)
            if known and known[0] != typename:
                narrowed = True
            scope.typed[name] = typename, narrowed
        else:
            self.top[name] = typename, narrowed

    def gettype(self, name):
        for scope in self.within[::-1]:
            if name in scope.typed:
                return scope.typed[name]

        if '.' in name:
            inclass = None
            owner, attr = name.split('.', 1)
            if owner == 'this':
                for scope in self.within[::-1]:
                    if isinstance(scope.node, ast.ClassDef):
                        inclass = scope.node.name
            else:
                ntype_narrowed = self.gettype(owner)
                if ntype_narrowed:
                    inclass = ntype_narrowed[0]

            classinfo = self.classes.get(inclass)
            if classinfo:
                return classinfo.get(attr)

        return self.top.get(name)

    def visit_Assert(self, node):
        self.stmt(f'assert {self.repr_expr(node.test)}') # node.msg

    def visit_Assign(self, node, annotation=None):
        ownerrefs = [self.repr_assignto(target) for target in node.targets]

        basename = node.value.value.id if isinstance(node.value, ast.Subscript) else None
        type_alias = self._typing_names.get(basename)
        if type_alias:
            rval = self.repr_expr(node.value, annot=True) if node.value else None
            if type_alias == 'Union':
                rval = 'Object'
            self._type_alias[ownerrefs[0]] = rval
        else:
            self._handle_Assign(node, ownerrefs)

    def visit_AugAssign(self, node):
        ownerref = self.repr_assignto(node.target)
        rval = self._cast(self.repr_expr(node.value))
        if isinstance(node.op, ast.Add):
            method = 'addAll'
            if isinstance(ownerref, AssignCall) and ownerref.method == 'put':
                self.stmt(f'((List) {ownerref.owner}.get({ownerref.key})).{method}({rval})')
            else:
                self.stmt(f'{ownerref}.{method}({rval})')
        else:
            raise NotImplementedError(f'unhandled: {(ast.dump(node))}')

    def visit_AnnAssign(self, node):
        typename = self.repr_annot(node.annotation)
        name = self.repr_annot(node.target)
        self._handle_Assign(node, name, typename)

    def _handle_Assign(self, node, ownerref, typename=None):
        rval = self.repr_expr(node.value) if node.value else None
        if isinstance(ownerref, list):
            ownerrefs, ownerref = ownerref, ownerref[0]
        else:
            ownerrefs = [ownerref]

        if not self.within:
            prefix = 'static '
            self.in_static = True
        else:
            prefix = ''

        if all(c == '_' or c.isupper() for c in ownerref):
            prefix += 'final '

        if typename:
            prefix += f'{typename} '

        if rval:
            rvalowner = rval.split('.', 1)[0]
            cast_rvalowner = self._cast(rvalowner, parens='.' in rval)
            if cast_rvalowner != rvalowner:
                rval = rval.replace(rvalowner, cast_rvalowner, 1)
            # TODO: judiciously apply casts for obvious types (only unless inferable!)
            #else:
            #    ownertype = self.gettype(ownerref) if isinstance(ownerref, str) else None
            #    if ownertype and prefix.startswith(ownertype[0]) and not rval.startswith('('):
            #        rval = f'({ownertype[0]}) {rval}'

        if isinstance(ownerref, tuple):
            ownerref, method, keyval = ownerref
            self.stmt(prefix, f'{self._cast(ownerref, parens=True)}.{method}({keyval}, {rval})', node=node)
        elif rval:
            self.stmt(prefix, ' = '.join(ownerrefs + [rval]), node=node)
        else:
            self.stmt(prefix, ownerref, node=node)

        if typename:
            self.addtype(ownerref, typename)

        if not self.within:
            self.in_static = False

        self.generic_visit(node)

    def visit_Expr(self, node):
        self.stmt(self.repr_expr(node.value), node=node)

    def visit_If(self, node, continued=False):
        scope = self.new_scope(node)
        orelse = node.orelse
        node.orelse = None
        test = self._thruthy(self.repr_expr(node.test))
        self.enter_block(scope, 'if (', test, ')',
                end=' ' if orelse else None,
                continued=continued)
        if orelse:
            self.check_after_negation(keep=True)
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                self.outln('else', end=' ', continued=True)
                self.visit_If(orelse[0], True)
            else:
                self.enter_block(orelse, 'else', continued=True)
        self.check_after_negation()

    def visit_Import(self, node):
        pass

    def visit_ImportFrom(self, node):
        # IMPROVE: Just verify standard names?
        if node.module == 'typing':
            self._typing_names = {
                name.asname or name.name: name.name
                for name in node.names
            }
        else:
            # TODO: also node.level 2 (e.g. `from ..base import *`)
            # TODO: [5f54c8e1] immediately call self.run(module_file_path)
            if node.level == 1:
                for name in node.names:
                    if node.module is None:
                        continue
                    assert name.asname is None
                    name = camelize(name.name)
                    if name == '*' or name[0].islower():
                        self.outln('import static ', self.package, '.', capital_camelize(node.module), '.', name, ';')
                    else:
                        self.outln('import ', self.package, '.', name, ';')

    def visit_For(self, node):
        scope = self.new_scope(node)
        container = self.repr_expr(node.iter)

        ctype, parttype = 'Object', 'Object'
        ctype_narrowed = self.gettype(container.rsplit('.', 1)[0])
        if ctype_narrowed:
            ctype, narrowed = ctype_narrowed
            if ctype.endswith('>'):
                ctype = ctype[:-1]
                ctype, parttype = ctype.split('<', 1)
        elif container.startswith('(') and '>' in container:
            ctype, parttype = container[1:container.rindex('>')].split('<', 1)


        part = self.repr_expr(node.target)
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

        self.enter_block(scope, 'for (', typedentry, ' : ', self._cast(container), ')',
                stmts=stmts, nametypes=nametypes)

    def visit_Break(self, node):
        self.stmt('break', node=node)

    def visit_Continue(self, node):
        self.stmt('continue', node=node)

    def visit_FunctionDef(self, node):
        prefix = 'public '
        if node.name.startswith('_') and not node.name.endswith('__'):
            prefix = 'protected '
        if not self.within or not isinstance(self.within[0].node, ast.ClassDef):
            self.in_static = True
            prefix += 'static '

        self.outln()

        scope = self.new_scope(node)
        # TODO: 5f55548d
        argdecls = []
        calls = []
        defaultcalls = []
        defaultsat = len(node.args.args) - len(node.args.defaults)
        # TODO: remove nametypes and just add (use new scope logic)
        nametypes = []

        for i, arg in enumerate(node.args.args):
            if arg.arg == 'self':
                continue

            aname = camelize(arg.arg)

            if arg.annotation:
                atype = self.repr_annot(arg.annotation)
            else:
                atype = NAME_MAP.get('object')

            if i >= defaultsat:
                default = node.args.defaults[i - defaultsat]
                call = calls[:] + [self.repr_expr(default)]
                defaultcalls.append((', '.join(argdecls[:]), ', '.join(call)))
                aval_name = default if isinstance(default, ast.Name) else type(default.value).__name__
                atype = NAME_MAP.get(aval_name, atype)

            calls.append(aname)

            argdecls.append(f'{atype} {aname}')
            nametypes.append((aname, atype))

        ret = self.repr_annot(node.returns) if node.returns else 'void'
        if ret == 'Boolean':
            ret = 'boolean'

        if ret:
            ret += ' '

        in_ctor = False
        if node.name == '__init__':
            name = self.within[-2].node.name
            ret = ''
            in_ctor = True
        elif node.name == '__repr__':
            return # IMPROVE:just drop these "debug innards"?
        elif node.name == '__str__':
            name = 'toString'
        elif node.name == '__eq__':
            name = 'equals'
        else:
            name = camelize(node.name)

        #for decorator in node.decorator_list:
        #    if isinstance(decorator, ast.Name) and decorator.id == 'property':
        #        name = f'get{name[0].upper()}{name[1:]}'

        if self.in_static:
            method = name
        elif in_ctor:
            method = 'this'
        else:
            method = f'this.{name}'
        doreturn = 'return ' if node.returns else ''
        for signature, call in defaultcalls:
            self.enter_block(None, prefix, ret, name, f'({signature})', stmts=[
                    f'{doreturn}{method}({call})'
            ])

        argrepr = ', '.join(argdecls)

        self.enter_block(scope, prefix, ret, name, f'({argrepr})', nametypes=nametypes)
        self.in_static = False

    def visit_Return(self, node):
        for scope in self.within[-1::-1]:
            if isinstance(scope.node, ast.FunctionDef) and not scope.node.returns:
                self.stmt('return', node=node)
                break
        else:
            self.stmt('return ', self._cast(self.repr_expr(node.value)), node=node)
        self.generic_visit(node)

    def visit_Raise(self, node):
        if isinstance(node.exc, ast.Call):
            self.stmt('throw ', self.repr_expr(node.exc), node=node)
        else:
            self.stmt('throw new ', self.repr_expr(node.exc), '()', node=node)
        self.generic_visit(node)

    def visit_Try(self, node):
        handlers = node.handlers
        node.handlers = None
        self.enter_block(node, 'try', end=' ')
        for handler in handlers:
            self.enter_block(handler, 'catch (Exception e)')

    def visit_ClassDef(self, node):
        self.outln()

        base = self.repr_expr(node.bases[0]) if node.bases else ''
        if base == 'NamedTuple':
            base = ''
        elif base:
            if base == 'Exception':
                base = 'RuntimeException'
            base = f' extends {base}'

        stmts = []
        # TODO: if derived from an Exception...
        if node.name.endswith('Error'):
            stmts.append(f'{node.name}() {{ }}')
            stmts.append(f'{node.name}(String msg) {{ super(msg); }}')

        if node.name == self.filename.with_suffix('').name:
            classdecl = 'public class '
        else:
            classdecl = 'class '

        self.enter_block(node, classdecl, node.name, base, stmts=stmts)

    def repr_annot(self, expr) -> str:
        return self.repr_expr(expr, annot=True)

    def repr_assignto(self, expr) -> Union[str, AssignCall]:
        if isinstance(expr, ast.Subscript):
            owner = self.repr_expr(expr.value)
            keyval = self.repr_expr(expr.slice.value) # type: ignore
            method = 'put' if self.gettype(owner)[0].startswith('Map') else 'add'
            return AssignCall(owner, method, keyval)
        else:
            return self.repr_expr(expr)

    def repr_expr(self, expr, annot=False, isowner=False, callargs=None) -> str:
        if isinstance(expr, ast.Str):
            s = expr.s.replace('"', r'\"')
            return expr.s if annot else f'"{s}"'

        elif isinstance(expr, ast.Num):
            return str(expr.n)

        elif isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub):
            return f'-{expr.operand.n}' # type: ignore

        elif isinstance(expr, (ast.Constant, ast.NameConstant, ast.Ellipsis)):
            if isinstance(expr, ast.Ellipsis) or expr.value is Ellipsis:
                return '/* ... */'
            return CONSTANT_MAP.get(expr.value, expr.value)

        if isinstance(expr, ast.Name):
            if expr.id == 'self':
                return 'this'
            name = self._type_alias.get(expr.id, expr.id)
            return NAME_MAP.get(name) or camelize(name)

        elif isinstance(expr, ast.Attribute):
            owner = self.repr_expr(expr.value, isowner=True)
            ownertype = self.gettype(owner) or ('Object', False)

            castowner = self._cast(owner, parens=True)

            if expr.attr == 'items':# and 'Map' in ownertype[0]:
                member = 'entrySet'
            elif expr.attr == 'keys':# and 'Map' in ownertype[0]:
                member = 'keySet'
            elif expr.attr == 'update' and 'Map' in ownertype[0]:
                member = 'putAll'
            elif expr.attr == 'pop':
                if 'Map' in ownertype[0] and len(callargs) == 2 and callargs[1] == 'null':
                    callargs.pop(1)
                member = 'remove'
            elif expr.attr == 'setdefault' and 'Map' in ownertype[0]:
                self._pre_stmts = [
                    f'if (!{castowner}.containsKey({callargs[0]})) '
                    f'{castowner}.put({callargs[0]}, {callargs.pop(1)})'
                ]
                member = 'get'
            elif expr.attr == 'append':
                if 'List' not in ownertype[0] and not castowner.startswith('('):
                    castowner = f'((List) {castowner})'
                member = 'add'
            elif expr.attr == 'isalpha':# and ownertype[0] == 'String':
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
                }.get(expr.attr, expr.attr)
            else:
                member = camelize(expr.attr)

            return f'{castowner}.{member}'

        elif isinstance(expr, ast.Call):
            return self._map_call(expr, isowner=isowner)

        elif isinstance(expr, ast.Subscript):
            return self._map_subscript(expr, annot=annot)

        elif isinstance(expr, ast.Compare):
            left = self.repr_expr(expr.left)
            op = expr.ops[0]
            right = ', '.join(self.repr_expr(c) for c in expr.comparators)
            contains = lambda: 'containsKey' if self.gettype(right) and self.gettype(right)[0].startswith('Map') else 'contains'
            castright = self._cast(right, parens=True)
            rightconstant = right.isupper() or right.startswith('"')
            if isinstance(op, ast.In):
                return f'{castright}.{contains()}({left})'
            elif isinstance(op, ast.NotIn):
                return f'!{castright}.{contains()}({left})'
            elif isinstance(op, ast.Eq):
                if right.isnumeric():
                    return f'{left} == {right}'
                if rightconstant:
                    return f'{right}.equals({left})'
                return f'{left}.equals({right})'
            elif isinstance(op, ast.NotEq):
                if right.isnumeric():
                    return f'{left} != {right}'
                if rightconstant:
                    return f'!{right}.equals({left})'
                return f'!{left}.equals({right})'
            else:
                ltype_narrowed = self.gettype(left)
                mop = OP_MAP[type(op)]
                if ('>' in mop or '<' in mop) and ltype_narrowed and ltype_narrowed[0] == 'String':
                    return f'{left}.compareTo({right}) {mop} 0'
                return f'{left} {mop} {right}'

        elif isinstance(expr, ast.IfExp):
            test = self._thruthy(self.repr_expr(expr.test))
            then = self._cast(self.repr_expr(expr.body))
            other = self._cast(self.repr_expr(expr.orelse))
            return f'({test} ? {then} : {other})'

        elif isinstance(expr, ast.Tuple):
            # TODO: self.on_block_enter_declarations = [...]
            return ', '.join(self.repr_expr(el) for el in expr.elts)

        elif isinstance(expr, ast.Dict):
            data = ', '.join(
                    f'{self.repr_expr(k)}, {self.repr_expr(expr.values[i])}'
                    for i, k in enumerate(expr.keys))
            if data:
                # TODO: decide whether to require imports of these base utils
                return f'trld.jsonld.Common.mapOf({data})'
            return f'new HashMap<>()'

        elif isinstance(expr, ast.BoolOp):
            if isinstance(expr.op, ast.And):
                joiner = ' && '
            elif isinstance(expr.op, ast.Or):
                joiner = ' || '
            boolexpr = joiner.join(
                    self._thruthy(self.repr_expr(self.check_after_negation(v, keep=True)))
                    for v in expr.values)
            # TODO: don't wrap in parens unless parent is BoolOp?
            return f'({boolexpr})' if len(expr.values) > 1 else boolexpr

        elif isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.Not):
                self._in_negation = True
                repr = f'!({self.repr_expr(expr.operand)})'
                self._in_negation = False
                return repr

        elif isinstance(expr, (ast.List, ast.Set)):
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
                lrepr = f'new ArrayList(Arrays.asList(new {eltype}[] {{{elems}}}))'
            else:
                lrepr = 'new ArrayList<>()'

            if isinstance(expr, ast.Set):
                return f'new HashSet({lrepr})'

            return lrepr

        elif isinstance(expr, ast.JoinedStr):
            return ' + '.join(
                    self.repr_expr(
                        v.value if isinstance(v, ast.FormattedValue)
                        else v)
                    for v in expr.values)

        elif isinstance(expr, ast.GeneratorExp):
            # TODO: just support GeneratorExp with any/all and list(?) comprehensions for map/filter...
            return ast.dump(expr)

        elif expr is None:
            return 'null'

        elif isinstance(expr, ast.BinOp):
            if isinstance(expr.op, ast.Add):
                lexpr = self.repr_expr(expr.left)
                ltype = self.gettype(lexpr)
                # TODO: the `or` is a hack since type inference is still too shallow
                if ltype and 'List' in ltype[0] or 'List' in lexpr:
                    return f'Stream.concat({lexpr}.stream(), {self.repr_expr(expr.right)}.stream()).collect(Collectors.toList())'
                bop = '+'
            elif isinstance(expr.op, ast.Sub):
                bop = '-'
            elif isinstance(expr.op, ast.Mult):
                bop = '+'
            elif isinstance(expr.op, ast.Div):
                bop = '/'
            return f'{self.repr_expr(expr.left)} {bop} {self.repr_expr(expr.right)}'

        raise NotImplementedError(f'unhandled: {(expr)}')

    def _map_call(self, expr: ast.Call, isowner=False):
        if isinstance(expr.func, ast.Name):
            funcname = expr.func.id
            # TODO: [5f55548d] handle or forbid kwargs
            if expr.keywords:
                print(f'WARNING: keywords in call: {ast.dump(expr)}', file=sys.stderr)
            if expr.args:
                arg0repr = self.repr_expr(expr.args[0])
                arg0cast = self._cast(arg0repr, parens=True)

            if funcname == 'isinstance':
                return self._map_isinstance(expr)
            elif funcname == 'len':
                arg0typeinfo = self.gettype(arg0repr)
                arg0type = arg0typeinfo[0] if arg0typeinfo else None
                return f"{arg0cast}.{'length' if arg0type == 'String' else 'size'}()"
            elif funcname == 'cast':
                arg0typerepr = self.repr_expr(expr.args[0], annot=True)
                castvalue = f'({arg0typerepr}) {self.repr_expr(expr.args[1])}'
                if isowner:
                    castvalue = f'({castvalue})'
                return castvalue

            do_map = {
                'any': self._map_any,
                'all': self._map_all,
                'str': (lambda expr: f'{arg0cast}.toString()'),
                'id': (lambda expr: f'{arg0cast}.hashCode()'),
            }.get(funcname)
            if do_map:
                return do_map(expr)

        callargs = [self._cast(self.repr_expr(arg)) for arg in expr.args]

        if isinstance(expr.func, ast.Attribute):
            owner = self.repr_expr(expr.func.value)
            ownertype = self.gettype(owner) or 'Object'

            if expr.func.attr == 'join':# and ownertype[0] == 'String':
                return f'String.join({owner}, {callargs[0]})'

            if expr.func.attr == 'get' and 'Map' in ownertype[0] and len(callargs) == 2:
                return f'{self._cast(owner, parens=True)}.getOrDefault({callargs[0]}, {callargs[1]})'

            if not callargs:
                if expr.func.attr == 'sort' and 'List' in ownertype[0]:
                        return f'Collections.sort({owner})'

                if expr.func.attr == 'copy' and 'Map' in ownertype[0]:
                        return f'new HashMap({owner})'

        name = self.repr_expr(expr.func, callargs=callargs)

        argrepr = ', '.join(callargs)

        if name in self.classes or name[0].isupper():
            return f'new {name}({argrepr})'
        else:
            return f'{name}({argrepr})'

    def _map_isinstance(self, expr):
        v = self.repr_expr(expr.args[0])

        if isinstance(expr.args[1], ast.Tuple):
            classes = (self.repr_expr(arg) for arg in expr.args[1].elts)
            return ' || '.join(f'{v} instanceof {c}' for c in classes)

        c = self.repr_expr(expr.args[1])
        if self._in_negation:
            self._post_negation = lambda: self.addtype(v, c, True)
        else:
            self.addtype(v, c, True)

        return f'{v} instanceof {c}'

    def _map_any(self, expr):
        assert expr.func.id == 'any'
        gen = expr.args[0]
        return self._map_generator(gen, 'anyMatch')

    def _map_all(self, expr):
        assert expr.func.id == 'all'
        gen = expr.args[0]
        return self._map_generator(gen, 'allMatch')

    def _map_generator(self, gen, method):
        assert isinstance(gen, ast.GeneratorExp)
        #print(ast.dump(gen))
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

    def _map_subscript(self, expr, annot):
        owner = self.repr_expr(expr.value, annot=annot)

        if isinstance(expr.slice, ast.Slice):
            lower = self.repr_expr(expr.slice.lower)
            if expr.slice.upper:
                upper = self.repr_expr(expr.slice.upper)
                if upper != '-1':
                    return f'{owner}.substring({lower}, {upper})'
            return f'{owner}.substring({lower})'

        sliceval = expr.slice.value
        if isinstance(sliceval, ast.Constant):
            tname = sliceval.value
        elif isinstance(sliceval, ast.Subscript):
            tname = self.repr_expr(sliceval, annot=annot)
        elif isinstance(sliceval, ast.Str):
            tname = sliceval.s if annot else self.repr_expr(sliceval)
        elif isinstance(sliceval, ast.Tuple):
            tname = ', '.join(self.repr_expr(p, annot=annot) for p in sliceval.elts)
        else:
            tname = self.repr_expr(sliceval, annot=annot)

        if isinstance(tname, int):
            tname = str(tname)

        if annot and isinstance(expr.value, ast.Name) and expr.value.id == 'Optional':
            return f'/*@Nullable*/ {tname}'

        if annot:
            if owner == 'Union':
                return 'Object'
            return f'{owner}<{tname}>'

        ownertype = self.gettype(owner)
        if ownertype:
            if tname.startswith('-'):
                sizelength = 'size' if 'List' in ownertype[0] else 'length'
                tname = f"{owner}.{sizelength}() {tname.replace('-', '- ')}"

            if ownertype[0] == 'String':
                return f'{owner}.substring({tname}, {tname} + 1)'

        return f'{self._cast(owner, parens=True)}.get({tname})'

    def _cast(self, name, parens=False):
        ntype_narrowed = self.gettype(name)
        if ntype_narrowed and ntype_narrowed[1]:
            result = f'({ntype_narrowed[0]}) {name}'
            if parens:
                result = f'({result})'
            return result
        return name

    def _thruthy(self, name, parens=False):
        ntype_narrowed = self.gettype(name)
        if ntype_narrowed and ntype_narrowed[0] != 'Boolean':
            result = f'{name} != null'
            if parens:
                result = f'({result})'
            return result
        return name

    def check_after_negation(self, o=None, keep=False):
        if self._post_negation and (keep or not self._in_negation):
            self._post_negation()
            if not keep:
                self._post_negation = None
        return o



def camelize(s: str) -> str:
    if s[0] == '_':
        s = s[1:]
    if not any(c.islower() for c in s):
        return s
    return ''.join(w.title() if i else w for i, w in enumerate(s.split('_')))


def capital_camelize(s: str) -> str:
    name = camelize(s)
    return name[0].upper() + name[1:]


def transpile(sources, outdir):
    transpiler = Transpiler(outdir)
    for src in sources:
        with open(src) as f:
            code = f.read()
        tree = ast.parse(code)
        transpiler.run(tree, src)


if __name__ == '__main__':
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument('source', nargs='+')
    argparser.add_argument('-o', '--output-dir')
    args = argparser.parse_args()

    transpile(args.source, args.output_dir)
