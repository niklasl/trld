# TODO:
# * [5f54c8e1] Use module data from TypeScanner, remove duplicate
#   logic and factor out remaining _visitor from Transpiler.
# * [5f76eae2] Improve isinstance checking (top-level bool, reset at or?).
# * [5f831dc1] Clear out java-specific code.
from typing import NamedTuple, Dict, List, Tuple, Union, Optional, Callable, Iterator
from enum import Enum, auto
from contextlib import contextmanager
from collections import OrderedDict
from pathlib import Path
import ast
import re
import sys

from .typescanner import TypeScanner, ClassType, FuncType


__all__ = 'Transpiler', 'Casing'


def camelize(s: str) -> str:
    if s[0] == '_':
        s = s[1:]
    uscore_i = s.find('_')
    if uscore_i > -1 and all(c.isupper() for c in s[:uscore_i - 1]):
        return s
    if not any(c.islower() for c in s):
        return s
    return ''.join(w.title() if i else w for i, w in enumerate(s.split('_')))


def upper_camelize(s: str) -> str:
    name = camelize(s)
    return name[0].upper() + name[1:]


def under_camelize(s: str, under: bool) -> str:
    if under and s.startswith('_') and not s.endswith('_'):
        return f'_{camelize(s)}'
    return camelize(s)


class Casing(Enum):
    UpperCamelCase = auto()
    lowerCamelCase = auto()
    UPPER_SNAKE_CASE = auto()
    lower_snake_case = auto()


class Scope(NamedTuple):
    node: object
    typed: Dict[str, Tuple[str, bool]]


