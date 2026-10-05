import sys

from rerank.scorer import rank_from_scores


def test_rank_from_scores_order_and_confidence():
    order, best, confidence = rank_from_scores([-1.0, -3.0, -2.5])
    assert order == [0, 2, 1] and best == 0 and abs(confidence - 1.5) < 1e-9


def test_single_and_empty_inputs():
    assert rank_from_scores([-1.0]) == ([0], 0, 0.0)
    assert rank_from_scores([]) == ([], None, 0.0)


def test_ties_are_stable():
    assert rank_from_scores([0.0, 0.0, -1.0])[0] == [0, 1, 2]


def test_import_does_not_load_mlx():
    import rerank.scorer  # noqa: F401
    assert not any(name == "mlx" or name.startswith("mlx.") for name in sys.modules)
