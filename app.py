import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Truck Load & 3D Packing Calculator", layout="wide"
)
st.title("🚚 Manufacturing Truck Load & 3D Bin Packing Calculator")

# --- CONSTANTS (Trailer Specs) ---
TRAILER_LENGTH = 636.0  # inches (X-axis)
TRAILER_WIDTH = 102.0  # inches (Y-axis)
TRAILER_HEIGHT = 110.0  # inches (Z-axis)
MAX_WEIGHT_KG = 18824.083  # kg


# --- REALISTIC PACKING ALGORITHM ---
def pack_truck_realistically(containers_list):
    """Packs containers realistically side-by-side across width (Y),

    stacked up to height (Z), and moving down length (X).
    """
    packed_items = []
    unpacked_items = []

    # Sort items by height (descending) and width to create stable tiers
    containers_sorted = sorted(
        containers_list,
        key=lambda c: (c["length"], c["width"], c["height"]),
        reverse=True,
    )

    current_x = 0.0
    current_y = 0.0
    current_z = 0.0

    row_length = 0.0  # Length consumed by current cross-section row
    layer_height = 0.0  # Height of current floor layer

    for item in containers_sorted:
        l, w, h = item["length"], item["width"], item["height"]

        # 1. Try placing next to current item across trailer width (Y-axis)
        if current_y + w <= TRAILER_WIDTH:
            # Check if height fits in current stack
            if current_z + h <= TRAILER_HEIGHT:
                pos = (current_x, current_y, current_z)
                packed_items.append({**item, "position": pos})
                row_length = max(row_length, l)
                layer_height = max(layer_height, h)
                current_y += w
                continue

        # 2. If width is full, try stacking on top (Z-axis) at start of width row
        if current_z + layer_height + h <= TRAILER_HEIGHT:
            current_z += layer_height
            current_y = 0.0
            layer_height = h
            if current_x + l <= TRAILER_LENGTH:
                pos = (current_x, current_y, current_z)
                packed_items.append({**item, "position": pos})
                row_length = max(row_length, l)
                current_y += w
                continue

        # 3. If full across width and height, move to next row along length (X-axis)
        current_x += row_length
        current_y = 0.0
        current_z = 0.0
        row_length = l
        layer_height = h

        if current_x + l <= TRAILER_LENGTH and h <= TRAILER_HEIGHT:
            pos = (current_x, current_y, current_z)
            packed_items.append({**item, "position": pos})
            current_y += w
        else:
            unpacked_items.append(item)

    return packed_items, unpacked_items


def plot_3d_truck(packed_items):
    """Generates an interactive 3D visual of realistically packed containers."""
    fig = go.Figure()

    # Draw Trailer Wireframe Boundary
    dx, dy, dz = TRAILER_LENGTH, TRAILER_WIDTH, TRAILER_HEIGHT
    fig.add_trace(
        go.Scatter3d(
            x=[0, dx, dx, 0, 0, 0, dx, dx, 0, 0, 0, 0, dx, dx, dx, dx],
            y=[0, 0, dy, dy, 0, 0, 0, dy, dy, 0, dy, dy, dy, dy, 0, 0],
            z=[0, 0, 0, 0, 0, dz, dz, dz, dz, dz, dz, 0, 0, dz, dz, 0],
            mode="lines",
            line=dict(color="black", width=4),
            name="Trailer Boundary",
        )
    )

    # Palette mapping per container type for clear visual grouping
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

        # 8 vertices of each rectangular container
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
                name=f"{item['name']} ({c_type})",
                hoverinfo="name",
            )
        )

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Length (X - 636\")", range=[0, TRAILER_LENGTH]),
            yaxis=dict(title="Width (Y - 102\")", range=[0, TRAILER_WIDTH]),
            zaxis=dict(title="Height (Z - 110\")", range=[0, TRAILER_HEIGHT]),
            aspectmode="data",
        ),
        margin=dict(r=0, l=0, b=0, t=30),
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

# Ensure required columns exist
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
        qty = row["Quantity"]
        max_per_container = row["MaxPartsPerContainer"]

        if pd.isna(max_per_container) or max_per_container <= 0:
            num_containers = 1
        else:
            num_containers = math.ceil(qty / max_per_container)

        unit_weight = (
            row["GrossWeight"] if not pd.isna(row["GrossWeight"]) else 0.0
        )

        for i in range(num_containers):
            containers_to_pack.append(
                {
                    "name": f"{row['PartName']} (C{i+1})",
                    "type": str(row["ContainerType"]),
                    "length": float(row["ContainerLength"]),
                    "width": float(row["ContainerWidth"]),
                    "height": float(row["ContainerHeight"]),
                    "weight": float(unit_weight),
                }
            )
            total_weight += unit_weight

    # Run realistic packing algorithm
    packed_items, unpacked_items = pack_truck_realistically(containers_to_pack)

    total_requested = len(containers_to_pack)
    total_packed = len(packed_items)
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
        st.success(
            "✅ **TRUCK STATUS: FIT** — All containers are realistically packed in floor-to-ceiling stacks across the width."
        )
    else:
        status_msg = "⚠️ **TRUCK STATUS: FULL / OVERLOADED**\n\n"
        if not is_weight_ok:
            status_msg += f"* **Weight Limit Exceeded:** Over capacity by {total_weight - MAX_WEIGHT_KG:,.2f} kg.\n"
        if not is_space_ok:
            status_msg += f"* **Spatial Limit Exceeded:** {unpacked_count} container(s) cannot physically fit.\n"
        st.error(status_msg)

    st.subheader("3. Realistic 3D Spatial Layout")
    fig_3d = plot_3d_truck(packed_items)
    st.plotly_chart(fig_3d, use_container_width=True)
