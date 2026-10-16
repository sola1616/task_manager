"""업무 우선순위 관리 웹 앱 (Streamlit)
- 중요도(1~5) × 긴급도(1~5) = 우선순위 점수
- 최우선(16점 이상) / 일반(9~15점) / 낮음(8점 이하)
- session_state로 브라우저 세션 동안 업무 목록 유지
- [개선 기능] 같은 업무명 중복 등록 방지 (공백·대소문자 무시)
"""
import streamlit as st

st.set_page_config(page_title="업무 우선순위 관리", page_icon="📋")


def calc_score(importance, urgency):
    return importance * urgency


def classify(score):
    if score >= 16:
        return "🔴 최우선"
    elif score >= 9:
        return "🟡 일반"
    else:
        return "🟢 낮음"


def normalize(name):
    return " ".join(name.split()).lower()


def is_duplicate(name):
    target = normalize(name)
    return any(normalize(t["업무명"]) == target for t in st.session_state.tasks)


# session_state 초기화
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "next_id" not in st.session_state:
    st.session_state.next_id = 1
if "message" not in st.session_state:
    st.session_state.message = None

st.title("📋 업무 우선순위 관리")
st.caption("중요도 × 긴급도로 우선순위 점수를 계산하고, 점수가 높은 순서로 업무를 정리합니다.")

# 업무 입력
with st.form("task_form", clear_on_submit=True):
    name = st.text_input("업무명", placeholder="예: 연차보고서 초안 작성")
    col1, col2 = st.columns(2)
    with col1:
        importance = st.slider("중요도", 1, 5, 3)
    with col2:
        urgency = st.slider("긴급도", 1, 5, 3)
    submitted = st.form_submit_button("업무 추가", type="primary")

# 업무 추가 처리
if submitted:
    clean_name = " ".join(name.split())
    if not clean_name:
        st.session_state.message = ("error", "업무명을 입력해야 등록할 수 있습니다.")
    elif is_duplicate(clean_name):
        st.session_state.message = ("warning", f"'{clean_name}'은(는) 이미 등록된 업무입니다.")
    else:
        score = calc_score(importance, urgency)
        st.session_state.tasks.append({
            "id": st.session_state.next_id,
            "업무명": clean_name,
            "중요도": importance,
            "긴급도": urgency,
            "점수": score,
            "등급": classify(score),
        })
        st.session_state.next_id += 1
        st.session_state.message = ("success", f"'{clean_name}' 업무가 등록되었습니다. (점수: {score}점)")

if st.session_state.message:
    kind, text = st.session_state.message
    getattr(st, kind)(text)
    st.session_state.message = None

st.divider()

# 업무 목록 (점수 높은 순)
st.subheader("업무 목록")
tasks = sorted(st.session_state.tasks, key=lambda t: (-t["점수"], t["id"]))

if not tasks:
    st.info("등록된 업무가 없습니다.")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 최우선", sum(t["등급"].endswith("최우선") for t in tasks))
    c2.metric("🟡 일반", sum(t["등급"].endswith("일반") for t in tasks))
    c3.metric("🟢 낮음", sum(t["등급"].endswith("낮음") for t in tasks))

    rows = [
        {"순위": i, "업무명": t["업무명"], "중요도": t["중요도"],
         "긴급도": t["긴급도"], "점수": t["점수"], "등급": t["등급"]}
        for i, t in enumerate(tasks, start=1)
    ]
    st.dataframe(rows, hide_index=True)

    # 업무 삭제
    st.subheader("업무 삭제")
    labels = {t["id"]: f"{t['업무명']} ({t['점수']}점)" for t in tasks}
    selected = st.multiselect("삭제할 업무를 선택하세요",
                              options=list(labels.keys()),
                              format_func=lambda i: labels[i])
    if st.button("선택 업무 삭제", disabled=not selected):
        st.session_state.tasks = [t for t in st.session_state.tasks if t["id"] not in selected]
        st.session_state.message = ("success", f"{len(selected)}건의 업무가 삭제되었습니다.")
        st.rerun()

st.caption("※ 업무 목록은 현재 브라우저 세션 동안만 유지됩니다.")
