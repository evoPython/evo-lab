import time

import requests
from bs4 import BeautifulSoup
from datetime import datetime

from services.search import build_search_text
from services.request_log import log_http_exchange
from services.leave_pass import is_pending_return_signature, normalize_user_info

BASE_URL = "https://pisayconnect.com/core/api"
BASE_FILE_URL = "https://pisayconnect.com/core/api/fileManager/downloadFileByName"
REQUEST_TIMEOUT = 45
DEFAULT_SCHOOL_YEAR = "2025-2026"


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "X-Token": token,
        "Admin-Token": token,
        "Referer": "https://pisayconnect.com/portal/",
        "Accept": "application/json",
    }


def logged_request(method, url, *, label=None, log_body=True, force_log=False, **kwargs):
    headers = kwargs.get("headers") or {}
    params = kwargs.get("params")
    json_body = kwargs.get("json")
    started = time.perf_counter()
    error = None
    response = None

    try:
        timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
        response = requests.request(method, url, timeout=timeout, **kwargs)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)

        body = None
        if log_body:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:4000] if response.text else None

        log_http_exchange(
            method=method,
            url=url,
            request_headers=headers,
            params=params,
            json_body=json_body,
            response_status=response.status_code,
            response_headers=dict(response.headers),
            response_body=body,
            duration_ms=duration_ms,
            label=label,
            force=force_log,
        )

        response.raise_for_status()
        if body is not None and isinstance(body, (dict, list)):
            return body
        return response.json()

    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        if response is not None:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:4000] if response.text else None
            status = response.status_code
            resp_headers = dict(response.headers)
        else:
            body = None
            status = None
            resp_headers = {}

        log_http_exchange(
            method=method,
            url=url,
            request_headers=headers,
            params=params,
            json_body=json_body,
            response_status=status,
            response_headers=resp_headers,
            response_body=body,
            duration_ms=duration_ms,
            error=str(exc),
            label=label,
            force=force_log,
        )
        raise


def format_datetime(value):
    dt = parse_datetime_value(value)
    if dt:
        return dt.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")
    return str(value or "").strip()


def format_date(value):
    dt = parse_datetime_value(value)
    if dt:
        return dt.strftime("%b %d, %Y")
    return str(value or "").strip()


_DATE_PARSE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%b %d, %Y · %I:%M %p",
)


def parse_datetime_value(value):
    if value is None or value == "":
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        pass

    for fmt in _DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(text.split(".")[0], fmt)
        except ValueError:
            continue

    return None


def format_display_date(value, raw_hint=None):
    dt = parse_datetime_value(value)
    if dt is None and raw_hint:
        dt = parse_datetime_value(raw_hint)
    if dt:
        return dt.strftime("%b %d, %Y")
    return str(raw_hint or value or "").strip()


def format_display_datetime(value, raw_hint=None):
    dt = parse_datetime_value(value)
    if dt is None and raw_hint:
        dt = parse_datetime_value(raw_hint)
    if dt:
        return dt.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")
    return str(raw_hint or value or "").strip()


def iso_datetime(value):
    dt = parse_datetime_value(value)
    return dt.isoformat() if dt else ""


def sort_enrollment_classes(classes):
    def sort_key(item):
        return (
            (item.get("course_code") or item.get("course_name") or item.get("description") or "")
            .strip()
            .lower()
        )

    return sorted(classes, key=sort_key)


def format_time(value):
    if not value:
        return ""

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%I:%M %p")
    except (ValueError, TypeError):
        return str(value)


def nested_name(value):
    if isinstance(value, dict):
        return value.get("Name") or value.get("StatusName") or ""
    if value is None:
        return ""
    return str(value)


def process_message(html):
    if not html:
        return "", []

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on"):
                del tag.attrs[attr]

    images = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            img.decompose()
            continue

        alt = (img.get("alt") or "").strip() or "Image"
        images.append({"src": src, "alt": alt})
        img.decompose()

    for tag in soup.find_all(["p", "div", "span", "br"]):
        if tag.name == "br":
            continue
        if not tag.get_text(strip=True) and not tag.find(True):
            tag.decompose()

    if not soup.get_text(strip=True) and not soup.find(True):
        return "", images

    from services.message_colors import remap_message_colors

    return remap_message_colors(str(soup).strip()), images


def normalize_attachments(files):
    cleaned = []

    for f in files or []:
        file_info = f.get("File", {}) or {}

        cleaned.append(
            {
                "name": file_info.get("Name"),
                "filename": file_info.get("FileName"),
                "type": file_info.get("Type"),
                "size": file_info.get("Size"),
                "id": file_info.get("FileId"),
                "url": build_file_url(file_info.get("FileName")),
            }
        )

    return cleaned


