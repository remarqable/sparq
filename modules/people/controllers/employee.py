# -----------------------------------------------------------------------------
# sparQ
#
# Description:
#     People module controllers for employee management.
#
# Copyright (c) 2025 remarQable LLC
#
# This software is released under an open-source license.
# See the LICENSE file for details.
# -----------------------------------------------------------------------------

import logging

from flask import flash
from flask import g
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required

from modules.core.models.group import Group
from modules.core.models.user import User
from modules.people.decorators import admin_required
from modules.people.models.employee import Employee
from modules.people.models.employee import EmployeeStatus
from modules.people.models.employee import EmployeeType
from system.db.database import db

from . import blueprint

logger = logging.getLogger(__name__)


def is_mobile():
    """Check if the current request is from a mobile device"""
    user_agent = request.user_agent.string.lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'webos']
    return any(keyword in user_agent for keyword in mobile_keywords)


@blueprint.route("/")
@login_required
def people_home():
    """People dashboard page"""
    template = "dashboard/index-mobile.html" if is_mobile() else "dashboard/index-desktop.html"
    return render_template(
        template,
        title=g.current_module["name"],
        module_name=g.current_module["name"],
        module_icon=g.current_module["icon_class"],
        page_icon=g.current_module["icon_class"],
        icon_color=g.current_module["color"],
        module_home="people_bp.people_home",
        installed_modules=g.installed_modules,
    )


@blueprint.route("/dashboard")
@login_required
def dashboard():
    """People dashboard page"""
    template = "dashboard/index-mobile.html" if is_mobile() else "dashboard/index-desktop.html"
    return render_template(
        template, 
        active_page="dashboard", 
        module_home="people_bp.people_home"
    )


@blueprint.route("/employees")
@login_required
def employees():
    """Employees list page"""
    users = User.query.join(Employee).filter(User.email != "admin").all()
    template = "employees/employees-mobile.html" if is_mobile() else "employees/index-desktop.html"
    return render_template(
        template,
        active_page="employees",
        users=users,
        module_home="people_bp.people_home",
    )


@blueprint.route("/employees/new", methods=["GET"])
@login_required
@admin_required
def new_employee():
    """Show new employee form"""
    # Get all employees as potential managers
    potential_managers = Employee.query.join(User).order_by(User.first_name).all()

    return render_template(
        "employees/form-desktop.html",
        title="New Employee",
        employee=None,
        employee_types=EmployeeType,
        potential_managers=potential_managers,
        module_home="people_bp.people_home",
    )


