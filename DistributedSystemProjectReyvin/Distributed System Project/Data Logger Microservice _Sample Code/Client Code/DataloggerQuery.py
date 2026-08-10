import requests
import sys
import json

API_URL = "http://103.231.240.136:31701"

def query_logs(node_name=None, severity=None):
    print("--- Sending Query to API Gateway ---")
    
    # 1. Build the query parameters dynamically
    params = {}
    if node_name:
        params['node_name'] = node_name
    if severity:
        params['severity'] = severity

    # 2. Execute the HTTP GET request
    try:
        response = requests.get(f"{API_URL}/logs", params=params)
        response.raise_for_status() # Check for HTTP errors
        
        data = response.json()
        print(f"\n[+] Query Successful. Found {data.get('count')} matching records.\n")
        
        # 3. Format and display the output
        for entry in data.get('results', []):
            print(f"[{entry['timestamp']}] {entry['node_name']} | {entry['severity']} | {entry['message']}")
            
    except requests.exceptions.RequestException as e:
        print(f"[!] API Request Failed: {e}")

def get_registered_nodes():
    print("\n--- Requesting Active Node Registry ---")
    try:
        response = requests.get(f"{API_URL}/nodes")
        response.raise_for_status()
        
        data = response.json()
        print(json.dumps(data, indent=4))
        
    except requests.exceptions.RequestException as e:
        print(f"[!] API Request Failed: {e}")

if __name__ == "__main__":
    # Example execution: fetch all ERROR logs
    print("Example 1: Fetching all ERROR severity logs...")
    query_logs(severity="INFO")
    
    # Example execution: fetch logs from a specific node
    print("\nExample 2: Fetching logs from 'Node-Alpha'...")
    query_logs(node_name="WKS1")
    
    # Example execution: view all registered nodes
    get_registered_nodes()
