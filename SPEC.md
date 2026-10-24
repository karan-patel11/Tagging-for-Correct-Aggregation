# Tagging for Correct Aggregation: Project Spec

*Owner: Karan Patel · Version 2.2 (3-day plan; BLS and Census macro data; Claude Haiku 5.5 eval; static results page for the pitch) · October 23, 2026 · Send target: Monday, October 26, 2026, morning ET*

---

## 0. How to use this document

Save this file as `SPEC.md` in the root of your repo. Phase 0 also creates a short `CLAUDE.md` file, which Claude Code reads automatically at the start of every session.

Work **one phase per Claude Code session**, using this prompt pattern:

> Read SPEC.md sections [X, Y]. Do Phase [N] only. Don't change anything outside the files listed for this phase. When finished, run the acceptance checks and show me their output. Then stop.

After each phase:

1. Do the "you check personally" items for that phase. Don't delegate these to Claude Code.
2. Commit with the message `phase N: <what was done>`, push, and open a pull request into `main`.
3. **Merge that pull request into `main` yourself, after your checks, before starting the next session.** Each new Claude Code session starts from `main`, so unmerged work is invisible to it.
4. If you made a design choice along the way, add it to the decisions log in §15.

Use your Claude project chat for thinking and decisions, and Claude Code for building.

### 0.1 What changed in Version 2

Version 1 planned 7 days. Version 2 fits the same design into 3 days (Friday to Sunday) and sends on Monday morning. The architecture, the 5 tables, the tags, `semantics.py`, the 4 MCP tools and the 4 setups are unchanged. What changed:

