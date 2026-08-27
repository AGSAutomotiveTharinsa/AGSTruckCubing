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


# --- STRICT SAME-SIZE STACKING PACKING ALGORITHM ---
def pack_truck_realistically(containers_list):
    """Packs containers into the trailer with strict same-size vertical stacking.

    Returns packed items and unplaced items.
    """
    packed_items = []
    unpacked_items = []

    # Group containers by type and dimensions
    groups = {}
    for c in containers_list:
        key = (
            c["part_name"],
            c["type"],
            c["length"],
            c["width"],
            c["height"],
            c["max_parts"],
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(c)

    # Sort groups by size descending
    sorted_group_keys = sorted(
        groups.keys(), key=lambda k: (k[2], k[3], k[4]), reverse=True
    )

    current_x = 0.0
    current_y = 0.0
    current_row_length = 0.0

    for key in sorted_group_keys:
        items = groups[key]
        part_name, c_type, l, w, h, max_parts = key

        max_stack_z = max(1, math.floor(TRAILER_HEIGHT / h))
        item_index = 0
        total_group_items = len(items)

        while item_index < total_group_items:
            # Check width boundary
            if current_y + w > TRAILER_WIDTH:
                current_x += current_row_length
                current_y = 0.0
                current_row_length = 0.0

            # Check length boundary
            if current_x + l > TRAILER_LENGTH:
                unpacked_items.extend(items[item_index:])
                break

            stack_count = min(total_group_items - item_index, max_stack_z)

            for z_idx in range(stack_count):
                curr_item = items[item_index]
                pos = (current_x, current_y, z_idx * h)
                packed_items.append({**curr_item, "position": pos})
                item_index += 1

            current_row_length = max(current_row_length, l)
            current_y += w

    return packed_items, unpacked_items


def plot_3d_truck(packed_items):
    """Renders ONLY items packed safely inside the fixed trailer dimensions."""
    fig = go.Figure()

    # Fixed Trailer Wireframe Boundary (Black Box)
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

    # Color mapping
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

    fig.update_layout(
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
        margin=dict(r=0, l=0, b=0, t=10),
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

required_cols = [
    "PartName",
    "MaxPartsPerContainer",
    "ContainerType",
    "ContainerLength",
    "ContainerWidth",
    "ContainerHeight",
    "GrossWeight",
]
if not all(col in df.columns for col in required_cols):
    st.error(f"Excel file must contain columns: {required_cols}")
    st.stop()

st.subheader("1. Enter Order Quantities")
df["Quantity"] = 0

edited_df = st.data_editor(
    df[
        [
            "PartName",
            "ContainerType",
            "MaxPartsPerContainer",
            "GrossWeight",
            "Quantity",
        ]
    ],
    num_rows="fixed",
    disabled=[
        "PartName",
        "ContainerType",
        "MaxPartsPerContainer",
        "GrossWeight",
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

        unit_weight = (
            row["GrossWeight"] if not pd.isna(row["GrossWeight"]) else 0.0
        )

        remaining_parts = qty
        for i in range(num_containers):
            parts_in_this_box = min(remaining_parts, max_per_container)
            containers_to_pack.append(
                {
                    "part_name": str(row["PartName"]),
                    "name": f"{row['PartName']} (C{i+1})",
                    "type": str(row["ContainerType"]),
                    "length": float(row["ContainerLength"]),
                    "width": float(row["ContainerWidth"]),
                    "height": float(row["ContainerHeight"]),
                    "weight": float(unit_weight),
                    "max_parts": max_per_container,
                    "parts_count": parts_in_this_box,
                }
            )
            total_weight += unit_weight
            remaining_parts -= parts_in_this_box

    # Run packing algorithm
    packed_items, unpacked_items = pack_truck_realistically(containers_to_pack)

    total_requested = len(containers_to_pack)
    unpacked_count = len(unpacked_items)

    is_weight_ok = total_weight <= MAX_WEIGHT_KG
    is_space_ok = unpacked_count == 0

    st.markdown("---")
    st.subheader("2. Load & Fit Diagnostics")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Containers", f"{total_requested} Units")
    col2.metric(
        "Gross Weight",
        f"{total_weight:,.2f} kg",
        delta=f"{MAX_WEIGHT_KG - total_weight:,.2f} kg margin",
    )
    col3.metric("Unpacked Containers", f"{unpacked_count} Units")

    if is_weight_ok and is_space_ok:
        st.success("✅ **TRUCK STATUS: FIT** — All items fit within capacity.")
    else:
        st.error(
            "⚠️ **TRUCK STATUS: OVERLOADED** — Some items cannot fit inside the trailer."
        )

    st.subheader("3. 3D Spatial Layout & Unpacked Summary")

    # Split screen into Plot (left) and Unpacked List (right)
    col_plot, col_unpacked = st.columns([7, 3])

    with col_plot:
        fig_3d = plot_3d_truck(packed_items)
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

            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.success("All boxes packed successfully!")
