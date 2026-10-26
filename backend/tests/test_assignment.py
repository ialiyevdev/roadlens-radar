"""Verify the global solver against exhaustive optima, not tracker output."""

from itertools import permutations
from random import Random

import pytest

from roadlens.assignment import maximum_score_matching, minimum_cost_assignment


def test_assignment_matches_exhaustive_small_rectangular_optima():
    random = Random(731)
    for rows in range(1, 5):
        for columns in range(rows, 6):
            for _ in range(8):
                costs = [[random.uniform(-3, 7) for _ in range(columns)] for _ in range(rows)]
                result = minimum_cost_assignment(costs)
                assert len(set(result)) == rows
                actual = sum(costs[row][column] for row, column in enumerate(result))
                expected = min(sum(costs[row][column] for row, column in enumerate(candidate))
                               for candidate in permutations(range(columns), rows))
                assert actual == pytest.approx(expected)


def test_global_cardinality_does_not_consume_another_rows_only_edge():
    result = maximum_score_matching(2, 2, {(0, 0): 1.9, (0, 1): .1, (1, 0): .2})
    assert result == [(0, 1), (1, 0)]


def test_unmatched_rows_and_forbidden_edges_never_create_an_assignment():
    assert maximum_score_matching(3, 2, {(0, 0): .5, (2, 1): .7}) == [(0, 0), (2, 1)]
    assert maximum_score_matching(2, 2, {}) == []
    assert maximum_score_matching(0, 0, {}) == []
    assert minimum_cost_assignment([]) == []


@pytest.mark.parametrize("costs", [[[1], [2]], [[1, 2], [3]], [[float("nan")]], [[float("inf")]]])
def test_bad_assignment_matrices_are_rejected(costs):
    with pytest.raises(ValueError):
        minimum_cost_assignment(costs)


@pytest.mark.parametrize("scores", [{(0, 0): -1}, {(0, 0): 3}, {(0, 0): float("nan")}, {(3, 0): 1}])
def test_bad_matching_edges_are_rejected(scores):
    with pytest.raises(ValueError):
        maximum_score_matching(2, 2, scores)
