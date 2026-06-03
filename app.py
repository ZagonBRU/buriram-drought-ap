
import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import json

# ============================================================
# ตั้งค่าหน้าเว็บ
# ============================================================
st.set_page_config(
    page_title="ระบบสารสนเทศความเสี่ยงภัยแล้ง จังหวัดบุรีรัมย์",
    page_icon="🌾",
    layout="wide"
)

# ============================================================
# โหลดข้อมูล
# ============================================================
@st.cache_data
def load_data():
    df = pd.read_csv("district_drought_stats.csv", index_col=0)
    with open("buriram_districts_23.json", "r", encoding="utf-8") as f:
        geojson = json.load(f)
    return df, geojson

df, geojson = load_data()

# ============================================================
# ฟังก์ชันกำหนดสีและระดับความเสี่ยง
# ============================================================
def get_risk_label(score):
    if score >= 0.75:
        return "🔴 เสี่ยงสูง"
    elif score >= 0.65:
        return "🟡 เสี่ยงปานกลาง"
    else:
        return "🟢 เสี่ยงต่ำ"

def get_risk_color(score):
    if score >= 0.75:
        return "#E24B4A"
    elif score >= 0.65:
        return "#EF9F27"
    else:
        return "#639922"

df["ระดับความเสี่ยง"] = df["Drought_Score"].apply(get_risk_label)
df["risk_color"]       = df["Drought_Score"].apply(get_risk_color)

# ============================================================
# Header
# ============================================================
st.title("🌾 ระบบสารสนเทศความเสี่ยงภัยแล้งทางการเกษตร")
st.markdown("### จังหวัดบุรีรัมย์ · ฤดูแล้ง 2567 (2024)")
st.markdown(
    "วิเคราะห์จากดัชนีพืชพรรณ **NDVI** และดัชนีความชื้น **NDMI** "
    "จากภาพถ่ายดาวเทียม Sentinel-2 ผ่าน Google Earth Engine "
    "เปรียบเทียบกับค่าเฉลี่ยปี 2562–2566"
)
st.divider()

# ============================================================
# Metric Cards — ภาพรวมจังหวัด
# ============================================================
st.subheader("📊 ภาพรวมจังหวัดบุรีรัมย์")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("NDVI ฤดูแล้ง",    "0.37",    "vs ฤดูฝน 0.67")
col2.metric("NDMI ฤดูแล้ง",    "-0.089",  "ความชื้นต่ำ")
col3.metric("ฝนสะสม 2567",     "106 mm",  "-71.3 mm จากค่าเฉลี่ย", delta_color="inverse")
col4.metric("ขาดน้ำฝน",        "-40%",    "เทียบ baseline 2562–66", delta_color="inverse")
col5.metric("อำเภอเสี่ยงสูง",  "8 อำเภอ", "จาก 23 อำเภอ")

st.divider()

# ============================================================
# Layout 2 คอลัมน์: แผนที่ + กราฟ
# ============================================================
col_map, col_chart = st.columns([3, 2])

with col_map:
    st.subheader("🗺️ แผนที่ความเสี่ยงภัยแล้งรายอำเภอ")

    # สร้างแผนที่ Folium
    m = folium.Map(
        location=[15.0, 103.1],
        zoom_start=9,
        tiles="CartoDB positron"
    )

    # วาด polygon แต่ละอำเภอ
    for feature in geojson["features"]:
        district_name = feature["properties"]["NAME_2"]
        row = df[df["อำเภอ"] == district_name]

        if len(row) > 0:
            score   = row["Drought_Score"].values[0]
            color   = get_risk_color(score)
            deficit = row["Rainfall_Deficit"].values[0]
            ndvi    = row["NDVI_Dry"].values[0]
            risk    = row["ระดับความเสี่ยง"].values[0]

            popup_html = f"""
            <div style="font-family:sans-serif; min-width:180px;">
                <b style="font-size:14px;">{district_name}</b><br>
                <hr style="margin:4px 0;">
                <b>ระดับความเสี่ยง:</b> {risk}<br>
                <b>Drought Score:</b> {score:.3f}<br>
                <b>NDVI ฤดูแล้ง:</b> {ndvi:.3f}<br>
                <b>ฝนขาด:</b> {deficit:.1f} mm
            </div>
            """

            folium.GeoJson(
                feature,
                style_function=lambda x, c=color: {
                    "fillColor":   c,
                    "color":       "white",
                    "weight":      1.5,
                    "fillOpacity": 0.7,
                },
                tooltip=district_name,
                popup=folium.Popup(popup_html, max_width=220)
            ).add_to(m)
        else:
            folium.GeoJson(
                feature,
                style_function=lambda x: {
                    "fillColor":   "#cccccc",
                    "color":       "white",
                    "weight":      1.5,
                    "fillOpacity": 0.5,
                }
            ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed; bottom:30px; left:30px; z-index:1000;
                background:white; padding:10px 14px; border-radius:8px;
                border:1px solid #ccc; font-family:sans-serif; font-size:13px;">
        <b>ระดับความเสี่ยง</b><br>
        <span style="color:#E24B4A;">●</span> เสี่ยงสูง (score ≥ 0.75)<br>
        <span style="color:#EF9F27;">●</span> เสี่ยงปานกลาง (0.65–0.75)<br>
        <span style="color:#639922;">●</span> เสี่ยงต่ำ (< 0.65)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=500)

