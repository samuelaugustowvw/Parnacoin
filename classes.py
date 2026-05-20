# classes.py
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.exceptions import InvalidSignature
from random import uniform
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import json
import hashlib
import os
import re

def SHA256(data: str) -> str:
    if isinstance(data, (dict, list)):
        s = json.dumps(data, sort_keys=True, ensure_ascii=True)
    elif isinstance(data, bytes):
        s = data.decode('utf-8', errors='ignore')
    else:
        s = str(data)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def double_sha256_of_obj(obj) -> str:
    serialized = json.dumps(
        obj,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True
    ).encode("utf-8")
    
    first_hash = hashlib.sha256(serialized).digest()
    return hashlib.sha256(first_hash).hexdigest()

def ensure_blockchain_file(path="blockchain.txt"):
    if not os.path.exists(path):
        print("criando novo blockchain")
        # create a genesis structure: dict with chain "0" containing genesis block
        genesis = {
            "0": [
                {
                    "id": 0,
                    "nonce": 0,
                    "raiz_merkle": SHA256([]),
                    "hash_anterior": "0"*64,
                    "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
                    "alvo_dificuldade": 1,
                    "transacoes": []
                }
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)

def carregar_ou_gerar_chaves(dados_path):
    def decode_base64_padded(data):
        data = "".join(data.split())  # remove quebras de linha e espaços
        # corrige padding
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data)

    if os.path.exists(dados_path):
        with open(dados_path, "r", encoding="utf-8") as arquivo:
            conteudo = arquivo.read().strip()
            if conteudo:
                try:
                    # Extrai PRIVATE KEY
                    pem_priv_base64 = re.search(
                        r"-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----",
                        conteudo, re.DOTALL
                    ).group(1)
                    pem_priv_bytes = decode_base64_padded(pem_priv_base64)

                    chave_privada = serialization.load_pem_private_key(
                        pem_priv_bytes,
                        password=None,
                        backend=default_backend()
                    )

                    # Extrai PUBLIC KEY
                    pem_pub_base64 = re.search(
                        r"-----BEGIN PUBLIC KEY-----(.*?)-----END PUBLIC KEY-----",
                        conteudo, re.DOTALL
                    ).group(1)
                    pem_pub_bytes = decode_base64_padded(pem_pub_base64)

                    chave_publica = serialization.load_pem_public_key(
                        pem_pub_bytes,
                        backend=default_backend()
                    )

                    # Converte para PEM padrão (bytes)
                    pem_priv_padrao = chave_privada.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    )

                    pem_pub_padrao = chave_publica.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    )

                    print("Chaves extraídas com sucesso!")
                    return pem_priv_padrao, pem_pub_padrao

                except Exception as e:
                    print(f"Erro ao extrair chave existente: {e}")

    # Se não existir, gera nova chave
    chave_privada = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    chave_publica = chave_privada.public_key()

    pem_priv_padrao = chave_privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    pem_pub_padrao = chave_publica.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Salva no arquivo em Base64 para manter compatibilidade
    with open(dados_path, "w", encoding="utf-8") as arquivo:
        arquivo.write("-----BEGIN PRIVATE KEY-----\n")
        arquivo.write(base64.b64encode(pem_priv_padrao).decode() + "\n")
        arquivo.write("-----END PRIVATE KEY-----\n\n")
        arquivo.write("-----BEGIN PUBLIC KEY-----\n")
        arquivo.write(base64.b64encode(pem_pub_padrao).decode() + "\n")
        arquivo.write("-----END PUBLIC KEY-----\n")

    return pem_priv_padrao, pem_pub_padrao

base_dir = os.path.dirname(os.path.abspath(__file__))

