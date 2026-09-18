import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Weight Tracker", page_icon="⚖️", layout="centered")

# --- Custom Styling Polish ---
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 1.85rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetricLabel"] {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }
    div[data-testid="stForm"] {
        border-radius: 12px;
        padding: 1.25rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚖️ Daily Weight Tracker")

# 1. Google Sheets Connection
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data() -> pd.DataFrame:
    try:
        data = conn.read(ttl=0)
        if data is None or data.empty:
            return pd.DataFrame(columns=["date", "weight"])
        data = data.dropna(subset=["date", "weight"]).copy()
        data["date"] = pd.to_datetime(data["date"])
        data["weight"] = pd.to_numeric(data["weight"])
        return data.sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "weight"])

df = load_data()

# 2. Daily Input Card
with st.container(border=True):
    st.subheader("Log Weight Entry", divider="gray")
    with st.form("weight_entry_form", clear_on_submit=True, border=False):
        c_date, c_weight = st.columns(2)
        with c_date:
            entry_date = st.date_input("Date", value=date.today())
        with c_weight:
            default_val = float(df.iloc[-1]["weight"]) if not df.empty else 80.0
            weight_val = st.number_input(
                "Morning Weight (kg)",
                min_value=30.0,
                max_value=250.0,
                value=default_val,
                step=0.1,
                format="%.1f"
            )
        
        submitted = st.form_submit_button("Record Weight", use_container_width=True, type="primary")

        if submitted:
            entry_ts = pd.to_datetime(entry_date)

            if not df.empty and entry_ts in df["date"].values:
                df.loc[df["date"] == entry_ts, "weight"] = float(weight_val)
            else:
                new_row = pd.DataFrame([{"date": entry_ts, "weight": float(weight_val)}])
                df = pd.concat([df, new_row], ignore_index=True)

            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")

            upload_df = df.copy()
            upload_df["date"] = upload_df["date"].dt.strftime("%Y-%m-%d")

            conn.update(data=upload_df)
            st.toast(f"Logged {weight_val:.1f} kg for {str(entry_date)}", icon="✅")
            st.rerun()

