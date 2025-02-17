Simple layout for modules

```html
{% extends "base-desktop.html" %}

{% block title %}{{ _("Dashboard") }}{% endblock %}

{% block app_class %}people-app{% endblock %}

{% block additional_styles %}
<link rel="stylesheet" href="{{ url_for('people_bp.static', filename='css/people.css') }}">
{% endblock %}

{% block content %}
  <div class="d-flex">
    <!-- Left Navigation -->
    <div class="col-md-2 mt-2">
        {% include 'people_nav.html' with context %}
    </div>

    <!-- Right Content Area -->
    <div class="col-md-10">
      <div class="content-wrapper" style="max-width: 1024px; margin-left: 10;">
        <!-- Your right content goes here -->
      </div>
    </div>
  </div>
</div>
{% endblock %} 
```
