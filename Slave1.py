import socket
import json
import hashlib
import base64
from multiprocessing import Pool, set_start_method, cpu_count

# ── Settings ────────────────────────────────────────────
MASTER_HOST       = "INDSÆT IP"  # change to master's IP if on separate machine
REGISTRATION_PORT = 9000
# ────────────────────────────────────────────────────────

def get_my_ip():
    # trick: connect to any external IP to find our own IP
    # no data is actually sent
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # google's DNS, nothing is sent
        return s.getsockname()[0]
        
passwords_to_crack = {}  # filled by init_worker in each process
        
# --- Find a free port automatically ---
def find_free_port(start=9001):
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError("No free ports found!")

# --- Tell master which port we are on ---
def register_with_master(my_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((MASTER_HOST, REGISTRATION_PORT))
            s.sendall(json.dumps({
                "host": SLAVE_HOST, 
                "port": my_port,
                "cores": cpu_count()  # ← send our core count
            }).encode('utf-8'))
        print(f"Registered with master — {cpu_count()} cores available")

# --- Called once per worker process to set up the password dict ---
def init_worker(passwords):
    global passwords_to_crack
    passwords_to_crack = passwords

# --- Hash a word and check if it matches any password ---
def check_password(word):
    encrypted = hashlib.sha1(word.encode('latin-1', errors='ignore')).digest()
    if encrypted in passwords_to_crack:
        return [(username, word) for username in passwords_to_crack[encrypted]]
    return []

# --- Generate all variations of a word and check each one ---
def process_word(word):
    results = []

    # Base variations
    variations = [
        word,
        word.upper(),                                                    # SECRET
        word.capitalize(),                                               # Secret
        word[::-1],                                                      # terces
        word[::-1].capitalize(),                                         # Terces
        word + word,                                                     # secretsecret
        word.capitalize() + word.capitalize(),                           # SecretSecret
        word[:-1] + word[-1].upper() if word else word,                  # secreT
        word.capitalize()[:-1] + word[-1].upper() if word else word,     # SecreT
    ]

    # Capitalize each letter position individually (catches HappY, ProgRaming etc)
    for i in range(len(word)):
        variations.append(word[:i] + word[i].upper() + word[i+1:])

    # Remove duplicate variations for speed
    variations = list(set(variations))

    for v in variations:
        results.extend(check_password(v))

        # Add 1-2 digit prefix/suffix (secret1, 01secret etc)
        for i in range(100):
            results.extend(check_password(v + str(i)))
            results.extend(check_password(str(i) + v))
            if i < 10:
                results.extend(check_password(v + f"0{i}"))
                results.extend(check_password(f"0{i}" + v))

        # Wrap with single digits (1secret3 etc)
        for i in range(10):
            for j in range(10):
                results.extend(check_password(str(i) + v + str(j)))

        # Leading caps (SEcret, SECret etc)
        for i in range(1, len(v) + 1):
            results.extend(check_password(v[:i].upper() + v[i:]))

        # L33t speak substitutions
        if 'a' in v: results.extend(check_password(v.replace('a', '@')))
        if 'o' in v: results.extend(check_password(v.replace('o', '0')))
        if 'i' in v: results.extend(check_password(v.replace('i', '1')))
        if 'e' in v: results.extend(check_password(v.replace('e', '3')))
        if 's' in v: results.extend(check_password(v.replace('s', '$')))

    return results

# --- Receive a job from master, crack it using all CPU cores ---
def handle_job(job_data):
    words = list(set(job_data["words"]))  # remove duplicates

    # Convert base64 password hashes to raw bytes for fast comparison
    passwords_bytes = {
        base64.b64decode(b64_hash): usernames
        for b64_hash, usernames in job_data["passwords"].items()
    }

    print(f"Cracking {len(words)} words on {cpu_count()} cores...")
    results = []
    with Pool(initializer=init_worker, initargs=(passwords_bytes,)) as pool:
        for result_list in pool.imap_unordered(process_word, words, chunksize=50):
            if result_list:
                results.extend(result_list)
    return results

# --- Helper: receive exact number of bytes ---
def recv_all(conn, length):
    data = b''
    while len(data) < length:
        data += conn.recv(min(4096, length - len(data)))
    return data

if __name__ == '__main__':
    set_start_method('spawn') # ÆNDRE TIL FORK HVIS LINUX

    PORT = find_free_port()
    SLAVE_HOST = get_my_ip()
    print(f"Slave starting on port {PORT}, my IP is {SLAVE_HOST}")

    try:
        register_with_master(PORT)
    except ConnectionRefusedError:
        print(f"Could not reach master — is Master.py running?")
        exit(1)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', PORT))
        server.listen(5)
        print(f"Ready and listening on port {PORT}...")

        while True:
            conn, _ = server.accept()
            with conn:
                data_len = int.from_bytes(recv_all(conn, 8), 'big')
                job = json.loads(recv_all(conn, data_len).decode('utf-8'))
                results = handle_job(job)
                print(f"Done — found {len(results)} matches")
                result_data = json.dumps(results).encode('utf-8')
                conn.sendall(len(result_data).to_bytes(8, 'big'))
                conn.sendall(result_data)
import socket
import json
import hashlib
import base64
from multiprocessing import Pool, set_start_method, cpu_count

# ── Settings ────────────────────────────────────────────
MASTER_HOST       = "127.0.0.1"  # change to master's IP if on separate machine
REGISTRATION_PORT = 9000
# ────────────────────────────────────────────────────────

def get_my_ip():
    # trick: connect to any external IP to find our own IP
    # no data is actually sent
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # google's DNS, nothing is sent
        return s.getsockname()[0]
        
passwords_to_crack = {}  # filled by init_worker in each process
        
# --- Find a free port automatically ---
def find_free_port(start=9001):
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError("No free ports found!")

# --- Tell master which port we are on ---
def register_with_master(my_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((MASTER_HOST, REGISTRATION_PORT))
            s.sendall(json.dumps({
                "host": SLAVE_HOST, 
                "port": my_port,
                "cores": cpu_count()  # ← send our core count
            }).encode('utf-8'))
        print(f"Registered with master — {cpu_count()} cores available")

# --- Called once per worker process to set up the password dict ---
def init_worker(passwords):
    global passwords_to_crack
    passwords_to_crack = passwords

# --- Hash a word and check if it matches any password ---
def check_password(word):
    encrypted = hashlib.sha1(word.encode('latin-1', errors='ignore')).digest()
    if encrypted in passwords_to_crack:
        return [(username, word) for username in passwords_to_crack[encrypted]]
    return []

# --- Generate all variations of a word and check each one ---
def process_word(word):
    results = []

    # Base variations
    variations = [
        word,
        word.upper(),                                                    # SECRET
        word.capitalize(),                                               # Secret
        word[::-1],                                                      # terces
        word[::-1].capitalize(),                                         # Terces
        word + word,                                                     # secretsecret
        word.capitalize() + word.capitalize(),                           # SecretSecret
        word[:-1] + word[-1].upper() if word else word,                  # secreT
        word.capitalize()[:-1] + word[-1].upper() if word else word,     # SecreT
    ]

    # Capitalize each letter position individually (catches HappY, ProgRaming etc)
    for i in range(len(word)):
        variations.append(word[:i] + word[i].upper() + word[i+1:])

    # Remove duplicate variations for speed
    variations = list(set(variations))

    for v in variations:
        results.extend(check_password(v))

        # Add 1-2 digit prefix/suffix (secret1, 01secret etc)
        for i in range(100):
            results.extend(check_password(v + str(i)))
            results.extend(check_password(str(i) + v))
            if i < 10:
                results.extend(check_password(v + f"0{i}"))
                results.extend(check_password(f"0{i}" + v))

        # Wrap with single digits (1secret3 etc)
        for i in range(10):
            for j in range(10):
                results.extend(check_password(str(i) + v + str(j)))

        # Leading caps (SEcret, SECret etc)
        for i in range(1, len(v) + 1):
            results.extend(check_password(v[:i].upper() + v[i:]))

        # L33t speak substitutions
        if 'a' in v: results.extend(check_password(v.replace('a', '@')))
        if 'o' in v: results.extend(check_password(v.replace('o', '0')))
        if 'i' in v: results.extend(check_password(v.replace('i', '1')))
        if 'e' in v: results.extend(check_password(v.replace('e', '3')))
        if 's' in v: results.extend(check_password(v.replace('s', '$')))

    return results

# --- Receive a job from master, crack it using all CPU cores ---
def handle_job(job_data):
    words = list(set(job_data["words"]))  # remove duplicates

    # Convert base64 password hashes to raw bytes for fast comparison
    passwords_bytes = {
        base64.b64decode(b64_hash): usernames
        for b64_hash, usernames in job_data["passwords"].items()
    }

    print(f"Cracking {len(words)} words on {cpu_count()} cores...")
    results = []
    with Pool(initializer=init_worker, initargs=(passwords_bytes,)) as pool:
        for result_list in pool.imap_unordered(process_word, words, chunksize=50):
            if result_list:
                results.extend(result_list)
    return results

# --- Helper: receive exact number of bytes ---
def recv_all(conn, length):
    data = b''
    while len(data) < length:
        data += conn.recv(min(4096, length - len(data)))
    return data

if __name__ == '__main__':
    set_start_method('spawn')

    PORT = find_free_port()
    SLAVE_HOST = get_my_ip()
    print(f"Slave starting on port {PORT}, my IP is {SLAVE_HOST}")

    try:
        register_with_master(PORT)
    except ConnectionRefusedError:
        print(f"Could not reach master — is Master.py running?")
        exit(1)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', PORT))
        server.listen(5)
        print(f"Ready and listening on port {PORT}...")

        while True:
            conn, _ = server.accept()
            with conn:
                data_len = int.from_bytes(recv_all(conn, 8), 'big')
                job = json.loads(recv_all(conn, data_len).decode('utf-8'))
                results = handle_job(job)
                print(f"Done — found {len(results)} matches")
                result_data = json.dumps(results).encode('utf-8')
                conn.sendall(len(result_data).to_bytes(8, 'big'))
                conn.sendall(result_data)
