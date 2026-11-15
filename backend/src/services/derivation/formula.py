"""Restricted formula language for derived criteria.

Grammar (no attribute access, no calls beyond an allow-list, no literals other
than non-negative numbers)::

    expr    := term (('+' | '-') term)*
    term    := factor (('*' | '/') factor)*
    factor  := unary (('^') number)?        # exponent must be a non-negative literal
    unary   := '-' unary | primary
    primary := number | name | func '(' expr (',' expr)* ')' | '(' expr ')'

Identifiers reference other criteria of the same study by code.  The same AST
drives numeric evaluation, dimensional inference and dependency extraction, so
the three can never disagree.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import dimensions as dims

ALLOWED_FUNCTIONS = {'sqrt', 'log', 'exp', 'abs', 'min', 'max'}
# Functions that only accept dimensionless arguments and return dimensionless.
DIMENSIONLESS_FUNCTIONS = {'log', 'exp'}
_IDENT_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


class FormulaError(ValueError):
    pass


@dataclass
class Node:
    kind: str
    value: object = None
    left: 'Node | None' = None
    right: 'Node | None' = None
    args: list | None = None


def _tokenize(text: str):
    tokens, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit() or (ch == '.' and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (text[j].isdigit() or text[j] == '.'):
                j += 1
            literal = text[i:j]
            try:
                number = float(literal)
            except ValueError:
                raise FormulaError(f'数字无法解析: {literal}')
            if not math.isfinite(number):
                raise FormulaError('公式只接受有限数字')
            tokens.append(('num', number))
            i = j
        elif ch.isalpha() or ch == '_':
            j = i
            while j < n and text[j] in _IDENT_CHARS:
                j += 1
            tokens.append(('name', text[i:j]))
            i = j
        elif ch in '+-*/^(),':
            tokens.append((ch, ch))
            i += 1
        else:
            raise FormulaError(f'公式含不允许的字符: {ch}')
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _take(self, kind=None):
        token = self._peek()
        if kind is not None and token[0] != kind:
            raise FormulaError(f'公式语法错误，期望 {kind}')
        self.pos += 1
        return token

    def parse(self) -> Node:
        if not self.tokens:
            raise FormulaError('公式为空')
        node = self._expr()
        if self.pos != len(self.tokens):
            raise FormulaError('公式存在无法解析的剩余片段')
        return node

    def _expr(self) -> Node:
        node = self._term()
        while self._peek()[0] in ('+', '-'):
            op, _ = self._take()
            node = Node('bin', op, node, self._term())
        return node

    def _term(self) -> Node:
        node = self._factor()
        while self._peek()[0] in ('*', '/'):
            op, _ = self._take()
            node = Node('bin', op, node, self._factor())
        return node

    def _factor(self) -> Node:
        node = self._unary()
        if self._peek()[0] == '^':
            self._take('^')
            kind, number = self._take('num')
            if number < 0 or not math.isfinite(number):
                raise FormulaError('幂指数须为非负有限数字')
            node = Node('pow', number, left=node)
        return node

    def _unary(self) -> Node:
        if self._peek()[0] == '-':
            self._take('-')
            return Node('neg', left=self._unary())
        if self._peek()[0] == '+':
            self._take('+')
            return self._unary()
        return self._primary()

    def _primary(self) -> Node:
        kind, value = self._peek()
        if kind == 'num':
            self._take()
            return Node('num', value)
        if kind == 'name':
            self._take()
            if self._peek()[0] == '(':
                return self._call(value)
            return Node('ref', value)
        if kind == '(':
            self._take('(')
            node = self._expr()
            self._take(')')
            return node
        raise FormulaError('公式语法错误：缺少操作数')

    def _call(self, name: str) -> Node:
        if name not in ALLOWED_FUNCTIONS:
            raise FormulaError(f'不支持的函数: {name}')
        self._take('(')
        args = [self._expr()]
        while self._peek()[0] == ',':
            self._take(',')
            args.append(self._expr())
        self._take(')')
        if name in ('sqrt', 'log', 'exp', 'abs') and len(args) != 1:
            raise FormulaError(f'{name} 接受且仅接受一个参数')
        if name in ('min', 'max') and len(args) < 2:
            raise FormulaError(f'{name} 至少需要两个参数')
        return Node('call', name, args=args)


def parse(text: str) -> Node:
    if not isinstance(text, str) or not text.strip():
        raise FormulaError('公式为空')
    if len(text) > 600:
        raise FormulaError('公式长度不能超过600字符')
    return _Parser(_tokenize(text.strip())).parse()


def dependencies(node: Node) -> set[str]:
    if node.kind == 'ref':
        return {node.value}
    if node.kind == 'num':
        return set()
    if node.kind == 'neg':
        return dependencies(node.left)
    if node.kind == 'pow':
        return dependencies(node.left)
    if node.kind == 'bin':
        return dependencies(node.left) | dependencies(node.right)
    if node.kind == 'call':
        result = set()
        for arg in node.args:
            result |= dependencies(arg)
        return result
    raise FormulaError('未知公式节点')


def infer_dimensions(node: Node, ref_dims: dict) -> tuple:
    """ref_dims maps referenced criterion code -> dimension tuple."""
    kind = node.kind
    if kind == 'num':
        return dims.DIMENSIONLESS
    if kind == 'ref':
        if node.value not in ref_dims:
            raise FormulaError(f'公式引用了未定义的指标: {node.value}')
        return tuple(ref_dims[node.value])
    if kind == 'neg':
        return infer_dimensions(node.left, ref_dims)
    if kind == 'pow':
        base = infer_dimensions(node.left, ref_dims)
        exponent = node.value
        if abs(exponent - round(exponent)) > 1e-9 and base != dims.DIMENSIONLESS:
            raise FormulaError('非整数次幂只能作用于无量纲量（量纲一致性检查未通过）')
        return dims.scale(base, int(round(exponent)) if abs(exponent - round(exponent)) <= 1e-9 else 0)
    if kind == 'bin':
        left = infer_dimensions(node.left, ref_dims)
        right = infer_dimensions(node.right, ref_dims)
        if node.value in ('+', '-'):
            if not dims.compatible(left, right):
                raise FormulaError(
                    f'加减两侧量纲不一致: {dims.format_dims(left)} 与 {dims.format_dims(right)}'
                )
            return left
        if node.value == '*':
            return dims.add(left, right)
        return dims.sub(left, right)
    if kind == 'call':
        arg_dims = [infer_dimensions(arg, ref_dims) for arg in node.args]
        name = node.value
        if name in DIMENSIONLESS_FUNCTIONS:
            if any(d != dims.DIMENSIONLESS for d in arg_dims):
                raise FormulaError(f'{name} 的参数必须是无量纲量')
            return dims.DIMENSIONLESS
        if name == 'sqrt':
            if any(any(exp % 2 != 0 for exp in d) for d in arg_dims):
                raise FormulaError('sqrt 只能作用于各量纲指数均为偶数的量')
            return dims.scale(arg_dims[0], 0) if arg_dims[0] == dims.DIMENSIONLESS else tuple(e // 2 for e in arg_dims[0])
        if name == 'abs':
            return arg_dims[0]
        if name in ('min', 'max'):
            first = arg_dims[0]
            if any(not dims.compatible(first, other) for other in arg_dims[1:]):
                raise FormulaError(f'{name} 的参数量纲必须一致')
            return first
    raise FormulaError('量纲推断失败')


def evaluate(node: Node, values: dict):
    """Return (value, refs_used). Missing/propagated inputs yield (None, refs)."""
    kind = node.kind
    if kind == 'num':
        return node.value, []
    if kind == 'ref':
        used = [node.value]
        value = values.get(node.value)
        return (None if value is None else float(value)), used
    if kind == 'neg':
        value, used = evaluate(node.left, values)
        return (None if value is None else -value), used
    if kind == 'pow':
        value, used = evaluate(node.left, values)
        if value is None:
            return None, used
        return math.pow(value, node.value), used
    if kind == 'bin':
        left, used_left = evaluate(node.left, values)
        right, used_right = evaluate(node.right, values)
        used = used_left + used_right
        if left is None or right is None:
            return None, used
        if node.value == '+':
            return left + right, used
        if node.value == '-':
            return left - right, used
        if node.value == '*':
            return left * right, used
        if node.value == '/':
            if right == 0:
                raise FormulaError('公式遇到除以零')
            return left / right, used
    if kind == 'call':
        evaluated, used = [], []
        for arg in node.args:
            value, arg_used = evaluate(arg, values)
            evaluated.append(value)
            used.extend(arg_used)
        if any(value is None for value in evaluated):
            return None, used
        name = node.value
        if name == 'sqrt':
            if evaluated[0] < 0:
                raise FormulaError('sqrt 的参数为负')
            return math.sqrt(evaluated[0]), used
        if name == 'log':
            if evaluated[0] <= 0:
                raise FormulaError('log 的参数须为正')
            return math.log(evaluated[0]), used
        if name == 'exp':
            return math.exp(evaluated[0]), used
        if name == 'abs':
            return abs(evaluated[0]), used
        if name == 'min':
            return min(evaluated), used
        if name == 'max':
            return max(evaluated), used
    raise FormulaError('公式求值失败')
