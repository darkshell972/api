from flask import Flask, request, jsonify
import aiohttp
import asyncio
import random
import re
from urllib.parse import urlparse
import json

app = Flask(__name__)

class Utils:
    @staticmethod
    def get_random_name():
        first_names = ["John", "Jane", "Mike", "Sarah", "David", "Lisa"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia"]
        return random.choice(first_names), random.choice(last_names)
    
    @staticmethod
    def generate_email(first_name, last_name):
        domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
        return f"{first_name.lower()}.{last_name.lower()}@{random.choice(domains)}"
    
    @staticmethod
    def get_formatted_address():
        addresses = [
            {'phone': '+1234567890', 'street': '123 Main St', 'city': 'New York', 'state': 'NY', 'zip': '10001'},
            {'phone': '+1234567891', 'street': '456 Oak Ave', 'city': 'Los Angeles', 'state': 'CA', 'zip': '90001'},
            {'phone': '+1234567892', 'street': '789 Pine Rd', 'city': 'Chicago', 'state': 'IL', 'zip': '60007'},
        ]
        return random.choice(addresses)

def extract_between(text, start, end):
    try:
        return text.split(start)[1].split(end)[0]
    except:
        return None

async def fetchProducts(proxy, domain):
    try:
        domain = "https://" + domain
        proxy_dict = {"http": proxy, "https": proxy} if proxy else None
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{domain}/products.json", timeout=timeout, proxy=proxy) as resp:
                if resp.status != 200:
                    return False, "Site Error!"
                text = await resp.text()
                if "shopify" not in text.lower():
                    return False, "Not Shopify!"

                result = (await resp.json())['products']
                if not result:
                    return False, "No Products!"

        min_price = float('inf')
        min_product = None

        for product in result:
            if not product.get('variants'):
                continue
            
            for variant in product['variants']:
                if not variant.get('available', True):
                    continue

                try:
                    price = variant.get('price', '0')
                    if isinstance(price, str):
                        price = float(price.replace(',', ''))
                    else:
                        price = float(price)

                    if price < min_price:
                        min_price = price
                        min_product = {
                            'site': domain,
                            'price': f"{price:.2f}",
                            'variant_id': str(variant['id']),
                            'link': f"{domain}/products/{product['handle']}"
                        }

                except (ValueError, TypeError, AttributeError):
                    continue
        
        if min_product and isinstance(min_product, dict) and min_product.get('price'):
            return min_product
        else:
            return False, "No Valid Products"

    except aiohttp.ClientError as e:
        return False, f"Proxy Error: {str(e)}"
    except asyncio.TimeoutError:
        return False, "Request Timeout"
    except Exception as e:
        return False, f"Error: {str(e)}"

async def process_card(cc, mes, ano, cvv, site=None, proxy=None):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Pragma': 'no-cache',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json'
        }

        print(f"Processing card for site: {site}")
        print(f"Using proxy: {proxy}")

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
        print("Fetching product information...")
        product_info = await fetchProducts(proxy, site)
        
        if isinstance(product_info, tuple) and not product_info[0]:
            return False, product_info[1]
        
        variant_id = product_info.get('variant_id') if isinstance(product_info, dict) else None
        
        if not variant_id:
            return False, "Could not find valid product variant"

        print(f"Found product variant: {variant_id}")

        connector = aiohttp.TCPConnector(verify_ssl=False)
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            
            # Add to cart
            cart_url = f"{ourl}/cart/add.js"
            cart_data = {'id': variant_id, 'quantity': 1}
            
            try:
                async with session.post(cart_url, data=cart_data, proxy=proxy) as resp:
                    if resp.status != 200:
                        return False, "Failed to add to cart"
                    print("Added to cart successfully")
            except Exception as e:
                return False, f"Cart error: {str(e)}"

            # Go to checkout
            checkout_url = f"{ourl}/checkout"
            try:
                async with session.get(checkout_url, proxy=proxy, allow_redirects=True) as resp:
                    checkout_url_str = str(resp.url)
                    if 'login' in checkout_url_str.lower():
                        return False, "Site requires login!"
                    
                    text = await resp.text()
                    print("Accessed checkout page")
            except Exception as e:
                return False, f"Checkout access error: {str(e)}"

            # Extract tokens
            sst = extract_between(text, 'name="serialized-session-token" content="&quot;', '&q')
            if not sst:
                sst = extract_between(text, 'sessionToken&quot;:&quot;', '&q')
            
            if not sst:
                return False, "Failed to get session token"

            # Extract other required data
            queueToken = extract_between(text, 'queueToken&quot;:&quot;', '&q')
            stableId = extract_between(text, 'stableId&quot;:&quot;', '&q') or "1"
            
            # Extract currency
            currency_match = re.search(r'currencyCode&quot;:&quot;([A-Z]{3})', text)
            currency = currency_match.group(1) if currency_match else 'USD'
            
            # Extract subtotal
            subtotal_match = re.search(r'totalAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;([0-9.]+)', text)
            subtotal = subtotal_match.group(1) if subtotal_match else '10.00'

            print(f"Currency: {currency}, Subtotal: {subtotal}")

            # Simplified GraphQL request for shipping
            graphql_url = f"https://{urlparse(ourl).netloc}/checkouts/unstable/graphql"
            
            shipping_query = {
                'query': '''
                query ($sessionToken: String!) {
                    session(sessionInput: {sessionToken: $sessionToken}) {
                        negotiate(input: {purchaseProposal: {delivery: {deliveryLines: []}}}) {
                            result {
                                ... on NegotiationResultAvailable {
                                    sellerProposal {
                                        delivery {
                                            ... on FilledDeliveryTerms {
                                                deliveryLines {
                                                    availableDeliveryStrategies {
                                                        handle
                                                        amount {
                                                            value {
                                                                amount
                                                                currencyCode
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        payment {
                                            availablePaymentLines {
                                                paymentMethod {
                                                    paymentMethodIdentifier
                                                    name
                                                }
                                            }
                                        }
                                        runningTotal {
                                            value {
                                                amount
                                                currencyCode
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                ''',
                'variables': {
                    'sessionToken': sst
                }
            }

            try:
                async with session.post(graphql_url, json=shipping_query, proxy=proxy) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print("Got shipping information")
                    else:
                        return False, "Failed to get shipping info"
            except Exception as e:
                return False, f"Shipping info error: {str(e)}"

            # Get payment token
            formattedCard = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
            payment_payload = {
                "credit_card": {
                    "month": mes,
                    "name": f"{firstName} {lastName}",
                    "number": formattedCard,
                    "verification_value": cvv,
                    "year": ano
                },
                "payment_session_scope": f"www.{urlparse(ourl).netloc}"
            }

            try:
                async with session.post('https://deposit.shopifycs.com/sessions', 
                                      json=payment_payload, proxy=proxy) as resp:
                    if resp.status == 200:
                        token_data = await resp.json()
                        payment_token = token_data.get('id')
                        if not payment_token:
                            return False, "Failed to get payment token"
                        print("Got payment token")
                    else:
                        return False, "Payment token request failed"
            except Exception as e:
                return False, f"Payment token error: {str(e)}"

            # Simplified final submission
            submit_query = {
                'query': '''
                mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!) {
                    submitForCompletion(input: $input, attemptToken: $attemptToken) {
                        ... on SubmitSuccess {
                            receipt {
                                id
                            }
                        }
                        ... on SubmitFailed {
                            reason
                        }
                    }
                }
                ''',
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
                }
            }

            try:
                async with session.post(graphql_url, json=submit_query, proxy=proxy) as resp:
                    response_text = await resp.text()
                    print(f"Final response: {response_text}")
                    
                    if "Your order total has changed." in response_text:
                        return False, "Site not supported"
                    if "CAPTCHA" in response_text:
                        return False, "Captcha detected"
                    if "PAYMENTS_CREDIT_CARD" in response_text:
                        return False, "Card declined"
                    
                    try:
                        result = json.loads(response_text)
                        if 'data' in result and 'submitForCompletion' in result['data']:
                            if 'receipt' in result['data']['submitForCompletion']:
                                return True, f"Charged {subtotal} {currency}", "Shopify", subtotal, currency
                            elif 'reason' in result['data']['submitForCompletion']:
                                return False, result['data']['submitForCompletion']['reason']
                    except:
                        pass
                    
                    return False, "Payment processing failed"

            except Exception as e:
                return False, f"Final submission error: {str(e)}"

    except Exception as e:
        print(f'Error processing card: {str(e)}')
        return False, f"Processing error: {str(e)}"

