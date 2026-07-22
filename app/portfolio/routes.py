from flask import Blueprint, render_template

from app.core.status import get_status
from app.core.schedule import get_schedule

portfolio = Blueprint(
    "portfolio",
    __name__
)


@portfolio.route("/")
def home():
    status_text, status_mode, status_updated = get_status()
    schedule_periods, schedule_holiday, _schedule_updated = get_schedule()
    return render_template(
        "home.html",
        status_text=status_text,
        status_mode=status_mode,
        status_updated=status_updated,
        schedule_periods=schedule_periods,
        schedule_holiday=schedule_holiday,
    )
