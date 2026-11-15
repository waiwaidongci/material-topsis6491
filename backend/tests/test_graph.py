"""Dependency graph: ordering, cycles, downstream invalidation, trace."""
import pytest
from src.services.derivation.graph import (
    topological_order, validate_definition, downstream, evaluate_study, GraphError)


def _crit(code, kind='base', formula='', dims=None):
    return {'code': code, 'kind': kind, 'formula': formula,
            'dims': dims or [0, 0, 0, 0, 0]}


def test_topological_order_respects_dependencies():
    criteria = [
        _crit('absorption_per_mm', 'derived', 'absorption / thickness', [-1, 0, 0, 0, 0]),
        _crit('absorption'), _crit('thickness', dims=[1, 0, 0, 0, 0]),
        _crit('chain2', 'derived', 'absorption_per_mm + absorption', [-1, 0, 0, 0, 0]),
    ]
    order = topological_order(criteria)
    assert order.index('absorption') < order.index('absorption_per_mm')
    assert order.index('thickness') < order.index('absorption_per_mm')
    assert order.index('absorption_per_mm') < order.index('chain2')


def test_cycle_detected():
    criteria = [
        _crit('a', 'derived', 'b'),
        _crit('b', 'derived', 'c', [0, 0, 0, 0, 0]),
        _crit('c', 'derived', 'a', [0, 0, 0, 0, 0]),
    ]
    with pytest.raises(GraphError, match='循环引用'):
        topological_order(criteria)


def test_unknown_reference_rejected():
    with pytest.raises(GraphError):
        validate_definition('x', 'derived', 'ghost + 1', [_crit('a')])


def test_downstream_chain():
    criteria = [
        _crit('a'), _crit('b'),
        _crit('d1', 'derived', 'a + b'),
        _crit('d2', 'derived', 'd1 * 2'),
        _crit('d3', 'derived', 'b'),
    ]
    assert downstream(criteria, {'a'}) == {'d1', 'd2'}
    assert downstream(criteria, {'b'}) == {'d1', 'd2', 'd3'}


def test_evaluate_study_with_trace_and_propagation():
    criteria = [
        _crit('absorption'), _crit('thickness', dims=[1, 0, 0, 0, 0]),
        _crit('absorption_per_mm', 'derived', 'absorption / thickness', [-1, 0, 0, 0, 0]),
        _crit('double_alpha', 'derived', 'absorption_per_mm * thickness'),
    ]
    values, traces, missing = evaluate_study(
        criteria, {'absorption': 0.8, 'thickness': 20.0})
    assert values['absorption_per_mm'] == pytest.approx(0.04)
    assert values['double_alpha'] == pytest.approx(0.8)
    assert traces['absorption_per_mm']['excluded'] is False
    assert traces['absorption_per_mm']['inputs'] == {'absorption': 0.8, 'thickness': 20.0}
    assert not missing


def test_missing_propagates_down_chain_with_reason():
    criteria = [
        _crit('thickness', dims=[1, 0, 0, 0, 0]), _crit('absorption'),
        _crit('absorption_per_mm', 'derived', 'absorption / thickness', [-1, 0, 0, 0, 0]),
        _crit('double_alpha', 'derived', 'absorption_per_mm * thickness'),
    ]
    values, traces, missing = evaluate_study(
        criteria, {'absorption': None, 'thickness': 20.0})
    assert values['absorption_per_mm'] is None
    assert values['double_alpha'] is None
    assert 'absorption' in missing['absorption_per_mm']
    assert 'absorption_per_mm' in missing['double_alpha']
    assert traces['double_alpha']['excluded'] is True


def test_negative_derived_value_excluded():
    criteria = [_crit('a'), _crit('b'),
                _crit('diff', 'derived', 'a - b')]
    values, traces, missing = evaluate_study(
        criteria, {'a': 1.0, 'b': 3.0})
    assert values['diff'] is None
    assert '负' in missing['diff']
