import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import json
import ee

# ============================================================
# Authenticate GEE ด้วย Service Account (อัตโนมัติ ถาวร)
# ============================================================
@st.cache_resource
def init_gee():
    secret = st.secrets["gee"]["service_account_json"]
    credentials = ee.ServiceAccountCredentials(
        email=json.loads(secret)["client_email"],
        key_data=secret
    )
    ee.Initialize(credentials)
    return True

gee_ready = init_gee()

# ============================================================
# โหลด Tile URL จาก GEE (cache 1 ชั่วโมง)
# ============================================================
@st.cache_data(ttl=3600)
def get_tiles():
    buriram_json = open("buriram_districts_23.json", "r").read()
    buriram_geojson = json.loads(buriram_json)
    buriram = ee.FeatureCollection(buriram_geojson)
    buriram_geom = buriram.union().first().geometry()

    def mask_clouds(image):
        scl = image.select("SCL")
        mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return image.updateMask(mask)

    s2_dry = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buriram_geom)
        .filterDate("2024-01-01", "2024-04-30")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_clouds).median().clip(buriram_geom))

    s2_wet = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buriram_geom)
        .filterDate("2024-08-01", "2024-10-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_clouds).median().clip(buriram_geom))

    s2_base = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(buriram_geom)
        .filter(ee.Filter.calendarRange(1, 4, "month"))
        .filterDate("2019-01-01", "2023-04-30")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_clouds).median().clip(buriram_geom))

    ndvi_dry  = s2_dry.normalizedDifference(["B8","B4"])
    ndmi_dry  = s2_dry.normalizedDifference(["B8","B11"])
    ndvi_wet  = s2_wet.normalizedDifference(["B8","B4"])
    ndvi_base = s2_base.normalizedDifference(["B8","B4"])
    ndmi_base = s2_base.normalizedDifference(["B8","B11"])

    pct = ndvi_dry.addBands(ndmi_dry).reduceRegion(
        reducer=ee.Reducer.percentile([5,95]),
        geometry=buriram_geom, scale=500, maxPixels=1e9)
    ndvi_p5  = ee.Number(pct.get("nd_p5"))
    ndvi_p95 = ee.Number(pct.get("nd_p95"))
    ndmi_p5  = ee.Number(pct.get("nd_1_p5"))
    ndmi_p95 = ee.Number(pct.get("nd_1_p95"))

    ndvi_norm = ndvi_dry.subtract(ndvi_p5).divide(ndvi_p95.subtract(ndvi_p5)).clamp(0,1)
    ndmi_norm = ndmi_dry.subtract(ndmi_p5).divide(ndmi_p95.subtract(ndmi_p5)).clamp(0,1)
    drought   = ndvi_norm.add(ndmi_norm).divide(2).multiply(-1).add(1).rename("Drought_Score")

    sp = drought.reduceRegion(
        reducer=ee.Reducer.percentile([33,66]),
        geometry=buriram_geom, scale=500, maxPixels=1e9)
    p33 = ee.Number(sp.get("Drought_Score_p33"))
    p66 = ee.Number(sp.get("Drought_Score_p66"))
    risk = (ee.Image(1).where(drought.gt(p33), 2)
                       .where(drought.gt(p66), 3)
                       .rename("Risk").clip(buriram_geom))

    ndvi_anom = ndvi_dry.subtract(ndvi_base)
    ndmi_anom = ndmi_dry.subtract(ndmi_base)

    chirps_2024 = (ee.ImageCollection("UCSB-CHC/CHIRPS/V3/DAILY_SAT")
        .filterBounds(buriram_geom)
        .filterDate("2024-01-01","2024-04-30")
        .select("precipitation").sum().clip(buriram_geom))
    chirps_base = (ee.ImageCollection("UCSB-CHC/CHIRPS/V3/DAILY_SAT")
        .filterBounds(buriram_geom)
        .filter(ee.Filter.calendarRange(1,4,"month"))
        .filterDate("2019-01-01","2023-04-30")
        .select("precipitation").sum().divide(5).clip(buriram_geom))
    rain_def = chirps_2024.subtract(chirps_base)

    def tile(img, vis):
        return img.getMapId(vis)["tile_fetcher"].url_format

    return {
        "risk":         tile(risk,      {"min":1,"max":3,"palette":["#639922","#EF9F27","#E24B4A"]}),
        "ndvi_dry":     tile(ndvi_dry,  {"min":0,"max":0.8,"palette":["#E24B4A","#FFFF00","#639922"]}),
        "ndvi_wet":     tile(ndvi_wet,  {"min":0,"max":0.8,"palette":["#E24B4A","#FFFF00","#639922"]}),
        "ndmi_dry":     tile(ndmi_dry,  {"min":-0.3,"max":0.3,"palette":["#E24B4A","#FFFF00","#639922"]}),
        "ndvi_anomaly": tile(ndvi_anom, {"min":-0.3,"max":0.3,"palette":["#E24B4A","#FFFFFF","#185FA5"]}),
        "ndmi_anomaly": tile(ndmi_anom, {"min":-0.3,"max":0.3,"palette":["#E24B4A","#FFFFFF","#185FA5"]}),
        "rainfall":     tile(rain_def,  {"min":-150,"max":50,"palette":["#E24B4A","#EF9F27","#FFFFFF","#185FA5"]}),
    }

