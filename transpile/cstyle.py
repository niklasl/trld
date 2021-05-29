from typing import Optional
from .base import Transpiler #, Casing


class CStyleTranspiler(Transpiler):
    #class_casing = Casing.UpperCamelCase
    #constant_casing = Casing.UPPER_SNAKE_CASE
    #method_casing = Casing.lowerCamelCase
    #name_casing = Casing.lowerCamelCase
    mknew = 'new '
    begin_block = ' {'
    end_block = '}'
    end_stmt = ';'
    this = 'this'
    void = 'void'
    none = 'null'
    line_comment = '//'
    inline_comment = '/*', '*/'
    indent = '  '

    def typed(self, name, typename=None):
        return f'{typename} {name}' if typename and self.typing else name

    def funcdef(self, name: str, args: str, ret: Optional[str] = None):
        if ret == '':
            return f'{name}({args})'
        return f"{ret or 'void'} {name}({args})"
