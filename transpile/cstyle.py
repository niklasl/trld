from typing import Optional
from .base import Transpiler, camelize, under_camelize


class CStyleTranspiler(Transpiler):
    #class_casing = Casing.UpperCamelCase
    #constant_casing = Casing.UPPER_SNAKE_CASE
    #method_casing = Casing.lowerCamelCase
    #name_casing = Casing.lowerCamelCase
    mknew = 'new '
    extends_keyword = 'extends'
    begin_block = ' {'
    end_block = '}'
    end_stmt = ';'
    this = 'this'
    void = 'void'
    none = 'null'
    line_comment = '//'
    inline_comment = '/*', '*/'
    indent = '  '

    def to_var_name(self, name):
        return camelize(name)

    def to_attribute_name(self, attr):
        if attr == '__str__':
            return 'toString'
        elif attr == '__eq__':
            return 'equals'
        return under_camelize(attr, self.protected == '_')
