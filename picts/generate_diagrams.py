#!/usr/bin/env python3
"""Generate project architecture diagrams as PNG + SVG files.

Usage:
    python picts/generate_diagrams.py

Output:
    picts/request_flow.png       — Request Processing Pipeline
    picts/request_flow.svg       — (same, vector)
    picts/rag_pipeline.png       — Multi-Modal RAG Pipeline
    picts/rag_pipeline.svg       — (same, vector)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Color palette (matches web UI)
# ---------------------------------------------------------------------------
C = {
    "purple":   "#667eea",
    "purple2":  "#764ba2",
    "green":    "#10b981",
    "amber":    "#f59e0b",
    "blue":     "#3b82f6",
    "indigo":   "#8b5cf6",
    "slate":    "#475569",
    "dark":     "#1e293b",
    "white":    "#ffffff",
    "gray":     "#f1f5f9",
    "border":   "#e2e8f0",
    "arrow":    "#64748b",
    "red":      "#ef4444",
    "light_green": "#d1fae5",
    "light_blue":  "#e0e7ff",
    "light_amber": "#fef3c7",
    "light_indigo":"#f3e8ff",
    "text":     "#1e293b",
    "text2":    "#475569",
    "text3":    "#94a3b8",
}

# ---------------------------------------------------------------------------
# Helper: draw a rounded box with text
# ---------------------------------------------------------------------------
def box(ax, x, y, w, h, text, color, text_color="white", fontsize=11, sub=None, sub_color=None):
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.3",
        facecolor=color, edgecolor="none", zorder=2
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2 + (2 if sub else 0), text,
            ha="center", va="center", fontsize=fontsize, fontweight="bold",
            color=text_color, zorder=3)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 8, sub,
                ha="center", va="center", fontsize=8,
                color=sub_color or text_color, alpha=0.85, zorder=3)


def sub_box(ax, x, y, w, h, text, color, text_color):
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.2",
        facecolor=color, edgecolor=text_color, linewidth=1, zorder=2
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=9, fontweight="bold",
            color=text_color, zorder=3)


def label_box(ax, x, y, w, h, text, color, text_color):
    rect = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.2",
        facecolor=color, edgecolor=text_color, linewidth=0.8, zorder=2
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=9, fontweight="bold",
            color=text_color, zorder=3)


def arrow(ax, x1, y1, x2, y2, color=C["arrow"], lw=1.5):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw))


def dashed_arrow(ax, x1, y1, x2, y2, color=C["arrow"]):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=1, linestyle="dashed"))


# ===========================================================================
# Diagram 1: Request Processing Pipeline
# ===========================================================================
def draw_request_flow():
    fig, ax = plt.subplots(1, 1, figsize=(14, 18))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 18)
    ax.axis("off")
    ax.set_facecolor("#f8fafc")

    # Title
    ax.text(7, 17.3, "Request Processing Pipeline", ha="center", fontsize=20,
            fontweight="bold", color=C["text"])

    # ---- 1. User Question ----
    box(ax, 5, 16, 4, 0.7, "User Question", C["purple"])
    arrow(ax, 7, 16, 7, 15)

    # ---- 2. Cache Check ----
    box(ax, 4.5, 14.2, 5, 0.85, "Cache Check", C["green"], sub="exact hash + token similarity")
    # Cache HIT
    arrow(ax, 9.5, 14.6, 11.5, 14.6, color=C["green"])
    arrow(ax, 11.5, 14.6, 11.5, 16.4, color=C["green"])
    label_box(ax, 10, 15.7, 3, 0.6, "Return (0 LLM)", C["light_green"], "#059669")
    # Cache MISS
    arrow(ax, 7, 14.2, 7, 13)

    # ---- 3. Rule Router ----
    box(ax, 4.5, 12.2, 5, 0.85, "Rule Router", C["amber"], sub="Weather / News / Stock keywords")
    # Rule matched → web
    arrow(ax, 9.5, 12.6, 12, 12.6, color=C["amber"])
    arrow(ax, 12, 12.6, 12, 9.7, color=C["amber"])
    # No match
    arrow(ax, 7, 12.2, 7, 11)

    # ---- 4. LLM Router ----
    box(ax, 4, 10.2, 6, 0.85, "LLM Router", C["slate"], sub="classify: lecture / web / hybrid / unknown")

    # ---- 5. Three branches ----
    # lecture path
    arrow(ax, 5, 10.2, 3.5, 9.2)
    label_box(ax, 2.5, 8.7, 2, 0.55, "lecture", C["light_blue"], "#4f46e5")
    box(ax, 1.5, 7.6, 4, 0.85, "RAG Retrieval", C["light_blue"], "#4f46e5", sub="ChromaDB + BM25", sub_color="#6366f1")
    arrow(ax, 3.5, 7.6, 3.5, 6.8)
    box(ax, 1, 5.6, 5, 1.2, "Similarity Gate", C["indigo"],
        sub="≥0.82→skip Guard | 0.45~0.82→Guard | ≤0.45→skip", sub_color="#ffffffcc")
    # Guard branch
    dashed_arrow(ax, 3.5, 5.6, 1.5, 4.6)
    label_box(ax, 0.2, 4.2, 2.6, 0.55, "Guard LLM", C["light_indigo"], "#7c3aed")
    arrow(ax, 3.5, 5.6, 3.5, 4.5)

    # web path
    arrow(ax, 7, 10.2, 7, 9.2)
    label_box(ax, 6, 9, 2, 0.55, "web", C["light_amber"], "#d97706")
    box(ax, 5.5, 7.8, 3, 0.85, "Tavily Search", C["light_amber"], "#d97706", sub="1h cache", sub_color="#b45309")
    arrow(ax, 7, 7.8, 7, 5.5)

    # hybrid path
    arrow(ax, 9, 10.2, 10.5, 9.2)
    label_box(ax, 9.5, 8.7, 2, 0.55, "hybrid", C["light_green"], "#059669")
    box(ax, 8.5, 7.6, 4, 0.85, "RAG + Search", C["light_green"], "#059669", sub="both pipelines", sub_color="#047857")
    arrow(ax, 10.5, 7.6, 7, 5.5)

    # ---- Merge into Analyst ----
    box(ax, 4, 3.8, 6, 1.1, "Analyst", C["blue"], sub="synthesize → Chinese Markdown", sub_color="#ffffffd9")
    arrow(ax, 3.5, 4.5, 3.5, 4.9)
    arrow(ax, 3.5, 4.9, 5, 4.9)
    arrow(ax, 10.5, 5.5, 8, 5.5)

    # ---- Answer ----
    arrow(ax, 7, 3.8, 7, 2.8)
    box(ax, 5, 2, 4, 0.7, "Answer", C["dark"])

    # ---- SSE label ----
    label_box(ax, 10.5, 2.5, 3, 1, "SSE Progress\n4 steps → frontend", C["gray"], C["text2"])
    dashed_arrow(ax, 10.5, 3, 9, 3.5)

    # ---- Optimizations legend ----
    legend_y = 1.2
    ax.add_patch(FancyBboxPatch((0.3, 0.1), 13.4, 1.1, boxstyle="round,pad=0.2",
                                facecolor="white", edgecolor=C["border"]))
    ax.text(0.6, 1, "Optimizations: ", fontsize=9, fontweight="bold", color=C["text"], va="center")

    items = [
        ("●", C["green"], "3-tier cache"),
        ("●", C["indigo"], "similarity gate (saves ~2s)"),
        ("●", C["amber"], "rule router (zero LLM)"),
        ("●", C["slate"], "2-3 LLM calls (vs 5 hierarchical)"),
    ]
    for i, (dot, clr, label) in enumerate(items):
        ax.text(0.6 + i * 3.2, 0.55, dot, fontsize=10, color=clr, va="center")
        ax.text(0.9 + i * 3.2, 0.55, label, fontsize=8, color=C["text2"], va="center")

    fig.tight_layout(pad=0.5)
    return fig


# ===========================================================================
# Diagram 2: Multi-Modal RAG Pipeline
# ===========================================================================
def draw_rag_pipeline():
    fig, ax = plt.subplots(1, 1, figsize=(14, 14))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 14)
    ax.axis("off")
    ax.set_facecolor("#f8fafc")

    # Title
    ax.text(7, 13.5, "Multi-Modal RAG Pipeline", ha="center", fontsize=20,
            fontweight="bold", color=C["text"])

    # ---- 1. Input files ----
    box(ax, 3.5, 12, 7, 0.7, "knowledge/*.pdf  /  *.pptx  /  *.docx", C["purple"])

    arrow(ax, 7, 12, 7, 11.3)

    # ---- 2. DocumentProcessor ----
    box(ax, 4, 10.8, 6, 0.6, "DocumentProcessor", C["slate"], fontsize=12)

    # Three extraction branches
    arrow(ax, 5, 10.8, 2.5, 9.8)
    arrow(ax, 7, 10.8, 7, 9.8)
    arrow(ax, 9, 10.8, 11.5, 9.8)

    # Text
    box(ax, 0.5, 8.5, 4, 1.4, "extract_text()", C["blue"], sub="semantic chunking\nparagraph/heading boundaries", sub_color="#ffffffb3")
    # Images
    box(ax, 5, 8.5, 4, 1.4, "extract_images()", C["indigo"], sub="PIL Image → BLIP caption\n+ easyocr text extraction", sub_color="#ffffffb3")
    # Tables
    box(ax, 9.5, 8.5, 4, 1.4, "extract_tables()", C["green"], sub="convert to Markdown\n| A | B | → table string", sub_color="#ffffffb3")

    # Merge
    arrow(ax, 2.5, 8.5, 2.5, 7.5)
    arrow(ax, 2.5, 7.5, 7, 7.5)
    arrow(ax, 7, 9.9, 7, 7.5)
    arrow(ax, 11.5, 8.5, 11.5, 7.5)
    arrow(ax, 11.5, 7.5, 7, 7.5)

    # ---- 3. ChromaDB ----
    box(ax, 3, 6.2, 8, 1.3, "ChromaDB  —  Local Persistence", C["dark"],
        sub="type: text | image | table | web    ·    384-dim  (paraphrase-multilingual-MiniLM-L12-v2)",
        sub_color="#ffffff99")

    arrow(ax, 7, 6.2, 7, 5.3)

    # ---- 4. Retrieval stages ----
    stages = [
        ("Cosine ANN Search", "#475569"),
        ("BM25 Hybrid Re-rank  (70/30)", "#475569"),
        ("Top-K Results", "#475569"),
    ]
    y = 4.8
    for text, color in stages:
        box(ax, 4, y, 6, 0.55, text, C["gray"], C["text2"], fontsize=11)
        arrow(ax, 7, y, 7, y - 0.55)
        y -= 0.55

    # ---- 5. Similarity Gate ----
    box(ax, 3, 2.4, 8, 0.85, "Similarity Gate", C["indigo"],
        sub="≥0.82 → skip Guard  |  0.45~0.82 → Guard LLM  |  ≤0.45 → skip",
        sub_color="#ffffffcc")

    arrow(ax, 7, 2.4, 7, 1.5)

    # ---- Output ----
    box(ax, 4, 0.8, 6, 0.7, "Context → Analyst LLM → Answer", C["purple"])

    # ---- Legend ----
    ax.add_patch(FancyBboxPatch((0.3, 0.1), 13.4, 0.6, boxstyle="round,pad=0.2",
                                facecolor="white", edgecolor=C["border"]))
    items = [
        ("●", C["blue"], "CrossEncoder removed (saves 1-2s)"),
        ("●", C["indigo"], "BLIP caption → text vector (no multi-modal embedding)"),
        ("●", C["green"], "incremental indexing (SHA256 hash)"),
    ]
    for i, (dot, clr, label) in enumerate(items):
        ax.text(0.6 + i * 4.3, 0.4, dot, fontsize=10, color=clr, va="center")
        ax.text(0.9 + i * 4.3, 0.4, label, fontsize=8, color=C["text2"], va="center")

    fig.tight_layout(pad=0.5)
    return fig


# ===========================================================================
# Main
# ===========================================================================
if __name__ == "__main__":
    diagrams = [
        ("request_flow", draw_request_flow),
        ("rag_pipeline", draw_rag_pipeline),
    ]

    for name, draw_fn in diagrams:
        print(f"Generating {name}...")
        fig = draw_fn()

        # Save PNG
        png_path = OUTPUT_DIR / f"{name}.png"
        fig.savefig(str(png_path), dpi=150, bbox_inches="tight",
                    facecolor="#f8fafc", edgecolor="none")
        print(f"  → {png_path}")

        # Save SVG
        svg_path = OUTPUT_DIR / f"{name}.svg"
        fig.savefig(str(svg_path), format="svg", bbox_inches="tight",
                    facecolor="#f8fafc", edgecolor="none")
        print(f"  → {svg_path}")

        plt.close(fig)

    print("\nDone. Output files in picts/")
