# -----------------------------------------------------------------------------
# sparQ
#
# Description:
#     People module controllers for hiring functionality.
#
# Copyright (c) 2025 remarQable LLC
#
# This software is released under an open-source license.
# See the LICENSE file for details.
# -----------------------------------------------------------------------------

from flask import render_template
from flask_login import login_required

from . import blueprint


@blueprint.route("/hiring")
@login_required
def hiring():
    return render_template(
        "people-coming-soon-mobile.html",
        active_page="hiring",
        title="Hiring",
        module_home="people_bp.people_home",
    )
