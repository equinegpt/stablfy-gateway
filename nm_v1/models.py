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


class HorseDeepDive(BaseModel):
    horse: HorseInfo
    career: CareerStats
    form: list[HorseStart] = []
    track_stats: list[TrackStat] = []
    condition_stats: list[ConditionStat] = []
    distance_stats: list[DistanceStat] = []
    jockey_stats: PersonStats | None = None
    trainer_stats: PersonStats | None = None


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
    """One BoD pick, lifted from /api/curated and enriched with race start
    time from RA Crawler. Status is PENDING for today's picks — settled
    rollups live on the lane summary, not per pick.
    """
    model_config = ConfigDict(extra="ignore")
    horse: str
    meeting: str | None = None
    race_number: int | None = None
    tab_number: int | None = None
    model_price: float | None = None
    market_price: float | None = None
    role: str = "primary"
    race_time: str | None = None
    status: MugStatus = "pending"


class BodLaneSummary(BaseModel):
    """Rolling-window summary for a BoD lane, scraped from /best-of-day HTML."""
    model_config = ConfigDict(extra="ignore")
    days: int = 30
    picks: int = 0
    settled: int = 0
    wins: int = 0
    places: int = 0
    no_run: int = 0
    strike_pct: float | None = None
    place_pct: float | None = None
    roi_pct: float | None = None
    profit: float | None = None
    avg_winning_sp: float | None = None


class BodLane(BaseModel):
    key: str             # "v1" | "v2"
    name: str            # public label
    subtitle: str
    summary: BodLaneSummary
    picks: list[MugPick]


class MugsResponse(BaseModel):
    date: str | None = None
    lanes: list[BodLane]


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
