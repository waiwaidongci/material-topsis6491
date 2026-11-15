"""Formula parser: dimension checks, dependency extraction and evaluation."""
import math
import pytest
from src.services.derivation.formula import (
    parse, dependencies, infer_dimensions, evaluate, FormulaError)
from src.services.derivation import dimensions as dims

L, M, T, I, C = (1, 0, 0, 0, 0), (0, 1, 0, 0, 0), (0, 0, 1, 0, 0), (0, 0, 0, 1, 0), (0, 0, 0, 0, 1)


def test_dependencies_extracted():
    node = parse('absorption / thickness + areal_density * 2')
    assert dependencies(node) == {'absorption', 'thickness', 'areal_density'}


def test_dimensional_arithmetic():
    ref = {'absorption': dims.DIMENSIONLESS, 'thickness': L}
    assert infer_dimensions(parse('absorption / thickness'), ref) == (-1, 0, 0, 0, 0)
    assert infer_dimensions(parse('thickness ^ 2'), ref) == (2, 0, 0, 0, 0)


def test_dimensional_mismatch_rejected():
    ref = {'thickness': L, 'mass': M}
    with pytest.raises(FormulaError):
        infer_dimensions(parse('thickness + mass'), ref)


def test_sqrt_even_dimensions():
    ref = {'area': (2, 0, 0, 0, 0)}
    assert infer_dimensions(parse('sqrt(area)'), ref) == (1, 0, 0, 0, 0)
    with pytest.raises(FormulaError):
        infer_dimensions(parse('sqrt(thickness)'), {'thickness': L})


def test_log_requires_dimensionless():
    with pytest.raises(FormulaError):
        infer_dimensions(parse('log(thickness)'), {'thickness': L})
    assert infer_dimensions(parse('log(absorption)'), {'absorption': dims.DIMENSIONLESS}) == dims.DIMENSIONLESS


def test_evaluation_basic():
    node = parse('price / areal_density')
    value, refs = evaluate(node, {'price': 120.0, 'areal_density': 3.0})
    assert value == 40.0
    assert set(refs) == {'price', 'areal_density'}


def test_missing_propagates_as_none():
    node = parse('absorption / thickness')
    value, _ = evaluate(node, {'absorption': 0.8, 'thickness': None})
    assert value is None


def test_divide_by_zero_and_negative_sqrt():
    with pytest.raises(FormulaError):
        evaluate(parse('a / b'), {'a': 1.0, 'b': 0.0})
    with pytest.raises(FormulaError):
        evaluate(parse('sqrt(a)'), {'a': -4.0})


def test_disallowed_syntax():
    for bad in ('__import__("os")', 'a.b', 'a + ', 'lambda: 1', 'a # comment', 'a & b'):
        with pytest.raises(FormulaError):
            parse(bad)


def test_nested_functions_and_min_max():
    node = parse('sqrt(absorption) + min(price, carbon)')
    value, _ = evaluate(node, {'absorption': 0.64, 'price': 10.0, 'carbon': 20.0})
    assert math.isclose(value, 0.8 + 10.0)
