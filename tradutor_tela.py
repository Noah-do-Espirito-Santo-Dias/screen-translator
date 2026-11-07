import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from difflib import SequenceMatcher

import mss
import numpy as np
from rapidocr_onnxruntime import RapidOCR

import argostranslate.package
import argostranslate.translate


def carregar_modelo_argos(from_code="en", to_code="pt"):
    """Garante que o pacote de idioma EN->PT está baixado e instalado apenas se necessário."""
    # Verifica se o modelo já está instalado localmente
    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = next((l for l in installed_languages if l.code == from_code), None)
    to_lang = next((l for l in installed_languages if l.code == to_code), None)

    if from_lang and to_lang:
        translation = from_lang.get_translation(to_lang)
        if translation:
            return  # Modelo já instalado e pronto para uso

    # Baixa o modelo caso ainda não esteja instalado
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    package_to_install = next(
        filter(lambda x: x.from_code == from_code and x.to_code == to_code, available_packages), None
    )
    if package_to_install:
        argostranslate.package.install_from_path(package_to_install.download())


try:
    import keyboard  # atalhos globais (opcional)
except Exception:
    keyboard = None

# ----------------------------- CONFIGURAÇÕES -----------------------------
INTERVALO = 0.05          # segundos entre capturas (maior = menos CPU)
FRAMES_ESTAVEIS = 2       # quantos frames iguais antes de rodar o OCR
SENSIBILIDADE = 0.005     # fração mínima de pixels mudados para contar como mudança
MIN_CONFIANCA = 0.55      # descarta trechos de OCR com confiança baixa
COR_FUNDO = "#000000"
COR_TEXTO = "#FFFFFF"
FONTE = "Segoe UI"
TAM_MAX, TAM_MIN = 60, 20  # tamanho da fonte (em pixels) - ajusta sozinho
OPACIDADE = 0.65
TECLA_PAUSA, TECLA_AREA, TECLA_SAIR = "f8", "f9", "f10"
ARQUIVO_REGIAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regiao.json")
# --------------------------------------------------------------------------

if sys.platform != "win32":
    sys.exit("Este script foi feito para Windows.")

user32 = ctypes.windll.user32
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


def hwnd_de(w):
    w.update_idletasks()
    i = w.winfo_id()
    return user32.GetParent(i) or i


def excluir_da_captura(w):
    """Faz a janela ficar invisível para capturas de tela (WDA_EXCLUDEFROMCAPTURE)."""
    return bool(user32.SetWindowDisplayAffinity(hwnd_de(w), 0x11))


