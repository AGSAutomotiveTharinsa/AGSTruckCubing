import math
import re
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import base64

# --- POWER AUTOMATE FLOW ENDPOINT ---
POWER_AUTOMATE_URL = "https://default9b2f9cbe865b4df8a5848494d8c1ef.f6.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/16/workflows/46a10b2e46d44a40a3a7163624ce59a5/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=GiJ6B2AxQl-aCWfJi8Fc66lC-zJyxtqyzM3GMCS0z3Y"

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
            if current_y + w > TRAILER_WIDTH:
                current_x += current_row_length
                current_y = 0.0
                current_row_length = 0.0

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
                opacity=0.75,
                lighting=dict(ambient=0.8, diffuse=0.8),
                flatshading=True,
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


# --- HARDCODED MANIFEST DATA ---
data = {
    "PartName": [
        "GM1121ACA", "GM1122ACA", "GM286YBA", "GM286EBA", "GM286FBA",
        "GM1100CBA", "GM1100DBA", "GM1110CCA", "GM1110DCA", "FC1100JAA-STMP",
        "FC1226CBA-WELD", "FC1226DBA-WELD", "FC1227ECA-WELD", "FC1227FCA-WELD",
        "GM1123ABB", "GM1124ABB", "GM1130ECA", "GM1130FCA", "CV2440FAA",
        "CV2440GAA", "GM2430UAA", "GM2430IAA", "GM2200EAA", "GM2200FAA"
    ],
    "ContainerType": [
        "*PLA405", "*PLA405", "*GM5131", "*CC3A", "*CC3A",
        "*AGS1091", "*AGS1091", "*AGS1091", "*AGS1091", "*AGS1010",
        "*AGS1010", "*AGS1010", "*AGS1010", "*AGS1010", "*PLA405",
        "*PLA405", "AGS1015", "AGS1015", "AGS1015", "AGS1015",
        "AGS1015", "AGS1015", "AGS1015", "AGS1015"
    ],
    "ContainerLength [in]": [
        48, 48, 54, 53, 53,
        62, 62, 62, 62, 48,
        48, 48, 48, 48, 48,
        48, 48, 48, 48, 48,
        48, 48, 48, 48
    ],
    "ContainerWidth": [
        45, 45, 44, 42, 42,
        48, 48, 48, 48, 45,
        45, 45, 45, 45, 45,
        45, 45, 45, 45, 45,
        45, 45, 45, 45
    ],
    "ContainerHeight": [
        53, 53, 40, 38, 38,
        50, 50, 50, 50, 34,
        34, 34, 34, 34, 53,
        53, 25, 25, 25, 25,
        25, 25, 25, 25
    ],
    "ContainerWeight [kg]": [
        79.1, 79.1, 170.0, 173.0, 173.0,
        256.8, 256.8, 256.8, 256.8, 181.8,
        181.8, 181.8, 181.8, 181.8, 79.1,
        79.1, 170.5, 170.5, 170.5, 170.5,
        170.5, 170.5, 170.5, 170.5
    ],
    "MaxPartsPerContainer": [
        192, 192, 350, 300, 300,
        112, 112, 112, 112, 798,
        48, 48, 450, 450, 144,
        144, 800, 1000, 2000, 2000,
        200, 200, 1008, 1008
    ],
    "Weight of 1 Part [kg]": [
        0.68, 0.68, 0.92, 0.82, 0.82,
        2.05, 2.05, 2.05, 2.05, 1.34,
        3.98, 3.96, 1.96, 1.96, 0.68,
        0.68, 0.27, 0.25, 0.23, 0.23,
        0.23, 0.23, 0.40, 0.40
    ]
}

df = pd.DataFrame(data)

# --- SIDEBAR PDF UPLOADER ---
st.sidebar.header("Invoice Auto-Fill")
pdf_file = st.sidebar.file_uploader("Upload AGS Invoice (PDF)", type=["pdf"])

pdf_triggered_calc = False

# Session state initializations
if "quantities_df" not in st.session_state:
    st.session_state.quantities_df = pd.DataFrame(
        {
            "PartName": df["PartName"],
            "ContainerType": df["ContainerType"],
            "MaxPartsPerContainer": df["MaxPartsPerContainer"],
            "PartQuantity": 0,
        }
    )

if "editor_key" not in st.session_state:
    st.session_state.editor_key = 0

# Handle PDF Upload Process via Power Automate HTTP Webhook
# --- IMPORTS (Add base64 at top of script) ---
import base64
import math
import re
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ... [Keep your constants, algorithms, and hardcoded manifest data as-is] ...

# --- SIDEBAR PDF UPLOADER ---
st.sidebar.header("Invoice Auto-Fill")
pdf_file = st.sidebar.file_uploader("Upload AGS Invoice (PDF)", type=["pdf"])

pdf_triggered_calc = False

# Session state initializations
if "quantities_df" not in st.session_state:
    st.session_state.quantities_df = pd.DataFrame(
        {
            "PartName": df["PartName"],
            "ContainerType": df["ContainerType"],
            "MaxPartsPerContainer": df["MaxPartsPerContainer"],
            "PartQuantity": 0,
        }
    )

if "editor_key" not in st.session_state:
    st.session_state.editor_key = 0

