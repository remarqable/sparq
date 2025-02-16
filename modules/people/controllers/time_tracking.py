# -----------------------------------------------------------------------------
# sparQ
#
# Description:
#     People module controllers for time tracking functionality.
#
# Copyright (c) 2025 remarQable LLC
#
# This software is released under an open-source license.
# See the LICENSE file for details.
# -----------------------------------------------------------------------------

from flask import render_template
from flask_login import login_required

from . import blueprint


@blueprint.route("/time_tracking")
@login_required
def time_tracking():
    """Time tracking page (coming soon)"""
    return render_template(
        "people-coming-soon-mobile.html",
        active_page="time_tracking",
        title="Time Tracking",
        module_home="people_bp.people_home",
    )
