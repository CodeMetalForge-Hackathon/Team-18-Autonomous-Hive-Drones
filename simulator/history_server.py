#!/usr/bin/env python3
"""Read-only history sidecar for installing replay while the mission server is busy.
New launches of server.py serve these routes directly; no sidecar is then required.
"""
import json, pathlib, shutil
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import replay
from runtime import find_node, node_script_path
ROOT=pathlib.Path(__file__).resolve().parent
NODE=find_node()
WORKER=node_script_path(ROOT/'sortie.mjs',NODE)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        try:
            route=urlparse(self.path);query=parse_qs(route.query);root=ROOT/'.runs'
            if route.path=='/api/history':
                states=sorted(root.glob('*/observer-state.json'),key=lambda p:p.stat().st_mtime)
                current=replay.optional(states[-1],{}).get('run_id') if states else None
                data=replay.history(root,current)
            elif route.path=='/api/replay':data=replay.get_replay(root,query.get('run',[''])[0],int(query.get('sortie',['0'])[0]),NODE,ROOT/'sortie.mjs',WORKER)
            elif route.path=='/api/sortie-report':data=replay.report(replay.run_folder(root,query.get('run',[''])[0]),int(query.get('sortie',['0'])[0]))
            else:raise ValueError('Unknown read-only history route')
            status=200
        except (ValueError,OSError,KeyError) as e:data={'error':str(e)};status=400
        encoded=json.dumps(data,allow_nan=False).encode();self.send_response(status);origin=self.headers.get('Origin')
        if origin in ('http://localhost:8765','http://127.0.0.1:8765'):self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
if __name__=='__main__':
    print('Read-only replay service: http://localhost:8766',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
