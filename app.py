import io
from datetime import datetime, time
from urllib.parse import quote

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128


# ============================================================
# 7 SEASONS ADDRESS GENERATOR
# ============================================================

st.set_page_config(
    page_title="7 Seasons Address Generator",
    layout="wide"
)

st.title("🌱 7 Seasons Address Generator")
st.caption("Live Order Processing, Address Labels & Packing Tool")


# ============================================================
# GOOGLE SHEET
# ============================================================

SHEET_ID = "1IAYZM4o4ko9QDdOwLXPe1zF3838Z5V_m2HsOaFpT2Hc"

STATE_SHEETS = {
    "Kerala": "KERALA",
    "Tamil Nadu": "TAMILNADU",
    "Karnataka": "KARNATAKA",
}

REPLACEMENT_SHEET = "REPLACEMENT COMMON"


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_number(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value.endswith(".0"):
        value = value[:-2]

    try:
        if "e" in value.lower():
            value = str(int(float(value)))
    except Exception:
        pass

    return value


def clean_text(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_header(value):
    return " ".join(str(value).strip().upper().split())


def normalize_state(value):
    value = normalize_header(value)

    mapping = {
        "KERALA": "Kerala",
        "KL": "Kerala",

        "KARNATAKA": "Karnataka",
        "KA": "Karnataka",

        "TAMIL NADU": "Tamil Nadu",
        "TAMILNADU": "Tamil Nadu",
        "TAMILNAD": "Tamil Nadu",
        "TN": "Tamil Nadu",
    }

    return mapping.get(value, clean_text(value))


def normalize_courier(value):
    value = normalize_header(value)

    mapping = {
        "D": "DTDC",
        "DTDC": "DTDC",

        "P": "PROFESSIONAL",
        "PROFESSIONAL": "PROFESSIONAL",
        "PROFESSIONAL COURIER": "PROFESSIONAL",

        "POST": "POST",
        "POST OFFICE": "POST",

        "SPEED POST": "SPEED POST",
        "SPEEDPOST": "SPEED POST",
        "SP": "SPEED POST",
    }

    return mapping.get(value, value)


def courier_for_label(value):
    value = normalize_courier(value)

    if value == "PROFESSIONAL":
        return "P"

    return value


def parse_tracking_numbers(text):
    values = []

    for line in text.splitlines():
        value = line.strip()

        if value:
            values.append(value)

    return values


# ============================================================
# GOOGLE SHEET LOADING
# ============================================================

@st.cache_data(ttl=30)
def read_google_tab(sheet_name):
    encoded_sheet = quote(sheet_name)

    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={encoded_sheet}"
    )

    df = pd.read_csv(
        url,
        dtype=str,
        keep_default_na=False
    )

    df.columns = [
        normalize_header(column)
        for column in df.columns
    ]

    return df


def find_column(df, possible_names):
    columns = {
        normalize_header(column): column
        for column in df.columns
    }

    for possible in possible_names:
        key = normalize_header(possible)

        if key in columns:
            return columns[key]

    return None


# ============================================================
# NORMAL STATE SHEETS
# ============================================================

def load_state_orders(sheet_name):
    df = read_google_tab(sheet_name)

    timestamp_col = find_column(
        df,
        ["TIMESTAMP", "TIME STAMP"]
    )

    name_col = find_column(
        df,
        ["NAME", "CUSTOMER NAME"]
    )

    address_col = find_column(
        df,
        ["ADDRESS", "CUSTOMER ADDRESS"]
    )

    district_col = find_column(
        df,
        ["DISTRICT"]
    )

    pin_col = find_column(
        df,
        ["PIN", "PIN CODE", "PINCODE"]
    )

    phone_col = find_column(
        df,
        [
            "PHONE NUMBER",
            "PHONE  NUMBER",
            "MOBILE",
            "MOBILE NUMBER",
            "PHONE"
        ]
    )

    item_col = find_column(
        df,
        [
            "ITEM",
            "ITEMS",
            "ITEM PURCHASED",
            "PRODUCT",
            "PLANT"
        ]
    )

    courier_col = find_column(
        df,
        [
            "COURIER",
            "COURIER TYPE",
            "COURIER SERVICE"
        ]
    )

    required = {
        "TIMESTAMP": timestamp_col,
        "NAME": name_col,
        "ADDRESS": address_col,
        "DISTRICT": district_col,
        "PIN": pin_col,
        "PHONE NUMBER": phone_col,
        "ITEM": item_col,
    }

    missing = [
        name
        for name, column in required.items()
        if column is None
    ]

    if missing:
        raise ValueError(
            "Missing columns in "
            + sheet_name
            + ": "
            + ", ".join(missing)
        )

    output = pd.DataFrame()

    # IMPORTANT:
    # Your timestamps are like:
    # 9/29/2026 9:41:23
    # so dayfirst MUST be False.

    output["TIMESTAMP"] = pd.to_datetime(
        df[timestamp_col],
        errors="coerce",
        dayfirst=False
    )

    output["NAME"] = df[name_col].apply(clean_text)
    output["ADDRESS"] = df[address_col].apply(clean_text)
    output["DISTRICT"] = df[district_col].apply(clean_text)
    output["PIN"] = df[pin_col].apply(clean_number)
    output["PHONE NUMBER"] = df[phone_col].apply(clean_number)
    output["ITEM"] = df[item_col].apply(clean_text)

    if courier_col is not None:
        output["COURIER"] = df[courier_col].apply(
            normalize_courier
        )
    else:
        output["COURIER"] = ""

    return output


# ============================================================
# REPLACEMENT COMMON
#
# A = TIMESTAMP
# B = NAME + ADDRESS
# C = ITEM
# D = STATE
# G = COURIER
# ============================================================

def load_replacements():
    df = read_google_tab(REPLACEMENT_SHEET)

    if df.shape[1] < 7:
        raise ValueError(
            "REPLACEMENT COMMON must contain at least columns A to G."
        )

    output = pd.DataFrame()

    output["TIMESTAMP"] = pd.to_datetime(
        df.iloc[:, 0],
        errors="coerce",
        dayfirst=False
    )

    output["FULL ADDRESS"] = (
        df.iloc[:, 1]
        .apply(clean_text)
    )

    output["ITEM"] = (
        df.iloc[:, 2]
        .apply(clean_text)
    )

    output["STATE"] = (
        df.iloc[:, 3]
        .apply(normalize_state)
    )

    output["COURIER"] = (
        df.iloc[:, 6]
        .apply(normalize_courier)
    )

    return output


# ============================================================
# SORTING
# ============================================================

def sort_by_item(df):
    if df.empty:
        return df.reset_index(drop=True)

    working = df.copy()

    working["_SORT_ITEM"] = (
        working["ITEM"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
    )

    working = working.sort_values(
        "_SORT_ITEM",
        kind="stable"
    )

    working = working.drop(
        columns=["_SORT_ITEM"]
    )

    return working.reset_index(drop=True)


# ============================================================
# DATE / TIME FILTER
# ============================================================

def filter_period(df, start_dt, end_dt):
    return df[
        (df["TIMESTAMP"] >= start_dt)
        &
        (df["TIMESTAMP"] <= end_dt)
    ].copy()


# ============================================================
# ITEM COUNTS
# ============================================================

def get_item_counts(df):
    if df.empty:
        return pd.DataFrame(
            columns=["ITEM", "COUNT"]
        )

    working = df.copy()

    working["ITEM"] = (
        working["ITEM"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    working = working[
        working["ITEM"] != ""
    ]

    counts = (
        working
        .groupby("ITEM", as_index=False)
        .size()
        .rename(columns={"size": "COUNT"})
    )

    counts["_SORT"] = (
        counts["ITEM"]
        .astype(str)
        .str.casefold()
    )

    counts = (
        counts
        .sort_values("_SORT")
        .drop(columns="_SORT")
        .reset_index(drop=True)
    )

    return counts


def make_item_count_pdf(df, heading):
    counts = get_item_counts(df)

    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    page_width, page_height = A4

    left = 18 * mm
    right = 18 * mm
    top = page_height - 18 * mm

    def draw_header():
        c.setFont(
            "Helvetica-Bold",
            16
        )

        c.drawString(
            left,
            top,
            heading
        )

        c.setFont(
            "Helvetica-Bold",
            11
        )

        c.drawString(
            left,
            top - 12 * mm,
            "ITEM"
        )

        c.drawRightString(
            page_width - right,
            top - 12 * mm,
            "COUNT"
        )

        c.line(
            left,
            top - 14 * mm,
            page_width - right,
            top - 14 * mm
        )

        return top - 22 * mm

    y = draw_header()

    total = 0

    for _, row in counts.iterrows():
        if y < 25 * mm:
            c.showPage()
            y = draw_header()

        item = clean_text(row["ITEM"])
        count = int(row["COUNT"])

        total += count

        c.setFont(
            "Helvetica",
            11
        )

        # Shorten only visually if extremely long
        display_item = item

        if len(display_item) > 65:
            display_item = display_item[:62] + "..."

        c.drawString(
            left,
            y,
            display_item
        )

        c.setFont(
            "Helvetica-Bold",
            11
        )

        c.drawRightString(
            page_width - right,
            y,
            str(count)
        )

        y -= 8 * mm

    if y < 25 * mm:
        c.showPage()
        y = top

    c.line(
        left,
        y,
        page_width - right,
        y
    )

    y -= 8 * mm

    c.setFont(
        "Helvetica-Bold",
        12
    )

    c.drawString(
        left,
        y,
        "TOTAL"
    )

    c.drawRightString(
        page_width - right,
        y,
        str(total)
    )

    c.save()

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# EXCEL ADDRESS DOWNLOAD
# ============================================================

def make_address_excel(
    df,
    tracking_numbers=None,
    replacement=False
):
    export = df.copy()

    if tracking_numbers is not None:
        export["TRACKING NUMBER"] = tracking_numbers

    # Timestamp is deliberately excluded from employee output.

    if replacement:
        wanted = [
            "FULL ADDRESS",
            "ITEM",
            "STATE",
            "COURIER",
        ]
    else:
        wanted = [
            "NAME",
            "ADDRESS",
            "DISTRICT",
            "PIN",
            "PHONE NUMBER",
            "ITEM",
            "COURIER",
        ]

    if "TRACKING NUMBER" in export.columns:
        wanted.append(
            "TRACKING NUMBER"
        )

    wanted = [
        column
        for column in wanted
        if column in export.columns
    ]

    export = export[wanted]

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        export.to_excel(
            writer,
            index=False,
            sheet_name="ADDRESSES"
        )

        ws = writer.book["ADDRESSES"]

        ws.freeze_panes = "A2"

        for cell in ws[1]:
            cell.font = cell.font.copy(
                bold=True
            )

        for column_cells in ws.columns:
            max_length = 0

            column_letter = (
                column_cells[0].column_letter
            )

            for cell in column_cells:
                value = (
                    ""
                    if cell.value is None
                    else str(cell.value)
                )

                max_length = max(
                    max_length,
                    len(value)
                )

            ws.column_dimensions[
                column_letter
            ].width = min(
                max(max_length + 2, 12),
                60
            )

    output.seek(0)

    return output.getvalue()


# ============================================================
# PDF TEXT WRAPPING
# ============================================================

def draw_multiline(
    c,
    text,
    x,
    y,
    max_width,
    font="Helvetica",
    size=9,
    leading=10.5,
    max_lines=4
):
    text = clean_text(text)

    words = text.split()

    lines = []
    current = ""

    for word in words:
        trial = (
            word
            if not current
            else current + " " + word
        )

        if (
            c.stringWidth(
                trial,
                font,
                size
            )
            <= max_width
        ):
            current = trial

        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    c.setFont(
        font,
        size
    )

    for line in lines[:max_lines]:
        c.drawString(
            x,
            y,
            line
        )

        y -= leading

    return y


# ============================================================
# NORMAL ADDRESS LABEL
# ============================================================

def draw_normal_label(
    c,
    row,
    x,
    y_top,
    width,
    height,
    tracking=None
):
    padding = 5 * mm

    x0 = x + padding
    y = y_top - padding
    max_width = width - (2 * padding)

    y = draw_multiline(
        c,
        row["NAME"],
        x0,
        y,
        max_width,
        "Helvetica-Bold",
        10.5,
        12,
        2
    )

    y -= 1

    y = draw_multiline(
        c,
        row["ADDRESS"],
        x0,
        y,
        max_width,
        "Helvetica",
        9,
        10.5,
        4
    )

    y = draw_multiline(
        c,
        f'District: {row["DISTRICT"]}',
        x0,
        y - 1,
        max_width,
        "Helvetica",
        9,
        10.5,
        2
    )

    y = draw_multiline(
        c,
        f'PIN: {row["PIN"]}',
        x0,
        y - 1,
        max_width,
        "Helvetica-Bold",
        9.5,
        11,
        1
    )

    y = draw_multiline(
        c,
        f'Phone: {row["PHONE NUMBER"]}',
        x0,
        y - 1,
        max_width,
        "Helvetica",
        9,
        10.5,
        1
    )

    y = draw_multiline(
        c,
        f'Item: {row["ITEM"]}',
        x0,
        y - 1,
        max_width,
        "Helvetica-Bold",
        9,
        10.5,
        2
    )

    courier = courier_for_label(
        row.get("COURIER", "")
    )

    if courier:
        y = draw_multiline(
            c,
            f"Courier: {courier}",
            x0,
            y - 1,
            max_width,
            "Helvetica-Bold",
            9.5,
            11,
            1
        )

    if tracking:
        y -= 2

        c.setFont(
            "Helvetica-Bold",
            9
        )

        c.drawString(
            x0,
            y,
            f"Tracking: {tracking}"
        )

        barcode = code128.Code128(
            str(tracking),
            barHeight=12 * mm,
            barWidth=0.38 * mm,
            humanReadable=False
        )

        scale = min(
            1.0,
            max_width / barcode.width
        )

        barcode_y = max(
            y - 16 * mm,
            y_top - height + 5 * mm
        )

        c.saveState()

        c.translate(
            x0,
            barcode_y
        )

        c.scale(
            scale,
            1
        )

        barcode.drawOn(
            c,
            0,
            0
        )

        c.restoreState()


# ============================================================
# REPLACEMENT ADDRESS LABEL
# ============================================================

def draw_replacement_label(
    c,
    row,
    x,
    y_top,
    width,
    height,
    tracking=None
):
    padding = 5 * mm

    x0 = x + padding
    y = y_top - padding
    max_width = width - (2 * padding)

    y = draw_multiline(
        c,
        row["FULL ADDRESS"],
        x0,
        y,
        max_width,
        "Helvetica-Bold",
        10,
        11.5,
        7
    )

    y -= 2

    y = draw_multiline(
        c,
        f'Item: {row["ITEM"]}',
        x0,
        y,
        max_width,
        "Helvetica-Bold",
        9.5,
        11,
        2
    )

    y = draw_multiline(
        c,
        f'State: {row["STATE"]}',
        x0,
        y - 1,
        max_width,
        "Helvetica",
        9,
        10.5,
        1
    )

    courier = courier_for_label(
        row["COURIER"]
    )

    if courier:
        y = draw_multiline(
            c,
            f"Courier: {courier}",
            x0,
            y - 1,
            max_width,
            "Helvetica-Bold",
            9.5,
            11,
            1
        )

    if tracking:
        y -= 2

        c.setFont(
            "Helvetica-Bold",
            9
        )

        c.drawString(
            x0,
            y,
            f"Tracking: {tracking}"
        )

        barcode = code128.Code128(
            str(tracking),
            barHeight=12 * mm,
            barWidth=0.38 * mm,
            humanReadable=False
        )

        scale = min(
            1.0,
            max_width / barcode.width
        )

        barcode_y = max(
            y - 16 * mm,
            y_top - height + 5 * mm
        )

        c.saveState()

        c.translate(
            x0,
            barcode_y
        )

        c.scale(
            scale,
            1
        )

        barcode.drawOn(
            c,
            0,
            0
        )

        c.restoreState()


# ============================================================
# ADDRESS PDF
#
# DTDC = 6 per page
# Other = 8 per page
# ============================================================

def make_address_pdf(
    df,
    tracking_numbers=None,
    replacement=False
):
    buffer = io.BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    page_width, page_height = A4

    has_tracking = (
        tracking_numbers is not None
        and len(tracking_numbers) > 0
    )

    if has_tracking:
        columns = 2
        rows = 3
    else:
        columns = 2
        rows = 4

    per_page = columns * rows

    label_width = (
        page_width / columns
    )

    label_height = (
        page_height / rows
    )

    records = df.to_dict("records")

    for index, record in enumerate(records):
        position = index % per_page

        if (
            position == 0
            and index > 0
        ):
            c.showPage()

        row_number = (
            position // columns
        )

        column_number = (
            position % columns
        )

        x = (
            column_number
            * label_width
        )

        y_top = (
            page_height
            - row_number
            * label_height
        )

        c.setLineWidth(0.25)

        c.rect(
            x,
            y_top - label_height,
            label_width,
            label_height
        )

        tracking = None

        if has_tracking:
            tracking = (
                tracking_numbers[index]
            )

        if replacement:
            draw_replacement_label(
                c,
                record,
                x,
                y_top,
                label_width,
                label_height,
                tracking
            )

        else:
            draw_normal_label(
                c,
                record,
                x,
                y_top,
                label_width,
                label_height,
                tracking
            )

    c.save()

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# TRACKING UI
# ============================================================

def tracking_section(df):
    st.subheader(
        "DTDC Tracking Numbers"
    )

    st.info(
        "The addresses are already sorted by Item A → Z. "
        "Tracking numbers will be attached in exactly this order."
    )

    tracking_text = st.text_area(
        "Paste DTDC Tracking Numbers — one per line",
        height=220,
        placeholder=(
            "R1002280902\n"
            "R1002280903\n"
            "R1002280904"
        )
    )

    tracking_numbers = (
        parse_tracking_numbers(
            tracking_text
        )
    )

    st.write(
        f"Addresses: **{len(df)}** | "
        f"Tracking numbers pasted: "
        f"**{len(tracking_numbers)}**"
    )

    ready = (
        len(df) > 0
        and len(tracking_numbers)
        == len(df)
    )

    if not ready:
        st.warning(
            "The number of tracking numbers must exactly "
            "match the number of DTDC addresses."
        )
    else:
        st.success(
            "Counts match. DTDC files are ready."
        )

    return tracking_numbers, ready


# ============================================================
# DOWNLOAD AREA
# ============================================================

def show_downloads(
    df,
    filename_prefix,
    heading,
    tracking_numbers=None,
    replacement=False,
    ready=True
):
    if df.empty:
        return

    st.subheader(
        "Packing Item Count"
    )

    counts = get_item_counts(df)

    st.dataframe(
        counts,
        use_container_width=True,
        hide_index=True
    )

    count_pdf = make_item_count_pdf(
        df,
        f"{heading} - Item Count"
    )

    st.download_button(
        "📋 Download Item Count PDF",
        data=count_pdf,
        file_name=(
            f"{filename_prefix}_item_count.pdf"
        ),
        mime="application/pdf"
    )

    if not ready:
        return

    address_pdf = make_address_pdf(
        df,
        tracking_numbers=tracking_numbers,
        replacement=replacement
    )

    address_excel = make_address_excel(
        df,
        tracking_numbers=tracking_numbers,
        replacement=replacement
    )

    st.subheader(
        "Address Downloads"
    )

    d1, d2 = st.columns(2)

    with d1:
        st.download_button(
            "📄 Download Address PDF",
            data=address_pdf,
            file_name=(
                f"{filename_prefix}_addresses.pdf"
            ),
            mime="application/pdf"
        )

    with d2:
        st.download_button(
            "📊 Download Address Excel",
            data=address_excel,
            file_name=(
                f"{filename_prefix}_addresses.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )


# ============================================================
# TOP MODE
# ============================================================

mode = st.radio(
    "Select Order Type",
    [
        "Regular Orders",
        "Replacement"
    ],
    horizontal=True
)


state = st.selectbox(
    "Select State",
    [
        "Kerala",
        "Tamil Nadu",
        "Karnataka"
    ]
)


# ============================================================
# LOAD DATA
# ============================================================

try:
    if mode == "Regular Orders":
        selected_sheet = (
            STATE_SHEETS[state]
        )

        orders = load_state_orders(
            selected_sheet
        )

        replacement_mode = False

    else:
        orders = load_replacements()

        orders = orders[
            orders["STATE"] == state
        ].copy()

        selected_sheet = (
            REPLACEMENT_SHEET
        )

        replacement_mode = True

except Exception as error:
    st.error(
        f"Could not load {selected_sheet if 'selected_sheet' in locals() else 'Google Sheet'}."
    )

    st.error(str(error))

    st.info(
        "Check that the Google Sheet is accessible "
        "and that the tab name/columns match the program."
    )

    st.stop()


st.success(
    f"Live Google Sheet connected — {selected_sheet}"
)


# ============================================================
# REFRESH
# ============================================================

if st.button(
    "🔄 Refresh Live Data"
):
    st.cache_data.clear()
    st.rerun()


# ============================================================
# TIMESTAMP RANGE
# ============================================================

valid_timestamps = (
    orders["TIMESTAMP"]
    .dropna()
)

if valid_timestamps.empty:
    st.error(
        "No valid timestamps were found "
        "for this selection."
    )

    st.stop()


min_date = (
    valid_timestamps
    .min()
    .date()
)

max_date = (
    valid_timestamps
    .max()
    .date()
)


st.subheader(
    "Select Order Period"
)


date_col1, date_col2 = (
    st.columns(2)
)


with date_col1:
    start_date = st.date_input(
        "From Date",
        value=max_date,
        min_value=min_date,
        max_value=max_date
    )

    start_time = st.time_input(
        "From Time",
        value=time(0, 0, 0)
    )


with date_col2:
    end_date = st.date_input(
        "To Date",
        value=max_date,
        min_value=min_date,
        max_value=max_date
    )

    end_time = st.time_input(
        "To Time",
        value=time(23, 59, 59)
    )


start_datetime = datetime.combine(
    start_date,
    start_time
)

end_datetime = datetime.combine(
    end_date,
    end_time
)


if start_datetime > end_datetime:
    st.error(
        "From date/time cannot be after To date/time."
    )

    st.stop()


filtered = filter_period(
    orders,
    start_datetime,
    end_datetime
)


# ============================================================
# COURIER LOGIC
# ============================================================

# Kerala:
# User chooses courier.
#
# Tamil Nadu + Karnataka:
# No courier selection.
# All orders in that state/date period are used.

selected_courier = None


if state == "Kerala":
    selected_courier = st.selectbox(
        "Select Courier",
        [
            "DTDC",
            "PROFESSIONAL",
            "POST",
            "SPEED POST"
        ]
    )

    final_orders = filtered[
        filtered["COURIER"]
        == selected_courier
    ].copy()

else:
    final_orders = (
        filtered.copy()
    )


# ============================================================
# SORT ITEM A-Z
# ============================================================

final_orders = sort_by_item(
    final_orders
)


# ============================================================
# COUNTS
# ============================================================

st.subheader(
    "Orders Found"
)

st.write(
    f"**{len(final_orders)} addresses** "
    f"for {state}"
)

if selected_courier:
    st.write(
        f"Courier: **{selected_courier}**"
    )


# ============================================================
# PREVIEW
# ============================================================

st.subheader(
    "Final Sorted Addresses"
)


if final_orders.empty:
    st.info(
        "No matching addresses were found "
        "for this state and date/time range."
    )

    st.stop()


if replacement_mode:
    preview_columns = [
        "FULL ADDRESS",
        "ITEM",
        "STATE",
        "COURIER"
    ]

else:
    preview_columns = [
        "NAME",
        "ADDRESS",
        "DISTRICT",
        "PIN",
        "PHONE NUMBER",
        "ITEM",
        "COURIER"
    ]


st.dataframe(
    final_orders[
        preview_columns
    ],
    use_container_width=True,
    hide_index=True
)


# ============================================================
# DETERMINE WHETHER DTDC TRACKING IS REQUIRED
# ============================================================

tracking_numbers = None
ready = True


# Kerala regular/replacement:
# if DTDC selected, use tracking box.

if (
    state == "Kerala"
    and selected_courier == "DTDC"
):
    tracking_numbers, ready = (
        tracking_section(
            final_orders
        )
    )


# ============================================================
# FILENAMES
# ============================================================

safe_state = (
    state
    .lower()
    .replace(" ", "_")
)

safe_mode = (
    "replacement"
    if replacement_mode
    else "regular"
)

safe_courier = ""

if selected_courier:
    safe_courier = (
        "_"
        + selected_courier
        .lower()
        .replace(" ", "_")
    )


filename_prefix = (
    f"{safe_mode}_"
    f"{safe_state}"
    f"{safe_courier}_"
    f"{start_date}_to_{end_date}"
)


heading = (
    f"{'Replacement' if replacement_mode else 'Regular Orders'} "
    f"- {state}"
)

if selected_courier:
    heading += (
        f" - {selected_courier}"
    )


# ============================================================
# DOWNLOADS
# ============================================================

show_downloads(
    final_orders,
    filename_prefix,
    heading,
    tracking_numbers=tracking_numbers,
    replacement=replacement_mode,
    ready=ready
)