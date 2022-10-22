# TODO:
# * [5f54c8e1] Use module data from TypeScanner, remove duplicate
#   logic and factor out remaining _visitor from Transpiler.
# * [5f76eae2] Improve isinstance checking (top-level bool, reset at or?).
# * [5f831dc1] Clear out java-specific code.
from typing import NamedTuple, Dict, List, Tuple, Union, Optional, Callable, Iterator, cast
from enum import Enum, auto
from contextlib import contextmanager
from collections import OrderedDict
from pathlib import Path
import ast
import re
import sys

from .typescanner import TypeScanner, ClassType, FuncType


# Handle the change of ast implementation in Python 3.8+:

# All literals are ast.Constant and the others are deprecated.
AST_NAME_CONSTANT = (ast.NameConstant,) if hasattr(ast, 'NameConstant') else ()
AST_ELLIPSIS = (ast.Ellipsis,) if hasattr(ast, 'Ellipsis') else ()
AST_STR = (ast.Str,) if hasattr(ast, 'Str') else ()
AST_NUM = (ast.Num,) if hasattr(ast, 'Num') else ()
AST_BYTES = (ast.Bytes,) if hasattr(ast, 'Bytes') else ()
AST_CONSTANTS = (ast.Constant,) + AST_NAME_CONSTANT + AST_STR + AST_NUM + AST_BYTES

# In 3.9, simple indices are represented by value, extended slices as tuples.
AST_INDEX = (ast.Index,) if hasattr(ast, 'Index') else ()

def _get_slice(slice):
    return slice.value if isinstance(slice, AST_INDEX) else slice


ReprAndType = Tuple[str, Optional[str]]


class Scope(NamedTuple):
    node: object
    typed: Dict[str, Tuple[str, bool]]


class ContainerType(NamedTuple):
    container: str
    contained: str