# ============================================================
# โหลดข้อมูล CSV และ GeoJSON
# ============================================================
@st.cache_data
def load_data():
    df = pd.read_csv("district_drought_stats.csv", index_col=0)
    with open("buriram_districts_23.json","r",encoding="utf-8") as f:
        geojson = json.load(f)
    return df, geojson

df, geojson = load_data()

def get_risk_label(score):
    if score >= 0.75:   return "🔴 เสี่ยงสูง"
    elif score >= 0.65: return "🟡 เสี่ยงปานกลาง"
    else:               return "🟢 เสี่ยงต่ำ"

def get_risk_color(score):
    if score >= 0.75:   return "#E24B4A"
    elif score >= 0.65: return "#EF9F27"
    else:               return "#639922"

df["ระดับความเสี่ยง"] = df["Drought_Score"].apply(get_risk_label)
df["risk_color"]       = df["Drought_Score"].apply(get_risk_color)

# ============================================================
# UI
# ============================================================
st.set_page_config(
    page_title="ระบบสารสนเทศความเสี่ยงภัยแล้ง จังหวัดบุรีรัมย์",
    page_icon="🌾", layout="wide"
)

st.title("🌾 ระบบสารสนเทศความเสี่ยงภัยแล้งทางการเกษตร")
st.markdown("### จังหวัดบุรีรัมย์ · ฤดูแล้ง 2567 (2024)")
st.markdown(
    "วิเคราะห์จากดัชนีพืชพรรณ **NDVI** และดัชนีความชื้น **NDMI** "
    "จากภาพถ่ายดาวเทียม Sentinel-2 ผ่าน Google Earth Engine "
    "เปรียบเทียบกับค่าเฉลี่ยปี 2562–2566"
)
st.divider()

col1,col2,col3,col4,col5 = st.columns(5)
col1.metric("NDVI ฤดูแล้ง",   "0.37",    "vs ฤดูฝน 0.67")
col2.metric("NDMI ฤดูแล้ง",   "-0.089",  "ความชื้นต่ำ")
col3.metric("ฝนสะสม 2567",    "106 mm",  "-71.3 mm จากค่าเฉลี่ย", delta_color="inverse")
col4.metric("ขาดน้ำฝน",       "-40%",    "เทียบ baseline 2562–66", delta_color="inverse")
col5.metric("อำเภอเสี่ยงสูง", "8 อำเภอ", "จาก 23 อำเภอ")
st.divider()

tab1, tab2 = st.tabs([
    "🏘️ ภาพรวมสำหรับประชาชน",
    "🔬 โหมดผู้เชี่ยวชาญ (แผนที่ดาวเทียม)"
])

