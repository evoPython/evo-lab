from flask import Flask, render_template, request, redirect, url_for, session, Response, stream_with_context, jsonify, flash, get_flashed_messages
from services.pisay_api import (
    PisayAPI,
    DEFAULT_SCHOOL_YEAR,
    normalize_bulletin_board,
    normalize_classwall,
    normalize_leave_passes,
    normalize_enrollment_classes,
    normalize_school_years,
    normalize_score_entries,
    sort_enrollment_classes,
)
from services.data_cache import get_page_cache, set_page_cache, delete_page_cache, delete_page_cache_prefix
from services.search import rank_posts, prepare_search_results
from services.assessments import (
    build_grading_summary,
    extract_grading_periods,
    filter_entries_by_period,
    resolve_active_period,
)
from services.accounts import is_student_username, is_parent_username
from services.request_log import get_debug_logs, clear_debug_logs, debug_enabled, log_debug_event, clear_logs_for_session
from services.leave_pass import (
    build_approve_return_payload,
    normalize_user_info,
    parse_departure_input,
    slim_leave_pass_for_update,
    unwrap_leave_pass_response,
)
from services.auth_store import (
    create_auth_session,
    delete_auth_session,
    get_auth_session,
    init_auth_table,
    update_auth_session,
)
import requests
from urllib.parse import quote
import sqlite3

PISAY_DOWNLOAD_URL = "https://pisayconnect.com/core/api/fileManager/downloadFile"
DB_PATH = "data.db"
BULLETIN_PAGE_SIZE = 5

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-this"

