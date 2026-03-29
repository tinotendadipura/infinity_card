"""
PayPal Subscriptions API utility module.

Handles: authentication, product/plan creation, subscription creation,
subscription verification, and cancellation.
"""
import logging
from base64 import b64encode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Authentication
# ──────────────────────────────────────────────

def _get_access_token():
    """Obtain an OAuth 2.0 access token from PayPal."""
    url = f'{settings.PAYPAL_API_BASE}/v1/oauth2/token'
    credentials = b64encode(
        f'{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_SECRET}'.encode()
    ).decode()
    resp = requests.post(
        url,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        data={'grant_type': 'client_credentials'},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def _headers():
    """Return standard headers for PayPal REST calls."""
    token = _get_access_token()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


# ──────────────────────────────────────────────
#  Catalog Products
# ──────────────────────────────────────────────

def create_product(name, description=''):
    """Create a PayPal Catalog Product (one per Plan)."""
    url = f'{settings.PAYPAL_API_BASE}/v1/catalogs/products'
    payload = {
        'name': name,
        'description': description or f'{name} subscription',
        'type': 'SERVICE',
        'category': 'SOFTWARE',
    }
    resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    logger.info('Created PayPal product %s for "%s"', data['id'], name)
    return data['id']


# ──────────────────────────────────────────────
#  Billing Plans
# ──────────────────────────────────────────────

def create_billing_plan(product_id, plan_name, price, interval_unit='MONTH', interval_count=1):
    """
    Create a PayPal Billing Plan linked to a product.
    Returns the PayPal plan ID (e.g. P-XXXXXXXX).
    """
    url = f'{settings.PAYPAL_API_BASE}/v1/billing/plans'
    payload = {
        'product_id': product_id,
        'name': f'{plan_name} - {interval_unit.capitalize()}ly',
        'description': f'{plan_name} {interval_unit.lower()}ly subscription',
        'status': 'ACTIVE',
        'billing_cycles': [
            {
                'frequency': {
                    'interval_unit': interval_unit,
                    'interval_count': interval_count,
                },
                'tenure_type': 'REGULAR',
                'sequence': 1,
                'total_cycles': 0,  # infinite
                'pricing_scheme': {
                    'fixed_price': {
                        'value': str(price),
                        'currency_code': 'USD',
                    }
                },
            }
        ],
        'payment_preferences': {
            'auto_bill_outstanding': True,
            'payment_failure_threshold': 3,
        },
    }
    resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    logger.info('Created PayPal plan %s for "%s"', data['id'], plan_name)
    return data['id']


# ──────────────────────────────────────────────
#  Subscriptions
# ──────────────────────────────────────────────

def create_subscription(paypal_plan_id, return_url, cancel_url, user_email=None):
    """
    Create a PayPal Subscription.
    Returns (subscription_id, approval_url).
    The caller should redirect the user to approval_url.
    """
    url = f'{settings.PAYPAL_API_BASE}/v1/billing/subscriptions'
    payload = {
        'plan_id': paypal_plan_id,
        'application_context': {
            'brand_name': 'InfinityCard',
            'locale': 'en-US',
            'shipping_preference': 'NO_SHIPPING',
            'user_action': 'SUBSCRIBE_NOW',
            'return_url': return_url,
            'cancel_url': cancel_url,
        },
    }
    if user_email:
        payload['subscriber'] = {
            'email_address': user_email,
        }

    logger.info('Creating PayPal subscription - Plan ID: %s, URL: %s', paypal_plan_id, url)
    logger.info('Subscription payload: %s', payload)
    
    resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
    
    logger.info('PayPal subscription response: %s', resp.status_code)
    if resp.status_code not in (200, 201):
        logger.error('PayPal subscription error - Status: %s, Body: %s', resp.status_code, resp.text[:1000])
        try:
            error_data = resp.json()
            logger.error('PayPal error details: %s', error_data)
        except:
            pass
    
    resp.raise_for_status()
    data = resp.json()

    approval_url = None
    for link in data.get('links', []):
        if link['rel'] == 'approve':
            approval_url = link['href']
            break

    logger.info('Created PayPal subscription %s', data['id'])
    return data['id'], approval_url


def get_subscription_details(paypal_subscription_id):
    """Fetch subscription details from PayPal. Returns dict."""
    url = f'{settings.PAYPAL_API_BASE}/v1/billing/subscriptions/{paypal_subscription_id}'
    resp = requests.get(url, headers=_headers(), timeout=30)
    logger.info('PayPal GET %s -> %s', url, resp.status_code)
    if resp.status_code != 200:
        logger.error('PayPal subscription details response: %s %s', resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


def cancel_subscription(paypal_subscription_id, reason='Cancelled by user'):
    """Cancel a PayPal subscription."""
    url = f'{settings.PAYPAL_API_BASE}/v1/billing/subscriptions/{paypal_subscription_id}/cancel'
    resp = requests.post(
        url,
        json={'reason': reason},
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    logger.info('Cancelled PayPal subscription %s', paypal_subscription_id)
    return True


# ──────────────────────────────────────────────
#  One-Time Payments (Orders API v2)
# ──────────────────────────────────────────────

def create_order(amount, description, return_url, cancel_url, currency='USD'):
    """
    Create a PayPal one-time payment order.
    Returns (order_id, approval_url).
    """
    url = f'{settings.PAYPAL_API_BASE}/v2/checkout/orders'
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [
            {
                'amount': {
                    'currency_code': currency,
                    'value': str(amount),
                },
                'description': description,
            }
        ],
        'application_context': {
            'brand_name': 'InfinityCard',
            'landing_page': 'NO_PREFERENCE',
            'shipping_preference': 'NO_SHIPPING',
            'user_action': 'PAY_NOW',
            'return_url': return_url,
            'cancel_url': cancel_url,
        },
    }
    
    logger.info('Creating PayPal order - Mode: %s, API Base: %s', settings.PAYPAL_MODE, settings.PAYPAL_API_BASE)
    logger.info('PayPal order payload: %s', payload)
    
    resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
    logger.info('PayPal create order response: %s', resp.status_code)
    
    if resp.status_code not in (200, 201):
        logger.error('PayPal create order error - Status: %s, Body: %s', resp.status_code, resp.text[:1000])
        try:
            error_data = resp.json()
            logger.error('PayPal error details: %s', error_data)
        except:
            pass
    
    resp.raise_for_status()
    data = resp.json()

    approval_url = None
    for link in data.get('links', []):
        if link['rel'] == 'approve':
            approval_url = link['href']
            break

    logger.info('Created PayPal order %s for $%s', data['id'], amount)
    return data['id'], approval_url


def capture_order(order_id):
    """
    Capture (finalise) a PayPal order after user approval.
    Returns the full capture response dict.
    """
    url = f'{settings.PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture'
    resp = requests.post(url, json={}, headers=_headers(), timeout=30)
    logger.info('PayPal capture order %s -> %s', order_id, resp.status_code)
    if resp.status_code not in (200, 201):
        logger.error('PayPal capture response: %s %s', resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


def get_order_details(order_id):
    """Fetch order details from PayPal. Returns dict."""
    url = f'{settings.PAYPAL_API_BASE}/v2/checkout/orders/{order_id}'
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
#  Webhook Verification
# ──────────────────────────────────────────────

def verify_webhook_signature(headers_dict, body, webhook_id):
    """
    Verify a PayPal webhook event signature.
    Returns True if verified.
    """
    url = f'{settings.PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature'
    payload = {
        'auth_algo': headers_dict.get('PAYPAL-AUTH-ALGO', ''),
        'cert_url': headers_dict.get('PAYPAL-CERT-URL', ''),
        'transmission_id': headers_dict.get('PAYPAL-TRANSMISSION-ID', ''),
        'transmission_sig': headers_dict.get('PAYPAL-TRANSMISSION-SIG', ''),
        'transmission_time': headers_dict.get('PAYPAL-TRANSMISSION-TIME', ''),
        'webhook_id': webhook_id,
        'webhook_event': body,
    }
    resp = requests.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.status_code == 200:
        return resp.json().get('verification_status') == 'SUCCESS'
    return False
