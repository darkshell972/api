from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import asyncio
import aiohttp
import random
import re
from urllib.parse import urlparse
from typing import Optional
import uuid
from datetime import datetime

# Copy ALL your existing code here (fetchProducts, process_card functions)
# I'll reference your existing functions

app = FastAPI(title="Shopify Checker API", version="1.0.0")

# Mock classes to replace your bot dependencies
class MockProxy:
    def __init__(self, proxy_str):
        self.proxy = proxy_str

class MockSite:
    def __init__(self, url, variant_id=None):
        self.url = url
        self.variant_id = variant_id

# Mock Utils class (replace with your actual Utils)
class Utils:
    @staticmethod
    def get_random_name():
        return "John", "Doe"
    
    @staticmethod
    def generate_email(first_name, last_name):
        return f"{first_name}.{last_name}@example.com"
    
    @staticmethod
    def get_formatted_address():
        return {
            'phone': '1234567890',
            'street': '123 Main St',
            'city': 'New York',
            'state': 'NY',
            'zip': '10001'
        }

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except:
        return None

@app.get("/")
async def check_shopify(site: str, cc: str, proxy: Optional[str] = None):
    """
    Shopify checker endpoint
    Format: /?site=store.com&cc=number|mes|ano|cvv&proxy=ip:port:user:pass
    """
    try:
        # Parse CC data (format: 5353181300085222|05|26|192)
        cc_parts = cc.split('|')
        if len(cc_parts) != 4:
            return JSONResponse(
                content={
                    "success": False, 
                    "message": "Invalid CC format. Use: number|mes|ano|cvv",
                    "site": site
                }
            )
        
        cc_number, mes, ano, cvv = cc_parts
        
        # Parse proxy (format: 142.111.67.146:5611:zhohvzzt:p4lbmy10wvug)
        proxies = []
        if proxy:
            proxy_parts = proxy.split(':')
            if len(proxy_parts) == 4:
                ip, port, username, password = proxy_parts
                proxy_url = f"http://{username}:{password}@{ip}:{port}"
                proxies = [MockProxy(proxy_url)]
            elif len(proxy_parts) == 2:
                ip, port = proxy_parts
                proxy_url = f"http://{ip}:{port}"
                proxies = [MockProxy(proxy_url)]
            else:
                return JSONResponse(
                    content={
                        "success": False,
                        "message": "Invalid proxy format. Use: ip:port:user:pass or ip:port",
                        "site": site
                    }
                )
        
        # Create mock site object
        site_obj = MockSite(site)
        
        # Call your existing process_card function
        result = await process_card(
            cc=cc_number,
            mes=mes,
            ano=ano,
            cvv=cvv,
            site=site_obj,
            proxies=proxies if proxies else []
        )
        
        # Parse result
        if len(result) >= 3:
            success, message, display_name = result[0], result[1], result[2]
            amount = result[3] if len(result) > 3 else None
            currency = result[4] if len(result) > 4 else None
        else:
            success, message = result[0], result[1]
            display_name = amount = currency = None
        
        return {
            "success": success,
            "message": message,
            "site": site,
            "display_name": display_name,
            "amount": amount,
            "currency": currency,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return JSONResponse(
            content={
                "success": False, 
                "message": f"Error: {str(e)}",
                "site": site
            }
        )

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# PASTE YOUR ENTIRE EXISTING CODE HERE
# Copy everything from your original file starting from:
# async def fetchProducts(proxy, domain):
# ... all the way to the end

# For Render deployment
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
