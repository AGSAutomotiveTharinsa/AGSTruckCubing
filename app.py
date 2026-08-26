import math
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Truck Capacity Calculator", layout="wide")

st.title("🚛 Truck Capacity & Load Calculator")
st.markdown(
    "Enter quantities directly in the catalog table below to calculate truck utilization."
)

CATALOG_FILE = "PartsCatalog.xlsx"

# Constants for Truck Specs
TRUCK_MAX_WEIGHT_KG = 18824.083
TRUCK_LENGTH, TRUCK_WIDTH, TRUCK_HEIGHT = 636.0, 102.0, 110.0
USABLE_VOL_LIMIT = (TRUCK_LENGTH * TRUCK_WIDTH * TRUCK_HEIGHT) * 0.85


# Load catalog automatically from GitHub repo
@st.cache_data
def load_catalog():
    if os.path.exists(CATALOG_FILE):
        return pd.read_excel(CATALOG_FILE)
    else:
        # Fallback to CSV if xlsx isn't present
        csv_file = CATALOG_FILE.replace(".xlsx", ".csv")
        if os.path.exists(csv_file):
            return pd.read_csv(csv_file)
        st.error(f"Catalog file '{CATALOG_FILE}' not found in repository!")
        st.stop()


df_catalog = load_catalog()

# Prepare table for user quantity input
if "Quantity" not in df_catalog.columns:
    df_catalog.insert(1, "Quantity", 0)

st.subheader("📋 Parts Catalog (Enter Quantities)")

# Data Editor allows editing quantities directly in the grid
edited_df = st.data_editor(
    df_catalog,
    column_config={
        "Quantity": st.column_config.NumberColumn(
            "Shipment Qty",
            help="Type the number of parts to ship",
            min_value=0,
            step=1,
            default=0,
        ),
        "PartName": st.column_config.TextColumn("Part Name", disabled=True),
        "MaxPartsPerContainer": st.column_config.NumberColumn(
            "Max Parts/Box", disabled=True
        ),
        "ContainerWeight": st.column_config.NumberColumn(
            "Box Weight (kg)", disabled=True
        ),
    },
    disabled=[
        "PartName",
        "MaxPartsPerContainer",
        "ContainerLength",
        "ContainerWidth",
        "ContainerHeight",
        "ContainerWeight",
    ],
    hide_index=True,
    use_container_width=True,
)

# Calculate Button
if st.button("Check Truck Capacity", type="primary"):
    # Filter only parts where quantity > 0
    selected_items = edited_df[edited_df["Quantity"] > 0]

    if selected_items.empty:
        st.warning("Please enter a quantity greater than 0 for at least one part.")
    else:
        total_weight_kg = 0.0
        total_volume_cu_in = 0.0
        manifest_summary = []

        for _, row in selected_items.iterrows():
            qty = row["Quantity"]
            max_per_box = row["MaxPartsPerContainer"]
            containers_needed = math.ceil(qty / max_per_box)

            box_vol = (
                row["ContainerLength"]
                * row["ContainerWidth"]
                * row["ContainerHeight"]
            )
            line_weight = containers_needed * row["ContainerWeight"]
            line_vol = containers_needed * box_vol

            total_weight_kg += line_weight
            total_volume_cu_in += line_vol

            manifest_summary.append(
                {
                    "Part Name": row["PartName"],
                    "Quantity": qty,
                    "Containers": containers_needed,
                    "Total Weight (kg)": line_weight,
                    "Total Vol (cu in)": line_vol,
                }
            )

        # 1. Summary Table of Active Items
        st.subheader("📦 Manifest Load Breakdown")
        st.dataframe(pd.DataFrame(manifest_summary), use_container_width=True)

        # 2. Capacity Gauges
        weight_pct = (total_weight_kg / TRUCK_MAX_WEIGHT_KG) * 100
        volume_pct = (total_volume_cu_in / USABLE_VOL_LIMIT) * 100

        st.divider()
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

        # 3. Status Verdict
        if (
            total_weight_kg > TRUCK_MAX_WEIGHT_KG
            or total_volume_cu_in > USABLE_VOL_LIMIT
        ):
            st.error("🚨 TRUCK OVERLOADED / FULL!")
            if total_weight_kg > TRUCK_MAX_WEIGHT_KG:
                st.write(
                    f"- **Weight Exceeded by:** {total_weight_kg - TRUCK_MAX_WEIGHT_KG:,.2f} kg"
                )
            if total_volume_cu_in > USABLE_VOL_LIMIT:
                st.write(
                    f"- **Volume Exceeded by:** {total_volume_cu_in - USABLE_VOL_LIMIT:,.0f} cu in"
                )
        else:
            st.success("✅ TRUCK OK - Load fits safely within limits.")
