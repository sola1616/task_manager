"""업무 우선순위 관리 웹 앱 (Streamlit)

[기본 기능]
- 업무명, 중요도(1~5), 긴급도(1~5) 입력 → 우선순위 점수 = 중요도 × 긴급도
- 최우선(16점 이상) / 일반(9~15점) / 낮음(8점 이하) 구분
- 점수 높은 순 정렬, 빈 업무명 등록 방지, 선택 삭제
- session_state로 브라우저 세션 동안 업무 목록 유지

[추가·개선 기능]
- 같은 업무명 중복 등록 방지 (공백·대소문자 무시)
- 마감일 지정 및 D-day 표시, 마감 임박(3일 이내) 집계
- 월별 달력 보기 (마감일 기준, 등급별 색상)
- 내 캘린더에 일정 추가: 구글 캘린더 바로가기 링크, 일정 파일(.ics) 다운로드
- 등급 필터, CSV 다운로드, 전체 목록 초기화
※ 외부 API·데이터베이스는 사용하지 않습니다.
"""

import calendar
import csv
import html
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import streamlit as st

KST = timezone(timedelta(hours=9))  # 한국 시간 (배포 서버는 UTC이므로 직접 지정)

st.set_page_config(page_title="업무 우선순위 관리", page_icon="📌", layout="wide")


# =========================================================
# 기능 함수
# =========================================================
def today_kst() -> date:
    return datetime.now(KST).date()


def calc_score(importance: int, urgency: int) -> int:
    return importance * urgency


def classify(score: int) -> str:
    if score >= 16:
        return "최우선"
    elif score >= 9:
        return "일반"
    return "낮음"


GRADE_ICON = {"최우선": "🔴", "일반": "🟡", "낮음": "🟢"}
GRADE_COLOR = {"최우선": "rgba(239,68,68,0.20)", "일반": "rgba(234,179,8,0.22)", "낮음": "rgba(34,197,94,0.20)"}


def normalize(name: str) -> str:
    return " ".join(name.split()).lower()


def is_duplicate(name: str) -> bool:
    target = normalize(name)
    return any(normalize(t["업무명"]) == target for t in st.session_state.tasks)


def d_day(due: date) -> str:
    diff = (due - today_kst()).days
    if diff == 0:
        return "D-Day"
    if diff > 0:
        return f"D-{diff}"
    return f"D+{-diff} (지남)"


def sorted_tasks():
    """점수 높은 순 → 마감일 빠른 순 → 등록 순"""
    return sorted(st.session_state.tasks, key=lambda t: (-t["점수"], t["마감일"], t["id"]))


# ---------- 캘린더 연동 (외부 API 없이 링크·파일로 처리) ----------
def google_calendar_url(task: dict) -> str:
    start = task["마감일"].strftime("%Y%m%d")
    end = (task["마감일"] + timedelta(days=1)).strftime("%Y%m%d")
    title = f"[{task['등급']}] {task['업무명']}"
    details = f"우선순위 점수 {task['점수']}점 (중요도 {task['중요도']} × 긴급도 {task['긴급도']})"
    if task["메모"]:
        details += f"\n메모: {task['메모']}"
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(title)}&dates={start}/{end}&details={quote(details)}")


