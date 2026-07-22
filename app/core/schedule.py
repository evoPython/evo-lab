import json

from app.core.db import get_db

# Order matches the columns in the "classes" list of each period below:
# Monday, Tuesday, Wednesday, Thursday, Friday.
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

DEFAULT_SCHEDULE = [
    {"start": "07:20", "end": "08:10", "classes": ["None", "Physics 4-2", "Filipino 6", "Physics 4-2", "STEM-R 3"]},
    {"start": "08:10", "end": "09:00", "classes": ["Homeroom", "Physics 4-2", "Social Sciences 6", "Physics 4-2", "Blank"]},
    {"start": "09:15", "end": "10:05", "classes": ["Social Sciences 6", "Physics 4-2", "Math 6-2", "Blank", "SCALE"]},
    {"start": "10:05", "end": "10:55", "classes": ["Filipino 6", "Filipino 6", "Engineering Elective", "English 6", "Blank"]},
    {"start": "10:55", "end": "11:45", "classes": ["English 6", "English 6", "Engineering Elective", "Social Sciences 6", "Blank"]},
    {"start": "12:45", "end": "13:35", "classes": ["Engineering Elective", "STEM-R 3", "Engineering Elective", "Blank", "Blank"]},
    {"start": "13:35", "end": "14:25", "classes": ["Engineering Elective", "STEM-R 3", "Blank", "Blank", "Blank"]},
    {"start": "15:30", "end": "16:20", "classes": ["Blank", "Blank", "Blank", "Math 6-2", "Blank"]},
    {"start": "16:20", "end": "17:10", "classes": ["Blank", "Blank", "Blank", "Math 6-2", "Blank"]},
]


def get_schedule():
    """Returns (periods, holiday, updated_at)."""
    db = get_db()
    row = db.execute(
        "SELECT schedule_json, holiday, updated_at FROM class_schedule WHERE id = 1"
    ).fetchone()
    if row:
        try:
            periods = json.loads(row["schedule_json"])
        except (TypeError, ValueError):
            periods = DEFAULT_SCHEDULE
        return periods, bool(row["holiday"]), row["updated_at"]
    return DEFAULT_SCHEDULE, False, None


def set_schedule(periods):
    db = get_db()
    db.execute(
        "UPDATE class_schedule SET schedule_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (json.dumps(periods),),
    )
    db.commit()


def set_holiday(is_holiday):
    db = get_db()
    db.execute(
        "UPDATE class_schedule SET holiday = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (1 if is_holiday else 0,),
    )
    db.commit()
