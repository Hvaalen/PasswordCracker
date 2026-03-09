import socket
import json
import threading
import time

# ── Settings ────────────────────────────────────────────
REGISTRATION_PORT = 9000  # slaves connect here to register
WAIT_FOR_SLAVES   = 15     # seconds to wait before starting
DICTIONARY_FILES  = ['webster-dictionary.txt', 'danish_words.txt']
PASSWORD_FILE     = 'passwords.txt'
# ────────────────────────────────────────────────────────

# --- Step 1: Load passwords from file into a dict {hash: [usernames]} ---
def load_passwords():
    passwords = {}
    with open(PASSWORD_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if ":" in line:
                username, password_hash = line.split(":", 1)
                if password_hash not in passwords:
                    passwords[password_hash] = []
                passwords[password_hash].append(username)
    return passwords

# --- Step 2: Load all words from dictionaries, remove duplicates ---
def load_words():
    words = []
    for filename in DICTIONARY_FILES:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                words += [line.strip().split()[0] for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: {filename} not found, skipping")
    return list(set(words))  # remove duplicates across dictionaries

# --- Step 3: Send a chunk of words + passwords to a slave, get results back ---
def send_job_to_slave(slave_addr, words_chunk, passwords):
    host, port = slave_addr
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))

            # Send job as JSON
            job = json.dumps({"passwords": passwords, "words": words_chunk}).encode('utf-8')
            s.sendall(len(job).to_bytes(8, 'big'))
            s.sendall(job)

            # Receive results
            result_len = int.from_bytes(recv_all(s, 8), 'big')
            return json.loads(recv_all(s, result_len).decode('utf-8'))
    except ConnectionRefusedError:
        print(f"Slave {host}:{port} not responding!")
        return []

# --- Helper: receive exact number of bytes from socket ---
def recv_all(conn, length):
    data = b''
    while len(data) < length:
        data += conn.recv(min(4096, length - len(data)))
    return data

# --- Step 4: Listen for slaves registering themselves ---
registered_slaves = []
stop_registration = threading.Event()

def registration_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", REGISTRATION_PORT))
        s.listen(10)
        s.settimeout(1)
        print(f"Waiting for slaves on port {REGISTRATION_PORT}...")
        while not stop_registration.is_set():
            try:
                conn, _ = s.accept()
                with conn:
                    info = json.loads(conn.recv(1024).decode('utf-8'))
                    registered_slaves.append((info['host'], info['port'], info['cores']))
                    print(f"  Slave registered: {info['host']}:{info['port']} ({len(registered_slaves)} total)")
            except socket.timeout:
                continue

if __name__ == '__main__':
    # Start registration server, wait for slaves to connect
    threading.Thread(target=registration_server, daemon=True).start()
    print(f"Waiting {WAIT_FOR_SLAVES}s for slaves to register...")
    time.sleep(WAIT_FOR_SLAVES)
    stop_registration.set()

    if not registered_slaves:
        print("No slaves registered! Start Slave.py first.")
        exit(1)

    # Load data
    passwords = load_passwords()
    words = load_words()
    print(f"\n{len(registered_slaves)} slave(s) ready | {len(words)} unique words loaded")

    # Split dictionary evenly across slaves
    total_cores = sum(s[2] for s in registered_slaves)
    chunks = []
    start = 0
    for slave in registered_slaves:
        proportion = slave[2] / total_cores
        count = int(len(words) * proportion)
        chunks.append(words[start:start + count])
        start += count
    chunks[-1].extend(words[start:])  # add any leftover words to last chunk

    # Send chunks to all slaves in parallel using threads
    all_results = []
    lock = threading.Lock()

    def crack_on_slave(slave_addr, chunk):
        print(f"Sending {len(chunk)} words to {slave_addr[0]}:{slave_addr[1]}")
        results = send_job_to_slave(slave_addr, chunk, passwords)
        with lock:
            all_results.extend(results)
        print(f"Slave :{slave_addr[1]} done — found {len(results)} matches")

    threads = [threading.Thread(target=crack_on_slave, args=(slave[:2], chunks[i]))
                           for i, slave in enumerate(registered_slaves)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Print results, removing duplicates
    print("\n--- RESULTS ---")
    seen = set()
    for username, password in all_results:
        if (username, password) not in seen:
            seen.add((username, password))
            print(f"FOUND! User: {username}, Password: {password}")
    print(f"\nTotal found: {len(seen)}")