# --- TAB 1 ---
with tab1:
    col_map, col_chart = st.columns([3,2])
    with col_map:
        st.subheader("🗺️ แผนที่ความเสี่ยงภัยแล้งรายอำเภอ")
        m = folium.Map(location=[15.0,103.1], zoom_start=9, tiles="CartoDB positron")
        for feature in geojson["features"]:
            name = feature["properties"]["NAME_2"]
            row  = df[df["อำเภอ"] == name]
            if len(row) > 0:
                score   = row["Drought_Score"].values[0]
                color   = get_risk_color(score)
                deficit = row["Rainfall_Deficit"].values[0]
                ndvi    = row["NDVI_Dry"].values[0]
                risk    = row["ระดับความเสี่ยง"].values[0]
                popup_html = f"""
                <div style="font-family:sans-serif;min-width:180px;">
                <b style="font-size:14px;">{name}</b><br>
                <hr style="margin:4px 0;">
                <b>ระดับความเสี่ยง:</b> {risk}<br>
                <b>Drought Score:</b> {score:.3f}<br>
                <b>NDVI ฤดูแล้ง:</b> {ndvi:.3f}<br>
                <b>ฝนขาด:</b> {deficit:.1f} mm
                </div>"""
                folium.GeoJson(feature,
                    style_function=lambda x,c=color:{
                        "fillColor":c,"color":"white",
                        "weight":1.5,"fillOpacity":0.7},
                    tooltip=name,
                    popup=folium.Popup(popup_html,max_width=220)
                ).add_to(m)
        legend_html = """
        <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                    background:white;padding:10px 14px;border-radius:8px;
                    border:1px solid #ccc;font-family:sans-serif;font-size:13px;">
            <b>ระดับความเสี่ยง</b><br>
            <span style="color:#E24B4A;">●</span> เสี่ยงสูง (≥ 0.75)<br>
            <span style="color:#EF9F27;">●</span> ปานกลาง (0.65–0.75)<br>
            <span style="color:#639922;">●</span> เสี่ยงต่ำ (< 0.65)
        </div>"""
        m.get_root().html.add_child(folium.Element(legend_html))
        st_folium(m, width=None, height=500)

    with col_chart:
        st.subheader("📈 Drought Score รายอำเภอ")
        fig = px.bar(df.sort_values("Drought_Score"),
            x="Drought_Score", y="อำเภอ", orientation="h",
            color="Drought_Score",
            color_continuous_scale=["#639922","#EF9F27","#E24B4A"],
            range_color=[0.2,0.9], height=500,
            labels={"Drought_Score":"Drought Score","อำเภอ":""})
        fig.add_vline(x=0.75,line_dash="dash",line_color="red",annotation_text="เสี่ยงสูง")
        fig.add_vline(x=0.65,line_dash="dash",line_color="orange",annotation_text="ปานกลาง")
        fig.update_layout(coloraxis_showscale=False,plot_bgcolor="white",
                          margin=dict(l=0,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("🌧️ ปริมาณน้ำฝนขาดแคลนรายอำเภอ")
    fig2 = px.bar(df.sort_values("Rainfall_Deficit"),
        x="อำเภอ", y="Rainfall_Deficit",
        color="Rainfall_Deficit",
        color_continuous_scale=["#E24B4A","#EF9F27","#639922"],
        range_color=[-140,0], height=350,
        labels={"Rainfall_Deficit":"ฝนขาดแคลน (mm)","อำเภอ":""})
    fig2.add_hline(y=0,line_color="black",line_width=1)
    fig2.update_layout(coloraxis_showscale=False,plot_bgcolor="white",
                       margin=dict(l=0,r=0,t=10,b=0),xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("📋 ตารางข้อมูลรายอำเภอ")
    display_df = df[["อำเภอ","ระดับความเสี่ยง","Drought_Score",
                     "NDVI_Dry","NDMI_Dry","Rainfall_2024_mm","Rainfall_Deficit"]].copy()
    display_df.columns = ["อำเภอ","ระดับความเสี่ยง","Drought Score",
                          "NDVI ฤดูแล้ง","NDMI ฤดูแล้ง",
                          "ฝนสะสม 2567 (mm)","ฝนขาดแคลน (mm)"]
    st.dataframe(display_df, use_container_width=True)

# --- TAB 2 ---
with tab2:
    st.subheader("🔬 แผนที่ดาวเทียมความละเอียดสูง")
    st.info("แผนที่ในแท็บนี้แสดงข้อมูลระดับ pixel จาก Sentinel-2 ความละเอียด 10–20 เมตร zoom เข้าดูรายละเอียดระดับแปลงเกษตรได้")

    with st.spinner("กำลังโหลดแผนที่ดาวเทียม..."):
        TILES = get_tiles()

    layer_options = {
        "🔴 แผนที่ความเสี่ยงภัยแล้ง":              "risk",
        "🌿 NDVI ฤดูแล้ง 2567 (ม.ค.–เม.ย.)":       "ndvi_dry",
        "🌿 NDVI ฤดูฝน 2567 (ส.ค.–ต.ค.)":          "ndvi_wet",
        "💧 NDMI ความชื้นในพืช ฤดูแล้ง 2567":       "ndmi_dry",
        "📊 NDVI Anomaly (เบี่ยงเบนจากค่าเฉลี่ย)":  "ndvi_anomaly",
        "📊 NDMI Anomaly (เบี่ยงเบนความชื้น)":       "ndmi_anomaly",
        "🌧️ Rainfall Deficit (ฝนขาดแคลน)":         "rainfall",
    }
    legends = {
        "risk":         ("🟢 เสี่ยงต่ำ",          "🟡 ปานกลาง",        "🔴 เสี่ยงสูง"),
        "ndvi_dry":     ("🔴 พืชพรรณน้อย",        "🟡 ปานกลาง",        "🟢 พืชพรรณสมบูรณ์"),
        "ndvi_wet":     ("🔴 พืชพรรณน้อย",        "🟡 ปานกลาง",        "🟢 พืชพรรณสมบูรณ์"),
        "ndmi_dry":     ("🔴 ความชื้นต่ำ",         "🟡 ปานกลาง",        "🟢 ความชื้นสูง"),
        "ndvi_anomaly": ("🔴 แย่กว่าค่าเฉลี่ย",   "⚪ เท่าค่าเฉลี่ย",  "🔵 ดีกว่าค่าเฉลี่ย"),
        "ndmi_anomaly": ("🔴 ชื้นน้อยกว่าเฉลี่ย", "⚪ เท่าค่าเฉลี่ย",  "🔵 ชื้นมากกว่าเฉลี่ย"),
        "rainfall":     ("🔴 ฝนขาดมาก",           "🟡 ขาดปานกลาง",     "🔵 ฝนมากกว่าเฉลี่ย"),
    }

    selected = st.selectbox("เลือก Layer", list(layer_options.keys()))
    key = layer_options[selected]
    leg = legends[key]
    c1,c2,c3 = st.columns(3)
    c1.markdown(f"**ต่ำ →** {leg[0]}")
    c2.markdown(f"**กลาง →** {leg[1]}")
    c3.markdown(f"**สูง →** {leg[2]}")

    m2 = folium.Map(location=[15.0,103.1], zoom_start=9, tiles="CartoDB positron")
    folium.TileLayer(
        tiles=TILES[key], attr="Google Earth Engine",
        name=selected, overlay=True, opacity=0.8
    ).add_to(m2)
    folium.GeoJson(geojson,
        style_function=lambda x:{
            "fillColor":"transparent","color":"white",
            "weight":1.5,"fillOpacity":0},
        tooltip=folium.GeoJsonTooltip(fields=["NAME_2"],aliases=["อำเภอ:"])
    ).add_to(m2)
    folium.LayerControl().add_to(m2)
    st_folium(m2, width=None, height=600)

    st.divider()
    st.subheader("📉 Cross-validation: Drought Score vs Rainfall Deficit")
    st.markdown("Spearman r = **0.57**, p = **0.013** (n=18) · มีนัยสำคัญทางสถิติ")
    fig3 = px.scatter(df, x="Rainfall_Deficit", y="Drought_Score",
        text="อำเภอ", color="Drought_Score",
        color_continuous_scale=["#639922","#EF9F27","#E24B4A"],
        range_color=[0.2,0.9], height=400,
        labels={"Rainfall_Deficit":"Rainfall Deficit (mm)","Drought_Score":"Drought Score"})
    fig3.update_traces(textposition="top center", textfont_size=10)
    fig3.update_layout(coloraxis_showscale=False, plot_bgcolor="white")
    st.plotly_chart(fig3, use_container_width=True)

with st.expander("ℹ️ วิธีการวิเคราะห์และแหล่งข้อมูล"):
    st.markdown("""
    **ข้อมูลที่ใช้**
    - Sentinel-2 Level-2A (COPERNICUS/S2_SR_HARMONIZED) ความละเอียด 10–20 เมตร
    - CHIRPS v3 Daily Precipitation ความละเอียดประมาณ 5.5 กิโลเมตร
    - ขอบเขตอำเภอจาก GADM 4.1

    **วิธีการคำนวณ**
    - NDVI = (B8 − B4) / (B8 + B4)
    - NDMI = (B8 − B11) / (B8 + B11)
    - Drought Score = 1 − mean(NDVI_norm, NDMI_norm)
    - Anomaly = ค่าปี 2567 − ค่าเฉลี่ยปี 2562–2566

    **ข้อจำกัด**
    - ผลลัพธ์เป็นการประเมินความเสี่ยงเชิงพืชพรรณ ไม่ใช่ประกาศเขตภัยแล้งอย่างเป็นทางการ

    **อ้างอิง**
    - Sentinel-2: European Space Agency (ESA)
    - CHIRPS: Climate Hazards Center, UC Santa Barbara
    - วิเคราะห์ด้วย Google Earth Engine · มหาวิทยาลัยราชภัฏบุรีรัมย์ 2567
    """)

st.markdown("---")
st.markdown(
    "<div style=\'text-align:center;color:gray;font-size:12px;\'>"
    "ระบบสารสนเทศความเสี่ยงภัยแล้ง จังหวัดบุรีรัมย์ · "
    "Google Earth Engine · มหาวิทยาลัยราชภัฏบุรีรัมย์ 2567"
    "</div>", unsafe_allow_html=True)
