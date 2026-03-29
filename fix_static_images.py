#!/usr/bin/env python
import os
import re
import glob

html_files = glob.glob(r'c:\Users\PROBOOK\Documents\solutions\templates\pages\home\*.html')

for file in html_files:
    if 'index.html' in file:
        continue
    
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace image src references  
    # First replace src="images/file.png" with src="{% static './home/images/file.png' %}"
    content = re.sub(r'src="images/', r'src="{% static \'./home/images/', content)
    content = re.sub(r'(\.png|\.svg|\.jpg)\"', r"\1' %}", content)
    
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)

print('Fixed image references in all HTML files')
