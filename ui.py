"""Identidade visual compartilhada pelas páginas do protótipo."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
LOGO_PATH = PROJECT_ROOT / "assets" / "logo_mac.png"


def apply_global_style() -> None:
    """Aplica o tema visual e exibe a logo quando o arquivo estiver disponível."""
    if LOGO_PATH.is_file():
        st.logo(str(LOGO_PATH), size="large")

    st.markdown(
        """
        <style>
        :root {
            --mac-navy: #0b1423;
            --mac-navy-soft: #17243a;
            --mac-blue: #075fc9;
            --mac-bg: #f4f6f8;
            --mac-surface: #ffffff;
            --mac-border: #d8dee8;
            --mac-text: #111827;
            --mac-muted: #64748b;
        }

        [data-testid="stAppViewContainer"] {
            background: var(--mac-bg);
        }

        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid var(--mac-border);
        }

        [data-testid="stMainBlockContainer"] {
            max-width: none;
            padding: 2rem 2rem 4rem;
        }

        h1, h2, h3, h4 {
            color: var(--mac-text);
            letter-spacing: -0.02em;
        }

        h1 {
            font-size: 1.65rem !important;
            font-weight: 750 !important;
            margin-bottom: 1rem !important;
        }

        h2, h3 {
            font-weight: 700 !important;
        }

        [data-testid="stSidebar"] {
            background: var(--mac-navy);
            border-right: 1px solid #172033;
        }

        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0.75rem;
        }

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] svg {
            color: #aeb8c7;
            fill: currentColor;
        }

        [data-testid="stSidebarNav"] a {
            border-radius: 0.5rem;
            margin: 0.2rem 0.65rem;
            min-height: 2.6rem;
            transition: background-color 120ms ease, color 120ms ease;
        }

        [data-testid="stSidebarNav"] a:hover {
            background: rgba(255, 255, 255, 0.06);
        }

        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: var(--mac-navy-soft);
        }

        [data-testid="stSidebarNav"] a[aria-current="page"] p,
        [data-testid="stSidebarNav"] a[aria-current="page"] span,
        [data-testid="stSidebarNav"] a[aria-current="page"] svg {
            color: #ffffff;
        }

        div[data-testid="stHorizontalBlock"]:has([data-testid="stSelectbox"]),
        div[data-testid="stHorizontalBlock"]:has([data-testid="stDateInput"]) {
            background: var(--mac-surface);
            border: 1px solid var(--mac-border);
            border-radius: 0.85rem;
            padding: 1rem;
            margin-bottom: 0.5rem;
        }

        [data-testid="stWidgetLabel"] p {
            color: var(--mac-muted);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.045em;
            text-transform: uppercase;
        }

        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        [data-testid="stDateInput"] [data-baseweb="input"] {
            background: #ffffff;
            border-color: var(--mac-border);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
        }

        [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"]) {
            min-height: 6.4rem;
            background: var(--mac-surface);
            border: 1px solid var(--mac-border);
            border-radius: 0.85rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
        }

        [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"])
        [data-testid="stMetric"] {
            min-height: 0;
            background: transparent;
            border: 0;
            border-radius: 0;
            padding: 0;
            box-shadow: none;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--mac-muted);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        [data-testid="stMetricValue"] {
            color: var(--mac-text);
            font-size: 1.55rem;
            font-weight: 750;
        }

        [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"])
        [data-testid="stCaptionContainer"] {
            color: var(--mac-muted);
        }

        [data-testid="stPlotlyChart"] {
            background: var(--mac-surface);
            border: 1px solid var(--mac-border);
            border-radius: 0.85rem;
            padding: 0.65rem;
            overflow: hidden;
        }

        [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
            background: var(--mac-blue);
        }

        [data-testid="stAlert"] {
            border-radius: 0.7rem;
        }

        hr {
            border-color: var(--mac-border) !important;
        }

        @media (max-width: 900px) {
            [data-testid="stMainBlockContainer"] {
                padding: 1.25rem 1rem 3rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
