from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MugLevel = Literal["full", "half", "splash"]
NamedVoice = Literal["gemini", "clone"]
SettleBand = Literal["lead", "on_pace", "midfield", "back", "unknown"]
ChatRole = Literal["user", "assistant"]
MugStatus = Literal["pending", "win", "lose", "no_run"]


class Mug(BaseModel):
    race_id: str
    meeting: str
    race_number: int
    horse_name: str
    tab_number: int
    mug_level: MugLevel
    voices_agree: int = Field(ge=2, le=4)
    named_voices_agree: list[NamedVoice]
    other_voices_agree: int = Field(ge=0, le=2)
    model_price: float | None = None
    market_price: float | None = None


class TodayMugsResponse(BaseModel):
    date: str
    as_of: str
    voices_total: int = 4
    mugs: list[Mug]


class RaceRunner(BaseModel):
    tab_number: int
    horse_name: str
    mug_level: MugLevel | None = None
    voices_agree: int = Field(ge=0, le=4)
    named_voices_agree: list[NamedVoice]
    other_voices_agree: int = Field(ge=0, le=2)
    model_price: float | None = None
    market_price: float | None = None
    career_starts: int | None = None
    career_wins: int | None = None
    win_pct: float | None = None
    last5_wins: int | None = None
    last5_places: int | None = None


class RaceDetail(BaseModel):
    race_id: str
    meeting: str
    race_number: int
    runner_count: int
    mug_count: int
    runners: list[RaceRunner]


class RaceSummary(BaseModel):
    race_id: str
    race_number: int
    runner_count: int
    mug_count: int
    top_mug_level: MugLevel | None = None


class MeetingSummary(BaseModel):
    meeting: str
    meeting_id: int | None = None
    races: list[RaceSummary]


class RacesIndexResponse(BaseModel):
    date: str
    as_of: str
    meetings: list[MeetingSummary]


class SpeedmapRunner(BaseModel):
    tab_number: int
    horse_name: str
    settle: int | None = None
    band: SettleBand
    barrier: int | None = None
    # PF rated run-style 1-6 (1=Leader, 6=Backmarker), 0 = no data.
    # Used by clients to position the runner on a track lane visual.
    rated_run_style: int = 0


class RaceSpeedmap(BaseModel):
    race_id: str
    meeting: str
    race_number: int
    runners: list[SpeedmapRunner]


class HorseStart(BaseModel):
    race_date: str | None = None
    track: str | None = None
    state: str | None = None
    distance: int | None = None
    race_class: str | None = None
    track_condition: str | None = None
    position: int | None = None
    field_size: int | None = None
    margin: float | None = None
    barrier: int | None = None
    weight: float | None = None
    handicap_rating: int | None = None
    jockey: str | None = None
    odds: float | None = None
    last_600m: float | None = None


class StatBreakdown(BaseModel):
    starts: int = 0
    wins: int = 0


class PersonStats(BaseModel):
    name: str
    this_track: StatBreakdown
    this_distance: StatBreakdown
    last_30_days: StatBreakdown


class TrackStat(BaseModel):
    track: str
    distance: int | None = None
    runs: int = 0
    wins: int = 0
    places: int = 0


class ConditionStat(BaseModel):
    condition: str
    runs: int = 0
    wins: int = 0
    places: int = 0


class DistanceStat(BaseModel):
    category: str
    runs: int = 0
    wins: int = 0
    places: int = 0


class HorseInfo(BaseModel):
    horse_code: str
    name: str
    sex: str | None = None
    colour: str | None = None
    dob: str | None = None
    country: str | None = None
    sire_name: str | None = None
    dam_name: str | None = None
    sire_of_dam: str | None = None
    trainer_name: str | None = None
    owner: str | None = None


class CareerStats(BaseModel):
    starts: int = 0
    wins: int = 0
    seconds: int = 0
    thirds: int = 0
    prizemoney: float = 0.0
    best_rating: int | None = None


class SaleHistoryEntry(BaseModel):
    sale_code: str
    sale_house: str | None = None
    sale_name: str | None = None
    sale_year: int | None = None
    sale_type: str | None = None
    lot_number: str | None = None
    price: float | None = None
    sale_status: str | None = None
    buyer: str | None = None
    vendor: str | None = None
    match_method: str | None = None
    match_confidence: float | None = None


class BiomechScore(BaseModel):
    sale_code: str | None = None
    lot_number: str | None = None
    # TOP / MID / BOT — or null when unscored
    tier: str | None = None
    # Net: n_out - n_under across the 12 features (-12 to +12)
    net: int | None = None
    n_out: int | None = None
    n_under: int | None = None
    n_neutral: int | None = None
    # Extraction quality
    n_trusted_sections: int | None = None
    total_trusted_seconds: float | None = None
    scorecard_version: str | None = None
    scored_at: str | None = None


