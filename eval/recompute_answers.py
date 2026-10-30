# Usage: python eval/recompute_answers.py .   (independent of make_questions.py and semantics.py)
"""Recompute every answer and trap from eval/verification_ai.csv only (no make_questions.py, semantics.py, warehouse)."""
import csv, sys, yaml
REPO = sys.argv[1]
V = {r["input_key"]: float(r["value_normalized"]) for r in csv.DictReader(open(f"{REPO}/eval/verification_ai.csv")) if r["value_normalized"] not in ("", "0") or r["input_key"].startswith("absent")}
src = {r["input_key"]: r["status"] for r in csv.DictReader(open(f"{REPO}/eval/verification_ai.csv"))}
used = {}
def v(k, q):
    used.setdefault(q, set()).add(k); return V[k]
def s(t, m, p, q): return v(f"sec:{t}:{m}:{p}", q)
A = {}
def assets(q, t, fy):
    fyv = s(t, "total_assets", f"instant:{fy}", q)
    qs = [v(f"trap:{t}:total_assets:instant:{fy}Q{i}", q) for i in (1, 2, 3)]
    A[q] = (fyv, {"sum_of_4_quarter_ends": sum(qs) + fyv, "mean_of_4_quarter_ends": (sum(qs) + fyv) / 4})
for q, t, fy in [("q001","CMG","FY2025"),("q002","WING","FY2025"),("q003","YUM","FY2025"),("q004","DRI","FY2025"),
                 ("q005","YUM","FY2024"),("q006","WING","FY2024"),("q039","CMG","FY2024")]: assets(q, t, fy)
def margin(q, ts, fy):
    oi = [s(t, "operating_income", f"FY:{fy}", q) for t in ts]; rv = [s(t, "revenue", f"FY:{fy}", q) for t in ts]
    A[q] = (100 * sum(oi) / sum(rv), {"mean_of_margins": 100 * sum(o / r for o, r in zip(oi, rv)) / len(ts)})
for q, ts, fy in [("q007",["CMG","WING"],"FY2025"),("q008",["CMG","YUM"],"FY2025"),("q009",["CMG","WING","YUM"],"FY2025"),
                  ("q010",["CMG","YUM","DRI"],"FY2025"),("q011",["WING","YUM"],"FY2025"),("q040",["CMG","WING"],"FY2024"),("q041",["CMG","YUM"],"FY2024")]:
    margin(q, ts, fy)
q = "q012"; A[q] = (s("CMG","op_cash_flow","YTD6:FY2025",q) - s("CMG","op_cash_flow","Q:FY2025",q),
                    {"used_ytd6_value": s("CMG","op_cash_flow","YTD6:FY2025",q), "used_fy_value": v("trap:CMG:op_cash_flow:FY:FY2025",q)})
q = "q013"; A[q] = (s("YUM","op_cash_flow","YTD9:FY2025",q) - s("YUM","op_cash_flow","YTD6:FY2025",q),
                    {"used_ytd9_value": s("YUM","op_cash_flow","YTD9:FY2025",q), "used_fy_value": s("YUM","op_cash_flow","FY:FY2025",q)})
for q, t in [("q014","CMG"),("q015","WING")]:
    A[q] = (s(t,"capex","FY:FY2025",q) - s(t,"capex","YTD9:FY2025",q), {"used_ytd9_value": s(t,"capex","YTD9:FY2025",q), "used_fy_value": s(t,"capex","FY:FY2025",q)})
q = "q016"; A[q] = (s("DRI","op_cash_flow","YTD9:FY2025",q) - s("DRI","op_cash_flow","YTD6:FY2025",q),
                    {"used_ytd9_value": s("DRI","op_cash_flow","YTD9:FY2025",q), "used_fy_value": v("trap:DRI:op_cash_flow:FY:FY2025",q),
                     "used_fiscal_2026": v("trap:DRI:op_cash_flow:YTD9:FY2026",q) - v("trap:DRI:op_cash_flow:YTD6:FY2026",q)})
q = "q017"; A[q] = (s("DRI","revenue","FY:FY2026",q) - s("DRI","revenue","YTD9:FY2026",q),
                    {"used_ytd9_value": s("DRI","revenue","YTD9:FY2026",q), "used_fy_value": s("DRI","revenue","FY:FY2026",q),
                     "used_fiscal_2025": s("DRI","revenue","FY:FY2025",q) - v("trap:DRI:revenue:YTD9:FY2025",q)})
q = "q042"; A[q] = (s("YUM","op_cash_flow","FY:FY2025",q) - s("YUM","op_cash_flow","YTD9:FY2025",q),
                    {"used_ytd9_value": s("YUM","op_cash_flow","YTD9:FY2025",q), "used_fy_value": s("YUM","op_cash_flow","FY:FY2025",q)})
