"""
Beast Academy Readability Analyzer
───────────────────────────────────
Single-file Streamlit application.
Run with:  streamlit run app.py
"""

import html as html_module
import re

import pandas as pd
import pdfplumber
import streamlit as st
import syllapy
import textstat

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

ZONE_COLORS = {
    "Dialogue":     "#AED6F1",  # pastel blue
    "Math Problem": "#A9DFBF",  # pastel green
    "Narration":    "#FAD7A0",  # pastel amber
}

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

def extract_pdf_text(file) -> str:
    """Extract text from a PDF, separating pages with a visible marker."""
    pages = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)
    return "\n\n───── Page Break ─────\n\n".join(pages)


def count_syllables(word: str) -> int:
    """Count syllables using syllapy, falling back to a vowel-group heuristic."""
    clean = re.sub(r"[^a-zA-Z]", "", word).lower()
    if not clean:
        return 0
    n = syllapy.count(clean)
    if n:
        return n
    # Vowel-group fallback for unknown words
    cnt, prev_vowel = 0, False
    for ch in clean:
        is_vowel = ch in "aeiouy"
        if is_vowel and not prev_vowel:
            cnt += 1
        prev_vowel = is_vowel
    if clean.endswith("e") and cnt > 1:
        cnt -= 1
    return max(1, cnt)


def split_into_sentences(text: str) -> list:
    """
    Split text at sentence boundaries.
    Splits after . ! ? when followed by whitespace + capital letter or quote,
    which avoids splitting on most abbreviations (Mr., Dr., etc.).
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def fk_grade(text: str) -> float:
    """Compute Flesch-Kincaid grade level, clamped to ≥ 0."""
    try:
        return max(round(textstat.flesch_kincaid_grade(text), 1), 0.0)
    except Exception:
        return 0.0


def render_zone_html(zone_text: str, zone_type: str, target: float) -> str:
    """
    Build and return the HTML block for a tagged zone, with:
      • Background color matching the zone type
      • Red underline on words with ≥ 3 syllables
      • Orange background on sentences whose FK grade exceeds the target
    """
    bg = ZONE_COLORS.get(zone_type, "#ffffff")
    sentences = split_into_sentences(zone_text)
    rendered_sentences = []

    for sentence in sentences:
        above_target = fk_grade(sentence) > target

        # Tokenize while preserving whitespace tokens
        tokens = re.split(r"(\s+)", sentence)
        word_html = []
        for tok in tokens:
            alpha_only = re.sub(r"[^a-zA-Z]", "", tok)
            if alpha_only and count_syllables(alpha_only) >= 3:
                word_html.append(
                    '<span style="'
                    "text-decoration:underline;"
                    "text-decoration-color:#cc0000;"
                    'text-underline-offset:3px;">'
                    + html_module.escape(tok)
                    + "</span>"
                )
            else:
                word_html.append(html_module.escape(tok))

        sentence_content = "".join(word_html)

        if above_target:
            rendered_sentences.append(
                '<span style="'
                "background:rgba(255,140,0,0.38);"
                'border-radius:3px;padding:1px 2px;">'
                + sentence_content
                + "</span>"
            )
        else:
            rendered_sentences.append(sentence_content)

    body = " ".join(rendered_sentences)
    label = html_module.escape(zone_type)

    return (
        f'<div style="background:{bg};padding:14px 18px;border-radius:10px;'
        f"margin:10px 0;border-left:5px solid rgba(0,0,0,0.18);"
        f'font-size:15px;line-height:1.9;">'
        f'<span style="font-size:10.5px;font-weight:800;text-transform:uppercase;'
        f'letter-spacing:1.5px;color:#555;">{label}</span>'
        f'<hr style="margin:7px 0 10px;border:none;border-top:1px solid rgba(0,0,0,0.12);">'
        f"{body}"
        f"</div>"
    )


def zone_summary_row(zone: dict, target: float) -> dict:
    """Compute summary statistics for a single tagged zone."""
    text = zone["text"]
    words = re.findall(r"\b[a-zA-Z]+\b", text)
    grade = fk_grade(text)
    return {
        "Zone Type":        zone["label"],
        "Words":            len(words),
        "Est. Grade Level": grade,
        "Target Grade":     int(target),
        "Status":           "✅ On Target" if grade <= target else "⚠️ Above Target",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Page configuration
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Beast Academy Readability Analyzer",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Session state initialization
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULTS = {
    "zones":      [],   # list of {"text": str, "label": str}
    "pdf_text":   "",   # raw text extracted from the uploaded PDF
    "last_fname": "",   # filename of the most recently processed PDF
    "zone_key":   0,    # incremented to force-reset the zone text-area widget
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — grade-level target sliders & visual legend
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🎯 Grade Level Targets")
    st.caption("Set a target reading grade level (1–8) for each zone type.")

    dialogue_target  = st.slider("Dialogue",     min_value=1, max_value=8, value=5)
    math_target      = st.slider("Math Problem", min_value=1, max_value=8, value=3)
    narration_target = st.slider("Narration",    min_value=1, max_value=8, value=4)

    TARGETS = {
        "Dialogue":     dialogue_target,
        "Math Problem": math_target,
        "Narration":    narration_target,
    }

    st.divider()
    st.markdown("**Zone colors**")
    for lbl, clr in ZONE_COLORS.items():
        st.markdown(
            f'<span style="display:inline-block;width:13px;height:13px;'
            f'background:{clr};border:1px solid #aaa;border-radius:3px;'
            f'vertical-align:middle;margin-right:8px;"></span>{lbl}',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("**Highlighting key**")
    st.markdown(
        '<span style="text-decoration:underline;text-decoration-color:#cc0000;'
        'text-underline-offset:3px;">word</span>&nbsp; = 3 + syllables',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span style="background:rgba(255,140,0,0.38);padding:2px 7px;'
        'border-radius:3px;">sentence</span>&nbsp; = above target grade',
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Title & instructions
# ──────────────────────────────────────────────────────────────────────────────

st.title("📚 Beast Academy Readability Analyzer")

with st.expander("📖  How to use this tool — start here!", expanded=True):
    st.markdown(
        """
