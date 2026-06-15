# -*- coding: utf-8 -*-
"""
Отвлекатель для глаз.

Каждый час глушит весь экран тёмно-зелёной плашкой и заставляет
отдохнуть глазами. На плашке идёт обратный отсчёт: перерыв засчитывается,
только если её не скипали хотя бы REST_SECONDS (по умолчанию 2 минуты).

Скип — ДВОЙНОЙ пробел (одиночный не закрывает, чтобы не смахнуть случайно).
Если перерыв скипнули, а за компом продолжается активность (ввод с клавы
или движения мышью), плашка возвращается настойчивее каждые NAG_MIN минут.
Если человек отошёл (нет активности >= AWAY_SECONDS) — считаем, что глаза
и так отдыхают, и не долбим.

Запуск:
    python eye_break.py

Интервал основного цикла можно задать первым аргументом (в минутах):
    python eye_break.py 30
"""

import sys
import ctypes
import tkinter as tk

# --- Настройки ---------------------------------------------------------------
INTERVAL_MIN = 60          # как часто показывать перерыв в спокойном режиме (мин)
NAG_MIN = 10               # как часто долбить, если перерыв скипнули (мин)
REST_SECONDS = 120         # длина обратного отсчёта = чтобы перерыв засчитался (сек)
AWAY_SECONDS = 60          # тишина дольше этого = "человек отошёл", долбёжку не шлём (сек)

BG_COLOR = "#0b3d2e"       # тёмно-зелёный фон обычной плашки
BG_COLOR_NAG = "#42201f"   # приглушённо-бордовый фон настойчивой плашки
FG_COLOR = "#e8f5e9"       # цвет основного текста
HINT_COLOR = "#7fbf9a"     # цвет подсказки на зелёной плашке
HINT_COLOR_NAG = "#c79a9a" # цвет подсказки на красной плашке
# -----------------------------------------------------------------------------


