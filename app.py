import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE SETUP ---
st.set_page_config(page_title="Trailer Optimization", layout="wide")
st.title("Trailer Optimization")

# --- CONSTANTS (Trailer Specs) ---
TRAILER_LENGTH = 636.0  # inches (X-axis)
TRAILER_WIDTH = 102.0  # inches (Y-axis)
TRAILER_HEIGHT = 110.0  # inches (Z-axis)
MAX_WEIGHT_KG = 18824.083  # kg


# --- PACKING ALGORITHM ---
def pack_truck_realistically(containers_list):
    """Packs containers into the trailer, grouping by container dimensions so identical box types can stack together."""
    packed_items = []
    unpacked_items = []

    # Group containers strictly by Container Type & Dimensions (ignoring PartName)
    groups = {}
    for c in containers_list:
        key = (
            c["type"],
            c["length"],
            c["width"],
            c["height"],
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(c)

    # Sort groups by footprint volume (largest base first)
    sorted_group_keys = sorted(
        groups.keys(), key=lambda k: (k[1], k[2], k[3]), reverse=True
    )

    current_x = 0.0
    current_y = 0.0
    current_row_length = 0.0

    for key in sorted_group_keys:
        items = groups[key]
        c_type, l, w, h = key

        max_stack_z = max(1, math.floor(TRAILER_HEIGHT / h))
        item_index = 0
        total_group_items = len(items)

        while item_index < total_group_items:
            # Advance to next X-row when Y reaches trailer width
            if current_y + w > TRAILER_WIDTH:
                current_x += current_row_length
                current_y = 0.0
                current_row_length = 0.0

            # Stop if X exceeds trailer length
            if current_x + l > TRAILER_LENGTH:
                unpacked_items.extend(items[item_index:])
                break

            # Stack items vertically up to max allowed height
            stack_count = min(total_group_items - item_index, max_stack_z)

            for z_idx in range(stack_count):
                curr_item = items[item_index]
                pos = (current_x, current_y, z_idx * h)
                packed_items.append({**curr_item, "position": pos})
                item_index += 1

            current_row_length = max(current_row_length, l)
            current_y += w

    return packed_items, unpacked_items

def calculate_fill_percentage(containers_to_pack):
    """Calculates usable space utilization percentage."""
    if not containers_to_pack:
        return 0.0

    total_requested_vol = sum(
        c["length"] * c["width"] * c["height"] for c in containers_to_pack
    )

    avg_top_gap = sum(
        (TRAILER_HEIGHT % c["height"]) for c in containers_to_pack
    ) / len(containers_to_pack)
    usable_height_capacity = TRAILER_HEIGHT - avg_top_gap
    effective_usable_capacity = (
        TRAILER_LENGTH * TRAILER_WIDTH * usable_height_capacity
    )

    return (total_requested_vol / effective_usable_capacity) * 100


def plot_3d_truck(packed_items, fill_percentage):
    """Renders 3D Plot of the trailer layout."""
    fig = go.Figure()

    dx, dy, dz = TRAILER_LENGTH, TRAILER_WIDTH, TRAILER_HEIGHT
    fig.add_trace(
        go.Scatter3d(
            x=[0, dx, dx, 0, 0, 0, dx, dx, 0, 0, 0, 0, dx, dx, dx, dx],
            y=[0, 0, dy, dy, 0, 0, 0, dy, dy, 0, dy, dy, dy, dy, 0, 0],
            z=[0, 0, 0, 0, 0, dz, dz, dz, dz, dz, dz, 0, 0, dz, dz, 0],
            mode="lines",
            line=dict(color="black", width=5),
            name="Trailer Boundary",
        )
    )

    color_map = {}
    colors = [
        "royalblue",
        "crimson",
        "forestgreen",
        "darkorange",
        "purple",
        "teal",
        "gold",
    ]

    for item in packed_items:
        c_type = item["type"]
        if c_type not in color_map:
            color_map[c_type] = colors[len(color_map) % len(colors)]

        x0, y0, z0 = item["position"]
        d, w, h = item["length"], item["width"], item["height"]

        x = [x0, x0 + d, x0 + d, x0, x0, x0 + d, x0 + d, x0]
        y = [y0, y0, y0 + w, y0 + w, y0, y0, y0 + w, y0 + w]
        z = [z0, z0, z0, z0, z0 + h, z0 + h, z0 + h, z0 + h]

        i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
        j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
        k = [0, 7, 5, 3, 6, 7, 1, 1, 5, 5, 7, 6]

        fig.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=z,
                i=i,
                j=j,
                k=k,
                color=color_map[c_type],
                opacity=0.85,
                name=f"{item['part_name']} ({c_type})",
                hoverinfo="name",
            )
        )

    status_color = "red" if fill_percentage > 100 else "green"
    status_label = "OVERLOADED" if fill_percentage > 100 else "CAPACITY OK"

    fig.update_layout(
        title=dict(
            text=f"<b>Trailer Usable Fill: <span style='color:{status_color};'>{fill_percentage:.1f}%</span> ({status_label})</b>",
            x=0.01,
            y=0.95,
            font=dict(size=18),
        ),
        scene=dict(
            xaxis=dict(
                title="Length (X - 636\")",
                range=[0, TRAILER_LENGTH + 10],
                autorange=False,
            ),
            yaxis=dict(
                title="Width (Y - 102\")",
                range=[0, TRAILER_WIDTH + 10],
                autorange=False,
            ),
            zaxis=dict(
                title="Height (Z - 110\")",
                range=[0, TRAILER_HEIGHT + 10],
                autorange=False,
            ),
            aspectmode="manual",
            aspectratio=dict(
                x=TRAILER_LENGTH / TRAILER_LENGTH,
                y=TRAILER_WIDTH / TRAILER_LENGTH,
                z=TRAILER_HEIGHT / TRAILER_LENGTH,
            ),
        ),
        margin=dict(r=0, l=0, b=0, t=40),
    )
    return fig


