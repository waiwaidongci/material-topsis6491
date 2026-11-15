"""Derived-criterion dependency graph.

The graph is rebuilt from the criterion definitions of one study.  It performs
cycle detection, topological ordering and per-sample evaluation with explicit
missing-value propagation.  Every derived value keeps a step-by-step trace so
frozen snapshots carry their full provenance.
"""
from __future__ import annotations

from . import dimensions as dims
from .formula import FormulaError, dependencies, evaluate, infer_dimensions, parse


class GraphError(ValueError):
    pass


def topological_order(criteria: list[dict], base_refs: set[str] | None = None) -> list[str]:
    """Kahn's algorithm.  Each criterion dict needs code/kind/formula.

    base_refs names research-defined base quantities that formulas may use even
    when they are not themselves trade-off criteria.
    """
    by_code = {c['code']: c for c in criteria}
    if len(by_code) != len(criteria):
        raise GraphError('指标代码重复，无法构建派生关系')
    base_refs = set(base_refs or ())
    deps_map = {}
    for c in criteria:
        if c['kind'] == 'derived':
            node = parse(c['formula'])
            refs = dependencies(node)
            unknown = refs - set(by_code) - base_refs
            if unknown:
                raise GraphError(f"指标 {c['code']} 引用了未定义指标或基础量: {sorted(unknown)}")
            deps_map[c['code']] = {r for r in refs if r in by_code}
        else:
            deps_map[c['code']] = set()
    indegree = {code: 0 for code in by_code}
    children = {code: [] for code in by_code}
    for code, deps in deps_map.items():
        indegree[code] = len(deps)
        for dep in deps:
            children[dep].append(code)
    ready = sorted(code for code, degree in indegree.items() if degree == 0)
    order = []
    while ready:
        code = ready.pop(0)
        order.append(code)
        for child in sorted(children[code]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()
    if len(order) != len(by_code):
        cyclic = sorted(code for code, degree in indegree.items() if degree > 0)
        raise GraphError(f'检测到循环引用，涉及指标: {cyclic}')
    return order


def validate_definition(code: str, kind: str, formula: str, criteria: list[dict],
                        base_refs: set[str] | None = None):
    """Validate one definition against the other (existing) criteria.

    Returns (parsed_node, refs, inferred_dimensions) or raises GraphError.
    """
    base_refs = set(base_refs or ())
    by_code = {c['code']: c for c in criteria if c['code'] != code}
    if kind == 'base':
        return None, set(), None
    node = parse(formula)
    refs = dependencies(node)
    unknown = refs - set(by_code) - base_refs
    if unknown:
        raise GraphError(f'公式引用了未定义的指标或基础量: {sorted(unknown)}')
    if code in refs:
        raise GraphError('指标公式不能引用自身')
    ref_dims = {c['code']: tuple(c['dims']) for c in by_code.values()}
    inferred = infer_dimensions(node, ref_dims)
    # Full-graph cycle check with this definition included.
    candidate = [
        {**c, 'formula': c.get('formula') or ''} for c in criteria if c['code'] != code
    ] + [{'code': code, 'kind': 'derived', 'formula': formula}]
    topological_order(candidate, base_refs)
    return node, refs, inferred


def downstream(criteria: list[dict], changed_codes: set[str]) -> set[str]:
    """All derived criteria transitively depending on any changed code."""
    criterion_codes = {c['code'] for c in criteria}
    children = {c['code']: set() for c in criteria}
    for c in criteria:
        if c['kind'] == 'derived':
            for dep in dependencies(parse(c['formula'])):
                if dep in children:
                    children[dep].add(c['code'])
    affected, frontier = set(), set(changed_codes & criterion_codes)
    while frontier:
        code = frontier.pop()
        for child in children.get(code, ()):
            if child not in affected:
                affected.add(child)
                frontier.add(child)
    return affected


def evaluate_study(criteria: list[dict], base_values: dict, base_dims: dict | None = None):
    """Evaluate every criterion for one sample.

    base_values maps criterion/base code -> float|None for base quantities.
    base_dims supplies dimensions of research base quantities used in formulas
    without being criteria themselves.
    Returns (values, traces, missing_reasons) keyed by derived code.
    """
    base_refs = set((base_dims or {}))
    order = topological_order(criteria, base_refs)
    by_code = {c['code']: c for c in criteria}
    values = dict(base_values)
    traces: dict[str, dict] = {}
    missing: dict[str, str] = {}
    for code in order:
        criterion = by_code[code]
        if criterion['kind'] == 'base':
            if values.get(code) is None:
                missing[code] = '基础量缺测，资料库未录入该测量值'
            continue
        node = parse(criterion['formula'])
        refs = sorted(dependencies(node))
        blocked = [r for r in refs if values.get(r) is None]
        if blocked:
            values[code] = None
            chain = sorted({missing.get(r, r) for r in blocked})
            reason = f"上游缺测传播: {', '.join(blocked)}（{'; '.join(chain)}）"
            missing[code] = reason
            traces[code] = {'code': code, 'formula': criterion['formula'], 'value': None,
                            'inputs': {r: values.get(r) for r in refs}, 'excluded': True, 'reason': reason}
            continue
        try:
            value, used = evaluate(node, values)
        except FormulaError as exc:
            values[code] = None
            missing[code] = f'公式无法计算: {exc}'
            traces[code] = {'code': code, 'formula': criterion['formula'], 'value': None,
                            'inputs': {r: values.get(r) for r in refs}, 'excluded': True,
                            'reason': f'公式无法计算: {exc}'}
            continue
        if value is None or value != value or value in (float('inf'), float('-inf')):
            values[code] = None
            missing[code] = '公式结果非有限值'
            traces[code] = {'code': code, 'formula': criterion['formula'], 'value': None,
                            'inputs': {r: values.get(r) for r in refs}, 'excluded': True,
                            'reason': '公式结果非有限值'}
            continue
        if value < 0:
            values[code] = None
            missing[code] = f'派生结果为负({value:.6g})，物理指标要求非负'
            traces[code] = {'code': code, 'formula': criterion['formula'], 'value': None,
                            'inputs': {r: values.get(r) for r in refs}, 'excluded': True,
                            'reason': missing[code]}
            continue
        traces[code] = {'code': code, 'formula': criterion['formula'], 'value': value,
                        'inputs': {r: values.get(r) for r in refs}, 'excluded': False, 'reason': ''}
        values[code] = value
    return values, traces, missing
