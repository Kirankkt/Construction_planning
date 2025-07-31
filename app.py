"""
construction_agent_app.py
=========================

This Streamlit application provides a simple user interface for the construction
manager prototype defined in ``construction_agent.py``.  It allows users to
upload a colour‑coded Excel schedule, configure schedule parameters and cost
assumptions and generate a summary report on demand.

The app performs the following steps:

1. Accepts an Excel file upload from the user.
2. Collects project parameters such as the Day 1 start date, working hours per
   day, base hourly labour rate in INR, labour‑burden percentage, inefficiency
   factor and contingency rate.
3. Parses the schedule into activities, assigns calendar dates, infers
   sequential dependencies, computes the critical path, estimates labour
   hours and costs and applies contingency.
4. Displays the activity list in a data frame and shows total hours, total
   cost, contingency amount and total cost including contingency.

Note: This app requires the ``streamlit`` package.  If it is not installed
in your environment, install it via ``pip install streamlit``.  To run the
app locally, execute ``streamlit run construction_agent_app.py`` in a
terminal.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from typing import Optional

import pandas as pd
import streamlit as st

from construction_agent import (
    Activity,
    assign_dates,
    compute_cpm,
    estimate_costs,
    infer_dependencies,
    parse_schedule,
    compute_contingency,
    plot_gantt,
)


def process_schedule(
    file_path: str,
    start_date: dt.date,
    hours_per_day: float,
    base_rate: float,
    labour_burden: float,
    inefficiency: float,
    contingency: float,
) -> tuple[pd.DataFrame, float, float, float]:
    """
    Core processing logic extracted for use by the Streamlit app.

    Parameters
    ----------
    file_path : str
        Path to the uploaded Excel schedule.
    start_date : datetime.date
        Calendar date corresponding to Day 1.
    hours_per_day, base_rate, labour_burden, inefficiency, contingency
        Parameters passed through to the cost estimator and contingency calculator.

    Returns
    -------
    tuple[pandas.DataFrame, float, float, float]
        The data frame of activities with schedule and cost details, total
        labour hours, total cost before contingency and total cost including
        contingency.
    """
    # Parse activities from schedule
    activities = parse_schedule(file_path)
    # Assign original dates based on Day1 mapping (not necessary since we'll
    # override with CPM dates later)
    assign_dates(activities, start_date)
    # Infer simple sequential dependencies
    deps = infer_dependencies(activities)
    # Compute CPM schedule (sequential model)
    compute_cpm(activities, deps)
    # Override start and end dates using ES/EF from CPM
    for act in activities:
        if act.es is not None:
            act.start_date = start_date + dt.timedelta(days=act.es - 1)
        if act.ef is not None:
            act.end_date = start_date + dt.timedelta(days=act.ef - 1)
    # Estimate labour costs
    total_hours, total_cost = estimate_costs(
        activities,
        hours_per_day=hours_per_day,
        base_rate=base_rate,
        labour_burden=labour_burden,
        inefficiency=inefficiency,
    )
    contingency_amount = compute_contingency(total_cost, contingency)
    total_with_contingency = total_cost + contingency_amount
    # Build data frame for display including CPM fields
    df = pd.DataFrame(
        {
            "Activity": [a.name for a in activities],
            "Start": [a.start_date for a in activities],
            "Finish": [a.end_date for a in activities],
            "Duration (days)": [a.duration for a in activities],
            "ES": [a.es for a in activities],
            "EF": [a.ef for a in activities],
            "LS": [a.ls for a in activities],
            "LF": [a.lf for a in activities],
            "Slack": [a.slack for a in activities],
            "Labour hours": [a.labour_hours for a in activities],
            "Cost (INR)": [a.labour_cost for a in activities],
            "Critical": ["YES" if a.slack == 0 else "no" for a in activities],
        }
    )
    return df, total_hours, total_cost, total_with_contingency


def main() -> None:
    st.set_page_config(page_title="Construction Manager Agent", layout="wide")
    st.title("AI‑Powered Construction Manager (Trivandrum, Kerala)")
    st.markdown(
        """
        Upload a colour‑coded Excel schedule and configure project parameters to
        generate a critical‑path schedule, labour‑cost estimate and contingency
        allowance.  The default rates reflect typical wages for construction
        workers in Kerala (around ₹893.6 per day【353133779557527†L274-L277】), but you can
        customise them to suit your project.
        """
    )

    uploaded_file = st.file_uploader(
        "Upload schedule (Excel)",
        type=["xlsx", "xls"],
        help="Upload the colour‑coded Excel schedule you want to analyse.",
    )
    # Parameter inputs
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date: dt.date = st.date_input(
            "Start date for Day 1",
            value=dt.date.today(),
            help="Calendar date corresponding to Day 1 of the schedule.",
        )
        hours_per_day = st.number_input(
            "Working hours per day",
            min_value=1.0,
            max_value=12.0,
            value=8.0,
            step=0.5,
            help="Number of working hours per day (must not exceed 9 hours per day as per labour law).",
        )
    with col2:
        base_rate = st.number_input(
            "Base hourly rate (INR)",
            min_value=50.0,
            max_value=10000.0,
            value=112.0,
            step=1.0,
            help="Hourly wage for the crew (in INR).  The default is based on Kerala’s average construction wage divided by 8 hours.",
        )
        labour_burden = st.number_input(
            "Labour burden (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.01,
            help="Fractional labour burden covering payroll taxes, insurance and other employer costs (e.g., 0.2 for 20%).",
        )
    with col3:
        inefficiency = st.number_input(
            "Inefficiency factor (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.01,
            help="Fractional allowance for unproductive time (e.g., 0.2 for 20%).",
        )
        contingency = st.number_input(
            "Contingency rate (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.07,
            step=0.01,
            help="Fraction of total cost to set aside as contingency (e.g., 0.07 for 7%).",
        )

    if uploaded_file is not None:
        # Write the uploaded file to a temporary location for openpyxl
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        if st.button("Generate Report"):
            try:
                df, total_hours, total_cost, total_with_contingency = process_schedule(
                    tmp_path,
                    start_date,
                    hours_per_day,
                    base_rate,
                    labour_burden,
                    inefficiency,
                    contingency,
                )
                # Store the dataframe and activities in session state for later interactions
                st.session_state['df'] = df
                st.session_state['total_hours'] = total_hours
                st.session_state['total_cost'] = total_cost
                st.session_state['total_with_contingency'] = total_with_contingency
                # Initialize completed status dict if not present
                if 'completed' not in st.session_state:
                    st.session_state['completed'] = {act: False for act in df['Activity']}
            except Exception as e:
                st.error(f"An error occurred while processing the schedule: {e}")

    # If we have processed a schedule, provide interactive features
    if 'df' in st.session_state:
        df = st.session_state['df']
        total_hours = st.session_state['total_hours']
        total_cost = st.session_state['total_cost']
        total_with_contingency = st.session_state['total_with_contingency']
        completed = st.session_state['completed']

        st.subheader("Activity Schedule and Cost Summary")
        # Display explanation of tuning parameters in an expander
        with st.expander("What do labour burden, inefficiency and contingency mean?"):
            st.markdown(
                """
                **Labour burden** represents the employer’s additional costs beyond
                wages, including payroll taxes, insurance and statutory fees (often
                around 20 % of wages)【143656559969249†L250-L284】.  
                **Inefficiency factor** accounts for unproductive time—studies show
                workers may lose around 42 minutes per day【143656559969249†L286-L312】, so
                adding about 20 % helps capture this hidden cost.  
                **Contingency** is a reserve set aside to cover unforeseen
                conditions or changes.  Renovation projects typically include
                about 7–8 % of construction cost as contingency【537146304403148†L190-L209】.
                You can adjust these values based on experience and risk tolerance.
                """
            )
        # Date selector for marking tasks complete
        st.markdown("### Progress Tracking")
        sel_date = st.date_input("Select date to mark all scheduled tasks as complete", value=start_date)
        if st.button("Mark tasks on selected date as complete"):
            # Mark tasks whose schedule spans selected date as completed
            for i, row in df.iterrows():
                if row['Start'] <= sel_date <= row['Finish']:
                    completed[row['Activity']] = True
        if st.button("Reset completion status"):
            for key in completed.keys():
                completed[key] = False
        # Display checkboxes for individual task completion
        st.markdown("### Mark individual tasks as complete")
        # Create two columns for readability
        col_a, col_b = st.columns(2)
        for idx, activity in enumerate(df['Activity']):
            checkbox_col = col_a if idx % 2 == 0 else col_b
            checked = completed.get(activity, False)
            new_val = checkbox_col.checkbox(activity, value=checked)
            completed[activity] = new_val
        st.session_state['completed'] = completed

        # Update DataFrame to include completion status
        df_display = df.copy()
        df_display['Completed'] = df_display['Activity'].map(completed)

        st.markdown("### Activities Table (with CPM analysis)")
        st.dataframe(df_display)
        st.markdown(
            f"**Total labour hours:** {total_hours:.1f} h\n\n"
            f"**Total labour cost:** ₹{total_cost:,.2f}\n\n"
            f"**Total including contingency:** ₹{total_with_contingency:,.2f}"
        )
        # Plot and display the Gantt chart using Activity objects with correct dates
        try:
            acts_for_plot = []
            for _, row in df_display.iterrows():
                a = Activity(name=row['Activity'], start_day=1, end_day=1)
                a.start_date = row['Start']
                a.end_date = row['Finish']
                acts_for_plot.append(a)
            fig = plot_gantt(acts_for_plot, completed=completed, title="Project Gantt Chart")
            st.pyplot(fig)
        except Exception as e:
            st.error(f"Error plotting Gantt chart: {e}")
    else:
        st.info("Please upload an Excel schedule and click Generate Report.")


if __name__ == "__main__":
    main()
