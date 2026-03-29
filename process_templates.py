#!/usr/bin/env python3
import os
import re

base_dir = r'c:\Users\PROBOOK\Documents\solutions\templates\pages\home'
files_to_process = [
    'about.html', 'contact.html', 'sign-in.html', 'reviews.html',
    'pricing.html', 'sign-up.html', 'blog-list.html', 'blog-detail.html', 'index.html'
]

def extract_title(content):
    """Extract title from the HTML content"""
    match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return 'HTML'

def process_file(filepath):
    """Process a single HTML file to extend base.html"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract the title
    title = extract_title(content)
    
    # Find where the actual page content starts
    # Look for the first major section after the header
    
    # Find header closing tag and footer opening tag
    header_end_match = re.search(r'</header>\s*', content, re.IGNORECASE | re.DOTALL)
    footer_start_match = re.search(r'<!-- Footer-Section start -->|<footer', content, re.IGNORECASE | re.DOTALL)
    
    # Handle regular pages with headers and footers
    if header_end_match and footer_start_match:
        header_end_pos = header_end_match.end()
        footer_start_pos = footer_start_match.start()
        
        # Extract the middle content
        middle_content = content[header_end_pos:footer_start_pos].strip()
        
        # Build new content using string concatenation
        new_content = "{% extends 'pages/home/base.html' %}\n\n"
        new_content += "{% block title %}" + title + "{% endblock %}\n\n"
        new_content += "{% block content %}\n"
        new_content += middle_content + "\n"
        new_content += "{% endblock %}\n"
        
        # Write back to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True
    
    # Handle special pages like sign-in and sign-up (no standard header/footer)
    # Find page_wrapper or the first main content section
    page_wrapper_match = re.search(r'<!-- Page-wrapper-Start -->(.+?)<!-- Page-wrapper-End -->', content, re.IGNORECASE | re.DOTALL)
    if page_wrapper_match:
        middle_content = page_wrapper_match.group(1).strip()
        # Remove Preloader from inner content (it's in base now)
        middle_content = re.sub(r'<!-- Preloader -->.*?</div>\s*', '', middle_content, flags=re.IGNORECASE | re.DOTALL)
        
        # Build new content
        new_content = "{% extends 'pages/home/base.html' %}\n\n"
        new_content += "{% block title %}" + title + "{% endblock %}\n\n"
        new_content += "{% block content %}\n"
        new_content += middle_content + "\n"
        new_content += "{% endblock %}\n"
        
        # Write back to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True
    
    return False

# Process all files
for filename in files_to_process:
    filepath = os.path.join(base_dir, filename)
    if os.path.exists(filepath):
        if process_file(filepath):
            print(f"✓ Updated {filename}")
        else:
            print(f"✗ Failed to process {filename}")
    else:
        print(f"✗ File not found: {filename}")

print("\nAll files processed!")
