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
    return r.get('result', {}).get('result', {}).get('value', str(r))

print('=== ZH Homepage ===')
print(f'nav menus_items count: {js("document.querySelectorAll(\'#nav .menus_items > *\').length")}')
print(f'has lang-switch: {js("!!document.getElementById(\'lang-switch\')")}')
print(f'lang-switch in nav: {js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')

# Click article
print('\n=== Click article ===')
page_ws.send(json.dumps({'id': 10, 'method': 'Runtime.evaluate',
    'params': {'expression': 'document.querySelector("a.article-title")?.click()', 'returnByValue': True}}))
json.loads(page_ws.recv())

# Poll every second
for i in range(8):
    time.sleep(1)
    path = js("window.location.pathname")
    sw = js("!!document.getElementById('lang-switch')")
    in_nav = js("!!document.querySelector('#nav .menus_items #lang-switch')")
    nav_count = js("document.querySelectorAll('#nav .menus_items > *').length")
    print(f'  +{i+1}s: path={path}, id#lang exists={sw}, in_nav={in_nav}, nav_items={nav_count}')
    if path != '/':
        break

# One more check at the end
print(f'\nFinal nav HTML: {js("document.querySelector(\'#nav .menus_items\')?.innerHTML?.substring(0, 400) || \'NONE\'")}')

page_ws.close()
bws.close()
