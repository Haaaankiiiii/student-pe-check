import streamlit as st
import pandas as pd
from datetime import datetime, time
import pytz
from typing import Optional

# ==============================
# 0. 설정: 교시 시간대 (학교 시간에 맞게 수정 완료!)
# ==============================
# 24시간 형식 "HH:MM"
PERIOD_SCHEDULE = [
    {"period": 1, "start": "08:50", "end": "09:40"},
    {"period": 2, "start": "09:50", "end": "10:40"},
    {"period": 3, "start": "10:50", "end": "11:40"},
    {"period": 4, "start": "11:50", "end": "12:40"},
    {"period": 5, "start": "13:40", "end": "14:30"},
    {"period": 6, "start": "14:40", "end": "15:30"},
    {"period": 7, "start": "15:40", "end": "16:30"},
    # 필요없으면 줄이거나, 더 있으면 추가
]

# 시간표에서 "체육"이라고 적힌 과목을 체육으로 인식
PE_KEYWORD = "체육"

# 한국 시간대
KST = pytz.timezone("Asia/Seoul")

WEEKDAY_MAP = {
    0: "월요일",
    1: "화요일",
    2: "수요일",
    3: "목요일",
    4: "금요일",
    5: "토요일",
    6: "일요일",
}


# ==============================
# 1. 시간표 불러오기
# ==============================
@st.cache_data
def load_timetable(path: str) -> pd.DataFrame:
    """
    timetable.xlsx 읽어서 DataFrame으로 반환.
    컬럼: 학년, 반, 요일, 교시, 과목
    """
    df = pd.read_excel(path)

    df["학년"] = df["학년"].astype(int)
    df["반"] = df["반"].astype(int)
    df["교시"] = df["교시"].astype(int)
    df["요일"] = df["요일"].astype(str)
    df["과목"] = df["과목"].astype(str)

    return df


def get_period_from_now(now: datetime) -> Optional[int]:
    """
    현재 시간이 어느 교시에 속하는지 PERIOD_SCHEDULE를 보고 반환.
    속하지 않으면 None 반환.
    """
    current_t = now.time()

    def parse_hm(hm_str: str) -> time:
        return datetime.strptime(hm_str, "%H:%M").time()

    for item in PERIOD_SCHEDULE:
        start_t = parse_hm(item["start"])
        end_t = parse_hm(item["end"])
        # start <= 현재 < end 이면 해당 교시로 본다
        if start_t <= current_t < end_t:
            return item["period"]

    return None


def check_pe(df: pd.DataFrame, grade: int, class_no: int, weekday: str, period: int) -> bool:
    """
    해당 학년/반/요일/교시에 체육(PE_KEYWORD)이 들어있는지 여부 반환.
    """
    cond = (
        (df["학년"] == grade)
        & (df["반"] == class_no)
        & (df["요일"] == weekday)
        & (df["교시"] == period)
    )
    sub_df = df[cond]

    if sub_df.empty:
        return False

    # 한 셀이 "체육", "체육A", "체육(축구)" 이런 식일 수도 있으니까 부분 포함으로 체크
    return any(PE_KEYWORD in subj for subj in sub_df["과목"])


def get_today_pe_summary(df: pd.DataFrame, weekday: str) -> pd.DataFrame:
    """
    오늘 요일 기준으로, 어떤 학년/반이 몇 교시에 체육이 있는지 요약.
    반환: 컬럼 [학년, 반, 체육 교시]
    """
    cond = (df["요일"] == weekday) & (df["과목"].str.contains(PE_KEYWORD))
    sub = df[cond].copy()

    if sub.empty:
        return pd.DataFrame(columns=["학년", "반", "체육 교시"])

    grouped = (
        sub.groupby(["학년", "반"])["교시"]
        .apply(lambda s: ", ".join(str(p) + "교시" for p in sorted(s.unique())))
        .reset_index()
        .rename(columns={"교시": "체육 교시"})
        .sort_values(["학년", "반"])
        .reset_index(drop=True)
    )
    return grouped


def get_today_pe_periods_for_class(
    df: pd.DataFrame, grade: int, class_no: int, weekday: str
) -> list[int]:
    """
    특정 학년/반이 오늘(weekday) 몇 교시에 체육이 있는지 리스트로 반환.
    """
    cond = (
        (df["학년"] == grade)
        & (df["반"] == class_no)
        & (df["요일"] == weekday)
        & (df["과목"].str.contains(PE_KEYWORD))
    )
    sub = df[cond]

    if sub.empty:
        return []

    return sorted(sub["교시"].unique())


