from raemf_mc.config import load_config


def test_comparison_config_inherits_baseline_and_overrides_mode():
    config = load_config("configs/comparison/variational_posterior_mc.yaml")
    assert config["target"]["volatility_window"] == 40
    assert config["bayesian"]["enabled"] is True
    assert config["monte_carlo"]["scenario_mode"] == "variational_posterior"