- **Smaller data:** 4 companies (CMG, WING, YUM, DRI), 12 comps values, 10 Wikipedia articles.
- **Smaller evaluation:** 42 questions (7 per category, minimum 36), 504 runs.
- **Cut:** auto-tagging (Phase 16) and the one-page case study PDF. The README carries the write-up.
- **Added rules:** concept chosen per company and metric with a coverage table; uniqueness keys based on dates, never fiscal labels; one numeric answer per question (or refuse); questions dropped when a trap answer is too close to the correct one; B vs. C reported paired by question.
- **Macro data source:** CPI from the Bureau of Labor Statistics and food-service sales from the Census Bureau, downloaded by hand, instead of FRED (FRED's terms restrict this use; see §6.4).
- **Eval model:** Claude Haiku 5.5 with a hard $5 budget cap (estimated full-run cost about $1), instead of Sonnet (about $22).
- **Pitch frontend:** a static, read-only results page (§13.1) built from the recorded eval runs, used as the main screen in the Loom video. No chatbot, no backend, no live model calls.
- **Added process:** question wording drafted by hand on Friday, before `semantics.py` exists; test values collected from filings first and reused in the answer-key verification.
- **Added to the write-up:** a "Related approaches" section on semantic layers.

---

## 1. Why this project exists

**The goal:** get the next interview round for the Data Scientist – Equity Research role on Jefferies' Equity Research Data Strategy team.

**The reader:** the data scientist you interviewed with. Check the exact spelling of their name: the public Databricks post names Tamar Kellner on this team, while your notes say "Temur." They oversee data science and AI work in Global Equity Research. The team has two pillars, alternative data and AI accessibility, and works with fundamental analysts across every sector.

**The challenge they named in your interview:** making existing datasets fully AI-accessible end to end. That means not just MCP connectors, but proper column and table tagging, so models understand each metric and calculate and aggregate correctly.

**The job description lines this proves:**

- "Enhance our platform through the creation and maintenance of tools, AI agents, MCP servers, and processes that streamline, scale, and standardize…"
- "Ensuring all first- and third-party data assets are AI-accessible and meet quality, lineage, and governance standards"
- Strong Python, SQL, LLMs, and evaluation
- "Translate open-ended questions into data-driven insights," and presenting technical work clearly

**Public context** (from the March 2026 Databricks case study on Jefferies Data Intelligence): analysts ask questions in plain language, the system queries curated datasets, and analysts can't be expected to check the SQL themselves. So trust has to come from the system being correct and transparent.

**The one-sentence pitch:**

> I measured how often an AI agent gets restaurant-sector calculations wrong when it only sees raw tables, and how much structured column tagging, plus an MCP tool that enforces those tags, fixes it. Every answer links back to its source filing.

**Positioning (say this, don't overclaim):** semantic layers already solve aggregation for metrics someone has defined (Kimball's semi-additive measures, dbt MetricFlow's `non_additive_dimension`, Databricks metric views). `semantics.py` is a minimal semantic layer. This project's contribution is the measurement: how much error each layer of context and enforcement removes, and whether structured tags beat plain descriptions with the same facts.

**Your personal reason:** in the interview you said QuantEra was still at the design stage. This project is shipped, tested work on the same ideas.

---

## 2. Will it matter? An honest expected outcome

**What it can realistically do:**

- Give you a legitimate, specific reason to email them three to six days after the call.
- Show that you listened. It answers the exact problem they described, not a generic AI topic.
- Show the three things a data team checks for: finance knowledge (fiscal calendars, YTD reporting, comparable-sales definitions), engineering (a working MCP server with tests), and scientific honesty (verified answers, fair baselines, reported failures).
- Give you a concrete project to walk through in the next round, where you know every detail.
- Replace the "designed" and "planned" bullets on your resume with something built.

**What it cannot do:**

- Guarantee a next round. Headcount, timing, and other candidates are outside your control.
- Get read in full. Assume they spend about two minutes on it. The email's first paragraph, the README's first screen, and the two-minute video must carry the whole message by themselves.

**What earns credibility with this reader (someone who builds this kind of system):**

- Answer keys checked by hand against primary sources (filings, BLS, Census, earnings releases).
- A fair baseline. Setup B contains the same facts as the tags, so the comparison is honest.
- Results that include where your own system failed.
- Checking data licenses and using primary public-domain sources (BLS, Census) instead of a redistributor with restrictive terms.
- Correct finance details: fiscal-quarter mapping, YTD subtraction, why annual EPS isn't the sum of quarterly EPS, why comps don't compare across companies.
- Naming the existing approaches (semantic layers, metric views) instead of presenting the idea as new.
- Reproducible with one command. Small, clean, and tested.
- Modest language. Call it a small experiment, not a production system.

**What destroys credibility:**

- One wrong finance fact (a mislabeled fiscal quarter, a wrong number from a filing).
- An answer key generated by the same code being tested.
- Results that look too perfect, with no failures discussed.
- Calling a small difference between setups a finding when it is within noise.
- Claims about Jefferies' internal systems.
- A chatbot, a live question-answering UI over financial data, or anything that looks like a copy of their product. (A static page that replays recorded eval runs, §13.1, is fine: it shows evidence, not a product.)
- Any number on the results page that isn't read from the eval output files.
- Broken links, an exposed API key, or a messy repo.
- Numbers that contradict your resume or what you said in the interview.

**Likely outcomes:**

- **Best case:** a reply, and a next round where they ask you to walk through it.
- **Common case:** a polite acknowledgment. The project still pays off as interview material and as a resume project.
- **Worst case:** they find a sloppy error. The pre-send checklist in §15 exists to prevent this.

**Definition of done:**

- Every question in the run is hand-verified (42, or at least 36).
- All tests pass.
- The results table exists.
- The repo reproduces with one command.
- The README's first screen carries the problem, results, and video.
- The two-minute video is recorded.
- The email is sent on Monday, October 26, morning ET.

---

## 3. The problem and the research questions

**The problem: valid SQL, wrong answer.** A model can write SQL that runs without error and still return a wrong number, because the schema doesn't say how each column may be combined. Example:

> "What were Yum's total assets for 2025?"
>
> - Wrong: `SUM(total_assets)` over the 4 quarters. This counts the balance four times.
> - Right: take the balance at the last quarter-end.

Data warehousing has standard names for this (from Kimball's dimensional modeling):

- **Additive:** can be summed across both companies and time. Example: revenue, by discrete quarter.
- **Semi-additive:** can be summed across companies but not across time. Example: total assets.
- **Non-additive:** can't be summed at all. Examples: margins, comparable sales %, EPS, price indices.

**The seven traps this project tests:**

1. **Time additivity:** summing balances over time.
2. **Ratios:** averaging margins instead of dividing totals.
3. **YTD basis:** 10-Q cash flow statements report year-to-date figures, not single quarters. Q4 is almost never reported directly and must be derived as full year minus nine months.
4. **Fiscal calendar:** Darden's fiscal year ends in May, so its "Q3" is roughly December through February.
5. **Indices:** CPI levels can't be summed; use percent change or an average.
6. **Hierarchy:** brand data rolled up to the parent company, without double-counting the parent's own page.
7. **Comparability:** each company defines comparable sales differently, so cross-company comparisons need a caveat. When the data doesn't exist, the agent should say so instead of guessing.

**Research questions:**

- **RQ1:** With only the schema, how often does the agent fall into each trap? (Setup A)
- **RQ2:** Does structured tagging beat well-written prose containing the same facts? (B vs. C) This is the main finding, because it speaks directly to how their team should tag.
- **RQ3:** Does enforcing the tags in a tool beat putting them in the prompt? (C vs. D)
- **RQ4 (cut in Version 2, listed as next step):** Can an LLM propose tags for a new dataset accurately enough to save human effort? This relates to onboarding new data vendors.

There are no predicted numbers. Whatever the results show gets reported as is.

---

## 4. Scope and non-goals

**In scope:**

- 4 companies (CMG, WING, YUM, DRI), fiscal years 2024–2025 (Darden: fiscal 2025–2026)
- 5 tables and about 20 tag entries
- 4 MCP tools
- 42 questions (7 per category; minimum 36), 4 setups, 3 runs each (504 runs), one model
- A static, read-only results page for the pitch (§13.1), a README whose first screen carries the write-up, and a two-minute video

**Not in scope:**

- Any interactive product UI: no chatbot, no live querying, no login, no backend. The only frontend is the static results page in §13.1.
- Streaming (one line in "next steps")
- Deploying on Databricks
- Auto-tagging (RQ4; one line in "next steps")
- A separate case study PDF
- Any Jefferies data, or claims about their internals
- Forecasting or investment signals
- Claims that Wikipedia pageviews predict anything. They are a public stand-in for an alternative-data panel, used here only for their data semantics.

---

## 5. System architecture

```
SOURCES                         INGESTION              STORAGE                    CORE LOGIC            INTERFACES                 OUTPUTS
SEC XBRL companyfacts API  ───► src/ingest_sec.py  ─┐
Wikimedia pageviews API    ───► src/ingest_wiki.py ─┤
BLS + Census (manual)      ───► src/ingest_macro.py─┼─► src/build_db.py ─► data/warehouse.duckdb ─┐
Earnings releases (manual) ───► data/comps*.csv    ─┘                                               ├─► src/semantics.py ─┬─► src/mcp_server.py ──► Claude Code demo, Loom
                                                         tags/tags.yaml ─► src/tags.py (validate) ──┘   (the only place    └─► eval/run_eval.py ──► eval/results/*.jsonl
                                                                                                         math rules live)                             └─► eval/score.py ──► summary.json ──► report/build_report.py ──► docs/index.html (results page), README
```

**The layers and why each exists:**

1. **Raw layer (`data/raw/`).** Files exactly as downloaded, committed to git with retrieval dates, so anyone can rebuild without API keys and every number is traceable.
2. **Warehouse (`warehouse.duckdb`).** Values stored as filed, including YTD rows and parent-company rows. The traps are kept on purpose: real data looks like this, and the test is meaningless if you clean the traps away.
3. **Tags (`tags/tags.yaml`).** Machine-readable meaning for each metric: what type it is, how it may be combined, its period basis, calendar, units, and lineage.
4. **Core logic (`semantics.py`).** The only code that knows the math rules. It reads the tags, refuses invalid aggregations, derives single quarters from YTD values, rolls brands up to parents, and attaches sources to every answer.
5. **Interfaces.** The MCP server (for a human or agent in Claude Code) and the evaluation harness (for measurement) both call the same `semantics.py` functions, with the same tool descriptions. What you demo is exactly what you measured.
6. **Evaluation.** A fixed, hand-verified question set, four setups, scoring, and error analysis.

**Design principles (say these in the interview):**

- Store data as filed and interpret it in one place.
- Every number carries lineage: a filing accession number, a BLS or Census series with its download date, or a release URL.
- Agents get read-only access.
- The answer key is computed independently of `semantics.py` and checked by hand.
- Questions are drafted before the core logic exists and frozen before any evaluation run.

**Why DuckDB and not Databricks:** DuckDB is a single file with full SQL, no server, no cost, and anyone can reproduce it. §14 explains how the design maps onto Unity Catalog.

**What happens for one question in setup D:**

1. Question: "What was Darden's operating cash flow in fiscal Q3 2025?"
2. The agent calls `describe_column("fundamentals.op_cash_flow")` and learns the metric is a flow and that 10-Q values are year-to-date.
3. The agent calls `get_metric("DRI", "op_cash_flow", "FY2025Q3")`.
4. `semantics.py` finds the YTD9 and YTD6 rows, checks that the period dates line up, subtracts them, and returns the value, the derivation, and two source links.
5. The agent ends with `FINAL: {"answer": …}`. The scorer compares it with the hand-verified key and the stored trap answers.

---

## 6. Data specification

### 6.1 Companies

Confirm each fiscal year-end on the 10-K cover page before coding.

| Ticker | Company | Fiscal year-end | Brands in scope | Why included |
|---|---|---|---|---|
| CMG | Chipotle | December | Chipotle | Single brand; 50-for-1 stock split in June 2024 (EPS restatement check) |
| WING | Wingstop | December | Wingstop | Mostly franchised; its comps definition likely differs from CMG's (confirm) |
| YUM | Yum! Brands | December | KFC, Taco Bell, Pizza Hut, Habit Burger Grill | Brand hierarchy |
| DRI | Darden | May | Olive Garden, LongHorn Steakhouse | Fiscal calendar trap; brand hierarchy |

CAVA and Sweetgreen are not in the data. CAVA appears in exactly one question, as data that doesn't exist (expected behavior: refuse).

**Time window:**

- December year-end companies: fiscal 2024 and 2025 (8 quarters).
- Darden: fiscal 2025 and 2026, covering about June 2024 to May 2026. Check the FY2026 10-K cover page for whether fiscal 2026 is a 53-week year, and record the answer in the decisions log.

### 6.2 SEC fundamentals

- **Company IDs:** look up CIKs from `https://www.sec.gov/files/company_tickers.json`. Don't type them by hand.
- **Data:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit zero-padded}.json`. Save each response to `data/raw/sec/{ticker}.json`.
- **Access rules:** every request needs the header `User-Agent: Karan Patel patelkaran.tech@gmail.com`. Stay under 10 requests per second; use `time.sleep(0.2)` between calls.

**Candidate concepts, in priority order:**

| Metric | XBRL concepts |
|---|---|
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues` |
| operating_income | `OperatingIncomeLoss` |
| net_income | `NetIncomeLoss` |
| op_cash_flow | `NetCashProvidedByUsedInOperatingActivities`, `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` |
| capex | `PaymentsToAcquirePropertyPlantAndEquipment` |
| total_assets | `Assets` |
| diluted_eps | `EarningsPerShareDiluted` (unit `USD/shares`) |

**Concept choice (per company and metric):**

- For each (ticker, metric), pick the first concept in priority order that covers **every** period in the window.
- Print a coverage table: for each (ticker, metric, concept), which fiscal periods it covers.
- If no single concept covers every period, stop and show the gap. Decide manually and record the decision. Don't silently drop or mix concepts.
- Assert exactly one concept per (ticker, metric).

**Rules (each one guards against a real trap in SEC data):**

1. **Ignore the JSON's `fy` and `fp` fields.** They describe the filing, not the number. A FY2025 10-K also contains FY2024 comparison figures, all labeled 2025. Compute fiscal labels yourself from the period end date.
2. **Classify each row by how long its period is,** not by its label. Restaurant companies use 52/53-week calendars, so quarters run 84–98 days.
3. **Remove duplicates by date-based keys.** For duration facts, keep the latest-filed row for each (ticker, metric, period_start, period_end). For balance-sheet facts, keep the earliest-filed row for each (ticker, metric, period_end): balance sheets are not split-adjusted, and later filings can mis-tag comparative dates (DRI's FY2026 Q1 and Q2 10-Qs do). Print every conflict between filings. Never use fiscal labels as keys: a YTD9 row and a Q3 row both get fiscal quarter 3. Using the latest filing means post-split EPS for CMG; record this choice in the decisions log.
4. **Keep only forms 10-Q and 10-K.** Amendments are out of scope; list that under limitations.
5. **Store all period types as filed:** single quarters, YTD6, YTD9, full-year, and balance-sheet values. Don't store derived Q4 values; `semantics.py` derives them on request.

```python
def classify_basis(start, end):
    if pd.isna(start): return "instant"
    d = (end - start).days
    if 80 <= d <= 100:  return "Q"
    if 170 <= d <= 190: return "YTD6"
    if 260 <= d <= 285: return "YTD9"
    if 350 <= d <= 380: return "FY"
    return "other"   # log and inspect, never silently keep

def fiscal_labels(end, fye_month=12):
    adj = end - pd.Timedelta(days=7)          # handles year-ends falling in early January
    m = (adj.month - fye_month) % 12 or 12    # months into the fiscal year, 1..12
    fy = adj.year if adj.month <= fye_month else adj.year + 1
    return fy, (m + 2) // 3                   # fiscal year, fiscal quarter
# FYE_MONTH = {"DRI": 5}; everyone else is 12.
# YTD6 -> quarter 2, YTD9 -> quarter 3, FY -> quarter 4.
```

### 6.3 Wikipedia pageviews (the alternative-data stand-in)

- **Endpoint:** `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/20240101/20251231`. Send the header `User-Agent: tagging-aggregation/0.1 (patelkaran.tech@gmail.com)`, Wikimedia's preferred format. Wait for each request to finish before sending the next.
- **Brand articles (8):** Chipotle Mexican Grill, Wingstop, KFC, Taco Bell, Pizza Hut, Habit Burger & Grill (plus its former title, The Habit Burger Grill), Olive Garden, LongHorn Steakhouse.
- **Parent articles (2):** Yum! Brands, Darden Restaurants.
- **Verify each title in a browser first** and copy it from the URL. The API counts only that exact title; views of redirect pages are not included.
- **Labeling:** brand articles get grain `brand`, parent articles get grain `parent`. For single-brand companies, the brand article is the only row.
- **Periods:** these are calendar dates. Questions about this data use calendar quarters (CY2025Q1, and so on).

### 6.4 Macro data (primary government sources, downloaded by hand)

FRED's terms of use forbid "data mining, scraping or extraction" and use "in connection with the development or training of any software program or system or machine learning." So both series come straight from the agencies that publish them. Both are U.S. government data; BLS states that everything it publishes is in the public domain.

- **CPI, food away from home:** Bureau of Labor Statistics series `CUSR0000SEFV` (seasonally adjusted, U.S. city average). Download the monthly values from January 2024 to the latest month from the BLS data tools. Save the file exactly as downloaded in `data/raw/macro/`, with a name like `bls_CUSR0000SEFV.csv`.
- **Food-service sales:** Census Bureau monthly retail trade data, "Food services and drinking places" (NAICS 722), seasonally adjusted, millions of dollars. Download the monthly values for the same months. Save the file exactly as downloaded in `data/raw/macro/`, with a name like `census_naics722_sa.csv`. Note whether the values are advance estimates or revised estimates.
- **Record in the decisions log, from each source page:** units, seasonal adjustment, whether the series is annualized, the CPI base period, the page URL, and the download date. These go into the tags word for word.
- The download date is part of the lineage, because retail sales estimates get revised after first release.
- `macro_monthly.series_id` values: `CUSR0000SEFV` for CPI and `CENSUS_722_SA` for food-service sales.
- No network is needed for this data. `src/ingest_macro.py` reads the local files only.

### 6.5 Comparable sales (entered by hand)

- **Companies:** CMG, WING, DRI (consolidated).
- **Periods:** the 4 most recent reported quarters inside the time window. 12 values in total.
- **Values:** from each 8-K earnings release (exhibit 99.1). Store each as a percent number (`3.2` means 3.2%), exactly as printed, with the release URL.
- **Definitions (3):** copied word for word from each company's 10-K into `comps_definitions.csv`, with the source URL. Note the differences you find, such as how long a restaurant must be open to count, company-operated vs. system-wide, and treatment of the 53rd week.
- **Check:** after entering everything, re-check every value against its source once.

---

## 7. Database schema

```sql
CREATE TABLE fundamentals (
  ticker VARCHAR, cik VARCHAR, metric VARCHAR, concept VARCHAR,
  value DOUBLE, unit VARCHAR,
  period_start DATE,          -- NULL for balance-sheet values
  period_end DATE,
  period_basis VARCHAR,       -- 'Q','YTD6','YTD9','FY','instant'
  fiscal_year INTEGER, fiscal_quarter INTEGER,
  form VARCHAR, accession VARCHAR, filed DATE
);

CREATE TABLE comps_quarterly (
  ticker VARCHAR, fiscal_year INTEGER, fiscal_quarter INTEGER,
  comp_sales_pct DOUBLE, definition_id VARCHAR, source_url VARCHAR
);

CREATE TABLE comps_definitions (
  definition_id VARCHAR, ticker VARCHAR, definition_text VARCHAR,
  source_url VARCHAR, notes VARCHAR
);

CREATE TABLE brand_attention_daily (
  date DATE, article_title VARCHAR, brand VARCHAR,
  grain VARCHAR,              -- 'brand' or 'parent'
  parent_ticker VARCHAR, views BIGINT
);

CREATE TABLE macro_monthly (
  series_id VARCHAR, date DATE, value DOUBLE, retrieved_on DATE
);
```

**Data checks `build_db.py` must print:**

- Row counts per table.
- Each of the 4 companies has 8 fiscal quarters of balance-sheet values.
- Each of the 10 brands and parents has 731 days, summed across its titles (Habit Burger Grill has two titles; 2024 is a leap year).
- No duplicate keys, using the date-based keys in §6.2 (never fiscal labels).
- No `period_basis = 'other'` rows left.
- 12 comps rows and 3 definitions.
- The concept chosen for each company and metric, with its coverage.

---

## 8. Tag schema

### 8.1 Fields

| Field | Allowed values | Meaning |
|---|---|---|
| `id` | `table.metric` or `table.column` | Unique name |
| `table`, `filter` | e.g. `{metric: total_assets}` | Where the metric lives. Needed because `fundamentals` is a long table: one `value` column holds many metrics, so you **tag each metric, not just each column** |
| `semantic_type` | flow, stock, ratio, per_share, index, count, identifier, dimension | What kind of number it is |
| `unit`, `scale` | USD, USD/shares, percent, index_points, views; scale 1 | Units |
| `additive_over_entities` | true / false | Can you add it across companies or brands? |
| `additive_over_time` | true / false | Can you add it across periods? |
| `time_rollup` | sum, last, reported_fy_value, mean, none | How to get a yearly figure |
| `valid_methods` | list from §9.3 | What `aggregate` allows |
| `period_basis` | quarterly, mixed, instant, daily, monthly | `mixed` means "read the period_basis column" |
| `derivation` | text | e.g. "Q_n = YTD_n − YTD_(n−1); Q4 = FY − YTD9" |
| `calendar` | fiscal, calendar | Which calendar periods refer to |
| `seasonal_adjustment` | SA, NSA, n/a | For macro series |
| `annualized` | true / false | For macro series |
| `entity_grain`, `hierarchy` | company, brand, parent; e.g. "brand → parent_ticker" | Level of detail |
| `comparability` | same_definition, by_definition_id | Whether values are comparable across companies |
| `lineage` | source, id_column or URL, retrieval date | Where the number came from |
| `description` | one or two plain sentences | For humans and models |

### 8.2 Pydantic validator (`src/tags.py`)

```python
from typing import Literal, Optional
from pydantic import BaseModel

class Tag(BaseModel):
    id: str
    table: str
    filter: Optional[dict] = None
    semantic_type: Literal["flow","stock","ratio","per_share","index","count","identifier","dimension"]
    unit: Optional[str] = None
    additive_over_entities: Optional[bool] = None
    additive_over_time: Optional[bool] = None
    time_rollup: Optional[Literal["sum","last","reported_fy_value","mean","none"]] = None
    valid_methods: list[str] = []
    period_basis: Optional[Literal["quarterly","mixed","instant","daily","monthly"]] = None
    derivation: Optional[str] = None
    calendar: Optional[Literal["fiscal","calendar"]] = None
    seasonal_adjustment: Optional[Literal["SA","NSA","n/a"]] = None
    annualized: Optional[bool] = None
    entity_grain: Optional[str] = None
    hierarchy: Optional[str] = None
    comparability: Optional[Literal["same_definition","by_definition_id"]] = None
    lineage: dict
    description: str
```

Loading should fail loudly on any unknown field or bad value. Add a rule that measures (flow, stock, ratio, per_share, index, count) must have both additivity fields filled in.

### 8.3 The full tag list (about 20 entries)

| id | Type | Key rule |
|---|---|---|
| fundamentals.revenue | flow | Sum discrete quarters only; derive Q4 as FY − YTD9 |
| fundamentals.operating_income | flow | Same as revenue |
| fundamentals.net_income | flow | Same as revenue |
| fundamentals.op_cash_flow | flow | 10-Q values are YTD; derive single quarters |
| fundamentals.capex | flow | 10-Q values are YTD; reported as a positive number |
| fundamentals.total_assets | stock | Yearly value is the last quarter-end; addable across companies |
| fundamentals.diluted_eps | per_share | Never sum quarters (share counts change); use the reported annual figure; not addable across companies |
| derived.operating_margin | ratio | Computed as total operating income ÷ total revenue; never averaged |
| comps_quarterly.comp_sales_pct | ratio | Not addable; comparability is by definition ID, so cross-company comparisons must warn |
| brand_attention_daily.views | count | Addable; roll up using brand rows only (parent rows would double-count) |
| macro.food_services_sales | flow | Census NAICS 722, monthly, seasonally adjusted; a quarter is the sum of its months *if* the series isn't annualized (check the Census page) |
| macro.CUSR0000SEFV | index | Use percent change or a period average; never sum |
| Dimension columns: ticker, fiscal_year, fiscal_quarter, period_basis, period_end, grain, parent_ticker, accession, date | dimension / identifier | Describe their meaning only |

Write the entries for the dimension columns too. Setup A won't see them, but setups B, C, and D need them.

---

## 9. `semantics.py` specification

### 9.1 Period formats

| Format | Meaning | Used for |
|---|---|---|
| `FY2025` | Fiscal year | Fundamentals, comps |
| `FY2025Q3` | Fiscal quarter | Fundamentals, comps |
| `CY2025Q1` | Calendar quarter | Pageviews, macro |
| `2025-01:2025-12` | Month range | Macro |

### 9.2 Every function returns the same envelope

```json
{
  "status": "ok | warning | error",
  "value": 123.4,
  "values": {"CMG": 1.2, "WING": 3.4},
  "unit": "USD",
  "period": {"label": "FY2025Q3", "start": "2024-11-25", "end": "2025-02-23"},
  "explanation": "Derived as YTD9 minus YTD6.",
  "derivation": ["YTD9 = ...", "YTD6 = ..."],
  "sources": [{"type": "sec_filing", "accession": "...", "url": "https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/"}],
  "use_instead": null,
  "definitions": null
}
```

Build SEC links as `https://www.sec.gov/Archives/edgar/data/{CIK without leading zeros}/{accession without dashes}/`. Test one per company in a browser.

### 9.3 Functions

- **`list_metrics()`** returns every metric ID with a one-line description.
- **`describe_column(metric_id)`** returns the full tag. For comps, it also returns each company's definition.
- **`get_metric(ticker, metric, period)`** returns one company, one period:
  - A reported single quarter is returned as is.
  - Otherwise Q2 = YTD6 − Q1, Q3 = YTD9 − YTD6, and Q4 = FY − YTD9.
  - Before subtracting, check that each period starts the day after the previous one ends.
  - For stocks, return the balance at the period end.
  - For EPS with a fiscal-year period, return the reported annual figure.
  - If any piece is missing, return `status: error` with "insufficient data." Never estimate.
- **`aggregate(metric_id, entities, period, method, denominator_id=None)`** checks the method against the tag first:

| Method | Allowed when | What it does |
|---|---|---|
| `last` | stock | Value at the last period end in the range |
| `sum_over_time` | flow or count with `additive_over_time` | Derives discrete quarters first, then sums |
| `sum_across_entities` | `additive_over_entities` | Sums across the listed companies |
| `ratio_of_sums` | numerator and denominator are flows | Sums each, then divides (combined margin) |
| `pct_change` | index, stock, or flow | (end − start) ÷ start |
| `mean_over_time` | index | Period average (e.g. annual average CPI) |
| `rollup_to_parent` | count with a hierarchy | Sums `grain = 'brand'` rows only |

  - **A disallowed method** returns `status: error` with `use_instead`. For example, `sum_over_time` on total assets returns `use_instead: "last"`, and averaging a ratio returns `use_instead: "ratio_of_sums"`.
  - **Comps across more than one company** returns `status: warning` with each company's value and full definition.
  - **Mixed fiscal calendars** (DRI combined with December year-end companies in one total) returns a warning that the periods don't line up.

### 9.4 Tests (`tests/test_semantics.py`), written before the code

First, collect every expected value by hand from the filings into `tests/expected_values.md`, noting the filing, statement, and column for each. The tests may use only those values. The same rows are reused in the answer-key verification log (§11.3).

1. YUM FY2025 total assets equals the Q4 balance.
2. `sum_over_time` on total assets returns an error suggesting `last`.
3. DRI FY2025Q3 operating cash flow equals YTD9 minus YTD6, with two sources.
4. CMG FY2025Q4 capex equals FY minus YTD9.
5. CMG FY2025 diluted EPS equals the reported annual value, not the sum of quarters.
6. A combined margin equals the ratio of sums; a mean of margins is rejected.
7. A YUM brand rollup excludes the "Yum! Brands" parent row.
8. A multi-company comps request returns a warning with definitions.
9. CPI `pct_change` works; `sum_over_time` on CPI is rejected.
10. A missing period returns "insufficient data."
11. Every `ok` result has at least one source.
12. The DRI fiscal Q3 period dates fall roughly between December and February.

The expected values in these tests must come from filings you checked by hand, not from running the code. Never change an expected value to make a test pass, unless re-reading the filing proves the value was wrong.

---

## 10. MCP server specification

**Four tools:** `list_metrics`, `describe_column`, `get_metric`, `aggregate`. Each is a thin wrapper around `semantics.py`.

**Tool descriptions matter, because models read them.** Store them once in `src/tool_specs.py` and use that same text in both the MCP server and the evaluation's setup D:

- `list_metrics`: "List available metrics with one-line descriptions."
- `describe_column`: "Return the semantic tags for a metric: type, how it may be aggregated, period basis, calendar, units, and lineage. Call this before computing anything."
- `get_metric`: "Return one company's value for one period (FY2025 or FY2025Q3). Derives single quarters from year-to-date values when needed. Returns sources."
- `aggregate`: "Aggregate a metric across companies or periods using a named method. Rejects methods the metric's tags don't allow and suggests the correct one. Returns sources and warnings."

**Running it:** `claude mcp add restaurant-semantics -- python src/mcp_server.py`

**Demo check:** ask in Claude Code, "What was Darden's operating cash flow in fiscal Q3 2025, and where does that number come from?" The answer should give the derived value and two working filing links.

---

## 11. Evaluation design

### 11.1 Question format (`eval/questions.yaml`)

```yaml
- id: q017
  category: ytd_calendar
  question: "What was Darden's net cash from operating activities in its fiscal Q3 2025, in US dollars?"
  expected_behavior: answer        # answer | answer_with_warning | refuse
  correct: 0                       # filled from independent calculation, then hand-checked
  unit: USD
  trap_answers: {used_ytd_value: 0}
  verified_against: "accession ..., cash flow statement, nine-month column"
  notes: ""
```

**Writing rules:**

- Draft the wording by hand in `eval/questions_draft.md` on Friday, as an analyst would ask, before `semantics.py` exists. Commit the draft. Later edits may only add a missing period or unit, and each edit is listed.
- Each question has exactly one correct numeric answer an expert would agree on, or `expected_behavior: refuse`. Name the period and unit, and say "annual average" when that's what you mean.
- Cross-company comps questions ask for one number (for example, "CMG comps minus WING comps for fiscal Q2 2025, in percentage points") and expect `answer_with_warning`.
- Store the answer each trap would produce. `make_questions.py` drops any question whose trap answer is within 2× the tolerance of the correct answer, because it can't tell right from wrong. Replace dropped questions so each category stays at 7.
- **Freeze the questions before any evaluation run** (`git tag questions-frozen`). If you must fix one later, log the change and re-run every setup.

### 11.2 The 42 questions

| Category | Count | What to vary | Trap answers to store |
|---|---|---|---|
| time_additivity | 7 | FY2025 total assets × 4 companies; FY2024 total assets × 1; full-year diluted EPS × 2 | Sum of 4 quarters; mean of 4 quarters |
| ratios | 7 | Combined FY2025 operating margin for 2–3 December year-end companies × 3; one company's annual margin from its quarters × 3; one question mixing in DRI (expects a warning) × 1 | Mean of margins |
| ytd_calendar | 7 | Q2/Q3 operating cash flow × 2; Q4 capex × 2; DRI fiscal-quarter values × 2; food-service sales during DRI's fiscal Q3 months × 1 | Raw YTD value; FY value; wrong months |
| indices | 7 | CPI December-to-December % change × 2; CPI annual average × 2; quarterly food-service sales totals × 3 | Index point difference; sum of index levels; average instead of sum |
| hierarchy | 7 | YUM brand views per calendar quarter × 3; Darden brand views × 2; KFC's share of YUM's views × 2 | Totals including parent rows |
| comparability_unanswerable | 7 | Cross-company comps as one number (expects a warning) × 3; a metric not in the data, such as average unit volume or restaurant counts × 2; a period outside the window × 1; CAVA comps, which aren't in the data (refuse) × 1 | Any confident single answer |

### 11.3 Building the answer key

- **Never use `semantics.py` to compute the answer key.** Use a separate short script, `eval/make_questions.py`, with direct pandas or SQL, so the code being tested is not grading itself. Check yourself that it imports nothing from `semantics.py`.
- Then check every answer by hand in `eval/verification_log.csv`, with columns `question_id, source_url, where_in_source, value_seen, matches, notes`. Reuse the rows from `tests/expected_values.md` where they apply:
  - **SEC numbers:** open the filing and find the number in the statement. For derived quarters, check both pieces. For CMG EPS, check against the latest filing that shows that period (post-split).
  - **BLS and Census:** check against the downloaded file and the agency's own web page for that series.
  - **Comps:** check against the earnings release.
  - **Pageviews:** spot-check three totals with the Wikimedia "Pageviews Analysis" web tool, and confirm the parent row is excluded.
- No question goes into an evaluation run until its log row says `matches = yes`.
- **Time limit:** stop verifying at midnight on Saturday. If fewer than 42 are verified, run only verified questions: at least 36 in total and at least 6 per category.

### 11.4 The four setups

All four share the same model, the same base instructions, and the same final-answer format.

| Setup | What the model gets | Tools |
|---|---|---|
| A | The output of `DESCRIBE` for every table | `run_sql` |
| B | Prose descriptions of every column, **containing the same facts as the tags** | `run_sql` |
| C | The full `tags.yaml` | `run_sql` |
| D | Tags available through `describe_column` | The 4 semantic tools; **no SQL** |

- Because B and C contain the same facts, B vs. C tests only the format. State this in the write-up.
- D changes two things at once, the interface and the enforcement. State that too.

**`run_sql` rules:** open DuckDB with `read_only=True`, return at most 200 rows, return errors as text so the model can retry, and time out after 10 seconds.

**Shared instructions:**

> Answer using only the tools. If the data needed isn't available, say so and set refused to true. If the answer needs a caveat, set warning to true. End with exactly one line:
> `FINAL: {"answer": number_or_null, "unit": "...", "warning": true_or_false, "refused": true_or_false}`

### 11.5 Harness (`eval/run_eval.py`)

- Model `claude-haiku-5-5` (Anthropic API), default temperature, up to 10 tool-use turns, `max_tokens` 2000.
- **Cost control:** the harness adds up the cost after every run from the token counts and the published prices, and stops at a hard cap of **$5**. Cache the fixed part of each prompt (instructions plus the setup's context) with prompt caching. The estimated full-run cost is about $1.
- **API key:** read from `ANTHROPIC_API_KEY`, stored as a network secret in the cloud environment or in a local `.env`. Never committed.
- 3 runs for each question and setup: 504 runs for 42 questions. Concurrency of 5.
- Retry API errors with increasing waits. Never retry because an answer was wrong.
- For each run, write one line to `eval/results/{setup}.jsonl`: question_id, setup, run, final, all tool calls with inputs, full text, tokens, and time taken.
- **Pilot first:** 5 questions × 4 setups = 20 runs. Read every transcript, fix bugs, and project the full-run cost from actual token use. Start the full run only if the projection is under the cap.
- **Fallback:** if the pilot shows a cost or rate-limit problem, use 2 runs per question and say so in the README.

### 11.6 Scoring (`eval/score.py`)

**Tolerances:**

| Unit | Tolerance |
|---|---|
| USD | 0.5% relative |
| Percent | 0.1 percentage points |
| EPS | $0.01 |
| Views | 0.1% |
| Index percent change | 0.05 percentage points |

**What each run is scored on:**

- **Correct:** the number is within tolerance *and* the behavior matches the expected one.
- **Trap hit:** the number matches a stored trap answer. Record which trap.
- **Behavior:** a warning when one was expected; a refusal for unanswerable questions; no refusal for answerable ones.
- **A final line that can't be parsed** counts as incorrect and is listed separately.

**Reported results (`eval/results/summary.md`):**

- Accuracy by setup and category: the mean across runs, with the lowest and highest run.
- Trap-hit rate by setup and trap.
- Behavior accuracy.
- **B vs. C paired by question:** how many questions B got right and C got wrong, and the reverse (majority vote across runs). With this sample size, a difference of a few questions is within noise and must be reported that way.
- Average tool calls and tokens per question, which shows the cost of each setup.
- The total cost of the run and the exact model ID and run date.

`score.py` also writes the same results as `eval/results/summary.json`. The results page (§13.1) reads only this file, `questions.yaml`, `tags.yaml`, `verification_log.csv` and the `.jsonl` transcripts.

### 11.7 Error analysis

- For each setup, pick the 2 most instructive failures.
- For each, write one sentence on what happened and one on what would fix it.
- At least one example must come from setup D. If D never failed, say what it cannot do, such as answering questions outside the tools' coverage.
- Written by you, using transcripts Claude Code pulls out.

### 11.8 Limits of the evaluation (state these openly)

- Small sample: 7 questions per category, 4 companies.
- One model.
- You wrote both the questions and the system, a source of bias. Mitigation: questions were drafted before the core logic existed, written from an analyst's point of view, and frozen before any run.
- In D, the interface and the enforcement change together.
- D's tools cover the question categories closely, so D's advantage on answerable questions is partly by design. The unanswerable and out-of-coverage questions are D's real test.
- Pageviews are only a proxy for real alternative data.
- No 10-K or 10-Q amendments are included.
- A two-year window.

---

## 12. Build phases

Each phase lists its day, goal, the files it produces, acceptance checks, what you must check personally, and a prompt seed.

### Friday, October 23 (Phases 0–5, plus question drafting)

**Phase 0: Repo setup.** Skip if already done.
- **Files:** folder structure (§5), `pyproject.toml`, `.gitignore` (`.env`, `*.duckdb`), `.env.example`, a README stub, `SPEC.md`, and `CLAUDE.md` containing:

```
Rules for this repo:
- Never invent data values. If a value can't be fetched or found, stop and tell me.
- Never commit API keys. Read keys from .env.
- Follow SPEC.md exactly; ask before changing the schema, tag fields, tool descriptions, or the question file.
- Scope is Version 2.2: 4 companies (CMG, WING, YUM, DRI), 42 questions, 504 runs, eval model claude-haiku-5-5 with a $5 cap. No auto-tagging, no case study PDF.
- The only frontend is the static results page in SPEC.md §13.1. Never build a chatbot, a live query UI, or a backend. Every number on the page must be read from eval output files.
- semantics.py is the only place aggregation rules live.
- The eval answer key must never be computed with semantics.py.
- Agents get read-only DuckDB access.
- Never change a test's expected value to make it pass.
- Start every session from an up-to-date main (git pull). If SPEC.md is missing, stop and tell me; never go looking for it on other branches.
- End every phase by committing, pushing, and opening a PR into main. Never merge it yourself; I merge after my checks.
- Every phase ends by running its acceptance checks and showing the output. Then stop.
```

- **Accept when:** `pip install -e .` works and `pytest` runs (0 tests is fine).
- **Prompt seed:** "Read SPEC.md §0, §5, and §12 Phase 0. Set up the repo exactly as described. Run the acceptance checks and show the output. Then stop."

**Phase 1: SEC ingestion.** Spec §6.1–6.2. The riskiest phase; start it first.
- **Files:** `src/ingest_sec.py`, `data/raw/sec/*.json`, `data/interim/fundamentals.parquet`.
- **Accept when:**
  - CMG FY2025 revenue printed.
  - DRI quarters labeled with the right fiscal years.
  - Q2 and Q3 operating cash flow present as YTD6 and YTD9 rows.
  - No `other` period types.
  - The concept coverage table is printed, with one concept per (ticker, metric) and no gaps.
- **You check personally:**
  - CMG FY2025 revenue and DRI fiscal Q3 2025 YTD operating cash flow against the actual filings.
  - Whether any company used an unexpected concept.
  - Whether Darden's fiscal 2026 is a 53-week year (10-K cover page).
- **Prompt seed:** "Read SPEC.md §6.1, §6.2 and §12 Phase 1. Do Phase 1 only, for CMG, WING, YUM and DRI. Choose the concept per (ticker, metric) and print the coverage table. If any metric has a gap, stop and show me; don't pick a fallback yourself. Print every row classified as 'other'. Run the acceptance checks and show the output. Then stop."

**Phase 4: Comps entry (you, by hand, while Phase 1 runs).** Spec §6.5. Claude Code only creates the two CSV templates.
- **Accept when:** 12 values entered, 3 definitions, every value re-checked.
- **You check personally:** all of it. This phase is the finance-credibility core.
- **Also while Phase 1 runs:** verify the 10 Wikipedia titles in a browser, and download the BLS and Census files into `data/raw/macro/` and write their metadata into the decisions log (§6.4).

**Phase 2: Wikipedia ingestion.** Spec §6.3.
- **Files:** `src/ingest_wiki.py`, raw JSON, parquet.
- **Accept when:** 731 distinct dates per brand and parent, summed across titles, with no gaps.

**Phase 3: Macro ingestion.** Spec §6.4. Can run in the same session as Phase 2.
- **Files:** `src/ingest_macro.py`, reading only the local files in `data/raw/macro/`. No network.
- **Accept when:** both series loaded monthly from January 2024, each with its download date, units and seasonal adjustment as recorded in the decisions log.
- **Prompt seed (Phases 2 and 3):** "Read SPEC.md §6.3, §6.4 and §12 Phases 2 and 3. Do Phases 2 and 3 only. Use exactly these Wikipedia titles: <paste the 10 titles>. Read the macro data only from the local files in data/raw/macro/; take download dates and units from the decisions log. Run both phases' acceptance checks and show the output. Then stop."

**Phase 5: Build the database.** Spec §7.
- **Accept when:** all data checks in §7 print clean.
- **Prompt seed:** "Read SPEC.md §6.2 rule 3, §7 and §12 Phase 5. Do Phase 5 only. Use the date-based uniqueness keys, never fiscal labels. Print every data check. Then stop."

**Question drafting (you, Friday night).** Spec §11.1–11.2.
- **Files:** `eval/questions_draft.md`: 42 questions, wording only, no answers.
- **Accept when:** committed before you sleep. This timestamp shows the questions came before the rule engine.

### Saturday, October 24 (Phases 6–10; questions frozen by the end of the day)

**Phase 6: Tags and validator.** Spec §8.
- **Files:** `tags/tags.yaml`, `src/tags.py`.
- **Accept when:**
  - Every metric and dimension column is tagged.
  - The validator passes.
  - A deliberately broken tag fails validation.
- **You check personally:** every additivity and time-rollup value.
- **Prompt seed:** "Read SPEC.md §8 and §12 Phase 6. Do Phase 6 only. Use the BLS and Census units, seasonal adjustment and annualization from the decisions log, word for word. Show that a deliberately broken tag fails validation. Then stop."

**Phase 7: Core logic and tests.** Spec §9.
- **Order:** first, you collect expected values from filings into `tests/expected_values.md` (about 1 hour). Then Claude Code writes the tests from those values only, you approve them, and then it writes the code.
- **Accept when:** all 12 tests pass.
- **You check personally:** read every line of the quarter-derivation and method-checking code. Open one SEC link per company in a browser.
- **Prompt seed:** "Read SPEC.md §9 and §12 Phase 7. Write tests/test_semantics.py first, using ONLY the expected values in tests/expected_values.md. Show me the tests and wait for my OK. Then write src/semantics.py until all 12 tests pass. Never change an expected value to make a test pass. Then stop."

**Phase 8: MCP server.** Spec §10.
- **Accept when:** the demo question returns the right value and two working links.
- **Prompt seed:** "Read SPEC.md §10 and §12 Phase 8. Do Phase 8 only. Tool descriptions live only in src/tool_specs.py. Then stop."

**Phase 9: Question set and answer key.** Spec §11.1–11.3.
- **Files:** `eval/make_questions.py` (independent of `semantics.py`), `eval/questions.yaml`.
- **Accept when:**
  - 42 questions, 7 per category, built from `eval/questions_draft.md`.
  - Trap answers stored.
  - Questions with trap answers within 2× tolerance removed and replaced.
- **You check personally:** `make_questions.py` imports nothing from `semantics.py`.
- **Prompt seed:** "Read SPEC.md §11.1–11.3 and §12 Phase 9. Turn eval/questions_draft.md into eval/questions.yaml. Keep my wording; change it only to name a missing period or unit, and list every change. Compute correct and trap answers in eval/make_questions.py with direct SQL or pandas. Never import semantics.py. Drop any question whose trap answer is within 2x tolerance and tell me which. Then stop."

**Phase 10: Hand verification.**
- **Files:** `eval/verification_log.csv`.
- **Accept when:** every question in the file says `matches = yes` (42, or at least 36 with 6 per category). Then commit and run `git tag questions-frozen`.
- **You check personally:** all of it. Budget 3 to 3.5 hours. Stop at midnight.

### Sunday, October 25 (Phases 11–15)

**Phase 11: Contexts.**
- **Files:** `eval/contexts/schema_only.txt`, `prose.txt`, `tags.txt`.
- **You check personally:** prose and tags contain the same facts. Put them side by side and tick off each fact.
- **Prompt seed:** "Read SPEC.md §11.4 and §12 Phase 11. Write schema_only.txt from DESCRIBE output, tags.txt from tags.yaml, and prose.txt as plain sentences containing exactly the same facts as tags.txt: no more, no less. Then stop."

**Phase 12: Harness and pilot.** Spec §11.4–11.5.
- **Accept when:** the pilot of 20 runs completes and the transcripts look sensible.
- **You check personally:** read all 20 transcripts. Decide on 3 runs or 2 from the measured cost, and record the decision.
- **Prompt seed:** "Read SPEC.md §11.4–11.5 and §12 Phase 12. Build eval/run_eval.py for claude-haiku-5-5 with prompt caching, concurrency 5, a running cost total with a hard $5 cap, and a --pilot flag (5 questions x 4 setups). Run the pilot. Print tokens and cost per run and the projected cost of the full run. Then stop."

**Phase 13: Full run and scoring.** Spec §11.6.
- **Files:** `eval/results/*.jsonl`, `eval/score.py`, `eval/results/summary.md`.
- **Accept when:** all runs complete, parse failures are listed, and the tables are generated, including the B vs. C paired table.
- **You check personally:** pick three runs at random and check their scores by hand.
- **While the full run is going:** Claude Code builds the results page (Phase 15a) against the pilot results, and you write the README sections that don't depend on results (§13).

**Phase 14: Error analysis.** Spec §11.7.
- **Files:** `docs/error_analysis.md`.
- **You check personally:** written by you, using examples Claude Code pulls out of the transcripts.

**Phase 15a: Results page.** Spec §13.1. Built by Claude Code while the full run (Phase 13) is going, first against the pilot results, then regenerated from the full results.
- **Files:** `report/build_report.py`, `report/template.html`, `report/replays.yaml`, `docs/index.html`.
- **Accept when:**
  - `python report/build_report.py` builds `docs/index.html` from the eval output files only, and fails loudly if any file or number is missing.
  - The page opens offline from the file system and on GitHub Pages.
  - All six sections in §13.1 render at a 1440-pixel-wide laptop window, and the page also reads at phone width.
  - Every SEC link on the page opens the right filing.
- **You check personally:** every number on the page against `summary.md`; the replay for Yum's total assets in setups A and D; that nothing on the page claims more than the results show.
- **Prompt seed:** "Read SPEC.md §13.1 and §12 Phase 15a. Build report/build_report.py and the template. The page is static and read-only: no backend, no API calls, no chatbot, no external scripts except one pinned charting library if needed. Read data only from eval/results/summary.json, eval/results/*.jsonl, eval/questions.yaml, tags/tags.yaml and eval/verification_log.csv. Use eval/results/pilot results for now. Fail loudly if any number is missing. Then stop."

**Phase 15b: Write-up, video, and email.** Spec §13.
- **Accept when:** the results page is regenerated from the full results, the README's first screen is complete, the video is recorded from the results page plus the live MCP demo, the email is drafted (not sent), and the quickstart works from a fresh clone.

**Phase 16: Auto-tagging. CUT in Version 2.** Listed as a next step in the README.

---

## 13. Deliverables

**README (the first screen must say everything):**

1. Title, plus one sentence stating the problem.
2. The results table: accuracy by setup, and trap-hit rate.
3. A three-line takeaway. Lead with the B vs. C result, stated honestly (if the difference is within noise, say so).
4. A link to the results page (§13.1) and to the video.
5. Quickstart: `python src/build_db.py && pytest && python eval/run_eval.py --pilot`
6. Architecture diagram (§5).
7. How the answer key was verified.
8. **Related approaches:** Kimball's additive, semi-additive and non-additive measures; dbt MetricFlow's `non_additive_dimension`; Databricks metric views. One sentence: `semantics.py` is a minimal semantic layer; this project measures how much each layer of context and enforcement buys.
9. What tagging fixed and what it didn't.
10. Limitations (§11.8).
11. "How this maps to Unity Catalog," two hedged sentences.
12. Next steps: auto-tagging for vendor onboarding, a clean-table baseline, streaming (one line each).

### 13.1 Results page: the pitch frontend (`docs/index.html`)

**Why it exists:** the reader will spend about two minutes. They won't read a repo, and a terminal recording is hard to follow. The results page turns the evidence into something they can see at a glance in the Loom video and open themselves afterwards.

**What it is:** one static, read-only HTML page, generated by `report/build_report.py` from the recorded eval output, and published free on GitHub Pages from the `docs/` folder. No backend, no login, no API key, no live model calls, no cost.

**What it is not:** not a chatbot, not a query box, not a product. It replays runs that already happened. This keeps it from looking like a copy of their analyst platform, and it can't fail on camera.

**Sections, top to bottom:**

1. **The problem.** One sentence, plus the Yum example: `SUM(total_assets)` over four quarters vs. the year-end balance, both numbers shown, with the 10-K link.
2. **Results at a glance.** A bar chart of accuracy by setup (A, B, C, D) with the run-to-run range, and trap-hit rate by setup. The sample size is printed beside the chart ("42 questions × 3 runs, claude-haiku-5-5, run on <date>").
3. **Side-by-side replay.** A picker for 6 questions you choose, one per category, listed in `report/replays.yaml`. For the chosen question it shows setup A and setup D in two columns, with tabs for B and C:
   - each step the model took: the SQL it wrote or the tool it called, with inputs;
   - a short excerpt of what came back;
   - the final answer, a badge (correct, or the name of the trap it hit), the correct answer, and the source links.
   Transcripts are shown as recorded, shortened with a "show full" toggle, never edited.
4. **What a tag looks like.** The tag cards for `total_assets` and `op_cash_flow`, each with one plain sentence on what the tag tells the model.
5. **B vs. C.** The paired result in one box, with the honest wording from §13 (if the difference is within noise, the page says so).
6. **How it was checked.** Answer key computed without `semantics.py`; number of questions hand-verified against filings; questions frozen before any run (with the commit date of the draft); the limits from §11.8; links to the repo and the error analysis.

**Rules:**

- **Never stage a failure.** If setup A happened to answer the Yum question correctly, replay the clearest real setup A failure instead, and say in the video that A sometimes gets it right. Pick the replays only after the full run.
- Every number on the page is read from `summary.json` or the other output files at build time. No number is typed into the template. The build fails if one is missing.
- Plain language, modest claims: "a small experiment."
- No Jefferies or Databricks logos, names in headings, or styling.
- Readable at a 1440-pixel laptop window for recording, and at phone width.
- Light and dark themes, a clear type scale, and one accent color. Green, red and amber are used only for correct, wrong and warning.
- Self-contained: inline CSS and JS. At most one charting library from a CDN, pinned to an exact version, or hand-drawn SVG bars.

**Time budget:** about 2 hours of Claude Code time on Sunday while the full run is going, plus 30 minutes of your checking.

**Two-minute Loom script (one or two takes, no editing, under 2:30):**

| Time | Screen | What you say |
|---|---|---|
| 0:00–0:15 | Results page, section 1 | The problem in one sentence: valid SQL, wrong answer |
| 0:15–0:45 | Replay: Yum's FY2025 total assets, setup A | The model sums four quarter-end balances and answers confidently; the badge names the trap |
| 0:45–1:10 | Same replay, setup D | The tool rejects the sum, returns the year-end balance; you click the filing link and the 10-K opens |
| 1:10–1:25 | Claude Code, live | One question through the MCP server, to show it's a working tool, not just a page |
| 1:25–1:50 | Results page, sections 2 and 5 | The results chart and the B vs. C finding, stated honestly |
| 1:50–2:10 | Results page, section 6 | How the answers were checked, the main limit, and the next step |

**The email:** use the draft from earlier in this conversation. Fill in the numbers only from `summary.md`, and verify the recipient's name.

---

## 14. How this maps to the team's world, and interview talking points

**Mapping:** keep this hedged. You know only what's public.

- Tags correspond to Unity Catalog column comments and tags.
- The enforcing `aggregate` tool plays the role of metric views and verified (trusted) queries in Genie.
- The question set works like a Genie benchmark set.
- Auto-tagging (next step) would speed up onboarding new vendor datasets.

**Design choices you should be able to explain in 30 seconds each:**

- **Why tag per metric, not per column:** long tables put many metrics in one column.
- **Why B has the same facts as C:** it isolates format from content.
- **Why D has no SQL:** enforcement only works if it can't be bypassed. The tradeoff is less flexibility.
- **Why the answer key is independent and hand-checked:** otherwise the code grades itself.
- **Why trap answers are stored:** scoring can say *which* mistake happened, without reading transcripts.
- **Why the latest-filed value is kept:** consistent, split-adjusted history. The tradeoff is losing as-originally-reported values, which you'd add for backtesting.
- **Why keys are dates, not fiscal labels:** a YTD9 row and a Q3 row share the label "quarter 3."
- **What you'd do with their data:** tag the most-used datasets first, build a benchmark from real analyst questions, and measure before and after tagging.

**Questions to expect:**

- How would this scale to 40 data sources?
- What happens when a vendor changes its schema?
- How would you tag data from a vendor's documentation?
- Why not just write better prompts?
- What would you change if analysts need as-reported values?
- **Why not just use a semantic layer, or fix the tables?** Answer: you should, for core metrics and data you own. Clean tables can't fix comps definitions that differ by company, questions with no answer, or vendor data that arrives raw. Tags are the source the semantic layer is built from, and the results show where tagging effort pays off.

---

## 15. Schedule, risks, decisions, checklist

**Schedule:**

| Day | Phases |
|---|---|
| Fri Oct 23 | 0–5, plus question drafting (comps by hand while Phase 1 runs) |
| Sat Oct 24 | 6–10; questions frozen by the end of the day (protect the evening) |
| Sun Oct 25 | 11–15 (the results page, 15a, is built while the full run goes) |
| Mon Oct 26, morning ET | Pre-send checklist, then send (8:30–10:00 ET) |

**Risks and fallbacks (decide now, not at 1 a.m.):**

| If this happens | Decide by | Do this |
|---|---|---|
| SEC data still isn't clean | Fri 10 p.m. | Drop WING's fundamentals and keep its comps. CMG, YUM and DRI can't be dropped, because each one carries a trap. |
| Comps entry is slow | Fri 11 p.m. | Enter CMG and WING only. Cross-company questions still work. Note it as a limitation. |
| Wikipedia titles wrong | Before Phase 2 | Check in a browser first |
| Tests still failing | Sat 4 p.m. | Give Claude Code the failing output and the filing value. Never edit an expected value unless the filing proves it wrong. |
| Verification behind | Sat midnight | Stop. Keep only verified questions: at least 36 in total, at least 6 per category. |
| Pilot shows high cost or rate limits | Sun noon | Use 2 runs per question and say so in the README. |
| Full run unfinished | Sun 6 p.m. | Score only if every setup has every question for at least 2 runs. Never compare setups on different questions. |
| D wins too easily | Sun, during write-up | Report it honestly, include D's failures and limits, and lead with the B-vs-C result |
| Results page not ready | Sun 6 p.m. | Ship only sections 1–3 (problem, results, Yum replay). If even that fails, record the Loom from the README and the live MCP demo. |
| Video isn't working | Sun 10 p.m. | Record a plain one-take screen capture of the results page and the demo only. |
| Still behind on Sunday night | Sun 11 p.m. | Send Tuesday morning instead. A one-day slip costs little; a wrong number costs a lot. |

**Cut order (if still late after the fallbacks above):** video polish first (a plain recording is fine), then WING's fundamentals. Never cut hand verification, setup B, or the error analysis.

**Working rules:**

1. One phase per Claude Code session. Commit after each phase.
2. Keep Claude Code and your manual work running at the same time.
3. Never type a number from memory. Every number comes from a source on your screen.
4. No verification after midnight. Sleep at least 6 hours a night.
5. No new features. Put new ideas in the README's next steps.

**Decisions log (already decided):**

- Restaurant sector; 4 companies (CMG, WING, YUM, DRI); fiscal 2024–2025 window (Darden fiscal 2025–2026).
- DuckDB.
- Data stored as filed, with traps kept.
- Latest-filed value kept for each period; date-based uniqueness keys.
- One XBRL concept per (ticker, metric), chosen for full coverage.
- Tags per metric.
- B contains the same facts as C; D has no SQL.
- One model, claude-haiku-5-5, with a $5 budget cap; 3 runs (2 if the pilot requires it).
- The only frontend is a static, read-only results page generated from eval output; no chatbot or live UI.
- 42 questions (minimum 36), drafted before the core logic and frozen before any run.
- Answer key built independently of `semantics.py` and hand-verified.
- Auto-tagging and the case study PDF cut.
- op_cash_flow candidate 2 is NetCashProvidedByUsedInOperatingActivitiesContinuingOperations. DRI uses it because DRI does not tag the total concept. DRI reports small nonzero discontinued-operations operating cash flow in the window (−7.9M fiscal Q3 2025 YTD9, −8.5M FY2025), so DRI op_cash_flow means continuing operations only. Every DRI cash-flow question and the op_cash_flow tag description must say "from continuing operations".
- Revenue concept: CMG, WING and YUM use Revenues; DRI uses RevenueFromContractWithCustomerExcludingAssessedTax.
- Phase 1 branch was fast-forwarded onto the Phase 0 commit.
- Coverage rule for flows: Q1 needs a single-quarter row; Q2 a quarter or YTD6 row; Q3 a quarter or YTD9 row; Q4 the FY row. Balances need a value at each quarter end. Diluted EPS Q4 is never derived as FY minus YTD9.
- Only rows inside each company's fiscal window are stored.
- Dedupe: duration facts keep the latest-filed row (post-split EPS); balance-sheet facts keep the earliest-filed row (as originally reported).
- DRI fiscal 2026 is a 53-week year (2025-05-26 to 2026-05-31, 371 days inclusive); its Q4 is 14 weeks. Confirmed by hand on the 10-K cover page.
- Copy-tag check compares kept rows with other kept rows only. Copies removed by the earliest-filed rule appear in the filing-conflicts report instead.
- Wikipedia: "Chipotle" is the pepper article; the brand uses "Chipotle_Mexican_Grill".
- Wikipedia: Habit Burger Grill was renamed during the window. Both titles are stored as brand rows and summed by date; the Pageviews API logs each request under one title, so this does not double-count. Habit therefore includes one former title's views; no other brand includes redirect views. Both are listed as limitations.
- Macro CPI: BLS CUSR0000SEFV, CPI-U food away from home, U.S. city average. Units: index, base 1982-84 = 100. Seasonally adjusted: yes. Annualized: no. URL: https://data.bls.gov/timeseries/CUSR0000SEFV. Downloaded: 2026-10-23. File: data/raw/macro/bls_CUSR0000SEFV.xlsx. BLS did not publish 2025-10 (data unavailable due to the 2025 lapse in appropriations); the month is absent from macro_monthly and is never filled.
- Macro food-service sales: Census Monthly Retail Trade, NAICS 722 Food services and drinking places, U.S. total, seasonally adjusted sales, monthly. Units: millions of USD, not annualized. Release date: October 15, 2026. The latest month in the file (2026-08) is a preliminary estimate (all current-month estimates are preliminary and are later superseded by revised estimates); Census prints NA for months without data. URL: https://www.census.gov/econ/currentdata/. Downloaded: 2026-10-24. File: data/raw/macro/census_naics722_sa.xlsx.
- semantics.py: mean_over_time and any aggregation over a range that includes a missing month returns status error with "insufficient data". It never averages the available months.
- Comps: the 12 comp values were entered by me from each company's earnings-release Exhibit 99.1 and cross-checked on 2026-10-24 against the text of each exhibit at the URL stored with the value. All 12 values, signs and quarters matched. WING uses domestic same store sales growth (system-wide domestic), CMG uses comparable restaurant sales, and DRI uses blended consolidated same-restaurant sales, so the three measures are not comparable.
- comps_quarterly.csv is generated by src/prepare_comps.py from data/raw/comps_entered.csv, which keeps period_end, metric and notes as provenance. The notes are not loaded into the database, so setup A cannot read them through SQL.

**Open questions to decide during the build (record answers here):**

- Exact Wikipedia titles.
- BLS and Census series details (units, seasonal adjustment, annualization, CPI base period, advance or revised estimates).
- Whether any company is missing a metric's concept.
- Whether Darden's fiscal 2026 is a 53-week year.
- 3 runs or 2, after the pilot.

**Pre-send checklist (Monday morning):**

- [ ] Recipient's name spelled correctly (check the calendar invite or the recruiter's email).
- [ ] Every number in the email matches `summary.md`.
- [ ] NorthPort and other numbers are consistent with your resume and what you said in the interview.
- [ ] Repo is public, and links open in a private browser window.
- [ ] No keys in git history (`git log -p | grep -i key`).
- [ ] README's first screen shows the problem, results, and links to the results page and video.
- [ ] Results page is live on GitHub Pages, every number matches `summary.md`, and every link opens.
- [ ] Video is under 2:30 and the filing link works on camera.
- [ ] Language is modest: a small experiment, no claims about Jefferies' internal systems.
- [ ] You have re-run the quickstart from a fresh clone.
- [ ] Sent once, on Monday morning, Eastern Time.
