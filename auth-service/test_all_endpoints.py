#!/usr/bin/env python3
"""
🧪 Complete Test Suite for Auth Service API
Tests all 6 endpoints with detailed output
"""

import httpx
import json
import os
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api/v1"
INTERNAL_SERVICE_KEY = os.getenv("INTERNAL_SERVICE_KEY", "change-me-in-production")

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(text):
    """Print a formatted header"""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text.center(70)}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    """Print error message"""
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    """Print info message"""
    print(f"{YELLOW}ℹ️  {text}{RESET}")


def print_request(method, endpoint, data=None):
    """Print request details"""
    print(f"{BOLD}{method} {endpoint}{RESET}")
    if data:
        print(f"Body: {json.dumps(data, indent=2)}")
    print()


def print_response(status_code, data):
    """Print response details"""
    if 200 <= status_code < 300:
        print(f"{GREEN}Status: {status_code}{RESET}")
    else:
        print(f"{RED}Status: {status_code}{RESET}")
    
    try:
        print(f"Response:\n{json.dumps(data, indent=2)}\n")
    except:
        print(f"Response:\n{data}\n")


async def test_health_check():
    """Test 1: Health Check"""
    print_header("Test 1: Health Check")
    
    endpoint = f"{BASE_URL}/health"
    print_request("GET", endpoint)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint)
        print_response(response.status_code, response.json())
        
        if response.status_code == 200:
            print_success("Health check passed!")
            return True
        else:
            print_error("Health check failed!")
            return False


async def test_register():
    """Test 2: Register User"""
    print_header("Test 2: Register User (POST /auth/register)")
    
    endpoint = f"{API_URL}/auth/register"
    payload = {
        "email": f"andre{datetime.now().timestamp()}@example.com",
        "password": "SenhaForte123",
        "full_name": "André Alexandre",
        "role": "fan"
    }
    
    # Store email for later tests
    test_register.email = payload["email"]
    test_register.password = payload["password"]
    
    print_request("POST", endpoint, payload)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 201:
            print_success("User registered successfully!")
            test_register.user_id = data.get("id")
            return True
        else:
            print_error(f"Registration failed: {data.get('detail', 'Unknown error')}")
            return False


async def test_login():
    """Test 3: Login"""
    print_header("Test 3: Login (POST /auth/login)")
    
    endpoint = f"{API_URL}/auth/login"
    payload = {
        "email": test_register.email,
        "password": test_register.password
    }
    
    print_request("POST", endpoint, payload)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 200:
            print_success("Login successful!")
            test_login.access_token = data.get("access_token")
            test_login.refresh_token = data.get("refresh_token")
            
            # Decode and show token info
            print_info("Token Type: Bearer")
            print_info(f"Access Token (short): {data.get('access_token')[:50]}...")
            return True
        else:
            print_error(f"Login failed: {data.get('detail', 'Unknown error')}")
            return False


async def test_get_profile():
    """Test 4: Get Current User Profile"""
    print_header("Test 4: Get Current User Profile (GET /auth/me)")
    
    endpoint = f"{API_URL}/auth/me"
    headers = {"Authorization": f"Bearer {test_login.access_token}"}
    
    print(f"{BOLD}GET {endpoint}{RESET}")
    print(f"Headers: Authorization: Bearer <token>\n")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint, headers=headers)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 200:
            print_success("Profile retrieved successfully!")
            print_info(f"User ID: {data.get('id')}")
            print_info(f"Email: {data.get('email')}")
            print_info(f"Role: {data.get('role')}")
            return True
        else:
            print_error(f"Failed to get profile: {data.get('detail', 'Unknown error')}")
            return False


async def test_refresh_token():
    """Test 5: Refresh Token"""
    print_header("Test 5: Refresh Token (POST /auth/refresh)")
    
    endpoint = f"{API_URL}/auth/refresh"
    payload = {"refresh_token": test_login.refresh_token}
    
    print_request("POST", endpoint, payload)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 200:
            print_success("Token refreshed successfully!")
            # Store new tokens
            test_login.access_token = data.get("access_token")
            test_login.refresh_token = data.get("refresh_token")
            print_info(f"New Access Token (short): {data.get('access_token')[:50]}...")
            return True
        else:
            print_error(f"Token refresh failed: {data.get('detail', 'Unknown error')}")
            return False


