"""Erros públicos, sem mensagens internas de modelos ou provedores."""


class ErroAnalise(Exception):
    def __init__(self, status_code: int, mensagem: str):
        super().__init__(mensagem)
        self.status_code = status_code
        self.mensagem = mensagem
