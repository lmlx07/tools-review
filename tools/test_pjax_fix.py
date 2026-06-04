import requests, json, time, websocket

bws_url = requests.get('http://127.0.0.1:9222/json/version').json().get('webSocketDebuggerUrl')
bws = websocket.create_connection(bws_url)

def send(cmd, params=None):
    m = {'id': 1, 'method': cmd}
    if params: m['params'] = params
    bws.send(json.dumps(m))
    return json.loads(bws.recv())

result = send('Target.createTarget', {'url': 'https://cdp.autify.cc/'})
target_id = result['result']['targetId']
time.sleep(6)

targets = requests.get('http://127.0.0.1:9222/json').json()
page_ws_url = None
for t in targets:
    if t['id'] == target_id:
        page_ws_url = t['webSocketDebuggerUrl']
        break

page_ws = websocket.create_connection(page_ws_url)
time.sleep(2)

def js(expr):
    page_ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                             'params': {'expression': expr, 'returnByValue': True}}))
    r = json.loads(page_ws.recv())
    return r.get('result', {}).get('result', {})

print('=== 1. ZH Homepage ===')
r = js("!!document.querySelector('#nav .menus_items #lang-switch')")
print(f'switch in nav: {r}')

# PJAX to article
print('\n=== 2. Click article link ===')
js("document.querySelector('a.article-title')?.click()")
time.sleep(5)
r = js("window.location.pathname")
print(f'pathname: {r}')
r = js("!!document.querySelector('#nav .menus_items #lang-switch')")
print(f'switch in nav: {r}')

# If switch exists, click EN to go to /en/article/
r = js("!!document.querySelector('#nav .menus_items #lang-switch')")
if r.get('value'):
    print('\n=== 3. Click EN on article page ===')
    js("document.querySelector('#lang-switch .lo[data-lang=\"en\"]')?.click()")
    time.sleep(5)
    r = js("window.location.pathname")
    print(f'pathname: {r}')
    r = js("!!document.querySelector('#nav .menus_items #lang-switch')")
    print(f'switch in nav: {r}')

    # Click EN nav link to trigger another PJAX
    print('\n=== 4. Click Tags link on EN site ===')
    js("document.querySelector('a[href*=\"/en/tags/\"]')?.click()")
    time.sleep(5)
    r = js("window.location.pathname")
    print(f'pathname: {r}')
    r = js("!!document.querySelector('#nav .menus_items #lang-switch')")
    print(f'switch in nav: {r}')

    # Click 中文 to go back
    print('\n=== 5. Click 中文 on EN tags page ===')
    js("document.querySelector('#lang-switch .lo[data-lang=\"zh-CN\"]')?.click()")
    time.sleep(5)
    r = js("window.location.pathname")
    print(f'pathname: {r}')

page_ws.close()
bws.close()
