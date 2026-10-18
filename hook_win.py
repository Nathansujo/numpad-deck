"""Hook global de teclado (Windows) usando o filtro de baixo nível do pynput.

O filtro roda dentro do hook do Windows: se demorar, o teclado inteiro trava. Por isso ele
só consulta o núcleo (rápido) e, em qualquer erro, deixa a tecla passar.
"""
import logging


def iniciar_hook(nucleo):
    from pynput import keyboard

    WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
    listener = None

    def filtro(msg, dados):
        suprimir = False
        try:
            suprimir = nucleo.evento(msg in (WM_KEYDOWN, WM_SYSKEYDOWN), dados.vkCode, dados.scanCode, dados.flags)
        except Exception:
            logging.exception("Erro no hook de teclado")
        if suprimir:
            listener.suppress_event()  # engole a tecla (não chega ao programa em foco)
        return False  # não precisamos dos callbacks on_press/on_release

    listener = keyboard.Listener(win32_event_filter=filtro)
    listener.daemon = True
    listener.start()
    return listener
