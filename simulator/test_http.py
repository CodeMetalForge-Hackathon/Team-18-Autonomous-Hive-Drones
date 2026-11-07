"""Local HTTP boundaries; never launches Claude or a rover sortie."""
import http.client, threading, unittest
from http.server import ThreadingHTTPServer
from server import Handler
class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.port=cls.server.server_port
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,method='GET',host=None,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);headers={'Host':host or f'localhost:{self.port}'}
        if origin:headers['Origin']=origin
        body=b'{}' if method=='POST' else None
        c.request(method,path,body=body,headers=headers);r=c.getresponse();status=r.status;r.read();c.close();return status
    def test_local_page_and_status(self):
        self.assertEqual(self.request('/'),200);self.assertEqual(self.request('/api/status'),200)
    def test_unexpected_host_rejected_for_reads_and_controls(self):
        self.assertEqual(self.request('/api/status',host=f'other.example:{self.port}'),403);self.assertEqual(self.request('/api/start','POST',host=f'other.example:{self.port}'),403)
    def test_cross_origin_control_rejected(self):self.assertEqual(self.request('/api/start','POST',origin='https://other.example'),403)
    def test_private_files_and_encoded_paths_not_served(self):
        for path in ('/.runs/example/observer-state.json','/%2eruns/example/observer-state.json','/server.py','/runtime.py','/.env'):
            self.assertEqual(self.request(path),404)
            self.assertEqual(self.request(path,'HEAD'),404)
    def test_static_head_and_notices(self):
        self.assertEqual(self.request('/index.html','HEAD'),200);self.assertEqual(self.request('/assets/M5STACK-LICENSE.txt'),200)
if __name__=='__main__':unittest.main()
