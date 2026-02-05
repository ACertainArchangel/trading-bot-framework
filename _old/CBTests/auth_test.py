from coinbase import jwt_generator
import requests

api_key_name = "organizations/12ca2c06-851f-4dc2-a60a-3da41a85b53e/apiKeys/2fc439d7-c773-446b-90b3-270009067642"
api_private_key = "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIGmJ+xqMhFcRn3KeCbzFrDbw++ChQJTN9qbkDTLOvgwBoAoGCCqGSM49\nAwEHoUQDQgAEzuRvBUMFfcCes98XXT07I+86DyOsLCIB1wl99/B09Oq5PHUc0HWC\n8lbpjSTUje2F/PbdVA8E8WIBRasUqCrDLQ==\n-----END EC PRIVATE KEY-----\n"

method = "GET"
request_path = "/api/v3/brokerage/accounts"
base_url = "https://api.coinbase.com"

jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
token = jwt_generator.build_rest_jwt(jwt_uri, api_key_name, api_private_key)

headers = {"Authorization": f"Bearer {token}"}
r = requests.get(base_url + request_path, headers=headers)

print(r.status_code)
import json
data = r.json()
print(json.dumps(data, indent=2))