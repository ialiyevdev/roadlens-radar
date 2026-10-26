"""Small deterministic global assignment, without a second numerical runtime.

The shortest augmenting path Hungarian implementation accepts rows <= columns.
Only finite costs are used; callers represent forbidden edges by a large cost.
"""

from math import isfinite


def minimum_cost_assignment(costs: list[list[float]]) -> list[int]:
    """Return one distinct column per row, minimizing the total finite cost."""
    if not costs:
        return []
    rows, columns = len(costs), len(costs[0])
    if columns < rows or any(len(row) != columns for row in costs):
        raise ValueError("Assignment requires a rectangular matrix with rows <= columns.")
    if any(not isfinite(value) for row in costs for value in row):
        raise ValueError("Assignment costs must be finite.")
    u, v = [0.0] * (rows + 1), [0.0] * (columns + 1)
    assigned_row, previous = [0] * (columns + 1), [0] * (columns + 1)
    for row in range(1, rows + 1):
        assigned_row[0] = row
        column = 0
        minimum = [float("inf")] * (columns + 1)
        used = [False] * (columns + 1)
        while True:
            used[column] = True
            current_row = assigned_row[column]
            delta, next_column = float("inf"), 0
            for candidate in range(1, columns + 1):
                if used[candidate]:
                    continue
                reduced = costs[current_row - 1][candidate - 1] - u[current_row] - v[candidate]
                if reduced < minimum[candidate]:
                    minimum[candidate] = reduced
                    previous[candidate] = column
                if minimum[candidate] < delta:
                    delta, next_column = minimum[candidate], candidate
            for candidate in range(columns + 1):
                if used[candidate]:
                    u[assigned_row[candidate]] += delta
                    v[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if assigned_row[column] == 0:
                break
        while column:
            predecessor = previous[column]
            assigned_row[column] = assigned_row[predecessor]
            column = predecessor
    assignment = [-1] * rows
    for column in range(1, columns + 1):
        if assigned_row[column]:
            assignment[assigned_row[column] - 1] = column - 1
    return assignment


def maximum_score_matching(rows: int, columns: int, scores: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    """Maximize valid match count, then total score; unmatched rows get dummies.

    Scores must lie in [0, 2]. The unmatched penalty dominates the full score
    range, so a greedy preference cannot consume the only feasible edge of
    another row. A gate defines feasibility; this is not an identity guarantee.
    """
    if not rows or not columns or not scores:
        return []
    if any(not isfinite(score) or not 0 <= score <= 2 for score in scores.values()):
        raise ValueError("Matching scores must be finite and between zero and two.")
    unmatched = 2 * rows + 1.0
    matrix = [[unmatched * 3] * columns + [unmatched] * rows for _ in range(rows)]
    for (row, column), score in scores.items():
        if not 0 <= row < rows or not 0 <= column < columns:
            raise ValueError("Matching edge index is outside the matrix.")
        matrix[row][column] = 2.0 - score
    assigned = minimum_cost_assignment(matrix)
    return [(row, column) for row, column in enumerate(assigned) if (row, column) in scores]
