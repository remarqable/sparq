# -----------------------------------------------------------------------------
# sparQ
#
# Description:
#     Nickname module class that implements nickname functionality.
#     Handles route registration and blueprint registration.
#
# Copyright (c) 2025 remarQable LLC
#
# This software is released under an open-source license.
# See the LICENSE file for details.
# -----------------------------------------------------------------------------

from flask import Blueprint
from pluggy import HookimplMarker

from .models import EmployeeNickname
from .models import NicknameModel

hookimpl = HookimplMarker("sparqone")


class NicknameModule:
    def __init__(self):
        self.blueprint = Blueprint("nickname_bp", __name__)
        self.model = NicknameModel()
        self.setup_routes()

    def setup_routes(self):
        @self.blueprint.route("/")
        def nickname_home():
            return {"message": "Nickname Module Home"}

    @hookimpl
    def get_routes(self):
        return [(self.blueprint, "/nickname")]

    @hookimpl
    def modify_new_employee_form(self):
        """Add nickname field to new employee form"""
        js = """
        <script>
            function addField(fieldHtml) {
                const lastNameField = document.querySelector('#last_name').closest('.mb-3');
                const div = document.createElement('div');
                div.className = 'mb-3';
                div.innerHTML = fieldHtml.trim();
                lastNameField.insertAdjacentElement('afterend', div);
            }

            document.addEventListener('DOMContentLoaded', function() {
                addField(`
                    <label for="nickname" class="fw-medium text-body-secondary">Nickname</label>
                    <input type="text" 
                           class="form-control" 
                           id="nickname" 
                           name="nickname" 
                           placeholder="Enter nickname">
                `);
            });
        </script>
        """
        return [js]

    @hookimpl
    def process_new_employee(self, form_data, employee):
        """Process nickname when a new employee is created"""
        if "nickname" in form_data and form_data["nickname"]:
            EmployeeNickname.create_or_update(employee, form_data["nickname"])
