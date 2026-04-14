from django.contrib import messages
from django.core.mail import mail_admins
from django.shortcuts import render, redirect
from cards.views import tap_redirect
from profiles.views import public_profile
from .forms import ContactForm


def _redirect_if_authenticated(request):
    """Return a redirect response if the user is logged in, else None."""
    if request.user.is_authenticated:
        return redirect('profiles:dashboard')
    return None


def home(request):
    # If request is coming from a subdomain, serve the public profile
    if request.subdomain:
        return public_profile(request)
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    from .models import BlogPost, VideoTestimonial, PartnerLogo
    from subscriptions.models import Plan
    blog_posts = BlogPost.objects.filter(status='published').select_related('author')[:2]
    video_testimonials = VideoTestimonial.objects.filter(is_active=True)
    partner_logos = PartnerLogo.objects.filter(is_active=True)
    
    # Handle HomepageTestimonial - table might not exist yet
    homepage_testimonials = []
    try:
        from profiles.models import HomepageTestimonial
        homepage_testimonials = HomepageTestimonial.objects.filter(is_active=True).order_by('order', '-created_at')
    except Exception:
        # Table doesn't exist yet, use empty list
        pass
    
    plans = Plan.objects.all()
    return render(request, 'pages/home/index.html', {
        'blog_posts': blog_posts,
        'video_testimonials': video_testimonials,
        'homepage_testimonials': homepage_testimonials,
        'partner_logos': partner_logos,
        'plans': plans,
    })


def tap_redirect_proxy(request, card_uid):
    return tap_redirect(request, card_uid)


def about(request):
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    return render(request, 'pages/about.html')

def pricing(request):
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    from subscriptions.models import Plan
    plans = Plan.objects.all()
    return render(request, 'pages/home/pricing.html', {'plans': plans})


def features(request):
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    return render(request, 'pages/home/features.html')


def reviews(request):
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    return render(request, 'pages/home/reviews.html')




def blog(request):
    from .models import BlogPost
    posts = BlogPost.objects.filter(status='published').select_related('author')
    category = request.GET.get('category')
    if category:
        posts = posts.filter(category=category)
    return render(request, 'pages/home/blog-list.html', {
        'posts': posts,
        'current_category': category or 'all',
        'categories': BlogPost.CATEGORY_CHOICES,
    })


def blog_detail(request, slug):
    from django.shortcuts import get_object_or_404
    from .models import BlogPost, BlogComment
    post = get_object_or_404(BlogPost, slug=slug, status='published')
    post.views_count += 1
    post.save(update_fields=['views_count'])

    # Handle comment submission
    comment_submitted = False
    if request.method == 'POST':
        author_name = request.POST.get('author_name', '').strip()
        author_email = request.POST.get('author_email', '').strip()
        body = request.POST.get('body', '').strip()
        if author_name and author_email and body:
            BlogComment.objects.create(
                post=post,
                author_name=author_name,
                author_email=author_email,
                body=body,
            )
            comment_submitted = True

    comments = post.comments.filter(is_approved=True)
    related_posts = (
        BlogPost.objects.filter(status='published', category=post.category)
        .exclude(pk=post.pk)[:3]
    )
    return render(request, 'pages/home/blog-detail.html', {
        'post': post,
        'related_posts': related_posts,
        'comments': comments,
        'comment_submitted': comment_submitted,
    })


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your message has been sent! We\'ll get back to you soon.')
            return redirect('core:contact')
    else:
        form = ContactForm()

    template = 'dashboard/contact.html' if request.user.is_authenticated else 'pages/contact.html'
    return render(request, template, {'form': form})


def faq(request):
    redir = _redirect_if_authenticated(request)
    if redir:
        return redir
    return render(request, 'pages/faq.html')


def privacy(request):
    return render(request, 'pages/privacy.html')


def terms(request):
    return render(request, 'pages/terms.html')


def error_404(request, exception=None):
    """Custom 404 error handler."""
    try:
        return render(request, '404.html', status=404)
    except Exception:
        # Try standalone template (no database dependencies)
        try:
            return render(request, 'errors/404_standalone.html', status=404)
        except Exception:
            # Ultimate fallback - plain HTML
            from django.http import HttpResponse
            return HttpResponse(
                '<h1>404 - Page Not Found</h1><p>The page you requested could not be found.</p><a href="/">Go Home</a>',
                status=404,
                content_type='text/html'
            )


def error_500(request):
    """Custom 500 error handler."""
    try:
        return render(request, '500.html', status=500)
    except Exception:
        # Try standalone template (no database dependencies)
        try:
            return render(request, 'errors/500_standalone.html', status=500)
        except Exception:
            # Ultimate fallback - plain HTML
            from django.http import HttpResponse
            return HttpResponse(
                '<h1>500 - Server Error</h1><p>Something went wrong. Please try again later.</p><a href="/">Go Home</a>',
                status=500,
                content_type='text/html'
            )


def error_403(request, exception=None):
    """Custom 403 error handler."""
    try:
        return render(request, '403.html', status=403)
    except Exception:
        # Try standalone template (no database dependencies)
        try:
            return render(request, 'errors/403_standalone.html', status=403)
        except Exception:
            # Ultimate fallback - plain HTML
            from django.http import HttpResponse
            return HttpResponse(
                '<h1>403 - Access Denied</h1><p>You do not have permission to access this page.</p><a href="/">Go Home</a>',
                status=403,
                content_type='text/html'
            )
