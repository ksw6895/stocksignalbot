#!/usr/bin/env python3
"""
Test script to verify proxy configuration
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_proxy():
    proxy_url = os.getenv('PROXY_URL')
    
    print("=== Proxy Configuration Test ===")
    print(f"Proxy URL: {proxy_url if proxy_url else 'Not configured'}")
    
    if not proxy_url:
        print("\nNo proxy configured. Set PROXY_URL in .env file.")
        return
    
    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }
    
    # Test 1: Check current IP without proxy
    print("\n1. Testing without proxy:")
    try:
        resp = requests.get('https://api.ipify.org?format=json', timeout=10)
        print(f"   Original IP: {resp.json()['ip']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: Check current IP with proxy
    print("\n2. Testing with proxy:")
    try:
        resp = requests.get('https://api.ipify.org?format=json', proxies=proxies, timeout=10)
        print(f"   Proxy IP: {resp.json()['ip']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Test Binance API with proxy
    print("\n3. Testing Binance API with proxy:")
    try:
        resp = requests.get('https://api.binance.com/api/v3/ping', proxies=proxies, timeout=10)
        print(f"   Binance ping status: {resp.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 4: Test CoinMarketCap API without proxy
    print("\n4. Testing CoinMarketCap API without proxy:")
    cmc_key = os.getenv('COINMARKETCAP_API_KEY')
    if cmc_key:
        headers = {'X-CMC_PRO_API_KEY': cmc_key}
        try:
            resp = requests.get(
                'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest',
                params={'limit': 1},
                headers=headers,
                timeout=10
            )
            print(f"   CMC API status: {resp.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("   CMC API key not configured")

if __name__ == "__main__":
    test_proxy()