# minerador.py
import base64
import json
import cryptography.exceptions
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import paho.mqtt.client as mqtt
from dateutil.parser import parse
from classes import Minerador, SHA256, double_sha256_of_obj, ensure_blockchain_file
import os
import time
from typing import List

idMinerador = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFtdkdiZERmanRPVXNFaGRTaDcrNAoyd29zamdxY1ByNDNDUU9CT0VaQ3U1aUxqZzU0R0ExQUFMMWtiR1g1L0tBK3Nyam15WUMydTUzSFJ6VG11eXI0CllvaHJMTXN2b0tlMDNwT0lSTVhYNU9Xb3o4cE9GeTNZd0s3RTlxS0FENGthbWNmeWVKaGxwK3l1aEtXZEJTZVEKeGZUdUtPZjJETy9Zb0t3NkJPQTFmRTgwckdTT3l5UWZvQzN1TGxhVjdRU0djN3VPZ2dOUENvNkRrQnFzbUQ5TwptOHJZYUFEd2piWEtqam1ZOWxqbllEZ3lzdFJDcXZXU3BURjJFOTloTUVjRFFRMmhkZElZVytFYW1hREMwbjNhCllGaTZMd0lob0xGT0ZESjZERnNoK0N5NGpwNUF1Q2FkNUJVajFvbjV4d0ZGM1JOekR6NUZqU0k5Ui9pU0JSd3kKaFFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

BLOCKCHAIN_PATH = "blockchain.txt"
ensure_blockchain_file(BLOCKCHAIN_PATH)

transacoes_recebidas: List[dict] = []
alvo_dificuldade = 24  # número de zeros binários exigidos no início da string hash do bloco

def carregar_blockchain():
    with open(BLOCKCHAIN_PATH, "r", encoding='utf-8') as f:
        return json.load(f)

def salvar_blockchain(blockchain):
    with open(BLOCKCHAIN_PATH, "w", encoding='utf-8') as f:
        json.dump(blockchain, f, indent=2, ensure_ascii=False)

def checar_saldo(chave_publica_b64: str, quantidade: float, taxa: float):
    """Checa se o pagador tem saldo suficiente para fazer uma transferência observando todo o seu histórico na blockchain."""
    try:
        copia_blockchain = carregar_blockchain()
        soma = 0.0
        if taxa and taxa > 0:
            soma += float(taxa)

        print(copia_blockchain)

        # assumimos cadeia principal "0"
        for bloco in copia_blockchain.get("0", []):
            for transacao in bloco.get("transacoes", []):
                print(transacao)
                # entrada: pagador (chave_publica) gastando => subtrai; recebimentos: if beneficiario==chave -> soma
                # Na modelagem original só havia 'quantidade' e 'beneficiario'. Aqui tratamos saldo simplificado:
                # se a chave_publica for beneficiário -> soma; se for chave_publica do tx (pagador) -> subtrai
                print(transacao["beneficiario"])
                print(transacao["chave_publica"])
                print(chave_publica_b64)
                if transacao["beneficiario"] == chave_publica_b64:
                    soma += float(transacao.get("quantidade", 0))
                if transacao["chave_publica"] == chave_publica_b64 and transacao.get("nonce_extra") is None:
                    # considerar gasto (pagador) - na prática nem todas txs terão campo de pagador separado; aqui assumimos
                    # A transação de recompensa do minerador é um caso especial (nonce_extra presente) e não deve ser debitada
                    soma -= float(transacao.get("quantidade", 0))
        print(soma)

        # saldo suficiente?
        return (soma - float(quantidade)) >= 0
    except Exception as e:
        print("Erro checando saldo:", e)
        return False

def tx_serial_para_hash(tx):
    # retorna id se presente, senão calcula id a partir do conteúdo (usado apenas para validação auxiliar)
    if tx.get("id"):
        return tx["id"]
    txc = tx.copy()
    txc["assinatura"] = txc.get("assinatura", "")
    return double_sha256_of_obj(txc)

