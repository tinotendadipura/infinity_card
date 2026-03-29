import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProfileEvent
from profiles.models import Profile


ALLOWED_EVENTS = {et[0] for et in ProfileEvent.EVENT_TYPES}


@csrf_exempt
@require_POST
def track_event(request):
    """Public endpoint to record a ProfileEvent from the public profile page."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    profile_id = data.get('profile_id')
    event_type = data.get('event_type', '')
    item_id = data.get('item_id')
    item_title = data.get('item_title', '')

    if not profile_id or event_type not in ALLOWED_EVENTS:
        return JsonResponse({'error': 'Bad request'}, status=400)

    try:
        profile = Profile.objects.get(pk=profile_id)
    except Profile.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    ProfileEvent.objects.create(
        profile=profile,
        event_type=event_type,
        item_id=item_id,
        item_title=item_title[:200] if item_title else '',
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    return JsonResponse({'ok': True})
