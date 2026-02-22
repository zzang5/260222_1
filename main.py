import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="지역별 인구 분석", layout="wide")

st.title("📊 지역별 인구 분포 분석 웹앱")

# 파일 업로드 기능
uploaded_file = st.file_uploader("CSV 파일을 업로드하세요", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_csv("260222_population.csv")

st.write("데이터 미리보기", df.head())

# -------------------------------
# 데이터 전처리 예시
# -------------------------------

# 열 이름 확인 후 필요 시 수정
# 예시: 지역, 총인구, 남자, 여자

region_col = st.selectbox("지역 컬럼 선택", df.columns)
population_col = st.selectbox("인구수 컬럼 선택", df.columns)

# -------------------------------
# 지역 선택 필터
# -------------------------------

selected_regions = st.multiselect(
    "분석할 지역 선택",
    options=df[region_col].unique(),
    default=df[region_col].unique()
)

filtered_df = df[df[region_col].isin(selected_regions)]

# -------------------------------
# 1. 지역별 인구 막대그래프
# -------------------------------

st.subheader("📌 지역별 인구 비교")

fig_bar = px.bar(
    filtered_df,
    x=region_col,
    y=population_col,
    text_auto=True,
    title="지역별 인구 현황"
)

fig_bar.update_layout(xaxis_title="지역", yaxis_title="인구수")

st.plotly_chart(fig_bar, use_container_width=True)

# -------------------------------
# 2. 파이차트
# -------------------------------

st.subheader("📌 인구 비율 분석")

fig_pie = px.pie(
    filtered_df,
    names=region_col,
    values=population_col,
    title="지역별 인구 비율"
)

st.plotly_chart(fig_pie, use_container_width=True)

# -------------------------------
# 3. 인구 상위 지역 TOP5
# -------------------------------

st.subheader("📌 인구 상위 지역 TOP5")

top5 = filtered_df.sort_values(by=population_col, ascending=False).head(5)

fig_top5 = px.bar(
    top5,
    x=population_col,
    y=region_col,
    orientation='h',
    title="인구 상위 5개 지역"
)

st.plotly_chart(fig_top5, use_container_width=True)

st.success("분석 완료 ✅")