def checar_bloco(bloco):
    global alvo_dificuldade
    """Verifica a validade do bloco."""
    try:
        # Carrega blockchain atual
        copia_blockchain = carregar_blockchain()

        # Estrutura básica
        required_block_fields = {"id", "nonce", "raiz_merkle", "hash_anterior", "data_hora", "alvo_dificuldade", "transacoes"}
        if not required_block_fields.issubset(set(bloco.keys())):
            raise ValueError("Campos do bloco faltando")

        if not isinstance(bloco["id"], int) or not isinstance(bloco["nonce"], int):
            raise ValueError("id ou nonce não são inteiros")

        if not isinstance(bloco["hash_anterior"], str) or len(bloco["hash_anterior"]) != 64:
            raise ValueError("hash_anterior inválido")

        if not isinstance(bloco["raiz_merkle"], str) or len(bloco["raiz_merkle"]) != 64:
            raise ValueError("raiz_merkle inválida")

        if not isinstance(bloco["alvo_dificuldade"], int) or bloco["alvo_dificuldade"] != alvo_dificuldade:
            raise ValueError("alvo_dificuldade inconsistente")

        if not bloco["transacoes"] or len(bloco["transacoes"]) == 0:
            raise ValueError("Bloco deve conter ao menos 1 transação")

        # validar formato de cada transação
        for idx, transacao in enumerate(bloco["transacoes"]):
            # id hex de 64
            if not isinstance(transacao.get("id", ""), str) or len(transacao.get("id", "")) != 64:
                raise ValueError(f"Transação {idx} id inválido")
            # datetime válido
            try:
                parse(transacao.get("data_hora"))
            except Exception:
                raise ValueError(f"Transação {idx} tem data_hora inválida")

            # reward tx check (assume index 0)
            if idx == 0:
                # reward must have nonce_extra and chave_publica == beneficiario
                if not isinstance(transacao.get("nonce_extra", None), int):
                    raise ValueError("Transação de recompensa inválida (nonce_extra faltante)")
                if transacao.get("beneficiario") != transacao.get("chave_publica"):
                    # acceptable in our miner implementation (both are miner's public key)
                    raise ValueError("Transação de recompensa: beneficiário inconsistente")

            else:
                # para txs normais: quantidade > 0, taxa float, assinatura válida, pagador com saldo
                if float(transacao.get("quantidade", 0)) <= 0:
                    raise ValueError(f"Transação {idx} quantidade inválida")
                if "taxa" not in transacao or not isinstance(transacao["taxa"], (int, float)):
                    raise ValueError(f"Transação {idx} taxa inválida")
                # assinatura e chave pública do pagador
                if not BaseLike_validar_assinatura(transacao):
                    raise ValueError(f"Transação {idx} assinatura inválida")
                # checar saldo do pagador
                pagador_b64 = transacao.get("chave_publica")
                if not checar_saldo(pagador_b64, transacao["quantidade"], transacao["taxa"]):
                    raise ValueError(f"Transação {idx} pagador sem saldo")

        # verifica raiz merkle
        tx_ids = [tx.get("id", "") for tx in bloco["transacoes"]]
        calc_raiz = double_sha256_of_obj(tx_ids)
        if calc_raiz != bloco["raiz_merkle"]:
            raise ValueError("Raiz Merkle inconsistente")

        # verifica hash do bloco (double sha256 de header-like object)
        header = {
            "id": bloco["id"],
            "nonce": bloco["nonce"],
            "raiz_merkle": bloco["raiz_merkle"],
            "hash_anterior": bloco["hash_anterior"],
            "data_hora": bloco["data_hora"],
            "alvo_dificuldade": bloco["alvo_dificuldade"]
        }
        bloco_hash_hex = double_sha256_of_obj(header)
        # converte para binário e conta zeros à esquerda
        bloco_hash_int = int(bloco_hash_hex, 16)
        hash_binario = bin(bloco_hash_int)[2:].zfill(256)
        leading_zeros = len(hash_binario) - len(hash_binario.lstrip("0"))
        if leading_zeros < alvo_dificuldade:
            raise ValueError("Dificuldade de mineração incorreta: bloco não atende ao alvo")

        # verifica encaixe na blockchain principal (chain "0")
        cadeia = copia_blockchain.get("0", [])
        # achamos o index do bloco cujo hash_anterior coincide com o hash calculado do último bloco da cadeia
        ultimo_bloco = cadeia[-1]
        if bloco["hash_anterior"] != double_sha256_of_obj({
            "id": ultimo_bloco["id"],
            "nonce": ultimo_bloco["nonce"],
            "raiz_merkle": ultimo_bloco["raiz_merkle"],
            "hash_anterior": ultimo_bloco["hash_anterior"],
            "data_hora": ultimo_bloco["data_hora"],
            "alvo_dificuldade": ultimo_bloco["alvo_dificuldade"]
        }):
            raise ValueError("Bloco não se encaixa no topo da cadeia principal (hash_anterior mismatch)")

        # checa timestamp de bloco maior que anterior
        t_prev = parse(ultimo_bloco["data_hora"])
        t_cur = parse(bloco["data_hora"])
        if t_cur <= t_prev:
            raise ValueError("Timestamp do bloco não é maior que o do bloco anterior")

        # tudo ok
        return True

    except Exception as e:
        print("checar_bloco: erro:", e)
        return False

