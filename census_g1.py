#!/usr/bin/env python3
"""
census_g1.py — Puerta G1 del SPEC v4 (censo de liquidaciones por cadena).

Solo lee CSV locales. No usa ninguna API ni red. Solo librería estándar.

USO
    python census_g1.py --markets markets.csv \
        --file robinhood=robinhood_liquidations.csv \
        --file base=base_liquidations.csv \
        [--days 90] [--top1-max 0.60] [--outside-min 300] \
        [--solvers 0xabc...,0xdef...] [--json out.json]

CSV DE LIQUIDACIONES (cabeceras, como el export de Dune que ya usaste)
    block_time, market_id, liquidator, borrower,
    repaid_assets_raw, seized_collateral_raw, bad_debt_assets_raw, tx_hash
    (opcional) tx_from : si existe y --use-tx-from, se usa en lugar de `liquidator`

CSV DE MERCADOS (obligatorio: nunca se asumen decimales ni LLTV)
    market_id, loan_decimals, lltv [, loan_usd]
    - lltv: 0.86, 86 o 86% (se normaliza)
    - loan_usd: precio USD del token de deuda; por defecto 1.0 (válido solo
      para stablecoins; para otros tokens ponlo tú)

NOTAS DE MÉTODO
    - Todo se pondera por IMPORTE repagado (USD), no por nº de eventos.
    - Incentivo bruto = repaid_usd * (LIF - 1), LIF = min(1.15, 1/(0.3*LLTV+0.7)).
      Es un TECHO: no descuenta slippage, gas ni oráculo desviado.
    - Se excluyen las auto-liquidaciones (liquidator == borrower) y los mercados
      que falten en markets.csv; ambos se informan.
    - Los umbrales son parámetros: fíjalos ANTES de mirar los resultados.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median


def parse_lltv(s: str) -> float:
    s = s.strip().replace("%", "")
    v = float(s)
    return v / 100.0 if v > 1.0 else v


def lif(lltv: float) -> float:
    return min(1.15, 1.0 / (0.3 * lltv + 0.7))


def parse_time(s: str) -> datetime:
    # Dune exporta "2026-08-14 12:00:00.000 UTC"; otros exports usan "T...Z" o "+00:00"
    s = s.strip()
    # Quitar sufijos de zona ANTES de normalizar la 'T' (si no, "UTC" se corrompe)
    for suffix in (" UTC", "UTC", "+00:00", "Z"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    s = s.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def load_markets(path):
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            mid = row["market_id"].strip().lower()
            out[mid] = {
                "dec": int(row["loan_decimals"]),
                "lltv": parse_lltv(row["lltv"]),
                "usd": float(row.get("loan_usd") or 1.0),
            }
    return out


def load_events(chain, path, markets, use_tx_from):
    events, missing, selfliq = [], defaultdict(int), 0
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mid = row["market_id"].strip().lower()
            if mid not in markets:
                missing[mid] += 1
                continue
            who = (row.get("tx_from") if use_tx_from and row.get("tx_from") else row["liquidator"]).strip().lower()
            borrower = row["borrower"].strip().lower()
            if who == borrower:
                selfliq += 1
                continue
            m = markets[mid]
            repaid = int(row["repaid_assets_raw"]) / (10 ** m["dec"]) * m["usd"]
            bad = int(row.get("bad_debt_assets_raw") or 0)
            events.append({
                "t": parse_time(row["block_time"]),
                "market": mid,
                "who": who,
                "repaid_usd": repaid,
                "bonus_usd": repaid * (lif(m["lltv"]) - 1.0),
                "bad_debt": bad > 0,
                "tx": row.get("tx_hash", ""),
            })
    return events, dict(missing), selfliq


def analyse(chain, events, days, top1_max, outside_min, solvers, missing, selfliq):
    res = {"chain": chain, "excluded_missing_markets": missing, "excluded_self_liquidations": selfliq}
    if not events:
        res.update(verdict="SIN DATOS", reasons=["no hay eventos utilizables"])
        return res

    end = max(e["t"] for e in events)
    start_win = end - timedelta(days=days)
    win = [e for e in events if e["t"] >= start_win]
    span_days = max((end - min(e["t"] for e in win)).total_seconds() / 86400.0, 1.0)
    months = span_days / 30.0
    coverage_warn = span_days < days * 0.8

    total_repaid = sum(e["repaid_usd"] for e in win)
    by_usd, by_n, by_bonus = defaultdict(float), defaultdict(int), defaultdict(float)
    for e in win:
        by_usd[e["who"]] += e["repaid_usd"]
        by_n[e["who"]] += 1
        by_bonus[e["who"]] += e["bonus_usd"]

    ranking = sorted(by_usd, key=lambda w: by_usd[w], reverse=True)
    top1 = ranking[0]
    top1_share = by_usd[top1] / total_repaid if total_repaid > 0 else 1.0
    top3_share = sum(by_usd[w] for w in ranking[:3]) / total_repaid if total_repaid > 0 else 1.0
    top1_share_n = max(by_n.values()) / len(win)

    total_bonus = sum(by_bonus.values())
    outside_bonus = total_bonus - by_bonus[top1]
    outside_month = outside_bonus / months

    sizes = sorted(e["repaid_usd"] for e in win)
    reasons, ok = [], True
    if top1_share >= top1_max:
        ok = False
        reasons.append(f"top1 por importe {top1_share:.1%} >= {top1_max:.0%}")
    if outside_month < outside_min:
        ok = False
        reasons.append(f"bruto fuera del top1 {outside_month:,.0f} $/mes < {outside_min:,.0f} $/mes")
    if top1 in solvers:
        ok = False
        reasons.append("el top1 figura en --solvers (solver/OEV)")
    if len(win) < 5:
        reasons.append("AVISO: menos de 5 eventos; muestra insuficiente")
    if coverage_warn:
        reasons.append(f"AVISO: los datos cubren {span_days:.0f} d, menos del 80% de {days} d")

    res.update(
        window_end=end.isoformat(sep=" "),
        span_days=round(span_days, 1),
        events=len(win),
        events_per_month=round(len(win) / months, 1),
        repaid_usd_total=round(total_repaid, 2),
        repaid_median_usd=round(median(sizes), 2),
        repaid_p90_usd=round(percentile(sizes, 0.9), 2),
        top1=top1,
        top1_share_usd=round(top1_share, 4),
        top1_share_events=round(top1_share_n, 4),
        top3_share_usd=round(top3_share, 4),
        gross_bonus_total_usd=round(total_bonus, 2),
        gross_bonus_outside_top1_per_month_usd=round(outside_month, 2),
        bad_debt_events=sum(1 for e in win if e["bad_debt"]),
        distinct_liquidators=len(by_usd),
        verdict="PASA G1" if ok else "NO PASA G1",
        reasons=reasons,
    )
    return res


def print_report(r):
    print("=" * 70)
    print(f"CADENA: {r['chain']}   ->   {r['verdict']}")
    if r["verdict"] == "SIN DATOS":
        print("  " + "; ".join(r["reasons"]))
        return
    print(f"  ventana: {r['span_days']} d hasta {r['window_end']}")
    print(f"  eventos: {r['events']}  ({r['events_per_month']}/mes), liquidadores distintos: {r['distinct_liquidators']}")
    print(f"  repagado: {r['repaid_usd_total']:,.2f} $   mediana {r['repaid_median_usd']:,.2f} $   p90 {r['repaid_p90_usd']:,.2f} $")
    print(f"  top1 {r['top1']}")
    print(f"    por importe {r['top1_share_usd']:.1%}   por eventos {r['top1_share_events']:.1%}   top3 por importe {r['top3_share_usd']:.1%}")
    print(f"  incentivo bruto total (techo): {r['gross_bonus_total_usd']:,.2f} $")
    print(f"  incentivo bruto fuera del top1: {r['gross_bonus_outside_top1_per_month_usd']:,.2f} $/mes")
    print(f"  eventos con deuda mala: {r['bad_debt_events']}")
    if r["excluded_self_liquidations"]:
        print(f"  excluidas {r['excluded_self_liquidations']} auto-liquidaciones")
    if r["excluded_missing_markets"]:
        print(f"  EXCLUIDOS por faltar en markets.csv: {r['excluded_missing_markets']}")
    for why in r["reasons"]:
        print("  - " + why)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markets", required=True)
    ap.add_argument("--file", action="append", required=True, metavar="CADENA=RUTA.csv")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--top1-max", type=float, default=0.60)
    ap.add_argument("--outside-min", type=float, default=300.0)
    ap.add_argument("--solvers", default="", help="direcciones separadas por coma")
    ap.add_argument("--use-tx-from", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    markets = load_markets(a.markets)
    solvers = {s.strip().lower() for s in a.solvers.split(",") if s.strip()}
    results = []
    for spec in a.file:
        if "=" not in spec:
            sys.exit(f"--file debe ser CADENA=RUTA, recibido: {spec}")
        chain, path = spec.split("=", 1)
        events, missing, selfliq = load_events(chain, path, markets, a.use_tx_from)
        results.append(analyse(chain, events, a.days, a.top1_max, a.outside_min, solvers, missing, selfliq))

    for r in results:
        print_report(r)
    print("=" * 70)
    print(f"Umbrales: top1 < {a.top1_max:.0%} por importe y bruto fuera del top1 >= {a.outside_min:,.0f} $/mes.")
    print("El bruto es un techo, no un ingreso esperado. No es asesoramiento financiero.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