class Transpiler(ast.NodeVisitor):
    #_visitor: ast.NodeVisitor
    typing: bool # or typecheck_implies_casts...
    union_surrogate: Optional[str] = None
    optional_type_form: Optional[str] = None
    begin_block: str
    end_block: str
    ctor: Optional[str] = None
    #call_keywords = AsDict
    func_defaults: Optional[str] = None
    this: str
    protected = ''
    none: str
    constants: Dict
    operators: Dict
    types: Dict
    strcmp: Optional[str] = None
    notmissing: Optional[str] = None
    list_concat: Optional[str] = None
    function_map: Dict[str, Optional[str]]

    indent: str

    outdir: str

    def __init__(self, outdir: str = None):
        super().__init__()
        self.in_static = False
        self.staticname = 'Statics'
        self.statics: List[Tuple] = []

        self._modules = None
        self._module = None
        self.classes: Dict[str, Dict[str, str]] = {}
        self._iterables: Dict[str, str] = {}

        self._top: Dict[str, Tuple] = {}
        self._within: List[Scope] = []
        self._level = 0
        self._typing_names: Dict[str, str] = {}
        self._type_alias: Dict[str, str] = {}
        self._pre_stmts: Optional[List[str]] = None
        self._post_stmts: Optional[List[str]] = None
        self._in_negation = False
        self._post_negation = None
        self.show_lineno = True

        if outdir is None:
            import argparse
            self.argparser = argparse.ArgumentParser()
            self.argparser.add_argument('source', nargs='+')
            self.argparser.add_argument('-o', '--output-dir')
        else:
            self.outdir = outdir

    def main(self, sources=None):
        if not sources and self.argparser:
            args = self.argparser.parse_args()
            self.outdir = args.output_dir
            sources = args.source

        typescanner = TypeScanner(self)
        for src in sources:
            typescanner.read(src)

        for src, mod in typescanner.modules.items():
            with open(src) as f:
                code = f.read()
            tree = ast.parse(code)
            self._modules = typescanner.modules
            self._module = typescanner.modules[src]
            self._transpile(tree, src)

    def _transpile(self, tree: ast.Module, src: str):
        srcpath = Path(src)
        with self.enter_file(srcpath):
            self.visit(tree)

        self._staticout()
        if self.outfile:
            self.outfile.close()

    @property
    def filename(self) -> Path:
        return Path(self.outfile.name)

    @filename.setter
    def filename(self, filename):
        filename = Path(filename)
        print(f'Writing file: {filename}')
        filename.parent.mkdir(parents=True, exist_ok=True)
        self.outfile = filename.open('w')

    def _staticout(self, inclass=None):
        if inclass and inclass != self.staticname:
            return
        if self.statics:
            self.outln()
            if not inclass:
                self.outln(f'{self.public}class ', self.staticname, self.begin_block)
            for args, kwargs in self.statics:
                self.outln(self.indent if args and not inclass else '', *args, **kwargs)
            if inclass:
                self.outln()
            else:
                self.outln(self.end_block)
            self.statics = []

    def outln(self, *parts, sep=None, end=None, continued=False, node=None):
        def out(*args, **kwargs):
            print(*args, **dict(kwargs, file=self.outfile))

        if self.in_static:
            out = lambda *args, **kwargs: self.statics.append((args, kwargs))
        if not parts:
            out()
        else:
            indent = '' if continued else self.indent * self._level
            lineno = self.note_lineno(node, eol=end is None)
            notes = (lineno,) if lineno else () 
            out(indent, *parts + notes, sep='', end=end)

    def stmt(self, *args, **kwargs):
        if self._pre_stmts:
            for stmt in self._pre_stmts:
                self.outln(f'{stmt}{self.end_stmt}')
            self._pre_stmts = None
        self.outln(*args + (self.end_stmt,), **kwargs)
        if self._post_stmts:
            for stmt in self._post_stmts:
                self.outln(f'{stmt}{self.end_stmt}')
            self._post_stmts = None

    def note_lineno(self, node, eol=True):
        if not self.show_lineno or not node or not isinstance(node, ast.AST):
            return None
        note = f'LINE: {node.lineno}'
        # TODO: 5f831dc1 (java-specific)
        return f' // {note}' if eol else f'/* {note} */'

    def new_scope(self, node=None):
        scope = Scope(node, OrderedDict())
        self._within.append(scope)
        return scope

    def exit_scope(self):
        self._within.pop()

    def enter_block(self, scope, *parts, end=None, continued=False, stmts=[], nametypes=[], on_exit: Optional[Callable] = None):
        if not isinstance(scope, Scope):
            scope = self.new_scope(scope)

        if '\n' not in self.begin_block:
            parts += (self.begin_block,)
        self.outln(*parts, node=scope.node, continued=continued)
        if self.begin_block.startswith('\n'):
            self.outln(self.begin_block[1:])
        self._level += 1
        if 'class ' in parts[0]:
            self.classes[parts[1]] = scope.typed
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

        if on_exit:
            on_exit()

        self.exit_scope()
        self._level -= 1
        self.outln(self.end_block, end=end)

    def addtype(self, name: str, typename: str, narrowed=False):
        # TODO: 5f831dc1 (java-specific)
        typename = typename.replace('/*@Nullable*/ ', '')
        if self._within:
            scope = self._within[-1]
            known = scope.typed.get(name)
            if known and known[0] != typename:
                narrowed = True
            scope.typed[name] = typename, narrowed
        else:
            self._top[name] = typename, narrowed

    def gettype(self, name):
        for scope in self._within[::-1]:
            if isinstance(scope.node, ast.ClassDef):
                break
            if name in scope.typed:
                return scope.typed[name]

        if '.' in name:
            inclass = None
            owner, attr = name.split('.', 1)
            if owner == self.this:
                for scope in self._within[::-1]:
                    if isinstance(scope.node, ast.ClassDef):
                        inclass = scope.node.name
            else:
                ntype_narrowed = self.gettype(owner)
                if ntype_narrowed:
                    inclass = ntype_narrowed[0]

            classinfo = self.classes.get(inclass)
            if classinfo:
                return classinfo.get(attr)

        call = name.split('(', 1)[0] if '(' in name and name.endswith(')') else None
        # TODO: check '.' and get ClassType if so.
        # Also define lang-based "builtin" ClassTypes
        dfn = self._module.get(call)
        if dfn:
            if isinstance(dfn, FuncType):
                return dfn.returns, False

        return self._top.get(name)

    def visit_Assert(self, node):
        # TODO: 5f831dc1 (java-specific)
        self.stmt(f'assert {self.repr_expr(node.test)}') # node.msg

    def visit_Assign(self, node, annotation=None):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
            target = node.targets[0]
            owner = self.repr_expr(target.value)
            key = self.repr_expr(target.slice.value)
            rval = self.repr_expr(node.value)
            self.stmt(self.map_setitem(owner, key, rval), node=node)
            return

        if not self._handle_type_alias(node):
            rval = self.repr_expr(node.value)
            ownerrefs = [self.repr_expr(target, assignedto=rval) for target in node.targets
                        if not isinstance(target, ast.Subscript)]
            assert len(ownerrefs) == len(node.targets)
            self._handle_Assign(node, ownerrefs, rval)

    def _handle_type_alias(self, node) -> bool:
        if not isinstance(node.value, ast.Subscript) or not isinstance(node.value.value, ast.Name):
            return False
        basename = node.value.value.id
        type_alias = self._typing_names.get(basename)
        if type_alias:
            rval = self.repr_annot(node.value) if node.value else None
            if self.typing and self.union_surrogate and type_alias == 'Union':
                rval = self.union_surrogate
            alias = self.repr_expr(node.targets[0])
            if rval:
                self._type_alias[alias] = rval
            return True
        return False

    def visit_AugAssign(self, node: ast.AugAssign):
        rval = self._cast(self.repr_expr(node.value))
        if isinstance(node.target, ast.Subscript):
            owner = self.repr_expr(node.target.value)
            key = self.repr_expr(node.target.slice.value) # type: ignore
            op_setitem = self.map_op_setitem(owner, key, node.op, rval)
            if op_setitem is not None:
                self.stmt(op_setitem)
                return

        op_assign = self.map_op_assign(self.repr_expr(node.target), node.op, rval)
        if op_assign is not None:
            self.stmt(op_assign)
            return

        raise NotImplementedError(f'unhandled: {(ast.dump(node))} at {node.lineno}')

    def visit_AnnAssign(self, node):
        typename = self.repr_annot(node.annotation)
        name = self.repr_annot(node.target)
        rval = self.repr_expr(node.value) if node.value else None
        self._handle_Assign(node, name, rval, typename)

    def _handle_Assign(self, node, ownerref, rval, typename=None):
        isclassattr = self._within and isinstance(self._within[-1].node, ast.ClassDef)

        if isinstance(ownerref, list):
            ownerrefs, ownerref = ownerref, ownerref[0]
        else:
            ownerrefs = [ownerref]

        if not self._within:
            self.in_static = self.has_static
            prefix = 'static ' if self.has_static else ''
        elif isclassattr and self.typing: # TODO: unless ownerref source startswith('_') ...
            prefix = self.public
        else:
            prefix = ''

        # TODO: 5ffce0a5 `not self.typing` is a gnarly mess of js-implied switches
        if all(c == '_' or c.isupper() or c.isdigit() for c in ownerref):
            prefix = self.public + prefix + self.constant
        elif not self.typing and '.' not in ownerref and self.gettype(ownerref) == None:
            if not isclassattr:
                prefix += self.declaring

        if typename and self.typing:
            prefix += f'{typename} ' # TODO: self.declare_assign(...)

        if rval:
            # TODO: 5f831dc1 (java-centric cast logic)
            # This involved maneuvre may be reundant in some cases (then again,
            # we might be able to remove a bunch of noise cast calls in the
            # source...)
            rvalowner = rval.split('.', 1)[0]
            cast_rvalowner = self._cast(rvalowner, parens='.' in rval)
            if cast_rvalowner != rvalowner:
                rval = rval.replace(rvalowner, cast_rvalowner, 1)
            elif not rval.startswith(('(', 'new ')) and ' ' not in rval \
                    or re.search(r'\(\([A-Z]\w+\)', rval):
                rvaltype = typename
                if not rvaltype and not rval.startswith('('):
                    ownertype = self.gettype(ownerref)
                    if ownertype:
                        rvaltype = ownertype[0]

                v = node.value.operand if isinstance(node.value, ast.UnaryOp) else node.value
                if self.typing and rvaltype and not isinstance(v, (ast.Constant,
                        ast.NameConstant, ast.Str, ast.Num, ast.Bytes)):
                    rval = f'({rvaltype}) {rval}'

        if self.typing or not self._within or not isinstance(self._within[-1].node, ast.ClassDef):
            if rval:
                self.stmt(prefix, ' = '.join(ownerrefs + [rval]), node=node)
            else:
                self.stmt(prefix, ownerref, node=node)

        if typename:
            self.addtype(ownerref, typename)

        if not self._within:
            self.in_static = False

        self.generic_visit(node)

    def visit_Delete(self, node):
        target = node.targets[0]

        if not isinstance(target, ast.Subscript) \
           or not isinstance(target.slice, ast.Index):
            raise NotImplementedError(f'unhandled: {(ast.dump(node))}')

        owner = self.repr_expr(target.value)
        key = self.repr_expr(target.slice.value)
        self.stmt(self.map_delitem(owner, key), node=node)

    def visit_Expr(self, node):
        self.stmt(self.repr_expr(node.value), node=node)

    def visit_If(self, node, continued=False):
        if isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__' and node.test.comparators[0].s == '__main__':
            return

        scope = self.new_scope(node)
        orelse = node.orelse
        node.orelse = None
        test = self._thruthy(self.repr_expr(node.test))
        self.enter_block(scope, 'if (', test, ')',
                end=' ' if orelse else None,
                continued=continued)
        if orelse:
            self._check_after_negation(keep=True)
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                self.outln('else', end=' ', continued=True)
                self.visit_If(orelse[0], True)
            else:
                self.enter_block(orelse, 'else', continued=True)
        self._check_after_negation()

    def visit_Import(self, node):
        pass

    def visit_ImportFrom(self, node):
        # IMPROVE: Just verify standard names?
        if node.module == 'typing':
            self._typing_names = {
                name.asname or name.name: name.name
                for name in node.names
            }
        elif node.module == 'collections':
            assert not any(name.asname for name in node.names)
        else:
            self.handle_import(node)

    def visit_For(self, node):
        scope = self.new_scope(node)

        container = self.repr_expr(node.iter)

        # TODO: 5f831dc1 (java-specific)
        ctype, parttype = 'Object', 'Object'
        ctype_narrowed = self.gettype(container.rsplit('.', 1)[0]) if container.endswith(')') else self.gettype(container)
        if (not ctype_narrowed or not ctype_narrowed[0].endswith('>')) and self._last_cast:
            ctype_narrowed = self._last_cast, None
        if ctype_narrowed:
            ctype, narrowed = ctype_narrowed
            if ctype.endswith('>'):
                ctype = ctype[:-1]
                ctype, parttype = ctype.split('<', 1)

        if ctype in self._iterables:
            parttype = self._iterables[ctype]
            ctype = self.types.get('Iterable', 'Iterable')

        if isinstance(node.target, ast.Tuple):
            part = ', '.join(self.repr_expr(el) for el in node.target.elts)
        else:
            part = self.repr_expr(node.target)

        for_repr, stmts, nametypes = self.map_for(container, ctype, part, parttype)

        self.enter_block(scope, for_repr,
                stmts=stmts, nametypes=nametypes)

    def visit_While(self, node):
        test = self._thruthy(self.repr_expr(node.test))
        scope = self.new_scope(node)
        self.enter_block(scope, 'while (', test, ')')

    def visit_Break(self, node):
        self.stmt('break', node=node)

    def visit_Continue(self, node):
        self.stmt('continue', node=node)

    def visit_FunctionDef(self, node):
        prefix = ''
        if self.typing or len(self._within) < 1:
            prefix = self.public

        if node.name.startswith('_') and not node.name.endswith('__'):
            if self.protected.endswith(' '):
                prefix = f'{self.protected}'
            else:
                prefix = ''

        if not self._within or not isinstance(self._within[0].node, ast.ClassDef):
            self.in_static = self.has_static
            if self.has_static:
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
                atype = self.types.get('object')

            aname_val = aname
            if i >= defaultsat:
                default = node.args.defaults[i - defaultsat]
                call = calls[:] + [self.repr_expr(default)]
                aval_name = default if isinstance(default, ast.Name) else type(default.n if isinstance(default, ast.Num) else default.value).__name__
                atype = self.types.get(aval_name, atype)
                if self.func_defaults:
                    aname_val = self.func_defaults.format(
                            key=aname, value=call[-1])
                else:
                    defaultcalls.append((', '.join(argdecls[:]), ', '.join(call)))

            calls.append(aname)

            argdecls.append(f'{atype} {aname_val}' if self.typing else aname_val)
            nametypes.append((aname, atype))

        ret = self.repr_annot(node.returns) if node.returns else 'void'
        # TODO: 5f831dc1 (java-specific)
        if ret == 'Boolean':
            ret = 'boolean'

        name = None
        on_exit: Callable = None
        stmts = []
        if isinstance(node.returns, ast.Subscript) and \
                isinstance(node.returns.value, ast.Name) and \
                node.returns.value.id == 'Iterator':
            iterated_type = self.repr_expr(node.returns.slice.value)
            name, stmts = self.declare_iterator(iterated_type)
            def on_exit():
                self.exit_iterator(node)

        if ret:
            ret += ' '

        in_ctor = False
        if node.name == '__init__':
            name = self.ctor or self._within[-2].node.name
            ret = ''
            in_ctor = True
        elif node.name == '__repr__':
            return # IMPROVE:just drop these "debug innards"?
        # TODO: 5f831dc1 (java-specific)
        elif node.name == '__str__':
            name = 'toString'
        elif node.name == '__eq__':
            name = 'equals'
        elif not name:
            name = under_camelize(node.name, self.protected == '_')

        #for decorator in node.decorator_list:
        #    if isinstance(decorator, ast.Name) and decorator.id == 'property':
        #        name = f'get{name[0].upper()}{name[1:]}'

        # FIXME: js-specific; factor out and improve
        if not self.typing:
            ret = 'function ' if len(self._within) < 2 else ''

        if self.in_static:
            method = name
        elif in_ctor:
            method = self.this
        else:
            method = f'{self.this}.{name}'
        doreturn = 'return ' if node.returns else ''
        for signature, call in defaultcalls:
            self.enter_block(None, prefix, ret, name, f'({signature})', stmts=[
                    f'{doreturn}{method}({call})'
            ])

        argrepr = ', '.join(argdecls)

        self.enter_block(scope, prefix, ret, name, f'({argrepr})', nametypes=nametypes, stmts=stmts, on_exit=on_exit)
        self.in_static = False

    #def map_function(self, node: ast.AST, method):
    #    pass

    def visit_Return(self, node):
        for scope in self._within[-1::-1]:
            if isinstance(scope.node, ast.FunctionDef) and not scope.node.returns:
                self.stmt('return', node=node)
                break
        else:
            self.stmt('return ', self._cast(self.repr_expr(node.value)), node=node)
        self.generic_visit(node)

    def visit_Raise(self, node):
        # TODO: 5f831dc1 (java-specific)
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
            # TODO: 5f831dc1 (java-specific)
            etype = 'Exception ' if self.typing else ''
            self.enter_block(handler, f'catch ({etype}e)')

    def visit_ClassDef(self, node):
        self.outln()

        on_exit: Callable = None

        # TODO: 5f831dc1 (java-specific)
        classname = self.map_name(node.name)
        if classname == self.filename.with_suffix('').name or not self.has_static:
            classdecl = f'{self.public}class '
        elif classname.startswith('_'):
            classname = classname[1:]
            classdecl = 'class ' # module scope
        else:
            classdecl = 'class '

        # TODO: 5f831dc1 (java-specific)
        base = self.repr_expr(node.bases[0]) if node.bases else ''
        if base == 'NamedTuple':
            base = ''
            sign = lambda tinfo: f'{tinfo[0]} ' if self.typing else ''
            def on_exit():
                classdfn = self.classes[classname]
                ctor = self.ctor or classname
                # TODO: use different self.export (for e.g. js!)
                public = self.public if self.typing else ''
                ctor = f'{public}{self.ctor or classname}'

                defaults = [self.repr_expr(ann.value) for ann in node.body
                            if isinstance(ann, ast.AnnAssign) and ann.value]
                if not self.func_defaults:
                    arg = lambda i, aname: aname
                    callclass = self.this or self.ctor or classname
                    for at in range(len(defaults)):
                        defaultargs = defaults[at:]
                        up_to = -len(defaultargs)
                        signature = ', '.join(f'{sign(atypeinfo)}{aname}'
                                    for aname, atypeinfo in list(classdfn.items())[:up_to])
                        args = list(classdfn)[:up_to] + defaultargs
                        self.enter_block(None, ctor, f'({signature})', stmts=[
                                f"{callclass}({', '.join(args)})"
                        ])
                else:
                    def arg(i, aname):
                        di = i - (len(classdfn) - len(defaults))
                        if di > -1:
                            return self.func_defaults.format(key=aname, value=defaults[di])
                        else:
                            return aname

                signature = ', '.join(f'{sign(atypeinfo)}{arg(i, aname)}'
                                for i, (aname, atypeinfo) in enumerate(classdfn.items()))
                assigns = (f'{self.this}.{aname} = {aname}' for aname in classdfn)
                self.enter_block(None, ctor, f'({signature})', stmts=assigns)
        elif base:
            if base == 'Exception':
                base = self.types.get(base, base)
            # TODO: 5f831dc1 (java-specific)
            base = f' extends {base}'

        # TODO:
        for member in node.body:
            if not (isinstance(member, ast.FunctionDef) and
                    member.name == '__iter__'):
                continue
            iterated_type = self.repr_expr(member.returns.slice.value)
            # TODO: 5f831dc1 (java-specific)
            iterable_type = self.types.get('Iterable', 'Iterable')
            if self.typing:
                base += f' implements {iterable_type}<{iterated_type}>'
            self._iterables[classname] = iterated_type
            break

        stmts = []
        # TODO: if derived from an Exception...
        if node.name.endswith('Error'):
            mtype = 'String ' if self.typing else ''
            ctor = self.ctor or classname
            if self.func_defaults:
                key_val = self.func_defaults.format(key=f'{mtype}msg',
                                                    value=self.none)
                stmts.append(f'{ctor}({key_val}) {{ super(msg){self.end_stmt} }}')
            else:
                stmts.append(f'{ctor}() {{ }}')
                stmts.append(f'{ctor}({mtype}msg) {{ super(msg); }}')

        self.enter_block(node, classdecl, classname, base,
                stmts=stmts, on_exit=on_exit)

    def repr_annot(self, expr) -> str:
        return self.repr_expr(expr, annot=True)

    def repr_expr(self, expr, annot=False, isowner=False, callargs=None,
            assignedto=None) -> str:
        if isinstance(expr, ast.Str):
            # TODO: just use repr(s) with some cleanup?
            s = expr.s.replace('\\', '\\\\')
            s = s.replace('"', r'\"')
            s = s.replace('\n', r'\n')
            return expr.s if annot else f'"{s}"'

        elif isinstance(expr, ast.Num):
            return str(expr.n)

        elif isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub):
            return f'-{expr.operand.n}' # type: ignore

        elif isinstance(expr, (ast.Constant, ast.NameConstant, ast.Ellipsis)):
            if isinstance(expr, ast.Ellipsis) or expr.value is Ellipsis:
                return '/* ... */'
            return self.constants.get(expr.value, expr.value)

        elif isinstance(expr, ast.Name):
            return self.map_name(expr.id, callargs)

        elif isinstance(expr, ast.Attribute):
            owner = self.repr_expr(expr.value, isowner=True)
            return self.map_attr(owner, expr.attr, callargs=callargs)

        elif isinstance(expr, ast.Call):
            return self._map_call(expr, isowner=isowner)

        elif isinstance(expr, ast.Subscript):
            return self._map_subscript(expr, annot=annot)

        elif isinstance(expr, ast.Compare):
            left = self.repr_expr(expr.left)
            op = expr.ops[0]
            right = ', '.join(self.repr_expr(c) for c in expr.comparators)
            return self.map_compare(left, op, right)

        elif isinstance(expr, ast.IfExp):
            scope = self.new_scope(expr)
            test = self._cast(self._thruthy(self.repr_expr(expr.test)))
            then = self._cast(self.repr_expr(expr.body))
            self.exit_scope()
            self._check_after_negation(keep=True)
            other = self._cast(self.repr_expr(expr.orelse))
            return f'({test} ? {then} : {other})'

        elif isinstance(expr, ast.BoolOp):
            if isinstance(expr.op, ast.And):
                joiner = self.operators[ast.And]
            elif isinstance(expr.op, ast.Or):
                joiner = self.operators[ast.Or]
            boolexpr = f' {joiner} '.join(
                    self._thruthy(self.repr_expr(self._check_after_negation(v, keep=True)))
                    for v in expr.values)
            # TODO: don't wrap in parens unless parent is BoolOp (5f76eae2)?
            return f'({boolexpr})' if len(expr.values) > 1 else boolexpr

        elif isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.Not):
                self._in_negation = True
                repr = self._negated(self.repr_expr(expr.operand))
                self._in_negation = False
                return repr

        elif isinstance(expr, ast.Tuple):
            if assignedto:
                return self.unpack_tuple(expr, assignedto)
            else:
                return self.map_tuple(expr)

        elif isinstance(expr, ast.Dict):
            return self.map_dict(expr)

        elif isinstance(expr, ast.List):
            return self.map_list(expr)

        elif isinstance(expr, ast.Set):
            return self.map_set(expr)

        elif isinstance(expr, ast.JoinedStr):
            return self.map_joined_str(expr)

        elif isinstance(expr, ast.GeneratorExp):
            # TODO: just support GeneratorExp with any/all
            return ast.dump(expr)

        elif isinstance(expr, ast.ListComp):
            return self.map_listcomp(expr)

        elif isinstance(expr, ast.DictComp):
            return self.map_dictcomp(expr)

        elif expr is None:
            return self.none

        elif isinstance(expr, ast.BinOp):
            if isinstance(expr.op, ast.Add):
                lexpr = self.repr_expr(expr.left)
                ltype = self.gettype(lexpr)
                # TODO: the `or` is a hack since type inference is still too shallow (use "in_boolop (5f54c8e1, 5f76eae2) to control better?)
                if self.list_concat and (ltype and 'List' in ltype[0] or 'List' in lexpr):
                    return self.list_concat.format(left=lexpr, right=self.repr_expr(expr.right))
                bop = '+'
            elif isinstance(expr.op, ast.Sub):
                bop = '-'
            elif isinstance(expr.op, ast.Mult):
                bop = '*'
            elif isinstance(expr.op, ast.Div):
                bop = '/'
            elif isinstance(expr.op, ast.Mod):
                bop = '%'
            return f'{self.repr_expr(expr.left)} {bop} {self.repr_expr(expr.right)}'

        elif isinstance(expr, ast.Yield):
            return self.add_to_iterator(expr.value)

        elif isinstance(expr, ast.YieldFrom):
            return self.add_all_to_iterator(expr.value)

        elif isinstance(expr, ast.Lambda):
            return self._map_lambda(expr)

        raise NotImplementedError(f'unhandled: {(expr)}')

    def map_compare(self, left: str, op: ast.cmpop, right: str) -> str:
        if isinstance(op, ast.In):
            return self.map_in(right, left)
        elif isinstance(op, ast.NotIn):
            return self.map_in(right, left, negated=True)
        elif isinstance(op, ast.Eq):
            if right.isnumeric():
                return self._fmt_op(ast.Is, left, right)
            return self._fmt_op(ast.Eq, left, right)
        elif isinstance(op, ast.NotEq):
            if right.isnumeric():
                return self._fmt_op(ast.IsNot, left, right)
            return self._fmt_op(ast.NotEq, left, right)
        else:
            ltype_narrowed = self.gettype(left)
            mop = self.operators[type(op)]
            if self.strcmp and ('>' in mop or '<' in mop) and ltype_narrowed and ltype_narrowed[0] == 'String':
                compare = self.strcmp.format(left, right)
                return f'{compare} {mop} 0'
            return f'{left} {mop} {right}'

    def _fmt_op(self, op: type, *args):
        oper = self.operators[op]
        if len(args) == 2 and '{0}' not in oper:
            fmt = f'{{0}} {oper} {{1}}'
        else:
            fmt = oper
        return fmt.format(*args)

    def _map_call(self, expr: ast.Call, isowner=False):
        call_args: list = expr.args
        if expr.keywords:
            # FIXME: [5f55548d] handle order of kwargs and transpile Lambdas
            print(f'WARNING: keywords in call: {ast.dump(expr)}', file=sys.stderr)
            call_args += [kw.value for kw in expr.keywords if kw.arg]

        callargs = [self._cast(self.repr_expr(arg)) for arg in call_args]

        self._last_cast = None

        if isinstance(expr.func, ast.Name):
            funcname = expr.func.id

            if funcname == 'isinstance':
                return self._map_isinstance(expr)

            elif funcname == 'cast':
                arg0typerepr = self.repr_expr(call_args[0], annot=True)
                arg1repr = self.repr_expr(call_args[1])
                # TODO: 5f831dc1 (java-specific)
                castvalue = f'({arg0typerepr}) {arg1repr}'
                self._last_cast = arg0typerepr
                if not self.typing:
                    return arg1repr
                #if isowner:
                #    castvalue = f'({castvalue})'
                return f'({castvalue})'

            elif funcname == 'any':
                return self.map_any(expr.args[0])

            elif funcname == 'all':
                return self.map_all(expr.args[0])

            elif funcname == 'len':
                return self.map_len(self.repr_expr(call_args[0]))

        return self.repr_expr(expr.func, callargs=callargs)

    def _map_isinstance(self, expr):
        v = self.repr_expr(expr.args[0])

        if isinstance(expr.args[1], ast.Tuple):
            classes = (self.repr_expr(arg) for arg in expr.args[1].elts)
            return ' || '.join(self.map_isinstance(v, c) for c in classes)

        c = self.repr_expr(expr.args[1])
        if self._in_negation:
            self._post_negation = lambda: self.addtype(v, c, True)
        else:
            self.addtype(v, c, True)

        return self.map_isinstance(v, c)

    def _map_subscript(self, expr, annot):
        owner = self.repr_expr(expr.value, annot=annot)

        if isinstance(expr.slice, ast.Slice):
            lower = self.repr_expr(expr.slice.lower)
            upper = self.repr_expr(expr.slice.upper) if expr.slice.upper else None
            return self.map_getslice(owner, lower, upper)

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

        if annot and isinstance(expr.value, ast.Name) and expr.value.id == 'Optional' and self.optional_type_form:
            return self.optional_type_form.format(tname)

        if annot:
            if owner == 'Union' and self.union_surrogate:
                return self.union_surrogate
            return f'{owner}<{tname}>'

        return self.map_getitem(owner, tname)

    def _cast(self, name, parens=False):
        if not self.typing:
            return name
        ntype_narrowed = self.gettype(name)
        if ntype_narrowed and ntype_narrowed[1]:
            result = f'({ntype_narrowed[0]}) {name}'
            if parens:
                result = f'({result})'
            return result
        return name

    def _thruthy(self, name, parens=False):
        ops = self.operators
        ntype_narrowed = self.gettype(name)
        if ntype_narrowed and ntype_narrowed[0] != self.types['bool']:
            if self.notmissing:
                result = f"{name} {self.notmissing}"
            else:
                result = f"{name} {ops[ast.IsNot]} {self.none}"
            if ntype_narrowed[0].startswith(self.types['List'] ):
                result = f'({result} {ops[ast.And]} {self.map_len(name)} {ops[ast.Gt]} 0)'
            if ntype_narrowed[0] == self.types['int']:
                result = f'{name} {ops[ast.Gt]} 0'
            if parens:
                result = f'({result})'
            return result
        return name

    def _negated(self, expr: str):
        ntype_narrowed = self.gettype(expr)
        if ntype_narrowed and ntype_narrowed[0] != self.types['bool']:
            isop = self.operators[ast.Is]
            if ntype_narrowed[0] == self.types['int']:
                return f'{expr} {isop} 0'
            else:
                return f'{expr} {isop} null'
        return f'!({expr})'

    def _check_after_negation(self, o=None, keep=False):
        if self._post_negation and (keep or not self._in_negation):
            self._post_negation()
            if not keep:
                self._post_negation = None
        return o

    @contextmanager
    def enter_file(self, srcpath: Path):
        raise NotImplementedError

    def map_for(self, container: str, ctype: str, part: str, parttype: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
        raise NotImplementedError

    def map_name(self, name: str, callargs: List[str] = None) -> str:
        if name == 'self':
            return self.this

        if callargs:
            map_repr: Optional[str] = self.function_map.get(name)
            if map_repr:
                return map_repr.format(*callargs)

        name = self._type_alias.get(name, name)
        obj = self.types.get(name) or under_camelize(name, self.protected == '_')

        if callargs is not None:
            argrepr = ', '.join(callargs)
            if obj in self.classes or obj[0].isupper():
                return f'new {obj}({argrepr})'
            else:
                return f'{obj}({argrepr})'

        return obj

    def handle_import(self, node: ast.ImportFrom):
        raise NotImplementedError

    def map_getitem(self, owner: str, key: str) -> str:
        raise NotImplementedError

    def map_getslice(self, owner: str, lower: str, upper: str = None) -> str:
        raise NotImplementedError

    def map_op_assign(self, owner: str, op: ast.operator, value: str) -> Optional[str]:
        raise NotImplementedError

    def map_setitem(self, owner: str, key: str, value: str) -> str:
        raise NotImplementedError

    def map_op_setitem(self, owner: str, key: str, op: ast.operator, value: str) -> str:
        raise NotImplementedError

    def map_delitem(self, owner: str, key: str) -> str:
        raise NotImplementedError

    def map_in(self, container, contained, negated=False):
        raise NotImplementedError

    def map_attr(self, owner: str, attr: str, callargs: List[str] = None) -> str:
        raise NotImplementedError

    def map_list(self, expr: ast.List) -> str:
        raise NotImplementedError

    def map_dict(self, expr: ast.Dict) -> str:
        raise NotImplementedError

    def map_set(self, expr: ast.Set) -> str:
        raise NotImplementedError

    def map_any(self, expr) -> str:
        raise NotImplementedError

    def map_all(self, expr) -> str:
        raise NotImplementedError

    def map_len(self, item: str) -> str:
        raise NotImplementedError

    def declare_iterator(self, node) -> Tuple[str, List]:
        raise NotImplementedError

    def add_to_iterator(self, expr) -> str:
        raise NotImplementedError

    def add_all_to_iterator(self, expr) -> str:
        raise NotImplementedError

    def exit_iterator(self, node):
        raise NotImplementedError

    def map_joined_str(self, expr: ast.JoinedStr) -> str:
        return ' + '.join(
                self.repr_expr(
                    v.value if isinstance(v, ast.FormattedValue)
                    else v)
                for v in expr.values)

    def map_tuple(self, expr: ast.Tuple) -> str:
        raise NotImplementedError

    def unpack_tuple(self, expr: ast.Tuple, assignedto=None) -> str:
        raise NotImplementedError

    def map_listcomp(self, comp: ast.ListComp) -> str:
        raise NotImplementedError

    def map_dictcomp(self, comp: ast.DictComp) -> str:
        raise NotImplementedError

    def _map_lambda(self, f: ast.Lambda) -> str:
        assert not f.args.defaults
        assert not f.args.vararg
        assert not f.args.kwarg
        assert not f.args.kwonlyargs
        assert not f.args.kw_defaults
        return self.map_lambda([arg.arg for arg in f.args.args], self.repr_expr(f.body))

    def map_lambda(self, args: List[str], body: str) -> str:
        raise NotImplementedError
