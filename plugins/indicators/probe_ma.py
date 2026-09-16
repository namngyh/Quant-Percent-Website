INDICATOR = {
    "name": "Probe MA",
    "type": "overlay",
    "params": {"length": {"type": "int", "default": 10}},
    "outputs": [{"key": "value", "label": "MA"}],
}


def calculate(df, params):
    return {"value": df["close"].rolling(int(params["length"])).mean()}
