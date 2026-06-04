import requests, json, time, websocket

targets = requests.get('http://127.0.0.1:9222/json').json()
page_ws_url = None
for t in targets:
    if 'cdp.autify.cc' in t.get('url', ''):
        page_ws_url = t['webSocketDebuggerUrl']
        break

if not page_ws_url:
    # Create new page
    import websocket as ws_mod
    WS_URL = 'ws://127.0.0.1:9222/devtools/browser/77f5343f-104e-4510-bf90-847aa720410c'
    bws = ws_mod.create_connection(WS_URL)
    bws.send(json.dumps({'id': 1, 'method': 'Target.createTarget', 'params': {'url': 'https://cdp.autify.cc/'}}))
    r = json.loads(bws.recv())
    target_id = r['result']['targetId']
    time.sleep(5)
    targets = requests.get('http://127.0.0.1:9222/json').json()
    for t in targets:
        if t['id'] == target_id:
            page_ws_url = t['webSocketDebuggerUrl']
            break
    bws.close()

page_ws = websocket.create_connection(page_ws_url)
time.sleep(2)

def eval_js(expr):
    page_ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                             'params': {'expression': expr, 'returnByValue': True}}))
    r = json.loads(page_ws.recv())
    return r.get('result', {}).get('result', {}).get('value', str(r))

print('=== ZH Homepage ===')
print(f'switch in nav: {eval_js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')
print(f'switch in body: {eval_js("!!document.querySelector(\'body > #lang-switch\')")}')

# Click first article link to navigate via PJAX
print('\n=== Clicking article link (PJAX navigation) ===')
links = eval_js('document.querySelectorAll(".recent-post-item a.article-title")')
print(f'article links found: {links}')

result = page_ws.send(json.dumps({'id': 2, 'method': 'Runtime.evaluate',
    'params': {'expression': 'document.querySelector(".recent-post-item a.article-title")?.click()', 'returnByValue': True}}))
json.loads(page_ws.recv())
time.sleep(5)

print(f'\n=== After navigation ===')
print(f'pathname: {eval_js("window.location.pathname")}')
print(f'switch in nav: {eval_js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')
print(f'switch in body: {eval_js("!!document.querySelector(\'body > #lang-switch\')")}')
print(f'readyState: {eval_js("document.readyState")}')

page_ws.close()
