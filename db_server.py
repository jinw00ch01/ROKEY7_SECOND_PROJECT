import sqlite3
import json
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

class NutDBHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/api/nut':
            query = urllib.parse.parse_qs(parsed_path.query)
            nut_name = query.get('name', [None])[0]
            
            if not nut_name:
                self.send_error_response(400, "Missing 'name' parameter")
                return
                
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM Nut_Details WHERE nut_name = ?', (nut_name,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    data = dict(row)
                    self.send_success_response(data)
                else:
                    self.send_error_response(404, "Nut not found")
            except Exception as e:
                self.send_error_response(500, str(e))
        else:
            self.send_error_response(404, "Not Found")

    def send_success_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode('utf-8'))

def run(server_class=HTTPServer, handler_class=NutDBHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Starting DB server on port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    run()
