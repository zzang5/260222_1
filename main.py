import subprocess, sys

def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    _install("plotly")
    import plotly.express as px
    import plotly.graph_objects as go

import streamlit as st
import pandas as pd
import re
import io

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🇰🇷 인구 현황 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 색상 테마 ────────────────────────────────────────────────────────────────
COLORS = {
    "primary": "#1E3A5F",
    "secondary": "#2E86AB",
    "accent": "#E84855",
    "bg": "#F8F9FA",
    "card": "#FFFFFF",
}

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {COLORS['bg']}; }}
    .metric-card {{
        background: {COLORS['card']};
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        text-align: center;
        border-left: 4px solid {COLORS['secondary']};
    }}
    .metric-value {{ font-size: 2rem; font-weight: 700; color: {COLORS['primary']}; }}
    .metric-label {{ font-size: 0.85rem; color: #666; margin-top: 4px; }}
    h1 {{ color: {COLORS['primary']}; }}
    .section-title {{
        font-size: 1.15rem; font-weight: 600;
        color: {COLORS['primary']};
        border-bottom: 2px solid {COLORS['secondary']};
        padding-bottom: 6px; margin-bottom: 16px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 데이터 로드 헬퍼 ──────────────────────────────────────────────────────────
ENCODINGS = ["utf-8", "cp949", "euc-kr", "utf-8-sig"]

def load_csv(source) -> pd.DataFrame:
    """파일 경로(str) 또는 업로드 객체(BytesIO-like) 모두 처리"""
    for enc in ENCODINGS:
        try:
            if isinstance(source, str):
                return pd.read_csv(source, encoding=enc)
            else:
                source.seek(0)
                return pd.read_csv(source, encoding=enc)
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("파일 인코딩을 인식할 수 없습니다.")


@st.cache_data(show_spinner="데이터 처리 중…")
def preprocess(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    # 행정구역 코드 추출 → 행정 레벨 분류
    def extract_code(s):
        m = re.search(r"\((\d+)\)", str(s))
        return m.group(1) if m else ""

    def region_level(code):
        if code.endswith("00000000"):
            return "시도"
        elif code.endswith("000000"):
            return "시군구"
        else:
            return "읍면동"

    def clean_name(s):
        return re.sub(r"\s*\(\d+\)\s*$", "", str(s)).strip()

    df["code"] = df["행정구역"].apply(extract_code)
    df["level"] = df["code"].apply(region_level)
    df["지역명"] = df["행정구역"].apply(clean_name)

    # 날짜 접두어 파악 (컬럼 동적 인식)
    # 예: "2025년12월_계_총인구수" → prefix = "2025년12월_계"
    total_col = [c for c in df.columns if "총인구수" in c]
    if not total_col:
        raise ValueError("총인구수 컬럼을 찾을 수 없습니다.")
    prefix = total_col[0].replace("_총인구수", "")  # "2025년12월_계"

    # 연령별 컬럼 추출 (0세 ~ 100세 이상)
    age_cols = [c for c in df.columns if re.search(r"_\d+세$|_100세 이상$", c)]
    age_labels = [re.sub(r".*_(\d+세|100세 이상)$", r"\1", c) for c in age_cols]

    # 숫자 변환 (콤마 제거)
    for col in age_cols + total_col:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "")
            .str.replace(" ", "")
            .apply(lambda x: pd.to_numeric(x, errors="coerce"))
            .fillna(0)
            .astype(int)
        )

    # 시도 이름 붙이기
    sido_map = {}
    current_sido = ""
    for _, row in df.iterrows():
        if row["level"] == "시도":
            current_sido = row["지역명"]
        sido_map[row["지역명"]] = current_sido
    df["시도"] = df["지역명"].map(sido_map)
    df["시도"] = df["시도"].fillna(df["지역명"])

    # 메타데이터 저장
    df.attrs["total_col"] = total_col[0]
    df.attrs["age_cols"] = age_cols
    df.attrs["age_labels"] = age_labels
    df.attrs["prefix"] = prefix

    return df


# ── 연령 그룹화 헬퍼 ──────────────────────────────────────────────────────────
AGE_GROUPS = {
    "0~9세": list(range(0, 10)),
    "10~19세": list(range(10, 20)),
    "20~29세": list(range(20, 30)),
    "30~39세": list(range(30, 40)),
    "40~49세": list(range(40, 50)),
    "50~59세": list(range(50, 60)),
    "60~69세": list(range(60, 70)),
    "70~79세": list(range(70, 80)),
    "80세 이상": list(range(80, 101)),
}


def get_group_cols(age_cols: list, ages: list) -> list:
    return [c for c in age_cols if any(f"_{a}세" in c or (a == 100 and "100세 이상" in c) for a in ages)]


# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📂 데이터 업로드")
    uploaded = st.file_uploader(
        "같은 형식의 CSV 파일을 업로드하면 대체됩니다",
        type=["csv"],
        help="행정안전부 연령별 인구 현황 CSV (CP949 또는 UTF-8)",
    )
    st.markdown("---")
    st.markdown("## 🔍 필터")

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
DEFAULT_PATH = "260222_population.csv"

try:
    raw_df = load_csv(uploaded if uploaded else DEFAULT_PATH)
    df = preprocess(raw_df)
except Exception as e:
    st.error(f"❌ 데이터 로드 실패: {e}")
    st.stop()

total_col = df.attrs["total_col"]
age_cols = df.attrs["age_cols"]
age_labels = df.attrs["age_labels"]
prefix = df.attrs["prefix"]

# 날짜 표시
date_label = prefix.replace("_계", "").replace("_남", "").replace("_여", "")

# 시도 목록
sido_list = df[df["level"] == "시도"]["지역명"].tolist()

# ── 헤더 ──────────────────────────────────────────────────────────────────────
st.markdown(
    f"<h1>🇰🇷 인구 현황 대시보드 <span style='font-size:1rem;font-weight:400;color:#888'>({date_label})</span></h1>",
    unsafe_allow_html=True,
)
if uploaded:
    st.success(f"✅ 업로드 파일 적용됨: **{uploaded.name}**")

# ── 탭 구성 ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["🗺️ 지역별 인구", "📈 연령별 분포", "🔬 지역 심층 분석", "📋 데이터 테이블"]
)

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  TAB 1 – 지역별 인구
# ╚══════════════════════════════════════════════════════════════════════════════
with tab1:
    # KPI 카드
    sido_df = df[df["level"] == "시도"].copy()
    total_pop = sido_df[total_col].sum()
    max_row = sido_df.loc[sido_df[total_col].idxmax()]
    min_row = sido_df.loc[sido_df[total_col].idxmin()]

    c1, c2, c3 = st.columns(3)
    for col, val, label in [
        (c1, f"{total_pop:,}명", "전국 총인구"),
        (c2, f"{max_row['지역명']} ({max_row[total_col]:,}명)", "최대 인구 시도"),
        (c3, f"{min_row['지역명']} ({min_row[total_col]:,}명)", "최소 인구 시도"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-value">{val}</div>'
                f'<div class="metric-label">{label}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1])

    # 시도별 인구 막대차트
    with col_left:
        st.markdown('<div class="section-title">📊 시도별 총인구</div>', unsafe_allow_html=True)
        sido_sorted = sido_df.sort_values(total_col, ascending=True)
        fig = px.bar(
            sido_sorted,
            x=total_col,
            y="지역명",
            orientation="h",
            color=total_col,
            color_continuous_scale="Blues",
            labels={total_col: "인구수", "지역명": ""},
            text=total_col,
        )
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(
            height=520,
            coloraxis_showscale=False,
            plot_bgcolor="white",
            xaxis_title="인구수",
            margin=dict(l=20, r=60, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 시도별 인구 트리맵
    with col_right:
        st.markdown('<div class="section-title">🗺️ 인구 비중 (트리맵)</div>', unsafe_allow_html=True)
        fig2 = px.treemap(
            sido_df,
            path=["지역명"],
            values=total_col,
            color=total_col,
            color_continuous_scale="Blues",
            labels={total_col: "인구수"},
        )
        fig2.update_traces(
            textinfo="label+value+percent root",
            hovertemplate="<b>%{label}</b><br>인구: %{value:,}명<br>비율: %{percentRoot:.1%}<extra></extra>",
        )
        fig2.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    # 시군구별 인구 (선택한 시도)
    st.markdown('<div class="section-title">🏙️ 시군구별 인구</div>', unsafe_allow_html=True)
    with st.sidebar:
        sel_sido_1 = st.selectbox("시도 선택 (지역별 탭)", sido_list, key="sido1")

    sigungu_df = df[(df["level"] == "시군구") & (df["시도"].str.contains(sel_sido_1.split()[0]))]
    sigungu_sorted = sigungu_df.sort_values(total_col, ascending=False)

    fig3 = px.bar(
        sigungu_sorted,
        x="지역명",
        y=total_col,
        color=total_col,
        color_continuous_scale="Teal",
        labels={total_col: "인구수", "지역명": ""},
        title=f"{sel_sido_1} 시군구별 인구",
    )
    fig3.update_layout(
        height=420,
        coloraxis_showscale=False,
        plot_bgcolor="white",
        xaxis_tickangle=-35,
        margin=dict(t=40, b=80),
    )
    st.plotly_chart(fig3, use_container_width=True)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  TAB 2 – 연령별 분포
# ╚══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">📈 전국 연령별 인구 분포</div>', unsafe_allow_html=True)

    # 전국 1세 단위 분포
    national = df[df["level"] == "시도"][age_cols].sum()
    age_fig_df = pd.DataFrame({"연령": age_labels, "인구수": national.values})
    # 연령 정렬
    def age_sort_key(s):
        m = re.search(r"\d+", s)
        return int(m.group()) if m else 999
    age_fig_df["_sort"] = age_fig_df["연령"].apply(age_sort_key)
    age_fig_df = age_fig_df.sort_values("_sort").drop(columns="_sort")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        fig_age = px.area(
            age_fig_df,
            x="연령",
            y="인구수",
            labels={"인구수": "인구수", "연령": "연령"},
            color_discrete_sequence=[COLORS["secondary"]],
        )
        fig_age.update_traces(
            fill="tozeroy",
            line_color=COLORS["primary"],
            hovertemplate="<b>%{x}</b><br>인구: %{y:,}명<extra></extra>",
        )
        fig_age.update_layout(
            height=380,
            plot_bgcolor="white",
            xaxis=dict(tickmode="array", tickvals=age_fig_df["연령"][::5].tolist(), tickangle=-60),
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig_age, use_container_width=True)

    with col_b:
        # 연령대별 파이차트
        group_totals = {}
        for g, ages in AGE_GROUPS.items():
            cols_g = get_group_cols(age_cols, ages)
            group_totals[g] = int(df[df["level"] == "시도"][cols_g].sum().sum())
        gt_df = pd.DataFrame({"연령대": list(group_totals.keys()), "인구수": list(group_totals.values())})
        fig_pie = px.pie(
            gt_df, names="연령대", values="인구수",
            color_discrete_sequence=px.colors.sequential.Blues_r,
            hole=0.4,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(height=380, showlegend=False, margin=dict(t=20, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)

    # 시도별 연령대 구성 비교 (누적 막대)
    st.markdown('<div class="section-title">🔢 시도별 연령대 구성 비교</div>', unsafe_allow_html=True)
    view_mode = st.radio("보기 방식", ["비율(%)", "절대값"], horizontal=True)

    group_rows = []
    for _, row in sido_df.iterrows():
        for g, ages in AGE_GROUPS.items():
            cols_g = get_group_cols(age_cols, ages)
            group_rows.append({"시도": row["지역명"], "연령대": g, "인구수": int(row[cols_g].sum())})
    grp_df = pd.DataFrame(group_rows)

    if view_mode == "비율(%)":
        totals = grp_df.groupby("시도")["인구수"].transform("sum")
        grp_df["값"] = grp_df["인구수"] / totals * 100
        y_label = "비율 (%)"
        barnorm = "total"
    else:
        grp_df["값"] = grp_df["인구수"]
        y_label = "인구수"
        barnorm = None

    fig_stack = px.bar(
        grp_df, x="시도", y="값", color="연령대",
        barmode="stack" if barnorm else "stack",
        labels={"값": y_label, "시도": ""},
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig_stack.update_layout(
        height=450, plot_bgcolor="white",
        xaxis_tickangle=-40,
        legend=dict(orientation="h", y=-0.3),
        margin=dict(b=80, t=20),
        barnorm=barnorm,
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # 인구 피라미드 (전국)
    st.markdown('<div class="section-title">🔺 전국 인구 피라미드</div>', unsafe_allow_html=True)
    st.info("ℹ️ 이 데이터셋에는 성별 구분이 없어 단일 막대 피라미드로 표시합니다.")

    pyramid_df = age_fig_df.copy()
    fig_pyr = go.Figure()
    fig_pyr.add_trace(
        go.Bar(
            y=pyramid_df["연령"],
            x=pyramid_df["인구수"],
            orientation="h",
            marker_color=COLORS["secondary"],
            name="인구",
        )
    )
    fig_pyr.update_layout(
        height=1000,
        plot_bgcolor="white",
        xaxis_title="인구수",
        yaxis_title="연령",
        margin=dict(l=60, r=20, t=20, b=20),
    )
    st.plotly_chart(fig_pyr, use_container_width=True)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  TAB 3 – 지역 심층 분석
# ╚══════════════════════════════════════════════════════════════════════════════
with tab3:
    with st.sidebar:
        st.markdown("---")
        sel_sido_3 = st.selectbox("시도 선택 (심층 분석)", sido_list, key="sido3")
        sigungu_list = df[
            (df["level"] == "시군구") & (df["시도"].str.contains(sel_sido_3.split()[0]))
        ]["지역명"].tolist()
        sel_sigungu = st.selectbox("시군구 선택", sigungu_list, key="sigungu3")

    # 선택 지역 데이터
    region_row = df[df["지역명"] == sel_sigungu]
    if region_row.empty:
        st.warning("선택된 시군구 데이터가 없습니다.")
    else:
        r = region_row.iloc[0]
        r_total = int(r[total_col])

        st.markdown(
            f"<h2>📍 {sel_sigungu} 상세 분석</h2>",
            unsafe_allow_html=True,
        )

        # KPI
        # 연령대별 합계
        young = int(region_row[get_group_cols(age_cols, list(range(0, 15)))].sum(axis=1).values[0])
        working = int(region_row[get_group_cols(age_cols, list(range(15, 65)))].sum(axis=1).values[0])
        senior = int(region_row[get_group_cols(age_cols, list(range(65, 101)))].sum(axis=1).values[0])

        k1, k2, k3, k4 = st.columns(4)
        for kc, val, lbl in [
            (k1, f"{r_total:,}명", "총 인구"),
            (k2, f"{young:,}명\n({young/r_total*100:.1f}%)", "유소년 (0~14세)"),
            (k3, f"{working:,}명\n({working/r_total*100:.1f}%)", "생산연령 (15~64세)"),
            (k4, f"{senior:,}명\n({senior/r_total*100:.1f}%)", "고령 (65세+)"),
        ]:
            with kc:
                st.markdown(
                    f'<div class="metric-card"><div class="metric-value" style="font-size:1.4rem">{val}</div>'
                    f'<div class="metric-label">{lbl}</div></div>',
                    unsafe_allow_html=True,
                )
        st.markdown("<br>", unsafe_allow_html=True)

        # 연령 분포 차트
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.markdown(f'<div class="section-title">연령별 인구 분포 – {sel_sigungu}</div>', unsafe_allow_html=True)
            vals = [int(r[c]) for c in age_cols]
            fig_r = px.bar(
                x=age_labels,
                y=vals,
                labels={"x": "연령", "y": "인구수"},
                color=vals,
                color_continuous_scale="Blues",
            )
            fig_r.update_layout(
                height=360, plot_bgcolor="white", coloraxis_showscale=False,
                xaxis=dict(tickmode="array", tickvals=age_labels[::5], tickangle=-60),
                margin=dict(t=10, b=60),
            )
            st.plotly_chart(fig_r, use_container_width=True)

        with col_r:
            st.markdown(f'<div class="section-title">연령대 구성 비율</div>', unsafe_allow_html=True)
            grp_vals = {g: int(region_row[get_group_cols(age_cols, ages)].sum(axis=1).values[0])
                        for g, ages in AGE_GROUPS.items()}
            grp_pie = pd.DataFrame({"연령대": list(grp_vals.keys()), "인구수": list(grp_vals.values())})
            fig_rp = px.pie(grp_pie, names="연령대", values="인구수",
                            color_discrete_sequence=px.colors.sequential.Teal_r, hole=0.45)
            fig_rp.update_traces(textposition="inside", textinfo="percent+label")
            fig_rp.update_layout(height=360, showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig_rp, use_container_width=True)

        # 읍면동 비교
        st.markdown(f'<div class="section-title">📍 읍면동별 인구 비교 – {sel_sigungu}</div>', unsafe_allow_html=True)
        dong_df = df[
            (df["level"] == "읍면동") &
            (df["지역명"].str.startswith(sel_sigungu.split()[0]) if " " in sel_sigungu else df["시도"].str.contains(sel_sido_3.split()[0]))
        ]
        # More precise filter: 읍면동 whose 시도 = sel_sido_3 and 시군구 code matches
        sigungu_code = r["code"][:5]
        dong_df = df[(df["level"] == "읍면동") & (df["code"].str.startswith(sigungu_code))].sort_values(total_col, ascending=False)

        if dong_df.empty:
            st.info("읍면동 데이터가 없습니다.")
        else:
            fig_dong = px.bar(
                dong_df.head(30),
                x="지역명", y=total_col,
                color=total_col,
                color_continuous_scale="Teal",
                labels={total_col: "인구수", "지역명": ""},
            )
            fig_dong.update_layout(
                height=400, plot_bgcolor="white",
                coloraxis_showscale=False,
                xaxis_tickangle=-45,
                margin=dict(t=10, b=80),
            )
            st.plotly_chart(fig_dong, use_container_width=True)

        # 시도 내 시군구 전체 비교 산점도
        st.markdown(f'<div class="section-title">📊 {sel_sido_3} 시군구별 고령화율 vs 생산연령비율</div>', unsafe_allow_html=True)
        sgg_df = df[(df["level"] == "시군구") & (df["시도"].str.contains(sel_sido_3.split()[0]))].copy()
        if not sgg_df.empty:
            sgg_df["생산연령"] = sgg_df[get_group_cols(age_cols, list(range(15, 65)))].sum(axis=1)
            sgg_df["고령"] = sgg_df[get_group_cols(age_cols, list(range(65, 101)))].sum(axis=1)
            sgg_df["고령화율"] = sgg_df["고령"] / sgg_df[total_col] * 100
            sgg_df["생산연령비율"] = sgg_df["생산연령"] / sgg_df[total_col] * 100
            fig_sc = px.scatter(
                sgg_df, x="고령화율", y="생산연령비율",
                size=total_col, text="지역명",
                color="고령화율", color_continuous_scale="RdYlGn_r",
                labels={"고령화율": "고령화율 (%)", "생산연령비율": "생산연령비율 (%)"},
                size_max=60,
            )
            fig_sc.update_traces(textposition="top center")
            fig_sc.update_layout(height=450, plot_bgcolor="white", margin=dict(t=20, b=20))
            st.plotly_chart(fig_sc, use_container_width=True)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  TAB 4 – 데이터 테이블
# ╚══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-title">📋 원본 데이터 테이블</div>', unsafe_allow_html=True)
    level_filter = st.selectbox("행정 레벨 필터", ["전체", "시도", "시군구", "읍면동"], key="lf")
    search_kw = st.text_input("지역명 검색", placeholder="예: 강남구")

    disp = df.copy()
    if level_filter != "전체":
        disp = disp[disp["level"] == level_filter]
    if search_kw:
        disp = disp[disp["지역명"].str.contains(search_kw)]

    show_cols = ["지역명", "시도", "level", total_col] + list(AGE_GROUPS.keys())

    # 연령대 합산 컬럼 추가
    for g, ages in AGE_GROUPS.items():
        cols_g = get_group_cols(age_cols, ages)
        disp[g] = disp[cols_g].sum(axis=1)

    st.dataframe(
        disp[show_cols].rename(columns={total_col: "총인구수", "level": "레벨"}).reset_index(drop=True),
        use_container_width=True,
        height=500,
    )

    # CSV 다운로드
    csv_buf = io.StringIO()
    disp[show_cols].to_csv(csv_buf, index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇️ 필터 결과 CSV 다운로드",
        data=csv_buf.getvalue().encode("utf-8-sig"),
        file_name="population_filtered.csv",
        mime="text/csv",
    )

# ── 푸터 ──────────────────────────────────────────────────────────────────────
st.markdown(
    "<br><hr><p style='text-align:center;color:#aaa;font-size:0.8rem;'>행정안전부 주민등록 인구 현황 | 인구 대시보드 by Claude</p>",
    unsafe_allow_html=True,
)
