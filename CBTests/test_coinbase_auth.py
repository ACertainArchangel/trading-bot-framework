#!/usr/bin/env python3
"""
Test script to debug Coinbase Advanced Trade API authentication
"""
import json
import requests
from coinbase import jwt_generator

# Load credentials
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

api_key_name = secrets['coinbase_api_key_name']
api_private_key = secrets['coinbase_api_private_key']

print("API Key Name:", api_key_name)
print("Private Key (first 50 chars):", api_private_key[:50])
print()

# Test JWT generation using official Coinbase SDK
method = "GET"
request_path = "/api/v3/brokerage/accounts"
base_url = "https://api.coinbase.com"

print(f"Request: {method} {request_path}")
print()

# Generate JWT using official SDK method
jwt_uri = jwt_generator.format_jwt_uri(method, request_path)
print(f"JWT URI: {jwt_uri}")

token = jwt_generator.build_rest_jwt(jwt_uri, api_key_name, api_private_key)
print(f"JWT Token (first 100 chars): {token[:100]}")
print()

print("JWT Token (first 100 chars):", token[:100])
print()

# Make request
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

print("Making request to:", f"{base_url}{request_path}")
print()

response = requests.get(f"{base_url}{request_path}", headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text[:500]}")

if response.status_code == 200:
    print("\n✅ SUCCESS! Authentication working!")
    accounts = response.json()
    print(f"Found {len(accounts.get('accounts', []))} accounts")
else:
    print("\n❌ FAILED!")
    print("Full response:", response.text)
