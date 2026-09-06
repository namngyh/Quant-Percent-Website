"""SQLAlchemy models.

Three ownership zones share one database (spec §21):

* ``public``  — ingestion pipeline (ticks, bars_1m, bars_1d, gap_log).
  Not mapped here: this service reads it only through the vetted ``api``
  views, and its role has no rights on those tables.
* ``quant``   — written by the model pipeline, read-only for the API.
* ``web``     — owned by this service.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import QUANT_SCHEMA, WEB_SCHEMA, Base, utcnow_column


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


# ===========================================================================
# web — accounts
# ===========================================================================


class User(Base):
    """An account. ``role`` is the switch the admin endpoints gate on; the
    frontend only reads it to decide which message to show."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'author', 'admin')", name="role_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')", name="status_valid"
        ),
        # NULL means never asked. Approval is read from role = 'author', not
        # duplicated here, so the two can never disagree.
        CheckConstraint(
            "author_request_status IN ('pending', 'rejected')",
            name="author_request_status_valid",
        ),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Optional, and the same width as contacts.phone so the two agree on what
    # a phone number is. Nobody needs one to hold an account.
    phone: Mapped[str | None] = mapped_column(String(40))
    locale: Mapped[str] = mapped_column(String(5), default="vi", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), default="user", server_default="user", nullable=False
    )
    author_request_status: Mapped[str | None] = mapped_column(String(20))
    author_request_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = utcnow_column()
    updated_at: Mapped[datetime] = utcnow_column()

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """Rotating refresh tokens.

    Only the hash is stored. Tokens share a ``family_id`` across rotations;
    replaying a already-rotated token revokes the whole family.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),
        Index("ix_refresh_tokens_family", "family_id"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = utcnow_column()

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class OneTimeToken(Base):
    """Password reset and email verification tokens — hashed, single use."""

    __tablename__ = "one_time_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('password_reset', 'email_verification')",
            name="purpose_valid",
        ),
        Index("ix_one_time_tokens_user_purpose", "user_id", "purpose"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = utcnow_column()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_created", "created_at"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(120))
    ip: Mapped[str | None] = mapped_column(INET)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = utcnow_column()


# ===========================================================================
# web — inbound messages
# ===========================================================================


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_created", "created_at"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    organization: Mapped[str | None] = mapped_column(String(200))
    inquiry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False
    )
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = utcnow_column()


class InvestorInterest(Base):
    """Registered interest — explicitly not an investment commitment."""

    __tablename__ = "investor_interests"
    __table_args__ = {"schema": WEB_SCHEMA}

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(5), nullable=False)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = utcnow_column()


# ===========================================================================
# web — published catalogue (moved out of the frontend config files)
# ===========================================================================


class Model(Base):
    """Model registry. ``access`` is the switch that gates members-only
    output server-side — the frontend blur is only cosmetic."""

    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint("access IN ('public', 'members')", name="access_valid"),
        CheckConstraint(
            "visibility IN ('public', 'hidden')", name="visibility_valid"
        ),
        CheckConstraint(
            "status IN ('active', 'paper_trading', 'experimental', 'archived')",
            name="status_valid",
        ),
        {"schema": WEB_SCHEMA},
    )

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    markets: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), default="public", nullable=False
    )
    access: Mapped[str] = mapped_column(
        String(20), default="public", nullable=False
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    horizons: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    show_forecast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_performance: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Bilingual copy: {"vi": ..., "en": ...}
    tagline: Mapped[dict] = mapped_column(JSONB, nullable=False)
    key_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict] = mapped_column(JSONB, nullable=False)
    architecture: Mapped[list | None] = mapped_column(JSONB)
    # Presentation-ready, audited research evidence. Keeping this in the
    # catalogue row makes the database the runtime source of truth while
    # allowing the frontend config to remain a development/seed fixture.
    sparkline: Mapped[list | None] = mapped_column(JSONB)
    sparkline_label: Mapped[dict | None] = mapped_column(JSONB)
    research_profile: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = utcnow_column()


class Strategy(Base):
    """One performance report = one evaluation run of one model (§10.1)."""

    __tablename__ = "strategies"
    __table_args__ = (
        CheckConstraint(
            "result_type IN ('backtest', 'out_of_sample', 'walk_forward',"
            " 'paper_trading', 'live')",
            name="result_type_valid",
        ),
        Index("ix_strategies_system", "system_slug"),
        {"schema": WEB_SCHEMA},
    )

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    system_slug: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_type: Mapped[str] = mapped_column(String(20), nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    benchmark: Mapped[dict] = mapped_column(JSONB, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fees_note: Mapped[dict] = mapped_column(JSONB, nullable=False)
    slippage_note: Mapped[dict] = mapped_column(JSONB, nullable=False)
    split_note: Mapped[dict] = mapped_column(JSONB, nullable=False)
    seed_note: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    code_version: Mapped[str] = mapped_column(String(40), nullable=False)
    caveats: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = utcnow_column()


class ReportMetric(Base):
    """Metric values. A metric that the run did not produce is simply
    absent — never zero-filled (spec §10.4)."""

    __tablename__ = "report_metrics"
    __table_args__ = (
        UniqueConstraint("strategy_slug", "metric", name="uq_report_metric"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    ci95_lo: Mapped[float | None] = mapped_column(Float)
    ci95_hi: Mapped[float | None] = mapped_column(Float)
    in_confidence_table: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class ReportEquityPoint(Base):
    """Per-trade equity. The runs record profit per closed trade with no
    timestamp, so the series is indexed by trade number."""

    __tablename__ = "report_equity_points"
    __table_args__ = (
        UniqueConstraint("strategy_slug", "trade", name="uq_report_equity_trade"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        nullable=False,
    )
    trade: Mapped[int] = mapped_column(Integer, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    equity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)


class ReportBucket(Base):
    """Histogram buckets: per-trade profit distribution and the seed
    distribution of the multi-seed run."""

    __tablename__ = "report_buckets"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('return_distribution', 'seed_distribution')",
            name="bucket_kind_valid",
        ),
        UniqueConstraint(
            "strategy_slug", "kind", "bucket", name="uq_report_bucket"
        ),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    bucket: Mapped[float] = mapped_column(Float, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class ReportFold(Base):
    __tablename__ = "report_folds"
    __table_args__ = (
        UniqueConstraint("strategy_slug", "fold", name="uq_report_fold"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        nullable=False,
    )
    fold: Mapped[int] = mapped_column(Integer, nullable=False)
    train_from: Mapped[int] = mapped_column(Integer, nullable=False)
    train_to: Mapped[int] = mapped_column(Integer, nullable=False)
    test_year: Mapped[int] = mapped_column(Integer, nullable=False)
    net_points: Mapped[float] = mapped_column(Float, nullable=False)
    net_pct: Mapped[float] = mapped_column(Float, nullable=False)
    trades: Mapped[int] = mapped_column(Integer, nullable=False)
    long_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    short_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    payoff: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_points: Mapped[float] = mapped_column(Float, nullable=False)
    partial_year: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ReportExitReason(Base):
    __tablename__ = "report_exit_reasons"
    __table_args__ = (
        UniqueConstraint("strategy_slug", "reason", name="uq_report_exit_reason"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    share: Mapped[float] = mapped_column(Float, nullable=False)


class ReportSimulation(Base):
    """Seed dispersion, bootstrap and cost sensitivity of one run."""

    __tablename__ = "report_simulations"
    __table_args__ = {"schema": WEB_SCHEMA}

    strategy_slug: Mapped[str] = mapped_column(
        ForeignKey(f"{WEB_SCHEMA}.strategies.slug", ondelete="CASCADE"),
        primary_key=True,
    )
    n_seeds: Mapped[int] = mapped_column(Integer, nullable=False)
    pct_positive: Mapped[float] = mapped_column(Float, nullable=False)
    long_bias_seeds: Mapped[int] = mapped_column(Integer, nullable=False)
    short_bias_seeds: Mapped[int] = mapped_column(Integer, nullable=False)
    profit: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bootstrap: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cost_stress: Mapped[dict] = mapped_column(JSONB, nullable=False)
    median_seed: Mapped[int | None] = mapped_column(Integer)


# ===========================================================================
# web — reference data the ingestion pipeline does not own
# ===========================================================================


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = {"schema": WEB_SCHEMA}

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    # Name this symbol carries in the ingestion feed. Usually identical to
    # `symbol`, but the website publishes the VN30 index as "VN30" while
    # DataPro delivers it as "VN30INDEX". Kept unique so the api views can
    # join on it without multiplying rows.
    feed_symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # index|future|stock
    exchange: Mapped[str] = mapped_column(String(10), default="HOSE", nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="VND", nullable=False)
    point_value: Mapped[float | None] = mapped_column(Numeric)
    sector: Mapped[str | None] = mapped_column(String(80))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class IndexConstituent(Base):
    """VN30 membership over time — HOSE rebalances every January and July,
    so membership needs validity dates rather than a static env list."""

    __tablename__ = "index_constituents"
    __table_args__ = (
        Index("ix_index_constituents_lookup", "index_symbol", "valid_from"),
        {"schema": WEB_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    index_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    member_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class TradingCalendar(Base):
    """Session calendar so "latest trading day" is correct on holidays."""

    __tablename__ = "trading_calendar"
    __table_args__ = {"schema": WEB_SCHEMA}

    trading_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    session_note: Mapped[str | None] = mapped_column(String(120))


# ===========================================================================
# quant — written by the model pipeline, read-only here
# ===========================================================================


class ModelForecast(Base):
    """One published forecast record (spec §18).

    Replaces the thin ``predictions`` EAV table for anything the website
    shows: a single row holds the whole record, so interval, regime and
    version can never drift apart.
    """

    __tablename__ = "model_forecasts"
    __table_args__ = (
        Index("ix_model_forecasts_lookup", "model_id", "symbol", "data_as_of"),
        {"schema": QUANT_SCHEMA},
    )

    model_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    horizon: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    horizon_unit: Mapped[str] = mapped_column(
        String(20), default="trading_days", nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    forecast_value: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_return: Mapped[float] = mapped_column(Float, nullable=False)
    probability_up: Mapped[float] = mapped_column(Float, nullable=False)
    probability_down: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    interval_level: Mapped[float] = mapped_column(Float, nullable=False)
    interval_lower: Mapped[float] = mapped_column(Float, nullable=False)
    interval_upper: Mapped[float] = mapped_column(Float, nullable=False)
    # Not every model produces a regime call or a risk grade. MSDP forecasts a
    # return distribution and nothing else; requiring these would force the
    # loader to invent a regime, which reads on the page as a real call. A
    # model that does produce them fills them in.
    regime: Mapped[str | None] = mapped_column(String(30))
    regime_probability: Mapped[float | None] = mapped_column(Float)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_state: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Realised value, filled in later so forecast error and interval
    # coverage can be computed honestly
    actual_value: Mapped[float | None] = mapped_column(Float)
    actual_filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class MarketState(Base):
    __tablename__ = "market_state"
    __table_args__ = (
        Index("ix_market_state_ts", "ts"),
        {"schema": QUANT_SCHEMA},
    )

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    scope: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="market"
    )
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    regime_probability: Mapped[float] = mapped_column(Float, nullable=False)
    probability_up: Mapped[float] = mapped_column(Float, nullable=False)
    probability_down: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    risk_state: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    model_consensus: Mapped[float] = mapped_column(Float, nullable=False)
    public_signal: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RiskMetric(Base):
    __tablename__ = "risk_metrics"
    __table_args__ = {"schema": QUANT_SCHEMA}

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    scope: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="market"
    )
    current_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_drawdown_60d: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    var_95: Mapped[float | None] = mapped_column(Float)
    es_95: Mapped[float | None] = mapped_column(Float)
    downside_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_state: Mapped[str] = mapped_column(String(20), nullable=False)
    mc_paths: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RiskDistributionBucket(Base):
    __tablename__ = "risk_mc_distribution"
    __table_args__ = {"schema": QUANT_SCHEMA}

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    scope: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="market"
    )
    bucket: Mapped[float] = mapped_column(Float, primary_key=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)


class RiskScenario(Base):
    __tablename__ = "risk_scenarios"
    __table_args__ = {"schema": QUANT_SCHEMA}

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    scope: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="market"
    )
    scenario_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    impact_percent: Mapped[float] = mapped_column(Float, nullable=False)


class StockRanking(Base):
    __tablename__ = "stock_rankings"
    __table_args__ = (
        Index("ix_stock_rankings_ts_rank", "ts", "rank"),
        {"schema": QUANT_SCHEMA},
    )

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    probability_up: Mapped[float] = mapped_column(Float, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, nullable=False)
    risk_state: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ModelRun(Base):
    """Heartbeat per model, backing /api/v1/model-status."""

    __tablename__ = "model_runs"
    __table_args__ = {"schema": QUANT_SCHEMA}

    model_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    healthy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
