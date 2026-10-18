import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import atualizador as at

EXE = b"MZ" + b"novo" * 100


class _H(BaseHTTPRequestHandler):
    release = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/releases/latest"):
            if self.release is None:
                self.send_response(404); self.end_headers(); return
            corpo = json.dumps(self.release).encode()
        elif self.path == "/baixar":
            corpo = EXE
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(corpo))); self.end_headers()
        self.wfile.write(corpo)


class TesteAtualizador(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"
        self.dir = Path(tempfile.mkdtemp())
        self.exe = self.dir / "NumpadDeck.exe"
        self.exe.write_bytes(b"MZvelho")
        self.addCleanup(self.srv.shutdown)
        _H.release = self.rel()

    def rel(self, tag="v1.2", sha=None, size=None):
        return {"tag_name": tag, "assets": [{"name": "NumpadDeck.exe", "browser_download_url": self.base + "/baixar",
                "size": len(EXE) if size is None else size,
                "digest": "sha256:" + (sha or hashlib.sha256(EXE).hexdigest())}]}

    def roda(self, atual="v1.0"):
        return at.verificar_e_atualizar(atual, self.exe, "x/y", self.base, exigir_https=False)

    def test_versoes(self):
        self.assertEqual(at.versao_tupla("v1.2"), (1, 2, 0))
        self.assertGreater(at.versao_tupla("v1.10"), at.versao_tupla("v1.9"))
        self.assertIsNone(at.versao_tupla("dev"))

    def test_dev_nao_atualiza(self):
        self.assertEqual(self.roda("dev")["status"], "dev")
        self.assertEqual(self.exe.read_bytes(), b"MZvelho")

    def test_atualiza(self):
        self.assertEqual(self.roda()["status"], "atualizado")
        self.assertEqual(self.exe.read_bytes(), EXE)
        self.assertEqual((self.dir / "NumpadDeck.antigo.exe").read_bytes(), b"MZvelho")
        at.limpar_restos(self.exe)
        self.assertFalse((self.dir / "NumpadDeck.antigo.exe").exists())

    def test_ja_atual(self):
        self.assertEqual(self.roda("v1.2")["status"], "atual")
        self.assertEqual(self.exe.read_bytes(), b"MZvelho")

    def test_sem_release(self):
        _H.release = None
        self.assertEqual(self.roda()["status"], "atual")

    def test_sha_errado_recusa(self):
        _H.release = self.rel(sha="0" * 64)
        with self.assertRaises(at.ErroAtualizacao):
            self.roda()
        self.assertEqual(self.exe.read_bytes(), b"MZvelho")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["NumpadDeck.exe"])

    def test_tamanho_errado_recusa(self):
        _H.release = self.rel(size=5)
        with self.assertRaises(at.ErroAtualizacao):
            self.roda()

    def test_origem_fora_do_repo_recusa(self):
        info = {"tag": "v9", "url": "https://evil.example/NumpadDeck.exe", "tamanho": None, "sha256": ""}
        with self.assertRaises(at.ErroAtualizacao):
            at.baixar(info, self.dir / "x.exe", "x/y")

    def test_sem_rede(self):
        self.srv.shutdown(); self.srv.server_close()
        with self.assertRaises(at.ErroAtualizacao):
            self.roda()


if __name__ == "__main__":
    unittest.main()
