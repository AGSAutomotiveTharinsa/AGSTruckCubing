import math
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Truck Capacity Calculator", layout="wide")
st.title("🚛 Truck Capacity & Load Calculator")

CATALOG_FILE = "PartsCatalog.xlsx"  # Path inside your GitHub repo

# Load catalog automatically from the repo
@st.cache_data
def load_catalog():
    if os.path.exists(CATALOG_FILE):
        return pd.read_excel(CATALOG_FILE)
    else:
        st.error(f"Catalog file '{CATALOG_FILE}' not found in repository!")
        st.stop()


df_catalog = load_catalog()

# 1. Multi-Select Part Selector
selected_parts = st.multiselect(
    "Select Parts for this Shipment:", options=df_catalog["PartName"].unique()
)

if selected_parts:
    st.subheader("📋 Enter Quantities")

    shipment_data = []
    with st.form("quantities_form"):
        for part in selected_parts:
            part_row = df_catalog[df_catalog["PartName"] == part].iloc[0]
            qty = st.number_input(
                label=f"Quantity for {part} (Max {part_row['MaxPartsPerContainer']} per container):",
                min_value=1,
                value=10,
                step=1,
            )
            shipment_data.append({"PartName": part, "Quantity": qty})

        calculate_btn = st.form_submit_button("Calculate Truck Load")

    # 2. Perform Calculations
    if calculate_btn:
        TRUCK_MAX_WEIGHT_KG = 18824.083
        USABLE_VOL_LIMIT = (636.0 * 102.0 * 110.0) * 0.85

        total_weight_kg = 0.0
        total_volume_cu_in = 0.0
        manifest_summary = []

        for item in shipment_data:
            part_name = item["PartName"]
            qty = item["Quantity"]
            part_info = df_catalog[df_catalog["PartName"] == part_name].iloc[0]

            containers_needed = math.ceil(
                qty / part_info["MaxPartsPerContainer"]
            )
            box_vol = (
                part_info["ContainerLength"]
                * part_info["ContainerWidth"]
                * part_info["ContainerHeight"]
            )
            line_weight = containers_needed * part_info["ContainerWeight"]
            line_vol = containers_needed * box_vol

            total_weight_kg += line_weight
            total_volume_cu_in += line_vol

            manifest_summary.append(
                {
                    "Part Name": part_name,
                    "Part Qty": qty,
                    "Containers": containers_needed,
                    "Total Weight (kg)": line_weight,
                    "Total Vol (cu in)": line_vol,
                }
            )

        # Display Results
        st.subheader("📦 Load Summary")
        st.dataframe(pd.DataFrame(manifest_summary), use_container_width=True)

        weight_pct = (total_weight_kg / TRUCK_MAX_WEIGHT_KG) * 100
        volume_pct = (total_volume_cu_in / USABLE_VOL_LIMIT) * 100

        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Total Weight",
                f"{total_weight_kg:,.2f} kg",
                f"{weight_pct:.1f}% limit",
            )
            st.progress(min(weight_pct / 100, 1.0))
        with col2:
            st.metric(
                "Usable Volume Used",
                f"{total_volume_cu_in:,.0f} cu in",
                f"{volume_pct:.1f}% limit",
            )
            st.progress(min(volume_pct / 100, 1.0))

        if (
            total_weight_kg > TRUCK_MAX_WEIGHT_KG
            or total_volume_cu_in > USABLE_VOL_LIMIT
        ):
            st.error("🚨 TRUCK OVERLOADED / FULL!")
        else:
            st.success("✅ TRUCK OK - Load fits safely within limits.")
