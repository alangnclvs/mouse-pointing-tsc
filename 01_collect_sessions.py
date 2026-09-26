"""Pointing-task collector for the Time Series Mining final assignment.

Each trial: click the home circle at the screen center, then click a target
that appears at a fixed distance in a balanced random direction. The target
diameter (small / medium / large) is the class label. Cursor positions are
recorded only inside this window, from target onset until the target is hit.

Usage:
    python 01_collect_sessions.py                 (asks for the session number)
    python 01_collect_sessions.py --session 1
    python 01_collect_sessions.py --session 0     (quick test, 3 targets per size)
"""

import argparse
import csv
import ctypes
import json
import math
import platform
import random
import statistics
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

SCRIPT_VERSION = "1.1"
SIZES_CSS_PX = {"small": 12, "medium": 24, "large": 44}
SIZE_NAMES = {"small": "pequeno", "medium": "médio", "large": "grande"}
DISTANCE_CSS_PX = 300
HOME_DIAMETER_CSS_PX = 40
EDGE_MARGIN_CSS_PX = 20

BACKGROUND = "#16181d"
SURFACE = "#1f2229"
BORDER = "#2b2f38"
TRACK = "#262a33"
TEXT = "#e6e7ea"
TEXT_SECONDARY = "#9aa0aa"
TEXT_MUTED = "#626873"
ACCENT = "#e06c75"
ACCENT_HOVER = "#ea8a91"
HOME_OUTLINE = "#5b606b"
HOME_OUTLINE_HOVER = "#c9ccd2"
HOME_FILL = "#1c1f25"
FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"


def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def display_scale(root):
    if sys.platform == "win32":
        try:
            return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0
        except Exception:
            pass
    return root.winfo_fpixels("1i") / 96.0


def mouse_settings():
    if sys.platform != "win32":
        return {}
    user32 = ctypes.windll.user32
    speed = ctypes.c_int()
    params = (ctypes.c_int * 3)()
    user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0)
    user32.SystemParametersInfoW(0x0003, 0, params, 0)
    return {"pointer_speed": speed.value, "enhance_pointer_precision": bool(params[2])}


def build_trial_plan(trials_per_size, seed):
    rng = random.Random(seed)
    step = 360 / trials_per_size
    trials = []
    for label in SIZES_CSS_PX:
        offset = rng.uniform(0, step)
        for k in range(trials_per_size):
            trials.append({"size_label": label, "angle_deg": round((offset + k * step) % 360, 2)})
    rng.shuffle(trials)
    return trials


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def blend(color_a, color_b, t):
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def format_seconds(value):
    return f"{value:.2f}".replace(".", ",") + " s"


def format_duration(seconds):
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