# --- MAIN APP INTERFACE ---
uploaded_file = st.sidebar.file_uploader(
    "Upload Excel Data (Parts Manifest)", type=["xlsx"]
)

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.sidebar.success("Excel File Loaded Successfully!")
else:
    st.info("👈 Please upload your `PartsData.xlsx` file to begin.")
    st.stop()

# Flexibly check and strip bracket spaces if needed
df.columns = df.columns.str.strip()

required_cols = [
    "PartName",
    "ContainerType",
    "ContainerLength [in]",
    "ContainerWidth",
    "ContainerHeight",
    "ContainerWeight [kg]",
    "MaxPartsPerContainer",
    "Weight of 1 Part [kg]",
]

missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    st.error(f"Excel file missing required columns: {missing_cols}")
    st.stop()

st.subheader("1. Enter Order Quantities")
df["Quantity"] = 0

edited_df = st.data_editor(
    df[
        [
            "PartName",
            "ContainerType",
            "MaxPartsPerContainer",
            "ContainerWeight [kg]",
            "Weight of 1 Part [kg]",
            "Quantity",
        ]
    ],
    num_rows="fixed",
    disabled=[
        "PartName",
        "ContainerType",
        "MaxPartsPerContainer",
        "ContainerWeight [kg]",
        "Weight of 1 Part [kg]",
    ],
    use_container_width=True,
)

df["Quantity"] = edited_df["Quantity"]