class BiomechSireContext(BaseModel):
    """Sire-cohort context for placing one horse's biomech in perspective."""
    n_scored: int
    median_net: float | None = None
    pct_top: float | None = None
    pct_bot: float | None = None


class HorseSearchResult(BaseModel):
    horse_code: str
    name: str
    sire_name: str | None = None
    dam_name: str | None = None
    sex: str | None = None
    colour: str | None = None
    trainer_name: str | None = None
    career_starts: int | None = None
    career_wins: int | None = None
    career_prizemoney: float | None = None


class HorseDeepDive(BaseModel):
    horse: HorseInfo
    career: CareerStats
    form: list[HorseStart] = []
    track_stats: list[TrackStat] = []
    condition_stats: list[ConditionStat] = []
    distance_stats: list[DistanceStat] = []
    jockey_stats: PersonStats | None = None
    trainer_stats: PersonStats | None = None
    sale_history: list[SaleHistoryEntry] = []
    biomech: BiomechScore | None = None
    biomech_sire_context: BiomechSireContext | None = None


# ---------------------------------------------------------------------------
# Breeding analytics — Research tab (Sharp tier)
# ---------------------------------------------------------------------------
# Pass-through shapes for racing-db /api/breeding/*. Models kept thin —
# nm_v1 doesn't reshape, it just stamps a typed contract over the proxy.


class SireLeaderboardRow(BaseModel):
    name: str
    runners: int
    winners: int
    starts: int
    wins: int
    places: int
    winners_to_runners: float
    win_pct: float
    place_pct: float
    prizemoney: float
    prize_per_runner: float
    prize_per_start: float
    avg_rating: float
    peak_rating: int | None = None
    stakes_runners: int
    stakes_winners: int
    stakes_placegetters: int


class DistanceBandStat(BaseModel):
    runs: int
    wins: int
    pct: float


class DistanceDNARow(BaseModel):
    name: str
    total_runs: int
    total_wins: int
    sprint: DistanceBandStat
    mile: DistanceBandStat
    middle: DistanceBandStat
    staying: DistanceBandStat


class NickRow(BaseModel):
    sire: str
    broodmare_sire: str
    runners: int
    winners: int
    starts: int
    wins: int
    winners_to_runners: float
    win_pct: float
    prizemoney: float
    avg_rating: float | None = None
    peak_rating: int | None = None


class SireSectionalRow(BaseModel):
    name: str
    runs: int
    avg_l600: float | None = None
    avg_l200: float | None = None
    avg_l600_wins: float | None = None
    avg_l200_wins: float | None = None
    avg_pos_800m: float | None = None
    avg_pos_400m: float | None = None
    avg_position_gain: float | None = None
    wins: int


class ClassCeilingRow(BaseModel):
    name: str
    runners: int
    avg_peak_rating: float | None = None
    top_rating: int | None = None
    g1_runners: int
    g1_winners: int
    g2_runners: int
    g2_winners: int
    g3_runners: int
    g3_winners: int
    listed_runners: int
    listed_winners: int
    pct_stakes_runners: float
    pct_stakes_winners: float


# ---------------------------------------------------------------------------
# Sales catalogues + parade biomech browser (Research → Sales, Sharp tier)
# ---------------------------------------------------------------------------


class SaleSummary(BaseModel):
    """One row in /v1/sales — catalogue-level rollup."""
    sale_code: str
    sale_house: str | None = None
    sale_name: str | None = None
    sale_type: str | None = None
    sale_year: int | None = None
    location: str | None = None
    total_lots: int | None = None
    total_sold: int | None = None
    total_passed_in: int | None = None
    total_withdrawn: int | None = None
    median_price: float | None = None
    mean_price: float | None = None
    total_turnover: float | None = None


class SaleDetail(SaleSummary):
    """`/v1/sale/{code}` adds the metadata fields the index leaves out."""
    house_code: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gcs_folder: str | None = None
    scraped_at: str | None = None


class RaceIQ(BaseModel):
    """Class+distance winning-rating benchmark from mv_iq_winning_runs.

    `typical_low`/`typical_high` is the p25..p75 of winning ratings in the
    same class+distance bucket. `avg_win_rating` is the mean. `n` is the
    historical sample size — small n means a noisy benchmark.
    """
    avg_win_rating: float | None = None
    win_low: int | None = None
    win_high: int | None = None
    typical_low: float | None = None
    typical_high: float | None = None
    n: int