api = PisayAPI()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_bookmarks_table(conn):
    c = conn.cursor()
    c.execute("PRAGMA table_info(bookmarks)")
    columns = {row[1] for row in c.fetchall()}

    if "source" in columns:
        return

    c.execute("""
        CREATE TABLE bookmarks_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            post_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'classwall',
            UNIQUE(user_id, post_id, source)
        )
    """)
    c.execute("""
        INSERT INTO bookmarks_migrated (id, user_id, post_id, source)
        SELECT id, user_id, post_id, 'classwall' FROM bookmarks
    """)
    c.execute("DROP TABLE bookmarks")
    c.execute("ALTER TABLE bookmarks_migrated RENAME TO bookmarks")
    conn.commit()


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        post_id INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'classwall',
        UNIQUE(user_id, post_id, source)
    )
    """)

    migrate_bookmarks_table(conn)

    c.execute("""
    CREATE TABLE IF NOT EXISTS parent_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_username TEXT NOT NULL,
        parent_username TEXT NOT NULL,
        parent_token TEXT NOT NULL,
        linked_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(student_username, parent_username)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS page_cache (
        user_id TEXT NOT NULL,
        cache_key TEXT NOT NULL,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, cache_key)
    )
    """)

    init_auth_table(conn)

    c.execute("""
    CREATE TABLE IF NOT EXISTS archived_assessment_classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        enrollment_class_id INTEGER NOT NULL,
        archived_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(user_id, enrollment_class_id)
    )
    """)

    conn.commit()
    conn.close()


init_db()


def nocache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.after_request
def prevent_auth_page_cache(response):
    if request.endpoint == "static":
        return response
    return nocache(response)


def get_token():
    auth_id = session.get("auth_id")
    if auth_id:
        row = get_auth_session(auth_id)
        if row:
            return row["token"]
        return None
    return session.get("token")


def get_username():
    auth_id = session.get("auth_id")
    if auth_id:
        row = get_auth_session(auth_id)
        if row:
            return row["username"]
        return None
    return session.get("username")


def is_logged_in():
    return bool(get_token())


def get_bookmark_ids(username):
    return get_bookmark_ids_by_source(username)["classwall"]


def get_bookmark_ids_by_source(username):
    empty = {"classwall": set(), "bulletin": set()}
    if not username:
        return empty

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT post_id, source FROM bookmarks WHERE user_id=? ORDER BY id DESC",
        (username,),
    )
    grouped = {"classwall": set(), "bulletin": set()}
    for row in c.fetchall():
        source = row["source"] or "classwall"
        if source not in grouped:
            source = "classwall"
        grouped[source].add(row["post_id"])
    conn.close()
    return grouped


def get_bookmark_entries(username):
    if not username:
        return []

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT post_id, source FROM bookmarks WHERE user_id=? ORDER BY id DESC",
        (username,),
    )
    rows = [
        {"post_id": row["post_id"], "source": row["source"] or "classwall"}
        for row in c.fetchall()
    ]
    conn.close()
    return rows


def get_archived_assessment_ids(username):
    if not username:
        return set()

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT enrollment_class_id FROM archived_assessment_classes WHERE user_id=?",
        (username,),
    )
    archived = {row["enrollment_class_id"] for row in c.fetchall()}
    conn.close()
    return archived


def is_assessment_archived(username, enrollment_class_id):
    return enrollment_class_id in get_archived_assessment_ids(username)


def set_assessment_archived(username, enrollment_class_id, archived):
    if not username:
        return False

    conn = get_db()
    c = conn.cursor()

    if archived:
        c.execute(
            """
            INSERT OR IGNORE INTO archived_assessment_classes (user_id, enrollment_class_id)
            VALUES (?, ?)
            """,
            (username, enrollment_class_id),
        )
        status = "archived"
    else:
        c.execute(
            """
            DELETE FROM archived_assessment_classes
            WHERE user_id=? AND enrollment_class_id=?
            """,
            (username, enrollment_class_id),
        )
        status = "unarchived"

    conn.commit()
    conn.close()
    return status


def filter_assessment_classes(classes, archived_ids, *, show_archived=False):
    if not classes:
        return []

    if show_archived:
        return [
            item for item in classes
            if item.get("enrollment_class_id") in archived_ids
        ]

    return [
        item for item in classes
        if item.get("enrollment_class_id") not in archived_ids
    ]


def get_parent_accounts(student_username):
    if not student_username:
        return []

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, parent_username, linked_at
        FROM parent_accounts
        WHERE student_username=?
        ORDER BY linked_at DESC
        """,
        (student_username,),
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_parent_account(student_username, parent_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, parent_username, parent_token, linked_at
        FROM parent_accounts
        WHERE student_username=? AND id=?
        """,
        (student_username, parent_id),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_parent_token(student_username, parent_id=None):
    accounts = get_parent_accounts(student_username)
    if not accounts:
        return None, None

    if parent_id is not None:
        account = get_parent_account(student_username, parent_id)
        if account:
            return account["parent_token"], account
        return None, None

    account = get_parent_account(student_username, accounts[0]["id"])
    return account["parent_token"], account


def fetch_posts_by_ids(token, post_ids, max_pages=20, limit=50):
    """Fetch classwall pages until all bookmarked posts are found."""
    if not post_ids:
        return []

    remaining = set(post_ids)
    found = {}

    for page in range(1, max_pages + 1):
        if not remaining:
            break

        raw = api.get_classwall(token, page=page, limit=limit)
        posts = normalize_classwall(raw)

        if not posts:
            break

        for post in posts:
            if post["id"] in remaining:
                found[post["id"]] = post
                remaining.discard(post["id"])

        if len(posts) < limit:
            break

    return [found[pid] for pid in post_ids if pid in found]


def fetch_bulletins_by_ids(token, bulletin_ids, max_pages=40, limit=None):
    """Fetch bulletin pages until all bookmarked posts are found."""
    if not bulletin_ids:
        return []

    if limit is None:
        limit = BULLETIN_PAGE_SIZE

    remaining = set(bulletin_ids)
    found = {}

    for page in range(1, max_pages + 1):
        if not remaining:
            break

        raw = api.get_bulletin_feed(token, page=page, limit=limit)
        posts = normalize_bulletin_board(raw)

        if not posts:
            break

        for post in posts:
            if post["id"] in remaining:
                found[post["id"]] = post
                remaining.discard(post["id"])

        if len(posts) < limit:
            break

    return [found[bid] for bid in bulletin_ids if bid in found]


def fetch_all_bulletin_board(token, max_pages=40, limit=None):
    """Fetch multiple bulletin pages for search."""
    if limit is None:
        limit = BULLETIN_PAGE_SIZE

    all_posts = []

    for page in range(1, max_pages + 1):
        raw = api.get_bulletin_feed(token, page=page, limit=limit)
        posts = normalize_bulletin_board(raw)

        if not posts:
            break

        all_posts.extend(posts)

        if len(posts) < limit:
            break

    return all_posts


def fetch_bookmarked_items(token, bookmark_entries):
    """Return bookmarked posts in saved order, tagged with source."""
    if not bookmark_entries:
        return []

    classwall_ids = [
        entry["post_id"] for entry in bookmark_entries if entry["source"] == "classwall"
    ]
    bulletin_ids = [
        entry["post_id"] for entry in bookmark_entries if entry["source"] == "bulletin"
    ]

    classwall_map = {post["id"]: post for post in fetch_posts_by_ids(token, classwall_ids)}
    bulletin_map = {post["id"]: post for post in fetch_bulletins_by_ids(token, bulletin_ids)}

    items = []
    for entry in bookmark_entries:
        post_id = entry["post_id"]
        source = entry["source"]
        if source == "classwall" and post_id in classwall_map:
            item = dict(classwall_map[post_id])
            item["source"] = "classwall"
            item["source_label"] = "Class Wall"
            items.append(item)
        elif source == "bulletin" and post_id in bulletin_map:
            item = dict(bulletin_map[post_id])
            item["source"] = "bulletin"
            item["source_label"] = "Bulletin Board"
            items.append(item)

    return items


def fetch_all_classwall(token, max_pages=40, limit=50):
    """Fetch multiple classwall pages for search."""
    all_posts = []

    for page in range(1, max_pages + 1):
        raw = api.get_classwall(token, page=page, limit=limit)
        posts = normalize_classwall(raw)

        if not posts:
            break

        all_posts.extend(posts)

        if len(posts) < limit:
            break

    return all_posts


def fetch_all_score_entries(token, student_id, enrollment_class_id):
    all_entries = []
    for page in range(1, 21):
        raw = api.get_score_entries(
            token, student_id, enrollment_class_id, page=page, limit=100
        )
        entries = normalize_score_entries(raw)
        all_entries.extend(entries)
        if len(entries) < 100:
            break
    return all_entries


def fetch_all_enrollment_classes(token, student_id, max_pages=10, limit=50, school_year=DEFAULT_SCHOOL_YEAR):
    """Fetch all enrollment classes across API pages."""
    all_classes = []

    for page in range(1, max_pages + 1):
        raw = api.get_enrollment_classes(token, student_id, page=page, limit=limit, school_year=school_year)
        classes = normalize_enrollment_classes(raw)

        if not classes:
            break

        all_classes.extend(classes)

        if len(classes) < limit:
            break

    return sort_enrollment_classes(all_classes)


def load_enrollment_classes(token, student_id, *, school_year=DEFAULT_SCHOOL_YEAR, fetch_if_missing=True):
    cache_key = f"assessments:{school_year}"
    cached = cached_payload(cache_key)

    if cached is not None:
        return cached["data"], cached.get("error")

    if not fetch_if_missing:
        return None, None

    classes = fetch_all_enrollment_classes(token, student_id, school_year=school_year)
    store_payload(cache_key, classes)
    return classes, None


def load_archived_assessment_classes(token, student_id, username, *, school_year=DEFAULT_SCHOOL_YEAR, fetch_if_missing=True):
    cache_key = f"assessments:archived:{school_year}"
    cached = cached_payload(cache_key)

    if cached is not None:
        return cached["data"], cached.get("error")

    all_classes, error = load_enrollment_classes(
        token,
        student_id,
        school_year=school_year,
        fetch_if_missing=fetch_if_missing,
    )
    if all_classes is None:
        return None, error

    archived_ids = get_archived_assessment_ids(username)
    classes = filter_assessment_classes(all_classes, archived_ids, show_archived=True)

    if fetch_if_missing:
        store_payload(cache_key, classes)

    return classes, error


def load_school_years(token, *, fetch_if_missing=True):
    """Fetch (and cache) the list of school years available from PisayConnect.

    This is a single lightweight API call, so we always fetch it eagerly
    (even on preload passes) rather than deferring to fetch_if_missing —
    otherwise preloaded/background-refreshed views end up stuck showing
    only the fallback default year.
    """
    cache_key = "school_years"
    cached = cached_payload(cache_key)

    if cached is not None:
        return cached["data"]

    try:
        raw = api.get_school_years(token)
        years = normalize_school_years(raw)
    except Exception:
        years = []

    if not years:
        years = [DEFAULT_SCHOOL_YEAR]

    store_payload(cache_key, years)
    return years


def get_preferred_school_year():
    return session.get("preferred_school_year")


def set_preferred_school_year(value):
    if value and session.get("preferred_school_year") != value:
        session["preferred_school_year"] = value
        session.modified = True


def resolve_school_year(requested, school_years):
    """Pick the requested year, else the last one the user picked, else the most recent."""
    school_years = school_years or [DEFAULT_SCHOOL_YEAR]

    if requested and requested in school_years:
        set_preferred_school_year(requested)
        return requested

    preferred = get_preferred_school_year()
    if preferred and preferred in school_years:
        return preferred

    return school_years[0]


def cached_payload(cache_key):
    return get_page_cache(cache_key)


def store_payload(cache_key, data, has_next=False, **extra):
    payload = {"data": data, "has_next": has_next, **extra}
    set_page_cache(cache_key, payload)
    return payload


def guess_mime(filename):
    if not filename:
        return None

    ext = filename.lower().split(".")[-1]

    return {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
    }.get(ext)


def cache_leave_passes(raw):
    cache = dict(session.get("_leave_pass_cache", {}))
    for item in raw.get("StudentLeavePassList", []):
        pass_id = item.get("StudentLeavePassId")
        if pass_id is not None:
            cache[str(pass_id)] = slim_leave_pass_for_update(item)
    session["_leave_pass_cache"] = cache
    session.modified = True


def get_student_id(token=None):
    auth_id = session.get("auth_id")
    if auth_id:
        row = get_auth_session(auth_id)
        if row and row.get("student_id"):
            return row["student_id"]

    cached = session.get("student_id")
    if cached:
        return cached

    token = token or get_token()
    if not token:
        return None

    student_id = api.resolve_student_id(token)
    if student_id:
        if auth_id:
            update_auth_session(auth_id, student_id=student_id)
        else:
            session["student_id"] = student_id
            session.modified = True
    return student_id


def get_raw_leave_pass(pass_id, parent_token, *, fresh=False):
    if not fresh:
        cache = session.get("_leave_pass_cache", {})
        cached = cache.get(str(pass_id))
        if cached:
            log_debug_event(
                "approve-return/cache-hit",
                {"pass_id": pass_id, "cached_keys": sorted(cached.keys())},
                force=True,
            )
            return cached

    log_debug_event(
        "approve-return/fetch-pass" if fresh else "approve-return/cache-miss",
        {"pass_id": pass_id, "fresh": fresh},
        force=True,
    )
    data = api.get_leave_pass(parent_token, pass_id)
    unwrapped = unwrap_leave_pass_response(data)
    if unwrapped.get("StudentLeavePassId"):
        return slim_leave_pass_for_update(unwrapped)
    return unwrapped


SPA_PRELOAD_ROUTES = (
    {"view": "bulletin_board", "page": 1},
    {"view": "dashboard"},
    {"view": "classwall", "page": 1},
    {"view": "bookmarks"},
    {"view": "assessments"},
    {"view": "leave_passes", "mode": "student", "page": 1},
    {"view": "parent_add"},
)

def spa_route_key(route):
    parts = [route["view"]]
    for key in ("page", "mode", "parent", "enrollment_class_id", "period", "linked", "archived", "school_year"):
        value = route.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    return ":".join(parts)


def parse_spa_path(subpath, args):
    subpath = (subpath or "").strip("/")

    if not subpath or subpath == "dashboard":
        return {"view": "dashboard"}

    if subpath == "classwall":
        route = {"view": "classwall", "page": int(args.get("page", 1))}
        if args.get("schoolYear"):
            route["school_year"] = args.get("schoolYear")
        return route

    if subpath == "bulletin-board":
        return {"view": "bulletin_board", "page": int(args.get("page", 1))}

    if subpath == "bookmarks":
        return {"view": "bookmarks"}

    if subpath == "assessments":
        route = {"view": "assessments"}
        if args.get("archived") in ("1", "true", "yes"):
            route["archived"] = True
        if args.get("schoolYear"):
            route["school_year"] = args.get("schoolYear")
        return route

    if subpath.startswith("assessments/"):
        class_id = subpath.split("/", 1)[1]
        if class_id.isdigit():
            period = args.get("period", type=int)
            route = {
                "view": "assessment_detail",
                "enrollment_class_id": int(class_id),
            }
            if period is not None:
                route["period"] = period
            return route

    if subpath == "leave-passes":
        mode = args.get("mode", "student")
        if mode not in ("student", "parent"):
            mode = "student"
        parent = args.get("parent", type=int)
        route = {
            "view": "leave_passes",
            "mode": mode,
            "page": int(args.get("page", 1)),
        }
        if parent:
            route["parent"] = parent
        if args.get("linked"):
            route["linked"] = args.get("linked")
        return route

    if subpath == "parent/add":
        return {"view": "parent_add"}

    return {"view": "dashboard"}


def render_spa_view_html(view_name, **context):
    context.setdefault("view", view_name)
    return render_template(f"partials/views/{view_name}.html", **context)


def build_view_context(route, *, fetch_if_missing=True):
    token = get_token()
    username = get_username()
    view = route["view"]

    if view == "bulletin_board":
        page = route.get("page", 1)
        cache_key = f"bulletin_board:{page}"
        cached = cached_payload(cache_key)

        if cached is not None:
            bulletins = cached["data"]
            has_next = cached.get("has_next", False)
            error = cached.get("error")
        elif fetch_if_missing:
            raw = api.get_bulletin_feed(token, page=page, limit=BULLETIN_PAGE_SIZE)
            bulletins = normalize_bulletin_board(raw)
            has_next = len(bulletins) == BULLETIN_PAGE_SIZE
            store_payload(cache_key, bulletins, has_next=has_next)
            error = None
        else:
            bulletins, has_next, error = None, False, None

        return {
            "view": "bulletin_board",
            "data": bulletins,
            "error": error,
            "page": page,
            "has_next": has_next,
            "cache_refresh_url": url_for("api_cache_bulletin_board", page=page),
        }

    if view == "dashboard":
        return {
            "view": "dashboard",
            "data": None,
            "error": None,
            "cache_refresh_url": None,
        }

    if view == "classwall":
        page = route.get("page", 1)
        school_years = load_school_years(token, fetch_if_missing=fetch_if_missing)
        school_year = resolve_school_year(route.get("school_year"), school_years)
        cache_key = f"classwall:{school_year}:{page}"
        cached = cached_payload(cache_key)

        if cached is not None:
            classwall = cached["data"]
            has_next = cached.get("has_next", False)
            error = cached.get("error")
        elif fetch_if_missing:
            classwall_raw = api.get_classwall(token, page=page, limit=10, school_year=school_year)
            classwall = normalize_classwall(classwall_raw)
            has_next = len(classwall) == 10
            store_payload(cache_key, classwall, has_next=has_next)
            error = None
        else:
            classwall, has_next, error = None, False, None

        return {
            "view": "classwall",
            "data": classwall,
            "error": error,
            "page": page,
            "has_next": has_next,
            "school_years": school_years or [school_year],
            "selected_school_year": school_year,
            "cache_refresh_url": url_for("api_cache_classwall", page=page, schoolYear=school_year),
        }

    if view == "bookmarks":
        cache_key = "bookmarks"
        bookmark_entries = get_bookmark_entries(username)

        cached = cached_payload(cache_key)
        if cached is not None:
            bookmarked = cached["data"]
            error = cached.get("error")
        elif fetch_if_missing:
            bookmarked = fetch_bookmarked_items(token, bookmark_entries)
            store_payload(cache_key, bookmarked, bookmark_entries=bookmark_entries)
            error = None
        else:
            bookmarked, error = None, None

        return {
            "view": "bookmarks",
            "data": bookmarked,
            "error": error,
            "cache_refresh_url": url_for("api_cache_bookmarks"),
        }

    if view == "assessments":
        show_archived = bool(route.get("archived"))
        archived_ids = get_archived_assessment_ids(username)

        student_id = get_student_id(token)
        school_years = load_school_years(token, fetch_if_missing=fetch_if_missing)
        school_year = resolve_school_year(route.get("school_year"), school_years)

        if not student_id:
            return {
                "view": "assessments",
                "data": None,
                "error": "Could not determine your student ID from PisayConnect.",
                "show_archived": show_archived,
                "has_archived": bool(archived_ids),
                "school_years": school_years or [school_year],
                "selected_school_year": school_year,
                "cache_refresh_url": url_for(
                    "api_cache_assessments",
                    archived=int(show_archived),
                    schoolYear=school_year,
                ),
            }

        if show_archived:
            classes, error = load_archived_assessment_classes(
                token,
                student_id,
                username,
                school_year=school_year,
                fetch_if_missing=fetch_if_missing,
            )
        else:
            all_classes, error = load_enrollment_classes(
                token,
                student_id,
                school_year=school_year,
                fetch_if_missing=fetch_if_missing,
            )
            classes = (
                filter_assessment_classes(all_classes, archived_ids)
                if all_classes is not None
                else None
            )

        return {
            "view": "assessments",
            "data": classes,
            "error": error,
            "show_archived": show_archived,
            "has_archived": bool(archived_ids),
            "school_years": school_years or [school_year],
            "selected_school_year": school_year,
            "cache_refresh_url": url_for(
                "api_cache_assessments",
                archived=int(show_archived),
                schoolYear=school_year,
            ),
        }

    if view == "assessment_detail":
        enrollment_class_id = route["enrollment_class_id"]
        requested_period = route.get("period")
        cache_key = f"assessment_detail:{enrollment_class_id}"
        cached = cached_payload(cache_key)

        if cached is None and not fetch_if_missing:
            return {
                "view": "assessment_detail",
                "data": None,
                "class_info": None,
                "grading_summary": None,
                "grading_periods": None,
                "period": requested_period,
                "error": None,
                "enrollment_class_id": enrollment_class_id,
                "is_archived": is_assessment_archived(username, enrollment_class_id),
                "cache_refresh_url": url_for(
                    "api_cache_assessment_detail",
                    enrollment_class_id=enrollment_class_id,
                    period=requested_period,
                ),
            }

        student_id = get_student_id(token)
        if not student_id:
            return {
                "view": "assessment_detail",
                "data": None,
                "class_info": None,
                "grading_summary": None,
                "grading_periods": None,
                "period": requested_period,
                "error": "Could not determine your student ID from PisayConnect.",
                "enrollment_class_id": enrollment_class_id,
                "is_archived": is_assessment_archived(username, enrollment_class_id),
                "cache_refresh_url": url_for(
                    "api_cache_assessment_detail",
                    enrollment_class_id=enrollment_class_id,
                    period=requested_period,
                ),
            }

        if cached is not None:
            all_entries = cached["data"]
            class_info = cached.get("class_info")
            grading_summary = cached.get("grading_summary")
            error = cached.get("error")
        elif fetch_if_missing:
            classes_raw = api.get_enrollment_classes(token, student_id, page=1, limit=100)
            classes = normalize_enrollment_classes(classes_raw)
            class_info = next(
                (c for c in classes if c["enrollment_class_id"] == enrollment_class_id),
                None,
            )

            all_entries = fetch_all_score_entries(token, student_id, enrollment_class_id)
            grading_summary = build_grading_summary(all_entries)

            store_payload(
                cache_key,
                all_entries,
                class_info=class_info,
                grading_summary=grading_summary,
            )
            error = None
        else:
            all_entries, class_info, grading_summary, error = None, None, None, None

        grading_periods = extract_grading_periods(all_entries or [])
        active_period = resolve_active_period(grading_periods, requested_period)
        entries = filter_entries_by_period(all_entries or [], active_period)

        return {
            "view": "assessment_detail",
            "data": entries,
            "class_info": class_info,
            "grading_summary": grading_summary,
            "grading_periods": grading_periods,
            "period": active_period,
            "error": error,
            "enrollment_class_id": enrollment_class_id,
            "is_archived": is_assessment_archived(username, enrollment_class_id),
            "cache_refresh_url": url_for(
                "api_cache_assessment_detail",
                enrollment_class_id=enrollment_class_id,
                period=active_period,
            ),
        }

    if view == "leave_passes":
        mode = route.get("mode", "student")
        page = route.get("page", 1)
        linked = route.get("linked")
        parent_accounts = get_parent_accounts(username)
        parent_id = route.get("parent")
        active_parent = None
        auth_token = token

        if mode == "parent" and not parent_accounts:
            return {
                "view": "leave_passes",
                "data": None,
                "error": None,
                "page": page,
                "has_next": False,
                "parent_accounts": parent_accounts,
                "active_parent": None,
                "needs_parent": True,
                "linked": linked,
                "mode": mode,
                "cache_refresh_url": None,
            }

        if mode == "parent":
            parent_token, active_parent = get_parent_token(username, parent_id)
            if not parent_token:
                return {
                    "view": "leave_passes",
                    "data": None,
                    "error": "Selected parent account was not found.",
                    "page": page,
                    "has_next": False,
                    "parent_accounts": parent_accounts,
                    "active_parent": None,
                    "mode": mode,
                    "cache_refresh_url": None,
                }
            auth_token = parent_token

        parent_key = active_parent["id"] if active_parent else ""
        cache_key = f"leave_passes:{mode}:{parent_key}:{page}"
        cached = cached_payload(cache_key)

        if cached is not None:
            passes = cached["data"]
            has_next = cached.get("has_next", False)
            error = cached.get("error")
        elif fetch_if_missing:
            if mode == "student":
                raw = api.get_leave_passes_student(auth_token, page=page, limit=10)
            else:
                raw = api.get_leave_passes_parent(auth_token, page=page, limit=10)
                cache_leave_passes(raw)

            passes = normalize_leave_passes(raw)
            has_next = len(passes) == 10
            store_payload(cache_key, passes, has_next=has_next)
            error = None
        else:
            passes, has_next, error = None, False, None

        return {
            "view": "leave_passes",
            "data": passes,
            "error": error,
            "page": page,
            "has_next": has_next,
            "parent_accounts": parent_accounts,
            "active_parent": active_parent,
            "linked": linked,
            "mode": mode,
            "cache_refresh_url": url_for(
                "api_cache_leave_passes",
                mode=mode,
                page=page,
                parent=active_parent["id"] if active_parent else None,
            ),
        }

    if view == "parent_add":
        return {
            "view": "parent_add",
            "parent_accounts": get_parent_accounts(username),
        }

    return {"view": "dashboard", "data": None, "error": None, "cache_refresh_url": None}


def spa_view_title(context):
    view = context.get("view")
    if view == "bulletin_board":
        return "Bulletin Board · PisayConnect"
    if view == "dashboard":
        return "Dashboard · PisayConnect"
    if view == "classwall":
        return "Class Wall · PisayConnect"
    if view == "bookmarks":
        return "Bookmarks · PisayConnect"
    if view == "assessments":
        return "Archived Classes · Assessments · PisayConnect" if context.get("show_archived") else "Assessments · PisayConnect"
    if view == "assessment_detail":
        class_info = context.get("class_info") or {}
        label = class_info.get("course_code") or class_info.get("description") or "Subject"
        return f"{label} · Assessments · PisayConnect"
    if view == "leave_passes":
        return "Leave Passes · PisayConnect"
    if view == "parent_add":
        return "Add Parent Account · PisayConnect"
    return "PisayConnect"


@app.context_processor
def inject_account_context():
    username = get_username()
    logged_in = is_logged_in()
    logs = get_debug_logs()
    show_debug = debug_enabled()
    return {
        "is_student": logged_in,
        "parent_accounts": get_parent_accounts(username) if logged_in and username else [],
        "username": username,
        "bookmark_ids_by_source": get_bookmark_ids_by_source(username) if logged_in and username else {"classwall": set(), "bulletin": set()},
        "debug_mode": show_debug,
        "debug_logs": logs if show_debug else [],
        "flashed_messages": get_flashed_messages(with_categories=True),
    }


@app.route("/")
def index():
    if is_logged_in():
        return redirect("/app/dashboard")
    return render_template("index.html", data=None, error=None, view="login")


@app.route("/app")
@app.route("/app/<path:subpath>")
def app_shell(subpath=None):
    token = get_token()
    if not token:
        return redirect(url_for("index"))

    active_route = parse_spa_path(subpath, request.args)
    active_route_key = spa_route_key(active_route)

    preloaded_views = {}
    preloaded_routes = []

    for route in SPA_PRELOAD_ROUTES:
        key = spa_route_key(route)
        preloaded_routes.append(key)
        try:
            ctx = build_view_context(route, fetch_if_missing=False)
            preloaded_views[key] = render_spa_view_html(route["view"], **ctx)
        except Exception:
            preloaded_views[key] = '<div class="card"><p class="card-subtitle">Loading…</p></div>'

    try:
        active_ctx = build_view_context(active_route, fetch_if_missing=True)
        active_html = render_spa_view_html(active_route["view"], **active_ctx)
    except Exception as exc:
        active_ctx = {
            "view": active_route["view"],
            "error": str(exc),
            "data": None,
            "page": active_route.get("page", 1),
            "has_next": False,
            "cache_refresh_url": None,
        }
        active_html = f'<div class="alert alert-error">{exc}</div>'
    preloaded_views[active_route_key] = active_html
    if active_route_key not in preloaded_routes:
        preloaded_routes.append(active_route_key)

    return render_template(
        "app_shell.html",
        view=active_route["view"],
        active_route=active_route,
        active_route_key=active_route_key,
        preloaded_views=preloaded_views,
        preloaded_routes=preloaded_routes,
    )


@app.route("/api/view/<view_name>")
def api_view(view_name):
    token = get_token()
    if not token:
        return jsonify({"error": "unauthorized"}), 401

    route = {"view": view_name}
    if view_name == "bulletin_board":
        route["page"] = int(request.args.get("page", 1))
    elif view_name == "dashboard":
        pass
    elif view_name == "classwall":
        route["page"] = int(request.args.get("page", 1))
        if request.args.get("schoolYear"):
            route["school_year"] = request.args.get("schoolYear")
    elif view_name == "assessments":
        if request.args.get("archived") in ("1", "true", "yes"):
            route["archived"] = True
        if request.args.get("schoolYear"):
            route["school_year"] = request.args.get("schoolYear")
    elif view_name == "assessment_detail":
        route["enrollment_class_id"] = request.args.get("enrollment_class_id", type=int)
        period = request.args.get("period", type=int)
        if period is not None:
            route["period"] = period
        if not route["enrollment_class_id"]:
            return jsonify({"error": "Missing enrollment_class_id."}), 400
    elif view_name == "leave_passes":
        route["mode"] = request.args.get("mode", "student")
        route["page"] = int(request.args.get("page", 1))
        parent = request.args.get("parent", type=int)
        if parent:
            route["parent"] = parent
        if request.args.get("linked"):
            route["linked"] = request.args.get("linked")
    elif view_name == "parent_add":
        pass
    else:
        return jsonify({"error": "Unknown view."}), 404

    ctx = build_view_context(route, fetch_if_missing=True)
    html = render_spa_view_html(view_name, **ctx)

    return jsonify({
        "html": html,
        "view": view_name,
        "title": spa_view_title(ctx),
        "route_key": spa_route_key(route),
        "search_scope": (
            "bookmarks"
            if view_name == "bookmarks"
            else "bulletin_board"
            if view_name == "bulletin_board"
            else "classwall"
            if view_name == "classwall"
            else "all"
        ),
        "cache_refresh_url": ctx.get("cache_refresh_url"),
    })


@app.route("/dashboard")
def dashboard():
    return redirect("/app/dashboard")


@app.route("/classwall")
def classwall():
    if not is_logged_in():
        return redirect(url_for("index"))

    page = int(request.args.get("page", 1))
    query = f"?page={page}" if page > 1 else ""
    return redirect(f"/app/classwall{query}")


@app.route("/bulletin-board")
def bulletin_board():
    if not is_logged_in():
        return redirect(url_for("index"))

    page = int(request.args.get("page", 1))
    query = f"?page={page}" if page > 1 else ""
    return redirect(f"/app/bulletin-board{query}")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if is_parent_username(username):
        return render_template(
            "index.html",
            data=None,
            error="Sign in with your student account. You can link a parent account after logging in.",
            view="login",
        )

    try:
        result = api.login(username, password)
        token = result.get("Token")

        if not token:
            return render_template("index.html", data=None, error="Login failed", view="login")

        student_id = None
        try:
            student_id = api.resolve_student_id(token)
        except Exception:
            pass

        old_auth_id = session.get("auth_id")
        session.clear()
        if old_auth_id:
            delete_auth_session(old_auth_id)
            clear_logs_for_session(old_auth_id)

        auth_id = create_auth_session(
            token,
            username,
            student_id=student_id,
            account_type="student",
        )
        session["auth_id"] = auth_id
        session.modified = True

        return redirect("/app/dashboard", code=303)

    except Exception as e:
        return render_template("index.html", data=None, error=str(e), view="login")


@app.route("/parent/add", methods=["GET", "POST"])
def add_parent():
    username = get_username()
    token = get_token()

    if not token or not get_username():
        return redirect(url_for("index"))

    if request.method == "GET":
        return redirect("/app/parent/add")

    error = None

    if request.method == "POST":
        parent_username = (request.form.get("parent_username") or "").strip()
        parent_password = request.form.get("parent_password") or ""

        if not is_parent_username(parent_username):
            error = "Parent usernames are numeric (e.g. guardian ID)."
        elif not parent_password:
            error = "Password is required."
        else:
            try:
                result = api.login(parent_username, parent_password)
                parent_token = result.get("Token")

                if not parent_token:
                    error = "Parent login failed. Check credentials."
                else:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute(
                        """
                        INSERT INTO parent_accounts (student_username, parent_username, parent_token)
                        VALUES (?, ?, ?)
                        ON CONFLICT(student_username, parent_username) DO UPDATE SET
                            parent_token=excluded.parent_token,
                            linked_at=datetime('now')
                        """,
                        (username, parent_username, parent_token),
                    )
                    conn.commit()
                    conn.close()
                    success = f"Linked parent account {parent_username}."
                    return redirect("/app/leave-passes?mode=parent&linked=1")

            except Exception as e:
                error = str(e)

    if error:
        flash(error, "error")
    return redirect("/app/parent/add")


@app.route("/parent/<int:parent_id>/remove", methods=["POST"])
def remove_parent(parent_id):
    username = get_username()

    if not is_logged_in() or not get_username():
        return redirect(url_for("index"))

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "DELETE FROM parent_accounts WHERE id=? AND student_username=?",
        (parent_id, username),
    )
    conn.commit()
    conn.close()

    next_url = request.form.get("next") or url_for("leave_passes")
    return redirect(next_url)


@app.route("/leave-passes")
def leave_passes():
    if not is_logged_in():
        return redirect(url_for("index"))

    params = request.args.to_dict(flat=True)
    query = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
    return redirect(f"/app/leave-passes{'?' + query if query else ''}")


@app.route("/leave-passes/<int:pass_id>/approve-return", methods=["POST"])
def approve_return(pass_id):
    username = get_username()

    if not is_logged_in() or not username:
        return redirect(url_for("index"))

    parent_id = request.form.get("parent_id", type=int)
    departure_datetime = request.form.get("departure_datetime", "")
    page = request.form.get("page", 1, type=int)

    log_debug_event(
        "approve-return/start",
        {
            "pass_id": pass_id,
            "parent_id": parent_id,
            "departure_datetime": departure_datetime,
            "student_username": username,
        },
        force=True,
    )

    parent_token, active_parent = get_parent_token(username, parent_id)
    if not parent_token:
        flash("Parent account not found.", "error")
        return redirect(f"/app/leave-passes?mode=parent&page={page}")

    try:
        raw_pass = get_raw_leave_pass(pass_id, parent_token, fresh=True)
        if not isinstance(raw_pass, dict) or not raw_pass.get("StudentLeavePassId"):
            raise ValueError(f"Could not load leave pass #{pass_id} from PisayConnect.")

        log_debug_event(
            "approve-return/loaded-pass",
            {
                "pass_id": pass_id,
                "DepartureDateTimeFromHomeStrInfo": raw_pass.get("DepartureDateTimeFromHomeStrInfo"),
                "DepartureDateTime": raw_pass.get("DepartureDateTime"),
                "ArrivalDateTime": raw_pass.get("ArrivalDateTime"),
                "ArrivalDateTimeStrInfo": raw_pass.get("ArrivalDateTimeStrInfo"),
                "GoingHomeDate": raw_pass.get("GoingHomeDate"),
                "ResidenceHeadApproval": raw_pass.get("ResidenceHeadApproval"),
            },
            force=True,
        )

        departure_dt = parse_departure_input(departure_datetime)
        parent_user_info = normalize_user_info(api.get_user_info(parent_token))
        payload = build_approve_return_payload(raw_pass, departure_dt, parent_user_info)

        api.update_leave_pass_guardian_status(parent_token, pass_id, payload)
        api.update_leave_pass(parent_token, pass_id, payload)
        fresh_pass = unwrap_leave_pass_response(api.get_leave_pass(parent_token, pass_id))

        log_debug_event(
            "approve-return/success",
            {
                "pass_id": pass_id,
                "DepartureDateTimeFromHomeStrInfo": fresh_pass.get("DepartureDateTimeFromHomeStrInfo"),
                "ArrivalDateTime": fresh_pass.get("ArrivalDateTime"),
                "ArrivalDateTimeStrInfo": fresh_pass.get("ArrivalDateTimeStrInfo"),
                "IsAttachGuardianSignature": fresh_pass.get("IsAttachGuardianSignature"),
                "AttachGuardianSignatureModifiedById": fresh_pass.get("AttachGuardianSignatureModifiedById"),
            },
            force=True,
        )

        cache = dict(session.get("_leave_pass_cache", {}))
        if fresh_pass.get("StudentLeavePassId"):
            cache[str(pass_id)] = slim_leave_pass_for_update(fresh_pass)
        else:
            cache[str(pass_id)] = payload
        session["_leave_pass_cache"] = cache
        session.modified = True

        flash(f"Return slip approved for pass #{pass_id}.", "success")

    except Exception as exc:
        log_debug_event(
            "approve-return/failed",
            {"pass_id": pass_id, "error": str(exc), "departure_datetime": departure_datetime},
            force=True,
        )
        flash(f"Approve return failed: {exc}", "error")

    redirect_parent = active_parent["id"] if active_parent else parent_id
    return redirect(f"/app/leave-passes?mode=parent&parent={redirect_parent}&page={page}")


@app.route("/assessments")
def assessments():
    if not is_logged_in():
        return redirect(url_for("index"))

    return redirect("/app/assessments")


@app.route("/assessments/<int:enrollment_class_id>")
def assessment_detail(enrollment_class_id):
    if not is_logged_in():
        return redirect(url_for("index"))

    period = request.args.get("period")
    query = f"?period={period}" if period else ""
    return redirect(f"/app/assessments/{enrollment_class_id}{query}")


@app.route("/settings/debug", methods=["POST"])
def toggle_debug():
    if not is_logged_in():
        return redirect(url_for("index"))

    auth_id = session.get("auth_id")
    row = get_auth_session(auth_id) if auth_id else None
    enabled = not bool(row.get("debug_mode") if row else session.get("debug_mode", False))

    if auth_id:
        update_auth_session(auth_id, debug_mode=int(enabled))
    session["debug_mode"] = enabled
    session.modified = True
    if not enabled:
        clear_debug_logs()

    next_url = request.form.get("next") or request.referrer or "/app/dashboard"
    return redirect(next_url)


@app.route("/settings/debug/clear", methods=["POST"])
def clear_debug():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401

    clear_debug_logs()
    next_url = request.form.get("next") or request.referrer or "/app/dashboard"
    return redirect(next_url)


@app.route("/api/debug/logs")
def api_debug_logs():
    if not is_logged_in():
        return jsonify({"error": "unauthorized"}), 401

    if not debug_enabled():
        return jsonify({"enabled": False, "logs": []})

    return jsonify({"enabled": True, "logs": get_debug_logs()})


@app.route("/download/<int:file_id>")
def download(file_id):
    token = get_token()

    if not token:
        return redirect(url_for("index"))

    classwall_data = api.get_classwall(token)

    file_token = None
    filename = None
    content_type = None

    for wall in classwall_data.get("ClassWallDetailList", []):
        files = wall.get("ClassWall", {}).get("ClassWallFileList", [])

        for f in files:
            if f.get("FileId") == file_id:
                file_info = f.get("File", {})
                file_token = file_info.get("Token")
                filename = file_info.get("Name") or file_info.get("FileName")
                content_type = guess_mime(filename)
                break

        if file_token:
            break

    if not file_token:
        return "File not found", 404

    safe_token = quote(file_token, safe="")
    url = f"{PISAY_DOWNLOAD_URL}/{file_id}/{safe_token}"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Token": token,
        "Referer": "https://pisayconnect.com/portal/",
        "Accept": "*/*",
    }

    r = requests.get(url, headers=headers, stream=True, allow_redirects=True)

    if r.status_code != 200:
        return f"Download failed: {r.status_code}", 400

    response = Response(
        stream_with_context(r.iter_content(chunk_size=8192)),
        status=200,
    )

    response.headers["Content-Type"] = r.headers.get(
        "Content-Type", content_type or "application/octet-stream"
    )

    if filename:
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@app.route("/bookmark/<int:post_id>", methods=["POST"])
def bookmark_legacy(post_id):
    return toggle_bookmark(post_id, "classwall")


@app.route("/bookmark/<source>/<int:post_id>", methods=["POST"])
def bookmark_with_source(source, post_id):
    if source not in ("classwall", "bulletin"):
        return jsonify({"error": "Invalid bookmark source."}), 400
    return toggle_bookmark(post_id, source)


def toggle_bookmark(post_id, source):
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT id FROM bookmarks WHERE user_id=? AND post_id=? AND source=?",
        (username, post_id, source),
    )
    row = c.fetchone()

    if row:
        c.execute(
            "DELETE FROM bookmarks WHERE user_id=? AND post_id=? AND source=?",
            (username, post_id, source),
        )
        status = "removed"
    else:
        c.execute(
            "INSERT INTO bookmarks (user_id, post_id, source) VALUES (?, ?, ?)",
            (username, post_id, source),
        )
        status = "added"

    conn.commit()
    conn.close()

    delete_page_cache("bookmarks")

    return jsonify({"status": status, "post_id": post_id, "source": source})


@app.route("/bookmarks")
def bookmarks():
    if not is_logged_in():
        return redirect(url_for("index"))
    return redirect("/app/bookmarks")


@app.route("/api/search")
def api_search():
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    query = request.args.get("q", "").strip()
    scope = request.args.get("scope", "all")

    if not query:
        return jsonify({"html": "", "count": 0, "query": query})

    try:
        if scope == "bookmarks":
            bookmarked = fetch_bookmarked_items(token, get_bookmark_entries(username))
            posts = bookmarked
        elif scope == "bulletin_board":
            posts = fetch_all_bulletin_board(token)
        elif scope == "classwall":
            posts = fetch_all_classwall(token)
        else:
            posts = fetch_all_classwall(token)

        results = rank_posts(posts, query)
        display_posts = prepare_search_results(results, query)

        if display_posts:
            if scope == "bulletin_board":
                html = render_template(
                    "partials/bulletin_list.html",
                    data=display_posts,
                )
            elif scope == "bookmarks":
                html = render_template(
                    "partials/bookmark_list.html",
                    data=display_posts,
                )
            else:
                html = render_template(
                    "partials/post_list.html",
                    data=display_posts,
                )
        else:
            html = ""

        return jsonify({
            "html": html,
            "count": len(results),
            "query": query,
            "scope": scope,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/bulletin-board")
def api_cache_bulletin_board():
    token = get_token()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    page = int(request.args.get("page", 1))
    cache_key = f"bulletin_board:{page}"

    try:
        raw = api.get_bulletin_feed(token, page=page, limit=BULLETIN_PAGE_SIZE)
        bulletins = normalize_bulletin_board(raw)
        has_next = len(bulletins) == BULLETIN_PAGE_SIZE
        store_payload(cache_key, bulletins, has_next=has_next)

        if bulletins:
            html = (
                '<div class="post-list">'
                + render_template("partials/bulletin_list.html", data=bulletins)
                + "</div>"
            )
        else:
            html = '<div class="empty-state"><p>No bulletin posts on this page.</p></div>'

        return jsonify({"html": html, "has_next": has_next, "target": "bulletin-list"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/classwall")
def api_cache_classwall():
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    page = int(request.args.get("page", 1))
    school_years = load_school_years(token, fetch_if_missing=False)
    school_year = resolve_school_year(request.args.get("schoolYear"), school_years)
    cache_key = f"classwall:{school_year}:{page}"
    bookmark_ids_by_source = get_bookmark_ids_by_source(username)

    try:
        classwall_raw = api.get_classwall(token, page=page, limit=10, school_year=school_year)
        classwall = normalize_classwall(classwall_raw)
        has_next = len(classwall) == 10
        store_payload(cache_key, classwall, has_next=has_next)

        if classwall:
            html = (
                '<div class="post-list">'
                + render_template("partials/post_list.html", data=classwall)
                + "</div>"
            )
        else:
            html = render_template("partials/empty_posts.html", view="classwall")

        return jsonify({"html": html, "has_next": has_next, "target": "post-list"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/bookmarks")
def api_cache_bookmarks():
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    bookmark_entries = get_bookmark_entries(username)
    cache_key = "bookmarks"

    try:
        bookmarked = fetch_bookmarked_items(token, bookmark_entries)
        store_payload(cache_key, bookmarked, bookmark_entries=bookmark_entries)

        if bookmarked:
            html = (
                '<div class="post-list">'
                + render_template("partials/bookmark_list.html", data=bookmarked)
                + "</div>"
            )
        else:
            html = render_template("partials/empty_posts.html", view="bookmarks")

        return jsonify({"html": html, "target": "post-list"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/leave-passes")
def api_cache_leave_passes():
    username = get_username()
    token = get_token()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    mode = request.args.get("mode", "student")
    if mode not in ("student", "parent"):
        mode = "student"

    parent_id = request.args.get("parent", type=int)
    page = int(request.args.get("page", 1))

    auth_token = token
    active_parent = None

    if mode == "parent":
        parent_token, active_parent = get_parent_token(username, parent_id)
        if not parent_token:
            return jsonify({"error": "Parent account not found."}), 404
        auth_token = parent_token

    parent_key = active_parent["id"] if active_parent else ""
    cache_key = f"leave_passes:{mode}:{parent_key}:{page}"

    try:
        if mode == "student":
            raw = api.get_leave_passes_student(auth_token, page=page, limit=10)
        else:
            raw = api.get_leave_passes_parent(auth_token, page=page, limit=10)
            cache_leave_passes(raw)

        passes = normalize_leave_passes(raw)
        has_next = len(passes) == 10
        store_payload(cache_key, passes, has_next=has_next)

        if passes:
            html = render_template(
                "partials/leave_pass_list.html",
                data=passes,
                mode=mode,
                active_parent=active_parent,
                page=page,
            )
        else:
            html = "<div class=\"empty-state\"><p>No leave passes on this page.</p></div>"

        return jsonify({"html": html, "has_next": has_next, "target": "leave-pass-list"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/assessments")
def api_cache_assessments():
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    show_archived = request.args.get("archived") in ("1", "true", "yes")
    archived_ids = get_archived_assessment_ids(username)
    school_years = load_school_years(token, fetch_if_missing=False)
    school_year = resolve_school_year(request.args.get("schoolYear"), school_years)

    student_id = get_student_id(token)
    if not student_id:
        return jsonify({"error": "Could not determine student ID."}), 400

    try:
        if show_archived:
            classes, _error = load_archived_assessment_classes(
                token,
                student_id,
                username,
                school_year=school_year,
                fetch_if_missing=True,
            )
        else:
            all_classes, _error = load_enrollment_classes(
                token,
                student_id,
                school_year=school_year,
                fetch_if_missing=True,
            )
            classes = filter_assessment_classes(all_classes or [], archived_ids)

        if classes:
            html = render_template("partials/assessment_class_list.html", data=classes)
        else:
            empty_message = (
                "No archived subjects."
                if show_archived
                else "No enrolled subjects found."
            )
            html = f'<div class="empty-state"><p>{empty_message}</p></div>'

        return jsonify({"html": html, "target": "assessment-class-list"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cache/assessments/<int:enrollment_class_id>")
def api_cache_assessment_detail(enrollment_class_id):
    token = get_token()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    requested_period = request.args.get("period", type=int)
    cache_key = f"assessment_detail:{enrollment_class_id}"

    student_id = get_student_id(token)
    if not student_id:
        return jsonify({"error": "Could not determine student ID."}), 400

    try:
        classes_raw = api.get_enrollment_classes(token, student_id, page=1, limit=100)
        classes = normalize_enrollment_classes(classes_raw)
        class_info = next(
            (c for c in classes if c["enrollment_class_id"] == enrollment_class_id),
            None,
        )

        all_entries = fetch_all_score_entries(token, student_id, enrollment_class_id)
        grading_summary = build_grading_summary(all_entries)
        grading_periods = extract_grading_periods(all_entries)
        active_period = resolve_active_period(grading_periods, requested_period)
        entries = filter_entries_by_period(all_entries, active_period)

        store_payload(
            cache_key,
            all_entries,
            class_info=class_info,
            grading_summary=grading_summary,
        )

        if entries:
            entry_html = render_template("partials/assessment_entry_list.html", data=entries)
        else:
            entry_html = (
                '<div class="empty-state"><p>No assessments found for this grading period.</p></div>'
            )

        header_html = render_template(
            "partials/assessment_class_header.html",
            class_info=class_info,
            enrollment_class_id=enrollment_class_id,
            is_archived=is_assessment_archived(username, enrollment_class_id),
        )
        grade_html = render_template(
            "partials/grade_summary_content.html",
            grading_summary=grading_summary,
        )
        tabs_html = render_template(
            "partials/assessment_period_tabs.html",
            grading_periods=grading_periods,
            period=active_period,
            enrollment_class_id=enrollment_class_id,
        )

        return jsonify({
            "targets": {
                "assessment-entry-list": entry_html,
                "assessment-class-header": header_html,
                "grade-summary-content": grade_html,
                "assessment-period-tabs": tabs_html,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/assessments/<int:enrollment_class_id>/archive", methods=["POST"])
def toggle_assessment_archive(enrollment_class_id):
    token = get_token()
    username = get_username()

    if not token:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    archived = payload.get("archived")
    if archived is None:
        archived = not is_assessment_archived(username, enrollment_class_id)
    else:
        archived = bool(archived)

    status = set_assessment_archived(username, enrollment_class_id, archived)
    delete_page_cache_prefix("assessments:archived:")
    return jsonify({
        "status": status,
        "enrollment_class_id": enrollment_class_id,
        "archived": archived,
    })


@app.route("/logout")
def logout():
    auth_id = session.get("auth_id")
    if auth_id:
        delete_auth_session(auth_id)
        clear_logs_for_session(auth_id)
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
