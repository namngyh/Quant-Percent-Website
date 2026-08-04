from pathlib import Path

from msdp.training.tuning import make_study_name


def test_study_name_changes_with_data_hash():
    cfg={"run_label":"default"}
    assert make_study_name(cfg,"a"*64)!=make_study_name(cfg,"b"*64)
    assert "default" in make_study_name(cfg,"a"*64)


def test_pipeline_objective_uses_inverse_fold_metrics():
    source=Path("src/msdp/pipeline.py").read_text(encoding="utf-8")
    assert "pred=_inverse(fold_tsc,pred)" in source
    for component in ("pinball_ratio","mae_ratio","brier_ratio","mdd_pinball_ratio","vol_mae_ratio","coverage_penalty","width_ratio"):
        assert component in source


def test_default_and_full_research_budget_is_declared():
    default=Path("configs/default.yaml").read_text(encoding="utf-8")
    full=Path("configs/full.yaml").read_text(encoding="utf-8")
    assert "n_trials: 50" in default and "n_folds: 4" in default and "pruner: hyperband" in default
    assert "n_trials: 80" in full and "n_folds: 5" in full and "pruner: hyperband" in full