class Base:
    def __init__(self, blockchain_path=os.path.join(base_dir, "blockchain.txt"), dados_path=os.path.join(base_dir, "dados.txt")):
        ensure_blockchain_file(blockchain_path)
        if not os.path.exists(dados_path):
            with open(dados_path, 'w', encoding='utf-8') as f:
                f.write("")

        pem_privado, pem_publico = carregar_ou_gerar_chaves(dados_path)

        with open(blockchain_path, 'r', encoding='utf-8') as arquivo:
            copia_blockchain = arquivo.read()

        self.chave_privada = pem_privado
        self.chave_publica = pem_publico
        self.copia_blockchain = copia_blockchain
        self.blockchain_path = blockchain_path

    def carregar_chave_privada(self):
        """Carrega a chave privada do formato PEM para um objeto RSAPrivateKey."""
        return serialization.load_pem_private_key(
            self.chave_privada,
            password=None,
            backend=default_backend()
        )

    @staticmethod
    def carregar_chave_publica_do_base64(b64: str):
        raw = base64.b64decode(b64)
        return serialization.load_pem_public_key(raw, backend=default_backend())

    def assinar(self, transacao: dict) -> dict:
        chave_privada_obj = self.carregar_chave_privada()
        transacao_para_assinar = transacao.copy()
        transacao_para_assinar["assinatura"] = ""
        
        # Use a mesma serialização consistente
        mensagem = json.dumps(
            transacao_para_assinar,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        ).encode("utf-8")

        assinatura = chave_privada_obj.sign(
            mensagem,
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        transacao["assinatura"] = base64.b64encode(assinatura).decode('utf-8')
        return transacao

    @staticmethod
    def validar_assinatura(transacao: dict) -> bool:
        """Valida assinatura usando a chave pública contida na transação (base64-PEM)."""
        try:
            chave_publica_b64 = transacao.get("chave_publica")
            if not chave_publica_b64:
                return False
            chave_obj = Base.carregar_chave_publica_do_base64(chave_publica_b64)

            transacao_sem_assinatura = transacao.copy()
            transacao_sem_assinatura["assinatura"] = ""
            
            # Use a mesma serialização consistente
            mensagem = json.dumps(
                transacao_sem_assinatura,
                sort_keys=True,
                separators=(',', ':'),
                ensure_ascii=True
            ).encode("utf-8")

            assinatura = base64.b64decode(transacao.get("assinatura", ""))
            chave_obj.verify(
                assinatura,
                mensagem,
                asym_padding.PSS(
                    mgf=asym_padding.MGF1(hashes.SHA256()),
                    salt_length=asym_padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False
        except Exception:
            return False


class Usuario(Base):
    def criar_transacao_aleatoria(self, beneficiario: bytes):
        """Cria uma transação aleatória para testes. beneficiário deve ser PEM bytes ou base64-encoded PEM string."""
        if isinstance(beneficiario, bytes):
            beneficiario_b64 = base64.b64encode(beneficiario).decode('utf-8')
        elif isinstance(beneficiario, str):
            beneficiario_b64 = beneficiario
        else:
            raise TypeError("Beneficiário deve ser bytes (PEM) ou string base64")
        
        transacao = {
            "id": "",
            "beneficiario": beneficiario_b64,
            "chave_publica": base64.b64encode(self.chave_publica).decode('utf-8'),
            "quantidade": round(uniform(0.5, 10), 8),
            "assinatura": "",
            "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
            "taxa": 0.0
        }

        # ← MUDANÇA: Usar a mesma serialização que será usada na assinatura
        transacao_copia = transacao.copy()
        transacao_copia["assinatura"] = ""
        
        # Usar a mesma serialização JSON que será usada no método assinar()
        transacao_serializada = json.dumps(
            transacao_copia,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        )
        
        # Calcular o ID baseado na serialização consistente
        transacao["id"] = hashlib.sha256(
            hashlib.sha256(transacao_serializada.encode('utf-8')).digest()
        ).hexdigest()
        
        transacao = self.assinar(transacao)
        return transacao

    def criar_transacao(self, beneficiario: bytes, quantidade: float, taxa: float):
        """Cria uma transação assinada."""
        beneficiario_b64 = beneficiario if isinstance(beneficiario, str) else base64.b64encode(beneficiario).decode('utf-8')
        
        transacao = {
            "id": "",
            "beneficiario": beneficiario_b64,
            "chave_publica": base64.b64encode(self.chave_publica).decode('utf-8'),
            "quantidade": float(quantidade),
            "assinatura": "",
            "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
            "taxa": float(taxa)
        }

        # Use a mesma serialização para cálculo do ID
        transacao_copia = transacao.copy()
        transacao_copia["assinatura"] = ""
        
        # Serialize exatamente como será para assinatura
        serialized = json.dumps(
            transacao_copia,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        ).encode("utf-8")
        
        # Calcule o ID usando double SHA256
        first_hash = hashlib.sha256(serialized).digest()
        transacao["id"] = hashlib.sha256(first_hash).hexdigest()
        
        transacao = self.assinar(transacao)
        return transacao


class Minerador(Base):
    def criar_transacao_recompensa(self, soma_taxas: float, nonce=0):
        """Cria uma transação de recompensa para o minerador"""
        beneficiario_b64 = base64.b64encode(self.chave_publica).decode('utf-8')
        transacao = {
            "id": "",
            "beneficiario": beneficiario_b64,
            "quantidade": float(10.0 + soma_taxas),
            "chave_publica": beneficiario_b64,
            "assinatura": "",
            "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
            "nonce_extra": int(nonce),
            "taxa": 0.0
        }

        transacao_copia = transacao.copy()
        transacao_copia["assinatura"] = ""
        
        serialized = json.dumps(
            transacao_copia,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        ).encode("utf-8")
        
        first_hash = hashlib.sha256(serialized).digest()
        transacao["id"] = hashlib.sha256(first_hash).hexdigest()
        
        return transacao

    def gerar_bloco(self, transacoes_do_bloco: list, hash_anterior: str, alvo_dificuldade: int):
        with open(self.blockchain_path, "r", encoding='utf-8') as arquivo:
            copia_blockchain = json.load(arquivo)
            # Aqui assumimos a cadeia principal chave "0"
            id = copia_blockchain["0"][-1]["id"] + 1

        # Calcula raiz merkle simples: double SHA of serialized tx ids list
        tx_ids = [tx.get("id", "") for tx in transacoes_do_bloco]
        raiz_merkle = double_sha256_of_obj(tx_ids)

        return {
            "id": id,
            "nonce": 0,
            "raiz_merkle": raiz_merkle,
            "hash_anterior": hash_anterior,
            "data_hora": datetime.now(ZoneInfo("America/Fortaleza")).isoformat(),
            "alvo_dificuldade": int(alvo_dificuldade),
            "transacoes": transacoes_do_bloco
        }

# teste (opcional) -- remova em produção
if __name__ == "__main__":
    teste = Base()
    print("Chave pública (PEM):")
    print(teste.chave_publica.decode('utf-8'))
