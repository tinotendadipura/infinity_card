from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Profile, SocialLink, CatalogItem, CatalogCategory, CatalogItemImage, Service
from .forms import ProfileForm, CatalogItemForm, ServiceForm
from subscriptions.middleware import check_user_subscription
from themes.models import Theme


def public_catalog(request):
    """Public catalog page — WhatsApp Business style full listing."""
    profile = request.tenant_profile
    if not profile or not profile.is_published:
        raise Http404

    # Subscription enforcement
    if not request.subscription_active:
        info = request.subscription_info or check_user_subscription(request.tenant_user)
        return render(request, 'profiles/suspended.html', {
            'profile': profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    categories = profile.catalog_categories.prefetch_related('items__extra_images').all()
    uncategorized = profile.catalog_items.filter(category__isnull=True).prefetch_related('extra_images')

    # WhatsApp number: try social link first, fall back to phone
    wa_link = profile.social_links.filter(platform='whatsapp').first()
    wa_number = ''
    if wa_link and wa_link.url:
        import re
        digits = re.sub(r'\D', '', wa_link.url)
        if digits:
            wa_number = digits
    if not wa_number and profile.phone:
        import re
        wa_number = re.sub(r'\D', '', profile.phone)

    return render(request, 'profiles/catalog_full.html', {
        'profile': profile,
        'catalog_categories': categories,
        'uncategorized_items': uncategorized,
        'total_items': profile.catalog_items.count(),
        'wa_number': wa_number,
    })


def public_catalog_preview(request, username):
    """Preview-friendly public catalog via /p/<username>/catalog/."""
    from accounts.models import User
    try:
        user = User.objects.select_related(
            'profile__category', 'profile__theme',
        ).get(username=username)
    except User.DoesNotExist:
        raise Http404

    profile = getattr(user, 'profile', None)
    if not profile:
        raise Http404

    # Subscription enforcement
    info = check_user_subscription(user)
    if not info['active']:
        return render(request, 'profiles/suspended.html', {
            'profile': profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    categories = profile.catalog_categories.prefetch_related('items__extra_images').all()
    uncategorized = profile.catalog_items.filter(category__isnull=True).prefetch_related('extra_images')

    wa_link = profile.social_links.filter(platform='whatsapp').first()
    wa_number = ''
    if wa_link and wa_link.url:
        import re
        digits = re.sub(r'\D', '', wa_link.url)
        if digits:
            wa_number = digits
    if not wa_number and profile.phone:
        import re
        wa_number = re.sub(r'\D', '', profile.phone)

    return render(request, 'profiles/catalog_full.html', {
        'profile': profile,
        'catalog_categories': categories,
        'uncategorized_items': uncategorized,
        'total_items': profile.catalog_items.count(),
        'wa_number': wa_number,
    })


def _build_profile_context(profile, subscription_active=True):
    """Build universal context dict for any public profile, regardless of category."""
    context = {
        'profile': profile,
        'subscription_active': subscription_active,
    }
    # Category-specific data — always included so the single template can
    # conditionally render whichever sections have data.
    if hasattr(profile, 'properties'):
        context['properties'] = profile.properties.all()
    if hasattr(profile, 'media_items'):
        context['media_items'] = profile.media_items.all()
    if hasattr(profile, 'event_packages'):
        context['packages'] = profile.event_packages.all()
    if hasattr(profile, 'menu_items'):
        context['menu_items'] = profile.menu_items.all()
    # Common sections
    context['catalog_categories'] = profile.catalog_categories.prefetch_related('items').all()
    context['uncategorized_items'] = profile.catalog_items.filter(category__isnull=True)
    context['services'] = profile.services.all()
    context['skills'] = profile.skills.all()
    context['experiences'] = profile.experiences.all()
    context['education_entries'] = profile.education_entries.all()
    context['gallery_images'] = profile.gallery_images.all()
    context['business_hours'] = profile.business_hours.all()
    context['testimonials'] = profile.testimonials.all()
    context['website_portfolios'] = profile.website_portfolios.all()
    return context


def public_profile(request, username, code):
    """Public profile via simple URL: /p/<username>/<code>/"""
    from accounts.models import User
    from django.http import Http404

    try:
        user = User.objects.select_related(
            'profile__category', 'profile__theme',
        ).get(username=username)
    except User.DoesNotExist:
        raise Http404(f"User '{username}' not found")

    profile = getattr(user, 'profile', None)
    if not profile:
        raise Http404(f"Profile not found for user '{username}'")

    if not profile.is_published:
        raise Http404(f"Profile for '{username}' is not published")

    # Verify the code matches
    if profile.profile_code != code:
        raise Http404(f"Invalid profile code. Expected: {profile.profile_code}, Got: {code}")

    # Subscription enforcement
    info = check_user_subscription(user)
    if not info['active']:
        return render(request, 'profiles/suspended.html', {
            'profile': profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    context = _build_profile_context(profile, info['active'])
    return render(request, 'profiles/default.html', context)


def public_profile_by_code(request, code):
    """Public profile via subdomain + profile code: username.inftycard.cc/code/"""
    profile = request.tenant_profile
    if not profile or not profile.is_published:
        raise Http404

    # Verify the code matches
    if profile.profile_code != code:
        raise Http404

    # Subscription enforcement
    if not request.subscription_active:
        info = request.subscription_info or check_user_subscription(request.tenant_user)
        return render(request, 'profiles/suspended.html', {
            'profile': profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    context = _build_profile_context(profile, request.subscription_active)
    return render(request, 'profiles/default.html', context)


def preview_profile(request, username):
    """Localhost-friendly profile preview via /p/<username>/."""
    from accounts.models import User
    try:
        user = User.objects.select_related(
            'profile__category', 'profile__theme',
        ).get(username=username)
    except User.DoesNotExist:
        raise Http404

    profile = getattr(user, 'profile', None)
    if not profile:
        raise Http404

    # Subscription enforcement
    info = check_user_subscription(user)
    if not info['active']:
        return render(request, 'profiles/suspended.html', {
            'profile': profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    context = _build_profile_context(profile, subscription_active=True)
    return render(request, 'profiles/default.html', context)


def nfc_profile_redirect(request, name_slug, code):
    """Redirect legacy NFC card URLs to new canonical URL format."""
    try:
        profile = Profile.objects.select_related(
            'user', 'category', 'theme',
        ).get(profile_code=code)
    except Profile.DoesNotExist:
        raise Http404

    # Redirect to new canonical URL: /p/<username>/<code>/
    from django.shortcuts import redirect
    return redirect('public_profile', username=profile.user.username, code=code)


FEATURE_TOGGLES = [
    # (field_name, label, description, icon_group)
    ('show_bio', 'About / Bio', 'Display your bio and about section', 'profile'),
    ('show_catalog', 'Products / Catalog', 'Show your product catalog with cart & WhatsApp ordering', 'profile'),
    ('show_social_links', 'Social Media Links', 'Display links to your social media profiles', 'profile'),
    ('show_contact_info', 'Contact Information', 'Show phone, email, and location details', 'profile'),
    ('show_services', 'Services', 'List the services you offer', 'extra'),
    ('show_skills', 'Skills / Expertise', 'Display your skills and expertise areas', 'extra'),
    ('show_experience', 'Experience', 'Show your work experience and positions', 'extra'),
    ('show_education', 'Education', 'Show your education history', 'extra'),
    ('show_gallery', 'Photo Gallery', 'Show a gallery of your work or photos', 'extra'),
    ('show_business_hours', 'Business Hours', 'Display your operating hours', 'extra'),
    ('show_testimonials', 'Testimonials', 'Show customer reviews and testimonials', 'extra'),
    ('show_contact_form', 'Contact Collection', 'Let visitors save their contact details to your phone book', 'extra'),
    ('show_map', 'Location Map', 'Show an interactive map with your location on your profile', 'extra'),
    ('show_website_portfolio', 'Website Portfolio', 'Showcase websites you have designed or built', 'extra'),
]

# ── Plan-based feature gating ──
# Maps plan slugs to the set of feature toggles they unlock.
# Each tier includes all features from the tier below it.
_STARTER_FEATURES = {
    'show_bio', 'show_catalog', 'show_social_links', 'show_contact_info',
    'show_services', 'show_skills',
}
_BUSINESS_FEATURES = _STARTER_FEATURES | {
    'show_experience', 'show_education', 'show_gallery', 'show_business_hours',
}
_PRO_FEATURES = _BUSINESS_FEATURES | {
    'show_testimonials', 'show_contact_form', 'show_map', 'show_website_portfolio',
}

PLAN_FEATURE_MAP = {
    'starter': _STARTER_FEATURES,
    'business': _BUSINESS_FEATURES,
    'pro': _PRO_FEATURES,
}

# Reverse lookup: for each feature, what is the minimum plan required?
FEATURE_REQUIRED_PLAN = {}
for _f in {t[0] for t in FEATURE_TOGGLES}:
    if _f in _STARTER_FEATURES:
        FEATURE_REQUIRED_PLAN[_f] = 'starter'
    elif _f in _BUSINESS_FEATURES:
        FEATURE_REQUIRED_PLAN[_f] = 'business'
    else:
        FEATURE_REQUIRED_PLAN[_f] = 'pro'


def get_user_plan_slug(user):
    """Return the active plan slug for a user, or None if no active subscription."""
    try:
        sub = user.subscription
        if sub.is_active():
            return sub.plan.slug
    except Exception:
        pass
    return None


def get_allowed_features(plan_slug):
    """Return the set of feature field names allowed for a given plan slug."""
    if plan_slug is None:
        return _STARTER_FEATURES
    return PLAN_FEATURE_MAP.get(plan_slug, _STARTER_FEATURES)


def is_feature_locked(field, plan_slug):
    """Check if a feature toggle is locked (not available) for the given plan."""
    allowed = get_allowed_features(plan_slug)
    return field not in allowed


@csrf_exempt
@require_POST
def submit_contact_message(request, profile_id):
    """Public endpoint for visitors to send a message via the contact form."""
    from .forms import ContactMessageForm
    profile = get_object_or_404(Profile, pk=profile_id, show_contact_form=True)
    form = ContactMessageForm(request.POST)
    if form.is_valid():
        phone = form.cleaned_data.get('sender_phone', '').strip()
        email = form.cleaned_data.get('sender_email', '').strip()

        # Check for duplicate by phone number
        if phone and profile.contact_messages.filter(sender_phone=phone).exists():
            return JsonResponse({
                'ok': False,
                'duplicate': True,
                'message': 'This phone number is already saved on this account.',
            }, status=409)

        # Check for duplicate by email
        if email and profile.contact_messages.filter(sender_email__iexact=email).exists():
            return JsonResponse({
                'ok': False,
                'duplicate': True,
                'message': 'This email address is already saved on this account.',
            }, status=409)

        msg = form.save(commit=False)
        msg.profile = profile
        msg.save()
        return JsonResponse({'ok': True, 'message': 'Contact saved successfully!'})
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


@login_required
def contact_messages_view(request):
    """Dashboard view – phone book of contacts collected via the public profile."""
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return redirect('profiles:edit_profile')

    contacts = profile.contact_messages.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        contact_id = request.POST.get('contact_id')
        contact = contacts.filter(pk=contact_id).first()
        if contact:
            if action == 'delete':
                contact.delete()
                messages.success(request, 'Contact deleted.')
        return redirect('profiles:contact_messages')

    return render(request, 'dashboard/contact_messages.html', {
        'profile': profile,
        'contacts': contacts,
        'total_count': contacts.count(),
    })


@login_required
def settings_view(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Please create your profile first.')
        return redirect('profiles:edit_profile')

    subscription = None
    try:
        subscription = request.user.subscription
    except Exception:
        pass

    plan_slug = get_user_plan_slug(request.user)
    allowed = get_allowed_features(plan_slug)

    toggles_profile = []
    toggles_extra = []
    for field, label, desc, group in FEATURE_TOGGLES:
        locked = field not in allowed
        item = {
            'field': field,
            'label': label,
            'description': desc,
            'enabled': getattr(profile, field, False),
            'locked': locked,
            'required_plan': FEATURE_REQUIRED_PLAN.get(field, 'pro') if locked else None,
        }
        if group == 'profile':
            toggles_profile.append(item)
        else:
            toggles_extra.append(item)

    return render(request, 'dashboard/settings.html', {
        'profile': profile,
        'subscription': subscription,
        'toggles_profile': toggles_profile,
        'toggles_extra': toggles_extra,
        'plan_slug': plan_slug or 'none',
    })


@login_required
@require_POST
def toggle_feature(request):
    """AJAX endpoint to toggle a profile feature on/off."""
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'No profile'}, status=400)

    field = request.POST.get('field', '')
    valid_fields = {t[0] for t in FEATURE_TOGGLES}
    if field not in valid_fields:
        return JsonResponse({'error': 'Invalid field'}, status=400)

    # Plan-based feature gating: block toggling ON if feature is locked
    plan_slug = get_user_plan_slug(request.user)
    if is_feature_locked(field, plan_slug):
        required = FEATURE_REQUIRED_PLAN.get(field, 'pro').title()
        return JsonResponse({
            'error': f'This feature requires the {required} plan. Please upgrade to unlock it.',
            'locked': True,
            'required_plan': FEATURE_REQUIRED_PLAN.get(field, 'pro'),
        }, status=403)

    current = getattr(profile, field, False)
    setattr(profile, field, not current)
    profile.save(update_fields=[field])

    return JsonResponse({'field': field, 'enabled': not current})


@login_required
def my_card_view(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Please create your profile first.')
        return redirect('profiles:edit_profile')

    nfc_cards = profile.nfc_cards.all()
    has_card = profile.card_front_image or profile.card_back_image or nfc_cards.exists()

    # Get ALL of the user's paid card orders
    from cards.models import CardOrder
    card_orders = (
        CardOrder.objects
        .filter(user=request.user)
        .exclude(status__in=['pending', 'cancelled'])
        .select_related('card_product')
        .prefetch_related('card_product__gallery_images')
        .order_by('-paid_at')
    )
    # Primary card = most recent order (shown in the card showcase)
    card_order = card_orders.first()

    return render(request, 'dashboard/my_card.html', {
        'profile': profile,
        'nfc_cards': nfc_cards,
        'has_card': has_card,
        'card_order': card_order,
        'card_orders': card_orders,
    })


@login_required
def dashboard_home(request):
    from cards.models import CardOrder

    profile = getattr(request.user, 'profile', None)
    tap_count = 0
    last_tap = None
    subscription = None

    if profile:
        tap_count = profile.tap_events.count()
        last_tap = profile.tap_events.first()

    try:
        subscription = request.user.subscription
    except Exception:
        pass

    # Card delivery status for subscription gating
    has_delivered_card = CardOrder.objects.filter(
        user=request.user, status='delivered'
    ).exists()
    has_pending_order = CardOrder.objects.filter(
        user=request.user, status__in=['pending', 'paid', 'shipped']
    ).exists()

    # Prompt user to set their name if missing
    needs_name = not request.user.first_name or not request.user.last_name

    return render(request, 'dashboard/home.html', {
        'profile': profile,
        'tap_count': tap_count,
        'last_tap': last_tap,
        'subscription': subscription,
        'has_delivered_card': has_delivered_card,
        'has_pending_order': has_pending_order,
        'needs_name': needs_name,
    })


@login_required
def update_name(request):
    """Handle the name update form from the dashboard prompt."""
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip().title()
        last_name = request.POST.get('last_name', '').strip().title()
        if first_name and last_name:
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.save(update_fields=['first_name', 'last_name'])
            # Update profile display_name to match
            try:
                profile = request.user.profile
                profile.display_name = f'{first_name} {last_name}'
                profile.save(update_fields=['display_name'])
            except Profile.DoesNotExist:
                pass
    return redirect('profiles:dashboard')


@login_required
def edit_profile(request):
    from .forms import (SkillForm, ExperienceForm, EducationForm, ServiceForm,
                        GalleryImageForm, BusinessHourForm, TestimonialForm,
                        WebsitePortfolioForm, CatalogItemForm)

    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = None

    if request.method == 'POST':
        # AJAX toggle for is_published from settings page
        if 'toggle_published' in request.POST:
            if profile:
                profile.is_published = request.POST.get('toggle_published') == '1'
                profile.save(update_fields=['is_published'])
                return JsonResponse({'ok': True, 'published': profile.is_published})
            return JsonResponse({'ok': False}, status=400)

        section_action = request.POST.get('section_action', '')

        # ── Plan-based gating for section CRUD actions ──
        _ACTION_FEATURE_MAP = {
            'add_skill': 'show_skills', 'delete_skill': 'show_skills',
            'add_experience': 'show_experience', 'edit_experience': 'show_experience', 'delete_experience': 'show_experience',
            'add_education': 'show_education', 'edit_education': 'show_education', 'delete_education': 'show_education',
            'add_service': 'show_services', 'delete_service': 'show_services', 'edit_service': 'show_services',
            'add_gallery_image': 'show_gallery', 'delete_gallery_image': 'show_gallery',
            'save_business_hour': 'show_business_hours', 'delete_business_hour': 'show_business_hours',
            'add_testimonial': 'show_testimonials', 'delete_testimonial': 'show_testimonials',
            'add_website_portfolio': 'show_website_portfolio', 'delete_website_portfolio': 'show_website_portfolio',
            'save_social_links': 'show_social_links',
            'add_catalog_item': 'show_catalog', 'delete_catalog_item': 'show_catalog',
            'add_catalog_category': 'show_catalog', 'delete_catalog_category': 'show_catalog',
        }
        required_feature = _ACTION_FEATURE_MAP.get(section_action)
        if required_feature and is_feature_locked(required_feature, get_user_plan_slug(request.user)):
            req_plan = FEATURE_REQUIRED_PLAN.get(required_feature, 'pro').title()
            messages.error(request, f'This feature requires the {req_plan} plan. Please upgrade to unlock it.')
            return redirect('profiles:edit_profile')

        # ── Skills CRUD ──
        if section_action == 'add_skill' and profile:
            sf = SkillForm(request.POST)
            if sf.is_valid():
                skill = sf.save(commit=False)
                skill.profile = profile
                try:
                    skill.save()
                    messages.success(request, f'Skill "{skill.name}" added!')
                except Exception:
                    messages.warning(request, 'That skill is already on your profile.')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_skill' and profile:
            skill = profile.skills.filter(pk=request.POST.get('skill_id')).first()
            if skill:
                skill.delete()
                messages.success(request, f'Skill removed.')
            return redirect('profiles:edit_profile')

        # ── Experience CRUD ──
        elif section_action == 'add_experience' and profile:
            ef = ExperienceForm(request.POST, request.FILES)
            if ef.is_valid():
                exp = ef.save(commit=False)
                exp.profile = profile
                exp.save()
                messages.success(request, f'Experience added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'edit_experience' and profile:
            exp = profile.experiences.filter(pk=request.POST.get('experience_id')).first()
            if exp:
                ef = ExperienceForm(request.POST, request.FILES, instance=exp)
                if ef.is_valid():
                    ef.save()
                    messages.success(request, 'Experience updated!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_experience' and profile:
            exp = profile.experiences.filter(pk=request.POST.get('experience_id')).first()
            if exp:
                exp.delete()
                messages.success(request, 'Experience deleted.')
            return redirect('profiles:edit_profile')

        # ── Education CRUD ──
        elif section_action == 'add_education' and profile:
            ef = EducationForm(request.POST, request.FILES)
            if ef.is_valid():
                edu = ef.save(commit=False)
                edu.profile = profile
                edu.save()
                messages.success(request, f'Education added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'edit_education' and profile:
            edu = profile.education_entries.filter(pk=request.POST.get('education_id')).first()
            if edu:
                ef = EducationForm(request.POST, request.FILES, instance=edu)
                if ef.is_valid():
                    ef.save()
                    messages.success(request, 'Education updated!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_education' and profile:
            edu = profile.education_entries.filter(pk=request.POST.get('education_id')).first()
            if edu:
                edu.delete()
                messages.success(request, 'Education deleted.')
            return redirect('profiles:edit_profile')

        # ── Services CRUD ──
        elif section_action == 'add_service' and profile:
            sf = ServiceForm(request.POST)
            if sf.is_valid():
                svc = sf.save(commit=False)
                svc.profile = profile
                svc.save()
                messages.success(request, f'Service "{svc.title}" added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'edit_service' and profile:
            svc = profile.services.filter(pk=request.POST.get('service_id')).first()
            if svc:
                sf = ServiceForm(request.POST, instance=svc)
                if sf.is_valid():
                    sf.save()
                    messages.success(request, 'Service updated!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_service' and profile:
            svc = profile.services.filter(pk=request.POST.get('service_id')).first()
            if svc:
                svc.delete()
                messages.success(request, 'Service deleted.')
            return redirect('profiles:edit_profile')

        # ── Gallery CRUD ──
        elif section_action == 'add_gallery_image' and profile:
            gf = GalleryImageForm(request.POST, request.FILES)
            if gf.is_valid():
                img = gf.save(commit=False)
                img.profile = profile
                img.save()
                messages.success(request, 'Image added to gallery!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_gallery_image' and profile:
            img = profile.gallery_images.filter(pk=request.POST.get('gallery_image_id')).first()
            if img:
                img.delete()
                messages.success(request, 'Image removed from gallery.')
            return redirect('profiles:edit_profile')

        # ── Business Hours CRUD ──
        elif section_action == 'save_business_hour' and profile:
            day_val = request.POST.get('day')
            existing = profile.business_hours.filter(day=day_val).first()
            if existing:
                bhf = BusinessHourForm(request.POST, instance=existing)
            else:
                bhf = BusinessHourForm(request.POST)
            if bhf.is_valid():
                bh = bhf.save(commit=False)
                bh.profile = profile
                bh.save()
                messages.success(request, f'{bh.get_day_display()} hours saved!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_business_hour' and profile:
            bh = profile.business_hours.filter(pk=request.POST.get('business_hour_id')).first()
            if bh:
                bh.delete()
                messages.success(request, 'Business hour removed.')
            return redirect('profiles:edit_profile')

        # ── Testimonials CRUD ──
        elif section_action == 'add_testimonial' and profile:
            tf = TestimonialForm(request.POST, request.FILES)
            if tf.is_valid():
                t = tf.save(commit=False)
                t.profile = profile
                t.save()
                messages.success(request, f'Testimonial from "{t.author_name}" added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_testimonial' and profile:
            t = profile.testimonials.filter(pk=request.POST.get('testimonial_id')).first()
            if t:
                t.delete()
                messages.success(request, 'Testimonial removed.')
            return redirect('profiles:edit_profile')

        # ── Website Portfolio CRUD ──
        elif section_action == 'add_website_portfolio' and profile:
            wf = WebsitePortfolioForm(request.POST)
            if wf.is_valid():
                wp = wf.save(commit=False)
                wp.profile = profile
                wp.save()
                messages.success(request, f'Website "{wp.title}" added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_website_portfolio' and profile:
            wp = profile.website_portfolios.filter(pk=request.POST.get('portfolio_id')).first()
            if wp:
                wp.delete()
                messages.success(request, 'Website removed from portfolio.')
            return redirect('profiles:edit_profile')

        # ── Social Links CRUD ──
        elif section_action == 'save_social_links' and profile:
            submitted = {}
            for key, val in request.POST.items():
                if key.startswith('link_') and val.strip():
                    platform = key[5:]
                    submitted[platform] = val.strip()
            profile.social_links.exclude(platform__in=submitted.keys()).delete()
            for idx, (platform, url) in enumerate(submitted.items()):
                SocialLink.objects.update_or_create(
                    profile=profile,
                    platform=platform,
                    defaults={'url': url, 'order': idx},
                )
            messages.success(request, 'Social links updated!')
            return redirect('profiles:edit_profile')

        # ── Catalog CRUD ──
        elif section_action == 'add_catalog_item' and profile:
            cf = CatalogItemForm(request.POST, request.FILES, profile=profile)
            if cf.is_valid():
                item = cf.save(commit=False)
                item.profile = profile
                item.save()
                messages.success(request, f'"{item.title}" added to catalog!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_catalog_item' and profile:
            item = profile.catalog_items.filter(pk=request.POST.get('catalog_item_id')).first()
            if item:
                item.delete()
                messages.success(request, 'Item removed from catalog.')
            return redirect('profiles:edit_profile')

        elif section_action == 'add_catalog_category' and profile:
            name = request.POST.get('cat_name', '').strip()
            if name:
                CatalogCategory.objects.create(profile=profile, name=name)
                messages.success(request, f'Category "{name}" added!')
            return redirect('profiles:edit_profile')

        elif section_action == 'delete_catalog_category' and profile:
            cat = profile.catalog_categories.filter(pk=request.POST.get('cat_id')).first()
            if cat:
                cat.delete()
                messages.success(request, 'Category removed.')
            return redirect('profiles:edit_profile')

        # ── Default: save profile form ──
        else:
            form = ProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
            if form.is_valid():
                profile = form.save(commit=False)
                profile.user = request.user
                # Auto-disable any locked feature toggles (e.g. after plan downgrade)
                plan_slug = get_user_plan_slug(request.user)
                allowed = get_allowed_features(plan_slug)
                for field_name in {t[0] for t in FEATURE_TOGGLES}:
                    if field_name not in allowed and getattr(profile, field_name, False):
                        setattr(profile, field_name, False)
                profile.save()
                form.save_user()
                messages.success(request, 'Profile saved!')
                return redirect('profiles:edit_profile')
    else:
        form = ProfileForm(instance=profile, user=request.user)

    ctx = {
        'form': form,
        'profile': profile,
    }

    if profile:
        ctx['skills'] = profile.skills.all()
        ctx['experiences'] = profile.experiences.all()
        ctx['education_entries'] = profile.education_entries.all()
        ctx['services'] = profile.services.all()
        ctx['gallery_images'] = profile.gallery_images.all()
        ctx['business_hours'] = profile.business_hours.all()
        ctx['testimonials'] = profile.testimonials.all()
        ctx['skill_form'] = SkillForm()
        ctx['experience_form'] = ExperienceForm()
        ctx['education_form'] = EducationForm()
        ctx['service_form'] = ServiceForm()
        ctx['gallery_image_form'] = GalleryImageForm()
        ctx['business_hour_form'] = BusinessHourForm()
        ctx['testimonial_form'] = TestimonialForm()
        ctx['website_portfolios'] = profile.website_portfolios.all()
        ctx['website_portfolio_form'] = WebsitePortfolioForm()
        # Social Links
        existing_links = {link.platform: link.url for link in profile.social_links.all()}
        ctx['social_platforms'] = SocialLink.PLATFORM_CHOICES
        ctx['social_links_existing'] = existing_links
        ctx['social_links_with_urls'] = [
            (val, label, existing_links.get(val, ''))
            for val, label in SocialLink.PLATFORM_CHOICES
        ]
        # Catalog
        ctx['catalog_categories'] = profile.catalog_categories.all()
        ctx['catalog_items'] = profile.catalog_items.all()
        ctx['catalog_form'] = CatalogItemForm(profile=profile)

    return render(request, 'dashboard/edit_profile.html', ctx)


@login_required
def analytics_view(request):
    from collections import Counter
    from django.utils import timezone
    from django.db.models import Count
    import datetime
    from analytics.models import ProfileEvent

    profile = getattr(request.user, 'profile', None)
    events = []
    tap_count = 0
    taps_7d = 0
    taps_30d = 0
    taps_today = 0
    growth_pct = None
    peak_day = None
    peak_day_count = 0
    top_countries = []
    daily_chart = []
    recent_events = []

    # Catalog analytics
    catalog_total_clicks = 0
    catalog_clicks_7d = 0
    catalog_clicks_30d = 0
    catalog_seeall_clicks = 0
    profile_views = 0
    profile_views_7d = 0
    top_products = []
    catalog_daily_chart = []
    contact_clicks = 0
    social_clicks = 0

    if profile:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - datetime.timedelta(days=7)
        month_ago = now - datetime.timedelta(days=30)
        prev_month_start = now - datetime.timedelta(days=60)

        all_events = profile.tap_events.all()
        tap_count = all_events.count()
        taps_today = all_events.filter(timestamp__gte=today_start).count()
        taps_7d = all_events.filter(timestamp__gte=week_ago).count()
        taps_30d = all_events.filter(timestamp__gte=month_ago).count()

        # Growth: compare last 30d vs previous 30d
        prev_30d = all_events.filter(
            timestamp__gte=prev_month_start, timestamp__lt=month_ago
        ).count()
        if prev_30d > 0:
            growth_pct = round(((taps_30d - prev_30d) / prev_30d) * 100)
        elif taps_30d > 0:
            growth_pct = 100

        # Daily chart data (last 14 days)
        for i in range(13, -1, -1):
            day = (now - datetime.timedelta(days=i)).date()
            day_start = timezone.make_aware(
                datetime.datetime.combine(day, datetime.time.min)
            )
            day_end = day_start + datetime.timedelta(days=1)
            count = all_events.filter(
                timestamp__gte=day_start, timestamp__lt=day_end
            ).count()
            daily_chart.append({'date': day, 'count': count, 'label': day.strftime('%d')})
            if count > peak_day_count:
                peak_day_count = count
                peak_day = day

        # Top countries
        countries = all_events.exclude(country='').values_list('country', flat=True)
        country_counts = Counter(countries).most_common(5)
        top_max = country_counts[0][1] if country_counts else 1
        top_countries = [
            {'name': c, 'count': n, 'pct': round((n / top_max) * 100)}
            for c, n in country_counts
        ]

        recent_events = all_events[:20]

        # ── Catalog & Engagement Analytics ──
        pe = profile.profile_events

        # Product clicks
        product_clicks_qs = pe.filter(event_type='product_click')
        catalog_total_clicks = product_clicks_qs.count()
        catalog_clicks_7d = product_clicks_qs.filter(timestamp__gte=week_ago).count()
        catalog_clicks_30d = product_clicks_qs.filter(timestamp__gte=month_ago).count()

        # See All clicks
        catalog_seeall_clicks = pe.filter(event_type='catalog_seeall').count()

        # Profile views (from ProfileEvent)
        profile_views = pe.filter(event_type='profile_view').count()
        profile_views_7d = pe.filter(event_type='profile_view', timestamp__gte=week_ago).count()

        # Contact & social clicks
        contact_clicks = pe.filter(event_type='contact_click').count()
        social_clicks = pe.filter(event_type='social_click').count()

        # Top products by clicks
        top_products_qs = (
            product_clicks_qs
            .values('item_id', 'item_title')
            .annotate(click_count=Count('id'))
            .order_by('-click_count')[:5]
        )
        top_prod_max = 1
        top_products_list = list(top_products_qs)
        if top_products_list:
            top_prod_max = top_products_list[0]['click_count'] or 1
        top_products = [
            {
                'id': p['item_id'],
                'title': p['item_title'] or f'Product #{p["item_id"]}',
                'clicks': p['click_count'],
                'pct': round((p['click_count'] / top_prod_max) * 100),
            }
            for p in top_products_list
        ]

        # Catalog clicks daily chart (last 14 days)
        for i in range(13, -1, -1):
            day = (now - datetime.timedelta(days=i)).date()
            day_start = timezone.make_aware(
                datetime.datetime.combine(day, datetime.time.min)
            )
            day_end = day_start + datetime.timedelta(days=1)
            count = product_clicks_qs.filter(
                timestamp__gte=day_start, timestamp__lt=day_end
            ).count()
            catalog_daily_chart.append({'date': day, 'count': count, 'label': day.strftime('%d')})

    # Calculate chart bar heights (max = 100%)
    max_count = max((d['count'] for d in daily_chart), default=1) or 1
    for d in daily_chart:
        d['pct'] = round((d['count'] / max_count) * 100)

    cat_max = max((d['count'] for d in catalog_daily_chart), default=1) or 1
    for d in catalog_daily_chart:
        d['pct'] = round((d['count'] / cat_max) * 100)

    # Catalog conversion rate: product clicks / profile views
    catalog_conversion = 0
    if profile_views > 0:
        catalog_conversion = round((catalog_total_clicks / profile_views) * 100, 1)

    has_any_data = (tap_count + profile_views + catalog_total_clicks + contact_clicks + social_clicks) > 0

    return render(request, 'dashboard/analytics.html', {
        'profile': profile,
        'tap_count': tap_count,
        'taps_today': taps_today,
        'taps_7d': taps_7d,
        'taps_30d': taps_30d,
        'growth_pct': growth_pct,
        'peak_day': peak_day,
        'peak_day_count': peak_day_count,
        'top_countries': top_countries,
        'daily_chart': daily_chart,
        'recent_events': recent_events,
        # Catalog analytics
        'catalog_total_clicks': catalog_total_clicks,
        'catalog_clicks_7d': catalog_clicks_7d,
        'catalog_clicks_30d': catalog_clicks_30d,
        'catalog_seeall_clicks': catalog_seeall_clicks,
        'profile_views': profile_views,
        'profile_views_7d': profile_views_7d,
        'top_products': top_products,
        'catalog_daily_chart': catalog_daily_chart,
        'catalog_conversion': catalog_conversion,
        'contact_clicks': contact_clicks,
        'social_clicks': social_clicks,
        'has_any_data': has_any_data,
    })


@login_required
def theme_picker(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Please create your profile first.')
        return redirect('profiles:edit_profile')

    if request.method == 'POST':
        profile.color_bg = request.POST.get('color_bg', profile.color_bg)
        profile.color_primary = request.POST.get('color_primary', profile.color_primary)
        profile.color_secondary = request.POST.get('color_secondary', profile.color_secondary)
        profile.color_text = request.POST.get('color_text', profile.color_text)
        profile.color_btn = request.POST.get('color_btn', profile.color_btn)
        profile.color_btn_text = request.POST.get('color_btn_text', profile.color_btn_text)

        # Handle cover image upload
        if 'cover_image' in request.FILES:
            profile.cover_image = request.FILES['cover_image']
        elif request.POST.get('remove_cover') == '1':
            profile.cover_image = ''

        profile.save()
        messages.success(request, 'Theme saved!')
        return redirect('profiles:theme_picker')

    social_links = profile.social_links.all()

    return render(request, 'dashboard/theme_picker.html', {
        'profile': profile,
        'social_links': social_links,
    })


@login_required
@require_POST
def theme_save_ajax(request):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'No profile'}, status=400)

    COLOR_FIELDS = ['color_bg', 'color_primary', 'color_secondary',
                    'color_text', 'color_btn', 'color_btn_text']
    for field in COLOR_FIELDS:
        val = request.POST.get(field)
        if val and val.startswith('#') and len(val) == 7:
            setattr(profile, field, val)
    profile.save()
    return JsonResponse({'ok': True})


@login_required
def social_links_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')


@login_required
def catalog_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')


@login_required
def catalog_item_detail(request, item_id):
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, 'Please create your profile first.')
        return redirect('profiles:edit_profile')

    item = CatalogItem.objects.filter(id=item_id, profile=profile).first()
    if not item:
        messages.error(request, 'Item not found.')
        return redirect('profiles:catalog')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'update_item':
            form = CatalogItemForm(request.POST, request.FILES, instance=item, profile=profile)
            if form.is_valid():
                form.save()
                messages.success(request, 'Item updated!')
                return redirect('profiles:catalog_item_detail', item_id=item.id)

        elif action == 'change_image':
            new_img = request.FILES.get('new_image')
            if new_img:
                item.image = new_img
                item.save(update_fields=['image'])
                messages.success(request, 'Image updated!')
            return redirect('profiles:catalog_item_detail', item_id=item.id)

        elif action == 'add_images':
            extra_files = request.FILES.getlist('extra_images')
            next_order = item.extra_images.count()
            for i, f in enumerate(extra_files):
                CatalogItemImage.objects.create(item=item, image=f, order=next_order + i)
            count = len(extra_files)
            if count:
                messages.success(request, f'{count} image{"s" if count > 1 else ""} added!')
            return redirect('profiles:catalog_item_detail', item_id=item.id)

        elif action == 'delete_image':
            img_id = request.POST.get('image_id')
            CatalogItemImage.objects.filter(id=img_id, item=item).delete()
            messages.success(request, 'Image removed.')
            return redirect('profiles:catalog_item_detail', item_id=item.id)

        elif action == 'delete_item':
            item.delete()
            messages.success(request, 'Item deleted.')
            return redirect('profiles:catalog')
    else:
        form = CatalogItemForm(instance=item, profile=profile)

    # Remove image field from edit form — image is changed via the hero camera button
    if 'image' in form.fields:
        del form.fields['image']

    extra_images = item.extra_images.all()

    return render(request, 'dashboard/catalog_item_detail.html', {
        'profile': profile,
        'item': item,
        'form': form,
        'extra_images': extra_images,
    })


@login_required
def services_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')


@login_required
def skills_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')


@login_required
def experience_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')


@login_required
def education_view(request):
    """Redirect to consolidated edit profile page."""
    return redirect('profiles:edit_profile')
