import os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- SETUP ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1YCVNif65X6To2mMjRmF0QqhylkBhhRSTdtVWMtTKecA/edit"
STATUSES = ["Full", "Half", "Low", "Very Low", "None"]
MATERIALS = ["PLA", "PETG", "PVB", "ASA", "ABS"]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DATA_START_ROW = 5  # Columns: A=Material, B=Brand, C=Color, D-G=Spool 1-4, H=Link

LOCAL_CREDENTIALS_FILE = "aerobic-tesla-507420-r2-ffd3cdfd04d5.json"

STATUS_COLORS = {
    "Full": "#C6EFCE",
    "Half": "#FFEB9C",
    "Low": "#FFD599",
    "Very Low": "#FFC7CE",
    "None": "#D9D9D9",
}


@st.cache_resource
def connect():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(script_dir, LOCAL_CREDENTIALS_FILE)

    if os.path.exists(local_path):
        creds = Credentials.from_service_account_file(local_path, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )

    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).sheet1


def get_rows(sheet):
    return sheet.get_all_values()[DATA_START_ROW - 1:]


def build_entries(rows):
    """Turn raw sheet rows into a list of dicts, one per color/material entry."""
    entries = []
    for i, row in enumerate(rows):
        if len(row) > 2 and row[2]:
            row_number = DATA_START_ROW + i
            material = row[0] if len(row) > 0 else ""
            brand = row[1] if len(row) > 1 else ""
            color = row[2]
            spools = row[3:7] if len(row) >= 7 else (row[3:] + [""] * (4 - len(row[3:])))
            link = row[7] if len(row) > 7 else ""
            entries.append({
                "row_number": row_number,
                "material": material,
                "brand": brand,
                "color": color,
                "spools": spools,
                "link": link,
            })
    return entries


st.set_page_config(page_title="Filament Inventory", page_icon="🧵")
st.title("🧵 Filament Inventory")

sheet = connect()
rows = get_rows(sheet)
entries = build_entries(rows)
materials_in_sheet = sorted({e["material"] for e in entries if e["material"]})

tab_update, tab_view, tab_alerts, tab_add = st.tabs(
    ["Update a spool", "View inventory", "⚠ Alerts", "➕ Add new"]
)

with tab_update:
    st.subheader("Update a spool")

    material_filter = st.selectbox(
        "Material", ["All"] + materials_in_sheet, key="update_material_filter"
    )
    filtered = [e for e in entries if material_filter == "All" or e["material"] == material_filter]

    if not filtered:
        st.info("No colors found for that material yet.")
    else:
        labels = [f"{e['color']} ({e['material']})" for e in filtered]
        choice_index = st.selectbox("Which color?", range(len(filtered)), format_func=lambda i: labels[i])
        info = filtered[choice_index]

        st.write("Current spools:")
        cols = st.columns(4)
        for i, (col, status) in enumerate(zip(cols, info["spools"])):
            with col:
                st.markdown(
                    f"<div style='background-color:{STATUS_COLORS.get(status, '#eee')};"
                    f"padding:8px;border-radius:6px;text-align:center'>"
                    f"Spool {i+1}<br><b>{status or 'empty'}</b></div>",
                    unsafe_allow_html=True,
                )

        spool_choice = st.selectbox("Which spool?", [1, 2, 3, 4])
        new_status = st.selectbox("New status", STATUSES)

        if st.button("Update", type="primary"):
            col_number = 4 + (spool_choice - 1)
            sheet.update_cell(info["row_number"], col_number, new_status)
            st.success(f"Updated {info['color']} - Spool {spool_choice} -> {new_status}")
            if new_status == "None" and info["link"]:
                st.warning(f"This spool is out. Reorder here: {info['link']}")
            st.cache_resource.clear()
            st.rerun()

with tab_view:
    st.subheader("Current inventory")

    material_filter_view = st.selectbox(
        "Material", ["All"] + materials_in_sheet, key="view_material_filter"
    )
    filtered_view = [e for e in entries if material_filter_view == "All" or e["material"] == material_filter_view]

    for e in filtered_view:
        spools_display = " / ".join(s for s in e["spools"] if s)
        st.write(f"**{e['color']}** ({e['material']}): {spools_display}")

with tab_alerts:
    st.subheader("Colors that need reordering")
    any_alert = False
    for e in entries:
        if "None" in e["spools"]:
            any_alert = True
            none_count = e["spools"].count("None")
            msg = f"**{e['color']}** ({e['material']}) — {none_count}/4 spools at None"
            if e["link"]:
                msg += f" — [Reorder here]({e['link']})"
            st.warning(msg)
    if not any_alert:
        st.success("All good, nothing needs reordering right now.")

with tab_add:
    st.subheader("Add a new color or material")
    st.caption("Use this when a color/material isn't in the list yet.")

    with st.form("add_new_form", clear_on_submit=True):
        material_choice = st.selectbox("Material", MATERIALS)
        brand_input = st.text_input("Brand (optional)")
        color_input = st.text_input("Color name")
        link_input = st.text_input("Reorder link (optional)")

        st.write("Initial spool statuses:")
        spool_cols = st.columns(4)
        initial_spools = []
        for i, col in enumerate(spool_cols, start=1):
            with col:
                initial_spools.append(st.selectbox(f"Spool {i}", ["(empty)"] + STATUSES, key=f"new_spool_{i}"))

        submitted = st.form_submit_button("Add to inventory", type="primary")

        if submitted:
            if not color_input.strip():
                st.error("Enter a color name first.")
            else:
                existing = [e for e in entries if e["color"].strip().lower() == color_input.strip().lower()
                            and e["material"] == material_choice]
                if existing:
                    st.error(f"{color_input} already exists for {material_choice}. Update it from the first tab instead.")
                else:
                    spools_to_save = [s if s != "(empty)" else "" for s in initial_spools]
                    new_row = [material_choice, brand_input, color_input.strip()] + spools_to_save + [link_input]
                    sheet.append_row(new_row)
                    st.success(f"Added {color_input} ({material_choice}) to the inventory.")
                    st.cache_resource.clear()
                    st.rerun()