with col_chart:
    st.subheader("📈 Drought Score รายอำเภอ")

    fig = px.bar(
        df.sort_values("Drought_Score"),
        x="Drought_Score",
        y="อำเภอ",
        orientation="h",
        color="Drought_Score",
        color_continuous_scale=["#639922", "#EF9F27", "#E24B4A"],
        range_color=[0.2, 0.9],
        labels={"Drought_Score": "Drought Score", "อำเภอ": ""},
        height=500,
    )
    fig.add_vline(x=0.75, line_dash="dash", line_color="red",
                  annotation_text="เสี่ยงสูง")
    fig.add_vline(x=0.65, line_dash="dash", line_color="orange",
                  annotation_text="ปานกลาง")
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(l=0, r=10, t=10, b=10),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ============================================================
# กราฟ Rainfall Deficit
# ============================================================
st.subheader("🌧️ ปริมาณน้ำฝนขาดแคลนรายอำเภอ (เทียบค่าเฉลี่ย 2562–2566)")

fig2 = px.bar(
    df.sort_values("Rainfall_Deficit"),
    x="อำเภอ",
    y="Rainfall_Deficit",
    color="Rainfall_Deficit",
    color_continuous_scale=["#E24B4A", "#EF9F27", "#639922"],
    range_color=[-140, 0],
    labels={"Rainfall_Deficit": "ฝนขาดแคลน (mm)", "อำเภอ": ""},
    height=350,
)
fig2.add_hline(y=0, line_color="black", line_width=1)
fig2.update_layout(
    coloraxis_showscale=False,
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="white",
    xaxis_tickangle=-45,
)
st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ============================================================
# ตารางข้อมูลรายอำเภอ
# ============================================================
st.subheader("📋 ตารางข้อมูลรายอำเภอ")

display_df = df[[
    "อำเภอ", "ระดับความเสี่ยง",
    "Drought_Score", "NDVI_Dry", "NDMI_Dry",
    "Rainfall_2024_mm", "Rainfall_Deficit"
]].copy()

display_df.columns = [
    "อำเภอ", "ระดับความเสี่ยง",
    "Drought Score", "NDVI ฤดูแล้ง", "NDMI ฤดูแล้ง",
    "ฝนสะสม 2567 (mm)", "ฝนขาดแคลน (mm)"
]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=False,
)

st.divider()

# ============================================================
# อธิบายวิธีการ
# ============================================================
with st.expander("ℹ️ วิธีการวิเคราะห์และแหล่งข้อมูล"):
    st.markdown("""
    **ข้อมูลที่ใช้**
    - ภาพถ่ายดาวเทียม Sentinel-2 Level-2A (COPERNICUS/S2_SR_HARMONIZED) ความละเอียด 10–20 เมตร
    - ข้อมูลปริมาณน้ำฝน CHIRPS v3 ความละเอียดประมาณ 5.5 กิโลเมตร
    - ขอบเขตอำเภอจาก GADM 4.1

    **วิธีการคำนวณ**
    - NDVI = (Band 8 − Band 4) / (Band 8 + Band 4)
    - NDMI = (Band 8 − Band 11) / (Band 8 + Band 11)
    - Drought Score = 1 − mean(NDVI_normalized, NDMI_normalized)
    - Anomaly = ค่าปี 2567 − ค่าเฉลี่ยปี 2562–2566

    **ข้อจำกัด**
    - ผลลัพธ์เป็นการประเมินความเสี่ยงเชิงพืชพรรณและความชื้น ไม่ใช่การประกาศเขตภัยแล้งอย่างเป็นทางการ
    - ควรใช้ประกอบการตัดสินใจร่วมกับข้อมูลภาคสนามและรายงานจากหน่วยงานที่เกี่ยวข้อง

    **อ้างอิง**
    - Sentinel-2: European Space Agency (ESA)
    - CHIRPS: Climate Hazards Center, UC Santa Barbara
    - วิเคราะห์ด้วย Google Earth Engine · มหาวิทยาลัยราชภัฏบุรีรัมย์ 2567
    """)

# ============================================================
# Footer
# ============================================================
st.markdown("---")
st.markdown(
    "<div style=\'text-align:center; color:gray; font-size:12px;\'>"
    "ระบบสารสนเทศความเสี่ยงภัยแล้ง จังหวัดบุรีรัมย์ · "
    "วิเคราะห์ด้วย Google Earth Engine · "
    "มหาวิทยาลัยราชภัฏบุรีรัมย์ 2567"
    "</div>",
    unsafe_allow_html=True
)
