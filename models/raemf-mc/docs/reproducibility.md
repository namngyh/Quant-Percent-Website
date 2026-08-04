# Khả năng tái lập

Mỗi run lưu Python version, OS, random seed, Git SHA, config snapshot, checksum dữ liệu, thời gian bắt đầu, kết thúc, tổng runtime và mode. Dependency trực tiếp được khóa trong `requirements-lock.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pytest -q
python -m raemf_mc.cli run --data data.csv --config configs/laptop.yaml
```

Run mới nằm trong `outputs/runs/<timestamp>_<git-sha>/`; `outputs/latest/` là bản sao của run hoàn tất gần nhất.