# --- REPLACE THIS BLOCK IN YOUR CODE ---
if pdf_file is not None:
    if (
        "last_uploaded_pdf" not in st.session_state
        or st.session_state.last_uploaded_pdf != pdf_file.name
    ):
        with st.sidebar.status(
            "Processing PDF via Power Automate...", expanded=True
        ) as status:
            try:
                # 1. Read and encode the raw PDF bytes to Base64
                pdf_bytes = pdf_file.getvalue()
                encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

                # 2. Send JSON payload containing Base64 content
                response = requests.post(
                    POWER_AUTOMATE_URL,
                    json={
                        "$content-type": "application/pdf",
                        "$content": encoded_pdf,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                if response.status_code == 200:
                    extracted_items = response.json()

                    # Convert response to dictionary mapping base part name (9 chars) to quantity
                    extracted_counts = {}
                    if isinstance(extracted_items, list):
                        for item in extracted_items:
                            p_num = str(item.get("part_number", ""))[:9]
                            try:
                                qty = int(float(item.get("quantity", 0)))
                            except (ValueError, TypeError):
                                qty = 0
                            if p_num:
                                extracted_counts[p_num] = (
                                    extracted_counts.get(p_num, 0) + qty
                                )

                    # Map extracted quantities to DataFrame order
                    new_quantities = [
                        extracted_counts.get(p_name[:9], 0)
                        for p_name in df["PartName"]
                    ]

                    st.session_state.quantities_df["PartQuantity"] = (
                        new_quantities
                    )
                    st.session_state.last_uploaded_pdf = pdf_file.name
                    st.session_state.editor_key += 1
                    pdf_triggered_calc = True

                    status.update(
                        label="Invoice extracted successfully!",
                        state="complete",
                        expanded=False,
                    )
                    st.sidebar.success(
                        f"Extracted {sum(new_quantities)} total parts!"
                    )
                    st.rerun()
                else:
                    status.update(
                        label="Failed to parse PDF",
                        state="error",
                        expanded=False,
                    )
                    st.sidebar.error(
                        f"Power Automate Error (HTTP {response.status_code}): {response.text}"
                    )

            except Exception as e:
                status.update(
                    label="Connection Error", state="error", expanded=False
                )
                st.sidebar.error(f"Failed to call Power Automate: {e}")

# --- CENTERED QUANTITY ENTRY SECTION ---
left_pad, center_col, right_pad = st.columns([1, 2, 1])

with center_col:
    st.subheader("1. Enter Order Quantities")

    # Displays PartName, ContainerType, MaxPartsPerContainer, and editable PartQuantity
    edited_df = st.data_editor(
        st.session_state.quantities_df,
        key=f"data_editor_{st.session_state.editor_key}",
        num_rows="fixed",
        disabled=["PartName", "ContainerType", "MaxPartsPerContainer"],
        use_container_width=True,
    )

    # --- BUTTON BAR ---
    col_calc, col_clear = st.columns([3, 2])

    with col_calc:
        calculate_clicked = st.button(
            "Calculate Truck Load & Spatial Fit",
            type="primary",
            use_container_width=True,
        )

    with col_clear:
        if st.button("Clear Quantities", use_container_width=True):
            st.session_state.quantities_df["PartQuantity"] = 0
            if "last_uploaded_pdf" in st.session_state:
                del st.session_state["last_uploaded_pdf"]
            st.session_state.editor_key += 1
            st.rerun()

# Sync inputs
st.session_state.quantities_df["PartQuantity"] = edited_df["PartQuantity"]
df["PartQuantity"] = edited_df["PartQuantity"]

# --- CALCULATION AND PLOTTING ---
if calculate_clicked or pdf_triggered_calc:
    selected_parts = df[df["PartQuantity"] > 0].copy()

    if selected_parts.empty:
        st.warning(
            "Please enter a quantity greater than 0 for at least one part."
        )
        st.stop()

    containers_to_pack = []
    total_weight = 0.0

    for idx, row in selected_parts.iterrows():
        qty = int(row["PartQuantity"])
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

    weight_margin = MAX_WEIGHT_KG - total_weight
    margin_color = "#28a745" if is_weight_ok else "#dc3545"
    with col2:
        st.metric("Gross Weight", f"{total_weight:,.2f} kg")
        st.markdown(
            f"<div style='margin-top: -12px; font-size: 15px; font-weight: 600; color: {margin_color};'>"
            f"Margin: {weight_margin:,.2f} kg"
            f"</div>",
            unsafe_allow_html=True,
        )

    col3.metric("Usable Spatial Fill", f"{fill_percentage:.1f}%")
    col4.metric("Unpacked Containers", f"{unpacked_count} Units")

    st.write("")  # Spacing

    if is_weight_ok and is_space_ok:
        st.success(
            "✅ **TRUCK STATUS: FIT** — All items fit within weight and space limits."
        )
    else:
        reasons = []
        if not is_weight_ok:
            reasons.append(
                f"WEIGHT ({total_weight - MAX_WEIGHT_KG:,.2f} kg over limit)"
            )
        if not is_space_ok:
            reasons.append(f"SPACE ({unpacked_count} containers could not fit)")

        st.error(f"⚠️ **TRUCK STATUS: OVERLOADED BY {' AND '.join(reasons)}**")

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
