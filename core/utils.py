from .constants import EMBED_FOOTER_TEXT
from socket import socket
from json import dumps as json_dumps
from base64 import b64encode

ssl_context = __import__("ssl").create_default_context()

def parse_proxy_string(proxy_str):
    proxy_str = proxy_str.rpartition("://")[2]
    auth, _, fields = proxy_str.rpartition("@")
    fields = fields.split(":", 2)

    if len(fields) == 2:
        hostname, port = fields
        if auth:
            auth = "Basic " + b64encode(auth.encode()).decode()
    elif len(fields) == 3:
        hostname, port, auth = fields
        auth = "Basic " + b64encode(auth.encode()).decode()
    else:
        raise Exception(f"Unrecognized proxy format: {proxy_str}")

    addr = (hostname.lower(), int(port))
    return auth, addr

def parse_batch_response(data, limit):
    index = 10
    status_assoc = {}
    for _ in range(limit):
        id_index = data.find(b'"id":', index)
        if id_index == -1:
            break
        index = data.find(b",", id_index + 5)
        group_id = data[id_index + 5 : index]
        index = data.find(b'"owner":', index) + 8
        status_assoc[group_id] = (data[index] == 123)
        index += 25
    return status_assoc

def find_latest_group_id():
    group_id = 0
    sock = make_http_socket(("www.roblox.com", 443))

    def exists(group_id):
        sock.send(f"GET /groups/{group_id}/- HTTP/1.1\nHost:www.roblox.com\n\n".encode())
        resp = sock.recv(1048576)
        return not b"location: https://www.roblox.com/search/groups?keyword=" in resp

    for l in range(8, 0, -1):
        num = int("1" + ("0" * (l - 1)))
        for inc in range(1, 10):
            if inc == 9 or not exists(group_id + (num * inc)):
                group_id += num * (inc - 1)
                break

    return group_id

def send_webhook(url, **kwargs):
    payload = json_dumps(kwargs, separators=(",", ":"))
    hostname, path = url.split("://", 1)[1].split("/", 1)
    https = url.startswith("https")
    if ":" in hostname:
        hostname, port = hostname.split(":", 1)
        port = int(port)
    else:
        port = 443 if https else 80

    sock = make_http_socket((hostname, port), ssl_wrap=https)
    try:
        sock.send(
            f"POST /{path} HTTP/1.1\r\n"
            f"Host: {hostname}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Content-Type: application/json\r\n"
            "\r\n"
            f"{payload}".encode())
        sock.recv(4096)
    finally:
        shutdown_socket(sock)

def mostvisitegame(id):
  game = requests.get(f'https://games.roblox.com/v2/groups/{id}/games?accessFilter=All&sortOrder=Asc&limit=100')
  game = json.loads(game.text)["data"]
  gameCount = len(game)
  visitGameList = []
  if gameCount == 0:
    mostVisits = 'None'
  else:
      for games in game:
        visits = games["placeVisits"]
        visitGameList.append(visits)
        mostVisits = max(visitGameList)
  return mostVisits
def gamecount(id):
  game = requests.get(f'https://games.roblox.com/v2/groups/{id}/games?accessFilter=All&sortOrder=Asc&limit=100')
  game = json.loads(game.text)["data"]
  return len(game)
 
def clothingcount(id):
  return str(len(requests.get(f'https://catalog.roblox.com/v1/search/items/details?Category=3&CreatorTargetId={id}&CreatorType=2&Limit=30').json()["data"]))
 
def robuxcount(id):
  er = requests.get(f'https://economy.roblox.com/v1/groups/{id}/currency',cookies={".ROBLOSECURITY": "_|WARNING-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_406F5E2F5D8DA0516BAA20D8A00AFED2D3FB7653FE948F86817BF1C8A1DF7499D7FBC7C69B92E74B92E82F64A5DD4EB8A1165F9E70530F763757BEEBBEF23152A033C61C9ABC25BDE7DA1F6D47D8346F94AA12C557D563F4F9B38B2814D2DFA58C9BBD426F712AAAB3D9B348C9C8C67B84F8A974E71DEEFD93D3514E18B3F8D4CEAB5E0963A706EE001265621F75ED72023D1DFF782AEBA8BD27F08C5B0429EFCF934229B5588A210A938A6F78E5F7FE3C5ADF8E87ABB0FCC3527413F40058E9D19F337D1F059647DA1C1BFD074F709C5947C2847A1817DC0D3E96AEC69FD6EE3C71E853EA27C9023EB208790FD64FD1E914B0AAD6983150BE7A2422936CDB8D81ACEA47B9D38DBC95AB83D35F72FFF835C9E9B6106849A5C46F6054FBD771853C495addr1vyh3ysu2rl4q2llq80sptvk3hftr8xen8dc73kdc3ezlqngpqtaye
  try:
   robux = er.json()["robux"]
  except:
   robux = '?'
def make_embed(group_info, date):
    embed = dict(
        title = "**Unclaimed Group Found!**",
      description = f"https://www.roblox.com/groups/{group_info['id']}",
      fields = [
            dict(name="Name", value=group_info["name"]),
            dict(name="Members", value=group_info["memberCount"]),
            dict(name="Description", value=f"{group_info['description']}"),
            dict(name="･Game Count", value=f"{gamecount(group_info['id'])}"),
            dict(name="･Total Game Visits", value=f"{mostvisitegame(group_info['id'])}"),
            dict(name="Clothing Count", value=f"{clothingcount(group_info['id'])}"),
            dict(name="Funds", value="?")
        ],
            thumbnail = dict(url = 'https://cdn.discordapp.com/attachments/926966000614776873/1007829247357890711/3FE3CE78-20A1-4A8E-94DD-E52D88C44F87.jpg'),
     color = random.randint(0,16777215),
        footer = dict(
            text = "Onyx Group finder beta"
        ),
        timestamp=date.isoformat()
                )

def make_http_socket(addr, timeout=5, proxy_addr=None, proxy_headers=None,
                     ssl_wrap=True, hostname=None):    
    sock = socket()
    sock.settimeout(timeout)
    sock.connect(proxy_addr or addr)
    
    try:
        if proxy_addr:
            sock.send("".join([
                f"CONNECT {addr[0]}:{addr[1]} HTTP/1.1\r\n",
                *([
                    f"{header}: {value}\r\n"
                    for header, value in proxy_headers.items()
                ] if proxy_headers else []),
                "\r\n"
            ]).encode())
            connect_resp = sock.recv(4096)
            if not (
                connect_resp.startswith(b"HTTP/1.1 200") or\
                connect_resp.startswith(b"HTTP/1.0 200")
            ):
                raise ConnectionRefusedError

        if ssl_wrap:
            sock = ssl_context.wrap_socket(
                sock, False, False, False, hostname or addr[0])
            sock.do_handshake()

        return sock

    except:
        shutdown_socket(sock)
        raise

def shutdown_socket(sock):
    try:
        sock.shutdown(2)
    except OSError:
        pass
    sock.close()

def slice_list(lst, num, total):
    per = int(len(lst)/total)
    chunk = lst[per * num : per * (num + 1)]
    return chunk

def slice_range(r, num, total):
    per = int((r[1]-r[0]+1)/total)
    return (
        r[0] + (num * per),
        r[0] + ((num + 1) * per)
    )
