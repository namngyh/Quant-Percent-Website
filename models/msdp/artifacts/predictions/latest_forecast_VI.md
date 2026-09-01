# Hồ sơ dự báo mới nhất theo kỳ hạn

```json
{
  "run_id": "20260722_154609_gpu",
  "artifact_role": "production",
  "data_date": "2026-08-28 00:00:00",
  "current_vnindex": 1832.12,
  "horizons": [
    {
      "horizon": 5,
      "probability_positive": 0.5683360695838928,
      "return_quantiles": [
        -4.8568339347839355,
        -1.3609009981155396,
        0.057408709079027176,
        1.6472458839416504,
        4.307033538818359
      ],
      "raw_interval": [
        -4.8568339347839355,
        4.307033538818359
      ],
      "calibrated_interval": [
        -5.268196825234544,
        4.718396429268968
      ],
      "projected_index_quantiles": [
        1745.2632106184958,
        1833.1720603704453,
        1912.753864302635
      ],
      "mdd_quantiles": [
        -4.013545513153076,
        -1.1239609718322754,
        -0.3159376084804535
      ],
      "volatility": 13.837944030761719,
      "expert_weights": [
        0.23050034046173096,
        0.26765480637550354,
        0.3129320442676544,
        0.1889127939939499
      ],
      "expert_disagreement": 0.07190041244029999,
      "seed_dispersion_return": 0.5058369040489197,
      "seed_dispersion_direction": 0.045474208891391754,
      "seed_dispersion_mdd": 0.07684767246246338,
      "seed_dispersion_volatility": 0.5866394639015198,
      "confidence_score": 69.28532829228399,
      "confidence_label": "Trung bình",
      "confidence_components": {
        "interval": 0.5271411338962606,
        "coverage": 0.005428226779252143,
        "disagreement": 0.20386007237635706,
        "seed": 0.5129674306393245,
        "drift": 0.20134401654174205
      },
      "confidence_component_sources": {
        "interval": "calibration interval-width percentile",
        "coverage": "calibration coverage",
        "disagreement": "calibration auxiliary disagreement percentile",
        "seed": "calibration seed-dispersion percentiles",
        "drift": "development robust-distance percentile"
      },
      "confidence_missing_components": [],
      "confidence_components_used": [
        "interval",
        "coverage",
        "disagreement",
        "seed",
        "drift"
      ],
      "gate_weights_source": "online_posterior",
      "empirical_coverage": 1.0
    },
    {
      "horizon": 20,
      "probability_positive": 0.5798253417015076,
      "return_quantiles": [
        -9.233323097229004,
        -2.6828670501708984,
        0.42276719212532043,
        4.026744365692139,
        10.433012962341309
      ],
      "raw_interval": [
        -9.233323097229004,
        10.433012962341309
      ],
      "calibrated_interval": [
        -10.301546780505937,
        11.501236645618242
      ],
      "projected_index_quantiles": [
        1670.5293585324287,
        1839.8821394157408,
        2033.5925094175338
      ],
      "mdd_quantiles": [
        -9.52478313446045,
        -3.6755788326263428,
        -1.262542963027954
      ],
      "volatility": 15.79255199432373,
      "expert_weights": [
        0.22834230959415436,
        0.2582905888557434,
        0.3125159740447998,
        0.20085112750530243
      ],
      "expert_disagreement": 0.25882822275161743,
      "seed_dispersion_return": 1.11086905002594,
      "seed_dispersion_direction": 0.043530356138944626,
      "seed_dispersion_mdd": 0.3025963604450226,
      "seed_dispersion_volatility": 0.6943010687828064,
      "confidence_score": 73.23737895573394,
      "confidence_label": "Cao",
      "confidence_components": {
        "interval": 0.5223160434258143,
        "coverage": 0.005428226779252143,
        "disagreement": 0.027744270205066344,
        "seed": 0.4939686369119421,
        "drift": 0.20134401654174205
      },
      "confidence_component_sources": {
        "interval": "calibration interval-width percentile",
        "coverage": "calibration coverage",
        "disagreement": "calibration auxiliary disagreement percentile",
        "seed": "calibration seed-dispersion percentiles",
        "drift": "development robust-distance percentile"
      },
      "confidence_missing_components": [],
      "confidence_components_used": [
        "interval",
        "coverage",
        "disagreement",
        "seed",
        "drift"
      ],
      "gate_weights_source": "online_posterior",
      "empirical_coverage": 1.0
    },
    {
      "horizon": 60,
      "probability_positive": 0.6024760603904724,
      "return_quantiles": [
        -16.570533752441406,
        -4.367717266082764,
        0.9862982630729675,
        7.775532245635986,
        20.0263614654541
      ],
      "raw_interval": [
        -16.570533752441406,
        20.0263614654541
      ],
      "calibrated_interval": [
        -17.831484695053142,
        21.287312408065837
      ],
      "projected_index_quantiles": [
        1552.3476190447807,
        1850.279562292099,
        2238.34634642601
      ],
      "mdd_quantiles": [
        -15.785494804382324,
        -7.97785758972168,
        -3.296220064163208
      ],
      "volatility": 17.25768280029297,
      "expert_weights": [
        0.22639618813991547,
        0.20115821063518524,
        0.2778639495372772,
        0.29458168148994446
      ],
      "expert_disagreement": 0.8162674307823181,
      "seed_dispersion_return": 1.985343098640442,
      "seed_dispersion_direction": 0.035978998988866806,
      "seed_dispersion_mdd": 0.3720349073410034,
      "seed_dispersion_volatility": 0.7146995067596436,
      "confidence_score": 72.35378426333345,
      "confidence_label": "Cao",
      "confidence_components": {
        "interval": 0.5367913148371531,
        "coverage": 0.005428226779252143,
        "disagreement": 0.2135102533172497,
        "seed": 0.2762364294330519,
        "drift": 0.20134401654174205
      },
      "confidence_component_sources": {
        "interval": "calibration interval-width percentile",
        "coverage": "calibration coverage",
        "disagreement": "calibration auxiliary disagreement percentile",
        "seed": "calibration seed-dispersion percentiles",
        "drift": "development robust-distance percentile"
      },
      "confidence_missing_components": [],
      "confidence_components_used": [
        "interval",
        "coverage",
        "disagreement",
        "seed",
        "drift"
      ],
      "gate_weights_source": "online_posterior",
      "empirical_coverage": null
    }
  ]
}
```
