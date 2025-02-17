# -----------------------------------------------------------------------------
# sparQ
#
# Description:
#     Core module route handlers and view logic. Implements authentication,
#     user management, and system settings functionality.
#
# Copyright (c) 2025 remarQable LLC
#
# This software is released under an open-source license.
# See the LICENSE file for details.
# -----------------------------------------------------------------------------

import importlib
import os
import sys
from functools import wraps

from flask import Blueprint
from flask import current_app
from flask import flash
from flask import g
from flask import jsonify
from flask import make_response
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from system.db.database import db
from system.i18n.translation import _  # Use our existing translation module

from ..models.group import Group
from ..models.user import User
from ..models.user_setting import UserSetting

# Create blueprint
blueprint = Blueprint(
    "core_bp", __name__, template_folder="../views/templates", static_folder="../views/assets"
)


@blueprint.before_request
def before_request():
    """Set cache control headers to prevent caching"""
    if request.endpoint != 'static':
        g.cache_control = 'no-cache, no-store, must-revalidate'
        g.pragma = 'no-cache'
        g.expires = '0'


def admin_required(f):
    """Decorator to require admin access for a route"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required", "error")
            return redirect(url_for("core_bp.login"))
        return f(*args, **kwargs)

    return decorated_function


@blueprint.route("/")
@login_required
def index():
    """Redirect root to functions page"""
    return redirect(url_for("people_bp.functions"))

def is_mobile():
    """Check if the current request is from a mobile device"""
    user_agent = request.user_agent.string.lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'webos']
    return any(keyword in user_agent for keyword in mobile_keywords)

@blueprint.route("/login", methods=["GET", "POST"])
def login():
    # Redirect if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for("people_bp.functions" if is_mobile() else "people_bp.people_home"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        remember = bool(request.form.get("remember"))

        user = User.get_by_email(email)
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            # Ensure the next page is safe and default to appropriate page based on device
            if not next_page or not next_page.startswith("/"):
                next_page = url_for("people_bp.functions" if is_mobile() else "people_bp.people_home")
            return redirect(next_page)

        flash("Invalid email or password", "error")

    return render_template("login-desktop.html")


@blueprint.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("core_bp.login"))


@blueprint.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")

        if User.get_by_email(email):
            flash("Email already registered", "error")
            return render_template("register.html")

        try:
            User.create(email=email, password=password, first_name=first_name, last_name=last_name)
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("core_bp.login"))
        except Exception:
            flash("Registration failed", "error")

    return render_template("register.html")


SUPPORTED_LANGUAGES = {"en": "English", "es": "Español", "nl": "Nederlands"}


@blueprint.route("/settings/language", methods=["POST"])
@login_required
def update_language():
    lang = request.form.get("language")
    if lang in SUPPORTED_LANGUAGES:
        session["lang"] = lang
        if current_user.is_authenticated:
            UserSetting.set(current_user.id, "language", lang)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid language"}), 400


@blueprint.route("/settings")
@login_required
def settings():
    """Settings page"""
    return render_template(
        "settings/index.html",
        title="Settings",
        languages=SUPPORTED_LANGUAGES,
        current_language=session.get("lang", "en"),
        module_name="Settings",
        module_icon="fa-solid fa-cog",
        module_home="core_bp.settings",
    )


@blueprint.route("/settings/apps")
@login_required
@admin_required
def manage_apps():
    """Apps management page"""
    modules_dir = "modules"
    modules = []

    for module_name in os.listdir(modules_dir):
        module_path = os.path.join(modules_dir, module_name)

        if os.path.isdir(module_path) and not module_name.startswith("__"):
            try:
                # Load the manifest
                manifest = importlib.import_module(f"modules.{module_name}.__manifest__").manifest

                # Check if module is disabled
                disabled_file = os.path.join(module_path, "__DISABLED__")
                manifest["enabled"] = not os.path.exists(disabled_file)

                modules.append(manifest)
            except Exception as e:
                print(f"Error loading manifest for {module_name}: {e}")

    return render_template(
        "settings/apps.html",
        modules=sorted(modules, key=lambda x: x["name"]),
        module_name="Settings",
        module_icon="fa-solid fa-cog",
        module_home="core_bp.settings",
        installed_modules=g.installed_modules,
    )


@blueprint.route("/api/modules/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_module():
    """Toggle module enabled/disabled state"""
    data = request.get_json()
    module_name = data.get("module")
    enabled = data.get("enabled")

    if not module_name:
        return jsonify({"error": "Module name required"}), 400

    module_path = os.path.join("modules", module_name)
    disabled_file = os.path.join(module_path, "__DISABLED__")

    try:
        if enabled and os.path.exists(disabled_file):
            os.remove(disabled_file)
        elif not enabled and not os.path.exists(disabled_file):
            open(disabled_file, "a").close()

        # After toggling, trigger a restart
        if current_app.debug:
            main_app_file = os.path.abspath(sys.modules["__main__"].__file__)
            print(f"Debug mode: Triggering reload by touching {main_app_file}")
            os.utime(main_app_file, None)

        return jsonify(
            {
                "success": True,
                "message": f"Module {module_name} {'enabled' if enabled else 'disabled'}. Restarting application...",
            }
        )
    except Exception as e:
        print(f"Error toggling module: {e}")
        print(f"Error type: {type(e)}")
        return jsonify({"error": str(e)}), 500


@blueprint.route("/restart")
@login_required
def system_restart():
    """Restart the application"""
    if current_user.is_admin:
        python = sys.executable
        os.execl(python, python, *sys.argv)
    return redirect(url_for("core_bp.index"))


@blueprint.route("/exception")
@login_required
@admin_required
def test_exception():
    """Test route to trigger a 500 error page"""
    # Deliberately raise an exception
    raise Exception("This is a test exception to verify the 500 error page functionality")


@blueprint.app_errorhandler(500)
def handle_500_error(e):
    """Handle internal server errors"""
    # Set up error context
    g.current_module = {
        "name": "Error",
        "color": "#dc3545",  # Bootstrap danger color
        "icon_class": "fas fa-exclamation-triangle",
    }
    g.installed_modules = []

    return render_template(
        "errors/500.html",
        error=str(e),
        module_name="Error",
        module_icon="fas fa-exclamation-triangle",
        module_home="core_bp.index",
    ), 500


@blueprint.app_errorhandler(404)
def handle_404_error(e):
    """Handle 404 errors"""
    # Set up error context
    g.current_module = {
        "name": "Error",
        "color": "#dc3545",
        "icon_class": "fas fa-exclamation-triangle",
    }
    g.installed_modules = []

    return render_template(
        "errors/404.html",
        error=str(e),
        module_name="Error",
        module_icon="fas fa-exclamation-triangle",
        module_home="core_bp.index",
    ), 404


@blueprint.route("/language/<lang_code>", methods=["POST"])
@login_required
def change_language(lang_code):
    """Change user's language preference"""
    if lang_code not in current_app.config["LANGUAGES"]:
        return jsonify({"error": "Invalid language code"}), 400

    try:
        if current_user.update_setting("language", lang_code):
            session["language"] = lang_code
            return jsonify({"success": True})
        return jsonify({"error": "Failed to update language setting"}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@blueprint.route("/settings/groups")
@login_required
@admin_required
def manage_groups():
    """Group management page"""
    users = User.query.filter(User.email != "admin").all()
    groups = Group.query.all()
    return render_template(
        "settings/groups.html",
        users=users,
        groups=groups,
        module_name="Settings",
        module_icon="fa-solid fa-cog",
        module_home="core_bp.settings",
    )


@blueprint.route("/settings/groups/<int:user_id>")
@login_required
@admin_required
def get_user_groups(user_id):
    """Get user's current group IDs"""
    user = User.query.get_or_404(user_id)
    return jsonify({"groups": [group.id for group in user.groups]})


@blueprint.route("/settings/groups/users/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def update_user_groups(user_id):
    """Update user's group memberships"""
    try:
        user = User.query.get_or_404(user_id)

        # Get selected group IDs
        group_ids = request.form.getlist("groups[]")

        # Validate group IDs
        if not group_ids:
            return jsonify({"success": False, "error": _("Please select at least one group")})

        groups = Group.query.filter(Group.id.in_(group_ids)).all()

        # Verify all groups exist
        if len(groups) != len(group_ids):
            return jsonify({"success": False, "error": _("One or more invalid groups selected")})

        # Check admin group changes
        admin_group = Group.get_admin_group()
        if admin_group in user.groups and admin_group not in groups:
            # Count other admin users
            admin_count = User.query.filter(User.groups.any(id=admin_group.id)).count()
            if admin_count <= 1:
                return jsonify({"success": False, "error": _("Cannot remove last admin user")})

        # Update user's groups
        user.groups = groups
        db.session.commit()

        response = make_response()
        response.headers["HX-Redirect"] = url_for("core_bp.manage_groups")
        return response

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


@blueprint.route("/settings/groups/<int:group_id>/details")
@login_required
@admin_required
def get_group_details(group_id):
    """Get group details for editing"""
    group = Group.query.get_or_404(group_id)
    return jsonify({"name": group.name, "description": group.description})


@blueprint.route("/settings/groups/modal/new")
@login_required
@admin_required
def create_group_modal():
    return render_template(
        "settings/_group_modal.html",
        title=_("New Group"),
        url=url_for("core_bp.save_group"),
        group=None,
    )


@blueprint.route("/settings/groups/modal/<int:group_id>")
@login_required
@admin_required
def edit_group_modal(group_id):
    group = Group.query.get_or_404(group_id)
    return render_template(
        "settings/_group_modal.html",
        title=_("Edit Group"),
        url=url_for("core_bp.update_group", group_id=group_id),
        group=group,
    )


@blueprint.route("/settings/groups/users/<int:user_id>/modal")
@login_required
@admin_required
def edit_user_groups_modal(user_id):
    user = User.query.get_or_404(user_id)
    groups = Group.query.all()
    return render_template("settings/_edit_user_groups_modal.html", user=user, groups=groups)


@blueprint.route("/settings/groups/manage/new", methods=["POST"])
@login_required
@admin_required
def save_group():
    try:
        name = request.form.get("name")
        description = request.form.get("description")

        if not name:
            return jsonify({"success": False, "error": _("Name is required")})

        # Create new group
        group = Group(name=name, description=description)
        db.session.add(group)
        db.session.commit()

        response = make_response()
        response.headers["HX-Redirect"] = url_for("core_bp.manage_groups")
        return response

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@blueprint.route("/settings/groups/<int:group_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_group(group_id):
    """Delete group"""
    try:
        group = Group.query.get_or_404(group_id)
        if group.is_system:
            raise ValueError("Cannot delete system groups")

        db.session.delete(group)
        db.session.commit()
        response = make_response()
        response.headers["HX-Redirect"] = url_for("core_bp.manage_groups")
        return response
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)})


@blueprint.route("/settings/groups/manage/<int:group_id>", methods=["POST"])
@login_required
@admin_required
def update_group(group_id):
    try:
        group = Group.query.get_or_404(group_id)
        name = request.form.get("name")
        description = request.form.get("description")

        if not name:
            return jsonify({"success": False, "error": _("Name is required")})

        group.name = name
        group.description = description
        db.session.commit()

        response = make_response()
        response.headers["HX-Redirect"] = url_for("core_bp.manage_groups")
        return response

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@blueprint.route("/settings/groups/clear-modal")
@login_required
@admin_required
def clear_modal():
    return ""
