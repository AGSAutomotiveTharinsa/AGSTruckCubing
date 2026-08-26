import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from py3dbp import Bin, Item, Packer

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Truck Load & 3D Packing Calculator", layout="wide"
)
st.title("🚚 Manufacturing Truck Load & 3D Bin Packing Calculator")

# --- CONSTANTS (Trailer Specs) ---
TRAILER_LENGTH = 636.0  # inches
TRAILER_WIDTH = 102.0  # inches
TRAILER_HEIGHT = 110.0  # inches
MAX_WEIGHT_KG = 18824.083  # kg


# --- HELPER FUNCTIONS ---
def run_3d_packing(containers_list):
    """Runs 3D Bin Packing algorithm using py3dbp."""
    packer = Packer()
    # Define trailer as main bin
    packer.add_bin(
        Bin(
            "Trailer",
            TRAILER_LENGTH,
            TRAILER_WIDTH,
            TRAILER_HEIGHT,
            MAX_WEIGHT_KG,
        )
    )

    # Add items to packer
    for item in containers_list:
        packer.add_item(
            Item(
                name=item["name"],
                width=item["width"],
                height=item["height"],
                depth=item["length"],
                weight=item["weight"],
            )
        )

    packer.pack()
    return packer.bins[0]


def plot_3d_truck(packed_bin):
    """Generates an interactive 3D visual of packed containers in the truck trailer."""
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

    # Draw Packed Containers
    for item in packed_bin.items:
        # Item position coordinates
        x0, y0, z0 = [float(c) for c in item.position]
        w, h, d = (
            float(item.width),
            float(item.height),
            float(item.depth),
        )  # X, Z, Y dimensions

        # Define 8 vertices of the box
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
                opacity=0.7,
                name=item.name,
                hoverinfo="name",
            )
        )

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Length (in)", range=[0, TRAILER_LENGTH]),
            yaxis=dict(title="Width (in)", range=[0, TRAILER_WIDTH]),
            zaxis=dict(title="Height (in)", range=[0, TRAILER_HEIGHT]),
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

# Display data editor for user to enter quantities
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

# Merge quantity back into main dataframe
df["Quantity"] = edited_df["Quantity"]

if st.button("Calculate Truck Load & Spatial Fit", type="primary"):
    selected_parts = df[df["Quantity"] > 0].copy()

    if selected_parts.empty:
        st.warning("Please enter a quantity greater than 0 for at least one part.")
        st.stop()

    # Calculate containers needed and total weight
    containers_to_pack = []
    total_weight = 0.0

    for idx, row in selected_parts.iterrows():
        qty = row["Quantity"]
        max_per_container = row["MaxPartsPerContainer"]

        # Handle missing or invalid MaxPartsPerContainer safely
        if pd.isna(max_per_container) or max_per_container <= 0:
            num_containers = 1
        else:
            num_containers = math.ceil(qty / max_per_container)

        unit_weight = row["GrossWeight"] if not pd.isna(row["GrossWeight"]) else 0.0
        container_weight = unit_weight  # weight per container

        for i in range(num_containers):
            containers_to_pack.append(
                {
                    "name": f"{row['PartName']} (C{i+1})",
                    "length": float(row["ContainerLength"]),
                    "width": float(row["ContainerWidth"]),
                    "height": float(row["ContainerHeight"]),
                    "weight": float(container_weight),
                }
            )
            total_weight += container_weight

    # Run spatial 3D bin packing
    packed_truck = run_3d_packing(containers_to_pack)

    total_packed_items = len(packed_truck.items)
    total_requested_items = len(containers_to_pack)
    unpacked_items = total_requested_items - total_packed_items

    # Capacity evaluations
    is_weight_ok = total_weight <= MAX_WEIGHT_KG
    is_space_ok = unpacked_items == 0

    st.markdown("---")
    st.subheader("2. Load & Fit Diagnostics")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Containers", f"{total_requested_items} Units")
    col2.metric(
        "Gross Weight",
        f"{total_weight:,.2f} kg",
        delta=f"{MAX_WEIGHT_KG - total_weight:,.2f} kg margin",
    )
    col3.metric("Unpacked Containers", f"{unpacked_items} Units")

    # Status Banner
    if is_weight_ok and is_space_ok:
        st.success(
            "✅ **TRUCK STATUS: FIT** — All containers fit spatially inside trailer boundaries and load is within weight limits."
        )
    else:
        status_msg = "⚠️ **TRUCK STATUS: FULL / OVERLOADED**\n\n"
        if not is_weight_ok:
            status_msg += f"* **Weight Limit Exceeded:** Over capacity by {total_weight - MAX_WEIGHT_KG:,.2f} kg.\n"
        if not is_space_ok:
            status_msg += f"* **Spatial Limit Exceeded:** {unpacked_items} container(s) cannot physically fit into the 636\"x102\"x110\" trailer space.\n"
        st.error(status_msg)

    # Render 3D Truck Diagram
    st.subheader("3. Interactive 3D Spatial Layout")
    fig_3d = plot_3d_truck(packed_truck)
    st.plotly_chart(fig_3d, use_container_width=True)
