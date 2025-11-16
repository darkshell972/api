from flask import Flask, request, jsonify
import httpx
import asyncio
import random
import re
from urllib.parse import urlparse
import json
import time

app = Flask(__name__)

class Utils:
    @staticmethod
    def get_random_name():
        first_names = ["John", "Jane", "Mike", "Sarah", "David", "Lisa", "James", "Emily", "Robert", "Jennifer"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
        return random.choice(first_names), random.choice(last_names)
    
    @staticmethod
    def generate_email(first_name, last_name):
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
        return f"{first_name.lower()}.{last_name.lower()}{random.randint(100,999)}@{random.choice(domains)}"
    
    @staticmethod
    def get_formatted_address():
        addresses = [
            {'phone': '+1234567890', 'street': '123 Main St', 'city': 'New York', 'state': 'NY', 'zip': '10001'},
            {'phone': '+1234567891', 'street': '456 Oak Ave', 'city': 'Los Angeles', 'state': 'CA', 'zip': '90001'},
            {'phone': '+1234567892', 'street': '789 Pine Rd', 'city': 'Chicago', 'state': 'IL', 'zip': '60007'},
            {'phone': '+1234567893', 'street': '321 Elm St', 'city': 'Houston', 'state': 'TX', 'zip': '77001'},
            {'phone': '+1234567894', 'street': '654 Maple Dr', 'city': 'Phoenix', 'state': 'AZ', 'zip': '85001'},
        ]
        return random.choice(addresses)

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except:
        return None

def parse_proxy(proxy_str):
    """Parse proxy string in format IP:PORT:USERNAME:PASSWORD or IP:PORT"""
    if not proxy_str:
        return None
    
    parts = proxy_str.split(':')
    
    if len(parts) == 4:
        # Format: IP:PORT:USERNAME:PASSWORD
        ip, port, username, password = parts
        proxy_url = f"http://{username}:{password}@{ip}:{port}"
        return {"http://": proxy_url, "https://": proxy_url}
    elif len(parts) == 2:
        # Format: IP:PORT (no auth)
        ip, port = parts
        proxy_url = f"http://{ip}:{port}"
        return {"http://": proxy_url, "https://": proxy_url}
    else:
        return None

async def fetchProducts(proxy, domain):
    try:
        domain = "https://" + domain
        proxy_config = parse_proxy(proxy) if proxy else None
        
        print(f"🔍 Fetching products from: {domain}")
        print(f"🔧 Using proxy: {proxy_config}")

        timeout = httpx.Timeout(15.0)
        
        async with httpx.AsyncClient(proxies=proxy_config, timeout=timeout, verify=False) as client:
            resp = await client.get(f"{domain}/products.json")
            
            if resp.status_code != 200:
                return False, f"Site Error - Failed to fetch products (HTTP {resp.status_code})"
            
            text = resp.text
            if "shopify" not in text.lower():
                return False, "Not a Shopify store"
            
            try:
                result = resp.json()['products']
                if not result:
                    return False, "No products found"
            except:
                return False, "Invalid products data"

        min_price = float('inf')
        min_product = None

        for product in result:
            for variant in product.get('variants', []):
                if not variant.get('available', True):
                    continue

                try:
                    price = variant.get('price', '0')
                    if isinstance(price, str):
                        price = float(price.replace(',', ''))
                    else:
                        price = float(price)

                    if price < min_price and price > 0:
                        min_price = price
                        min_product = {
                            'site': domain,
                            'price': f"{price:.2f}",
                            'variant_id': str(variant['id']),
                            'link': f"{domain}/products/{product.get('handle', '')}"
                        }

                except (ValueError, TypeError):
                    continue
        
        if min_product and isinstance(min_product, dict) and min_product.get('variant_id'):
            print(f"✅ Found product: ${min_product['price']} - Variant: {min_product['variant_id']}")
            return min_product
        else:
            return False, "No available products found"

    except httpx.TimeoutException:
        return False, "Request timeout"
    except httpx.RequestError as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Error fetching products: {str(e)}"

async def process_card(cc, mes, ano, cvv, site=None, proxy=None):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json'
        }

        proxy_config = parse_proxy(proxy)
        print(f"🎯 Processing card for site: {site}")
        print(f"🔧 Proxy: {proxy_config}")

        ourl = 'https://' + str(site)
        
        # Generate user info
        firstName, lastName = Utils.get_random_name()
        email = Utils.generate_email(firstName, lastName)
        data = Utils.get_formatted_address()

        phone = data['phone']
        street = data['street']
        city = data['city']
        state = data['state']
        s_zip = data['zip']
        address2 = "Apt 1"

        # Fetch product info
        print("📦 Fetching product information...")
        product_info = await fetchProducts(proxy, site)
        
        if isinstance(product_info, tuple) and not product_info[0]:
            return False, product_info[1]
        
        variant_id = product_info.get('variant_id') if isinstance(product_info, dict) else None
        
        if not variant_id:
            return False, "Could not find valid product variant"

        print(f"✅ Found product variant: {variant_id}")

        timeout = httpx.Timeout(30.0)
        
        async with httpx.AsyncClient(proxies=proxy_config, timeout=timeout, headers=headers, verify=False) as client:
            
            # Add to cart
            cart_url = f"{ourl}/cart/add.js"
            cart_data = {'id': variant_id, 'quantity': 1}
            
            try:
                resp = await client.post(cart_url, json=cart_data)
                if resp.status_code != 200:
                    return False, f"Failed to add to cart (HTTP {resp.status_code})"
                print("🛒 Added to cart successfully")
            except Exception as e:
                return False, f"Cart error: {str(e)}"

            # Go to checkout
            checkout_url = f"{ourl}/checkout"
            try:
                resp = await client.get(checkout_url, follow_redirects=True)
                checkout_url_str = str(resp.url)
                if 'login' in checkout_url_str.lower():
                    return False, "Site requires login!"
                
                text = resp.text
                print("✅ Accessed checkout page")
            except Exception as e:
                return False, f"Checkout access error: {str(e)}"

            # Extract tokens
            sst = extract_between(text, 'name="serialized-session-token" content="&quot;', '&q')
            if not sst:
                sst = extract_between(text, 'sessionToken&quot;:&quot;', '&q')
            
            if not sst:
                return False, "Failed to get session token"

            # Extract currency and subtotal
            currency_match = re.search(r'currencyCode&quot;:&quot;([A-Z]{3})', text)
            currency = currency_match.group(1) if currency_match else 'USD'
            
            subtotal_match = re.search(r'totalAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;([0-9.]+)', text)
            subtotal = subtotal_match.group(1) if subtotal_match else '10.00'

            print(f"💰 Currency: {currency}, Subtotal: {subtotal}")

            # Get payment token
            print("💳 Getting payment token...")
            formatted_card = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
            payment_payload = {
                "credit_card": {
                    "month": mes,
                    "name": f"{firstName} {lastName}",
                    "number": formatted_card,
                    "verification_value": cvv,
                    "year": ano
                },
                "payment_session_scope": f"www.{site}"
            }

            try:
                resp = await client.post(
                    'https://deposit.shopifycs.com/sessions', 
                    json=payment_payload
                )
                if resp.status_code == 200:
                    token_data = resp.json()
                    payment_token = token_data.get('id')
                    if not payment_token:
                        return False, "Failed to get payment token"
                    print("✅ Got payment token")
                else:
                    return False, f"Payment token failed: HTTP {resp.status_code}"
            except Exception as e:
                return False, f"Payment token error: {str(e)}"

            # Submit payment
            print("🚀 Submitting payment...")
            graphql_url = f"https://{urlparse(ourl).netloc}/checkouts/unstable/graphql"
            
            submit_query = '''
            mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!) {
                submitForCompletion(input: $input, attemptToken: $attemptToken) {
                    ... on SubmitSuccess { receipt { id } }
                    ... on SubmitFailed { reason }
                }
            }
            '''

            submit_data = {
                'query': submit_query,
                'variables': {
                    'input': {
                        'sessionInput': {'sessionToken': sst},
                        'payment': {
                            'paymentLines': [{
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': 'directPaymentMethod',
                                        'sessionId': payment_token
                                    }
                                },
                                'amount': {
                                    'value': {
                                        'amount': subtotal,
                                        'currencyCode': currency
                                    }
                                }
                            }]
                        }
                    },
                    'attemptToken': checkout_url_str.split('/')[-1]
                },
                'operationName': 'SubmitForCompletion'
            }

            try:
                resp = await client.post(graphql_url, json=submit_data)
                response_text = resp.text
                print(f"📄 Final response: {response_text[:500]}...")
                
                # Check for specific response patterns
                if "3d_secure" in response_text.lower() or "three_d_secure" in response_text.lower() or "actionreq" in response_text.lower():
                    return "3d_required", "3d required 🔒", "Shopify", subtotal, currency
                
                if "card declined" in response_text.lower() or "declined" in response_text.lower():
                    return False, "card declined", "Shopify", subtotal, currency
                
                # Check for common errors
                if "Your order total has changed." in response_text:
                    return False, "Site not supported - order total changed"
                if "CAPTCHA" in response_text or "CAPTCHA_METADATA_MISSING" in response_text:
                    return False, "Captcha detected - use better proxies"
                if "PAYMENTS_CREDIT_CARD" in response_text:
                    return False, "card declined"
                if "The requested payment method is not available." in response_text:
                    return False, "Shopify Payments not available"
                if "PAYMENTS_CREDIT_CARD_VERIFICATION_VALUE_INVALID_FOR_CARD_TYPE" in response_text:
                    return False, "Invalid CVV"
                if "insufficient" in response_text.lower() or "insuff" in response_text.lower():
                    return False, "Insufficient funds"
                if "invalid_cvc" in response_text.lower() or "incorrect_cvc" in response_text.lower():
                    return False, "Invalid CVC"
                if "ZIP" in response_text:
                    return False, "Incorrect ZIP code"
                
                # Check for success
                try:
                    result = json.loads(response_text)
                    if 'data' in result and 'submitForCompletion' in result['data']:
                        if 'receipt' in result['data']['submitForCompletion']:
                            return True, "Charged 🔥", "Shopify", subtotal, currency
                        elif 'reason' in result['data']['submitForCompletion']:
                            reason = result['data']['submitForCompletion']['reason']
                            if "declined" in reason.lower():
                                return False, "card declined", "Shopify", subtotal, currency
                            return False, f"Payment failed: {reason}"
                except:
                    pass
                
                if 'receipt' in response_text.lower():
                    return True, "Charged 🔥", "Shopify", subtotal, currency
                
                return False, "Payment processing failed - unknown response"

            except Exception as e:
                return False, f"Final submission error: {str(e)}"

    except httpx.TimeoutException:
        return False, "Request timeout - site may be slow or proxy not working"
    except httpx.RequestError as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

