from msdp.splits import chronological_split
def test_purge():
    s=chronological_split(3000,60); assert s["calibration"][0]-s["development"][-1]-1==60; assert s["test"][0]-s["calibration"][-1]-1==60

