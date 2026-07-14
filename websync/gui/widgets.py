"""공통 위젯 및 테마 색상 상수"""
import tkinter as tk
from tkinter import ttk

# 라이트 테마 색상 정의 (Clean Light Theme)
BG_COLOR      = "#f8f9fa" # 연한 회색 배경
FG_COLOR      = "#212529" # 어두운 텍스트
ACCENT_COLOR  = "#0d6efd" # 파란색 포인트
SECONDARY_BG  = "#e9ecef" # 비활성 탭 및 서브 프레임 배경
TEXT_BG       = "#ffffff" # 입력 필드, 리스트 박스 배경
GREEN_COLOR   = "#198754" # 상태 양호 초록색
RED_COLOR     = "#dc3545" # 에러 빨간색
YELLOW_COLOR  = "#fd7e14" # 미확인/대기 주황색
HINT_COLOR    = "#6c757d" # 보조 힌트 텍스트


def center_window(window: tk.Misc, width: int | None = None, height: int | None = None) -> None:
    window.update_idletasks()
    w = width or window.winfo_width()
    h = height or window.winfo_height()
    x = max(0, (window.winfo_screenwidth() - w) // 2)
    y = max(0, (window.winfo_screenheight() - h) // 2)
    if width and height:
        window.geometry(f"{width}x{height}+{x}+{y}")
    else:
        window.geometry(f"+{x}+{y}")


def setup_dialog(dialog: tk.Toplevel, root: tk.Misc, width: int, height: int, *, resizable: bool = True) -> None:
    dialog.transient(root)
    dialog.grab_set()
    dialog.resizable(resizable, resizable)
    dialog.minsize(min(width, 420), min(height, 240))
    center_window(dialog, width, height)


def bind_widget_mousewheel(widget: tk.Misc, handler) -> None:
    widget.bind("<MouseWheel>", handler, add="+")
    for child in widget.winfo_children():
        if child.winfo_class() in ("Treeview", "Text", "TCombobox", "TSpinbox"):
            continue
        bind_widget_mousewheel(child, handler)


def bind_text_mousewheel(text_widget: tk.Text) -> None:
    def _on_mousewheel(event):
        text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"
    text_widget.bind("<MouseWheel>", _on_mousewheel)


def create_scrolled_tree(
    parent,
    columns,
    show: str = "headings",
    height: int = 10,
    *,
    padx: int = 10,
    pady: int = 8,
    **tree_kwargs,
) -> ttk.Treeview:
    """스크롤바가 붙은 Treeview를 생성합니다."""
    wrapper = ttk.Frame(parent)
    wrapper.pack(fill="both", expand=True, padx=padx, pady=pady)
    wrapper.grid_rowconfigure(0, weight=1)
    wrapper.grid_columnconfigure(0, weight=1)

    tree = ttk.Treeview(wrapper, columns=columns, show=show, height=height, **tree_kwargs)
    vsb = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    return tree


def create_scrollable_frame(parent) -> ttk.Frame:
    """세로 스크롤이 가능한 내부 프레임을 생성합니다."""
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, highlightthickness=0, bg=BG_COLOR)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    def _on_frame_configure(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    scrollable_frame.bind("<Configure>", _on_frame_configure)

    window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    def _on_canvas_configure(event):
        canvas.itemconfig(window_id, width=event.width)

    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    bind_widget_mousewheel(scrollable_frame, _on_mousewheel)
    canvas.bind("<MouseWheel>", _on_mousewheel)

    return scrollable_frame
