import json, base64, urllib.request, os

token = os.environ.get("GH_TOKEN", "")
api = "https://api.github.com/repos/ivanareazero-eng/areazero-novedades/contents/state.json"
headers = {
    "Authorization": "token " + token,
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json"
}

with open("areazero_products_state.json", "rb") as f:
    data = f.read()

encoded = base64.b64encode(data).decode()
req = urllib.request.Request(api, headers=headers)
sha = None
try:
    with urllib.request.urlopen(req) as r:
        sha = json.loads(r.read())["sha"]
except:
    pass

payload = {"message": "Actualizar estado", "content": encoded}
if sha:
    payload["sha"] = sha

req2 = urllib.request.Request(
    api, data=json.dumps(payload).encode(),
    headers=headers, method="PUT"
)
urllib.request.urlopen(req2)
print("Estado guardado OK")