@app.route('/')
def home():
    return jsonify({
        'message': 'Shopify Auto-Checkout API - Ready!',
        'version': '2.0',
        'status': 'active',
        'endpoints': {
            'main': '/autosh?site=example.com&cc=4111111111111111|12|2025|123&proxy=ip:port:user:pass',
            'health': '/health'
        },
        'proxy_formats': [
            'IP:PORT:USERNAME:PASSWORD',
            'IP:PORT',
            'Leave empty for no proxy'
        ]
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'Shopify Auto-Checkout API'})

@app.route('/autosh', methods=['GET'])
def autosh_endpoint():
    """Main API endpoint for Shopify auto-checkout"""
    try:
        site = request.args.get('site', '').strip()
        cc = request.args.get('cc', '').strip()
        proxy = request.args.get('proxy', '').strip()
        
        # Validate required parameters
        if not site:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: site'
            }), 400
        
        if not cc:
            return jsonify({
                'status': 'error', 
                'message': 'Missing required parameter: cc'
            }), 400
        
        # Parse CC details
        cc_parts = cc.split('|')
        if len(cc_parts) != 4:
            return jsonify({
                'status': 'error',
                'message': 'Invalid CC format. Use: number|month|year|cvv'
            }), 400
        
        cc_number, month, year, cvv = cc_parts
        
        # Basic validation
        if not cc_number.isdigit() or len(cc_number) < 15:
            return jsonify({
                'status': 'error',
                'message': 'Invalid credit card number'
            }), 400
        
        if not month.isdigit() or not (1 <= int(month) <= 12):
            return jsonify({
                'status': 'error',
                'message': 'Invalid month (1-12)'
            }), 400
            
        if not year.isdigit() or len(year) != 4:
            return jsonify({
                'status': 'error',
                'message': 'Invalid year (4 digits)'
            }), 400
            
        if not cvv.isdigit() or len(cvv) not in [3, 4]:
            return jsonify({
                'status': 'error',
                'message': 'Invalid CVV (3-4 digits)'
            }), 400
        
        # Process the request
        print(f"🚀 Starting process for site: {site}")
        start_time = time.time()
        
        # Create new event loop for async processing
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                process_card(cc_number, month, year, cvv, site, proxy if proxy else None)
            )
        finally:
            loop.close()
        
        processing_time = time.time() - start_time
        
        # Format response according to specifications
        base_response = {
            'gateway': 'Shopify',
            'site': site,
            'processing_time': f"{processing_time:.2f}s"
        }
        
        if result and result[0] == "3d_required":
            # 3D Secure required
            response_data = {
                'status': 'success',
                'message': '3d required 🔒',
                **base_response
            }
            if len(result) > 3:
                response_data['amount'] = result[3]
            if len(result) > 4:
                response_data['currency'] = result[4]
            print(f"🔒 3D Secure Required")
            return jsonify(response_data)
            
        elif result and result[0] is True:
            # Successfully charged
            response_data = {
                'status': 'success',
                'message': 'Charged 🔥',
                **base_response
            }
            if len(result) > 3:
                response_data['amount'] = result[3]
            if len(result) > 4:
                response_data['currency'] = result[4]
            print(f"✅ Charged Successfully")
            return jsonify(response_data)
            
        else:
            # Failed or declined
            error_msg = result[1] if result else "Unknown error occurred"
            
            # Check if it's specifically a card decline
            if "card declined" in error_msg.lower():
                response_data = {
                    'status': 'failed',
                    'message': 'card declined',
                    **base_response
                }
                if result and len(result) > 3:
                    response_data['amount'] = result[3]
                if result and len(result) > 4:
                    response_data['currency'] = result[4]
                print(f"❌ Card Declined")
                return jsonify(response_data)
            else:
                # Other failure
                response_data = {
                    'status': 'failed',
                    'message': error_msg,
                    **base_response
                }
                print(f"❌ Failed: {error_msg}")
                return jsonify(response_data)
            
    except Exception as e:
        print(f"💥 Server error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint to verify the API is working"""
    return jsonify({
        'status': 'success',
        'message': 'API is running correctly',
        'timestamp': time.time()
    })

if __name__ == '__main__':
    print("🚀 Starting Shopify Auto-Checkout API...")
    print("📝 Available endpoints:")
    print("   GET / - API documentation")
    print("   GET /health - Health check")
    print("   GET /autosh - Main checkout endpoint")
    print("   GET /test - Test endpoint")
    app.run(host='0.0.0.0', port=5000, debug=False)
