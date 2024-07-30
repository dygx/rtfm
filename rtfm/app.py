import csv
import os
import socket
import requests
import subprocess
import json
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from datetime import datetime

app = Flask(__name__)
machines = []
file_path = 'machines.csv'
history_file = 'command_history.json'
default_columns = ['Nom', 'IP', 'Port', 'Description']

def load_csv(file_path):
    machines = []
    if os.path.exists(file_path):
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                machines.append(row)
        print(f"Fichier CSV '{file_path}' chargé automatiquement.")
    else:
        print(f"Aucun fichier CSV trouvé. Un nouveau fichier sera créé lors de la sauvegarde.")
    return machines

def save_csv(file_path, machines):
    if not machines:
        return
    
    fieldnames = machines[0].keys()
    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in machines:
            writer.writerow(row)

def add_to_history(command_type, command, response):
    if not os.path.exists(history_file):
        history = []
    else:
        with open(history_file, 'r') as f:
            history = json.load(f)
    
    history.append({
        'timestamp': datetime.now().isoformat(),
        'type': command_type,
        'command': command,
        'response': response
    })
    
    with open(history_file, 'w') as f:
        json.dump(history, f)

def check_online(ip, port):
    if not port:
        ports = [80, 443]
    else:
        ports = [int(port)]
    
    for p in ports:
        try:
            url = f"http://{ip}:{p}"
            response = requests.get(url, timeout=2)
            return True
        except requests.RequestException:
            pass
    return False

@app.route('/')
def index():
    columns = default_columns if not machines else list(machines[0].keys())
    return render_template('index.html', machines=machines, columns=columns)

@app.route('/add_machine', methods=['POST'])
def add_machine_route():
    machine = request.json
    machines.append(machine)
    save_csv(file_path, machines)
    return jsonify({"success": True, "message": "Machine ajoutée avec succès"})

@app.route('/update_machine', methods=['POST'])
def update_machine_route():
    index = request.json['index']
    updated_machine = request.json['machine']
    machines[index] = updated_machine
    save_csv(file_path, machines)
    return jsonify({"success": True, "message": "Machine mise à jour avec succès"})

@app.route('/delete_machine/<int:index>', methods=['DELETE'])
def delete_machine_route(index):
    del machines[index]
    save_csv(file_path, machines)
    return jsonify({"success": True, "message": "Machine supprimée avec succès"})

@app.route('/upload_csv', methods=['POST'])
def upload_csv_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Aucun fichier n'a été téléchargé"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "Aucun fichier n'a été sélectionné"})
    if file:
        file.save(file_path)
        global machines
        machines = load_csv(file_path)
        return jsonify({"success": True, "message": "Fichier CSV téléchargé et chargé avec succès"})

@app.route('/download_csv')
def download_csv_route():
    return send_file(file_path, as_attachment=True)

@app.route('/send_udp', methods=['POST'])
def send_udp_route():
    message = request.json['message']
    host = request.json['host']
    port = int(request.json['port'])
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(message.encode(), (host, port))
    add_to_history('UDP', f"{host}:{port} - {message}", "Message envoyé")
    return jsonify({"success": True, "message": "Message UDP envoyé"})

@app.route('/send_tcp', methods=['POST'])
def send_tcp_route():
    message = request.json['message']
    host = request.json['host']
    port = int(request.json['port'])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(message.encode())
        response = sock.recv(1024).decode()
    add_to_history('TCP', f"{host}:{port} - {message}", response)
    return jsonify({"success": True, "message": "Message TCP envoyé", "response": response})

@app.route('/send_http', methods=['POST'])
def send_http_route():
    url = request.json['url']
    method = request.json['method']
    data = request.json.get('data')
    try:
        if method.upper() == 'GET':
            response = requests.get(url, timeout=5)
        elif method.upper() == 'POST':
            response = requests.post(url, json=data, timeout=5)
        else:
            return jsonify({"success": False, "message": "Méthode HTTP non supportée"})
        add_to_history('HTTP', f"{method} {url}", response.text)
        return jsonify({"success": True, "message": "Requête HTTP envoyée", "response": response.text})
    except requests.RequestException as e:
        error_message = f"Erreur lors de la requête HTTP: {str(e)}"
        add_to_history('HTTP', f"{method} {url}", error_message)
        return jsonify({"success": False, "message": error_message})

@app.route('/ping_stream')
def ping_stream():
    host = request.args.get('host')
    def generate():
        process = subprocess.Popen(['ping', '-c', '4', host], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.STDOUT,
                                   universal_newlines=True)
        for stdout_line in iter(process.stdout.readline, ""):
            yield f"data: {stdout_line}\n\n"
        process.stdout.close()
        return_code = process.wait()
        if return_code:
            yield f"data: Ping failed. Return code: {return_code}\n\n"
        else:
            yield f"data: Ping completed successfully.\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/check_online', methods=['POST'])
def check_online_route():
    ip = request.json['ip']
    port = request.json.get('port')
    result = check_online(ip, port)
    return jsonify({"success": True, "online": result})

@app.route('/get_history')
def get_history_route():
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            history = json.load(f)
        return jsonify(history)
    else:
        return jsonify([])

@app.route('/download_history')
def download_history_route():
    return send_file(history_file, as_attachment=True)

@app.route('/fill_udp/<int:index>')
def fill_udp(index):
    if 0 <= index < len(machines):
        machine = machines[index]
        return jsonify({
            'host': machine.get('IP', ''),
            'port': machine.get('Port', '5000')
        })
    return jsonify({'error': 'Machine not found'}), 404

@app.route('/fill_tcp/<int:index>')
def fill_tcp(index):
    if 0 <= index < len(machines):
        machine = machines[index]
        return jsonify({
            'host': machine.get('IP', ''),
            'port': machine.get('Port', '5000')
        })
    return jsonify({'error': 'Machine not found'}), 404

@app.route('/fill_http/<int:index>')
def fill_http(index):
    if 0 <= index < len(machines):
        machine = machines[index]
        port = machine.get('Port', '80')
        return jsonify({
            'url': f"http://{machine.get('IP', '')}:{port}"
        })
    return jsonify({'error': 'Machine not found'}), 404


if __name__ == "__main__":
    machines = load_csv(file_path)
    app.run(debug=True)