# --- Системный idle-таймер (активность клавы/мыши) ---------------------------
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """Сколько секунд не было ввода с клавиатуры или мыши."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0.0, millis / 1000.0)
    except (AttributeError, OSError):
        return 0.0


class EyeBreakApp:
    def __init__(self, root: tk.Tk, interval_min: int):
        self.root = root
        self.interval_ms = int(interval_min * 60 * 1000)
        self.nag_ms = int(NAG_MIN * 60 * 1000)

        # Прячем главное окно — оно нужно только как держатель таймеров.
        self.root.withdraw()

        self.overlay = None          # текущая плашка (или None)
        self.remaining = 0           # остаток отсчёта, сек
        self.tick_job = None         # id задачи отсчёта
        self.space_armed = False     # ждём второй пробел для скипа

        # Запускаем цикл: первая плашка покажется через INTERVAL_MIN.
        self.root.after(self.interval_ms, self.show_break)

    # --- Показ плашки --------------------------------------------------------
    def show_break(self, insistent: bool = False):
        # Если плашка уже на экране — ничего не делаем.
        if self.overlay is not None:
            return

        bg = BG_COLOR_NAG if insistent else BG_COLOR
        hint_fg = HINT_COLOR_NAG if insistent else HINT_COLOR
        title = "Серьёзно — сделай перерыв" if insistent else "Ты час за ПК"
        sub = "Глаза не казённые, посмотри вдаль" if insistent else "Сделай перерыв для глаз"

        ov = tk.Toplevel(self.root)
        self.overlay = ov
        ov.configure(bg=bg)
        ov.overrideredirect(True)            # без рамки и заголовка
        ov.attributes("-topmost", True)      # поверх всех окон

        sw = ov.winfo_screenwidth()
        sh = ov.winfo_screenheight()
        ov.geometry(f"{sw}x{sh}+0+0")
        try:
            ov.attributes("-fullscreen", True)
        except tk.TclError:
            pass

        # Перехватываем фокус и клавиатуру, чтобы пробел ловился гарантированно.
        ov.focus_force()
        ov.grab_set()

        frame = tk.Frame(ov, bg=bg)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame, text=title, bg=bg, fg=FG_COLOR,
            font=("Segoe UI", 60, "bold"),
        ).pack(pady=(0, 10))

        tk.Label(
            frame, text=sub, bg=bg, fg=FG_COLOR,
            font=("Segoe UI", 36),
        ).pack(pady=(0, 40))

        # Обратный отсчёт отдыха.
        self.remaining = REST_SECONDS
        self.timer_label = tk.Label(
            frame, text=self._fmt(self.remaining), bg=bg, fg=FG_COLOR,
            font=("Consolas", 80, "bold"),
        )
        self.timer_label.pack(pady=(0, 40))

        tk.Label(
            frame, text="Чтобы пропустить — нажми ПРОБЕЛ дважды",
            bg=bg, fg=hint_fg, font=("Segoe UI", 20),
        ).pack()

        # Скип — двойной пробел.
        self.space_armed = False
        ov.bind("<space>", self._on_space)

        # Поехал отсчёт.
        self.tick_job = ov.after(1000, self._tick)

    # --- Обратный отсчёт -----------------------------------------------------
    def _tick(self):
        if self.overlay is None:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            # Отдых отстоял до конца — перерыв засчитан.
            self._close_overlay()
            self._schedule_normal()
            return
        self.timer_label.config(text=self._fmt(self.remaining))
        self.tick_job = self.overlay.after(1000, self._tick)

    @staticmethod
    def _fmt(sec: int) -> str:
        return f"{sec // 60}:{sec % 60:02d}"

    # --- Скип по двойному пробелу --------------------------------------------
    def _on_space(self, event=None):
        if self.overlay is None:
            return
        if self.space_armed:
            self._skip_break()
        else:
            self.space_armed = True
            self.overlay.after(600, self._disarm_space)

    def _disarm_space(self):
        self.space_armed = False

    def _skip_break(self):
        # Перерыв НЕ засчитан. Прячем и планируем настойчивую проверку.
        self._close_overlay()
        self.root.after(self.nag_ms, self._nag_check)

    # --- Настойчивая проверка после скипа ------------------------------------
    def _nag_check(self):
        if self.overlay is not None:
            return  # плашка уже висит — ничего не надо
        if idle_seconds() >= AWAY_SECONDS:
            # Человек отошёл — глаза отдыхают, возвращаемся в спокойный режим.
            self._schedule_normal()
        else:
            # За компом продолжается суета — долбим настойчивее.
            self.show_break(insistent=True)

    # --- Вспомогательное -----------------------------------------------------
    def _close_overlay(self):
        if self.tick_job is not None and self.overlay is not None:
            try:
                self.overlay.after_cancel(self.tick_job)
            except tk.TclError:
                pass
        self.tick_job = None
        if self.overlay is not None:
            self.overlay.grab_release()
            self.overlay.destroy()
            self.overlay = None

    def _schedule_normal(self):
        self.root.after(self.interval_ms, self.show_break)


def enable_dpi_awareness():
    """Делает процесс DPI-aware, чтобы Windows не растягивал окно
    (иначе шрифт мылится и идёт 'лесенкой' при масштабировании != 100%)."""
    try:
        # Per-Monitor v2 — самый чёткий вариант (Windows 10+).
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()        # System DPI
    except (AttributeError, OSError):
        pass


def main():
    enable_dpi_awareness()
    interval = INTERVAL_MIN
    if len(sys.argv) > 1:
        try:
            interval = float(sys.argv[1])
        except ValueError:
            print(f"Не понял интервал '{sys.argv[1]}', беру {INTERVAL_MIN} мин.")

    root = tk.Tk()
    EyeBreakApp(root, interval)
    root.mainloop()


if __name__ == "__main__":
    main()