class UpcomingRace(BaseModel):
    """One row of /v1/iq/upcoming — a forward-looking race card entry
    overlaid with winning-rating intelligence.

    `competitiveness` is non-null only when the caller passed `?rating=N`,
    in which case it's one of STRONG | POSSIBLE | OVERQUALIFIED | UNLIKELY.
    """
    date: str
    race_time: str | None = None
    race_no: int
    track: str
    state: str | None = None
    race_class: str | None = None
    type: str | None = None
    condition: str | None = None
    sex: str | None = None
    age: str | None = None
    distance_m: int | None = None
    band: str | None = None
    prize: int | float | None = None
    bonus: bool = False
    description: str | None = None
    url: str | None = None
    iq: RaceIQ | None = None
    competitiveness: str | None = None


class UpcomingRacesResponse(BaseModel):
    from_: str = Field(alias="from")
    to: str
    count: int
    races: list[UpcomingRace]

    model_config = ConfigDict(populate_by_name=True)


class SaleLot(BaseModel):
    """One lot in /v1/sale/{code}/lots, with biomech tier joined in.

    `biomech_tier` is the Sharp-tier hook: TOP standouts, MID neutral,
    BOT under-built. `horse_code` is non-null only when the lot matched
    to a racing horse (so iOS can deep-link to the full profile).
    """
    lot_number: str | None = None
    sire_name: str | None = None
    dam_name: str | None = None
    sex: str | None = None
    colour: str | None = None
    dob_year: int | None = None
    vendor: str | None = None
    buyer: str | None = None
    buyer_location: str | None = None
    price: float | None = None
    sale_status: str | None = None
    horse_id: int | None = None
    horse_code: str | None = None
    horse_name: str | None = None
    match_method: str | None = None
    match_confidence: float | None = None
    biomech_tier: str | None = None
    biomech_net: int | None = None


class PastRun(BaseModel):
    """One past-start sectional entry for a runner. Times in seconds; class
    deviations are signed (negative = above class par / sharper)."""
    date: str | None = None
    track: str | None = None
    distance: int | None = None
    condition: str | None = None
    last_600m: float | None = None
    last_200m: float | None = None
    last_600_class: float | None = None


class RunnerSectional(BaseModel):
    tab_number: int
    horse_name: str
    # Most-recent-only fields (kept for the Race Detail view):
    last_run_date: str | None = None
    last_run_track: str | None = None
    last_run_distance: int | None = None
    last_run_condition: str | None = None
    last_600m: float | None = None
    finish_position: int | None = None
    # Full history + aggregates (Tab 5 Sectionals):
    runs: list[PastRun] = []
    avg_last_600m: float | None = None
    avg_last_200m: float | None = None
    avg_last_600_class: float | None = None


class RaceSectionals(BaseModel):
    race_id: str
    meeting: str
    race_number: int
    runners: list[RunnerSectional]
    # Race-level metadata (added for Sectionals tab; optional / backward-compat):
    track_condition: str | None = None
    race_class: str | None = None
    distance: int | None = None
    race_name: str | None = None


class SectionalRace(BaseModel):
    """One race in the Sectionals tab index — what `/v1/sectionals/races`
    returns under each meeting."""
    race_id: str
    meeting_id: int
    race_number: int
    description: str | None = None
    distance: int | None = None
    race_time: str | None = None


class SectionalMeeting(BaseModel):
    meeting_id: int
    track: str
    state: str | None = None
    date: str
    races: list[SectionalRace]


class SectionalRacesResponse(BaseModel):
    date: str
    meetings: list[SectionalMeeting]


class SystemROI(BaseModel):
    """One system's rolled-up stats over the requested window. Percentages are
    NORMAL percentages (24.88 not 0.2488) — converted from TRS's fractions
    in the gateway service.
    """
    key: str                       # internal id, e.g. "ai_best"
    label: str                     # public display, e.g. "AI Best"
    tips: int = 0
    wins: int = 0
    places: int = 0
    strike_pct: float = 0.0
    place_pct: float = 0.0
    roi_pct: float = 0.0
    profit: float = 0.0
    stake_per_tip: float = 10.0
    sample: int = 0                # alias for `tips` — UI convention
    confidence: str = "anecdote"   # "anecdote" | "moderate" | "ok"


class SystemROIPlaceholder(BaseModel):
    """A system whose rollup isn't available yet (no JSON source). Surfaces in
    the UI as a 'Coming when backend rollup lands' card. Honest by design."""
    key: str
    label: str
    note: str


