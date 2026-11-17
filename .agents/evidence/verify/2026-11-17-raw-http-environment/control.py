import http.server,socket,threading,json,http.client,urllib.request
class H(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'ok')
 def do_POST(self):
  self.send_response(413);self.send_header('Content-Length','0');self.end_headers()
s=http.server.ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=s.serve_forever,daemon=True).start()
result={}
try:
 port=s.server_port
 for label,request in [('get',b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'),('header-only-post',b'POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: 999999999\r\nConnection: close\r\n\r\n')]:
  with socket.create_connection(('127.0.0.1',port),timeout=2) as c:
   c.settimeout(2);c.sendall(request)
   try:result['raw-'+label]=c.recv(4096).decode(errors='replace').split('\r\n')[0]
   except TimeoutError:result['raw-'+label]='TimeoutError'
 c=http.client.HTTPConnection('127.0.0.1',port,timeout=2);c.request('GET','/');r=c.getresponse();result['httpclient-get']={'status':r.status,'body':r.read().decode()};c.close()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));r=opener.open(f'http://127.0.0.1:{port}/',timeout=2);result['urllib-no-proxy-get']={'status':r.status,'body':r.read().decode()}
finally:s.shutdown();s.server_close()
print(json.dumps(result,indent=2))
