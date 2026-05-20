# usuario.py
import json
import paho.mqtt.client as mqtt
from classes import Usuario, SHA256
import base64
import time

def ao_conectar(client, userdata, flags, rc, properties=None):
    print("Conectado à rede Parnacoin! rc=", rc)

mqttc = mqtt.Client(protocol=mqtt.MQTTv311)
mqttc.on_connect = ao_conectar

# Se inscreve na rede Parnacoin com Qualidade de Serviço 1 (1 confirmação de recebimento)
mqttc.connect("127.0.0.1", 1883, 60)
mqttc.subscribe("rede-parnacoin", 1)

# criando um usuário e um beneficiário de teste
a = Usuario()
# b = Usuario()  # beneficiário
chave_beneficiario = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF4Q25ObUhOeEtsNlhXanFvQUh6WgpQeXhHTGIrSVRmR3RSamJsS2twdWpIZk1BdUhyKzBQM2hYc1BlZWViOW5rdEFCOUxnaUo3alpYNG5OdHloRXRiCjlVdkFrUVkzallhZk9lbmhlM1FNNSt0K3kzVmluemc1Q3pDbmNxMytVZytGL3h1RzY0Z2M4OVI4OUxxeGRaOG8KeUV5ZEtaa0YyS25OOVB3cU9SQTNvWW9RRmZQaWVrTm1mWGJFN1JnNUpxNXpGeXNCU2lKQ2RQQUFTcGFzakhQLwo0VXR0S2UzWFdSQ3kvZ2hSYmg3RTFUK2dJK2wzeTNXQ0IySDE3ZjhxanlNVWltc2VLWmJoR1JkOUQ1TmdLUFZjCnRaT3dMY1dZVWhPSjN1ZFo5UGY4TUphV1RaNlRjYk83djlLeVpVQWVxajY3bHlPWUVRbEhWZGpIYytlU0IwVDkKNndJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

transacao = a.criar_transacao(chave_beneficiario, quantidade=1.5, taxa=0.01)
print("Publicando transação:")
print(json.dumps(transacao, indent=2, ensure_ascii=False))

mqttc.publish("rede-parnacoin", json.dumps(transacao), qos=1)
time.sleep(0.5)
print("starting MQTT loop")
mqttc.loop_start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    mqttc.loop_stop()
    print("Usuário encerrado.")
