from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import platform
import re
import socket
import csv
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'votre_clé_secrète_ici'  # Nécessaire pour utiliser les sessions

def ping(ip):
    operating_system = platform.system().lower()
    if operating_system == "windows":
        command = ["ping", "-n", "1", "-w", "1000", ip]
    else:  # Pour Linux et MacOS
        command = ["ping", "-c", "1", "-W", "1", ip]
    try:
        output = subprocess.check_output(command, universal_newlines=True, stderr=subprocess.STDOUT)
        return True, output
    except subprocess.CalledProcessError as e:
        return False, e.output

def send_tcp_request(host, port, message):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, int(port)))
            s.sendall(message.encode())
            response = s.recv(1024)
        return True, response.decode()
    except Exception as e:
        return False, str(e)

def read_csv(file):
    content = file.read().decode('utf-8')
    csv_reader = csv.reader(io.StringIO(content), delimiter=';')  # Utilisez le point-virgule comme délimiteur
    headers = next(csv_reader)
    rows = list(csv_reader)
    return headers, rows

@app.route('/')
def index():
    csv_data = session.get('csv_data', {})
    headers = csv_data.get('headers', [])
    rows = csv_data.get('rows', [])
    ip_column = csv_data.get('ip_column', -1)
    return render_template('index.html', headers=headers, rows=rows, ip_column=ip_column)

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier n\'a été uploadé'})
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier n\'a été sélectionné'})
    
    if file and file.filename.endswith('.csv'):
        headers, rows = read_csv(file)
        ip_column = next((i for i, header in enumerate(headers) if 'ip' in header.lower()), None)
        
        csv_data = {
            'headers': headers,
            'rows': rows,
            'ip_column': ip_column
        }
        session['csv_data'] = csv_data
        return redirect(url_for('index'))
    else:
        return jsonify({'error': 'Le fichier doit être au format CSV'})

@app.route('/ping', methods=['POST'])
def ping_route():
    ips = request.form.get('ips', '')
    results = []
    if ips:
        for ip in ips.split(','):
            ip = ip.strip()
            is_online, output = ping(ip)
            results.append({'ip': ip, 'status': 'en ligne' if is_online else 'hors ligne', 'output': output})
    else:
        results.append({'ip': 'Aucune adresse IP fournie', 'status': 'N/A', 'output': ''})
    return jsonify(results)

@app.route('/tcp', methods=['POST'])
def tcp_route():
    host = request.form.get('host', '')
    port = request.form.get('port', '')
    message = request.form.get('message', '')
    
    if host and port and message:
        success, result = send_tcp_request(host, port, message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tcp_history = session.get('tcp_history', [])
        tcp_history.append({
            'timestamp': timestamp,
            'host': host,
            'port': port,
            'message': message,
            'response': result,
            'success': success
        })
        session['tcp_history'] = tcp_history
        session.modified = True
        return jsonify({'result': result, 'history': tcp_history})
    else:
        return jsonify({'error': "Veuillez fournir l'hôte, le port et le message."})

if __name__ == '__main__':
    app.run(debug=True)