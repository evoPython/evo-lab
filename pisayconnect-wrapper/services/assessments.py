"""Grading period summaries from class standing score entries."""

import re

from services.pisay_api import format_score_pair

QUARTER_ORDINALS = ("First", "Second", "Third", "Fourth", "Fifth", "Sixth")

_YEAR_SUFFIX_RE = re.compile(
    r"\s*(?:"
    r"(?:SY|S\.Y\.|School\s*Year)\s*\d{4}.*"
    r"|\d{4}\s*[-–/]\s*\d{4}"
    r"|\d{4}"
    r")\s*$",
    re.IGNORECASE,
)


def strip_school_year_suffix(name):
    """Remove trailing school-year markers from a grading period label."""
    if not name:
        return ""
    return _YEAR_SUFFIX_RE.sub("", name).strip(" ·-")


def period_tab_short_label(index):
    """Compact quarter label for narrow screens."""
    if index < 4:
        return f"Q{index + 1}"
    return f"P{index + 1}"


def period_tab_label(name, code, index):
    """Ordinal quarter label by tab order (First, Second, …)."""
    del name, code  # school-year suffixes and codes ignored for tab chips
    if index < len(QUARTER_ORDINALS):
        return f"{QUARTER_ORDINALS[index]} Quarter"
    return f"Period {index + 1}"


def extract_grading_periods(entries):
    """Unique grading periods in API order, with display labels for tabs."""
    seen = {}

    for entry in entries:
        period_id = entry.get("grading_period_id")
        if period_id is None:
            continue

        if period_id not in seen:
            seen[period_id] = {
                "grading_period_id": period_id,
                "name": entry.get("grading_period") or "",
                "code": entry.get("grading_period_code") or "",
            }

    periods = [seen[key] for key in sorted(seen.keys())]
    for index, period in enumerate(periods):
        period["label"] = period_tab_label(period["name"], period["code"], index)
        period["short_label"] = period_tab_short_label(index)

    return periods


def resolve_active_period(periods, requested_period_id):
    """Pick the requested period when valid, otherwise the first tab."""
    if not periods:
        return None

    if requested_period_id is not None:
        for period in periods:
            if period["grading_period_id"] == requested_period_id:
                return requested_period_id

    return periods[0]["grading_period_id"]


def filter_entries_by_period(entries, period_id):
    """Return entries for one grading period."""
    if period_id is None:
        return entries

    return [
        entry
        for entry in entries
        if entry.get("grading_period_id") == period_id
    ]


def build_grading_summary(entries):
  """Compute weighted per-grading-period grades from normalized score entries."""
  periods = {}

  for entry in entries:
    if not entry.get("is_show_score") or entry.get("score") is None:
      continue

    gp_id = entry.get("grading_period_id")
    if gp_id is None:
      continue

    period = periods.setdefault(
      gp_id,
      {
        "grading_period_id": gp_id,
        "name": entry.get("grading_period") or "",
        "code": entry.get("grading_period_code") or "",
        "components": {},
      },
    )

    comp_id = entry.get("component_id")
    if comp_id is None:
      continue

    component = period["components"].setdefault(
      comp_id,
      {
        "component_id": comp_id,
        "name": entry.get("category") or "Component",
        "code": entry.get("category_code") or "",
        "weight": entry.get("component_weight"),
        "entries": [],
        "total_score": 0.0,
        "total_perfect": 0.0,
      },
    )

    if component["weight"] is None and entry.get("component_weight") is not None:
      component["weight"] = entry.get("component_weight")

    score = float(entry["score"])
    perfect = float(entry.get("perfect_score") or 0)
    component["entries"].append(entry)
    component["total_score"] += score
    component["total_perfect"] += perfect

  result_periods = []

  for gp_id in sorted(periods.keys()):
    period = periods[gp_id]
    components_list = []
    period_weighted_sum = 0.0
    weights_with_scores = 0.0

    for comp in period["components"].values():
      weight = comp["weight"]
      weight_f = float(weight) if weight is not None else None

      if comp["total_perfect"] > 0:
        raw_pct = (comp["total_score"] / comp["total_perfect"]) * 100.0
      else:
        raw_pct = None

      weighted_contrib = None
      if raw_pct is not None and weight_f is not None:
        weighted_contrib = raw_pct * (weight_f / 100.0)
        period_weighted_sum += weighted_contrib
        weights_with_scores += weight_f

      enriched_entries = []
      for entry in sorted(comp["entries"], key=lambda e: (e.get("description") or "").lower()):
        score = entry.get("score")
        perfect = float(entry.get("perfect_score") or 0)
        entry_raw_pct = None
        entry_weighted = None

        if score is not None and perfect > 0:
          entry_raw_pct = (float(score) / perfect) * 100.0

        if (
          score is not None
          and comp["total_perfect"] > 0
          and weight_f is not None
        ):
          entry_weighted = (float(score) / comp["total_perfect"]) * weight_f

        enriched_entries.append({
          **entry,
          "raw_percent_display": (
            f"{entry_raw_pct:.2f}%" if entry_raw_pct is not None else "—"
          ),
          "weighted_contribution_display": (
            f"{entry_weighted:.2f}" if entry_weighted is not None else "—"
          ),
        })

      components_list.append({
        "name": comp["name"],
        "code": comp["code"],
        "weight": weight_f,
        "weight_display": f"{weight_f:.2f}%" if weight_f is not None else "—",
        "score_total_display": format_score_pair(comp["total_score"], comp["total_perfect"]),
        "raw_percent": round(raw_pct, 2) if raw_pct is not None else None,
        "raw_percent_display": f"{raw_pct:.2f}%" if raw_pct is not None else "—",
        "weighted_contribution": round(weighted_contrib, 2) if weighted_contrib is not None else None,
        "weighted_contribution_display": (
          f"{weighted_contrib:.2f}" if weighted_contrib is not None else "—"
        ),
        "entries": enriched_entries,
      })

    components_list.sort(key=lambda c: c["name"])

    period_grade = round(period_weighted_sum, 2) if weights_with_scores > 0 else None
    computation_lines = []
    for comp in components_list:
      if comp["raw_percent"] is not None and comp["weight"] is not None:
        computation_lines.append(
          f"{comp['raw_percent_display']} × {comp['weight_display']} = {comp['weighted_contribution_display']}"
        )

    result_periods.append({
      "name": period["name"],
      "code": period["code"],
      "components": components_list,
      "period_grade": period_grade,
      "period_grade_display": f"{period_grade:.2f}%" if period_grade is not None else "—",
      "computation_lines": computation_lines,
      "computation_summary": (
        " + ".join(c["weighted_contribution_display"] for c in components_list if c["weighted_contribution"] is not None)
        + (f" = {period_grade:.2f}%" if period_grade is not None else "")
      ),
    })

  return result_periods