# 3. Dashboard View
if not df.empty:
    # Calculations
    df["iso_year"] = df["date"].dt.isocalendar().year
    df["iso_week"] = df["date"].dt.isocalendar().week
    df["kw_label"] = df.apply(lambda r: f"KW {r['iso_week']:02d}", axis=1)

    weekly_agg = (
        df.groupby(["iso_year", "iso_week", "kw_label"], as_index=False)
        .agg(avg_weight=("weight", "mean"), count=("weight", "count"))
        .sort_values(["iso_year", "iso_week"])
        .reset_index(drop=True)
    )

    latest_weight = df.iloc[-1]["weight"]
    latest_kw_avg = weekly_agg.iloc[-1]["avg_weight"]
    current_kw_label = weekly_agg.iloc[-1]["kw_label"]

    if len(weekly_agg) >= 5:
        base_kw_row = weekly_agg.iloc[-5]
    elif len(weekly_agg) > 1:
        base_kw_row = weekly_agg.iloc[0]
    else:
        base_kw_row = None

    bulk_help = (
        "Optimal lean bulk rate: ~1.0% to 2.0% body weight increase per month "
        "to maximize muscle accretion while limiting fat gain. "
        "Calculated by comparing the current weekly average with the baseline week."
    )

    # Overview Metrics Card
    with st.container(border=True):
        head_col1, head_col2 = st.columns([2, 1])
        with head_col1:
            st.subheader("Performance Overview")
        with head_col2:
            metric_unit = st.segmented_control(
                "Metric Unit",
                options=["%", "kg"],
                default="%",
                label_visibility="collapsed"
            )

        col1, col2, col3 = st.columns(3)
        col1.metric("Latest Log", f"{latest_weight:.1f} kg")
        col2.metric(f"Current {current_kw_label}", f"{latest_kw_avg:.2f} kg")

        if base_kw_row is not None and base_kw_row["avg_weight"] > 0:
            base_avg = base_kw_row["avg_weight"]
            delta_abs = latest_kw_avg - base_avg
            delta_pct = (delta_abs / base_avg) * 100.0
            kw_distance = (len(weekly_agg) - 1) if len(weekly_agg) < 5 else 4
            delta_label = f"Monthly Gain ({kw_distance}w)"

            if metric_unit == "%":
                col3.metric(
                    label=delta_label,
                    value=f"{delta_pct:+.2f}%",
                    delta=f"{delta_abs:+.2f} kg (Target: +1.0% to +2.0%)",
                    help=bulk_help
                )
            else:
                col3.metric(
                    label=delta_label,
                    value=f"{delta_abs:+.2f} kg",
                    delta=f"{delta_pct:+.2f}% (Target: +1.0% to +2.0%)",
                    help=bulk_help
                )
        else:
            col3.metric(
                label="Monthly Gain",
                value="N/A",
                delta="Need ≥ 2 weeks",
                help=bulk_help
            )

    # Weekly Summary Table Card
    with st.container(border=True):
        st.subheader("Kalenderwochen Historie")
        kw_table = weekly_agg[["kw_label", "avg_weight"]].copy()
        kw_table["avg_weight"] = kw_table["avg_weight"].round(2).map("{:.2f} kg".format)
        kw_display = kw_table.set_index("kw_label").T
        kw_display.index = ["Ø Schnitt"]
        st.dataframe(kw_display, use_container_width=True)

    # Visual Chart Card
    with st.container(border=True):
        view_col1, view_col2 = st.columns([1.5, 2.5])
        with view_col1:
            st.subheader("Visual Trajectory")
        with view_col2:
            view_mode = st.radio(
                "Select Resolution:",
                options=["Täglich (Daily View)", "Kalenderwoche (Weekly Average)"],
                horizontal=True,
                label_visibility="collapsed"
            )

        y_axis_config = alt.Y(
            "weight:Q",
            scale=alt.Scale(domain=[77, 85], clamp=False),
            axis=alt.Axis(
                values=list(range(77, 86)),
                title="Weight (kg)",
                format=".0f",
                grid=True,
                gridDash=[2, 2]
            )
        )

        if view_mode == "Täglich (Daily View)":
            chart_data = df[["date", "weight"]].copy()
            chart_data["DisplayDate"] = chart_data["date"].dt.strftime("%Y-%m-%d")

            chart = (
                alt.Chart(chart_data)
                .mark_line(
                    point=alt.OverlayMarkDef(filled=True, size=65, stroke="white", strokeWidth=1.5),
                    strokeWidth=3,
                    interpolate="monotone",
                    color="#2563EB"
                )
                .encode(
                    x=alt.X("DisplayDate:N", title="Datum", sort=None),
                    y=y_axis_config,
                    tooltip=[
                        alt.Tooltip("DisplayDate:N", title="Date"),
                        alt.Tooltip("weight:Q", format=".1f", title="Weight (kg)")
                    ]
                )
                .properties(height=360)
            )
        else:
            chart_data = weekly_agg.rename(columns={"avg_weight": "weight"}).copy()

            chart = (
                alt.Chart(chart_data)
                .mark_line(
                    point=alt.OverlayMarkDef(filled=True, size=75, stroke="white", strokeWidth=1.5),
                    strokeWidth=3,
                    interpolate="monotone",
                    color="#D97706"
                )
                .encode(
                    x=alt.X("kw_label:N", title="Kalenderwoche", sort=None),
                    y=y_axis_config,
                    tooltip=[
                        alt.Tooltip("kw_label:N", title="Week"),
                        alt.Tooltip("weight:Q", format=".2f", title="Ø Weight (kg)"),
                        alt.Tooltip("count:Q", title="Days Logged")
                    ]
                )
                .properties(height=360)
            )

        st.altair_chart(chart, use_container_width=True)

    with st.expander("Full Data Log"):
        display_df = df[["date", "weight", "kw_label"]].copy()
        display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            display_df.sort_values("date", ascending=False).reset_index(drop=True),
            use_container_width=True
        )
