import io
import math
import re
import pandas as pd
import pdfplumber
import plotly.graph_objects as go
import requests
import streamlit as st

# --- PAGE SETUP ---
st.set_page_config(page_title="Trailer Tetris", layout="wide")
st.title("Trailer Optimization")

# --- POWER AUTOMATE CONFIGURATION ---
POWER_AUTOMATE_URL = st.secrets.get(
    "POWER_AUTOMATE_URL",
    "https://default9b2f9cbe865b4df8a5848494d8c1ef.f6.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/31/workflows/9687f733d7fb4262b4d8a2a0eff59bb4/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=RkJNO5xEsj9s4UFEK7Ov5C-LvAfgQEo5iQ0alG96w0E",
)

@st.cache_data(ttl=5)
def load_manifest_from_sharepoint(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # Verify response body isn't empty
        if not response.text.strip():
            st.error(
                "Received an empty response from Power Automate. Ensure the flow"
                " Response step Body is populated."
            )
            st.stop()

        try:
            data = response.json()
        except Exception:
            st.error(
                "Power Automate did not return JSON. Raw output received:\n"
                f"{response.text[:300]}"
            )
            st.stop()

        # Handle wrapped JSON response bodies if nested
        if isinstance(data, dict):
            if "value" in data:
                data = data["value"]
            elif "body" in data and isinstance(data["body"], dict):
                data = data["body"].get("value", data["body"])

        df = pd.DataFrame(data)

        if df.empty:
            st.error("Received an empty dataset from Power Automate table.")
            st.stop()

        # Clean headers and string values
        df.columns = df.columns.astype(str).str.strip()

        expected_cols = [
            "Plant",
            "PartName",
            "ContainerType",
            "ContainerLength [in]",
            "ContainerWidth",
            "ContainerHeight",
            "ContainerWeight [kg]",
            "MaxPartsPerContainer",
            "Weight of 1 Part [kg]",
        ]

        missing = [col for col in expected_cols if col not in df.columns]
        if missing:
            st.error(
                "Missing required columns in Power Automate JSON output:"
                f" {missing}\nColumns found: {list(df.columns)}"
            )
            st.stop()

        numeric_cols = [
            "ContainerLength [in]",
            "ContainerWidth",
            "ContainerHeight",
            "ContainerWeight [kg]",
            "MaxPartsPerContainer",
            "Weight of 1 Part [kg]",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["Plant"] = df["Plant"].astype(str).str.strip()
        df["PartName"] = df["PartName"].astype(str).str.strip()
        df["ContainerType"] = df["ContainerType"].astype(str).str.strip()

        df = df[
            (df["PartName"].str.len() > 0) & (df["PartName"] != "nan")
        ].reset_index(drop=True)

        return df

    except Exception as e:
        st.error(f"Failed to load catalog: {e}")
        st.stop()

# Dynamic Load from Power Automate Endpoint
df_manifest = load_manifest_from_sharepoint(POWER_AUTOMATE_URL)

# --- CONSTANTS (Trailer Specs) ---
TRAILER_LENGTH = 636.0  # inches (X-axis)
TRAILER_WIDTH = 102.0  # inches (Y-axis)
TRAILER_HEIGHT = 110.0  # inches (Z-axis)
MAX_WEIGHT_KG = 18824.083  # kg

GLOBAL_MIN_CONTAINER_LENGTH = float(df_manifest["ContainerLength [in]"].min())
GLOBAL_MIN_CONTAINER_WIDTH = float(df_manifest["ContainerWidth"].min())

# --- GLOBAL SESSION STATE INITIALIZATION ---
if "editor_key" not in st.session_state:
    st.session_state.editor_key = 0

# Sync session state with updated SharePoint values
if "quantities_df" not in st.session_state:
    st.session_state.quantities_df = pd.DataFrame({
        "Plant": df_manifest["Plant"],
        "PartName": df_manifest["PartName"],
        "ContainerType": df_manifest["ContainerType"],
        "MaxPartsPerContainer": df_manifest["MaxPartsPerContainer"],
        "PartQuantity": 0,
    })
else:
    # Preserve existing user-entered quantities
    existing_qtys = dict(
        zip(
            st.session_state.quantities_df["PartName"],
            st.session_state.quantities_df["PartQuantity"],
        )
    )

    # Rebuild DataFrame with updated SharePoint metadata + saved user quantities
    st.session_state.quantities_df = pd.DataFrame({
        "Plant": df_manifest["Plant"],
        "PartName": df_manifest["PartName"],
        "ContainerType": df_manifest["ContainerType"],
        "MaxPartsPerContainer": df_manifest["MaxPartsPerContainer"],
        "PartQuantity": [
            existing_qtys.get(p, 0) for p in df_manifest["PartName"]
        ],
    })

# --- HELPER FUNCTIONS ---
def _extract_quantity_from_line(line):
    """
    Tries several common invoice quantity formats, most specific first:
      1. "<number> EA / PCS / PC / CT / UNITS"  -- quantity BEFORE the unit
      2. A "QTY" / "QUANTITY" label followed by a number.
      3. "KG / EA <number>"                      -- unit BEFORE the number
      4. Fallback: the last "reasonable" standalone number on the line
    """
    match = re.search(r"\b(\d{1,6})\s*(?:EA|PCS?|CT|UNITS?)\b", line)
    if match:
        return int(match.group(1))

    match = re.search(r"(?:QTY|QUANTITY)[:.\s]*\s*(\d{1,6})", line)
    if match:
        return int(match.group(1))

    match = re.search(r"(?:KG|EA)\s*(\d{1,5})\b", line)
    if match:
        return int(match.group(1))

    numbers = [int(n) for n in re.findall(r"\b\d+\b", line)]
    valid_qtys = [n for n in numbers if n not in [2024, 2025, 2026, 2027, 8708] and 0 < n < 50000]
    if valid_qtys:
        return valid_qtys[-1]

    return None


def _sub_codes_for_part(part_name):
    """
    Splits a catalog PartName into the individual customer part codes it
    represents. Most parts are a single code. Shared-container entries are
    written as "CODE_A/CODE_B" (two different parts packed into the same
    container) -- each side is its own line item on an invoice, so each
    needs to be matched independently.
    """
    return [
        code.split("-")[0].strip().upper()
        for code in str(part_name).split("/")
        if code.strip()
    ]


def parse_pdf_invoice(pdf_file, df_manifest):
    """
    Extracts part quantities and invoice header metadata (Trailer Car No., Ship Date, BOL)
    from a single invoice PDF.
    """
    contributions = {}
    metadata = {
        "Trailer Car No.": "N/A",
        "Ship Date": "N/A",
        "BOL": "N/A",
    }

    try:
        with pdfplumber.open(io.BytesIO(pdf_file.getvalue())) as pdf:
            full_text = ""
            for page in pdf.pages:
                raw_text = page.extract_text() or ""
                full_text += raw_text + "\n"

                compact_text = re.sub(r"(?<=\b[A-Z0-9])\s+(?=[A-Z0-9]\b)", "", raw_text.upper())
                lines = [l.strip() for l in compact_text.split("\n") if l.strip()]

                for line in lines:
                    for part_name in df_manifest["PartName"]:
                        for sub_code in _sub_codes_for_part(part_name):
                            if sub_code in line:
                                qty = _extract_quantity_from_line(line)
                                if qty is not None:
                                    contributions.setdefault(part_name, {})[sub_code] = qty

            # Extract Header Metadata from Invoice
            trailer_match = re.search(r"TRAILER\s+CAR\s+NO\.?[:\s]*([A-Z0-9-]+)", full_text, re.IGNORECASE)
            if trailer_match:
                metadata["Trailer Car No."] = trailer_match.group(1).strip()

            ship_date_match = re.search(r"SHIP\s+DATE[:\s]*(\d{2}/\d{2}/\d{4})", full_text, re.IGNORECASE)
            if ship_date_match:
                metadata["Ship Date"] = ship_date_match.group(1).strip()

            bol_match = re.search(r"BOL[:\s]*(\d+)", full_text, re.IGNORECASE)
            if bol_match:
                metadata["BOL"] = bol_match.group(1).strip()

    except Exception:
        pass

    counts = {part_name: sum(sub_qtys.values()) for part_name, sub_qtys in contributions.items()}
    return counts, metadata


def pack_truck_realistically(containers_list, min_container_length=None, min_container_width=None):
    """
    Packs containers into the trailer using a greedy row/column/stack
    strategy, while simultaneously measuring usable trailer volume.
    """
    if min_container_length is None:
        min_container_length = GLOBAL_MIN_CONTAINER_LENGTH
    if min_container_width is None:
        min_container_width = GLOBAL_MIN_CONTAINER_WIDTH

    packed_items = []
    unpacked_items = []

    if not containers_list:
        return packed_items, unpacked_items, 0.0

    groups = {}
    for c in containers_list:
        key = (c["type"], c["length"], c["width"], c["height"])
        if key not in groups:
            groups[key] = []
        groups[key].append(c)

    sorted_group_keys = sorted(groups.keys(), key=lambda k: (k[1], k[2], k[3]), reverse=True)

    current_x = 0.0
    current_y = 0.0
    current_row_length = 0.0

    usable_volume = 0.0
    row_min_width = None

    def close_row():
        nonlocal usable_volume, row_min_width
        if row_min_width is not None:
            leftover_width = TRAILER_WIDTH - current_y
            if leftover_width >= min_container_width:
                usable_volume += current_row_length * leftover_width * TRAILER_HEIGHT
        row_min_width = None

    for key in sorted_group_keys:
        items = groups[key]
        c_type, l, w, h = key

        if l > TRAILER_LENGTH or w > TRAILER_WIDTH:
            unpacked_items.extend(items)
            continue

        max_stack_z = max(1, math.floor(TRAILER_HEIGHT / h))
        usable_stack_height = max_stack_z * h

        item_index = 0
        total_group_items = len(items)

        while item_index < total_group_items:
            if current_y + w > TRAILER_WIDTH:
                close_row()
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

            usable_volume += l * w * usable_stack_height
            row_min_width = w if row_min_width is None else min(row_min_width, w)

            current_row_length = max(current_row_length, l)
            current_y += w

    close_row()

    remaining_length = max(0.0, TRAILER_LENGTH - (current_x + current_row_length))
    if remaining_length >= min_container_length:
        usable_volume += remaining_length * TRAILER_WIDTH * TRAILER_HEIGHT

    return packed_items, unpacked_items, usable_volume


def calculate_fill_percentage(containers_to_pack, packed_items, unpacked_items, usable_volume):
    """Space Usage % calculation."""
    if not containers_to_pack:
        return 0.0

    packed_volume = sum(c["length"] * c["width"] * c["height"] for c in packed_items)

    if unpacked_items:
        unpacked_volume = sum(c["length"] * c["width"] * c["height"] for c in unpacked_items)
        overage_pct = 100.0 * unpacked_volume / usable_volume if usable_volume > 0 else 100.0
        return round(min(999.0, 100.0 + max(overage_pct, 0.1)), 1)

    if usable_volume <= 0:
        return 100.0

    return round(min(100.0, 100.0 * packed_volume / usable_volume), 1)


def evaluate_manifest_data(df_input):
    """Runs full load and fit diagnostics for a given set of part quantities."""
    working_df = df_manifest.copy()
    working_df["PartQuantity"] = df_input["PartQuantity"].values
    selected_parts = working_df[working_df["PartQuantity"] > 0].copy()

    if selected_parts.empty:
        return None

    # Determine active plants
    active_plants = selected_parts["Plant"].dropna().unique()
    plant_manifest_subset = df_manifest[df_manifest["Plant"].isin(active_plants)]

    if not plant_manifest_subset.empty:
        active_min_length = float(plant_manifest_subset["ContainerLength [in]"].min())
        active_min_width = float(plant_manifest_subset["ContainerWidth"].min())
    else:
        active_min_length = GLOBAL_MIN_CONTAINER_LENGTH
        active_min_width = GLOBAL_MIN_CONTAINER_WIDTH

    containers_to_pack = []
    total_weight = 0.0

    for idx, row in selected_parts.iterrows():
        qty = int(row["PartQuantity"])
        max_per_container = int(row["MaxPartsPerContainer"]) if not pd.isna(row["MaxPartsPerContainer"]) else 1
        num_containers = math.ceil(qty / max_per_container)

        container_empty_weight = float(row["ContainerWeight [kg]"]) if not pd.isna(row["ContainerWeight [kg]"]) else 0.0
        part_unit_weight = float(row["Weight of 1 Part [kg]"]) if not pd.isna(row["Weight of 1 Part [kg]"]) else 0.0

        remaining_parts = qty
        for i in range(num_containers):
            parts_in_this_box = min(remaining_parts, max_per_container)
            box_gross_weight = container_empty_weight + (parts_in_this_box * part_unit_weight)

            containers_to_pack.append(
                {
                    "plant": str(row["Plant"]),
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

    packed_items, unpacked_items, usable_volume = pack_truck_realistically(
        containers_to_pack,
        min_container_length=active_min_length,
        min_container_width=active_min_width
    )
    fill_percentage = calculate_fill_percentage(containers_to_pack, packed_items, unpacked_items, usable_volume)

    total_requested = len(containers_to_pack)
    unpacked_count = len(unpacked_items)

    is_weight_ok = total_weight <= MAX_WEIGHT_KG
    is_space_ok = unpacked_count == 0

    if is_weight_ok and is_space_ok:
        status = "FIT"
    else:
        reasons = []
        if not is_weight_ok:
            reasons.append("OVERWEIGHT")
        if not is_space_ok:
            reasons.append("OVER SPACE")
        status = "OVERLOADED (" + " & ".join(reasons) + ")"

    return {
        "Total Containers": total_requested,
        "Packed Containers": len(packed_items),
        "Unpacked Containers": unpacked_count,
        "Gross Weight (kg)": round(total_weight, 2),
        "Weight Capacity (kg)": MAX_WEIGHT_KG,
        "Weight Margin (kg)": round(MAX_WEIGHT_KG - total_weight, 2),
        "Weight Usage (%)": round((total_weight / MAX_WEIGHT_KG) * 100, 1),
        "Space Usage (%)": round(fill_percentage, 1),
        "Trailer Status": status,
        "packed_items": packed_items,
        "containers_to_pack": containers_to_pack,
        "fill_percentage": fill_percentage,
        "active_min_length": active_min_length,
        "active_min_width": active_min_width,
    }


def plot_3d_truck(packed_items, fill_percentage, is_overloaded):
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
    colors = ["royalblue", "crimson", "forestgreen", "darkorange", "purple", "teal", "gold"]

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
                x=x, y=y, z=z, i=i, j=j, k=k,
                color=color_map[c_type],
                opacity=0.75,
                lighting=dict(ambient=0.8, diffuse=0.8),
                flatshading=True,
                name=f"{item['part_name']} ({c_type})",
                hoverinfo="name",
            )
        )

    status_color = "red" if is_overloaded else "green"
    status_label = "OVERLOADED" if is_overloaded else "SPACE OK"

    fig.update_layout(
        title=dict(
            text=f"<b>Trailer Space Usage: <span style='color:{status_color};'>{fill_percentage:.1f}%</span> ({status_label})</b>",
            x=0.01,
            y=0.95,
            font=dict(size=18),
        ),
        scene=dict(
            xaxis=dict(title='Length (X - 636")', range=[0, TRAILER_LENGTH + 10], autorange=False),
            yaxis=dict(title='Width (Y - 102")', range=[0, TRAILER_WIDTH + 10], autorange=False),
            zaxis=dict(title='Height (Z - 110")', range=[0, TRAILER_HEIGHT + 10], autorange=False),
            aspectmode="manual",
            aspectratio=dict(x=TRAILER_LENGTH / TRAILER_LENGTH, y=TRAILER_WIDTH / TRAILER_LENGTH, z=TRAILER_HEIGHT / TRAILER_LENGTH),
        ),
        margin=dict(r=0, l=0, b=0, t=40),
    )
    return fig


# --- SIDEBAR: MULTI-INVOICE UPLOAD & COMPARISON EXPORT ---
st.sidebar.header("Batch Invoice Processing")
uploaded_pdfs = st.sidebar.file_uploader(
    "Upload multiple AGS Invoices (PDFs)", type=["pdf"], accept_multiple_files=True
)

if uploaded_pdfs:
    st.sidebar.markdown("---")
    st.sidebar.subheader("📈Export Stats to Excel (.xlsx)")
    
    if st.sidebar.button("Generate Excel Comparison", type="primary"):
        batch_summary_list = []
        
        for pdf_file in uploaded_pdfs:
            extracted_counts, meta = parse_pdf_invoice(pdf_file, df_manifest)
            temp_quantities_df = pd.DataFrame({
                "PartName": df_manifest["PartName"],
                "PartQuantity": [extracted_counts.get(p, 0) for p in df_manifest["PartName"]]
            })
            
            stats = evaluate_manifest_data(temp_quantities_df)
            
            row_data = {
                "Invoice Name": pdf_file.name,
                "Trailer Car No.": meta["Trailer Car No."],
                "Ship Date": meta["Ship Date"],
                "BOL": meta["BOL"],
            }
            
            if stats:
                # Include calculated metrics except for 'Weight Capacity (kg)' and internal objects
                excluded_keys = [
                    "packed_items",
                    "containers_to_pack",
                    "fill_percentage",
                    "active_min_length",
                    "active_min_width",
                    "Weight Capacity (kg)",
                    "Packed Containers",
                    "Unpacked Containers",
            ]
                row_data.update({k: v for k, v in stats.items() if k not in excluded_keys})
            else:
                row_data.update({
                    "Total Containers": 0,
                    "Gross Weight (kg)": 0.0,
                    "Weight Margin (kg)": 0.0,
                    "Weight Usage (%)": 0.0,
                    "Space Usage (%)": 0.0,
                    "Trailer Status": "NO MATCHING PARTS FOUND",
                })
            
            batch_summary_list.append(row_data)

        summary_df = pd.DataFrame(batch_summary_list)

        # Generate Excel buffer and apply auto-fit column widths
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            summary_df.to_excel(writer, index=False, sheet_name="Invoice Comparison")
            worksheet = writer.sheets["Invoice Comparison"]
            
            # Auto-expand columns to fit full header and cell content text
            for col in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
        excel_data = excel_buffer.getvalue()

        st.sidebar.download_button(
            label="📥 Download Excel Comparison",
            data=excel_data,
            file_name="trailer_load_comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Optional: Load single file into editor
    selected_pdf_to_view = st.sidebar.selectbox(
        "Select PDF to view in Editor",
        options=[f.name for f in uploaded_pdfs],
    )
    
    if st.sidebar.button("Load Selected into Table"):
        target_file = next(f for f in uploaded_pdfs if f.name == selected_pdf_to_view)
        extracted, _ = parse_pdf_invoice(target_file, df_manifest)
        st.session_state.quantities_df["PartQuantity"] = [extracted.get(p, 0) for p in df_manifest["PartName"]]
        st.session_state.editor_key += 1
        st.rerun()

# --- MAIN QUANTITY ENTRY SECTION ---
st.subheader("1. Enter Order Quantities")

# Search Bar implementation
search_query = st.text_input(
    "🔍 Search Catalog (by Part Name, Plant, or Container Type):",
    value="",
    placeholder="Type part number or plant..."
)

# Filter the dataframe for display based on search query
if search_query.strip():
    query = search_query.strip().lower()
    filtered_df = st.session_state.quantities_df[
        st.session_state.quantities_df["PartName"].str.lower().str.contains(query) |
        st.session_state.quantities_df["Plant"].str.lower().str.contains(query) |
        st.session_state.quantities_df["ContainerType"].str.lower().str.contains(query)
    ]
else:
    filtered_df = st.session_state.quantities_df.copy()

edited_df = st.data_editor(
    filtered_df,
    key=f"editor_widget_{st.session_state.editor_key}_{search_query}",
    num_rows="fixed",
    hide_index=True,
    disabled=["Plant", "PartName", "ContainerType", "MaxPartsPerContainer"],
    use_container_width=True,
    column_config={
        "Plant": st.column_config.TextColumn("Plant", width=100),
        "PartName": st.column_config.TextColumn("Part Name", width=260),
        "ContainerType": st.column_config.TextColumn("Container Type", width=140),
        "MaxPartsPerContainer": st.column_config.NumberColumn("Max Parts / Container", width=150),
        "PartQuantity": st.column_config.NumberColumn("Part Quantity", width=140, min_value=0, step=1),
    },
)

# Sync edits from filtered view back into global quantities_df session state
if not edited_df.empty:
    for idx, row in edited_df.iterrows():
        part_name = row["PartName"]
        new_qty = row["PartQuantity"]
        st.session_state.quantities_df.loc[
            st.session_state.quantities_df["PartName"] == part_name, "PartQuantity"
        ] = new_qty

col_calc, col_clear, _ = st.columns([2, 2, 4])

with col_calc:
    calculate_clicked = st.button("Calculate Truck Load & Spatial Fit", type="primary", use_container_width=True)

with col_clear:
    if st.button("Clear Quantities", use_container_width=True):
        st.session_state.quantities_df["PartQuantity"] = 0
        st.session_state.editor_key += 1
        st.rerun()

# --- CALCULATION AND PLOTTING ---
if calculate_clicked:
    results = evaluate_manifest_data(st.session_state.quantities_df)

    if not results:
        st.warning("Please enter a quantity greater than 0 for at least one part.")
        st.stop()

    packed_items = results["packed_items"]
    fill_percentage = results["fill_percentage"]
    unpacked_count = results["Unpacked Containers"]
    total_weight = results["Gross Weight (kg)"]
    is_weight_ok = total_weight <= MAX_WEIGHT_KG
    is_space_ok = unpacked_count == 0

    st.markdown("---")
    st.subheader("2. Load & Fit Diagnostics")

    col1, col2, col_weight_pct, col3, col4 = st.columns(5)
    col1.metric("Total Containers", f"{results['Total Containers']} Units")

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

    col_weight_pct.metric("Weight Usage", f"{results['Weight Usage (%)']}%")
    col3.metric("Space Usage", f"{fill_percentage:.1f}%")
    col4.metric("Unpacked Containers", f"{unpacked_count} Units")

    st.write("")

    if is_weight_ok and is_space_ok:
        st.success("✅ **TRAILER STATUS: FIT** — All items fit within weight and space limits.")
    else:
        st.error(f"⚠️ **TRUCK STATUS: {results['Trailer Status']}**")

    st.subheader("3. 3D Layout")

    col_plot, col_unpacked = st.columns([6, 4])

    with col_plot:
        fig_3d = plot_3d_truck(packed_items, fill_percentage, not is_space_ok)
        st.plotly_chart(fig_3d, use_container_width=True)

    with col_unpacked:
        st.markdown("### ⚠️ Unpacked Items")
        
        _, unpacked_items, _ = pack_truck_realistically(
            results["containers_to_pack"],
            min_container_length=results["active_min_length"],
            min_container_width=results["active_min_width"]
        )
        
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
                        "Unpacked_Parts_QTY": "Unpacked Part QTY",
                    }
                )
            )

            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.success("All boxes packed successfully!")