class SystemsROIResponse(BaseModel):
    date_from: str
    date_to: str
    stake_per_tip: float = 10.0
    systems: list[SystemROI]
    pending: list[SystemROIPlaceholder]


class AskMessage(BaseModel):
    role: ChatRole
    text: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[AskMessage] = []


class AskResponse(BaseModel):
    answer: str


class BuildRoi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    n_settled: int = 0
    n_unsettled: int = 0
    wins: int = 0
    places: int = 0
    strike_pct: float = 0.0
    place_pct: float = 0.0
    roi_pct: float = 0.0
    avg_winning_sp: float | None = None
    confidence: str | None = None


class BuildRequest(BaseModel):
    query: str = Field(min_length=1)


class BuildResponse(BaseModel):
    answer: str
    mode: str
    n: int = 0
    roi: BuildRoi | None = None
    error: str | None = None


class MugPick(BaseModel):
    """One pick from /api/curated. Lifted with race start time from RA
    Crawler. `role` tells you whether this pick was the BoD primary
    (L4) or a fallback (L2/L1/L3) — important since L4 is the only
    +ROI lane on the executable feed.

    `is_star_tier` is True for L4_class picks where Gemini also rates
    the runner AI_BEST. On the 9-week audit (Apr 23 → Jun 26) the ★
    intersection ran +34.7% ROI on n=222 — the only meaningfully
    standout signal in the lane system.
    """
    model_config = ConfigDict(extra="ignore")
    horse: str
    meeting: str | None = None
    race_number: int | None = None
    tab_number: int | None = None
    model_price: float | None = None        # Clone-derived fair price
    market_price: float | None = None       # tab live
    role: str = "primary"                   # primary | fallback | fallback2 | fallback3
    source_lane: str | None = None          # "L4_class" | "L2_mid_favs" | ...
    is_star_tier: bool = False              # L4 ∩ Gemini AI_BEST
    win_pct: float | None = None
    career_starts: int | None = None
    race_time: str | None = None
    status: MugStatus = "pending"


class LaneAudit(BaseModel):
    """Static 9-week backtest stats (Apr 23 → Jun 26) hard-coded into the
    gateway. The /api/curated payload doesn't carry rolling SR/ROI per
    lane — these numbers come from the stablfy-social audit that locked
    in the lane system. Refreshed manually when the audit re-runs.
    """
    model_config = ConfigDict(extra="ignore")
    n: int                                   # sample size
    strike_pct: float
    roi_pct: float


class Lane(BaseModel):
    """One of the four production lanes (L4 / L2 / L1 / L3).

    Research-only lanes (V / P / S) are deliberately not surfaced here —
    they don't validate on the executable feed.
    """
    model_config = ConfigDict(extra="ignore")
    key: str                                  # "L4_class" | "L2_mid_favs" | ...
    name: str                                 # display label
    subtitle: str
    is_primary: bool = False                  # True only for L4_class
    audit: LaneAudit | None = None            # hard-coded backtest stats
    picks: list[MugPick]


class MugsResponse(BaseModel):
    date: str | None = None
    best_of_day: list[MugPick] = []           # top-3 picks (sourced from primary first, then fallbacks)
    lanes: list[Lane] = []                    # full L4/L2/L1/L3 plays
    is_stakes_day: bool = False
    metro_pick_count: int = 0


class AgreementRunner(BaseModel):
    """A runner where at least 2 of the 3 AI voices (Clone + Gemini + SkyNet)
    are picking it as #1. SkyNet is anonymised as "other AI model" — only
    Gemini and Clone are named publicly.
    """
    race_id: str
    meeting: str
    race_number: int
    race_time: str | None = None
    tab_number: int
    horse: str
    agreement: int = Field(ge=2, le=3)
    named_voices: list[NamedVoice]
    other_voices: int = Field(ge=0, le=1)
    model_price: float | None = None
    market_price: float | None = None


class AgreementsResponse(BaseModel):
    date: str | None = None
    runners: list[AgreementRunner]


class RankRunner(BaseModel):
    """Tab 3 — runner ranked by Clone. `agreement` flag indicates overlap
    with the 3-voice AI Agreement view (0=Clone-only, 2=2/3, 3=all-3)."""
    clone_rank: int = Field(ge=1, le=3)
    tab_number: int
    horse: str
    model_price: float | None = None
    market_price: float | None = None
    agreement: int = Field(ge=0, le=3)


class RankRace(BaseModel):
    race_id: str
    race_number: int
    race_time: str | None = None
    runners: list[RankRunner]


class RankMeeting(BaseModel):
    meeting: str
    races: list[RankRace]


class RankResponse(BaseModel):
    date: str | None = None
    meetings: list[RankMeeting]