def BaseLike_validar_assinatura(transacao):
    # wrapper para usar a implementação de validação de assinatura das classes sem circular import
    try:
        from classes import Base as _Base
        
        # Log temporário para depuração
        print("Validando assinatura da transação:")
        print(f"ID: {transacao['id']}")
        print(f"Chave pública: {transacao['chave_publica'][:50]}...")
        print(f"Assinatura: {transacao['assinatura'][:50]}...")
        
        return _Base.validar_assinatura(transacao)
    except Exception as e:
        print(f"Erro na validação de assinatura: {e}")
        return False

def checar_transacao(transacao: dict):
    """Verifica a validade da transação."""
    try:
        # Primeiro valide a assinatura
        if not BaseLike_validar_assinatura(transacao):
            raise cryptography.exceptions.InvalidSignature("Assinatura inválida")

        # Resto da validação...
        # Beneficiário: deve ser base64 PEM válido
        try:
            base64.b64decode(transacao["beneficiario"])
            serialization.load_pem_public_key(base64.b64decode(transacao["beneficiario"]))
        except Exception:
            raise ValueError("Beneficiário com chave pública inválida")

        # Checa a validade do objeto datetime
        parse(transacao["data_hora"], fuzzy=False)

        # Checa se a quantidade e a taxa a ser transferida é válida
        if float(transacao.get("quantidade", 0)) <= 0 or not isinstance(transacao.get("taxa", 0.0), (int, float)):
            raise ValueError("Quantidade ou taxa inválida")

        # Carrega a chave pública do pagador
        try:
            serialization.load_pem_public_key(base64.b64decode(transacao["chave_publica"]))
        except Exception:
            raise ValueError("Chave pública do pagador inválida")

        # Verifica saldo do pagador
        if not checar_saldo(transacao["chave_publica"], transacao["quantidade"], transacao["taxa"]):
            raise ValueError("Saldo insuficiente para a transação")

        print("Transação válida recebida!")
        return True

    except cryptography.exceptions.InvalidSignature as e:
        print("ERRO: Transação inválida (assinatura)!", e)
        return False
    except ValueError as e:
        print("Transação inválida:", e)
        return False
    except Exception as e:
        print("Erro inesperado checando transação:", e)
        return False