if st.button("Calculate Truck Load & Spatial Fit", type="primary"):
    selected_parts = df[df["Quantity"] > 0].copy()

    if selected_parts.empty:
        st.warning("Please enter a quantity greater than 0 for at least one part.")
        st.stop()

    containers_to_pack = []
    total_weight = 0.0

    for idx, row in selected_parts.iterrows():
        qty = int(row["Quantity"])
        max_per_container = (
            int(row["MaxPartsPerContainer"])
            if not pd.isna(row["MaxPartsPerContainer"])
            else 1
        )
        num_containers = math.ceil(qty / max_per_container)

        container_empty_weight = (
            float(row["ContainerWeight [kg]"])
            if not pd.isna(row["ContainerWeight [kg]"])
            else 0.0
        )
        part_unit_weight = (
            float(row["Weight of 1 Part [kg]"])
            if not pd.isna(row["Weight of 1 Part [kg]"])
            else 0.0
        )

        remaining_parts = qty
        for i in range(num_containers):
            parts_in_this_box = min(remaining_parts, max_per_container)

            # Weight = (Parts Qty * Single Part Weight) + Empty Container Weight
            box_gross_weight = container_empty_weight + (
                parts_in_this_box * part_unit_weight
            )

            containers_to_pack.append(
                {
                    "part_name": str(row["PartName"]),
                    "name": f"{row['PartName']} (C{i+1})",
                    "type": str(row["ContainerType"]),
                    "length": float(row["ContainerLength [in]"]),
                    "width": float(row["ContainerWidth"]),
                    "height": float(row["ContainerHeight"]),
                    "weight": box_gross_weight,
                    "max_parts": max_per_container,
                    "parts_count": parts_in_this_box,
                }
            )
            total_weight += box_gross_weight
            remaining_parts -= parts_in_this_box

    # Run packing logic
    packed_items, unpacked_items = pack_truck_realistically(containers_to_pack)
    fill_percentage = calculate_fill_percentage(containers_to_pack)

    total_requested = len(containers_to_pack)
    unpacked_count = len(unpacked_items)

    is_weight_ok = total_weight <= MAX_WEIGHT_KG
    is_space_ok = unpacked_count == 0

    st.markdown("---")
    st.subheader("2. Load & Fit Diagnostics")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Containers", f"{total_requested} Units")
    col2.metric(
        "Gross Weight",
        f"{total_weight:,.2f} kg",
        delta=f"{MAX_WEIGHT_KG - total_weight:,.2f} kg margin",
    )
    col3.metric("Usable Spatial Fill", f"{fill_percentage:.1f}%")
    col4.metric("Unpacked Containers", f"{unpacked_count} Units")

    if is_weight_ok and is_space_ok:
        st.success("✅ **TRUCK STATUS: FIT** — All items fit within capacity.")
    else:
        st.error(
            "⚠️ **TRUCK STATUS: OVERLOADED** — Exceeds weight or space limit."
        )

    st.subheader("3. 3D Spatial Layout & Unpacked Summary")

    col_plot, col_unpacked = st.columns([6, 4])

    with col_plot:
        fig_3d = plot_3d_truck(packed_items, fill_percentage)
        st.plotly_chart(fig_3d, use_container_width=True)

    with col_unpacked:
        st.markdown("### ⚠️ Unpacked Items")
        if unpacked_items:
            unpacked_df = pd.DataFrame(unpacked_items)
            summary = (
                unpacked_df.groupby(["part_name", "type"])
                .agg(
                    Unpacked_Containers=("name", "count"),
                    Unpacked_Parts_QTY=("parts_count", "sum"),
                )
                .reset_index()
                .rename(
                    columns={
                        "part_name": "Part Name",
                        "type": "Container Type",
                        "Unpacked_Containers": "Unpacked Containers",
                        "Unpacked_Parts_QTY": "Unpacked QTY",
                    }
                )
            )

            st.dataframe(
                summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Part Name": st.column_config.TextColumn(
                        "Part Name", width="medium"
                    ),
                    "Container Type": st.column_config.TextColumn(
                        "Type", width="small"
                    ),
                    "Unpacked Containers": st.column_config.NumberColumn(
                        "Containers", width="small"
                    ),
                    "Unpacked QTY": st.column_config.NumberColumn(
                        "Qty", width="small"
                    ),
                },
            )
        else:
            st.success("All boxes packed successfully!")