def build_file_url(filename, token=""):
    return f"{BASE_FILE_URL}/{filename}/{token}"


def normalize_classwall(data):
    items = data.get("ClassWallDetailList", [])

    normalized = []

    for item in items:
        wall = item.get("ClassWall", {})
        employee = wall.get("Employee", {})

        message, images = process_message(wall.get("Message"))

        normalized.append({
            "id": wall.get("ClassWallId"),
            "message": message,
            "images": images,
            "date": wall.get("PostDateLongString"),
            "teacher": f"{employee.get('FirstName', '')} {employee.get('LastName', '')}".strip(),
            "attachments": normalize_attachments(wall.get("ClassWallFileList", [])),
        })

    for post in normalized:
        post["search_text"] = build_search_text(post)

    return normalized


def _extract_bulletin_items(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    for key in (
        "BulletinBoardFeedList",
        "BulletinBoardList",
        "FeedList",
        "Items",
        "Data",
    ):
        items = data.get(key)
        if isinstance(items, list):
            return items

    return []


def _unwrap_bulletin_item(item):
    if not isinstance(item, dict):
        return {}

    for key in ("BulletinBoard", "Bulletin", "Feed", "Item"):
        nested = item.get(key)
        if isinstance(nested, dict):
            return nested

    return item


def normalize_bulletin_board(data):
    items = _extract_bulletin_items(data)
    normalized = []

    for item in items:
        board = _unwrap_bulletin_item(item)
        if not board:
            continue

        employee = (
            board.get("Employee")
            or board.get("CreatedBy")
            or board.get("PostedBy")
            or {}
        )
        if isinstance(employee, dict):
            author = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}".strip()
        else:
            author = str(employee or "").strip()

        message_html = board.get("Message") or board.get("Content") or board.get("Body")
        message, images = process_message(message_html)

        file_list = (
            board.get("BulletinBoardFileList")
            or board.get("BulletinFileList")
            or board.get("FileList")
            or []
        )

        date_display = (
            board.get("PostDateLongString")
            or board.get("DateCreatedLongString")
            or format_datetime(board.get("PostDate") or board.get("DateCreated"))
        )

        normalized.append({
            "id": board.get("BulletinBoardId") or board.get("Id") or board.get("id"),
            "title": (board.get("Title") or board.get("Subject") or "").strip(),
            "message": message,
            "images": images,
            "date": date_display,
            "author": author or board.get("PostedByName") or "",
            "attachments": normalize_attachments(file_list),
            "is_acknowledged": bool(
                board.get("IsAcknowledged")
                or item.get("IsAcknowledged")
                or board.get("Acknowledged")
            ),
            "requires_acknowledgment": bool(
                board.get("RequiresAcknowledgment")
                or board.get("IsRequireAcknowledgment")
                or board.get("RequireAcknowledgment")
                or board.get("IsAcknowledgementRequired")
            ),
        })

    for entry in normalized:
        entry["search_text"] = build_search_text({**entry, "teacher": entry["author"]})

    return normalized


def normalize_leave_passes(data):
    items = data.get("StudentLeavePassList", [])
    normalized = []

    for item in items:
        student = item.get("Student") or {}
        first = (student.get("FirstName") or "").strip()
        last = (student.get("LastName") or "").strip()
        nickname = (student.get("Nickname") or "").strip()

        display_name = f"{first} {last}".strip()
        if nickname:
            display_name = f"{display_name} ({nickname})" if display_name else nickname

        status = nested_name(item.get("LeavePassStatus") or item.get("Status"))
        status_key = status.lower().replace(" ", "-") if status else "unknown"
        pending_return = is_pending_return_signature(item)

        if pending_return:
            status = "Pending parent's return slip signature"
            status_key = "pending-return"
            status_short = "Return pending"
        else:
            status_short = status

        normalized.append({
            "id": item.get("StudentLeavePassId"),
            "student_id": item.get("StudentId"),
            "student_no": student.get("StudentNo") or "",
            "student_name": display_name,
            "student_email": student.get("Email") or "",
            "date_created": item.get("DateCreated"),
            "date_created_display": format_datetime(item.get("DateCreated")),
            "date_from": item.get("DateFrom") or item.get("LeaveDate") or item.get("GoingHomeDate"),
            "date_from_display": format_date(item.get("DateFrom") or item.get("LeaveDate") or item.get("GoingHomeDate")),
            "date_to": item.get("DateTo") or item.get("ReturnDate"),
            "date_to_display": format_date(item.get("DateTo") or item.get("ReturnDate")),
            "departure_display": item.get("DepartureDateTimeStrInfo") or format_datetime(item.get("DepartureDateTime")),
            "arrival_display": item.get("ArrivalDateTimeStrInfo") or format_datetime(item.get("ArrivalDateTime")),
            "departure_from_home_display": (item.get("DepartureDateTimeFromHomeStrInfo") or "").strip(),
            "pending_return_signature": pending_return,
            "time_out": item.get("TimeOut"),
            "time_out_display": format_time(item.get("TimeOut")),
            "time_in": item.get("TimeIn"),
            "time_in_display": format_time(item.get("TimeIn")),
            "reason": (item.get("Reason") or item.get("Purpose") or item.get("Remarks") or "").strip(),
            "destination": (item.get("Destination") or item.get("Place") or item.get("GoingHomePlace") or "").strip(),
            "status": status,
            "status_short": status_short,
            "status_key": status_key,
            "approved_by": nested_name(item.get("ApprovedBy") or item.get("Approver")),
            "residence_head_approval": item.get("ResidenceHeadApproval") or "",
        })

    return normalized