@blueprint.route("/employees", methods=["POST"])
@login_required
@admin_required
def create_employee():
    """Create a new employee"""
    try:
        # Validate required fields
        email = request.form.get("email")
        if not email:
            flash("Email is required", "error")
            return redirect(url_for("people_bp.new_employee"))

        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists", "error")
            return redirect(url_for("people_bp.new_employee"))

        # Create user
        user = User.create(
            email=email,
            password=request.form.get("password"),
            first_name=request.form.get("first_name", ""),
            last_name=request.form.get("last_name", ""),
            is_admin=bool(request.form.get("is_admin", False)),
        )

        # Create employee profile
        employee = Employee(
            user_id=user.id,
            department=request.form.get("department", ""),
            position=request.form.get("position", ""),
            type=EmployeeType[request.form.get("type", "FULL_TIME")],
            status=EmployeeStatus.ACTIVE,
        )

        # Add manager if selected
        manager_id = request.form.get("manager_id")
        if manager_id:
            employee.manager_id = int(manager_id)

        db.session.add(employee)
        db.session.commit()

        flash("Employee created successfully", "success")
        return redirect(url_for("people_bp.employees"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error creating employee: {str(e)}", "error")
        return redirect(url_for("people_bp.new_employee"))


@blueprint.route("/employees/<int:employee_id>/edit", methods=["GET"])
@login_required
@admin_required
def edit_employee(employee_id):
    """Show edit employee form"""
    employee = Employee.query.get_or_404(employee_id)
    potential_managers = Employee.query.join(User).order_by(User.first_name).all()

    # Get admin count if the employee is an admin
    admin_count = 0
    if employee.user.is_admin:
        admin_count = User.query.filter(User.groups.any(name="ADMIN")).count()

    return render_template(
        "employees/form-desktop.html",
        title="Edit Employee",
        employee=employee,
        employee_types=EmployeeType,
        potential_managers=potential_managers,
        admin_count=admin_count,
        module_home="people_bp.people_home",
    )


@blueprint.route("/employees/<int:employee_id>", methods=["POST"])
@login_required
@admin_required
def update_employee(employee_id):
    """Update an employee"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        user = employee.user

        # Handle admin status changes
        is_admin = request.form.get("is_admin") == "on"
        if user.is_admin and not is_admin:
            # Count other admin users
            admin_count = User.query.filter(User.groups.any(name="ADMIN")).count()
            if admin_count <= 1:
                flash("Cannot remove admin status from the only administrator", "error")
                return redirect(url_for("people_bp.edit_employee", employee_id=employee_id))

        # Update admin status if changed
        if is_admin != user.is_admin:
            admin_group = Group.get_admin_group()
            if is_admin:
                user.add_to_group(admin_group)
            else:
                user.remove_from_group(admin_group)

        # Update other fields...

        db.session.commit()
        flash("Employee updated successfully", "success")
        return redirect(url_for("people_bp.employee_detail", employee_id=employee_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error updating employee: {str(e)}", "error")
        return redirect(url_for("people_bp.edit_employee", employee_id=employee_id))


@blueprint.route("/employees/<int:employee_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_employee(employee_id):
    """Delete an employee"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        user = employee.user

        db.session.delete(employee)
        db.session.delete(user)
        db.session.commit()

        flash("Employee deleted successfully", "success")
        return redirect(url_for("people_bp.employees"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting employee: {str(e)}", "error")
        return redirect(url_for("people_bp.employees"))


@blueprint.route("/employees/<int:employee_id>/delete-modal", methods=["GET"])
@login_required
@admin_required
def delete_modal(employee_id):
    """Show delete confirmation modal"""
    return render_template("employees/delete-modal.html", employee_id=employee_id)


@blueprint.route("/employees/<int:employee_id>")
@login_required
def employee_detail(employee_id):
    """Show employee details"""
    employee = Employee.query.get_or_404(employee_id)

    # Check if user is admin or viewing their own profile
    is_admin = current_user.is_admin
    is_self = current_user.id == employee.user_id

    # If not admin and not viewing own profile, show limited view
    if not is_admin and not is_self:
        return render_template(
            "employees/employee-view/details.html",  # Limited view template
            employee=employee,
            module_home="people_bp.people_home",
        )

    # Admin or self view gets full details
    return render_template(
        "employees/admin-view/details.html",  # Full admin view template
        employee=employee,
        module_home="people_bp.people_home",
    )


@blueprint.route("/employee/<int:user_id>/groups")
@login_required
@admin_required
def get_user_groups(user_id):
    """Get user's groups and all available groups"""
    user = User.query.get_or_404(user_id)
    all_groups = Group.query.all()

    return jsonify(
        {
            "groups": [
                {"id": group.id, "name": group.name, "is_member": group in user.groups}
                for group in all_groups
            ]
        }
    )


@blueprint.route("/employee/<int:user_id>/groups", methods=["POST"])
@login_required
@admin_required
def update_user_groups(user_id):
    """Update user's group memberships"""
    try:
        user = User.query.get_or_404(user_id)

        # Get selected group IDs
        group_ids = request.form.getlist("groups")
        groups = Group.query.filter(Group.id.in_(group_ids)).all()

        # Get ALL group
        all_group = Group.get_all_group()
        if all_group not in groups:
            groups.append(all_group)

        # Check admin group changes
        admin_group = Group.get_admin_group()
        if admin_group in user.groups and admin_group not in groups:
            # Count other admin users
            admin_count = User.query.filter(User.groups.any(id=admin_group.id)).count()
            if admin_count <= 1:
                raise ValueError("Cannot remove last admin user")

        # Update user's groups
        user.groups = groups
        db.session.commit()

        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


@blueprint.route("/functions")
@login_required
def functions():
    """Functions page"""
    template = "functions/index-mobile.html" if is_mobile() else "functions/index-desktop.html"
    return render_template(
        template,
        active_page="functions",
        module_home="people_bp.people_home"
    )


@blueprint.route("/profile")
@login_required
def profile():
    """User profile page"""
    template = "profile/profile-mobile.html" if is_mobile() else "profile/index-desktop.html"
    return render_template(
        template,
        active_page="profile",
        module_home="people_bp.people_home"
    )