class Transpiler(ast.NodeVisitor):
    #_visitor: ast.NodeVisitor
    typing: bool # or typecheck_implies_casts...
    classdfn = 'class '
    if_stmt = 'if (%s)'
    while_stmt = 'while (%s)'
    inherit_constructor = True
    mknew = ''
    union_surrogate: Optional[str] = None
    optional_type_form: Optional[str] = None
    static_annotation_form: Optional[str] = None
    begin_block: str
    end_block: str
    ctor: Optional[str] = None
    #call_keywords = AsDict
    func_defaults: Optional[str] = None
    selfarg: Optional[str] = None
    this: str
    protected = ''
    declaring: Optional[str] = None
    none: str
    constants: Dict
    operators: Dict
    types: Dict
    strcmp: Optional[str] = None
    notmissing: Optional[str] = None
    list_concat: Optional[str] = None
    function_map: Dict[str, Union[Optional[str], List[str]]]

    line_comment: str
    inline_comment: Tuple[str, str]
    indent: str

    outdir: str

    def __init__(self, outdir: str = None):
        super().__init__()
        self.in_static = False
        self.staticname = 'Statics'
        self.statics: List[Tuple] = []

        self._modules = None
        self._module = None
        # TODO: replace these (entirely?) with use of self._modules (5f54c8e1) {{{
        self.classes: Dict[str, Dict[str, str]] = {}
        self._iterables: Dict[str, str] = {}

        self._top: Dict[str, Tuple] = {}
        # }}}
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
            self.argparser.add_argument('-I', '--ignore', nargs='*')
            self.argparser.add_argument('-o', '--output-dir')
            self.argparser.add_argument('-L', '--no-lineno', action='store_true')
        else:
            self.outdir = outdir

    def main(self, sources=None):
        if not sources and self.argparser:
            args = self.argparser.parse_args()
            self.outdir = args.output_dir
            self.show_lineno = not args.no_lineno
            sources = args.source
            ignores = set(args.ignore or [])

        typescanner = TypeScanner(self)
        for src in sources:
            typescanner.read(src)

        self._modules = typescanner.modules

        for src, mod in typescanner.modules.items():
            if src in ignores:
                print('SKIPPING:', src)
                continue

            with open(src) as f:
                code = f.read()

            tree = ast.parse(code)

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
                self.outln(f'{self.public}{self.classdfn}', self.staticname, self.begin_block)
            nl = True
            for args, kwargs in self.statics:
                self.outln(self.indent if nl and args and not inclass else '', *args, **kwargs)
                nl = kwargs.get('end') is None
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
        if eol:
            return f' {self.line_comment} {note}'
        elif self.inline_comment:
            start, stop = self.inline_comment
            return f'{start} {note} {stop}'
        else:
            return ''

    def new_scope(self, node=None):
        scope = Scope(node, OrderedDict())
        self._within.append(scope)
        return scope

    def exit_scope(self):
        self._within.pop()

    def enter_block(self, scope, *parts, end=None, continued=False,
                    stmts=[], nametypes=[], on_exit: Optional[Callable] = None):
        if not isinstance(scope, Scope):
            scope = self.new_scope(scope)

        if '\n' not in self.begin_block:
            parts += (self.begin_block,)
        self.outln(*parts, node=scope.node, continued=continued)
        if self.begin_block.startswith('\n'):
            self.outln(self.begin_block[1:])
        self._level += 1
        if self.classdfn in parts[0]:
            self.classes[parts[1]] = scope.typed
            self._staticout(inclass=parts[1])

        for argtype in nametypes:
            self.addtype(*argtype)

        for stmt in stmts:
            self.stmt(stmt)

        if isinstance(scope.node, list):
            for node in scope.node:
                self.visit(node)
        elif scope.node:
            body = scope.node.body
            if (
                isinstance(scope.node, (ast.ClassDef, ast.FunctionDef))
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                print("Skipping docstring:", body[0].value.value)
                for node in body[1:]:
                    self.visit(node)
            else:
                self.generic_visit(scope.node)

        if on_exit:
            on_exit()

        self.exit_scope()
        self._level -= 1
        self.outln(self.end_block, end=end)

    def addtype(self, name: str, typename: str, narrowed=False):
        typename = cast(str, self.cleantype(typename))
        if self._within:
            scope = self._within[-1]
            known = scope.typed.get(name)
            if known and known[0] != typename:
                narrowed = True
            scope.typed[name] = typename, narrowed
        else:
            self._top[name] = typename, narrowed

    def cleantype(self, typename: str) -> Optional[str]:
        return typename

    def gettype(self, name):
        # Look in local (non-class) scope
        for scope in self._within[::-1]:
            if isinstance(scope.node, ast.ClassDef):
                break
            if name in scope.typed:
                return scope.typed[name]

        # Look in class scope
        if '.' in name:
            inclass = None
            owner, *attrs = name.split('.') # TODO: not needed anymore? if ' ' not in name else name.split('.', 1)
            if owner == self.this:
                for scope in self._within[::-1]:
                    if isinstance(scope.node, ast.ClassDef):
                        inclass = scope.node.name
                        break
            else:
                ntype_narrowed = self.gettype(owner)
                if ntype_narrowed:
                    inclass = ntype_narrowed[0]

            if inclass is None:
                dfn = self._getdef(owner)
                if isinstance(dfn, ClassType):
                    inclass = owner

            if inclass and attrs:
                for attr in attrs:
                    if '(' in attr and attr.endswith(')'):
                        attr = attr.split('(', 1)[0]
                    inclassinfo = self._attrtype(inclass, attr)
                    if inclassinfo:
                        inclass = inclassinfo[0]
                    else:
                        inclass = None
                        break
                if inclass:
                    return inclass, False

        call = name.split('(', 1)[0] if '(' in name and name.endswith(')') else None
        # TODO: Check '.' as per above, and get ClassType if so.
        # Also define lang-based "builtin" ClassTypes.
        # NOTE: no self._module set here when used via typescanner!
        dfn = self._module.get(call) if self._module else None
        if dfn:
            if isinstance(dfn, FuncType):
                return dfn.returns, False

        # Look in global scope
        topdfn = self._top.get(name)
        if topdfn:
            return topdfn

        dfn = self._getdef(name, includeownmodule=False)
        if isinstance(dfn, str):
            return dfn, False

        return None

    def _getdef(self, name, includeownmodule=True):
        if self._module is None:
            return None
        if includeownmodule:
            dfn = self._module.get(name)
            if dfn is not None:
                return dfn
        imprefs = self._module.get('__imports')
        if imprefs and name in imprefs:
            return self._modules[imprefs[name]].get(name)
        if imprefs and '*' in imprefs:
            return self._modules[imprefs['*']].get(name)
        return None

    def _attrtype(self, inclass, attr):
        unalias = lambda name: self._type_alias.get(name, name)

        classinfo = self._getdef(inclass)
        while classinfo:
            member = classinfo.members.get(attr)
            if isinstance(member, FuncType):
                member = member.returns
            mtype = self.cleantype(member)
            if mtype:
                return unalias(mtype), False
            classinfo = self._getdef(classinfo.base)

        return None

    def visit_Assert(self, node):
        self.stmt(self.map_assert(self.repr_expr(node.test), self.repr_expr(node.msg)))

    def visit_Assign(self, node, annotation=None):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
            target = node.targets[0]
            owner = self.repr_expr(target.value)
            key = self.repr_expr(_get_slice(target.slice))
            rval = self.repr_expr(node.value)
            self.stmt(self.map_setitem(owner, key, rval), node=node)
            return

        if not self._handle_type_alias(node):
            rval, rvaltype = self.repr_expr_and_type(node.value)
            ownerrefs = [self.repr_expr(target, assignedto=rval) for target in node.targets
                        if not isinstance(target, ast.Subscript)]
            assert len(ownerrefs) == len(node.targets)
            self._handle_Assign(node, ownerrefs, None, rval, rvaltype)

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
            key = self.repr_expr(_get_slice(node.target.slice)) # type: ignore
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
        self._handle_Assign(node, name, typename, rval)

    def _handle_Assign(self, node, ownerref, typename=None, rval=None, rvaltype=None):
        isclassattr = self._within and isinstance(self._within[-1].node, ast.ClassDef)

        if isinstance(ownerref, list):
            ownerrefs, ownerref = ownerref, ownerref[0]
        else:
            ownerrefs = [ownerref]

        static_anno = self.static_annotation_form.replace('{0}', '', 1) \
                      if self.static_annotation_form else None
        if not self._within:
            self.in_static = self.has_static
            prefix = 'static ' if self.has_static else ''
        elif typename and static_anno and typename.startswith(static_anno):
            typename = typename[len(static_anno):]
            typename = self.types.get(typename, typename)
            prefix = 'static ' if self.has_static else ''
        else:
            prefix = ''

        # TODO: unless ownerref source startswith('_') ...
        public = isclassattr and self.typing

        # TODO: 5ffce0a5 `not self.typing` is a gnarly mess of js-implied switches
        if all(c == '_' or c.isupper() or c.isdigit() for c in ownerref):
            prefix = prefix + self.constant
            public = True
        elif self.declaring and '.' not in ownerref and self.gettype(ownerref) == None:
            if not isclassattr:
                prefix += self.declaring

        if typename is None and self.isname(ownerref):
            if self.gettype(ownerref) is None:
                typename = rvaltype

                if typename is None and rval.startswith(self.mknew):
                    # TODO: 5f831dc1 (too java-specific)
                    typename = rval.replace(self.mknew, '')
                    for c in ['(', '<']:
                        ci = typename.find(c)
                        if ci > -1 and self.isname(typename[:ci]):
                            typename = typename[:ci]
                    for interface in ['List', 'Map', 'Set']:
                        if typename.endswith(interface):
                            typename = interface

        if public:
            prefix = self.public + prefix

        if rval:
            # TODO: 5f831dc1 (java-centric cast logic)
            # This involved maneuvre may be reundant in some cases (then again,
            # we might be able to remove a bunch of noise cast calls in the
            # source...)
            rvalowner = rval.split('.', 1)[0]
            cast_rvalowner = self._cast(rvalowner, parens='.' in rval)
            if cast_rvalowner != rvalowner:
                rval = rval.replace(rvalowner, cast_rvalowner, 1)
            elif not rval.startswith(('(', self.mknew)) and ' ' not in rval \
                    or re.search(r'\(\([A-Z]\w+\)', rval):
                rvaltype = typename
                if not rvaltype and not rval.startswith('('):
                    ownertype = self.gettype(ownerref)
                    if ownertype:
                        rvaltype = ownertype[0]

                v = node.value.operand if isinstance(node.value, ast.UnaryOp) else node.value
                if self.typing and rvaltype and not isinstance(v, AST_CONSTANTS):
                    knowntypeinfo = self.gettype(rval)
                    if not self.isname(rval) or (knowntypeinfo and rvaltype != knowntypeinfo[0]):
                        rval = self.repr_cast(rvaltype, rval)

        # TODO: for JS < 7?
        classlevel = self._within and isinstance(self._within[-1].node, ast.ClassDef)
        ok_to_declare = self.typing or not classlevel
        if ok_to_declare:
            if rval:
                self.stmt(prefix, self.typed(ownerref, typename), ' = ',
                          ' = '.join(ownerrefs[1:] + [rval]), node=node)
            else:
                self.stmt(prefix, self.typed(ownerref, typename), node=node)
        elif rval:
            self.stmt(self.typed(ownerref, typename), ' = ',
                        ' = '.join(ownerrefs[1:] + [rval]), node=node)

        if typename:
            self.addtype(ownerref, typename)

        if not self._within:
            self.in_static = False

        self.generic_visit(node)

    def visit_Delete(self, node):
        target = node.targets[0]

        if not isinstance(target, ast.Subscript):
            raise NotImplementedError(f'unhandled: {(ast.dump(node))}')

        owner = self.repr_expr(target.value)
        key = self.repr_expr(_get_slice(target.slice))
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
        self.enter_block(scope, self.if_stmt % test,
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
        assert len(node.names) == 1 and node.names[0].asname is None, \
                f'Unexpected: {ast.dump(node)}'
        modname = node.names[0].name
        if modname != 're': # re.compile and re.Pattern are transcribed differently
            warn(f'Ignoring `import {modname}`')

    def visit_ImportFrom(self, node):
        # IMPROVE: Just verify standard names?
        if node.module == 'typing':
            self._typing_names = {
                name.asname or name.name: name.name
                for name in node.names
            }
        elif node.module == 'collections':
            assert not any(name.asname for name in node.names)
        elif node.module == 'builtins' and node.level > 0:
            pass # Members are treated at global names and mapped differently
        else:
            self.handle_import(node)

    def visit_For(self, node: ast.For):
        scope = self.new_scope(node)

        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):
            callargs = [self.repr_expr(arg) for arg in node.iter.args]

            if node.iter.func.id == 'range':
                counter = self.repr_expr(node.target)
                assert len(callargs) == 1, "Only 1-ary range is supported"
                ceiling = callargs[0]
                for_repr, stmts, nametypes = self.map_for_to(counter, ceiling)
                self.enter_block(scope, for_repr, stmts=stmts, nametypes=nametypes)
                return

            if node.iter.func.id == 'enumerate':
                assert isinstance(node.target, ast.Tuple)
                counter, part = [self.repr_expr(el) for el in node.target.elts]
                assert len(callargs) == 1, "Only 1-ary enumerate is supported"
                container = callargs[0]
                ctype, parttype = self._get_containertype(container)

                for_repr, stmts, nametypes = self.map_enumerated_for(container, ctype, part, parttype, counter)
                self.enter_block(scope, for_repr, stmts=stmts, nametypes=nametypes)
                return

        container = self.repr_expr(node.iter)
        ctype, parttype = self._get_containertype(container)

        if isinstance(node.target, ast.Tuple):
            part = ', '.join(self.repr_expr(el) for el in node.target.elts)
        else:
            part = self.repr_expr(node.target)

        for_repr, stmts, nametypes = self.map_for(container, ctype, part, parttype)

        self.enter_block(scope, for_repr, stmts=stmts, nametypes=nametypes)

    def _get_containertype(self, container):
        ctypeinfo = self.gettype(
            container.rsplit('.', 1)[0] if container.endswith(')') else container
        )
        ctype = ctypeinfo[0] if ctypeinfo else self._last_cast
        containertype = self.container_type(ctype)
        # TODO: hacked this fix to let transpile.js further along, but really
        # check this logic! (I've lost my way in my djungle of code...)
        if not containertype or not containertype.contained:
            containertype = self.container_type(self._last_cast)

        if containertype:
            ctype, parttype = containertype
        else:
            otype = self.types.get('object')
            assert otype is not None
            ctype, parttype = (ctype or otype), otype

        if ctype in self._iterables:
            parttype = self._iterables[ctype]
            ctype = self.types.get('Iterable', 'Iterable')

        return ctype, parttype

    def visit_While(self, node):
        test = self._thruthy(self.repr_expr(node.test))
        scope = self.new_scope(node)
        self.enter_block(scope, self.while_stmt % test)

    def visit_Break(self, node):
        self.stmt('break', node=node)

    def visit_Continue(self, node):
        self.stmt('continue', node=node)

    def visit_With(self, node: ast.With):
        assert len(node.items) == 1
        withitem = node.items[0]
        expr = self.repr_expr(withitem.context_expr)
        var = self.repr_expr(withitem.optional_vars)
        self.handle_with(expr, var)

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
                if self.selfarg is None:
                    continue
                else:
                    aname = self.selfarg
            else:
                aname = self.to_var_name(arg.arg)

            if arg.annotation:
                atype = self.repr_annot(arg.annotation)
            else:
                atype = self.types.get('object')

            aname_val = aname
            if i >= defaultsat:
                default = node.args.defaults[i - defaultsat]
                call = calls[:] + [self.repr_expr(default)]
                # TODO: self.repr_expr(default)?
                aval_name = default if isinstance(default, ast.Name) else type(default.n if isinstance(default, AST_NUM) else default.value).__name__
                atype = self.types.get(aval_name, atype)
                if self.func_defaults:
                    aname_val = self.func_defaults.format(
                            key=aname, value=call[-1])
                else:
                    defaultcalls.append((argdecls[:], ', '.join(call)))

            calls.append(aname)

            argdecls.append((aname_val, aname, atype))
            nametypes.append((aname, atype))

        ret = self.repr_annot(node.returns) if node.returns else None
        # TODO: 5f831dc1 (java-specific)
        if ret == 'Boolean':
            ret = 'boolean'

        name = None
        on_exit: Callable = None
        stmts = []
        if isinstance(node.returns, ast.Subscript) and \
                isinstance(node.returns.value, ast.Name) and \
                node.returns.value.id == 'Iterator':
            iterated_type = self.repr_expr(_get_slice(node.returns.slice))
            name, stmts = self.declare_iterator(iterated_type)
            def on_exit():
                self.exit_iterator(node)

        in_ctor = False
        if node.name == '__init__':
            name = self.ctor or self._within[-2].node.name
            ret = '' # TODO: self.ctordef?
            in_ctor = True
        elif node.name == '__repr__':
            return # IMPROVE:just drop these "debug innards"?
        elif not name:
            name = self.to_attribute_name(node.name)

        #for decorator in node.decorator_list:
        #    if isinstance(decorator, ast.Name) and decorator.id == 'property':
        #        name = f'get{name[0].upper()}{name[1:]}'

        if self.in_static:
            method = name
        elif in_ctor:
            method = self.this
        else:
            method = f'{self.this}.{name}'
        doreturn = 'return ' if node.returns else ''
        for signature, call in defaultcalls:
            self.enter_block(None, prefix, self.overload(name, signature, ret), stmts=[
                    f'{doreturn}{method}({call})'
            ])

        self.enter_block(scope, prefix, self.funcdef(name, argdecls, ret), nametypes=nametypes, stmts=stmts, on_exit=on_exit)
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
            self.stmt(f'throw {self.mknew}', self.repr_expr(node.exc), '()', node=node)
        self.generic_visit(node)

    def visit_Try(self, node):
        handlers = node.handlers
        node.handlers = None
        self.enter_block(node, 'try', end='')
        for handler in handlers:
            # TODO: 5f831dc1 (java-specific)
            etype = self.repr_annot(handler.type) if handler.type else 'Exception'
            etypevar = self.typed('e', etype)
            self.enter_block(handler, f' catch ({etypevar})', continued=True)

    def visit_ClassDef(self, node):
        self.outln()

        on_exit: Callable = None

        # TODO: 5f831dc1 (java-specific)
        classname = self.map_name(node.name)
        if classname == self.filename.with_suffix('').name or not self.has_static:
            classdecl = f'{self.public}{self.classdfn}'
        elif classname.startswith('_'):
            classname = classname[1:]
            classdecl = self.classdfn # module scope
        else:
            classdecl = self.classdfn

        # TODO: 5f831dc1 (java-specific)
        base = self.repr_expr(node.bases[0]) if node.bases else ''
        if base == 'NamedTuple':
            base = ''
            def on_exit():
                classdfn = self.classes[classname]
                ctor = self._ctor_callable(classname)

                defaults = [self.repr_expr(ann.value) for ann in node.body
                            if isinstance(ann, ast.AnnAssign) and ann.value]
                if not self.func_defaults:
                    arg = lambda i, aname: aname
                    callclass = self.this or self.ctor or classname
                    for at in range(len(defaults)):
                        defaultargs = defaults[at:]
                        up_to = -len(defaultargs)
                        signature = ', '.join(self.typed(aname, atypeinfo[0])
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

                signature = ', '.join(self.typed(arg(i, aname), atypeinfo[0])
                                for i, (aname, atypeinfo) in enumerate(classdfn.items()))
                assigns = (f'{self.this}.{aname} = {aname}' for aname in classdfn)
                self.enter_block(None, ctor, f'({signature})', stmts=assigns)
        elif base == 'Protocol':
            base = ' implements java.util.function.Function'
            pass  # TODO: multi-arg callables (may be too costly for e.g. java...)
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
            iterated_type = self.repr_expr(_get_slice(member.returns.slice))
            # TODO: 5f831dc1 (java-specific)
            iterable_type = self.types.get('Iterable', 'Iterable')
            if self.typing:
                base += f' implements {iterable_type}<{iterated_type}>'
            self._iterables[classname] = iterated_type
            break

        stmts = []
        # TODO: if derived from an Exception...
        if not self.inherit_constructor and node.name.endswith('Error'):
            msgdecl = self.typed('msg', 'String')
            ctor = self._ctor_callable(classname)
            if self.func_defaults:
                key_val = self.func_defaults.format(key=msgdecl,
                                                    value=self.none)
                stmts.append(f'{ctor}({key_val}) {{ super(msg){self.end_stmt} }}')
            else:
                stmts.append(f'{ctor}() {{ }}')
                stmts.append(f'{ctor}({msgdecl}) {{ super(msg); }}')
        elif not self.inherit_constructor:
            classinfo = self._getdef(classname)
            ctor = self._ctor_callable(classname)
            if classinfo and 'Init' not in classinfo.members and classinfo.base:
                while True:
                    classinfo = self._getdef(classinfo.base)
                    if not classinfo:
                        break
                    ctordef = classinfo.members.get('Init')
                    if ctordef:
                        argdefs = ', '.join(self.typed(n, t)
                                            for n, t in ctordef.args.items()
                                            if n != self.this)
                        args = ', '.join(n for n in ctordef.args.keys()
                                          if n != self.this)
                        stmts.append(f'{ctor}({argdefs}) {{ super({args}); }}')
                        break

        self.enter_block(node, classdecl, classname, base, stmts=stmts, on_exit=on_exit)

    def _ctor_callable(self, classname):
        # TODO: use different self.export (for e.g. js!)
        public = self.public if self.typing else ''
        return f'{public}{self.ctor or classname}'

    def repr_annot(self, expr) -> str:
        return self.repr_expr(expr, annot=True)

    def repr_expr(self, expr, annot=False, isowner=False, callargs=None,
            assignedto=None) -> str:
        return self.repr_expr_and_type(expr, annot, isowner, callargs, assignedto)[0]

    def repr_expr_and_type(self, expr, annot=False, isowner=False, callargs=None,
            assignedto=None) -> ReprAndType:
        gt = self.types.get

        def repr_and_type(r: Union[ReprAndType, str], etype=None) -> ReprAndType:
            if isinstance(r, tuple):
                r, rtype = r
                if etype is None:
                    etype = rtype

            if etype is not None:
                return r, etype
            else:
                typeinfo = self.gettype(r)
                return r, typeinfo[0] if typeinfo else etype

        if isinstance(expr, AST_ELLIPSIS):
            return '/* ... */', None

        elif isinstance(expr, AST_NAME_CONSTANT):
            return self.constants.get(expr.value, (expr.value, None))

        elif isinstance(expr, AST_STR):
            # TODO: just use repr(s) with some cleanup?
            s = expr.s.replace('\\', '\\\\')
            s = s.replace('"', r'\"')
            s = ''.join(repr(c)[1:-1].replace(r'\x', r'\u00')
                        if c.isspace() else c for c in s)
            return (str(expr.s) if annot else f'"{s}"'), gt('str')

        elif isinstance(expr, AST_NUM):
            s = str(expr.n)
            return s, gt('float' if '.' in s else 'int')

        elif isinstance(expr, ast.Constant):
            if expr.value is Ellipsis:
                return '/* ... */', None
            return self.constants.get(expr.value, (expr.value, None))

        elif isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub):
            s, t = self.repr_expr_and_type(expr.operand)
            return f'-{expr.operand.n}', t # type: ignore

        elif isinstance(expr, ast.Name):
            name = self.map_name(expr.id, callargs)
            return repr_and_type(name)

        elif isinstance(expr, ast.Attribute):
            owner = self.repr_expr(expr.value, isowner=True)
            if (owner, expr.attr) == ('re', 'compile'):
                return self.new_regexp(callargs)
            rt = self.map_attr(owner, expr.attr, callargs=callargs)
            return repr_and_type(rt)

        elif isinstance(expr, ast.Call):
            return self._map_call(expr, isowner=isowner)

        elif isinstance(expr, ast.Subscript):
            return self._map_subscript(expr, annot=annot)

        elif isinstance(expr, ast.Compare):
            left = self.repr_expr(expr.left)
            op = expr.ops[0]
            right = ', '.join(self.repr_expr(c) for c in expr.comparators)
            return self.map_compare(left, op, right), None

        elif isinstance(expr, ast.IfExp):
            scope = self.new_scope(expr)
            test = self._cast(self._thruthy(self.repr_expr(expr.test)))
            then = self._cast(self.repr_expr(expr.body))
            self.exit_scope()
            self._check_after_negation(keep=True)
            other = self._cast(self.repr_expr(expr.orelse))
            return f'({test} ? {then} : {other})', None

        elif isinstance(expr, ast.BoolOp):
            if isinstance(expr.op, ast.And):
                joiner = self.operators[ast.And]
            elif isinstance(expr.op, ast.Or):
                joiner = self.operators[ast.Or]
            boolexpr = f' {joiner} '.join(
                    self._thruthy(self.repr_expr(self._check_after_negation(v, keep=True)))
                    for v in expr.values)
            # TODO: don't wrap in parens unless parent is BoolOp (5f76eae2)?
            return f'({boolexpr})' if len(expr.values) > 1 else boolexpr, None

        elif isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.Not):
                self._in_negation = True
                s, t = self.repr_expr_and_type(expr.operand)
                s = self._negated(s)
                self._in_negation = False
                return s, t

        elif isinstance(expr, ast.Tuple):
            if assignedto:
                return self.unpack_tuple(expr, assignedto)
            else:
                return repr_and_type(self.map_tuple(expr))

        elif isinstance(expr, ast.Dict):
            return repr_and_type(self.map_dict(expr))

        elif isinstance(expr, ast.List):
            return repr_and_type(self.map_list(expr))

        elif isinstance(expr, ast.Set):
            return repr_and_type(self.map_set(expr))

        elif isinstance(expr, ast.JoinedStr):
            return self.map_joined_str(expr), gt('str')

        elif isinstance(expr, ast.GeneratorExp):
            # TODO: just support GeneratorExp with any/all
            #raise NotImplementedError(ast.dump(expr))
            #return self.map_generator(expr), None
            return ast.dump(expr), None

        elif isinstance(expr, ast.ListComp):
            return repr_and_type(self.map_listcomp(expr), gt('List'))

        elif isinstance(expr, ast.DictComp):
            return repr_and_type(self.map_dictcomp(expr), gt('Map'))

        elif expr is None:
            return self.none, None

        elif isinstance(expr, ast.BinOp):
            if isinstance(expr.op, ast.Add):
                lexpr = self.repr_expr(expr.left)
                ltype = self.gettype(lexpr)
                # TODO: the `or` is a hack since type inference is still too shallow (use "in_boolop (5f54c8e1, 5f76eae2) to control better?)
                if self.list_concat and (ltype and 'List' in ltype[0] or 'List' in lexpr):
                    return self.list_concat.format(left=lexpr,
                            right=self.repr_expr(expr.right)), gt('List')
                bop = '+'
            elif isinstance(expr.op, ast.Sub):
                bop = '-'
            elif isinstance(expr.op, ast.Mult):
                bop = '*'
            elif isinstance(expr.op, ast.Div):
                bop = '/'
            elif isinstance(expr.op, ast.Mod):
                bop = '%'
            return f'{self.repr_expr(expr.left)} {bop} {self.repr_expr(expr.right)}', None

        elif isinstance(expr, ast.Yield):
            return self.add_to_iterator(expr.value), None

        elif isinstance(expr, ast.YieldFrom):
            return self.add_all_to_iterator(expr.value), None

        elif isinstance(expr, ast.Lambda):
            return self._map_lambda(expr), gt('function')

        raise NotImplementedError(f'unhandled: {expr!r}')

    def repr_cast(self, type, expr) -> str:
        return  f'({type}) {expr}'

    def to_var_name(self, name):
        return name

    def to_attribute_name(self, attr):
        return attr

    def map_compare(self, left: str, op: ast.cmpop, right: str) -> str:
        if isinstance(op, ast.In):
            return self.map_in(right, left)
        elif isinstance(op, ast.NotIn):
            return self.map_in(right, left, negated=True)
        elif isinstance(op, ast.Eq):
            if right.replace('-', '').isnumeric():
                return self._fmt_op(ast.Is, left, right)
            return self._fmt_op(ast.Eq, left, right)
        elif isinstance(op, ast.NotEq):
            if right.replace('-', '').isnumeric():
                return self._fmt_op(ast.IsNot, left, right)
            return self._fmt_op(ast.NotEq, left, right)
        else:
            ltype_narrowed = self.gettype(left)
            mop = self.operators[type(op)]
            if self.strcmp and ('>' in mop or '<' in mop) and ltype_narrowed and ltype_narrowed[0] == self.types['str']:
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

    def _map_call(self, expr: ast.Call, isowner=False) -> ReprAndType:
        gt = self.types.get

        call_args: list = expr.args
        if expr.keywords:
            # FIXME: [5f55548d] handle order of kwargs and transpile Lambdas
            warn(f'keywords in call: {ast.dump(expr)}')
            call_args += [kw.value for kw in expr.keywords if kw.arg]

        callargs = [self._cast(self.repr_expr(arg)) for arg in call_args]

        self._last_cast = None

        if isinstance(expr.func, ast.Name):
            funcname = expr.func.id

            if funcname == 'isinstance':
                return self._map_isinstance(expr), gt('bool')

            elif funcname == 'cast':
                arg0typerepr = self.repr_expr(call_args[0], annot=True)
                arg1repr, arg1typerepr = self.repr_expr_and_type(call_args[1])
                # TODO: 5f831dc1 (java-specific)
                castvalue = self.repr_cast(arg0typerepr, arg1repr)
                self._last_cast = arg0typerepr
                if not self.typing:
                    return arg1repr, arg0typerepr
                #if isowner:
                #    castvalue = f'({castvalue})'
                return f'({castvalue})', arg0typerepr

            elif funcname == 'any':
                return self.map_any(expr.args[0]), gt('bool')

            elif funcname == 'all':
                return self.map_all(expr.args[0]), gt('bool')

            elif funcname == 'len':
                return self.map_len(self.repr_expr(call_args[0])), gt('int')

        return self.repr_expr_and_type(expr.func, callargs=callargs)

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

    def _map_subscript(self, expr, annot) -> ReprAndType:
        owner, ownertype = self.repr_expr_and_type(expr.value, annot=annot)

        if isinstance(expr.slice, ast.Slice):
            lower = self.repr_expr(expr.slice.lower)
            upper = self.repr_expr(expr.slice.upper) if expr.slice.upper else None
            return self.map_getslice(owner, lower, upper), ownertype

        sliceval = _get_slice(expr.slice)

        if isinstance(sliceval, ast.Constant):
            tname = sliceval.value if annot else self.repr_expr(sliceval)
        elif isinstance(sliceval, AST_STR):
            tname = sliceval.s if annot else self.repr_expr(sliceval)
        elif isinstance(sliceval, ast.Tuple):
            tname = ', '.join(self.repr_expr(p.elts[0]
                                    if isinstance(p, ast.List) # Callable[[A1], RT]
                                    else p,
                                    annot=annot)
                              for p in sliceval.elts)
        elif isinstance(sliceval, ast.Subscript):
            tname = self.repr_expr(sliceval, annot=annot)
        else:
            tname = self.repr_expr(sliceval, annot=annot)

        if isinstance(tname, int):
            tname = str(tname)

        tname = self.types.get(tname, tname)

        if annot:
            if isinstance(expr.value, ast.Name) and expr.value.id == 'Optional' \
                    and self.optional_type_form:
                return self.optional_type_form.format(tname), None

            # TODO: unhack the static_annotation_form and cleantype juggling
            if isinstance(expr.value, ast.Name) and expr.value.id == 'ClassVar' \
                    and self.static_annotation_form:
                return self.static_annotation_form.format(tname), None

            if owner == 'Union' and self.union_surrogate:
                return self.union_surrogate, None
            return f'{owner}<{tname}>', None

        containertype = self.container_type(ownertype) if ownertype else None
        containedtype = containertype.contained if containertype else None

        if containedtype and ', ' in containedtype:
            containedtype = containedtype.split(', ', 1)[-1]

        return self.map_getitem(owner, tname), containedtype

    def _cast(self, name, parens=False, lvaltype=None):
        if not self.typing:
            return name
        ntype_narrowed = self.gettype(name)
        if ntype_narrowed and ntype_narrowed[1] and ntype_narrowed != lvaltype:
            result = self.repr_cast(ntype_narrowed[0], name)
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

    def container_type(self, containertype: Optional[str]) -> Optional[ContainerType]:
        # TODO: 5f831dc1 (java-specific)
        if containertype is None:
            return None
        if containertype.endswith('>'):
            container, contained = containertype.split('<', 1)
            contained = contained[:-1]
            return ContainerType(container, contained)
        return None

    def isname(self, expr) -> bool:
        return re.match(r'^(\w|_)+$', expr) is not None

    def typed(self, name: str, typename: Optional[str] = None):
        raise NotImplementedError

    def funcdef(self, name: str, args: List[Tuple], ret: Optional[str] = None):
        raise NotImplementedError

    def overload(self, name: str, args: List[Tuple], ret: Optional[str] = None):
        return self.funcdef(name, args, ret)

    def map_assert(self, expr: str, failmsg: str) -> str:
        raise NotImplementedError

    def map_for(self, container: str, ctype: str, part: str, parttype: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
        raise NotImplementedError

    def map_enumerated_for(self, container: str, ctype: str, part: str, parttype: str, counter: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
        raise NotImplementedError

    def map_for_to(self, counter: str, ceiling: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
        raise NotImplementedError

    def map_name(self, name: str, callargs: List[str] = None) -> str:
        if name == 'self':
            return self.this

        if callargs:
            map_repr = self.function_map.get(name)
            if map_repr:
                if isinstance(map_repr, list):
                    map_repr = map_repr[len(callargs) - 1]
                return map_repr.format(*callargs)

        name = self._type_alias.get(name, name)
        obj = self.types.get(name) or self.to_attribute_name(name)

        if callargs is not None:
            argrepr = ', '.join(callargs)
            if obj in self.classes or obj[0].isupper():
                return f'{self.mknew}{obj}({argrepr})'
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

    def unpack_tuple(self, expr: ast.Tuple, assignedto=None) -> Tuple[str, str]:
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

    def handle_with(self, expr: str, var: str) -> Tuple[str, List]:
        raise NotImplementedError

    def new_regexp(self, callargs) -> Tuple[str, str]:
        raise NotImplementedError


def warn(msg):
    print(f'WARNING: {msg}', file=sys.stderr)


def camelize(s: str) -> str:
    if s == '_':
        return s

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