class PointingSession:
    def __init__(self, root, session, trials_per_size, out_dir):
        self.root = root
        self.session = session
        self.kind = "Teste" if session == 0 else f"Sessão {session}"
        self.out_dir = out_dir
        self.seed = 1000 + session
        self.plan = build_trial_plan(trials_per_size, self.seed)
        self.scale = display_scale(root)
        self.width = root.winfo_screenwidth()
        self.height = root.winfo_screenheight()
        self.cx = self.width / 2
        self.cy = self.height / 2
        max_radius = max(SIZES_CSS_PX.values()) * self.scale / 2
        limit = min(self.cx, self.cy) - max_radius - EDGE_MARGIN_CSS_PX * self.scale
        self.distance = min(DISTANCE_CSS_PX * self.scale, limit)
        self.home_radius = HOME_DIAMETER_CSS_PX * self.scale / 2
        self.index = 0
        self.state = "intro"
        self.samples = []
        self.misses = []
        self.movement_times = {label: [] for label in SIZES_CSS_PX}
        self.errors = {label: 0 for label in SIZES_CSS_PX}
        self.session_t0 = None
        self.elapsed = 0.0
        self.pulse_job = None
        self.button_bbox = None
        self.button_item = None
        self.button_hover = False
        self.home_item = None
        self.home_hover = False

        self.canvas = tk.Canvas(root, bg=BACKGROUND, highlightthickness=0, cursor="arrow")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_click)
        root.bind("<Escape>", self.on_escape)

        self.metadata = {
            "session": session,
            "seed": self.seed,
            "script_version": SCRIPT_VERSION,
            "started_at": now_iso(),
            "finished_at": None,
            "aborted": None,
            "trials_planned": len(self.plan),
            "trials_completed": 0,
            "screen_px": [self.width, self.height],
            "display_scale": self.scale,
            "distance_css_px": round(self.distance / self.scale, 2),
            "distance_px": round(self.distance, 2),
            "sizes_css_px": SIZES_CSS_PX,
            "home_diameter_css_px": HOME_DIAMETER_CSS_PX,
            "mouse": mouse_settings(),
            "python": platform.python_version(),
            "os": platform.platform(),
        }
        self.write_metadata()
        self.show_intro()

    def write_metadata(self):
        with open(self.out_dir / "session.json", "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

    def pointer_in_canvas(self):
        x = self.root.winfo_pointerx() - self.canvas.winfo_rootx()
        y = self.root.winfo_pointery() - self.canvas.winfo_rooty()
        return x, y

    def inside_home(self, x, y):
        return math.hypot(x - self.cx, y - self.cy) <= self.home_radius

    def inside_button(self, x, y):
        if self.button_bbox is None:
            return False
        x1, y1, x2, y2 = self.button_bbox
        return x1 <= x <= x2 and y1 <= y <= y2

    def rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                  x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def card(self, width, height, tag):
        s = self.scale
        x1, y1 = self.cx - width * s / 2, self.cy - height * s / 2
        x2, y2 = x1 + width * s, y1 + height * s
        self.rounded_rect(x1, y1, x2, y2, 34 * s, fill=SURFACE, outline=BORDER, tags=tag)
        return x1, y1, x2, y2

    def draw_progress(self):
        s = self.scale
        total = len(self.plan)
        self.canvas.create_rectangle(0, 0, self.width, 3 * s, fill=TRACK, outline="", tags="scene")
        done = self.width * self.index / total
        if done > 0:
            self.canvas.create_rectangle(0, 0, done, 3 * s, fill=ACCENT, outline="", tags="scene")
        self.canvas.create_text(24 * s, 18 * s, anchor="nw", text=f"{self.kind}  ·  Esc encerra",
                                fill=TEXT_MUTED, font=(FONT, 10), tags="scene")
        self.canvas.create_text(self.width - 24 * s, 18 * s, anchor="ne", text=f"{self.index + 1} / {total}",
                                fill=TEXT_SECONDARY, font=(FONT, 11), tags="scene")

    def show_intro(self):
        s = self.scale
        self.canvas.delete("all")
        x1, y1, x2, y2 = self.card(520, 380, "intro")
        pad = 44 * s
        self.canvas.create_text(x1 + pad, y1 + pad, anchor="nw", text=self.kind,
                                fill=TEXT, font=(FONT_SEMIBOLD, 22), tags="intro")
        self.canvas.create_text(x1 + pad, y1 + pad + 44 * s, anchor="nw",
                                text=f"Tarefa de apontamento  ·  {len(self.plan)} alvos",
                                fill=TEXT_SECONDARY, font=(FONT, 11), tags="intro")
        steps = [
            "Clique no círculo do centro",
            "Um alvo aparece em algum ponto da tela",
            "Clique nele o mais rápido que conseguir, sem errar",
        ]
        r = 13 * s
        for i, text in enumerate(steps):
            y = y1 + 140 * s + i * 40 * s
            cx = x1 + pad + r
            self.canvas.create_oval(cx - r, y - r, cx + r, y + r, outline=ACCENT, width=1.5, tags="intro")
            self.canvas.create_text(cx, y, text=str(i + 1), fill=ACCENT, font=(FONT_SEMIBOLD, 10), tags="intro")
            self.canvas.create_text(cx + r + 16 * s, y, anchor="w", text=text,
                                    fill=TEXT, font=(FONT, 12), tags="intro")
        bw, bh = 168 * s, 46 * s
        bx1, by1 = self.cx - bw / 2, y1 + 262 * s
        self.button_bbox = (bx1, by1, bx1 + bw, by1 + bh)
        self.button_item = self.rounded_rect(*self.button_bbox, 22 * s, fill=ACCENT, outline="", tags="intro")
        self.canvas.create_text(self.cx, by1 + bh / 2, text="Começar", fill=BACKGROUND,
                                font=(FONT_SEMIBOLD, 12), tags="intro")
        self.canvas.create_text(self.cx, y2 - 30 * s, text="Esc encerra a qualquer momento",
                                fill=TEXT_MUTED, font=(FONT, 10), tags="intro")

    def show_home(self):
        self.state = "home"
        self.canvas.delete("intro", "scene")
        self.canvas.config(cursor="arrow")
        x, y = self.pointer_in_canvas()
        self.home_hover = self.inside_home(x, y)
        r = self.home_radius
        self.home_item = self.canvas.create_oval(
            self.cx - r, self.cy - r, self.cx + r, self.cy + r, fill=HOME_FILL, width=2,
            outline=HOME_OUTLINE_HOVER if self.home_hover else HOME_OUTLINE, tags="scene")
        d = 2.5 * self.scale
        self.canvas.create_oval(self.cx - d, self.cy - d, self.cx + d, self.cy + d,
                                fill=HOME_OUTLINE, outline="", tags="scene")
        self.draw_progress()

    def start_trial(self):
        self.cancel_pulse()
        if self.session_t0 is None:
            self.session_t0 = time.perf_counter()
        trial = self.plan[self.index]
        radius = SIZES_CSS_PX[trial["size_label"]] * self.scale / 2
        angle = math.radians(trial["angle_deg"])
        tx = self.cx + self.distance * math.cos(angle)
        ty = self.cy - self.distance * math.sin(angle)
        self.target = (tx, ty, radius)
        self.canvas.delete("all")
        self.canvas.create_oval(tx - radius, ty - radius, tx + radius, ty + radius,
                                fill=ACCENT, outline="", tags="scene")
        self.draw_progress()
        self.canvas.update_idletasks()
        self.t0 = time.perf_counter()
        self.onset_at = now_iso()
        x, y = self.pointer_in_canvas()
        self.start_xy = (x, y)
        self.samples = [(0.0, x, y)]
        self.misses = []
        self.state = "trial"

    def pulse(self, x, y, radius):
        self.cancel_pulse()
        frames = 8
        grow = 20 * self.scale

        def step(i):
            self.canvas.delete("pulse")
            if i > frames:
                self.pulse_job = None
                return
            t = i / frames
            color = blend(ACCENT, BACKGROUND, t)
            disc = radius * (1 - 0.35 * t)
            ring = radius + grow * t
            self.canvas.create_oval(x - disc, y - disc, x + disc, y + disc, fill=color, outline="", tags="pulse")
            self.canvas.create_oval(x - ring, y - ring, x + ring, y + ring, outline=color, width=2, tags="pulse")
            self.pulse_job = self.root.after(20, step, i + 1)

        step(0)

    def cancel_pulse(self):
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None
        self.canvas.delete("pulse")

    def on_motion(self, event):
        if self.state == "trial":
            self.samples.append((time.perf_counter() - self.t0, event.x, event.y))
        elif self.state == "home":
            inside = self.inside_home(event.x, event.y)
            if inside != self.home_hover:
                self.home_hover = inside
                self.canvas.itemconfig(self.home_item, outline=HOME_OUTLINE_HOVER if inside else HOME_OUTLINE)
        elif self.state == "intro":
            inside = self.inside_button(event.x, event.y)
            if inside != self.button_hover:
                self.button_hover = inside
                self.canvas.itemconfig(self.button_item, fill=ACCENT_HOVER if inside else ACCENT)
                self.canvas.config(cursor="hand2" if inside else "arrow")

    def on_click(self, event):
        if self.state == "intro":
            if self.inside_button(event.x, event.y):
                self.show_home()
        elif self.state == "home":
            if self.inside_home(event.x, event.y):
                self.start_trial()
        elif self.state == "trial":
            t = time.perf_counter() - self.t0
            tx, ty, radius = self.target
            if math.hypot(event.x - tx, event.y - ty) <= radius:
                self.samples.append((t, event.x, event.y))
                self.save_trial(t)
                self.pulse(tx, ty, radius)
                self.index += 1
                if self.index == len(self.plan):
                    self.finish(aborted=False)
                else:
                    self.show_home()
            else:
                self.misses.append((t, event.x, event.y))
        elif self.state == "summary":
            self.root.destroy()

    def on_escape(self, _event):
        if self.state == "summary":
            self.root.destroy()
        else:
            self.finish(aborted=True)

    def save_trial(self, movement_time):
        trial = self.plan[self.index]
        label = trial["size_label"]
        name = f"trial_{self.index + 1:03d}_{label}.csv"
        with open(self.out_dir / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["t", "x", "y"])
            for t, x, y in self.samples:
                writer.writerow([f"{t:.6f}", x, y])

        tx, ty, radius = self.target
        row = {
            "session": self.session,
            "trial": self.index + 1,
            "file": name,
            "size_label": label,
            "width_css_px": SIZES_CSS_PX[label],
            "width_px": round(2 * radius, 2),
            "distance_px": round(self.distance, 2),
            "angle_deg": trial["angle_deg"],
            "start_x": self.start_xy[0],
            "start_y": self.start_xy[1],
            "target_x": round(tx, 2),
            "target_y": round(ty, 2),
            "onset_at": self.onset_at,
            "movement_time_s": round(movement_time, 6),
            "n_misses": len(self.misses),
            "miss_times_s": ";".join(f"{t:.3f}" for t, _, _ in self.misses),
            "n_samples": len(self.samples),
        }
        trials_path = self.out_dir / "trials.csv"
        is_new = not trials_path.exists()
        with open(trials_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            if is_new:
                writer.writeheader()
            writer.writerow(row)

        self.movement_times[label].append(movement_time)
        self.errors[label] += len(self.misses)
        self.metadata["trials_completed"] = self.index + 1
        self.write_metadata()

    def finish(self, aborted):
        if self.state in ("done", "summary"):
            return
        self.state = "done"
        if self.session_t0 is not None:
            self.elapsed = time.perf_counter() - self.session_t0
        self.metadata["finished_at"] = now_iso()
        self.metadata["aborted"] = aborted
        self.write_metadata()
        print(f"{self.kind}: {self.metadata['trials_completed']}/{len(self.plan)} alvos -> {self.out_dir}")
        for label, times in self.movement_times.items():
            if times:
                print(f"  {SIZE_NAMES[label]:<8} tempo médio {statistics.mean(times):.3f} s  "
                      f"(n={len(times)}, erros={self.errors[label]})")
        if aborted:
            self.root.destroy()
            return
        self.show_summary()

    def show_summary(self):
        s = self.scale
        self.state = "summary"
        self.cancel_pulse()
        self.canvas.delete("all")
        self.canvas.config(cursor="arrow")
        x1, y1, x2, y2 = self.card(460, 340, "summary")
        pad = 40 * s
        title = "Teste concluído" if self.session == 0 else f"{self.kind} concluída"
        self.canvas.create_text(x1 + pad, y1 + pad, anchor="nw", text=title, fill=TEXT, font=(FONT_SEMIBOLD, 20))
        self.canvas.create_text(x1 + pad, y1 + pad + 40 * s, anchor="nw",
                                text=f"{self.metadata['trials_completed']} alvos em {format_duration(self.elapsed)}",
                                fill=TEXT_SECONDARY, font=(FONT, 11))
        col_time = x1 + pad + 150 * s
        header_y = y1 + 140 * s
        self.canvas.create_text(x1 + pad, header_y, anchor="w", text="alvo", fill=TEXT_MUTED, font=(FONT, 10))
        self.canvas.create_text(col_time, header_y, anchor="w", text="tempo médio", fill=TEXT_MUTED, font=(FONT, 10))
        self.canvas.create_text(x2 - pad, header_y, anchor="e", text="erros", fill=TEXT_MUTED, font=(FONT, 10))
        for i, label in enumerate(SIZES_CSS_PX):
            y = header_y + 38 * s + i * 38 * s
            self.canvas.create_line(x1 + pad, y - 19 * s, x2 - pad, y - 19 * s, fill=BORDER)
            times = self.movement_times[label]
            mean_time = format_seconds(statistics.mean(times)) if times else "-"
            n = self.errors[label]
            self.canvas.create_text(x1 + pad, y, anchor="w", text=SIZE_NAMES[label], fill=TEXT, font=(FONT, 12))
            self.canvas.create_text(col_time, y, anchor="w", text=mean_time, fill=TEXT, font=(FONT_SEMIBOLD, 12))
            self.canvas.create_text(x2 - pad, y, anchor="e", text=f"{n} erro" if n == 1 else f"{n} erros",
                                    fill=TEXT_SECONDARY, font=(FONT, 12))
        self.canvas.create_text(self.cx, y2 - 28 * s, text="clique para fechar", fill=TEXT_MUTED, font=(FONT, 10))


def main():
    parser = argparse.ArgumentParser(description="Pointing-task data collector")
    parser.add_argument("--session", type=int, help="session number (0 = test); asked interactively if omitted")
    parser.add_argument("--trials-per-size", type=int, help="default: 3 for session 0, 10 otherwise")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data" / "raw")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    while args.session is None:
        answer = input("Número da sessão (0 = teste): ").strip()
        if answer.isdigit():
            args.session = int(answer)
    if args.trials_per_size is None:
        args.trials_per_size = 3 if args.session == 0 else 10
    if args.session == 0:
        args.overwrite = True

    out_dir = args.out / f"session_{args.session:02d}"
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        sys.exit(f"{out_dir} já existe. Use outro número de sessão ou --overwrite.")
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        for f in out_dir.iterdir():
            f.unlink()

    enable_dpi_awareness()
    root = tk.Tk()
    root.title("Pointing task")
    root.attributes("-fullscreen", True)
    root.configure(bg=BACKGROUND)
    PointingSession(root, args.session, args.trials_per_size, out_dir)
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