def pct(q, a, b):
    x, y = v(f"cpi:{a}", q), v(f"cpi:{b}", q); A[q] = (100 * (y / x - 1), {"index_point_difference": y - x})
pct("q018","2024-12","2025-12"); pct("q019","2024-06","2025-06"); pct("q021","2024-12","2025-06")
m = [v(f"cpi:2024-{i:02d}", "q020") for i in range(1, 13)]; A["q020"] = (sum(m) / 12, {"sum_of_index_levels": sum(m)})
for q, ms in [("q022",["2024-07","2024-08","2024-09"]),("q023",["2025-01","2025-02","2025-03"]),("q024",["2025-04","2025-05","2025-06"])]:
    x = [v(f"census722:{k}", q) for k in ms]; A[q] = (sum(x), {"average_instead_of_sum": sum(x) / 3})
YB = ["KFC","Taco_Bell","Pizza_Hut","Habit_Burger_&_Grill","The_Habit_Burger_Grill"]
def yum(q, per): return sum(v(f"views:{b}:{per}", q) for b in YB)
for q, per in [("q025","CY2024Q4"),("q026","CY2025Q1"),("q027","CY2025Q2")]:
    b = yum(q, per); A[q] = (b, {"included_parent_rows": b + v(f"parent:Yum!_Brands:{per}", q)})
for q, per in [("q028","CY2024Q2"),("q029","CY2025Q3")]:
    b = v(f"views:Olive_Garden:{per}", q) + v(f"views:LongHorn_Steakhouse:{per}", q)
    A[q] = (b, {"included_parent_rows": b + v(f"parent:Darden_Restaurants:{per}", q)})
q = "q030"; tot = sum(yum(q, f"CY2025Q{i}") for i in range(1, 5)); kfc = sum(v(f"views:KFC:CY2025Q{i}", q) for i in range(1, 5))
A[q] = (100 * kfc / tot, {"included_parent_rows": 100 * kfc / (tot + v("parent:Yum!_Brands:CY2025", q))})
q = "q031"; tot = yum(q, "CY2024Q4"); kfc = v("views:KFC:CY2024Q4", q)
A[q] = (100 * kfc / tot, {"included_parent_rows": 100 * kfc / (tot + v("parent:Yum!_Brands:CY2024Q4", q))})
for q, p in [("q032","FY2025Q1"),("q033","FY2025Q2"),("q034","FY2025Q4")]:
    A[q] = (v(f"comps:CMG:{p}", q) - v(f"comps:WING:{p}", q), {})
for q in ("q035","q036","q037","q038"): A[q] = (None, {})

TOL = {"USD": ("rel", 0.005), "USD millions": ("rel", 0.005), "percent": ("abs", 0.1), "percentage_points": ("abs", 0.1),
       "views": ("rel", 0.001), "index_points": ("abs", 0.1)}
def ok(a, b, unit):
    if a is None or b is None: return a is None and b is None, 0.0
    kind, t = TOL[unit]; d = abs(a - b); r = d / abs(b) if kind == "rel" and b else d
    return r <= t, d
rows, bad = [], []
for Q in yaml.safe_load(open(f"{REPO}/eval/questions.yaml")):
    q = Q["id"]; mine, traps = A[q]
    good, d = ok(mine, Q["correct"], Q["unit"])
    line = [q, Q["unit"], Q["correct"], None if mine is None else round(mine, 6), "yes" if good else "NO", f"{d:.6g}"]
    if not good: bad.append(f"{q} correct: yaml {Q['correct']} vs recomputed {mine}")
    yt = Q.get("trap_answers") or {}
    if set(yt) != set(traps): bad.append(f"{q} trap names differ: yaml {sorted(yt)} vs recomputed {sorted(traps)}")
    tr = []
    for k in yt:
        if k in traps:
            g, dd = ok(traps[k], yt[k], Q["unit"]); tr.append(f"{k}={'ok' if g else 'NO'}(d={dd:.6g})")
            if not g: bad.append(f"{q} trap {k}: yaml {yt[k]} vs recomputed {traps[k]}")
    blocked = sorted(k for k in used.get(q, ()) if src.get(k) in ("pending_blocked", "hand_checked_not_reread"))
    rows.append(line + [" ".join(tr), "UNVERIFIED inputs: " + ",".join(blocked) if blocked else ""])
for r in rows: print(" | ".join(str(x) for x in r))
print("\nquestions:", len(rows), "traps checked:", sum(r[6].count("(d=") for r in rows))
print("MISMATCHES:" if bad else "MISMATCHES: none", *bad, sep="\n")
