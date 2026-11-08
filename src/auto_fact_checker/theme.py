"""Visual theme of the Gradio UI: a calm Soft theme (one indigo accent on slate neutrals) plus the app stylesheet.

Local: THEME is passed to `Blocks.launch(theme=...)` and CSS_PATH to `launch(css_paths=...)`; since Gradio 6 these
are launch() parameters, not Blocks() parameters (gradio/blocks.py `launch`, Gradio 6.30). The fonts are the system
sans and Gradio's bundled IBM Plex Mono (`LocalFont`, served from Gradio's own static files), so the page makes no
request to Google Fonts. Soft's tinted label pills are made transparent so ~100 settings widgets read as plain
labels; selected checkboxes keep the accent so choices stand out.
Global context: ui.launch() is the only caller; ui.css holds the classes that render_html.py emits (status pill,
tiles, claim cards, meters, diff) and the readability rules (prose width, table font, scrolling long lists).
Sources: theming guide https://www.gradio.app/guides/theming-guide ; custom CSS and elem_classes
https://www.gradio.app/guides/custom-CSS-and-JS ; system font stack as in the dataviz skill's reference palette
(`system-ui, -apple-system, "Segoe UI", sans-serif`).
"""

from pathlib import Path

import gradio as gr

CSS_PATH = Path(__file__).with_name("ui.css")  # read by Gradio at launch; edits apply on restart

THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,  # one accent: primary button, selected checkboxes, active tab, sliders
    neutral_hue=gr.themes.colors.slate,  # cool greys for surfaces, borders and secondary text
    font=("system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"),  # native UI font on every OS
    font_mono=(gr.themes.LocalFont("IBM Plex Mono"), "ui-monospace", "Consolas", "monospace"),  # code, run ids
).set(
    block_label_background_fill="transparent",  # Soft paints every label as an accent pill; plain text is calmer
    block_label_background_fill_dark="transparent",
    block_title_background_fill="transparent",
    block_title_background_fill_dark="transparent",
    block_label_text_color="*neutral_600",
    block_label_text_color_dark="*neutral_300",
    block_title_text_color="*neutral_600",
    block_title_text_color_dark="*neutral_300",
    block_label_padding="0",  # without the pill, the label aligns with the widget's left edge
    block_title_padding="0",
    block_radius="*radius_lg",
    block_border_width="1px",  # a hairline separates white cards from the light page without heavy shadows
    block_border_color="*neutral_200",
    block_border_color_dark="*neutral_700",
    button_large_radius="*radius_lg",
    button_cancel_text_color="#b91c1c",  # variant="stop" uses the cancel colours; Soft makes them plain secondary,
    button_cancel_text_color_dark="#fca5a5",  # red text keeps Stop recognisable without a large red block
)