def _score_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    if "JS:" in text:
        text = text.split("JS:", 1)[0]
    try:
        return float(text)
    except (ValueError, TypeError):
        return value


def format_score_float(value):
    if value is None:
        return ""
    return f"{float(value):.2f}"


def format_score_pair(score, perfect):
    if score is None:
        return ""
    score_text = format_score_float(score)
    if perfect is not None:
        return f"{score_text}/{format_score_float(perfect)}"
    return score_text


def normalize_school_years(data):
    years = (data or {}).get("SchoolYearList") or []
    return [year for year in years if year]


def normalize_enrollment_classes(data):
    items = data.get("EnrollmentClassList", [])
    normalized = []

    for item in items:
        course = (item.get("Course") or item.get("Class", {}).get("Course") or {})
        class_info = item.get("Class") or {}

        total = item.get("TotalAssessmentCount") or 0
        submitted = item.get("TotalSubmittedAssessment") or 0
        pending = max(total - submitted, 0)

        normalized.append({
            "enrollment_class_id": item.get("EnrollmentClassId"),
            "class_id": item.get("ClassId") or class_info.get("ClassId"),
            "description": (item.get("Description") or "").strip(),
            "course_code": (course.get("Code") or "").strip(),
            "course_name": (course.get("Description") or course.get("Name") or "").strip(),
            "schedule": (item.get("ScheduleIdLec") or "").strip(),
            "notification_count": item.get("AssessmentNotificationCount") or 0,
            "total_submitted": submitted,
            "total_count": total,
            "pending_count": pending,
            "completed_percent": item.get("AssessmentCompletedInPercent") or "0",
        })

    return normalized


def normalize_score_entries(data):
    items = data.get("ClassStandingScoreEntryList", [])
    normalized = []

    for item in items:
        detail = item.get("ClassStandingComponentDetail") or {}
        component = detail.get("ClassStandingComponent") or {}
        category = component.get("ClassStandingComponentCategory") or {}
        grading_period = detail.get("GradingPeriod") or component.get("GradingPeriod") or {}

        perfect = _score_value(detail.get("PerfectScore"))
        score = _score_value(item.get("Score"))
        is_show_score = detail.get("IsShowScore", True)
        component_weight = _score_value(
            component.get("ComponentWeight") or detail.get("ComponentWeight")
        )

        score_display = ""
        if is_show_score and score is not None:
            score_display = format_score_pair(score, perfect)

        normalized.append({
            "id": item.get("ClassStandingScoreEntryId"),
            "description": (detail.get("Description") or "").strip(),
            "category": (category.get("Name") or category.get("Code") or "").strip(),
            "category_code": (category.get("Code") or "").strip(),
            "grading_period": (grading_period.get("Name") or grading_period.get("Code") or "").strip(),
            "grading_period_code": (grading_period.get("Code") or "").strip(),
            "grading_period_id": grading_period.get("GradingPeriodId"),
            "component_id": component.get("ClassStandingComponentId") or detail.get("ClassStandingComponentId"),
            "component_weight": component_weight,
            "perfect_score": perfect,
            "score": score,
            "score_display": score_display,
            "deadline": format_display_date(detail.get("Deadline"), detail.get("DeadlineStr")),
            "deadline_iso": iso_datetime(detail.get("Deadline")),
            "date_conducted": format_display_date(
                detail.get("DateConducted"),
                detail.get("DateConductedString"),
            ),
            "date_conducted_iso": iso_datetime(detail.get("DateConducted")),
            "is_submitted": bool(item.get("IsSubmitted")),
            "is_show_score": bool(is_show_score),
            "date_modified": format_display_datetime(
                item.get("DateModified"),
                item.get("DateModifiedStr"),
            ),
            "date_modified_iso": iso_datetime(item.get("DateModified")),
        })

    return normalized