def clique_atravessa(w):
    """Clique do mouse passa pela janela (TRANSPARENT | LAYERED | TOOLWINDOW)."""
    h = hwnd_de(w)
    estilo = user32.GetWindowLongW(h, -20)
    user32.SetWindowLongW(h, -20, estilo | 0x20 | 0x80000 | 0x80)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tradutor")
        self.root.attributes("-topmost", True)
        self.root.geometry("+20+20")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.sair)

        self.q = queue.Queue()
        self.region = None
        self.versao = 0
        self.pausado = False
        self.selecionando = False
        self.rodando = True
        self.overlay = None
        self.label = None

        self.status = tk.Label(self.root, text="Carregando OCR...", width=60, anchor="w")
        self.status.pack(padx=6, pady=(6, 2))
        barra = tk.Frame(self.root)
        barra.pack(padx=6, pady=(2, 6))
        tk.Button(barra, text=f"Selecionar área ({TECLA_AREA.upper()})",
                  command=self.selecionar_area).pack(side="left", padx=2)
        self.btn_pausa = tk.Button(barra, text=f"Pausar ({TECLA_PAUSA.upper()})",
                                   command=self.alternar_pausa)
        self.btn_pausa.pack(side="left", padx=2)
        tk.Button(barra, text="Sair", command=self.sair).pack(side="left", padx=2)

        self.root.update()
        excluir_da_captura(self.root)  # painel de controle também some da captura

        self.criar_overlay()
        self.carregar_regiao()

        if keyboard:
            try:
                keyboard.add_hotkey(TECLA_PAUSA, lambda: self.q.put(("cmd", "pausa")))
                keyboard.add_hotkey(TECLA_AREA, lambda: self.q.put(("cmd", "area")))
                keyboard.add_hotkey(TECLA_SAIR, lambda: self.q.put(("cmd", "sair")))
            except Exception:
                pass

        threading.Thread(target=self.worker, daemon=True).start()
        self.root.after(50, self.poll)

    # ------------------------------ OVERLAY ------------------------------
    def criar_overlay(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.0)
        w.configure(bg=COR_FUNDO)
        self.label = tk.Label(w, bg=COR_FUNDO, fg=COR_TEXTO, justify="left", anchor="nw")
        self.label.pack(fill="both", expand=True, padx=8, pady=6)
        w.geometry("10x10+0+0")
        w.update()
        clique_atravessa(w)
        if not excluir_da_captura(w):
            self.status.config(text="AVISO: Windows sem suporte a ocultar overlay")
        self.overlay = w

    def esconder(self):
        self.overlay.attributes("-alpha", 0.0)

    def mostrar(self, texto):
        if not texto or self.pausado or not self.region:
            self.esconder()
            return
        w, h = self.region["width"], self.region["height"]
        self.label.config(wraplength=max(50, w - 20), text=texto)
        for tam in range(TAM_MAX, TAM_MIN - 1, -2):  # maior fonte que cabe
            self.label.config(font=(FONTE, -tam))
            self.label.update_idletasks()
            if self.label.winfo_reqheight() <= h - 6:
                break
        self.overlay.attributes("-alpha", OPACIDADE)

    # ------------------------------ REGIÃO -------------------------------
    def definir_regiao(self, x, y, w, h, salvar=True):
        self.region = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        self.overlay.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        self.esconder()
        self.versao += 1
        if salvar:
            try:
                with open(ARQUIVO_REGIAO, "w") as f:
                    json.dump(self.region, f)
            except Exception:
                pass
        self.status.config(text="Pausado" if self.pausado else "Ativo")

    def carregar_regiao(self):
        try:
            with open(ARQUIVO_REGIAO) as f:
                r = json.load(f)
            self.definir_regiao(r["left"], r["top"], r["width"], r["height"], salvar=False)
        except Exception:
            pass

    def selecionar_area(self):
        if self.selecionando:
            return
        self.selecionando = True
        self.esconder()
        with mss.mss() as s:
            m = s.monitors[0]  # todos os monitores juntos
        sel = tk.Toplevel(self.root)
        sel.overrideredirect(True)
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.3)
        sel.configure(bg="black")
        sel.geometry(f"{m['width']}x{m['height']}+{m['left']}+{m['top']}")
        cv = tk.Canvas(sel, bg="black", highlightthickness=0, cursor="crosshair")
        cv.pack(fill="both", expand=True)
        ini, ret = [0, 0], [None]

        def cancelar(_e=None):
            sel.destroy()
            self.selecionando = False

        def pressionar(e):
            ini[:] = [e.x, e.y]
            ret[0] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=3)

        def arrastar(e):
            if ret[0]:
                cv.coords(ret[0], ini[0], ini[1], e.x, e.y)

        def soltar(e):
            if not ret[0]:
                return cancelar()
            x1, x2 = sorted((ini[0], e.x))
            y1, y2 = sorted((ini[1], e.y))
            sel.destroy()
            self.selecionando = False
            if x2 - x1 >= 30 and y2 - y1 >= 20:
                self.definir_regiao(m["left"] + x1, m["top"] + y1, x2 - x1, y2 - y1)

        cv.bind("<ButtonPress-1>", pressionar)
        cv.bind("<B1-Motion>", arrastar)
        cv.bind("<ButtonRelease-1>", soltar)
        sel.bind("<Escape>", cancelar)
        sel.focus_force()
        self.status.config(text="Arraste sobre a caixa de texto (Esc cancela)")

    # ------------------------------ CONTROLE -----------------------------
    def alternar_pausa(self):
        self.pausado = not self.pausado
        if self.pausado:
            self.esconder()
            self.btn_pausa.config(text=f"Retomar ({TECLA_PAUSA.upper()})")
            self.status.config(text="Pausado")
        else:
            self.versao += 1  # força nova leitura ao retomar
            self.btn_pausa.config(text=f"Pausar ({TECLA_PAUSA.upper()})")
            self.status.config(text="Ativo")

    def sair(self):
        self.rodando = False
        if keyboard:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.root.destroy()

    def poll(self):
        try:
            while True:
                tipo, *dados = self.q.get_nowait()
                if tipo == "cmd":
                    {"pausa": self.alternar_pausa, "area": self.selecionar_area,
                     "sair": self.sair}[dados[0]]()
                    if dados[0] == "sair":
                        return
                elif tipo == "texto":
                    ver, txt = dados
                    if ver == self.versao:
                        self.mostrar(txt)
                elif tipo == "status":
                    self.status.config(text=dados[0])
        except queue.Empty:
            pass
        if self.rodando:
            self.root.after(50, self.poll)

    # ------------------------------ WORKER -------------------------------
    @staticmethod
    def ler(ocr, img):
        resultado, _ = ocr(np.ascontiguousarray(img))
        if not resultado:
            return ""
        linhas = [r[1] for r in resultado if float(r[2]) >= MIN_CONFIANCA]
        texto = re.sub(r"\s+", " ", " ".join(linhas)).strip()
        return texto if len(texto) >= 2 else ""

    def worker(self):
        try:
            try:
                ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            except Exception:
                ocr = RapidOCR()
        except Exception as e:
            self.q.put(("status", f"Erro ao carregar OCR: {e}"))
            return

        self.q.put(("status", "Carregando modelo de tradução..."))
        try:
            carregar_modelo_argos("en", "pt")
        except Exception as e:
            self.q.put(("status", f"Erro ao carregar ArgosTranslate: {e}"))

        self.q.put(("status", "Ativo" if self.region else "Selecione a área (F9)"))

        cache = {}
        anterior, sujo, estavel, ver_local, ultimo = None, False, 0, -1, None

        with mss.mss() as sct:  # mss precisa ser criado dentro da própria thread
            while self.rodando:
                if self.pausado or self.selecionando or self.region is None:
                    time.sleep(0.1)
                    continue
                if ver_local != self.versao:
                    ver_local = self.versao
                    anterior, sujo, estavel, ultimo = None, True, 0, None
                ver = ver_local

                try:
                    frame = np.asarray(sct.grab(dict(self.region)))  # BGRA
                except Exception:
                    time.sleep(0.5)
                    continue

                # versão pequena em cinza só para detectar mudanças (barato)
                cinza = frame[::4, ::4, :3].astype(np.int16).sum(axis=2) // 3
                if anterior is not None and cinza.shape == anterior.shape:
                    mudou = (np.abs(cinza - anterior) > 40).mean() > SENSIBILIDADE
                else:
                    mudou = True
                anterior = cinza

                if mudou:
                    sujo, estavel = True, 0
                else:
                    estavel += 1

                if sujo and estavel >= FRAMES_ESTAVEIS:
                    sujo = False
                    texto = self.ler(ocr, frame[:, :, :3])
                    # texto quase idêntico ao anterior = ruído do OCR, não retraduz
                    parecido = bool(ultimo and texto and len(texto) > 15
                                    and SequenceMatcher(None, texto, ultimo).ratio() > 0.95)
                    if texto != ultimo and not parecido:
                        ultimo = texto
                        if not texto:
                            self.q.put(("texto", ver, ""))
                        else:
                            texto_chave = re.sub(r"[^\w\s]", "", texto.lower()).strip()

                            pt = cache.get(texto_chave)
                            if pt is None:
                                self.q.put(("status", "Traduzindo..."))
                                try:
                                    # Tradução 100% local e sem risco de bloqueio
                                    pt = argostranslate.translate.translate(texto, "en", "pt")

                                    if len(cache) > 500:
                                        cache.clear()
                                    cache[texto_chave] = pt
                                except Exception as e:
                                    self.q.put(("status", f"Erro na tradução: {e}"))
                                    continue
                                self.q.put(("status", "Ativo"))
                            self.q.put(("texto", ver, pt))
                time.sleep(INTERVALO)


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordenadas em pixels reais
    except Exception:
        pass
    try:  # prioridade baixa: o jogo tem preferência sobre o tradutor
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass
    App().root.mainloop()