Welcome! This tool checks whether sections of a **Beast Academy script** are written at
the right reading level for your students. No technical knowledge is needed — just follow
the steps below.

| Step | What to do |
|------|-----------|
| **1 · Upload** | Click *Browse files* and select your Beast Academy PDF. The text will be extracted automatically. |
| **2 · Edit** | The extracted text appears in an editable box. Fix any characters the PDF reader may have garbled before moving on. |
| **3 · Tag zones** | Copy a passage from the text box, paste it into the *Zone Text* area, choose a zone type (Dialogue / Math Problem / Narration), and click **Add Zone**. Repeat for every section you want to analyze. |
| **4 · Set targets** | Use the **sidebar sliders** to choose your target grade level for each zone type. The defaults are Dialogue = 5, Math Problem = 3, Narration = 4. |
| **5 · Read results** | Color-coded zone blocks appear below. <span style="text-decoration:underline;text-decoration-color:#cc0000;text-underline-offset:3px;">Words underlined in red</span> have 3 or more syllables. <span style="background:rgba(255,140,0,0.38);padding:0 4px;border-radius:3px;">Sentences highlighted in orange</span> are above your target grade level. Scroll to the bottom for a **summary table** of all zones. |

💡 *Tip: Click the ❌ button next to any zone to remove it and re-tag it if you made a mistake.*
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — PDF upload
# ──────────────────────────────────────────────────────────────────────────────

st.subheader("Step 1 — Upload your PDF")

uploaded = st.file_uploader(
    "Select a Beast Academy PDF",
    type="pdf",
    label_visibility="collapsed",
)

if uploaded is not None and uploaded.name != st.session_state.last_fname:
    with st.spinner("Extracting text from PDF …"):
        st.session_state.pdf_text = extract_pdf_text(uploaded)
    st.session_state.last_fname = uploaded.name
    # Delete the text-area widget state so the new content becomes the default
    if "pdf_editor" in st.session_state:
        del st.session_state["pdf_editor"]
    st.success(f"✅  Text extracted from **{uploaded.name}**.")

# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Editable extracted text
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.pdf_text:
    st.subheader("Step 2 — Review & edit extracted text")
    st.caption(
        "Fix any characters the PDF reader may have misread. "
        "Then copy passages from here to paste into the zone tagger below."
    )
    # Keyed widget: Streamlit preserves user edits between reruns.
    # Deleting the key above (on new file upload) forces it to reset to `value`.
    st.text_area(
        "Extracted text",
        value=st.session_state.pdf_text,
        height=380,
        key="pdf_editor",
        label_visibility="collapsed",
    )

# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Zone tagging
# ──────────────────────────────────────────────────────────────────────────────

st.subheader("Step 3 — Tag zones")
st.caption(
    "Paste a passage from the text above, choose its zone type, "
    "then click **Add Zone**. Repeat for each passage you want to analyze."
)

ta_col, ctrl_col = st.columns([3, 1])

with ta_col:
    zone_text_input = st.text_area(
        "Zone text",
        height=165,
        placeholder="Paste a passage from the extracted text above …",
        # Incrementing key resets this widget after a zone is added
        key=f"zone_ta_{st.session_state.zone_key}",
        label_visibility="collapsed",
    )

with ctrl_col:
    zone_type_sel = st.radio(
        "Zone type",
        ["Dialogue", "Math Problem", "Narration"],
        label_visibility="collapsed",
    )
    btn_add   = st.button("➕  Add Zone",       type="primary", use_container_width=True)
    btn_clear = st.button("🗑️  Clear All Zones", use_container_width=True)

if btn_add:
    if zone_text_input.strip():
        st.session_state.zones.append(
            {"text": zone_text_input.strip(), "label": zone_type_sel}
        )
        st.session_state.zone_key += 1  # resets the text-area on next render
        st.rerun()
    else:
        st.warning("Please paste some text into the Zone Text box before clicking Add Zone.")

if btn_clear:
    st.session_state.zones.clear()
    st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Analyzed zones
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.zones:
    st.subheader("Step 4 — Analyzed zones")

    # Inline legend banner
    st.markdown(
        '<div style="background:#f0f2f6;border-radius:7px;padding:9px 14px;'
        "font-size:13px;margin-bottom:14px;\">"
        "<b>Legend: </b>"
        '<span style="text-decoration:underline;text-decoration-color:#cc0000;'
        'text-underline-offset:3px;">word</span> = 3+ syllables'
        "&nbsp;|&nbsp;"
        '<span style="background:rgba(255,140,0,0.38);padding:1px 6px;'
        'border-radius:3px;">sentence</span> = above target grade level'
        "</div>",
        unsafe_allow_html=True,
    )

    for idx, zone in enumerate(list(st.session_state.zones)):
        target   = TARGETS[zone["label"]]
        zone_col, del_col = st.columns([14, 1])

        with zone_col:
            st.markdown(
                render_zone_html(zone["text"], zone["label"], target),
                unsafe_allow_html=True,
            )

        with del_col:
            # Small spacer so the button sits vertically centered in the block
            st.write("")
            st.write("")
            if st.button("❌", key=f"del_{idx}", help="Remove this zone"):
                st.session_state.zones.pop(idx)
                st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5 — Summary table
    # ──────────────────────────────────────────────────────────────────────────

    st.subheader("Step 5 — Summary")

    rows = [zone_summary_row(z, TARGETS[z["label"]]) for z in st.session_state.zones]
    df   = pd.DataFrame(rows)

    def _style_status(val: str) -> str:
        if "On Target" in val:
            return "color:green;font-weight:600"
        return "color:darkorange;font-weight:600"

    def _style_grade(row):
        """Highlight estimated grade in orange when it exceeds the target."""
        styles = [""] * len(row)
        cols   = list(row.index)
        above  = row.get("Est. Grade Level", 0) > row.get("Target Grade", 99)
        if above and "Est. Grade Level" in cols:
            styles[cols.index("Est. Grade Level")] = "color:darkorange;font-weight:600"
        return styles

    try:
        # pandas ≥ 2.1
        styled_df = (
            df.style
            .map(_style_status, subset=["Status"])
            .apply(_style_grade, axis=1)
        )
    except AttributeError:
        # pandas < 2.1 uses applymap
        styled_df = (
            df.style
            .applymap(_style_status, subset=["Status"])
            .apply(_style_grade, axis=1)
        )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

elif not st.session_state.pdf_text:
    # Friendly placeholder before any content exists
    st.info(
        "Upload a PDF and tag at least one zone to see the analysis here.",
        icon="👆",
    )