class PisayAPI:
    def login(self, username, password):
        return logged_request(
            "POST",
            f"{BASE_URL}/user/login",
            label="login",
            json={
                "UserName": username,
                "Password": password,
            },
        )

    def get_user_info(self, token):
        return logged_request(
            "GET",
            f"{BASE_URL}/user/info",
            label="user/info",
            headers=auth_headers(token),
            force_log=True,
        )

    def get_classwall(self, token, page=1, limit=10, school_year=DEFAULT_SCHOOL_YEAR):
        return logged_request(
            "GET",
            f"{BASE_URL}/classwall/classWallDetailList",
            label="classwall",
            headers=auth_headers(token),
            params={
                "schoolYear": school_year or DEFAULT_SCHOOL_YEAR,
                "page": page,
                "limit": limit,
                "sort": "-ClassWall.PostDate",
            },
        )

    def get_school_years(self, token):
        return logged_request(
            "GET",
            f"{BASE_URL}/term/schoolYearList",
            label="school-years",
            headers=auth_headers(token),
        )

    def get_bulletin_feed(
        self,
        token,
        page=1,
        limit=5,
        *,
        is_viewing_manage=False,
        is_acknowledged=False,
    ):
        return logged_request(
            "GET",
            f"{BASE_URL}/bulletinBoard/getFeed",
            label="bulletin-board",
            headers=auth_headers(token),
            params={
                "page": page,
                "limit": limit,
                "isViewingManage": str(is_viewing_manage).lower(),
                "isAcknowledged": str(is_acknowledged).lower(),
            },
        )

    def get_leave_passes_student(self, token, page=1, limit=10):
        return logged_request(
            "GET",
            f"{BASE_URL}/studentLeavePass/getLeavePassPerStudent",
            label="leave-passes/student",
            headers=auth_headers(token),
            params={
                "page": page,
                "limit": limit,
                "sort": "-DateCreated",
            },
        )

    def get_leave_passes_parent(self, token, page=1, limit=10):
        return logged_request(
            "GET",
            f"{BASE_URL}/studentLeavePass",
            label="leave-passes/parent",
            headers=auth_headers(token),
            params={
                "page": page,
                "limit": limit,
                "sort": "-DateCreated",
                "residenceHeadApproval": "all",
                "notedBySSD": "all",
                "isShowEntryWithoutArrivalDateTime": "false",
                "isShowDeleted": "false",
                "isShowEntryWithoutDepartureDateTime": "false",
            },
        )

    def get_leave_pass(self, token, pass_id):
        return logged_request(
            "GET",
            f"{BASE_URL}/studentLeavePass/{pass_id}",
            label=f"leave-pass/get/{pass_id}",
            headers=auth_headers(token),
            force_log=True,
        )

    def update_leave_pass_guardian_status(self, token, pass_id, payload):
        return logged_request(
            "PUT",
            f"{BASE_URL}/studentLeavePass/updateStatus/{pass_id}/guardian",
            label=f"leave-pass/guardian-status/{pass_id}",
            headers={
                **auth_headers(token),
                "Content-Type": "application/json",
            },
            json=payload,
            force_log=True,
        )

    def update_leave_pass(self, token, pass_id, payload):
        return logged_request(
            "PUT",
            f"{BASE_URL}/studentLeavePass/{pass_id}",
            label=f"leave-pass/update/{pass_id}",
            headers={
                **auth_headers(token),
                "Content-Type": "application/json",
            },
            json=payload,
            force_log=True,
        )

    def get_enrollment_classes(self, token, student_id, page=1, limit=50, school_year=DEFAULT_SCHOOL_YEAR):
        return logged_request(
            "GET",
            f"{BASE_URL}/enrollmentClass/enrollmentClassListPerStudent",
            label="enrollment-classes",
            headers=auth_headers(token),
            params={
                "studentId": student_id,
                "sort": "-ClassId",
                "schoolYear": school_year or DEFAULT_SCHOOL_YEAR,
                "page": page,
                "limit": limit,
            },
        )

    def get_score_entries(self, token, student_id, enrollment_class_id, page=1, limit=100, school_year=DEFAULT_SCHOOL_YEAR):
        return logged_request(
            "GET",
            f"{BASE_URL}/classStandingScoreEntry/scoreEntryPerStudent",
            label=f"score-entries/{enrollment_class_id}",
            headers=auth_headers(token),
            params={
                "page": page,
                "limit": limit,
                "enrollmentClassId": enrollment_class_id,
                "studentId": student_id,
                "schoolYear": school_year or DEFAULT_SCHOOL_YEAR,
                "sort": "-ClassStandingComponentDetail.Deadline",
            },
        )

    def resolve_student_id(self, token):
        user = normalize_user_info(self.get_user_info(token))
        student_id = user.get("StudentId")
        if student_id:
            return student_id

        student = user.get("Student") or {}
        return student.get("StudentId")
