import json
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from classes import Minerador, SHA256

# Cria o minerador (gera chave pública automaticamente)
minerador = Minerador()

# Cria a transação de recompensa (sem taxas porque não há transações ainda)
transacao_recompensa = minerador.criar_transacao_recompensa(soma_taxas=0.0)

# --- Corrige os campos que ainda estão em bytes ---
for campo in ["beneficiario", "chave_publica"]:
    if isinstance(transacao_recompensa[campo], (bytes, bytearray)):
        transacao_recompensa[campo] = base64.b64encode(transacao_recompensa[campo]).decode("utf-8")

# --- Gera o bloco gênese ---
transacoes_json = json.dumps([transacao_recompensa], sort_keys=True)
bloco_genesis = {
    "id": 0,
    "nonce": 0,
    "raiz_merkle": SHA256(SHA256(transacoes_json)),
    "hash_anterior": "0" * 64,
    "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
    "alvo_dificuldade": 4,  # dificuldade inicial (pode aumentar depois)
    "transacoes": [transacao_recompensa]
}

# --- Salva no arquivo blockchain.txt ---
blockchain = {"0": [bloco_genesis]}
with open("blockchain.txt", "w", encoding="utf-8") as f:
    json.dump(blockchain, f, indent=2, ensure_ascii=False)

print("✅ Bloco gênese criado com sucesso!")
