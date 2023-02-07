from __future__ import annotations
from typing import NamedTuple, Dict, List, Tuple, Union, Optional
import ast
from collections import OrderedDict
from pathlib import Path
import os


class ClassType(NamedTuple):
    name: str
    members: OrderedDict[str, str]
    base: Optional[str] = None


class FuncType(NamedTuple):
    args: OrderedDict[str, str]
    returns: str
    protocol: Optional[ClassType] = None


Type = Union[str, ClassType, FuncType]


class TypeScanner(ast.NodeVisitor):

    def __init__(self, transpiler = None):
        self.modules: Dict[str, Dict[str, Type]] = {}
        self._protocols = {}
        self._in_src: List[Path] = []
        self._within: List[str] = []
        if transpiler:
            self._transpiler = transpiler
            self.repr_annot = transpiler.repr_annot
            self.map_name = transpiler.map_name

    @property
    def module(self):
        src = str(self._in_src[-1])
        return self.modules.setdefault(src, {'__file': src})

    def read(self, src):
        self._in_src.append(Path(src))
        with open(src) as f:
            code = f.read()
        tree = ast.parse(code)
        self.visit(tree)
        self._in_src.pop()

    def visit_ImportFrom(self, node):
        if node.module == 'typing':
            self._transpiler.visit_ImportFrom(node)
            return

        if node.level == 0:
            return

        if self._in_src:
            basedir = self._in_src[-1].parent
        if node.module is not None:
            src = node.module.replace('.', os.sep)
            if basedir:
                for i in range(node.level - 1):
                    basedir = basedir.parent
                src = basedir / src
            src = src.with_suffix('.py')

            imprefs = self.module.setdefault('__imports', {})
            for impname in node.names:
                imprefs[impname.name] = str(src)

            self.read(src)

    def visit_Assign(self, node):
        self._transpiler._handle_type_alias(node)
        name = self.map_name(self._transpiler.repr_annot(node.targets[0]))
        typename = self._transpiler.repr_expr_and_type(node.value)[1]
        self.addtype(name, typename)

    def visit_AnnAssign(self, node):
        name = self.map_name(self.repr_annot(node.target))
        typename = self.repr_annot(node.annotation)
        self.addtype(name, typename)

    def visit_FunctionDef(self, node):
        name = self.map_name(node.name)
        args = OrderedDict()
        for arg in node.args.args:
            aname = self.map_name(arg.arg)
            args[aname] = self.repr_annot(arg.annotation)
        ret = self.repr_annot(node.returns) if node.returns else None
        signature = tuple(arg for arg in args.items())
        protocol = self._protocols.get(signature)
        self.addtype(name, FuncType(args, ret, protocol))

    def visit_ClassDef(self, node):
        name = self.map_name(node.name)
        self._within.append(name)
        base_repr = self.repr_annot(node.bases[0]) if node.bases else None
        clstype = ClassType(name, OrderedDict(), base_repr)
        self.module[name] = clstype
        self.generic_visit(node)
        self._within.pop()
        if base_repr == 'Protocol':
            callname = self.map_name('__call__')
            proto_args = (self.module[name].members[callname].args)
            proto_args = tuple(arg for arg in list(proto_args.items())[1:])
            self._protocols[proto_args] = clstype

    def addtype(self, name: str, typename: str, narrowed=False):
        ns = self.module[self._within[-1]] if self._within else self.module
        if isinstance(ns, ClassType):
            ns = ns.members
        ns[name] = typename


if __name__ == '__main__':
    import sys
    import json
    from .java import JavaTranspiler

    typescanner = TypeScanner(JavaTranspiler())
    sort_keys = False

    for src in sys.argv[1:]:
        if src == '-k':
            sort_keys = True
            continue

        typescanner.read(src)

    print(json.dumps(typescanner.modules, indent=2, sort_keys=sort_keys))
