import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# ----------------------------------------------------
# PAGE CONFIG & CUSTOM STYLES
# ----------------------------------------------------
st.set_page_config(page_title="Fitness Hub", page_icon="⚡", layout="centered")

st.markdown("""
<style>
    .history-card {
        background-color: #f3f4f6;
        border-left: 4px solid #6b7280;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 12px;
        font-size: 13px;
        color: #374151;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------
# GSHEETS CONNECTION & DATA HELPERS
# ----------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name, default_cols):
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame(columns=default_cols)
        df = df.dropna(how="all")
        for col in default_cols:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=default_cols)

df_weights = load_data("weights", ["date", "weight"])
df_workouts = load_data("workouts", ["date", "split_type", "completed"])
df_exercises = load_data("exercise_logs", ["date", "exercise", "set_number", "weight_kg", "reps", "notes"])

# ----------------------------------------------------
# NAVIGATION TABS
# ----------------------------------------------------
tab_weight, tab_gym = st.tabs(["⚖️ Daily Weight Tracker", "🏋️ Gym & Workout Log"])

# ====================================================
# TAB 1: WEIGHT TRACKER
# ====================================================
with tab_weight:
    st.title("⚖️ Daily Weight Tracker")

    with st.form("weight_form", clear_on_submit=False):
        col_d, col_w = st.columns(2)
        with col_d:
            w_date = st.date_input("Date", date.today(), key="original_w_date")
        with col_w:
            w_val = st.number_input("Morning Weight (kg)", min_value=40.0, max_value=150.0, value=80.0, step=0.1, format="%.1f")
        submit_weight = st.form_submit_button("Record Weight", use_container_width=True)

        if submit_weight:
            date_str = w_date.strftime("%Y-%m-%d")
            df_weights_clean = df_weights[df_weights["date"] != date_str].copy()
            new_entry = pd.DataFrame([{"date": date_str, "weight": float(w_val)}])
            updated_weights = pd.concat([df_weights_clean, new_entry], ignore_index=True)
            conn.update(worksheet="weights", data=updated_weights)
            st.success(f"Recorded {w_val} kg for {date_str}!")
            st.rerun()

    if not df_weights.empty:
        df_calc = df_weights.copy()
        df_calc["date"] = pd.to_datetime(df_calc["date"])
        df_calc["weight"] = pd.to_numeric(df_calc["weight"])
        df_calc = df_calc.sort_values("date").reset_index(drop=True)

        latest_wt = df_calc.iloc[-1]["weight"]

        # Kalenderwochen aufbereiten
        df_calc["KW"] = df_calc["date"].dt.isocalendar().week
        df_calc["Year"] = df_calc["date"].dt.isocalendar().year

        # Wöchentliche Durchschnitte aggregieren
        kw_grouped = df_calc.groupby(["Year", "KW"])["weight"].mean().reset_index().sort_values(["Year", "KW"])
        current_weekly_avg = kw_grouped.iloc[-1]["weight"]

        # 4-Wochen Durchschnitts-Vergleich
        if len(kw_grouped) >= 5:
            baseline_kw_avg = kw_grouped.iloc[-5]["weight"]
            monthly_diff_kg = current_weekly_avg - baseline_kw_avg
            monthly_diff_pct = (monthly_diff_kg / baseline_kw_avg) * 100
        elif len(kw_grouped) > 1:
            baseline_kw_avg = kw_grouped.iloc[0]["weight"]
            monthly_diff_kg = current_weekly_avg - baseline_kw_avg
            monthly_diff_pct = (monthly_diff_kg / baseline_kw_avg) * 100
        else:
            monthly_diff_kg = 0.0
            monthly_diff_pct = 0.0

        st.markdown("---")

        # TOGGLE: % vs. absolute (kg)
        gain_format = st.radio("Monthly Gain Display", ["Absolute (kg)", "Percentage (%)"], horizontal=True)

        # METRICS: Current Weight (links) | Weekly Average mit "i" (mitte) | Monthly Gain mit "i" (rechts)
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Weight", f"{latest_wt:.1f} kg")
        m2.metric(
            "Weekly Average", 
            f"{current_weekly_avg:.2f} kg",
            help="Average morning weight for the current calendar week. Filters out daily water and sodium fluctuations."
        )
        if gain_format == "Absolute (kg)":
            m3.metric(
                "Monthly Gain", 
                f"{monthly_diff_kg:+.2f} kg",
                help="Calculated as (Current KW Avg - KW Avg 4 Weeks Prior). Target: 1.0% - 2.0% body weight gain per month for a lean bulk."
            )
        else:
            m3.metric(
                "Monthly Gain", 
                f"{monthly_diff_pct:+.2f} %",
                help="Calculated as ((Current KW Avg - KW Avg 4 Weeks Prior) / KW Avg 4 Weeks Prior) * 100. Target: 1.0% - 2.0% body weight gain per month for a lean bulk."
            )

        st.markdown("---")
        st.subheader("Weight Progression Chart")

        # TOGGLE: Daily vs. Calendar Weeks
        chart_view = st.radio("Chart Resolution", ["Daily", "Calendar Weeks (KW Average)"], horizontal=True)

        if chart_view == "Daily":
            chart = alt.Chart(df_calc).mark_line(point=True, color="#e04848").encode(
                x=alt.X("date:T", title="Date", axis=alt.Axis(format="%d %b")),
                y=alt.Y("weight:Q", scale=alt.Scale(domain=[76, 83]), title="Weight (kg)"),
                tooltip=[alt.Tooltip("date:T", format="%Y-%m-%d"), alt.Tooltip("weight:Q", format=".2f")]
            ).properties(height=320)
        else:
            kw_trend = df_calc.groupby(["Year", "KW"]).agg(
                weight=("weight", "mean"),
                date=("date", "min")
            ).reset_index().sort_values(["Year", "KW"])
            kw_trend["KW_Label"] = kw_trend.apply(lambda r: f"KW {int(r['KW'])}", axis=1)

            chart = alt.Chart(kw_trend).mark_line(point=True, color="#e04848").encode(
                x=alt.X("KW_Label:N", title="Calendar Week", sort=None),
                y=alt.Y("weight:Q", scale=alt.Scale(domain=[76, 83]), title="Average Weight (kg)"),
                tooltip=["KW_Label:N", alt.Tooltip("weight:Q", format=".2f", title="Ø Weight")]
            ).properties(height=320)

        st.altair_chart(chart, use_container_width=True)

        # KALENDERWOCHEN TABELLE
        st.subheader("Calendar Week (KW) Summary")
        kw_summary = df_calc.groupby(["Year", "KW"])["weight"].agg(
            Average="mean",
            Min="min",
            Max="max",
            Entries="count"
        ).reset_index().sort_values(["Year", "KW"], ascending=False)
        kw_summary["Average"] = kw_summary["Average"].round(2)
        kw_summary["Range"] = kw_summary.apply(lambda r: f"{r['Min']:.1f} - {r['Max']:.1f} kg", axis=1)
        st.dataframe(
            kw_summary[["Year", "KW", "Average", "Range", "Entries"]],
            use_container_width=True,
            hide_index=True
        )


# ====================================================
# TAB 2: GYM & WORKOUT LOG
# ====================================================
with tab_gym:
    st.header("Daily Gym Log")

    EXERCISE_SPLITS = {
        "Upper Body": [
            "Dumbbells Bench Press",
            "Overhead Shoulder Press Dumbbells",
            "Seitheben",
            "Latzug",
            "Rudern",
            "Butterfly Chest",
            "Trizeps Overhead Cable Extensions",
            "Trizeps Pushdowns",
            "Cable Curls Bizeps",
            "Hammer Curls",
            "Custom"
        ],
        "Lower Body": [
            "Squat",
            "Leg Extensions Machine",
            "Leg Curls Machine",
            "Calves",
            "Roll Outs (Abs)",
            "Normal Crunches",
            "Custom"
        ],
        "Weaknesses / Custom Split": [
            "Seitheben",
            "Cable Curls Bizeps",
            "Hammer Curls",
            "Roll Outs (Abs)",
            "Calves",
            "Custom"
        ]
    }

    weekday_num = datetime.now().weekday()
    default_split_idx = 0
    if weekday_num in [0, 3]:
        default_split_idx = 0
    elif weekday_num in [1, 4]:
        default_split_idx = 1
    elif weekday_num == 5:
        default_split_idx = 2

    c_date, c_split = st.columns(2)
    with c_date:
        workout_date = st.date_input("Workout Date", date.today(), key="wk_date")
    with c_split:
        selected_split = st.selectbox(
            "Session Focus",
            options=list(EXERCISE_SPLITS.keys()),
            index=default_split_idx
        )

    # Swipe Slider
    st.markdown("##### Session Completion")
    swipe_val = st.slider(
        "Swipe right when session is done 👉",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        format="%d%%"
    )

    if swipe_val >= 95:
        st.success("🔥 Workout Completed!")
        if st.button("Confirm & Save Workout Day"):
            date_str = workout_date.strftime("%Y-%m-%d")
            df_workouts_clean = df_workouts[df_workouts["date"] != date_str].copy()
            new_workout = pd.DataFrame([{
                "date": date_str,
                "split_type": selected_split,
                "completed": "TRUE"
            }])
            updated_workouts = pd.concat([df_workouts_clean, new_workout], ignore_index=True)
            conn.update(worksheet="workouts", data=updated_workouts)
            st.toast("Workout consistency logged!")
            st.rerun()

    st.markdown("---")
    st.subheader("Log Exercise Sets")

    split_options = EXERCISE_SPLITS.get(selected_split, [])
    selected_option = st.selectbox("Select Exercise", options=split_options)

    # CUSTOM ÜBUNG
    if selected_option == "Custom":
        active_exercise = st.text_input("Name your Custom Exercise:", placeholder="e.g., Incline Dumbbell Bench")
    else:
        active_exercise = selected_option

    # HISTORIE DER ÜBUNG (IN GRAU)
    if active_exercise and not df_exercises.empty:
        history_match = df_exercises[df_exercises["exercise"].astype(str).str.strip().str.lower() == active_exercise.strip().lower()].copy()
        
        if not history_match.empty:
            history_match["date_dt"] = pd.to_datetime(history_match["date"])
            sorted_dates = history_match.sort_values("date_dt", ascending=False)["date"].unique()

            last_date_str = sorted_dates[0]
            last_sets = history_match[history_match["date"] == last_date_str].sort_values("set_number")
            summary_str = " • ".join([
                f"Satz {r['set_number']}: {r['weight_kg']} kg × {r['reps']}"
                for _, r in last_sets.iterrows()
            ])
            last_note = last_sets.iloc[-1].get("notes", "")
            note_str = f"<br><em>Note: {last_note}</em>" if pd.notna(last_note) and str(last_note).strip() else ""

            st.markdown(
                f"""<div class="history-card">
                    <strong>Last Session ({last_date_str}):</strong><br>
                    {summary_str}{note_str}
                </div>""",
                unsafe_allow_html=True
            )

            if len(sorted_dates) > 1:
                with st.expander("🕒 View Older Sessions"):
                    for prev_d in sorted_dates[1:]:
                        prev_sets = history_match[history_match["date"] == prev_d].sort_values("set_number")
                        prev_sum = " • ".join([
                            f"Satz {r['set_number']}: {r['weight_kg']} kg × {r['reps']}"
                            for _, r in prev_sets.iterrows()
                        ])
                        p_note = prev_sets.iloc[-1].get("notes", "")
                        p_note_str = f" — <em>{p_note}</em>" if pd.notna(p_note) and str(p_note).strip() else ""
                        st.markdown(f"- **{prev_d}**: {prev_sum}{p_note_str}", unsafe_allow_html=True)
        else:
            st.caption("No previous entries found for this exercise.")

    with st.form("set_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            set_num = st.number_input("Set #", min_value=1, max_value=12, value=1, step=1)
        with c2:
            weight_val = st.number_input("Weight (kg)", min_value=0.0, max_value=400.0, value=20.0, step=2.5)
        with c3:
            reps_val = st.number_input("Reps", min_value=1, max_value=50, value=10, step=1)

        set_note = st.text_input("Notes (optional, e.g., 'Felt easy, increase weight')")
        submit_set = st.form_submit_button("Record Set", use_container_width=True)

        if submit_set:
            if not active_exercise or not active_exercise.strip():
                st.error("Please provide an exercise name.")
            else:
                date_str = workout_date.strftime("%Y-%m-%d")
                new_log = pd.DataFrame([{
                    "date": date_str,
                    "exercise": active_exercise.strip(),
                    "set_number": int(set_num),
                    "weight_kg": float(weight_val),
                    "reps": int(reps_val),
                    "notes": set_note
                }])
                updated_ex = pd.concat([df_exercises, new_log], ignore_index=True)
                conn.update(worksheet="exercise_logs", data=updated_ex)
                st.success(f"Recorded Set {set_num} for {active_exercise} ({weight_val} kg × {reps_val})")
                st.rerun()

    current_date_str = workout_date.strftime("%Y-%m-%d")
    todays_sets = df_exercises[df_exercises["date"] == current_date_str]
    if not todays_sets.empty:
        st.markdown("##### Logged Today")
        st.dataframe(
            todays_sets[["exercise", "set_number", "weight_kg", "reps", "notes"]],
            use_container_width=True,
            hide_index=True
        )

    st.markdown("---")
    st.subheader("Weekly Gym Consistency")
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    days_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    cal_cols = st.columns(7)
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        logged_day = df_workouts[df_workouts["date"] == day_str]
        hit_gym = not logged_day.empty and logged_day.iloc[0].get("completed") in [True, "TRUE", "True", 1]

        with cal_cols[i]:
            symbol = "✅" if hit_gym else "⚪"
            st.markdown(f"<div style='text-align:center;'><b>{days_labels[i]}</b><br>{symbol}</div>", unsafe_allow_html=True)