async def test_verify_token():
    """Test 6: Verify Token (Internal Service Use)"""
    print_header("Test 6: Verify Token (POST /auth/verify) - For Other Services")
    
    endpoint = f"{API_URL}/auth/verify"
    payload = {"token": test_login.access_token}
    headers = {"X-Service-Auth": INTERNAL_SERVICE_KEY}
    
    print_request("POST", endpoint, payload)
    print_info("This endpoint is used by Inventory and Payment services")
    print_info("to validate tokens without parsing them locally\n")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 200:
            if data.get("valid"):
                print_success("Token is valid!")
                print_info(f"User ID: {data.get('user_id')}")
                print_info(f"Email: {data.get('email')}")
                print_info(f"Role: {data.get('role')}")
                return True
            else:
                print_error("Token is invalid!")
                return False
        else:
            print_error(f"Token verification failed: {data.get('detail', 'Unknown error')}")
            return False


async def test_logout():
    """Test 7: Logout"""
    print_header("Test 7: Logout (POST /auth/logout)")
    
    endpoint = f"{API_URL}/auth/logout"
    headers = {"Authorization": f"Bearer {test_login.access_token}"}
    
    print(f"{BOLD}POST {endpoint}{RESET}")
    print(f"Headers: Authorization: Bearer <token>\n")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, headers=headers)
        print(f"{GREEN}Status: {response.status_code}{RESET}\n")
        
        if response.status_code == 204:
            print_success("Logout successful! (No Content response)")
            return True
        else:
            print_error(f"Logout failed with status {response.status_code}")
            return False


async def test_invalid_token():
    """Test 8: Invalid Token Handling"""
    print_header("Test 8: Error Handling - Invalid Token")
    
    endpoint = f"{API_URL}/auth/me"
    headers = {"Authorization": "Bearer invalid.token.here"}
    
    print(f"{BOLD}GET {endpoint}{RESET}")
    print_info("Testing with deliberately invalid token\n")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint, headers=headers)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 401:
            print_success("Invalid token properly rejected!")
            return True
        else:
            print_error("Token validation failed")
            return False


async def test_duplicate_registration():
    """Test 9: Duplicate Email Handling"""
    print_header("Test 9: Error Handling - Duplicate Email")
    
    endpoint = f"{API_URL}/auth/register"
    payload = {
        "email": test_register.email,  # Same email as before
        "password": "DifferentPassword123",
        "full_name": "Another Person",
        "role": "promoter"
    }
    
    print_request("POST", endpoint, payload)
    print_info("Testing with email that already exists\n")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload)
        data = response.json()
        print_response(response.status_code, data)
        
        if response.status_code == 409:
            print_success("Duplicate email properly rejected!")
            return True
        else:
            print_error("Duplicate email handling failed")
            return False


async def run_all_tests():
    """Run all tests"""
    print(f"\n{BOLD}{YELLOW}")
    print("╔" + "═" * 68 + "╗")
    print("║" + " 🔐 AUTH SERVICE - COMPLETE API TEST SUITE ".center(68) + "║")
    print("║" + f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print(RESET)
    
    results = {}
    
    try:
        # Check service is running
        print_info("Checking if service is available...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{BASE_URL}/health", timeout=5)
                if response.status_code == 200:
                    print_success(f"Service is running at {BASE_URL}\n")
                else:
                    print_error(f"Service is not responding properly")
                    return
            except:
                print_error(f"Cannot connect to {BASE_URL}")
                print_info("Make sure the service is running:")
                print_info("  docker compose up -d")
                print_info("or")
                print_info("  uvicorn app.main:app --reload")
                return
        
        # Run tests in sequence
        results["1. Health Check"] = await test_health_check()
        results["2. Register User"] = await test_register()
        results["3. Login"] = await test_login()
        results["4. Get Profile"] = await test_get_profile()
        results["5. Refresh Token"] = await test_refresh_token()
        results["6. Verify Token"] = await test_verify_token()
        results["7. Logout"] = await test_logout()
        results["8. Invalid Token"] = await test_invalid_token()
        results["9. Duplicate Email"] = await test_duplicate_registration()
        
    except Exception as e:
        print_error(f"Fatal error: {str(e)}")
        return
    
    # Print summary
    print_header("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"{test_name}: {status}")
    
    print(f"\n{YELLOW}Total: {passed}/{total} tests passed{RESET}\n")
    
    if passed == total:
        print(f"{GREEN}{BOLD}🎉 ALL TESTS PASSED! 🎉{RESET}\n")
    else:
        print(f"{RED}{BOLD}⚠️  {total - passed} test(s) failed{RESET}\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())