def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_ics(tasks: list) -> bytes:
    """iCalendar(.ics) 파일 생성 — 구글·아웃룩·애플·삼성 캘린더에서 가져오기 가능"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//task-manager//KO", "CALSCALE:GREGORIAN"]
    for t in tasks:
        desc = f"우선순위 점수 {t['점수']}점 (중요도 {t['중요도']} × 긴급도 {t['긴급도']})"
        if t["메모"]:
            desc += f"\n메모: {t['메모']}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@task-manager",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{t['마감일'].strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(t['마감일'] + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{ics_escape('[' + t['등급'] + '] ' + t['업무명'])}",
            f"DESCRIPTION:{ics_escape(desc)}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-P1D",
            f"DESCRIPTION:{ics_escape(t['업무명'] + ' 마감 하루 전')}", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


def make_csv(tasks: list) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["순위", "등급", "업무명", "점수", "중요도", "긴급도", "마감일", "D-day", "메모"])
    for i, t in enumerate(tasks, start=1):
        writer.writerow([i, t["등급"], t["업무명"], t["점수"], t["중요도"], t["긴급도"],
                         t["마감일"].isoformat(), d_day(t["마감일"]), t["메모"]])
    return buf.getvalue().encode("utf-8-sig")  # 엑셀에서 한글 깨짐 방지


def render_month(year: int, month: int, tasks: list) -> str:
    """월별 달력 HTML (일요일 시작)"""
    by_day = {}
    for t in tasks:
        if t["마감일"].year == year and t["마감일"].month == month:
            by_day.setdefault(t["마감일"].day, []).append(t)

    today = today_kst()
    head = "".join(f"<th>{d}</th>" for d in ["일", "월", "화", "수", "목", "금", "토"])
    rows = []
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        cells = []
        for i, day in enumerate(week):
            if day == 0:
                cells.append("<td class='empty'></td>")
                continue
            cls = "today" if date(year, month, day) == today else ""
            num_cls = "sun" if i == 0 else ("sat" if i == 6 else "")
            items = "".join(
                f"<div class='chip' style='background:{GRADE_COLOR[t['등급']]}'>"
                f"{GRADE_ICON[t['등급']]} {html.escape(t['업무명'])}</div>"
                for t in sorted(by_day.get(day, []), key=lambda x: -x["점수"])
            )
            cells.append(f"<td class='{cls}'><div class='num {num_cls}'>{day}</div>{items}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    style = """
    <style>
    .cal{width:100%;border-collapse:collapse;table-layout:fixed}
    .cal th{padding:6px;font-size:0.85rem;opacity:.7;border-bottom:1px solid rgba(128,128,128,.3)}
    .cal td{height:92px;vertical-align:top;padding:4px;border:1px solid rgba(128,128,128,.2)}
    .cal td.empty{background:rgba(128,128,128,.05)}
    .cal td.today{outline:2px solid #ef4444;outline-offset:-2px}
    .cal .num{font-size:.8rem;font-weight:600;margin-bottom:3px}
    .cal .num.sun{color:#ef4444}.cal .num.sat{color:#3b82f6}
    .cal .chip{font-size:.72rem;padding:2px 4px;border-radius:4px;margin-bottom:2px;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    </style>"""
    return style + f"<table class='cal'><tr>{head}</tr>{''.join(rows)}</table>"


# =========================================================
# session_state 초기화
# =========================================================
defaults = {"tasks": [], "next_id": 1, "message": None,
            "cal_year": today_kst().year, "cal_month": today_kst().month}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# =========================================================
# 사이드바: 업무 등록
# =========================================================
with st.sidebar:
    st.header("➕ 새 업무 등록")
    with st.form("task_form", clear_on_submit=True):
        name = st.text_input("업무명", placeholder="예: 연차보고서 초안 작성")
        importance = st.slider("중요도 (1~5)", 1, 5, 3)
        urgency = st.slider("긴급도 (1~5)", 1, 5, 3)
        due = st.date_input("마감일", value=today_kst(), format="YYYY-MM-DD")
        memo = st.text_input("메모 (선택)", placeholder="예: 학과 회의 전 공유")
        submitted = st.form_submit_button("업무 추가", type="primary", use_container_width=True)

    if submitted:
        clean_name = " ".join(name.split())
        if not clean_name:
            st.session_state.message = ("error", "업무명을 입력해야 등록할 수 있습니다.")
        elif is_duplicate(clean_name):
            st.session_state.message = ("warning", f"'{clean_name}'은(는) 이미 등록된 업무입니다.")
        else:
            score = calc_score(importance, urgency)
            grade = classify(score)
            st.session_state.tasks.append({
                "id": st.session_state.next_id, "업무명": clean_name,
                "중요도": importance, "긴급도": urgency, "점수": score, "등급": grade,
                "마감일": due, "메모": memo.strip(),
            })
            st.session_state.next_id += 1
            st.session_state.cal_year, st.session_state.cal_month = due.year, due.month
            st.session_state.message = (
                "success", f"'{clean_name}' 업무가 등록되었습니다. ({score}점 / {GRADE_ICON[grade]} {grade})")

    if st.session_state.message:
        kind, text = st.session_state.message
        getattr(st, kind)(text)
        st.session_state.message = None

    st.caption("※ 업무 목록은 현재 브라우저 세션 동안만 유지됩니다.")


# =========================================================
# 메인 화면
# =========================================================
st.title("📌 업무 우선순위 관리 웹 앱")

tasks = sorted_tasks()
soon = [t for t in tasks if 0 <= (t["마감일"] - today_kst()).days <= 3]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("전체 업무", f"{len(tasks)}건")
m2.metric("🔴 최우선 (16점+)", f"{sum(t['등급'] == '최우선' for t in tasks)}건")
m3.metric("🟡 일반 (9~15점)", f"{sum(t['등급'] == '일반' for t in tasks)}건")
m4.metric("🟢 낮음 (8점-)", f"{sum(t['등급'] == '낮음' for t in tasks)}건")
m5.metric("⏰ 마감 임박 (3일 이내)", f"{len(soon)}건")

st.divider()
tab_list, tab_cal, tab_del = st.tabs(["📋 업무 목록", "📅 달력 · 일정 추가", "🗑️ 삭제 및 초기화"])

# ---------- 탭 1: 업무 목록 ----------
with tab_list:
    if not tasks:
        st.info("등록된 업무가 없습니다. 왼쪽에서 업무를 추가하세요.")
    else:
        top_left, top_right = st.columns([3, 2])
        with top_left:
            grade_filter = st.radio("등급 필터", ["전체", "🔴 최우선", "🟡 일반", "🟢 낮음"], horizontal=True)
        shown = tasks if grade_filter == "전체" else [t for t in tasks if grade_filter.endswith(t["등급"])]
        with top_right:
            b1, b2 = st.columns(2)
            b1.download_button("⬇️ CSV 다운로드", make_csv(shown), file_name="업무목록.csv",
                               mime="text/csv", use_container_width=True)
            b2.download_button("📅 전체 일정(.ics)", make_ics(shown), file_name="업무일정.ics",
                               mime="text/calendar", use_container_width=True)

        if not shown:
            st.info("해당 등급의 업무가 없습니다.")
        else:
            rows = [{"순위": i, "등급": f"{GRADE_ICON[t['등급']]} {t['등급']}", "업무명": t["업무명"],
                     "점수": t["점수"], "중요도": t["중요도"], "긴급도": t["긴급도"],
                     "마감일": t["마감일"].isoformat(), "D-day": d_day(t["마감일"]), "메모": t["메모"]}
                    for i, t in enumerate(shown, start=1)]
            st.dataframe(rows, hide_index=True, width="stretch")

# ---------- 탭 2: 달력 및 캘린더 연동 ----------
with tab_cal:
    c_prev, c_title, c_next, c_today = st.columns([1, 3, 1, 1])
    if c_prev.button("◀ 이전 달", use_container_width=True):
        y, m = st.session_state.cal_year, st.session_state.cal_month - 1
        st.session_state.cal_year, st.session_state.cal_month = (y - 1, 12) if m == 0 else (y, m)
        st.rerun()
    if c_next.button("다음 달 ▶", use_container_width=True):
        y, m = st.session_state.cal_year, st.session_state.cal_month + 1
        st.session_state.cal_year, st.session_state.cal_month = (y + 1, 1) if m == 13 else (y, m)
        st.rerun()
    if c_today.button("오늘", use_container_width=True):
        st.session_state.cal_year, st.session_state.cal_month = today_kst().year, today_kst().month
        st.rerun()
    year, month = st.session_state.cal_year, st.session_state.cal_month
    c_title.markdown(f"<h3 style='text-align:center;margin:0'>{year}년 {month}월</h3>", unsafe_allow_html=True)

    st.markdown(render_month(year, month, tasks), unsafe_allow_html=True)

    month_tasks = sorted([t for t in tasks if t["마감일"].year == year and t["마감일"].month == month],
                         key=lambda t: (t["마감일"], -t["점수"]))
    st.markdown("#### 📲 내 캘린더에 일정 추가")
    st.caption("구글 캘린더는 버튼을 누르면 바로 추가 화면이 열립니다. "
               "아웃룩·삼성·애플 캘린더는 .ics 파일을 내려받아 열면 추가됩니다. (마감 하루 전 알림 포함)")
    if not month_tasks:
        st.info("이 달에 마감되는 업무가 없습니다.")
    for t in month_tasks:
        col_a, col_b, col_c = st.columns([4, 1.3, 1.3])
        col_a.markdown(f"**{t['마감일'].strftime('%m/%d')}** · {GRADE_ICON[t['등급']]} {t['업무명']} "
                       f"({t['점수']}점, {d_day(t['마감일'])})")
        col_b.link_button("구글 캘린더", google_calendar_url(t), use_container_width=True)
        col_c.download_button(".ics 파일", make_ics([t]), file_name=f"{t['업무명']}.ics",
                              mime="text/calendar", key=f"ics_{t['id']}", use_container_width=True)

# ---------- 탭 3: 삭제 및 초기화 ----------
with tab_del:
    if not tasks:
        st.info("삭제할 업무가 없습니다.")
    else:
        labels = {t["id"]: f"{GRADE_ICON[t['등급']]} {t['업무명']} ({t['점수']}점, {t['마감일']:%m/%d})"
                  for t in tasks}
        selected = st.multiselect("삭제할 업무를 선택하세요 (다중 선택 가능)",
                                  options=list(labels.keys()), format_func=lambda i: labels[i])
        d1, d2 = st.columns(2)
        if d1.button("선택 업무 삭제", disabled=not selected, use_container_width=True):
            st.session_state.tasks = [t for t in st.session_state.tasks if t["id"] not in selected]
            st.session_state.message = ("success", f"{len(selected)}건의 업무가 삭제되었습니다.")
            st.rerun()
        confirm = d2.checkbox("전체 초기화에 동의합니다")
        if d2.button("전체 목록 초기화", disabled=not confirm, type="primary", use_container_width=True):
            count = len(st.session_state.tasks)
            st.session_state.tasks = []
            st.session_state.message = ("success", f"전체 {count}건의 업무가 초기화되었습니다.")
            st.rerun()