# ==============================
# 2. Streamlit UI
# ==============================
def main():
    st.set_page_config(page_title="체육복 확인 앱", layout="wide")
    st.title("🏃 교사용 학생 체육시간 확인 앱")

    st.markdown(
        """
        교사가 학년/반을 선택하면,  
        **현재 시간 기준으로 체육 시간인지 여부**를 자동으로 확인해주는 앱입니다.  
        학생 이름은 저장하지 않고, 시간표에 있는 학년/반/과목 정보만 사용합니다.
        """
    )

    # ---- 시간표 로드 ----
    try:
        df_timetable = load_timetable("timetable.xlsx")
    except Exception as e:
        st.error("❌ timetable.xlsx 파일을 읽는 중 오류가 발생했습니다.")
        st.error(str(e))
        st.stop()

    # 학년/반 목록 준비
    grades = sorted(df_timetable["학년"].unique())
    classes_by_grade = {
        g: sorted(df_timetable[df_timetable["학년"] == g]["반"].unique())
        for g in grades
    }

    # ---- 현재 시간 & 오늘 요일 ----
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_kst = now_utc.astimezone(KST)
    weekday_name = WEEKDAY_MAP[now_kst.weekday()]  # ex) "월요일", "토요일"

    st.info(
        f"현재 시간 (KST 기준): **{now_kst.strftime('%Y-%m-%d %H:%M:%S')}**, "
        f"오늘 요일: **{weekday_name}**"
    )

    st.markdown("---")

    # ==============================
    # A. 상단: 학년/반 선택
    # ==============================
    st.subheader("🎓 학년 / 반 선택")

    col_grade, col_class = st.columns(2)
    with col_grade:
        selected_grade = st.selectbox("학년 선택", options=grades)
    with col_class:
        selected_class = st.selectbox(
            "반 선택",
            options=classes_by_grade[selected_grade],
            key="class_select",
        )

    st.write(
        f"선택된 학급: **{selected_grade}학년 {selected_class}반**"
    )

    st.markdown("---")

    # ==============================
    # B. 오늘 전체 체육 요약 표시
    # ==============================
    st.subheader("📅 오늘 요일 기준 체육 시간 요약")

    if weekday_name in ["월요일", "화요일", "수요일", "목요일", "금요일"]:
        df_today_pe = get_today_pe_summary(df_timetable, weekday_name)

        if df_today_pe.empty:
            st.warning(f"오늘(**{weekday_name}**)은 어느 학급에도 체육 시간이 등록되어 있지 않습니다.")
        else:
            st.caption(f"오늘(**{weekday_name}**) 체육이 있는 학급과 교시 목록입니다.")
            st.dataframe(
                df_today_pe,
                use_container_width=True,
                height=300,
            )
    else:
        st.warning("오늘은 토요일/일요일이므로, 정규 수업이 없을 수 있습니다.")

    st.markdown("---")

    # ==============================
    # C. 현재 시간 기준 자동 계산만 제공
    # ==============================
    st.subheader("⏱ 현재 시간 기준 자동 계산")

    if weekday_name not in ["월요일", "화요일", "수요일", "목요일", "금요일"]:
        st.warning("📌 오늘은 토요일/일요일이므로 수업 시간이 아닐 가능성이 큽니다.")
    else:
        current_period = get_period_from_now(now_kst)

        if current_period is None:
            st.warning(
                "지금 시간은 어느 교시에도 속하지 않습니다. "
                "교시 시간 설정(PERIOD_SCHEDULE)을 확인해주세요."
            )
        else:
            st.write(
                f"현재 시간은 **{current_period}교시** 시간대로 인식했습니다."
            )

            if st.button("현재 시간 기준 체육시간 여부 확인"):
                is_pe = check_pe(
                    df_timetable,
                    grade=selected_grade,
                    class_no=selected_class,
                    weekday=weekday_name,
                    period=current_period,
                )

                if is_pe:
                    st.success(
                        f"✅ **지금은 {selected_grade}학년 {selected_class}반의 체육시간입니다. "
                        "체육복 착용이 정상입니다.**"
                    )
                else:
                    st.warning(
                        f"⚠️ **지금은 {selected_grade}학년 {selected_class}반의 체육시간이 아닙니다. "
                        "체육복 착용은 규정 위반일 수 있습니다.**"
                    )

                # 오늘 이 반의 체육 교시 안내
                today_periods = get_today_pe_periods_for_class(
                    df_timetable,
                    grade=selected_grade,
                    class_no=selected_class,
                    weekday=weekday_name,
                )
                if today_periods:
                    txt = ", ".join(f"{p}교시" for p in today_periods)
                    st.info(
                        f"📌 참고: 오늘(**{weekday_name}**) {selected_grade}학년 {selected_class}반의 체육 시간은 "
                        f"**{txt}** 입니다."
                    )
                else:
                    st.info(
                        f"📌 참고: 오늘(**{weekday_name}**) {selected_grade}학년 {selected_class}반은 체육 시간이 없습니다."
                    )

    st.caption(
        "※ 교시 시간대가 실제 학교 시간과 다르면, 코드 맨 위의 PERIOD_SCHEDULE를 수정해주세요."
    )


if __name__ == "__main__":
    main()