@app.route('/')
def home():
    return jsonify({
        'message': 'Shopify Auto-Checkout API',
        'usage': '/autosh?site=example.com&cc=4111111111111111|12|2025|123&proxy=ip:port',
        'status': 'active'
    })

@app.route('/autosh', methods=['GET'])
def autosh_endpoint():
    site = request.args.get('site')
    cc = request.args.get('cc')
    proxy = request.args.get('proxy')
    
    if not site or not cc:
        return jsonify({'error': 'Missing required parameters: site and cc'}), 400
    
    # Parse CC details
    cc_parts = cc.split('|')
    if len(cc_parts) != 4:
        return jsonify({'error': 'Invalid CC format. Use: number|month|year|cvv'}), 400
    
    cc_number, month, year, cvv = cc_parts
    
    # Validate CC number (basic check)
    if not cc_number.isdigit() or len(cc_number) < 15:
        return jsonify({'error': 'Invalid credit card number'}), 400
    
    try:
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_card(cc_number, month, year, cvv, site, proxy))
        loop.close()
        
        if result[0]:  # Success
            return jsonify({
                'status': 'success',
                'message': result[1],
                'gateway': result[2] if len(result) > 2 else 'Shopify',
                'amount': result[3] if len(result) > 3 else 'Unknown',
                'currency': result[4] if len(result) > 4 else 'USD'
            })
        else:  # Failed
            return jsonify({
                'status': 'failed',
                'message': result[1]
            })
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Shopify Auto-Checkout API'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