def minerar_bloco(hash_anterior, mempool):
    """Minera um novo bloco"""

    # Ordena transações da mempool por taxa (o minerador prioriza as transações mais lucrativas)
    transacoes_ordenadas = sorted(mempool, key=lambda transacao: transacao.get('taxa', 0), reverse=True)
    # Limita em 100 transações por bloco
    transacoes_selecionadas = transacoes_ordenadas[:100]

    soma_taxas = sum([float(tx.get("taxa", 0)) for tx in transacoes_selecionadas])

    # Transação que premia o minerador
    miner = Minerador()  # cria um minerador local (gera chaves)
    transacao_recompensa = miner.criar_transacao_recompensa(soma_taxas)

    # Bloco conterá a recompensa mais as transações selecionadas
    transacoes_do_bloco = [transacao_recompensa] + transacoes_selecionadas

    global alvo_dificuldade
    novo_bloco = miner.gerar_bloco(transacoes_do_bloco, hash_anterior, alvo_dificuldade)

    # Processo de Proof of Work
    while True:
        # calcula hash do header (double SHA)
        header = {
            "id": novo_bloco["id"],
            "nonce": novo_bloco["nonce"],
            "raiz_merkle": novo_bloco["raiz_merkle"],
            "hash_anterior": novo_bloco["hash_anterior"],
            "data_hora": novo_bloco["data_hora"],
            "alvo_dificuldade": novo_bloco["alvo_dificuldade"]
        }
        tentativa_hash = double_sha256_of_obj(header)
        tentativa_int = int(tentativa_hash, 16)
        bin_hash = bin(tentativa_int)[2:].zfill(256)
        leading_zeros = len(bin_hash) - len(bin_hash.lstrip("0"))
        if leading_zeros >= alvo_dificuldade:
            # bloco minerado
            return novo_bloco
        novo_bloco["nonce"] += 1
        # pequenas pausas podem ser úteis para evitar 100% CPU em ambiente de teste
        # time.sleep(0.0001)

######## v Implementação do MQTT v ########

def ao_conectar(client, userdata, flags, rc, properties=None):
    print("Conectado! rc=", rc)

def mensagem_recebida(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        print("Mensagem chegada tópico:", msg.topic, "payload:", payload)
        if msg.topic == "rede-parnacoin":
            global transacoes_recebidas
            transacao = json.loads(payload)

            if checar_transacao(transacao):
                transacoes_recebidas.append(transacao)
                print("Transação aceita e adicionada à fila.")
            else:
                print("Transação rejeitada.")

        elif msg.topic == "rede-blocos":
            bloco = json.loads(payload)
            if checar_bloco(bloco):
                # se válido, anexar à cadeia principal
                bc = carregar_blockchain()
                bc["0"].append(bloco)
                salvar_blockchain(bc)
                print("Bloco válido adicionado à blockchain.")
            else:
                print("Bloco inválido recebido.")

    except Exception as e:
        print("Erro ao processar mensagem MQTT:", e)

def iniciar_mqtt(broker="127.0.0.1", port=1883):
    mqttc = mqtt.Client(protocol=mqtt.MQTTv311)
    mqttc.on_connect = ao_conectar
    mqttc.on_message = mensagem_recebida

    mqttc.connect(broker, port, 60)
    mqttc.subscribe("rede-parnacoin", qos=1)
    mqttc.subscribe("rede-blocos", qos=1)
    mqttc.loop_start()
    return mqttc

if __name__ == "__main__":
    print("Iniciando minerador de teste...")
    mqtt_client = iniciar_mqtt()
    # loop principal de mineração (exemplo simples)
    try:
        while True:
            # se precisarmos minerar: pegar o hash anterior do último bloco
            bc = carregar_blockchain()
            ultimo = bc["0"][-1]
            header_ultimo = {
                "id": ultimo["id"],
                "nonce": ultimo["nonce"],
                "raiz_merkle": ultimo["raiz_merkle"],
                "hash_anterior": ultimo["hash_anterior"],
                "data_hora": ultimo["data_hora"],
                "alvo_dificuldade": ultimo["alvo_dificuldade"]
            }
            hash_anterior = double_sha256_of_obj(header_ultimo)
            if transacoes_recebidas:
                mempool = transacoes_recebidas.copy()
                transacoes_recebidas.clear()
                bloco = minerar_bloco(hash_anterior, mempool)
                # publica bloco na rede
                mqtt_client.publish("rede-blocos", json.dumps(bloco), qos=1)
                print("Bloco publicado na rede.")
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        print("Minerador encerrado.")
        mqtt_client.loop_stop()
