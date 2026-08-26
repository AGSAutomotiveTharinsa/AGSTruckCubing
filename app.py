import math
import pandas as pd
import streamlit as st

# Configure page layout
st.set_page_config(page_title="Truck Capacity Calculator", layout="wide")

st.title("🚛 Truck Capacity & Load Calculator")
st.markdown(
    "Upload your parts catalog Excel file, select items, and calculate truck space/weight utilization."
)

# Constants for Truck Specs
TRUCK_LENGTH = 636.0  # inches
TRUCK_WIDTH = 102.0  # inches
TRUCK_HEIGHT = 110.0  # inches
TRUCK_MAX_WEIGHT_KG = 18824.083
TRUCK_TOTAL_VOL_CU_IN = TRUCK_LENGTH * TRUCK_WIDTH * TRUCK_HEIGHT
USABLE_VOL_LIMIT = TRUCK_TOTAL_VOL_CU_IN * 0.85  # 85% volumetric fill efficiency

# 1. File Uploader for Excel Catalog
uploaded_file = st.sidebar.file_uploader(
    "Upload Parts Catalog (.xlsx)", type=["xlsx", "xls"]
)

if uploaded_file:
    df_catalog = pd.read_excel(uploaded_file)

    st.sidebar.success("Catalog Loaded Successfully!")

    # Validate required columns
    required_cols = [
        "PartName",
        "MaxPartsPerContainer",
        "ContainerLength",
        "ContainerWidth",
        "ContainerHeight",
        "GrossWeight",
    ]
    if not all(col in df_catalog.columns for col in required_cols):
        st.error(f"Excel file must contain columns: {', '.join(required_cols)}")
        st.stop()

    # 2. Multi-Select Part Selector
    selected_parts = st.multiselect(
        "Select Parts for this Shipment:", options=df_catalog["PartName"].unique()
    )

    if selected_parts:
        st.subheader("📋 Enter Quantities")

        # Create a form to input quantities per part
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

        # 3. Perform Calculations
        if calculate_btn:
            total_weight_kg = 0.0
            total_volume_cu_in = 0.0

            manifest_summary = []

            for item in shipment_data:
                part_name = item["PartName"]
                qty = item["Quantity"]
                part_info = df_catalog[
                    df_catalog["PartName"] == part_name
                ].iloc[0]

                # Calculations
                max_per_box = part_info["MaxPartsPerContainer"]
                containers_needed = math.ceil(qty / max_per_box)

                box_vol = (
                    part_info["ContainerLength"]
                    * part_info["ContainerWidth"]
                    * part_info["ContainerHeight"]
                )
                line_weight = containers_needed * part_info["GrossWeight"]
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

            # Display Manifest Table
            st.subheader("📦 Load Summary")
            st.dataframe(pd.DataFrame(manifest_summary), use_container_width=True)

            # Capacity Evaluation
            weight_pct = (total_weight_kg / TRUCK_MAX_WEIGHT_KG) * 100
            volume_pct = (total_volume_cu_in / USABLE_VOL_LIMIT) * 100

            st.divider()
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Total Weight", f"{total_weight_kg:,.2f} kg", f"{weight_pct:.1f}% limit")
                st.progress(min(weight_pct / 100, 1.0))

            with col2:
                st.metric("Usable Volume Used", f"{total_volume_cu_in:,.0f} cu in", f"{volume_pct:.1f}% limit")
                st.progress(min(volume_pct / 100, 1.0))

            # Verdict Status
            if total_weight_kg > TRUCK_MAX_WEIGHT_KG or total_volume_cu_in > USABLE_VOL_LIMIT:
                st.error("🚨 TRUCK OVERLOADED / FULL!")
                if total_weight_kg > TRUCK_MAX_WEIGHT_KG:
                    st.write(f"- **Weight Exceeded by:** {total_weight_kg - TRUCK_MAX_WEIGHT_KG:,.2f} kg")
                if total_volume_cu_in > USABLE_VOL_LIMIT:
                    st.write(f"- **Volume Exceeded by:** {total_volume_cu_in - USABLE_VOL_LIMIT:,.0f} cu in")
            else:
                st.success("✅ TRUCK OK - Load fits safely within limits.")

else:
    st.info("Please upload your `PartsCatalog.xlsx` file in the sidebar to begin.")
