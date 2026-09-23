"""Quant Portfolio: đo một danh mục cổ phiếu Việt Nam đã nhập.

POST chứ không GET, kể cả khi không có gì được ghi xuống: danh mục là dữ liệu
vị thế của người dùng. Để nó ngoài URL là để nó ngoài log truy cập, lịch sử
trình duyệt và header referrer. Không có gì được lưu: yêu cầu được phân tích
rồi bỏ đi.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.data import market_vn
from backend.portfolio import analytics

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class Holding(BaseModel):
    """Một vị thế. ``quantity`` là số cổ phiếu, ``cost_basis`` là giá vốn mỗi cổ."""

    symbol: str = Field(min_length=1, max_length=20)
    quantity: float = Field(gt=0)
    # Không bắt buộc: người phân tích một rổ giả định thì không có giá vốn, và
    # đòi hỏi nó sẽ đẩy họ tới việc bịa một con số, con số đó rồi hiện ra thành
    # lãi/lỗ. Để trống thì các cột lãi/lỗ báo "không có" thay vì báo sai.
    cost_basis: float | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=analytics.MAX_HOLDINGS)
    cash: float = Field(default=0.0, ge=0)
    # 21 / 63 / 126 / 252 phiên — số phiên giao dịch tương ứng 1, 3, 6 tháng và
    # 1 năm, là bốn lựa chọn trên form.
    horizon_days: int = Field(default=63, ge=21, le=252)
    # Cửa sổ đo rủi ro đã xảy ra. Mặc định một năm giao dịch; cửa sổ ngắn hơn
    # phản ứng nhanh hơn nhưng ước lượng tương quan từ ít quan sát hơn.
    lookback_days: int = Field(default=252, ge=60, le=1000)

    @model_validator(mode="after")
    def _unique(self) -> "PortfolioRequest":
        seen = [h.symbol for h in self.holdings]
        if len(seen) != len(set(seen)):
            raise ValueError("Mỗi mã chỉ được xuất hiện một lần.")
        return self


@router.post("/analyze")
def analyze(request: PortfolioRequest) -> dict:
    """Phân tích danh mục. Sync `def` nên pandas/psycopg chạy ở threadpool."""
    if not market_vn.configured():
        raise HTTPException(
            503,
            "Chưa cấu hình MARKET_DSN, nên không đọc được dữ liệu chứng khoán "
            "Việt Nam. Danh mục cần dữ liệu này.",
        )

    holdings = [h.model_dump() for h in request.holdings]
    try:
        return analytics.analyse(
            holdings,
            request.cash,
            request.lookback_days,
            request.horizon_days,
            market_vn.daily_closes,
        )
    except analytics.PortfolioError as exc:
        # Danh mục không đo được là một tính chất của yêu cầu, nên 422 kèm lý
        # do, không phải 500.
        raise HTTPException(422, str(exc)) from exc
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("portfolio analysis failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
