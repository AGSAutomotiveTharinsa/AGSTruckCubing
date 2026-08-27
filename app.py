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
    """Packs containers into the trailer.

    STRICT RULE: Boxes can ONLY stack on top of boxes that share the exact
    same dimensions (length, width, height).
    Unpacked items are positioned outside the trailer.
    """
    packed_items = []
    unpacked_items = []

    # Group containers by size/dimensions: (length, width, height)
    groups = {}
    for c in containers_list:
        key = (c["length"], c["width"], c["height"])
        if key not in groups:
            groups[key] = []
        groups[key].append(c)

    # Sort groups by length, width, height descending
    sorted_group_keys = sorted(
        groups.keys(), key=lambda k: (k[0], k[1], k[2]), reverse=True
    )

    current_x = 0.0
    current_y = 0.0
    row_length = 0.0

    for key in sorted_group_keys:
        items = groups[key]
        l, w, h = key

        # How many of this identical box can stack vertically in the trailer?
        max_stack_z = max(1, math.floor(TRAILER_HEIGHT / h))

        for item in items:
            placed = False

            # Try placing in current lane (X, Y) stacked up to max_stack_z
            # First, check if we need to advance Y (across width)
            if current_y + w > TRAILER_WIDTH:
                current_x += row_length
                current_y = 0.0
                row_length = 0.0

            # Check if current stack at (current_x, current_y) has room
            # Count existing boxes in this exact ground spot
            spot_stack = [
                p
                for p in packed_items
                if abs(p["position"][0] - current_x) < 0.1
                and abs(p["position"][1] - current_y) < 0.1
            ]

            if len(spot_stack) < max_stack_z:
                current_z = len(spot_stack) * h
                if (
                    current_x + l <= TRAILER_LENGTH
                    and current_z + h <= TRAILER_HEIGHT
                ):
                    pos = (current_x, current_y, current_z)
                    packed_items.append({**item, "position": pos})
                    row_length = max(row_length, l)
                    placed = True

            # If stack is full, move to next Y position in the current row
            if not placed:
                current_y += w
                if current_y + w <= TRAILER_WIDTH:
                    if current_x + l <= TRAILER_LENGTH and h <= TRAILER_HEIGHT:
                        pos = (current_x, current_y, 0.0)
                        packed_items.append({**item, "position": pos})
                        row_length = max(row_length, l)
                        placed = True

            # If width is full, move to next X position (row along length)
            if not placed:
                current_x += row_length
                current_y = 0.0
                row_length = l
                if current_x + l <= TRAILER_LENGTH and h <= TRAILER_HEIGHT:
                    pos = (current_x, current_y, 0.0)
                    packed_items.append({**item, "position": pos})
                    placed = True

            # If it still doesn't fit in trailer bounds, mark as unpacked
            if not placed:
                unpacked_items.append(item)

    # Position unpacked items OUTSIDE trailer bounds along Y-axis (Y > 110)
    out_x = 0.0
    out_y = TRAILER_WIDTH + 15.0  # Outside trailer wall
    out_z = 0.0
    out_row_l = 0.0

    positioned_unpacked = []
    for item in unpacked_items:
        l, w, h = item["length"], item["width"], item["height"]
        if out_z + h > TRAILER_HEIGHT:
            out_z = 0.0
            out_y += w + 5.0

        pos = (out_x, out_y, out_z)
        positioned_unpacked.append({**item, "position": pos})
        out_z += h
        out_row_l = max(out_row_l, l)

        if out_z >= TRAILER_HEIGHT:
            out_z = 0.0
            out_x += out_row_l
            out_row_l = 0.0

    return packed_items, positioned_unpacked


def plot_3d_truck(packed_items, unpacked_items):
    """Generates 3D visualization.

    Trailer frame size remains fixed at all times. Unpacked items are rendered
    outside the trailer boundary.
    """
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
            name="Trailer Boundary (Fixed)",
        )
    )

    # Palette mapping per container type
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

    all_items = packed_items + unpacked_items
    for item in all_items:
        c_type = item["type"]
        if c_type not in color_map:
            color_map[c_type] = colors[len(color_map) % len(colors)]

    # Draw Packed Items Inside Trailer
    for item in packed_items:
        c_type = item["type"]
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
                name=f"{item['name']} (Packed)",
                hoverinfo="name",
            )
        )

    # Draw Unpacked Items Outside Trailer (Red outline / shaded)
    for item in unpacked_items:
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
                color="darkred",
                opacity=0.5,
                name=f"{item['name']} (OVERFLOW - Outside)",
                hoverinfo="name",
            )
        )

    # Enforce Fixed Axes Ranges so Trailer Never Shrinks or Changes Size
    max_y_range = max(TRAILER_WIDTH + 60.0, 180.0) if unpacked_items else TRAILER_WIDTH + 20.0

    fig.update_layout(
        scene=dict(
            xaxis=dict(
                title="Length (X - 636\")",
                range=[0, TRAILER_LENGTH + 20],
                autorange=False,
            ),
            yaxis=dict(
                title="Width (Y - 102\") [Overflow Outside > 102\"]",
                range=[0, max_y_range],
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
                y=max_y_range / TRAILER_LENGTH,
                z=TRAILER_HEIGHT / TRAILER_LENGTH,
            ),
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

    # Run packing algorithm with same-size stacking constraint
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
        st.success(
            "✅ **TRUCK STATUS: FIT** — All containers packed with same-size vertical stacking inside trailer."
        )
    else:
        status_msg = "⚠️ **TRUCK STATUS: FULL / OVERLOADED**\n\n"
        if not is_weight_ok:
            status_msg += f"* **Weight Limit Exceeded:** Over capacity by {total_weight - MAX_WEIGHT_KG:,.2f} kg.\n"
        if not is_space_ok:
            status_msg += f"* **Spatial Limit Exceeded:** {unpacked_count} container(s) cannot fit and are stacked outside the trailer in dark red.\n"
        st.error(status_msg)

    st.subheader("3. 3D Spatial Layout")
    fig_3d = plot_3d_truck(packed_items, unpacked_items)
    st.plotly_chart(fig_3d, use_container_width=True)
