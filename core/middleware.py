import re
from django.conf import settings
from accounts.models import User


class DevCsrfTrustedOriginMiddleware:
    """In DEBUG mode, trust any localhost/127.0.0.1 origin for CSRF.
    Django 4+ port wildcards don't work, and dev proxy ports change constantly."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG:
            origin = request.META.get('HTTP_ORIGIN', '')
            if origin:
                from urllib.parse import urlsplit
                parsed = urlsplit(origin)
                host = parsed.hostname or ''
                if host in ('127.0.0.1', 'localhost'):
                    # Dynamically add this exact origin so CsrfViewMiddleware trusts it
                    if origin not in settings.CSRF_TRUSTED_ORIGINS:
                        settings.CSRF_TRUSTED_ORIGINS.append(origin)
        return self.get_response(request)


class SubdomainMiddleware:
    IGNORED_SUBDOMAINS = {'www', 'tap', ''}
    IP_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]

        request.subdomain = None
        request.tenant_user = None
        request.tenant_profile = None

        # Skip subdomain extraction for bare IPs and localhost
        if self.IP_RE.match(host) or host == 'localhost':
            return self.get_response(request)

        parts = host.split('.')

        if len(parts) >= 3:
            subdomain = parts[0].lower()
            if subdomain not in self.IGNORED_SUBDOMAINS:
                request.subdomain = subdomain
                try:
                    user = User.objects.select_related(
                        'profile__category', 'profile__theme',
                    ).get(username=subdomain)
                    request.tenant_user = user
                    request.tenant_profile = getattr(user, 'profile', None)
                except User.DoesNotExist:
                    pass

        return self.get_response(request)
